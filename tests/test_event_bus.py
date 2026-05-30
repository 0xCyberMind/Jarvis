import asyncio

from events.event_bus import EventBus
from events.event_types import Event


def test_eventbus_sync_handler(tmp_path):
    bus = EventBus()
    called = []

    def handler(ev: Event):
        called.append((ev.type, ev.payload))

    async def run():
        await bus.subscribe("TestEvent", handler)
        await bus.publish(Event(type="TestEvent", payload={"k": "v"}))
        # allow any tasks to complete
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert called and called[0][0] == "TestEvent"
    assert called[0][1]["k"] == "v"
