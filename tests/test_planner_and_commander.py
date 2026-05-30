import asyncio

from agents.agent_manager import AgentManager
from agents.planner_agent import PlannerAgent
from agents.commander_agent import CommanderAgent


class DummyResearch:
    def __init__(self, manager):
        self.capabilities = ["research.web"]

    async def execute_task(self, task):
        return {"status": "ok", "results": [{"title": "r1"}], "summary": "res"}


class DummyCoding:
    def __init__(self, manager):
        self.capabilities = ["code.generate"]

    async def execute_task(self, task):
        return {"status": "ok", "stats": {"files": 1}}


class DummySecurity:
    def __init__(self, manager):
        self.capabilities = ["security.check"]

    async def execute_task(self, task):
        return {"status": "ok", "approved": True}


def test_planner_agent_basic():
    mgr = AgentManager()
    pa = PlannerAgent(mgr)
    mgr.register("planner", pa)

    async def run():
        res = await mgr.route_task({"description": "Build a landing page"}, capability="plan.generate")
        assert res["status"] == "ok"

    asyncio.get_event_loop().run_until_complete(run())


def test_commander_orchestration():
    mgr = AgentManager()
    # register dummy agents
    r = DummyResearch(mgr)
    c = DummyCoding(mgr)
    s = DummySecurity(mgr)
    mgr.register("research", r)
    mgr.register("coder", c)
    mgr.register("security", s)

    commander = CommanderAgent(mgr)
    mgr.register("commander", commander)

    async def run():
        out = await commander.execute_task({"op": "intent", "text": "Build a landing page"})
        assert "research" in out and "plan" in out and "code" in out and "security" in out

    asyncio.get_event_loop().run_until_complete(run())
