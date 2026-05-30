"""Agent lifecycle manager for lazy activation and health checks."""
import asyncio
from typing import Any
from agents.manager import AgentManager


class AgentLifecycleManager:
    def __init__(self, manager: AgentManager):
        self.manager = manager

    async def activate_agent(self, name: str) -> bool:
        if name not in getattr(self.manager, "agents", {}):
            # attempt to lazy-load via manager if available
            if hasattr(self.manager, "lazy_load"):
                try:
                    await self.manager.lazy_load(name)
                except Exception:
                    return False
        agent = self.manager.get_agent(name) if self.manager.get_agent(name) is not None else None
        if agent and hasattr(agent, "activate"):
            try:
                # prefer start() lifecycle method
                if hasattr(agent, "start"):
                    await agent.start()
                elif hasattr(agent, "activate"):
                    await agent.activate()
            except Exception:
                return False
        return agent is not None

    async def health_check(self, name: str) -> dict:
        if name not in getattr(self.manager, "agents", {}):
            return {"name": name, "status": "missing"}
        agent = self.manager.get_agent(name)
        if hasattr(agent, "health"):
            try:
                return await agent.health()
            except Exception:
                return {"name": name, "status": "unhealthy"}
        return {"name": name, "status": "unknown"}
