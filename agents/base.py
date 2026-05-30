"""Base agent interface and simple helpers."""
from typing import Any


class BaseAgent:
    """Minimal agent interface.

    Agents should subclass this and implement `handle_event` for events
    they subscribe to. Agents receive a reference to the manager on init.
    """

    def __init__(self, manager: Any):
        self.manager = manager

    async def start(self) -> None:  # pragma: no cover - optional
        return None

    async def stop(self) -> None:  # pragma: no cover - optional
        return None

    async def handle_event(self, event_type: str, payload: dict) -> None:  # pragma: no cover - implement
        """Handle an incoming event.

        event_type: a short string like 'MemoryStore' or 'TaskCreated'
        payload: event-specific dictionary
        """
        raise NotImplementedError()
