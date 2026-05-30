import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from shared_context import SharedContext

log = logging.getLogger("jarvis.agent")


class BaseAgent:
    def __init__(self, manager: Any, name: Optional[str] = None, capabilities: Optional[List[str]] = None):
        self.id = str(uuid.uuid4())
        self.name = name or self.__class__.__name__
        self.capabilities = capabilities or []
        self.manager = manager
        self.shared_context: SharedContext = getattr(manager, "shared_context", SharedContext())
        self.status = "idle"
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        log.info("Starting agent %s (%s)", self.name, self.id)
        self.status = "running"

    async def stop(self) -> None:
        log.info("Stopping agent %s (%s)", self.name, self.id)
        self.status = "stopped"

    async def handle_event(self, event: Any) -> Any:
        """Override to respond to events."""
        log.debug("%s received event %s", self.name, getattr(event, "type", type(event)))
        return None

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task. Override in subclasses."""
        async with self._lock:
            self.status = "busy"
            try:
                log.info("%s executing task %s", self.name, task.get("id"))
                res = {"status": "ok", "agent": self.name, "result": None}
                return res
            finally:
                self.status = "idle"

    def memory_store(self, content: str, mem_type: str = "fact", importance: int = 5) -> None:
        try:
            import memory

            memory.remember(content, mem_type=mem_type, importance=importance)
            self.shared_context.add_memory_ref(content)
        except Exception:
            log.exception("memory_store failed")

    def memory_recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            import memory

            rows = memory.recall(query, limit=limit)
            return rows
        except Exception:
            log.exception("memory_recall failed")
            return []
