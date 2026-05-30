import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.research_agent")


class ResearchAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="ResearchAgent", capabilities=["research.web", "research.summarize"])
        try:
            import browser

            self._browser = browser
        except Exception:
            self._browser = None

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        query = task.get("query")
        if not query:
            return {"status": "error", "reason": "no query"}

        results: List[Dict[str, Any]] = []
        try:
            if self._browser and hasattr(self._browser, "search"):
                hits = self._browser.search(query)
                for h in hits[:10]:
                    results.append({"title": h.get("title"), "url": h.get("url"), "snippet": h.get("snippet")})
            else:
                # best-effort: return query as placeholder
                results.append({"title": query, "url": None, "snippet": "no-browser-available"})

            # summarization (cheap)
            summary = "\n".join([r.get("title", "") for r in results[:3]])
            return {"status": "ok", "results": results, "summary": summary}
        except Exception:
            log.exception("ResearchAgent failed")
            return {"status": "error", "reason": "research failed"}
