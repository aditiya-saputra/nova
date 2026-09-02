import json
from config.settings import Settings
from memory.session_manager import SessionManager
from memory.history_store import HistoryStore
from services.groq_client import GroqClient
from core.context_builder import ContextBuilder
from utils.logger import get_logger

logger = get_logger(__name__)


class CompactionEngine:
    def __init__(self, settings: Settings, session_manager: SessionManager,
                 history_store: HistoryStore, groq_client: GroqClient,
                 context_builder: ContextBuilder, audit_logger=None):
        self.settings = settings
        self.session_manager = session_manager
        self.history_store = history_store
        self.groq_client = groq_client
        self.context_builder = context_builder
        self.audit_logger = audit_logger

    async def check_and_compact(self, key, user_id):
        usage = self.session_manager.get_token_usage(key)

        if usage >= self.settings.COMPACTION_THRESHOLD:
            history = self.session_manager.get_history(key)
            if len(history) < 2:
                return False

            system_prompt = self.context_builder.build_compaction_prompt(history)
            summary = self.groq_client.compact(history, system_prompt)

            self.session_manager.replace_history(key, summary)
            self.history_store.append_compaction(key, user_id, summary)

            usage_after = self.session_manager.get_token_usage(key)
            logger.info(f"Compacted session {key}: {usage:.1%} -> {usage_after:.1%}")
            if self.audit_logger:
                await self.audit_logger.log_compaction(key, usage, usage_after)
            return True

        return False
