import tiktoken
from functools import lru_cache
from utils.logger import get_logger

logger = get_logger(__name__)


class TokenCounter:
    """Estimasi token berbasis tiktoken cl100k_base (OpenAI).

    PENTING: ini HANYA aproksimasi untuk Gemini (SentencePiece-based).
    Jangan dipakai untuk billing presisi — hanya untuk compaction threshold.
    Untuk akurasi penuh, gunakan Gemini count_tokens API.
    """

    def __init__(self):
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.encoding = None

    @lru_cache(maxsize=2048)
    def _encode_cached(self, text: str) -> int:
        # #4: cache hit untuk pesan berulang (hydrate, retry) — hemat CPU encode.
        return len(self.encoding.encode(text))

    def count_tokens(self, text):
        if not self.encoding:
            return len(text or "") // 4
        if not text:
            return 0
        try:
            # lru_cache pada method (self ikut jadi key — aman 1 instance global).
            return self._encode_cached(text)
        except Exception:
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
