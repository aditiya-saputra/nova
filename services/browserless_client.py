import re
import html
import hashlib
import asyncio
import socket
from urllib.parse import urlparse, urljoin
from utils.logger import get_logger

logger = get_logger(__name__)

# Dangerous patterns for prompt injection
INJECTION_PATTERNS = [
    r'(?i)ignore\s+(all\s+)?previous\s+instructions',
    r'(?i)disregard\s+(all\s+)?(previous|prior|above)',
    r'(?i)forget\s+everything\s+(above|before|prior)',
    r'(?i)new\s+instructions?\s*:\s*',
    r'(?i)system\s*prompt\s*:\s*',
    r'(?i)you\s+are\s+now\s+(a|an|the|my)\s+',
    r'(?i)act\s+as\s+(a|an|the|my)\s+',
    r'(?i)pretend\s+(to\s+be|you\s+are)\s+',
    r'(?i)from\s+now\s+on,?\s+(you|ignore|always|never)',
    r'(?i)override\s+(system|safety|all)\s+',
    r'(?i)bypass\s+(safety|filter|guard)',
    r'(?i)\bjailbreak\b',
    r'(?i)DAN\s+mode',
    r'(?i)developer\s+mode',
    r'(?i)<\s*script\b',
    r'(?i)<\s*iframe\b',
    r'(?i)javascript\s*:',
    r'(?i)\bonerror\s*=',
    r'(?i)\bonload\s*=',
]

# Blocked for SSRF prevention. Each entry: (match_type, value)
# match_type "exact" checks hostname equality; "suffix" checks hostname ends with "."+value (subdomain safe);
# "octet" checks IPv4 first-octet CIDR; "ipv6" checks literal IPv6 loopback/ULA.
BLOCKED_RULES = [
    ('exact', 'localhost'),
    ('octet', '127'),
    ('octet', '0'),
    ('octet', '10'),
    ('octet', '192.168'),
    ('octet', '172.16'), ('octet', '172.17'), ('octet', '172.18'), ('octet', '172.19'),
    ('octet', '172.20'), ('octet', '172.21'), ('octet', '172.22'), ('octet', '172.23'),
    ('octet', '172.24'), ('octet', '172.25'), ('octet', '172.26'), ('octet', '172.27'),
    ('octet', '172.28'), ('octet', '172.29'), ('octet', '172.30'), ('octet', '172.31'),
    ('octet', '169.254'),
    ('ipv6', '::1'),
    ('ipv6', 'fc00::/7'),
    ('ipv6', 'fe80::/10'),
]


def _ip_in_blocked(ip_str: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


class BrowserlessClient:
    def __init__(self, settings):
        self.api_url = getattr(settings, 'BROWSERLESS_URL', '')
        self.api_token = getattr(settings, 'BROWSERLESS_TOKEN', '')
        self.enabled = bool(self.api_url and self.api_token)
        self.max_content_length = 15000
        self.timeout = 30
        # #3: shared aiohttp session (connection pool reuse, hemat TLS handshake).
        self._session = None

    async def _get_session(self):
        import aiohttp
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=20, limit_per_host=6, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def aclose(self):
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    def _is_safe_url(self, url):
        """Sync literal check: scheme, IP literal, exact/suffix/octet rules, single-label.

        Untuk hostname DNS, panggil _is_safe_url_async() yang juga resolve DNS
        dan cek tiap IP hasil resolve (cegah DNS-rebinding ke private IP).
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False, "Only HTTP/HTTPS URLs are allowed"
            # Tolak userinfo (user:pass@host) — sering dipakai untuk menyamarkan host.
            if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
                # urlparse sudah strip userinfo dari hostname, tapi tetap tolak pola ini.
                if "@" in url.split("://", 1)[-1].split("/", 1)[0]:
                    return False, "Userinfo in URL is not allowed"

            hostname = parsed.hostname or ''
            if not hostname:
                return False, "Invalid hostname"

            import ipaddress
            try:
                ip = ipaddress.ip_address(hostname)
                if _ip_in_blocked(hostname):
                    return False, f"Access to {hostname} is blocked"
                return True, "OK"
            except ValueError:
                pass

            host_lower = hostname.lower().rstrip('.')
            for kind, value in BLOCKED_RULES:
                if kind == 'exact' and host_lower == value:
                    return False, f"Access to {hostname} is blocked"
                if kind == 'suffix' and (host_lower == value or host_lower.endswith('.' + value)):
                    return False, f"Access to {hostname} is blocked"
                if kind == 'octet':
                    # value seperti '10', '192.168', '172.16' — cocokkan dot-bounded
                    # agar '10evil.com' tidak lolos via startswith naif, dan
                    # '10.0.0.1.evil.com' tetap terdeteksi bila diawali oktet privat.
                    if host_lower == value or host_lower.startswith(value + "."):
                        return False, f"Access to {hostname} is blocked"
                if kind == 'ipv6' and ':' in host_lower and host_lower == value.lower():
                    return False, f"Access to {hostname} is blocked"

            if '.' not in host_lower:
                return False, "Invalid hostname"

            return True, "OK"
        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    async def _is_safe_url_async(self, url):
        """Sync check + resolve DNS dan pastikan tidak ada IP privat/loopback."""
        ok, reason = self._is_safe_url(url)
        if not ok:
            return False, reason
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower().rstrip(".")
            import ipaddress
            try:
                ipaddress.ip_address(hostname)
                return True, "OK"  # sudah dicek literal di atas
            except ValueError:
                pass
            loop = asyncio.get_running_loop()
            try:
                infos = await loop.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            except Exception as e:
                return False, f"DNS resolution failed for {hostname}: {e}"
            for _fam, _typ, _proto, _canon, sockaddr in infos:
                ip_str = sockaddr[0]
                if _ip_in_blocked(ip_str):
                    return False, f"Access to {hostname} is blocked (resolves to {ip_str})"
            return True, "OK"
        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    def _sanitize_content(self, text):
        if not text:
            return ""

        # Decode HTML entities
        text = html.unescape(text)

        # Remove script/style tags and their content
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<object[^>]*>.*?</object>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<embed[^>]*>.*?</embed>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags but keep content
        text = re.sub(r'<[^>]+>', ' ', text)

        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        # Check for prompt injection patterns
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text):
                logger.warning(f"Potential prompt injection detected: {pattern}")
                # Remove the suspicious content
                text = re.sub(pattern, '[FILTERED]', text)

        # Limit length
        if len(text) > self.max_content_length:
            text = text[:self.max_content_length] + "\n\n[Content truncated...]"

        return text

    def _extract_text_from_markdown(self, markdown):
        if not markdown:
            return ""

        # Remove markdown formatting but keep content
        text = markdown

        # Remove images but keep alt text
        text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)

        # Remove links but keep text
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)

        # Remove headers markers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Remove bold/italic markers
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)

        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '[Code block removed]', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Remove blockquotes
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)

        # Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

        # Collapse whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    async def fetch_content(self, url, mode="markdown"):
        is_safe, reason = await self._is_safe_url_async(url)
        if not is_safe:
            return {"error": reason, "safe": False}

        if not self.enabled:
            return {"error": "Browserless not configured", "safe": False}

        try:
            import aiohttp
            session = await self._get_session()

            payload = {
                "url": url,
                "waitFor": 5000,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            }

            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }

            # Instance chrome.browserless.io (openresty, API v1) wajib auth via
            # query ?token= — header Bearer saja dibalas 500 (terverifikasi
            # 2026-09-04: Bearer-only 500, ?token= 200). Kirim keduanya.
            token_qs = f"?token={self.api_token}"
            if mode == "pdf":
                endpoint = f"{self.api_url}/pdf{token_qs}"
            elif mode == "screenshot":
                endpoint = f"{self.api_url}/screenshot{token_qs}"
            else:
                endpoint = f"{self.api_url}/content{token_qs}"

            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    transient = resp.status in (429, 500, 502, 503, 504)
                    return {
                        "error": f"Browserless error: {resp.status} - {error_text}",
                        "safe": False,
                        "transient": transient,
                    }

                if mode in ("pdf", "screenshot"):
                    data = await resp.read()
                    return {
                        "success": True,
                        "type": mode,
                        "data": data,
                        "content_type": "application/pdf" if mode == "pdf" else "image/png",
                        "safe": True
                    }
                else:
                    data = await resp.json()
                    content = data.get("content", "")
                    title = data.get("title", "")
                    link = data.get("url", url)

                    # Sanitize content
                    sanitized = self._sanitize_content(content)
                    clean_text = self._extract_text_from_markdown(sanitized)

                    return {
                        "success": True,
                        "type": "text",
                        "title": title,
                        "url": link,
                        "content": clean_text,
                        "original_length": len(content),
                        "cleaned_length": len(clean_text),
                        "safe": True
                    }

        except Exception as e:
            logger.error(f"Browserless fetch error: {e}")
            return {"error": f"Fetch failed: {str(e)}", "safe": False, "transient": True}

    async def fetch_with_retry(self, url, mode="markdown", retries=2):
        for attempt in range(retries + 1):
            result = await self.fetch_content(url, mode)
            if result.get("success"):
                return result
            if not result.get("transient", False):
                return result
            if attempt < retries:
                import asyncio
                await asyncio.sleep(2 ** attempt)
        return result

    async def fetch_image(self, url):
        is_safe, reason = await self._is_safe_url_async(url)
        if not is_safe:
            return {"error": reason, "safe": False}

        if not self.enabled:
            return {"error": "Browserless not configured", "safe": False}

        try:
            import aiohttp

            # Shared session (Context7: reuse ClientSession).
            # GET image langsung tanpa Authorization (itu hanya untuk Browserless API).
            current_url = url
            origin_host = (urlparse(url).hostname or "").lower()
            session = await self._get_session()
            for _ in range(5):
                async with session.get(
                    current_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=False
                ) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        location = resp.headers.get("Location", "") or resp.headers.get("URI", "")
                        if not location:
                            return {"error": "Redirect without Location", "safe": False}
                        # Selesaikan redirect relatif terhadap URL saat ini.
                        next_url = urljoin(current_url, location)
                        safe, reason = await self._is_safe_url_async(next_url)
                        if not safe:
                            return {"error": f"Redirect blocked: {reason}", "safe": False}
                        next_host = (urlparse(next_url).hostname or "").lower()
                        if next_host != origin_host:
                            # Cross-origin: jangan bawa kredensial apapun.
                            origin_host = next_host
                        current_url = next_url
                        continue
                    if resp.status != 200:
                        return {"error": f"HTTP {resp.status}", "safe": False}

                    content_type = resp.content_type or ""
                    if not content_type.startswith("image/"):
                        return {"error": f"Not an image: {content_type}", "safe": False}

                    data = await resp.read()
                    if len(data) > 20 * 1024 * 1024:
                        return {"error": "Image too large (max 20MB)", "safe": False}

                    return {
                        "success": True,
                        "mime_type": content_type,
                        "data": data,
                        "size": len(data),
                        "safe": True
                    }
            return {"error": "Too many redirects", "safe": False}

        except Exception as e:
            logger.error(f"Browserless fetch_image error: {e}")
            return {"error": f"Fetch failed: {str(e)}", "safe": False}

    async def screenshot_page(self, url):
        return await self.fetch_content(url, mode="screenshot")
