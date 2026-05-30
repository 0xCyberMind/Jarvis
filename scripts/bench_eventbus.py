import asyncio
import time

from events.event_bus import EventBus


async def empty_handler(event):
    return True


async def bench_publish(iterations: int = 1000):
    bus = EventBus()
    await bus.subscribe("Ping", empty_handler)
    start = time.time()
    for i in range(iterations):
        await bus.publish(type('E', (), {'type': 'Ping', 'payload': {}})())
    duration = time.time() - start
    print(f"Published {iterations} events in {duration:.3f}s — {iterations/duration:.1f} ev/s")


if __name__ == '__main__':
    asyncio.run(bench_publish(1000))
