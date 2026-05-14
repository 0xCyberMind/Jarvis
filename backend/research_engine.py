from typing import Dict, List

import httpx


class ResearchEngine:
    async def search(self, query: str, limit: int = 3) -> Dict[str, List[Dict[str, str]]]:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        results: List[Dict[str, str]] = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            for topic in payload.get("RelatedTopics", []):
                if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                    results.append({"title": topic["Text"], "url": topic["FirstURL"]})
                    if len(results) >= limit:
                        break
        except Exception:
            results.append({"title": "Research temporarily unavailable", "url": ""})

        return {"query": query, "results": results}
