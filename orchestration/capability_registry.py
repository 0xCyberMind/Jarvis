"""Registry of capabilities exposed by agents."""
from typing import Dict, Any


class CapabilityRegistry:
    def __init__(self):
        self._caps: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, meta: Dict[str, Any]):
        self._caps[name] = meta

    def get(self, name: str) -> Dict[str, Any]:
        return self._caps.get(name, {})

    def find(self, query: str):
        q = query.lower()
        return {k: v for k, v in self._caps.items() if q in k or q in (v.get("description", "")).lower()}
