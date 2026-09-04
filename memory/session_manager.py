import time
from collections import defaultdict
from config.settings import Settings
from memory.history_store import HistoryStore
from services.token_counter import token_counter
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    def __init__(self, settings: Settings, history_store: HistoryStore = None):
        self.settings = settings
        self.history_store = history_store
        self.sessions = defaultdict(list)
        self.last_activity = {}
        self.token_counts = defaultdict(int)
        self._hydrated_keys = set()

    def hydrate_from_disk(self, key):
        if not self.history_store or key in self._hydrated_keys:
            return
        entries = self.history_store.load(key)
        for entry in entries:
            role = entry.get("role")
            content = entry.get("content")
            if not role or content is None:
                continue
            tokens = token_counter.count_tokens(content)
            self.sessions[key].append({
                "role": role,
                "content": content,
                "tokens": tokens,
                "timestamp": float(entry.get("timestamp") or time.time()),
            })
            self.token_counts[key] += tokens
            if role == "system" and content.startswith("Previous conversation summary:"):
                pass
        if entries:
            self.last_activity[key] = time.time()
            logger.info(f"Hydrated {len(entries)} entries for {key}")
        self._hydrated_keys.add(key)

    def add_message(self, key, role, content):
        self.hydrate_from_disk(key)
        tokens = token_counter.count_tokens(content)
        self.sessions[key].append({
            "role": role,
            "content": content,
            "tokens": tokens,
            "timestamp": time.time()
        })
        self.token_counts[key] += tokens
        self.last_activity[key] = time.time()

    def get_history(self, key):
        self.hydrate_from_disk(key)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.sessions[key]
        ]

    def get_token_count(self, key):
        self.hydrate_from_disk(key)
        return self.token_counts[key]

    def get_token_usage(self, key):
        self.hydrate_from_disk(key)
        return self.token_counts[key] / self.settings.GEMINI_CONTEXT_LIMIT

    def replace_history(self, key, summary, tail_keep=4):
        summary_tokens = token_counter.count_tokens(summary)
        existing = self.sessions[key]
        tail = existing[-tail_keep:] if len(existing) > tail_keep else list(existing)
        summary_entry = {
            "role": "system",
            "content": f"Previous conversation summary: {summary}",
            "tokens": summary_tokens,
            "timestamp": time.time(),
        }
        new_session = [summary_entry] + tail
        self.sessions[key] = new_session
        self.token_counts[key] = sum(m["tokens"] for m in new_session)
        self.last_activity[key] = time.time()
        if self.history_store:
            self.history_store.clear(key)
            self.history_store.append_message(
                key, 0, "system", summary_entry["content"]
            )
            for tail_msg in tail:
                ts = tail_msg.get("timestamp", time.time())
                self.history_store.append(
                    key,
                    {
                        "user_id": 0,
                        "role": tail_msg["role"],
                        "content": tail_msg["content"],
                        "timestamp": ts,
                    },
                )

    def clear(self, key):
        self.sessions[key] = []
        self.token_counts[key] = 0
        self.last_activity[key] = time.time()
        if self.history_store:
            self.history_store.clear(key)
        self._hydrated_keys.discard(key)

    def get_channel_key(self, channel_id):
        return f"channel_{channel_id}"

    def get_user_key(self, user_id):
        return f"user_{user_id}"
