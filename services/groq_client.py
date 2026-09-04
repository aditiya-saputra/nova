import groq
from groq import AsyncGroq, DefaultAioHttpClient
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GroqClient:
    """Async Groq wrapper (Context7: gunakan AsyncGroq + await, bukan sync + to_thread)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # AsyncGroq dengan aiohttp backend untuk non-blocking di event loop.
        # API key boleh kosong saat boot (fitur opsional) — client dibuat lazy.
        self._api_key = settings.GROQ_API_KEY
        self._client: AsyncGroq | None = None
        self.model_heavy = settings.GROQ_MODEL_HEAVY
        self.model_fast = settings.GROQ_MODEL_FAST

    def _get_client(self) -> AsyncGroq | None:
        if not self._api_key:
            return None
        if self._client is None:
            try:
                self._client = AsyncGroq(
                    api_key=self._api_key,
                    http_client=DefaultAioHttpClient(),
                )
            except Exception:
                # Fallback tanpa custom http_client bila versi groq lama.
                self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def aclose(self):
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None

    async def compact(self, history, system_prompt):
        client = self._get_client()
        if not client:
            raise ValueError("Groq API key not configured")
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {
                "role": "user",
                "content": "Summarize this conversation concisely, preserving key context, decisions, and important information. Output only the summary."
            }
        ]
        response = await client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.3
        )
        return response.choices[0].message.content

    async def extract_facts(self, prompt):
        client = self._get_client()
        if not client:
            raise ValueError("Groq API key not configured")
        messages = [
            {"role": "system", "content": "You are a fact extractor. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=2048,
            temperature=0.2
        )
        return response.choices[0].message.content

    async def retrieve_relevant(self, prompt):
        client = self._get_client()
        if not client:
            raise ValueError("Groq API key not configured")
        messages = [
            {"role": "system", "content": "You are a relevance matcher. Output only valid JSON array."},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=2048,
            temperature=0.2
        )
        return response.choices[0].message.content

    async def process_search_results(self, query, results):
        client = self._get_client()
        if not client:
            raise ValueError("Groq API key not configured")
        messages = [
            {"role": "system", "content": "Process search results and provide a concise, accurate summary."},
            {"role": "user", "content": f"Query: {query}\n\nResults:\n{results}"}
        ]
        response = await client.chat.completions.create(
            model=self.model_fast,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.3
        )
        return response.choices[0].message.content

    async def synthesize(self, context, intent, search_data=None):
        client = self._get_client()
        if not client:
            raise ValueError("Groq API key not configured")
        prompt = f"Intent: {intent}\nContext: {context}"
        if search_data:
            prompt += f"\nSearch Data: {search_data}"

        messages = [
            {"role": "system", "content": "Synthesize a helpful, accurate response based on the context and intent."},
            {"role": "user", "content": prompt}
        ]
        response = await client.chat.completions.create(
            model=self.model_fast,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.7
        )
        return response.choices[0].message.content
