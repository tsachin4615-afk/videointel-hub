import httpx
import logging

logger = logging.getLogger(__name__)

class ResearchService:
    @staticmethod
    async def fetch_context_snippets(query: str, max_results: int = 3) -> list[dict]:
        """
        Fetches external background context and summary snippets using DuckDuckGo HTML/Instant API.
        Acts as a supplementary evidence gatherer without requiring paid search API keys.
        """
        if not query or not query.strip():
            return []

        endpoint = "https://api.duckduckgo.com/"
        params = {
            "q": query.strip(),
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1"
        }
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(endpoint, params=params)
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    
                    # Extract Abstract if present
                    if data.get("AbstractText"):
                        results.append({
                            "source": data.get("AbstractSource", "Reference"),
                            "url": data.get("AbstractURL", ""),
                            "snippet": data.get("AbstractText")
                        })
                        
                    # Extract Related Topics
                    for topic in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append({
                                "source": "DuckDuckGo Context",
                                "url": topic.get("FirstURL", ""),
                                "snippet": topic.get("Text")
                            })
                            
                    return results
        except Exception as e:
            logger.warning(f"External research lookup failed for query '{query}': {e}")

        return []
