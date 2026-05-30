import logging
from typing import Any, Dict, Optional

from graph_db import GraphDB

log = logging.getLogger("jarvis.twin")


class DigitalTwin:
    """Digital Twin engine that keeps a lightweight model of the user and environment.

    Designed to integrate with existing systems by registering as an agent
    with the central AgentManager and reacting to memory events.
    """

    def __init__(self, manager: Any, db_path: str = "jarvis_twin.db"):
        self.manager = manager
        self.graph = GraphDB(db_path)
        self._log = log

    async def handle_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        try:
            if event_type == "MemoryStore":
                content = payload.get("content")
                src = payload.get("source") or payload.get("source_name")
                importance = payload.get("importance", 5)
                node_id = self.graph.add_node(label=content[:250], type="memory", data={"content": content, "source": src, "importance": importance})
                # Link memory to user node (create user node if missing)
                users = self.graph.find_nodes(label="user", type="role", limit=1)
                if users:
                    uid = users[0]["id"]
                else:
                    uid = self.graph.add_node(label="user", type="role", data={"name": "primary"})
                self.graph.add_edge(uid, node_id, relation="has_memory")
        except Exception:
            self._log.exception("DigitalTwin failed processing MemoryStore")

    def summarize(self, limit: int = 10) -> Dict[str, Any]:
        # Return recent memory nodes as a simple summary
        nodes = self.graph.find_nodes(type="memory", limit=limit)
        summary = [{"id": n["id"], "snippet": (n["data"].get("content")[:300] if isinstance(n.get("data"), dict) else ""), "importance": n["data"].get("importance", 5) if isinstance(n.get("data"), dict) else 5} for n in nodes]
        return {"summary_count": len(summary), "items": summary}

    def close(self):
        try:
            self.graph.close()
        except Exception:
            pass
