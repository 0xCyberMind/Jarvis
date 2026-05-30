import threading
from typing import Any, Dict, List, Optional
import time


class SharedContext:
    def __init__(self):
        self._lock = threading.RLock()
        self.active_conversation: List[Dict[str, Any]] = []
        self.active_tasks: List[Dict[str, Any]] = []
        self.memory_refs: List[str] = []
        self.screen_context: Dict[str, Any] = {}
        self.agent_state: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[Dict[str, Any]] = []

    def push_conversation(self, msg: Dict[str, Any]):
        with self._lock:
            self.active_conversation.append({**msg, "ts": time.time()})

    def pop_conversation(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self.active_conversation:
                return self.active_conversation.pop()
            return None

    def add_task(self, task: Dict[str, Any]):
        with self._lock:
            self.active_tasks.append(task)

    def complete_task(self, task_id: str):
        with self._lock:
            for t in self.active_tasks:
                if t.get("id") == task_id:
                    t["completed"] = True
            self.execution_history.append({"task_id": task_id, "completed_at": time.time()})

    def set_agent_state(self, agent_id: str, state: Dict[str, Any]):
        with self._lock:
            self.agent_state[agent_id] = state

    def get_agent_state(self, agent_id: str) -> Dict[str, Any]:
        with self._lock:
            return self.agent_state.get(agent_id, {})

    def add_memory_ref(self, ref: str):
        with self._lock:
            self.memory_refs.append(ref)
