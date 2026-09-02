import json
import uuid
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
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
            existing = self.load(channel_id)
            new_hash = _fact_hash(nugget.get("fact", ""))
            for old in existing[-DEDUP_SCAN_LINES:]:
                if _fact_hash(old.get("fact", "")) == new_hash:
                    return False

            path = self._get_file_path(channel_id)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(nugget) + "\n")
            return True

    async def clean_expired(self, channel_id):
        async with self._lock:
            nuggets = self.load(channel_id)
            now = datetime.utcnow()
            valid = []

            for nugget in nuggets:
                try:
                    expiry = datetime.fromisoformat(nugget["expiry"].replace("Z", "+00:00"))
                    if expiry.replace(tzinfo=None) > now:
                        valid.append(nugget)
                except (KeyError, ValueError):
                    continue

            if len(valid) < len(nuggets):
                path = self._get_file_path(channel_id)
                if valid:
                    path.write_text(
                        "\n".join(json.dumps(n) for n in valid) + "\n",
                        encoding="utf-8"
                    )
                else:
                    path.write_text("", encoding="utf-8")

            return valid

    def create_nugget(self, channel_id, user_id, message_id, fact):
        now = datetime.utcnow()
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

    def list_channels(self):
        return [f.stem.replace("channel_", "") for f in self.base_dir.glob("channel_*.jsonl")]
