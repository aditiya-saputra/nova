import asyncio
import aiohttp
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 3
DEFAULT_QUESTION = "Deskripsikan gambar ini secara detail."


class AttachmentProcessor:
    def __init__(self, gemini):
        self.gemini = gemini
        # #3: shared session reuse (hindari handshake per gambar).
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=4, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def aclose(self):
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    def extract_image_attachments(self, message):
        images = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                images.append({
                    "url": att.url,
                    "filename": att.filename,
                    "content_type": att.content_type,
                    "size": att.size,
                })
        return images

    async def analyze(self, images, question):
        if not images:
            return []

        question = question or DEFAULT_QUESTION
        # #5: batasi + paralel — download + VLM jalan bareng, bukan sekuensial.
        images = images[:MAX_IMAGES_PER_MESSAGE]
        session = await self._get_session()

        async def _one(img):
            try:
                async with session.get(
                    img["url"],
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
                    if len(data) > MAX_IMAGE_BYTES:
                        return None
                    analysis = await self.gemini.generate_with_images(
                        prompt=question,
                        images=[{
                            "mime_type": img["content_type"],
                            "data": data
                        }]
                    )
                    return {
                        "filename": img["filename"],
                        "analysis": analysis
                    }
            except Exception as e:
                logger.error(f"VLM attachment error: {e}")
                return None

        results = await asyncio.gather(*(_one(img) for img in images))
        return [r for r in results if r]
