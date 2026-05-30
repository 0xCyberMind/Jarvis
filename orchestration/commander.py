"""Commander: central decision-maker that delegates tasks to agents.

This is non-invasive scaffolding that uses the existing AgentManager.
"""
from typing import Any, Dict, Optional
import asyncio
from agents.manager import AgentManager
from shared_context import SharedContext


class Commander:
    def __init__(self, manager: AgentManager, context: SharedContext):
        self.manager = manager
        self.context = context

    async def decide_and_dispatch(self, intent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Decide which agent should handle the intent and dispatch the task.

        Returns a dict with dispatch result metadata.
        """
        # Simple routing: prefer commander agent if intent is administrative
        if intent.startswith("admin") and "commander" in getattr(self.manager, "agents", {}):
            agent = self.manager.get_agent("commander")
        else:
            # fallback: use planner agent if available
            agent = self.manager.get_agent("planner") if self.manager.get_agent("planner") is not None else None

        if agent is None:
            # fallback to planner
            agent = self.manager.get("planner") if self.manager.has("planner") else None

        if agent is None:
            return {"ok": False, "reason": "no-agent-found"}

        # Ensure agent is active (lazy activation through lifecycle manager normally)
        if hasattr(agent, "start"):
            try:
                await agent.start()
            except Exception:
                pass

        # Dispatch the task
        if hasattr(agent, "handle_intent"):
            res = await agent.handle_intent(intent, payload)
            return {"ok": True, "agent": agent.__class__.__name__, "result": res}
        elif hasattr(agent, "handle"):
            res = await agent.handle(payload)
            return {"ok": True, "agent": agent.__class__.__name__, "result": res}

        return {"ok": False, "reason": "agent-cannot-handle"}
