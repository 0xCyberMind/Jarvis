import asyncio
import logging
import uuid
from typing import Any, Dict, List

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.commander")


class CommanderAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="CommanderAgent", capabilities=["commander.orchestrate"])

    async def handle_event(self, event: Any) -> None:
        # React to user intent events
        if getattr(event, "type", "") == "UserMessageEvent":
            payload = getattr(event, "payload", {})
            await self.process_intent(payload.get("text"), payload)

    async def process_intent(self, text: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        # Very small orchestration pipeline: research -> plan -> code -> security
        manager = self.manager
        request_id = str(uuid.uuid4())
        self.shared_context.push_conversation({"role": "user", "content": text, "id": request_id})

        # 1. research
        research_task = {"op": "query", "query": text}
        research_agents = manager.discover("research.web")
        research_res = None
        if research_agents:
            ra = manager.get_agent(research_agents[0])
            research_res = await ra.execute_task({"query": text})

        # 2. planning
        planner_agents = manager.discover("plan.generate") or manager.discover("plan.decompose")
        plan_res = None
        if planner_agents:
            pa = manager.get_agent(planner_agents[0])
            plan_res = await pa.execute_task({"description": text})

        # 3. coding
        coding_agents = manager.discover("code.generate") or manager.discover("code.patch")
        code_res = None
        if coding_agents:
            ca = manager.get_agent(coding_agents[0])
            code_res = await ca.execute_task({"op": "analyze_repo", "root": "."})

        # 4. security review
        sec_agents = manager.discover("security.check")
        sec_res = None
        if sec_agents:
            sa = manager.get_agent(sec_agents[0])
            sec_res = await sa.execute_task({"op": "audit", "entry": {"request": text}})

        result = {"request_id": request_id, "research": research_res, "plan": plan_res, "code": code_res, "security": sec_res}
        self.shared_context.execution_history.append({"request_id": request_id, "result": result})
        return result

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if task.get("op") == "intent":
            text = task.get("text")
            return await self.process_intent(text, task.get("meta", {}))
        return {"status": "unknown_op"}
"""CommanderAgent: handle OS action requests via `actions.py`.

This agent exposes a safe adapter that invokes existing actions through the
actions module. It intentionally does not change semantics — only routes calls.
"""
from .base import BaseAgent
import actions



