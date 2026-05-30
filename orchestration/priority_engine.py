"""Priority engine: compute task priorities from context and metadata."""
from typing import Dict, Any


class PriorityEngine:
    def __init__(self):
        pass

    def score(self, task_meta: Dict[str, Any]) -> int:
        # Lower number == higher priority for PriorityQueue convention
        base = task_meta.get("base_priority", 50)
        urgency = task_meta.get("urgency", 0)
        importance = task_meta.get("importance", 0)
        score = max(1, int(base - (importance * 2 + urgency)))
        return score
