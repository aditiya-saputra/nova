import tiktoken
from utils.logger import get_logger

logger = get_logger(__name__)


class TokenCounter:
    def __init__(self):
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.encoding = None

    def count_tokens(self, text):
        if not self.encoding:
            return len(text) // 4

        try:
            return len(self.encoding.encode(text))
        except Exception:
            return len(text) // 4

    def count_messages(self, messages):
        total = 0
        for msg in messages:
            total += self.count_tokens(msg.get("content", ""))
            total += 4
        return total + 3


token_counter = TokenCounter()
