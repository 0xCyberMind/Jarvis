"""Windows-only mail access placeholder.

Mail support is disabled in this Windows-focused build.
These functions keep server imports stable and return empty/disabled results.
"""


async def get_accounts() -> list[str]:
    return []


async def get_unread_count() -> dict:
    return {"total": 0, "accounts": {}, "disabled": True}


async def get_recent_messages(count: int = 10) -> list[dict]:
    return []


async def get_unread_messages(count: int = 10) -> list[dict]:
    return []


async def get_messages_from_account(account_name: str, count: int = 10) -> list[dict]:
    return []


async def search_mail(query: str, count: int = 10) -> list[dict]:
    return []


async def read_message(subject_match: str) -> dict | None:
    return None


def format_unread_summary(unread: dict) -> str:
    if unread.get("disabled"):
        return "Mail integration is disabled in this Windows-only build, sir."
    total = unread.get("total", 0)
    return "Inbox is clear, sir. No unread messages." if total == 0 else f"You have {total} unread messages."


def format_messages_for_context(messages: list[dict], label: str = "Recent emails") -> str:
    return f"{label}: mail integration is disabled in this Windows-only build."


def format_messages_for_voice(messages: list[dict]) -> str:
    return "Mail integration is disabled in this Windows-only build, sir."
