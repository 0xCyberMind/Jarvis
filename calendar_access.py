"""Windows-only calendar access placeholder.

Calendar support is disabled in this Windows-focused build.
These functions keep server imports stable and return empty/disabled results.
"""


async def refresh_cache():
    return None


async def get_todays_events() -> list[dict]:
    return []


async def get_upcoming_events(hours: int = 4) -> list[dict]:
    return []


async def get_next_event() -> dict | None:
    return None


async def get_calendar_names() -> list[str]:
    return []


def format_events_for_context(events: list[dict]) -> str:
    return "Calendar integration is disabled in this Windows-only build."


def format_schedule_summary(events: list[dict]) -> str:
    return "Calendar integration is disabled in this Windows-only build, sir."
