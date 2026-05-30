import asyncio
import time
import logging
from typing import Callable, Dict, List, Optional

from events.event_types import Event
from events.event_store import EventStore

log = logging.getLogger("jarvis.events")
from metrics import event_publish_count, event_publish_latency, event_publish_failures


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._lock = asyncio.Lock()
        self._store = EventStore()

    async def subscribe(self, event_type: str, callback: Callable[[Event], None]):
        async with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)
            log.debug("Subscribed %s to %s", getattr(callback, "__name__", str(callback)), event_type)

    async def unsubscribe(self, event_type: str, callback: Callable[[Event], None]):
        async with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    async def publish(self, event: Event):
        # persist event first for durability
        try:
            self._store.append(event)
        except Exception:
            log.exception("Failed to persist event")

        handlers = []
        async with self._lock:
            handlers = list(self._subscribers.get(event.type, []))

        if not handlers:
            log.debug("No handlers for event %s", event.type)
            return

        tasks = []
        start = time.time()
        for h in handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    tasks.append(asyncio.create_task(h(event)))
                else:
                    # run sync handlers in threadpool
                    tasks.append(asyncio.get_event_loop().run_in_executor(None, h, event))
            except Exception:
                log.exception("Failed to schedule handler %s for event %s", h, event.type)
                event_publish_failures.inc()

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start
            try:
                event_publish_count.inc()
                event_publish_latency.observe(duration)
            except Exception:
                pass
            # count exceptions in results
            for r in results:
                if isinstance(r, Exception):
                    event_publish_failures.inc()

    async def replay(self, since_ts: Optional[int] = None):
        for ev in self._store.replay(since_ts):
            await self.publish(ev)
