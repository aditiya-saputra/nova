import asyncio
from tavily import TavilyClient as TavilySDK
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class TavilyClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.TAVILY_API_KEY
        self._client = None

    def _get_client(self):
        if not self._client:
            if not self.api_key:
                logger.warning("Tavily API key not configured")
                return None
            self._client = TavilySDK(api_key=self.api_key)
        return self._client

    def _search_sync(self, query, max_results=5):
        client = self._get_client()
        if not client:
            return None
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            include_raw_content=False
        )
        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
            })
        return {
            "answer": response.get("answer"),
            "results": results
        }

    async def search(self, query, max_results=5):
        """Async wrapper — SDK Tavily sync, jalankan di thread agar tidak block loop."""
        try:
            return await asyncio.to_thread(self._search_sync, query, max_results)
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return None
