import asyncio

from agents.manager import AgentManager
from agents.memory_agent import MemoryAgent


def test_agent_registration_and_memory_event(tmp_path):
    mgr = AgentManager()
    mem = MemoryAgent(mgr)
    mgr.register("memory", mem)
    mgr.subscribe("MemoryStore", "memory")

    async def run():
        await mgr.emit_event("MemoryStore", {"content": "testing memory", "type": "fact", "importance": 3})

    asyncio.run(run())

    # Verify DB file exists and contains an entry via memory.get_recent_memories
    import memory

    recents = memory.get_recent_memories(5)
    assert any("testing memory" in m["content"] for m in recents)
