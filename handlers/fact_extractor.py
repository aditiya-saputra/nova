import json
import asyncio
from utils.logger import get_logger

logger = get_logger(__name__)


class FactExtractor:
    def __init__(self, groq, rag_store, audit_logger):
        self.groq = groq
        self.rag_store = rag_store
        self.audit_logger = audit_logger

    async def extract_and_save(self, extract_prompt, channel_id, user_id, message_id):
        if not extract_prompt:
            return 0

        try:
            facts_response = await asyncio.to_thread(self.groq.extract_facts, extract_prompt)
            facts = json.loads(facts_response.strip().strip("```json").strip("```"))
            if not isinstance(facts, list):
                return 0

            saved = 0
            for fact in facts:
                if isinstance(fact, str) and fact.strip():
                    nugget = self.rag_store.create_nugget(channel_id, user_id, message_id, fact)
                    if await self.rag_store.save(channel_id, nugget):
                        saved += 1

            await self.audit_logger.log_rag_extract(channel_id, len(facts))
            return saved
        except Exception:
            return 0
