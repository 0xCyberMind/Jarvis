import asyncio

from agents.agent_manager import AgentManager
from agents.base_agent import BaseAgent


class DummyAgent(BaseAgent):
    def __init__(self, manager):
        super().__init__(manager, name="Dummy", capabilities=["dummy.cap"]) 

    async def execute_task(self, task):
        return {"status": "ok", "task": task}


def test_register_and_route():
    mgr = AgentManager()
    d = DummyAgent(mgr)
    mgr.register("dummy", d)

    async def run():
        res = await mgr.route_task({"id": "t1"}, capability="dummy.cap")
        assert res["status"] == "ok"

    asyncio.get_event_loop().run_until_complete(run())
