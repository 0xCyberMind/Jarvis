import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class TaskItem:
    id: str
    title: str
    status: str
    created_at: str


class TaskManager:
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskItem] = {}
        self._lock = threading.Lock()

    def create_task(self, title: str) -> TaskItem:
        task = TaskItem(
            id=str(uuid.uuid4()),
            title=title,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._tasks[task.id] = task
        return task

    def list_tasks(self) -> List[Dict[str, str]]:
        with self._lock:
            return [asdict(task) for task in self._tasks.values()]

    def update_status(self, task_id: str, status: str) -> Optional[TaskItem]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = status
            return task
