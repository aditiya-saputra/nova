import re
import html
import hashlib
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger(__name__)

# Dangerous patterns for prompt injection
INJECTION_PATTERNS = [
    r'(?i)ignore\s+(all\s+)?previous\s+instructions',
    r'(?i)you\s+are\s+now\s+',
    r'(?i)act\s+as\s+if',
    r'(?i)pretend\s+you\s+are',
    r'(?i)disregard\s+',
    r'(?i)forget\s+everything',
    r'(?i)new\s+instructions?\s*:',
    r'(?i)system\s*prompt\s*:',
    r'(?i)IMPORTANT\s*:\s*',
    r'(?i)CRITICAL\s*:\s*',
    r'(?i)URGENT\s*:\s*',
    r'(?i)you\s+must\s+',
    r'(?i)do\s+not\s+',
    r'(?i)never\s+',
    r'(?i)always\s+respond',
    r'(?i)from\s+now\s+on',
    r'(?i)override\s+',
    r'(?i)bypass\s+',
    r'(?i)jailbreak',
    r'(?i)DAN\s+mode',
    r'(?i)developer\s+mode',
    r'(?i)admin\s+mode',
    r'(?i)<\s*script',
    r'(?i)<\s*iframe',
    r'(?i)javascript\s*:',
    r'(?i)onerror\s*=',
    r'(?i)onload\s*=',
]

# Blocked domains for safety
BLOCKED_DOMAINS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    '10.',
    '192.168.',
    '172.16.',
    '172.17.',
    '172.18.',
    '172.19.',
    '172.20.',
    '172.21.',
    '172.22.',
    '172.23.',
    '172.24.',
    '172.25.',
    '172.26.',
    '172.27.',
    '172.28.',
    '172.29.',
    '172.30.',
    '172.31.',
    '169.254.',
    '[::1]',
]


class BrowserlessClient:
    def __init__(self, settings):
        self.api_url = getattr(settings, 'BROWSERLESS_URL', '')
        self.api_token = getattr(settings, 'BROWSERLESS_TOKEN', '')
        self.enabled = bool(self.api_url and self.api_token)
        self.max_content_length = 15000
        self.timeout = 30

    def _is_safe_url(self, url):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False, "Only HTTP/HTTPS URLs are allowed"

            hostname = parsed.hostname or ''
            for blocked in BLOCKED_DOMAINS:
                if hostname == blocked or hostname.startswith(blocked):
                    return False, f"Access to {hostname} is blocked"

            if not hostname or '.' not in hostname:
                return False, "Invalid hostname"

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
        is_safe, reason = self._is_safe_url(url)
        if not is_safe:
            return {"error": reason, "safe": False}

        if not self.enabled:
            return {"error": "Browserless not configured", "safe": False}

        try:
            import aiohttp

            payload = {
                "url": url,
                "waitFor": 2000,
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

            async with aiohttp.ClientSession() as session:
                if mode == "pdf":
                    endpoint = f"{self.api_url}/pdf"
                elif mode == "screenshot":
                    endpoint = f"{self.api_url}/screenshot"
                else:
                    endpoint = f"{self.api_url}/content"

                async with session.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return {"error": f"Browserless error: {resp.status} - {error_text}", "safe": False}

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
            return {"error": f"Fetch failed: {str(e)}", "safe": False}

    async def fetch_with_retry(self, url, mode="markdown", retries=2):
        for attempt in range(retries + 1):
            result = await self.fetch_content(url, mode)
            if result.get("success") or not result.get("safe", True):
                return result
            if attempt < retries:
                import asyncio
                await asyncio.sleep(1)
        return result

    async def fetch_image(self, url):
        is_safe, reason = self._is_safe_url(url)
        if not is_safe:
            return {"error": reason, "safe": False}

        if not self.enabled:
            return {"error": "Browserless not configured", "safe": False}

        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {self.api_token}",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=True
                ) as resp:
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

        except Exception as e:
            logger.error(f"Browserless fetch_image error: {e}")
            return {"error": f"Fetch failed: {str(e)}", "safe": False}

    async def screenshot_page(self, url):
        return await self.fetch_content(url, mode="screenshot")
