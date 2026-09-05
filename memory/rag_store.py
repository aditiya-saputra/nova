import json
import uuid
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)

DEDUP_SCAN_LINES = 1000


def _normalize_fact(fact: str) -> str:
    return " ".join(fact.lower().split())


def _fact_hash(fact: str) -> str:
    return hashlib.sha1(_normalize_fact(fact).encode("utf-8")).hexdigest()


class RagStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_dir = settings.MEMORIES_DIR
        self._lock = asyncio.Lock()

    def _get_file_path(self, channel_id):
        return self.base_dir / f"channel_{channel_id}.jsonl"

    def load(self, channel_id):
        nuggets = []
        path = self._get_file_path(channel_id)
        if not path.exists():
            return nuggets

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                nuggets.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return nuggets

    async def save(self, channel_id, nugget):
        async with self._lock:
            existing = await asyncio.to_thread(self.load, channel_id)
            new_hash = _fact_hash(nugget.get("fact", ""))
            for old in existing[-DEDUP_SCAN_LINES:]:
                if _fact_hash(old.get("fact", "")) == new_hash:
                    return False

            path = self._get_file_path(channel_id)
            line = json.dumps(nugget) + "\n"
            await asyncio.to_thread(self._append_line, path, line)
            return True

    @staticmethod
    def _append_line(path, line):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    @staticmethod
    def _rewrite_file(path, valid):
        if valid:
            path.write_text(
                "\n".join(json.dumps(n) for n in valid) + "\n",
                encoding="utf-8"
            )
        else:
            path.write_text("", encoding="utf-8")

    async def aload(self, channel_id):
        # Baca file di thread — dipanggil tiap pesan via clean_expired/get_all.
        return await asyncio.to_thread(self.load, channel_id)

    async def clean_expired(self, channel_id):
        async with self._lock:
            nuggets = await asyncio.to_thread(self.load, channel_id)
            now = datetime.now(timezone.utc)
            valid = []

            for nugget in nuggets:
                try:
                    raw = nugget["expiry"].replace("Z", "+00:00")
                    expiry = datetime.fromisoformat(raw)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    if expiry > now:
                        valid.append(nugget)
                except (KeyError, ValueError):
                    continue

            if len(valid) < len(nuggets):
                path = self._get_file_path(channel_id)
                await asyncio.to_thread(self._rewrite_file, path, valid)

            return valid

    def create_nugget(self, channel_id, user_id, message_id, fact):
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=self.settings.NUGGETS_TTL_DAYS)

        return {
            "id": str(uuid.uuid4()),
            "fact": fact.strip(),
            "fact_hash": _fact_hash(fact),
            "timestamp": now.isoformat() + "Z",
            "expiry": expiry.isoformat() + "Z",
            "channel_id": str(channel_id),
            "user_id": str(user_id),
            "message_id": str(message_id)
        }

    def get_all(self, channel_id):
        return self.load(channel_id)

    async def aget_all(self, channel_id):
        return await asyncio.to_thread(self.load, channel_id)

    def list_channels(self):
        return [f.stem.replace("channel_", "") for f in self.base_dir.glob("channel_*.jsonl")]

    @staticmethod
    def _delete_file(path):
        if path.exists():
            path.unlink()

    async def delete_channel(self, channel_id):
        """Hapus semua nugget memori untuk satu channel (file JSONL dihapus)."""
        async with self._lock:
            path = self._get_file_path(channel_id)
            await asyncio.to_thread(self._delete_file, path)
