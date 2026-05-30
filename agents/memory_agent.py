import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.memory_agent")


class MemoryAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="MemoryAgent", capabilities=["memory.store", "memory.recall"])

    async def handle_event(self, event: Any) -> None:
        try:
            if getattr(event, "type", "") == "MemoryStoredEvent":
                payload = getattr(event, "payload", {})
                content = payload.get("content")
                mem_type = payload.get("type", "fact")
                importance = int(payload.get("importance", 5))
                self.memory_store(content, mem_type=mem_type, importance=importance)
        except Exception:
            log.exception("MemoryAgent failed handling event")

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        op = task.get("op")
        if op == "store":
            self.memory_store(task.get("content", ""), mem_type=task.get("type", "fact"), importance=task.get("importance", 5))
            return {"status": "stored"}
        if op == "recall":
            q = task.get("query", "")
            rows = self.memory_recall(q, limit=task.get("limit", 5))
            return {"status": "ok", "rows": rows}
        return {"status": "unknown_op"}
"""MemoryAgent: adapter around existing `memory` module."""
from .base import BaseAgent
import memory


class MemoryAgent(BaseAgent):
    """Wrap memory operations and expose them via events.

    Supported events:
    - MemoryStore: {'content': str, 'type': str, 'source': str, 'importance': int}
    - MemoryQuery: {'query': str, 'limit': int, 'reply_to': str}
    """

    async def handle_event(self, event_type: str, payload: dict) -> None:
        if event_type == "MemoryStore":
            content = payload.get("content")
            mem_type = payload.get("type", "fact")
            source = payload.get("source", "")
            importance = int(payload.get("importance", 5))
            memory.remember(content, mem_type=mem_type, source=source, importance=importance)
        elif event_type == "MemoryQuery":
            # synchronous recall; keep as sync call but run in event loop
            query = payload.get("query", "")
            limit = int(payload.get("limit", 5))
            results = memory.recall(query, limit=limit)
            # optionally dispatch results back via manager
            reply_to = payload.get("reply_to")
            if reply_to and hasattr(self.manager, "emit_event"):
                await self.manager.emit_event(reply_to, {"results": results})
