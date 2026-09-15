import asyncio
import aiohttp
from utils.logger import get_logger

logger = get_logger(__name__)

# Whitelist extensions — only text-based files, no binaries/executables.
ALLOWED_EXTENSIONS = {
    # Code
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".bash", ".zsh", ".fish",
    ".cs", ".swift", ".kt", ".scala", ".r", ".m", ".mm",
    # Data / Config
    ".json", ".yaml", ".yml", ".toml", ".xml", ".csv", ".tsv", ".ini",
    ".cfg", ".conf", ".env",
    # Text / Docs
    ".txt", ".md", ".markdown", ".rst", ".log",
    # Web
    ".html", ".htm", ".css", ".scss", ".less",
    # Other text
    ".gitignore", ".dockerignore", ".editorconfig",
}

MAX_FILE_SIZE = 500 * 1024          # 500KB per file
MAX_CONTENT_CHARS = 8000            # max chars per file content sent to Gemini
MAX_FILES_PER_MESSAGE = 5
MAX_TOTAL_CHARS = 20000             # sum of all file contents


class FileProcessor:
    def __init__(self):
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

    def extract_file_attachments(self, message):
        """Filter message attachments — return non-image text-based files only."""
        files = []
        for att in message.attachments:
            # Skip images (handled by AttachmentProcessor)
            if att.content_type and att.content_type.startswith("image/"):
                continue
            # Check extension whitelist
            filename = att.filename or ""
            ext = ""
            dot_idx = filename.rfind(".")
            if dot_idx >= 0:
                ext = filename[dot_idx:].lower()
            if not ext:
                # No extension: require text MIME type to avoid binary files
                if not (att.content_type and att.content_type.startswith("text/")):
                    continue
            elif ext not in ALLOWED_EXTENSIONS:
                # Also allow if MIME type is text-based
                if not (att.content_type and att.content_type.startswith("text/")):
                    continue
            if att.size and att.size > MAX_FILE_SIZE:
                logger.warning(f"File too large ({att.size} bytes): {filename}")
                continue
            files.append({
                "url": att.url,
                "filename": filename,
                "content_type": att.content_type or "application/octet-stream",
                "size": att.size or 0,
            })
        return files[:MAX_FILES_PER_MESSAGE]

    async def read_attachments(self, files):
        """Download and read text content from file attachments.

        Returns list[{filename, content, size, truncated}].
        """
        if not files:
            return []

        async def _read_one(f):
            try:
                session = await self._get_session()
                async with session.get(
                    f["url"],
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to download {f['filename']}: HTTP {resp.status}")
                        return None
                    raw = await resp.read()
                    if len(raw) > MAX_FILE_SIZE:
                        logger.warning(f"File too large after download: {f['filename']}")
                        return None
                    # Try decoding as text
                    content = self._decode_text(raw)
                    if content is None:
                        logger.info(f"Non-text file skipped: {f['filename']}")
                        return None
                    truncated = len(content) > MAX_CONTENT_CHARS
                    if truncated:
                        content = content[:MAX_CONTENT_CHARS] + "\n\n[... truncated ...]"
                    return {
                        "filename": f["filename"],
                        "content": content,
                        "size": len(raw),
                        "truncated": truncated,
                    }
            except Exception as e:
                logger.error(f"File read error for {f['filename']}: {e}")
                return None

        results = await asyncio.gather(*[_read_one(f) for f in files])
        return [r for r in results if r]

    @staticmethod
    def _decode_text(raw_bytes):
        """Decode bytes to string. Returns None if not text-decodable."""
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            pass
        # Null bytes strongly indicate binary content — reject before latin-1
        if b'\x00' in raw_bytes[:8192]:
            return None
        try:
            return raw_bytes.decode("latin-1")
        except Exception:
            return None

    def format_for_prompt(self, file_contents):
        """Format file contents for injection into Gemini prompt."""
        if not file_contents:
            return ""
        parts = []
        total = 0
        for fc in file_contents:
            chunk = f"--- File: {fc['filename']} ({fc['size']} bytes) ---\n{fc['content']}\n--- End: {fc['filename']} ---"
            if total + len(chunk) > MAX_TOTAL_CHARS:
                remaining = MAX_TOTAL_CHARS - total
                if remaining > 200:
                    chunk = chunk[:remaining] + "\n\n[... total limit reached ...]"
                    parts.append(chunk)
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n\n".join(parts)
