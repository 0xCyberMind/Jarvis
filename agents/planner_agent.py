import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.planner_agent")


class PlannerAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="PlannerAgent", capabilities=["plan.generate", "plan.decompose"])
        try:
            from planner import TaskPlanner

            self._planner = TaskPlanner()
        except Exception:
            self._planner = None

    async def handle_event(self, event: Any) -> None:
        if getattr(event, "type", "") == "StartPlanning":
            payload = getattr(event, "payload", {})
            user_request = payload.get("request", "")
            projects = payload.get("projects", [])
            client = payload.get("client")
            if not self._planner:
                return
            try:
                result = await self._planner.start_planning(user_request, projects, client)
                if hasattr(self.manager, "emit_event"):
                    await self.manager.emit_event("PlanningResult", {"result": result})
            except Exception:
                log.exception("PlannerAgent event handling failed")

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not self._planner:
            return {"status": "error", "reason": "TaskPlanner not available"}

        # task may contain: description (user request), projects, client
        description = task.get("description") or task.get("prompt") or task.get("request")
        projects: List[Dict[str, Any]] = task.get("projects", [])
        client = task.get("client")

        try:
            await self._planner.start_planning(description or "", projects, client)
            prompt = await self._planner.build_prompt()
            return {"status": "ok", "plan_prompt": prompt}
        except Exception:
            log.exception("PlannerAgent failed to generate plan")
            return {"status": "error", "reason": "planner failed"}
