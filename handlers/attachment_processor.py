import aiohttp
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_IMAGE_BYTES = 20 * 1024 * 1024
DEFAULT_QUESTION = "Deskripsikan gambar ini secara detail."


class AttachmentProcessor:
    def __init__(self, gemini):
        self.gemini = gemini

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
        results = []
        async with aiohttp.ClientSession() as session:
            for img in images:
                try:
                    async with session.get(
                        img["url"],
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.read()
                        if len(data) > MAX_IMAGE_BYTES:
                            continue
                        analysis = await self.gemini.generate_with_images(
                            prompt=question,
                            images=[{
                                "mime_type": img["content_type"],
                                "data": data
                            }]
                        )
                        results.append({
                            "filename": img["filename"],
                            "analysis": analysis
                        })
                except Exception as e:
                    logger.error(f"VLM attachment error: {e}")
        return results
