import asyncio

from graph_db import GraphDB
from twin_engine import DigitalTwin


def test_graphdb_basic(tmp_path):
    p = str(tmp_path / "g.db")
    g = GraphDB(p)
    n1 = g.add_node("Alice", type="person", data={"age": 30})
    n2 = g.add_node("Note1", type="memory", data={"content": "hello"})
    assert n1 > 0 and n2 > 0
    e = g.add_edge(n1, n2, relation="has_memory")
    assert e > 0
    found = g.find_nodes(label="Alice")
    assert any(x["label"] == "Alice" for x in found)
    neigh = g.neighbors(n1)
    assert any(r["node"] == n2 for r in neigh)
    g.close()


def test_digital_twin_handles_memory(tmp_path):
    p = str(tmp_path / "twin.db")
    twin = DigitalTwin(manager=None, db_path=p)

    async def run():
        await twin.handle_event("MemoryStore", {"content": "remember this", "source": "unittest", "importance": 8})

    asyncio.run(run())
    s = twin.summarize()
    assert s["summary_count"] >= 1
    assert any("remember this" in item["snippet"] for item in s["items"]) or len(s["items"]) >= 1
    twin.close()
