from typing import Any, Dict, List


class WorkflowEngine:
    def __init__(self, action_router: Any) -> None:
        self.action_router = action_router

    async def execute(self, steps: List[str]) -> List[Dict[str, str]]:
        output = []
        for step in steps:
            result = await self.action_router.execute(step)
            output.append({"step": step, "result": result.get("message", str(result))})
        return output
