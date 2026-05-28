"""Windows-only notes access placeholder.

Platform notes support is disabled in this Windows-focused build.
Project memory notes still live in memory.py.
"""


async def get_recent_notes(count: int = 10) -> list[dict]:
    return []


async def read_note(title_match: str) -> dict | None:
    return None


async def search_notes_apple(query: str, count: int = 5) -> list[dict]:
    return []


async def create_apple_note(title: str, body: str, folder: str = "Notes") -> bool:
    return False


def _body_to_html(body: str) -> str:
    return body


async def get_note_folders() -> list[str]:
    return []
