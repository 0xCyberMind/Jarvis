"""AgentManager: lightweight in-process event bus and agent registry."""
import asyncio
from typing import Any, Callable, Dict, List


class AgentManager:
    """Register agents and route events to subscribed agents.

    This is intentionally small and in-process. Agents subscribe by name
    to event types. Emitting an event will dispatch concurrently to all
    subscribers and await their handlers.
    """

    def __init__(self) -> None:
        self.agents: Dict[str, Any] = {}
        self.subscribers: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def subscribe(self, event_type: str, agent_name: str) -> None:
        self.subscribers.setdefault(event_type, []).append(agent_name)

    def get_agent(self, name: str) -> Any | None:
        return self.agents.get(name)

    async def emit_event(self, event_type: str, payload: dict) -> None:
        """Dispatch event to all subscribed agents concurrently."""
        async with self._lock:
            subs = list(self.subscribers.get(event_type, []))

        tasks = []
        for name in subs:
            agent = self.get_agent(name)
            if not agent:
                continue
            coro = agent.handle_event(event_type, payload)
            tasks.append(asyncio.create_task(coro))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
