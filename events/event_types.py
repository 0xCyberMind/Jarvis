from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Event:
    payload: Dict[str, Any] = field(default_factory=dict)
    type: str = "Event"
    source: Optional[str] = None


@dataclass
class UserMessageEvent(Event):
    type: str = "UserMessageEvent"


@dataclass
class TaskCreatedEvent(Event):
    type: str = "TaskCreatedEvent"


@dataclass
class TaskCompletedEvent(Event):
    type: str = "TaskCompletedEvent"


@dataclass
class MemoryStoredEvent(Event):
    type: str = "MemoryStoredEvent"


@dataclass
class ScreenChangedEvent(Event):
    type: str = "ScreenChangedEvent"


@dataclass
class SecurityAlertEvent(Event):
    type: str = "SecurityAlertEvent"


@dataclass
class EmailReceivedEvent(Event):
    type: str = "EmailReceivedEvent"


@dataclass
class CalendarUpdatedEvent(Event):
    type: str = "CalendarUpdatedEvent"
