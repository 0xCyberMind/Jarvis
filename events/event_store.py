"""Simple JSONL-backed EventStore for persistence and replay."""
import json
import threading
from pathlib import Path
from typing import Iterable, Dict, Any, Optional

from events.event_types import Event


class EventStore:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or (Path(__file__).parent.parent / "data" / "events.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, event: Event) -> None:
        record = {
            "type": event.type,
            "payload": event.payload,
            "source": event.source,
            "ts": int(__import__("time").time()),
        }
        line = json.dumps(record, default=str)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def replay(self, since_ts: Optional[int] = None) -> Iterable[Event]:
        if not self.path.exists():
            return []
        out = []
        with self._lock, self.path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                if since_ts and rec.get("ts", 0) < since_ts:
                    continue
                out.append(Event(payload=rec.get("payload", {}), type=rec.get("type", "Event"), source=rec.get("source")))
        return out
