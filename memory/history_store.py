import json
import threading
from pathlib import Path
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class HistoryStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_dir = settings.HISTORY_DIR
        self._lock = threading.Lock()

    def _get_file_path(self, key):
        return self.base_dir / f"{key}.jsonl"

    def load(self, key):
        history = []
        path = self._get_file_path(key)
        if not path.exists():
            return history

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                history.append(entry)
            except json.JSONDecodeError:
                continue
        return history

    def append(self, key, entry):
        path = self._get_file_path(key)
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def append_message(self, key, user_id, role, content):
        entry = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "timestamp": __import__("time").time()
        }
        self.append(key, entry)

    def append_compaction(self, key, user_id, summary):
        entry = {
            "user_id": user_id,
            "role": "system",
            "content": f"[COMPACTION] {summary}",
            "timestamp": __import__("time").time()
        }
        self.append(key, entry)

    def clear(self, key):
        path = self._get_file_path(key)
        with self._lock:
            if path.exists():
                path.unlink()

    def list_keys(self):
        return [f.stem for f in self.base_dir.glob("*.jsonl")]
