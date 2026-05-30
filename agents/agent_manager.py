import asyncio
import logging
import time
from typing import Dict, List, Optional, Any

from events.event_bus import EventBus

log = logging.getLogger("jarvis.manager")


class AgentManager:
    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._by_capability: Dict[str, List[str]] = {}
        self.event_bus = EventBus()
        try:
            from shared_context import SharedContext

            self.shared_context = SharedContext()
        except Exception:
            self.shared_context = None
        self._task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._health: Dict[str, Dict[str, Any]] = {}
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in this thread (common in pytest); create one for internal use
            self._loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(self._loop)
            except Exception:
                # setting loop may fail in some test harnesses; keep the created loop
                pass

    def register(self, name: str, agent: Any) -> None:
        self._agents[name] = agent
        for cap in getattr(agent, "capabilities", []):
            self._by_capability.setdefault(cap, []).append(name)
        # expose manager and shared_context on agent
        setattr(agent, "manager", self)
        setattr(agent, "shared_context", self.shared_context)
        self._health[name] = {"status": getattr(agent, "status", "idle"), "last_seen": time.time()}
        log.info("Registered agent %s", name)

    def unregister(self, name: str) -> None:
        agent = self._agents.pop(name, None)
        if not agent:
            return
        for cap, names in list(self._by_capability.items()):
            if name in names:
                names.remove(name)
        self._health.pop(name, None)
        log.info("Unregistered agent %s", name)

    def discover(self, capability: str) -> List[str]:
        return list(self._by_capability.get(capability, []))

    async def emit_event(self, event_type: str, payload: Dict[str, Any], source: Optional[str] = None):
        from events.event_types import Event

        evt = Event(type=event_type, payload=payload, source=source)
        await self.event_bus.publish(evt)

    async def route_task(self, task: Dict[str, Any], capability: str, priority: int = 50) -> Any:
        candidates = self.discover(capability)
        if not candidates:
            raise RuntimeError(f"No agent for capability {capability}")

        # simple round-robin: pick first available
        agent_name = candidates[0]
        agent = self._agents.get(agent_name)
        if not agent:
            raise RuntimeError("Agent disappeared")

        await self._task_queue.put((priority, time.time(), agent_name, task))

        # dispatch immediately
        _, _, name, t = await self._task_queue.get()
        ag = self._agents.get(name)
        if not ag:
            return {"status": "error", "reason": "agent missing"}
        try:
            if asyncio.iscoroutinefunction(ag.execute_task):
                return await ag.execute_task(t)
            else:
                return await asyncio.get_event_loop().run_in_executor(None, ag.execute_task, t)
        finally:
            self._task_queue.task_done()

    def get_agent(self, name: str) -> Optional[Any]:
        return self._agents.get(name)

    def agents(self) -> Dict[str, Any]:
        return dict(self._agents)

    def health(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._health)
