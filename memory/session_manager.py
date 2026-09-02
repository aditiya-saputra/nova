import time
from collections import defaultdict
from config.settings import Settings
from services.token_counter import token_counter
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions = defaultdict(list)
        self.last_activity = {}
        self.token_counts = defaultdict(int)

    def add_message(self, key, role, content):
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
        self._cleanup_expired(key)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.sessions[key]
        ]

    def get_token_count(self, key):
        return self.token_counts[key]

    def get_token_usage(self, key):
        return self.token_counts[key] / self.settings.GEMINI_CONTEXT_LIMIT

    def replace_history(self, key, summary):
        summary_tokens = token_counter.count_tokens(summary)
        self.sessions[key] = [
            {
                "role": "system",
                "content": f"Previous conversation summary: {summary}",
                "tokens": summary_tokens,
                "timestamp": time.time()
            }
        ]
        self.token_counts[key] = summary_tokens

    def clear(self, key):
        self.sessions[key] = []
        self.token_counts[key] = 0
        self.last_activity[key] = time.time()

    def _cleanup_expired(self, key):
        if key in self.last_activity:
            if time.time() - self.last_activity[key] > self.settings.SESSION_TIMEOUT:
                self.clear(key)

    def get_channel_key(self, channel_id):
        return f"channel_{channel_id}"

    def get_user_key(self, user_id):
        return f"user_{user_id}"
