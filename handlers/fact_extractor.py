import json
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
            facts_response = await self.groq.extract_facts(extract_prompt)
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

    async def retrieve_relevant_facts(self, query, channel_id, top_k=5):
        """Shared helper: load nuggets (prune expired) + Groq relevance rank.

        Dipakai oleh MessageHandler, /ask, dan ToolExecutor agar tidak duplikat.
        Return list[str] (max top_k), [] bila tidak ada / error.
        """
        nuggets = await self.rag_store.clean_expired(channel_id)
        if not nuggets:
            return []
        # settings diakses via rag_store.settings bila ada
        settings = getattr(self.rag_store, "settings", None)
        limit = getattr(settings, "NUGGETS_TOP_K", top_k) if settings else top_k
        try:
            # Build prompt manual (tanpa ContextBuilder instance) agar helper mandiri.
            nuggets_text = "\n".join(
                f"- [{n.get('channel_id', 'N/A')}] {n.get('fact', '')} "
                f"(by user {n.get('user_id', 'N/A')})"
                for n in nuggets
            )
            # Coba pakai template bila tersedia di disk
            try:
                from pathlib import Path
                tpl_path = Path(__file__).resolve().parent.parent / "config" / "prompts" / "rag_retrieve_prompt.txt"
                template = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else "Query: {query}\nMemories:\n{nuggets_text}"
            except Exception:
                template = "Query: {query}\nMemories:\n{nuggets_text}"
            retrieve_prompt = template.format(query=query, top_k=limit, nuggets_text=nuggets_text)
            response_text = await self.groq.retrieve_relevant(retrieve_prompt)
            relevant = json.loads(response_text.strip().strip("```json").strip("```"))
            if not isinstance(relevant, list):
                return []
            return [f for f in relevant if isinstance(f, str)][:limit]
        except Exception:
            return []
