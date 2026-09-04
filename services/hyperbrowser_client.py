"""Hyperbrowser provider — alternatif/fallback untuk Browserless.

Return-shape disamakan dengan BrowserlessClient agar ToolExecutor bisa
fallback transparan:
- fetch_content/fetch_with_retry -> {success, type, title, url, content, ...}
- screenshot_page -> {success, data(bytes PNG), ...}
- error -> {error, safe: False, transient?: bool}
"""

import asyncio
import base64
from utils.logger import get_logger

logger = get_logger(__name__)


class HyperbrowserClient:
    def __init__(self, settings):
        self.settings = settings
        self.api_key = getattr(settings, "HYPERBROWSER_API_KEY", "") or ""
        self.enabled = bool(self.api_key)
        self.max_content_length = 15000
        self.timeout = 30
        # Reuse URL SSRF guard + sanitizer yang sudah teruji milik Browserless.
        from services.browserless_client import BrowserlessClient
        self._guard = BrowserlessClient(settings)

    def _get_sdk(self):
        try:
            from hyperbrowser import AsyncHyperbrowser
            from hyperbrowser.models import StartScrapeJobParams, ScrapeOptions
        except ImportError as e:
            logger.error(f"hyperbrowser SDK not installed: {e}")
            return None, None, None
        return AsyncHyperbrowser, StartScrapeJobParams, ScrapeOptions

    @staticmethod
    def _first_page(result):
        data = getattr(result, "data", None)
        if isinstance(data, list) and data:
            return data[0]
        if data is not None and not isinstance(data, list):
            return data
        return None

    async def fetch_content(self, url, mode="markdown"):
        ok, reason = await self._guard._is_safe_url_async(url)
        if not ok:
            return {"error": reason, "safe": False}
        if not self.enabled:
            return {"error": "Hyperbrowser not configured", "safe": False}

        sdk = self._get_sdk()
        if sdk[0] is None:
            return {"error": "hyperbrowser SDK not installed", "safe": False}
        AsyncHyperbrowser, StartScrapeJobParams, ScrapeOptions = sdk

        try:
            async with AsyncHyperbrowser(api_key=self.api_key) as client:
                params = StartScrapeJobParams(
                    url=url,
                    scrape_options=ScrapeOptions(
                        formats=["markdown"],
                        only_main_content=True,
                        wait_for=5000,
                        wait_until="networkidle",
                        timeout=self.timeout * 1000,
                    ),
                )
                result = await client.scrape.start_and_wait(params)
            page = self._first_page(result)
            if page is None:
                return {"error": "Empty scrape result", "safe": False, "transient": True}
            if getattr(page, "status", None) not in (None, "completed", "success", 200, "200"):
                return {"error": f"Scrape status: {getattr(page, 'status', '?')}", "safe": False, "transient": True}

            markdown = getattr(page, "markdown", None) or getattr(page, "html", None) or ""
            title = getattr(page, "title", None) or ""
            if not title:
                meta = getattr(page, "metadata", None) or {}
                title = meta.get("title", "") if isinstance(meta, dict) else getattr(meta, "title", "") or ""
            link = getattr(page, "url", None) or url

            sanitized = self._guard._sanitize_content(markdown)
            clean_text = self._guard._extract_text_from_markdown(sanitized)
            return {
                "success": True,
                "type": "text",
                "title": title,
                "url": link,
                "content": clean_text,
                "original_length": len(markdown),
                "cleaned_length": len(clean_text),
                "safe": True,
                "provider": "hyperbrowser",
            }
        except Exception as e:
            logger.error(f"Hyperbrowser fetch error: {e}")
            return {"error": f"Fetch failed: {str(e)}", "safe": False, "transient": True}

    async def fetch_with_retry(self, url, mode="markdown", retries=2):
        for attempt in range(retries + 1):
            result = await self.fetch_content(url, mode)
            if result.get("success"):
                return result
            if not result.get("transient", False):
                return result
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
        return result

    async def screenshot_page(self, url):
        ok, reason = await self._guard._is_safe_url_async(url)
        if not ok:
            return {"error": reason, "safe": False}
        if not self.enabled:
            return {"error": "Hyperbrowser not configured", "safe": False}

        sdk = self._get_sdk()
        if sdk[0] is None:
            return {"error": "hyperbrowser SDK not installed", "safe": False}
        AsyncHyperbrowser, StartScrapeJobParams, ScrapeOptions = sdk

        try:
            async with AsyncHyperbrowser(api_key=self.api_key) as client:
                params = StartScrapeJobParams(
                    url=url,
                    scrape_options=ScrapeOptions(
                        formats=["screenshot"],
                        wait_for=5000,
                        wait_until="networkidle",
                        timeout=self.timeout * 1000,
                    ),
                )
                result = await client.scrape.start_and_wait(params)
            page = self._first_page(result)
            if page is None:
                return {"error": "Empty screenshot result", "safe": False, "transient": True}
            shot = (
                getattr(page, "screenshot", None)
                or getattr(page, "screenshot_url", None)
                or getattr(page, "image", None)
            )
            data = await self._coerce_image_bytes(shot)
            if not data:
                return {"error": "No screenshot in result", "safe": False, "transient": True}
            return {"success": True, "data": data, "safe": True, "provider": "hyperbrowser"}
        except Exception as e:
            logger.error(f"Hyperbrowser screenshot error: {e}")
            return {"error": f"Screenshot failed: {str(e)}", "safe": False, "transient": True}

    async def _coerce_image_bytes(self, shot):
        if not shot:
            return None
        if isinstance(shot, (bytes, bytearray)):
            return bytes(shot)
        if isinstance(shot, dict):
            for k in ("data", "base64", "url", "screenshot"):
                if shot.get(k):
                    return await self._coerce_image_bytes(shot[k])
            return None
        if isinstance(shot, str):
            s = shot.strip()
            if s.startswith("data:image"):
                try:
                    return base64.b64decode(s.split(",", 1)[1])
                except Exception:
                    return None
            if s.startswith("http"):
                ok, _ = await self._guard._is_safe_url_async(s)
                if not ok:
                    return None
                try:
                    import aiohttp

                    session = await self._guard._get_session()
                    async with session.get(
                        s, timeout=aiohttp.ClientTimeout(total=30), allow_redirects=False
                    ) as resp:
                        if resp.status != 200:
                            return None
                        return await resp.read()
                except Exception as e:
                    logger.error(f"Hyperbrowser screenshot download error: {e}")
                    return None
            try:
                return base64.b64decode(s)
            except Exception:
                return None
        return None

    async def aclose(self):
        # SDK dipakai via context manager per call — tidak ada session persisten,
        # tapi guard punya shared aiohttp session untuk download screenshot-URL.
        try:
            await self._guard.aclose()
        except Exception:
            pass
        return None
