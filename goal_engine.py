import logging
from typing import Any, Dict, Optional

from planner import TaskPlanner

log = logging.getLogger("jarvis.goals")


class GoalEngine:
    """Goal-driven execution coordinator. Not an agent replacement — registers
    with AgentManager to receive goal requests and uses existing TaskPlanner
    and task_manager to spawn work.
    """

    def __init__(self, manager: Any):
        self.manager = manager
        # task_manager is a global in server.py; we access it at runtime

    async def handle_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        # Accept events of type 'GoalRequest' with payload {'goal': str, 'priority': int}
        try:
            if event_type != "GoalRequest":
                return
            goal = payload.get("goal")
            priority = int(payload.get("priority", 50))
            if not goal:
                return
            # build a plan using TaskPlanner (uses existing planner.py)
            planner = TaskPlanner()
            prompt = planner.build_prompt(goal)
            plan = await planner.start_planning(prompt)
            # spawn plan as tasks using server.task_manager if available
            try:
                from server import task_manager

                # coarse: spawn a single task that contains the plan summary
                task_id = await task_manager.spawn(plan or goal, None)
                # emit TaskCreated event via manager if supported
                if hasattr(self.manager, "emit_event"):
                    await self.manager.emit_event("TaskCreated", {"task_id": task_id, "goal": goal})
            except Exception:
                log.exception("Failed to spawn tasks for goal")
        except Exception:
            log.exception("GoalEngine failed handling event")

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        # Allow manager.route_task to dispatch to this engine
        try:
            # simple echo execution
            return {"status": "accepted", "task": task}
        except Exception:
            log.exception("GoalEngine task execution failed")
            return {"status": "error"}
