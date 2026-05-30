"""Lightweight intent router mapping user intents to capabilities."""
from typing import Optional, Dict


class IntentRouter:
    def __init__(self):
        # simple mapping; can be extended from capabilities registry
        self._map: Dict[str, str] = {}

    def register(self, intent_prefix: str, capability: str):
        self._map[intent_prefix] = capability

    def route(self, text: str) -> Optional[str]:
        txt = text.lower().strip()
        for prefix, cap in self._map.items():
            if txt.startswith(prefix):
                return cap
        return None
