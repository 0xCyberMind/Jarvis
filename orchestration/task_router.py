"""Task router: queue-based async task dispatching with optional priority."""
import asyncio
from typing import Any, Dict, Optional


class TaskRouter:
    def __init__(self, max_workers: int = 4):
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.max_workers = max_workers
        self._workers = []
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        for _ in range(self.max_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()

    async def enqueue(self, payload: Dict[str, Any], priority: int = 50):
        await self.queue.put((priority, payload))

    async def _worker(self):
        while self._running:
            try:
                priority, payload = await self.queue.get()
                # payload must include a callable 'handler' or 'callable'
                handler = payload.get("handler")
                if callable(handler):
                    await handler(payload.get("data"))
            except asyncio.CancelledError:
                break
            except Exception:
                pass
