"""
JARVIS Action Executor - Windows-only system actions.

Execute actions immediately before/alongside the LLM response.
Each function returns {"success": bool, "confirmation": str}.

Pipeline:
  detect_action_fast()  →  execute_fast_action()  →  actions here
  LLM [ACTION:X] tags   →  _execute_*()            →  actions here

Normal communication (chat/questions) bypasses this file entirely
and goes straight to generate_response() in server.py.
"""

import asyncio
import ctypes
import datetime
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus
from typing import Optional

try:
    from screen import get_active_windows
except Exception:
    get_active_windows = None

log = logging.getLogger("jarvis.actions")

DESKTOP_PATH = Path.home() / "Desktop"
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = False

# When set, actions will avoid real side-effects (open files, spawn processes).
# Useful for CI/dry-run/testing. Can be enabled via env `JARVIS_DRY_RUN=true`.
DRY_RUN = os.getenv("JARVIS_DRY_RUN", "false").lower() in ("1", "true", "yes")

_SKIP_PERMISSIONS = os.getenv("JARVIS_SKIP_PERMISSIONS", "true").lower() not in ("0", "false", "no")

# ---------------------------------------------------------------------------
# Expanded App Commands
# ---------------------------------------------------------------------------
APP_COMMANDS = {
    # Browsers
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "brave": "brave",
    # Editors / IDEs
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "wordpad": "wordpad",
    # System tools
    "calculator": "calc",
    "calc": "calc",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "terminal": "wt",
    "windows terminal": "wt",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "registry editor": "regedit",
    "regedit": "regedit",
    "snipping tool": "snippingtool",
    "paint": "mspaint",
    "paint 3d": "ms-paint:",
    "camera": "microsoft.windows.camera:",
    # Microsoft Office
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "onenote": "onenote",
    "access": "msaccess",
    "publisher": "mspub",
    # Microsoft Apps
    "teams": "ms-teams:",
    "phone link": "ms-phone:",
    "calendar": "outlookcal:",
    "sticky notes": "ms-stickynotes:",
    "stickynotes": "ms-stickynotes:",
    "sticky note": "ms-stickynotes:",
    "onedrive": "onedrive",
    "skype": "skype:",
    "xbox": "xbox:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "maps": "bingmaps:",
    "weather": "bingweather:",
    "news": "bingnews:",
    "mail": "ms-outlook:",
    "photos": "ms-photos:",
    "movies": "mswindowsvideo:",
    "groove music": "mswindowsmusic:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "alarm": "ms-clock:",
    "timer": "ms-clock:",
    "stopwatch": "ms-clock:",
    # Media
    "spotify": "spotify",
    "vlc": "vlc",
    "windows media player": "wmplayer",
    # Communication
    "whatsapp": "whatsapp",
    "whats app": "whatsapp",
    "whatspp": "whatsapp",
    "watsapp": "whatsapp",
    "telegram": "telegram",
    "discord": "discord",
    "zoom": "zoom",
    # Utilities
    "7zip": "7zfm",
    "winrar": "winrar",
    "notepad": "notepad",
}

WINDOWS_APP_FALLBACKS = {
    "whatsapp": [
        ("uri", "whatsapp:"),
        ("shell", r"shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"),
        ("path", str(Path(os.environ.get("LocalAppData", "")) / "WhatsApp" / "WhatsApp.exe")),
    ],
    "spotify": [
        ("uri", "spotify:"),
        ("shell", r"shell:AppsFolder\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
    ],
    "telegram": [
        ("path", str(Path(os.environ.get("AppData", "")) / "Telegram Desktop" / "Telegram.exe")),
    ],
    "discord": [
        ("path", str(Path(os.environ.get("LocalAppData", "")) / "Discord" / "Update.exe")),
    ],
    "onedrive": [
        ("path", str(Path(os.environ.get("LocalAppData", "")) / "Microsoft" / "OneDrive" / "OneDrive.exe")),
    ],
}

# ---------------------------------------------------------------------------
# JARVIS Personality Message System
# ---------------------------------------------------------------------------

_MSG_TEMPLATES = {
    "success_open": [
        "{app} is open, sir.",
        "Pulled up {app}, sir.",
        "{app} is ready, sir.",
        "Opening {app} now, sir.",
        "There you go — {app} is up.",
    ],
    "success_action": [
        "Done, sir.",
        "Consider it done, sir.",
        "Right away, sir.",
        "Handled, sir.",
        "Will do, sir.",
    ],
    "fail_open": [
        "I couldn't open {app}, sir.",
        "Trouble opening {app}, sir.",
        "{app} didn't respond, sir.",
        "I'm afraid {app} isn't cooperating, sir.",
    ],
    "fail_action": [
        "I couldn't complete that, sir.",
        "That didn't work, sir.",
        "I ran into a problem, sir.",
        "I'm afraid that failed, sir.",
    ],
    "success_file": [
        "File ready at {path}, sir.",
        "Created {name}, sir.",
        "Done — {name} is saved, sir.",
    ],
    "success_copy": [
        "Copied to clipboard, sir.",
        "In your clipboard, sir.",
        "Clipboard updated, sir.",
    ],
    "success_delete": [
        "Deleted, sir.",
        "Gone, sir.",
        "Removed, sir.",
    ],
    "success_network": [
        "Network check complete, sir.",
        "Here's the network status, sir.",
    ],
    "success_system": [
        "System check complete, sir.",
        "Here's what I found, sir.",
    ],
}

# Add a touch of British phrasing options
_MSG_TEMPLATES.setdefault("success_action").extend([
    "Righto, sir.",
    "Very good, sir.",
])


def _pick(key: str, **kwargs) -> str:
    """Pick a varied JARVIS message from a template pool."""
    import random
    templates = _MSG_TEMPLATES.get(key, ["{key}"])
    msg = random.choice(templates)
    try:
        return msg.format(**kwargs)
    except KeyError:
        return msg


def _time_greeting() -> str:
    """Return a time-appropriate greeting prefix."""
    hour = datetime.datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------

def applescript_escape(s: str) -> str:
    """Compatibility helper kept for server imports; normalizes text to one line."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", " ")


def _windows_terminal_command(command: str, cwd: str | None = None) -> tuple[str, list[str]]:
    shell_command = command or "powershell"
    if cwd:
        shell_command = f'Set-Location -LiteralPath "{cwd}"; {shell_command}'

    wt = shutil.which("wt")
    if wt:
        return wt, ["powershell", "-NoExit", "-Command", shell_command]

    powershell = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    return powershell, ["-NoExit", "-Command", shell_command]


async def _open_windows_terminal(command: str = "", cwd: str | None = None) -> bool:
    exe, args = _windows_terminal_command(command, cwd)
    try:
        await asyncio.create_subprocess_exec(
            exe,
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        log.error(f"open_windows_terminal failed: {e}")
        return False


def _find_windows_browser(browser: str) -> str | None:
    names = ["firefox"] if browser.lower() == "firefox" else ["chrome", "msedge"]
    for name in names:
        path = shutil.which(name)
        if path:
            return path

    if browser.lower() == "firefox":
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "Mozilla Firefox" / "firefox.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Mozilla Firefox" / "firefox.exe",
        ]
    else:
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LocalAppData", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Core Browser / Terminal / Path Actions
# ---------------------------------------------------------------------------

async def open_terminal(command: str = "") -> dict:
    success = await _open_windows_terminal(command)
    return {
        "success": success,
        "confirmation": "PowerShell is open, sir." if success else "I had trouble opening PowerShell, sir.",
    }


async def open_browser(url: str, browser: str = "chrome") -> dict:
    app_name = "Firefox" if browser.lower() == "firefox" else "Chrome"
    if url.startswith("file://"):
        raw_path = url.removeprefix("file://")
        try:
            url = Path(raw_path).resolve().as_uri()
        except Exception:
            pass

    browser_path = _find_windows_browser(browser)
    try:
        if DRY_RUN:
            log.debug(f"DRY_RUN: open_browser {url} in {browser}")
            return {"success": True, "confirmation": f"(dry-run) Pulled that up in {app_name}, sir."}

        if browser_path:
            await asyncio.create_subprocess_exec(
                browser_path,
                url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            os.startfile(url)  # type: ignore[attr-defined]
        return {"success": True, "confirmation": f"Pulled that up in {app_name}, sir."}
    except Exception as e:
        log.error(f"open_browser ({app_name}) failed: {e}")
        return {"success": False, "confirmation": f"{app_name} ran into a problem, sir."}


async def open_chrome(url: str) -> dict:
    return await open_browser(url, "chrome")


async def open_incognito(url: str = "", browser: str = "chrome") -> dict:
    """Open a URL in incognito/private mode."""
    target_url = url.strip() or "about:blank"
    try:
        if browser.lower() == "firefox":
            browser_path = _find_windows_browser("firefox")
            flag = "--private-window"
        else:
            browser_path = _find_windows_browser("chrome")
            flag = "--incognito"

        if browser_path:
            await asyncio.create_subprocess_exec(
                browser_path, flag, target_url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            mode = "private" if browser.lower() == "firefox" else "incognito"
            return {"success": True, "confirmation": f"Opened {mode} window, sir."}
        return {"success": False, "confirmation": "Browser not found, sir."}
    except Exception as e:
        log.error(f"open_incognito failed: {e}")
        return {"success": False, "confirmation": "I couldn't open an incognito window, sir."}


async def open_path(path: str) -> dict:
    try:
        if DRY_RUN:
            log.debug(f"DRY_RUN: open_path {path}")
            return {"success": True, "confirmation": "(dry-run) Opened it in Windows Explorer, sir."}
        os.startfile(path)  # type: ignore[attr-defined]
        return {"success": True, "confirmation": "Opened it in Windows Explorer, sir."}
    except Exception as e:
        log.error(f"open_path failed: {e}")
        return {"success": False, "confirmation": "I had trouble opening that, sir."}


async def edit_file(path: str) -> dict:
    """Open a file for editing. Prefer VS Code if available, otherwise use the platform default."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "confirmation": "That file does not exist, sir."}

        code = shutil.which("code")
        if code:
            if DRY_RUN:
                log.debug(f"DRY_RUN: open editor 'code' {p}")
                return {"success": True, "confirmation": f"(dry-run) Opened {p.name} in VS Code, sir."}
            await asyncio.create_subprocess_exec(code, str(p), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            return {"success": True, "confirmation": f"Opened {p.name} in VS Code, sir."}

        try:
            if DRY_RUN:
                log.debug(f"DRY_RUN: startfile {p}")
                return {"success": True, "confirmation": f"(dry-run) Opened {p.name}, sir."}
            os.startfile(str(p))  # type: ignore[attr-defined]
            return {"success": True, "confirmation": f"Opened {p.name}, sir."}
        except Exception:
            if DRY_RUN:
                log.debug(f"DRY_RUN: fallback notepad {p}")
                return {"success": True, "confirmation": f"(dry-run) Opened {p.name} in Notepad, sir."}
            await _run_detached("notepad", str(p))
            return {"success": True, "confirmation": f"Opened {p.name} in Notepad, sir."}
    except Exception as e:
        log.error(f"edit_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't open that file, sir."}


async def run_command_detached(*args: str) -> dict:
    """Run a shell command detached (non-blocking)."""
    try:
        ok = await _run_detached(*args)
        return {"success": ok, "confirmation": "Command started, sir." if ok else "I couldn't start that command, sir."}
    except Exception as e:
        log.error(f"run_command_detached failed: {e}")
        return {"success": False, "confirmation": "I couldn't start that command, sir."}


async def create_task_action(title: str, description: str = "") -> dict:
    """Create a task in the Jarvis memory system (if available)."""
    try:
        from memory import create_task
        create_task(title=title, description=description or "", priority="medium")
        return {"success": True, "confirmation": f"Added task: {title}."}
    except Exception as e:
        log.error(f"create_task_action failed: {e}")
        return {"success": False, "confirmation": "I couldn't create the task, sir."}


async def open_url(url: str, browser: str = "chrome") -> dict:
    """Open a URL in the preferred browser."""
    try:
        return await open_browser(url, browser)
    except Exception as e:
        log.error(f"open_url failed: {e}")
        return {"success": False, "confirmation": "I couldn't open the URL, sir."}


# ---------------------------------------------------------------------------
# Power Management
# ---------------------------------------------------------------------------

async def shutdown_pc(delay_seconds: int = 30) -> dict:
    try:
        await asyncio.create_subprocess_exec(
            "shutdown", "/s", "/t", str(delay_seconds),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"success": True, "confirmation": f"Shutdown scheduled in {delay_seconds} seconds, sir."}
    except Exception as e:
        log.error(f"shutdown_pc failed: {e}")
        return {"success": False, "confirmation": "I couldn't schedule the shutdown, sir."}


async def restart_pc(delay_seconds: int = 30) -> dict:
    try:
        await asyncio.create_subprocess_exec(
            "shutdown", "/r", "/t", str(delay_seconds),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"success": True, "confirmation": f"Restart scheduled in {delay_seconds} seconds, sir."}
    except Exception as e:
        log.error(f"restart_pc failed: {e}")
        return {"success": False, "confirmation": "I couldn't schedule the restart, sir."}


async def cancel_power_action() -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/a",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        success = proc.returncode == 0
        return {
            "success": success,
            "confirmation": "Pending power action cancelled, sir." if success else "No pending power action to cancel, sir.",
        }
    except Exception as e:
        log.error(f"cancel_power_action failed: {e}")
        return {"success": False, "confirmation": "I couldn't cancel the power action, sir."}


# ---------------------------------------------------------------------------
# Keyboard / Input Helpers
# ---------------------------------------------------------------------------

async def _send_windows_keys(keys: str) -> bool:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{keys}')"
    )
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    return proc.returncode == 0


def _press_vk_combo_sync(keys: list[int]) -> None:
    user32 = ctypes.windll.user32
    keybd_event = user32.keybd_event
    for key in keys:
        keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        keybd_event(key, 0, 2, 0)


async def _press_vk_combo(keys: list[int]) -> bool:
    try:
        await asyncio.to_thread(_press_vk_combo_sync, keys)
        return True
    except Exception as e:
        log.error(f"press_vk_combo failed: {e}")
        return False


async def _open_windows_search_and_type(query: str) -> bool:
    try:
        if not await _press_vk_combo([0x5B, 0x53]):  # Win+S
            return False
        await asyncio.sleep(0.8)
        if not await _send_windows_keys(query):
            return False
        await asyncio.sleep(0.4)
        return await _press_vk_combo([0x0D])  # Enter
    except Exception as e:
        log.error(f"open_windows_search_and_type failed: {e}")
        return False


async def _confirm_app_visible(app_name: str, timeout: float = 6.0) -> bool:
    if get_active_windows is None:
        return True
    target = app_name.lower().strip()
    start = time.time()
    while time.time() - start < timeout:
        try:
            windows = await get_active_windows()
            for window in windows:
                app = str(window.get("app", "")).lower()
                title = str(window.get("title", "")).lower()
                if target in app or target in title:
                    return True
        except Exception as e:
            log.debug(f"confirm_app_visible failed: {e}")
        await asyncio.sleep(0.5)
    return False


async def _run_detached(*args: str) -> bool:
    try:
        if DRY_RUN:
            log.debug(f"DRY_RUN: _run_detached {args}")
            return True
        await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        log.error(f"run_detached failed ({args}): {e}")
        return False


async def _open_uri_or_path(target: str) -> bool:
    try:
        if DRY_RUN:
            log.debug(f"DRY_RUN: open uri/path {target}")
            return True
        await asyncio.to_thread(os.startfile, target)  # type: ignore[attr-defined]
        return True
    except Exception as e:
        log.debug(f"startfile failed for {target}: {e}")
        return False


# ---------------------------------------------------------------------------
# Search Helpers
# ---------------------------------------------------------------------------

def is_keyword_only(query: str) -> bool:
    """Return True if the query looks like keywords (not a URL or domain)."""
    if not query or not query.strip():
        return False
    q = query.strip()
    if re.search(r"\bhttps?://|www\.|/|@", q, flags=re.I):
        return False
    if re.search(r"\b[\w-]+\.[a-z]{2,}\b", q, flags=re.I):
        return False
    return True


async def open_youtube_search(query: str) -> dict:
    """Open YouTube search results for keyword-only queries."""
    q = (query or "").strip()
    if not q:
        return {"success": False, "confirmation": "No search query provided for YouTube, sir."}
    if not is_keyword_only(q):
        return {"success": False, "confirmation": "Please provide keywords only for YouTube search, not a URL, sir."}

    try:
        await open_browser("https://www.youtube.com", "chrome")
        await asyncio.sleep(1.0)
        await _send_windows_keys("^l")
        await asyncio.sleep(0.2)
        await _send_windows_keys(q)
        await asyncio.sleep(0.1)
        await _send_windows_keys("{ENTER}")
        return {"success": True, "confirmation": f"Searched YouTube for '{q}', sir."}
    except Exception as e:
        log.debug(f"Keyboard YouTube search failed: {e}")
        url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
        return await open_browser(url, "chrome")


async def open_google_search(query: str) -> dict:
    """Open Google search results for keyword-only queries."""
    q = (query or "").strip()
    if not q:
        return {"success": False, "confirmation": "No search query provided for Google, sir."}
    if not is_keyword_only(q):
        return {"success": False, "confirmation": "Please provide keywords only for Google search, not a URL, sir."}
    url = f"https://www.google.com/search?q={quote_plus(q)}"
    return await open_browser(url, "chrome")


# ---------------------------------------------------------------------------
# Task Splitting
# ---------------------------------------------------------------------------

def split_into_tasks(text: str) -> list[str]:
    """Naively split a freeform instruction into smaller tasks."""
    if not text:
        return []
    parts = re.split(r"[.;]\s+|\band\b|\bthen\b|,\s*", text, flags=re.I)
    tasks = [p.strip() for p in parts if p and p.strip()]
    return tasks


async def split_into_tasks_advanced(text: str, use_llm: bool = False, client=None, model: str | None = None) -> list[str]:
    """Advanced task splitter with optional LLM assistance."""
    if not text or not text.strip():
        return []
    if use_llm and client:
        try:
            prompt = (
                "You are an assistant that converts a user's freeform request into a concise ordered "
                "list of actionable tasks. Return ONLY valid JSON: an array of short task strings, "
                "for example: [\"Create project folder\", \"Initialize git\", \"Write README\"]"
            )
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ]
            kwargs = {}
            if model:
                kwargs["model"] = model

            resp = await client.chat.completions.create(messages=messages, max_tokens=300, **kwargs)
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            import json as _json
            try:
                parsed = _json.loads(content)
                if isinstance(parsed, list):
                    return [p.strip() for p in parsed if isinstance(p, str) and p.strip()]
            except Exception:
                lines = [l.strip(" -\n\r\t") for l in content.splitlines() if l.strip()]
                if lines:
                    return lines
        except Exception as e:
            log.debug(f"LLM task split failed: {e}")

    return split_into_tasks(text)


# ---------------------------------------------------------------------------
# App Launching Internals
# ---------------------------------------------------------------------------

async def _open_shell_app(shell_target: str) -> bool:
    return await _run_detached("explorer.exe", shell_target)


async def _launch_windows_app(command: str) -> bool:
    if command.endswith(":") or command.startswith("ms-"):
        return await _open_uri_or_path(command)

    executable = shutil.which(command)
    if executable:
        return await _run_detached(executable)

    for kind, target in WINDOWS_APP_FALLBACKS.get(command, []):
        if kind == "uri" and await _open_uri_or_path(target):
            return True
        if kind == "shell" and await _open_shell_app(target):
            return True
        if kind == "path" and target and Path(target).exists() and await _run_detached(target):
            return True

    return await _run_detached(command)


async def open_app(app_name: str) -> dict:
    name = app_name.lower().strip()
    command = APP_COMMANDS.get(name, name)
    try:
        if name in {"whatsapp", "whats app", "whatspp", "watsapp"}:
            opened = await _open_windows_search_and_type("WhatsApp")
            confirmed = await _confirm_app_visible("whatsapp")
            success = opened or confirmed
            return {
                "success": success,
                "confirmation": "Opening WhatsApp from Windows search, sir." if success else "I couldn't open WhatsApp from Windows search, sir.",
            }
        if command in {"chrome", "msedge", "firefox"}:
            return await open_browser("about:blank", "firefox" if command == "firefox" else "chrome")
        success = await _launch_windows_app(command)
        return {
            "success": success,
            "confirmation": _pick("success_open", app=app_name) if success else _pick("fail_open", app=app_name),
        }
    except Exception as e:
        log.error(f"open_app failed: {e}")
        return {"success": False, "confirmation": _pick("fail_open", app=app_name)}


async def list_running_apps(limit: int = 20) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            "tasklist", "/FO", "CSV", "/NH",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        names: list[str] = []
        for line in stdout.decode(errors="replace").splitlines():
            if line.strip():
                names.append(line.split('","')[0].strip('"'))
        unique = sorted(set(names), key=str.lower)
        shown = ", ".join(unique[:limit])
        extra = len(unique) - limit
        suffix = f", plus {extra} more" if extra > 0 else ""
        return {"success": True, "confirmation": f"Running apps: {shown}{suffix}."}
    except Exception as e:
        log.error(f"list_running_apps failed: {e}")
        return {"success": False, "confirmation": "I couldn't list running apps, sir."}


async def close_app_by_name(app_name: str) -> dict:
    name = app_name.lower().strip().replace(".exe", "")
    executable = APP_COMMANDS.get(name, name).lower().replace(".exe", "")
    if executable in {"chrome", "msedge", "firefox"}:
        target = f"{executable}.exe"
    elif executable == "code":
        target = "code.exe"
    elif executable == "calc":
        target = "calculatorapp.exe"
    else:
        target = f"{executable}.exe"

    try:
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/IM", target, "/T",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        success = proc.returncode == 0
        return {
            "success": success,
            "confirmation": f"Closed {app_name}, sir." if success else f"I couldn't find {app_name} running, sir.",
        }
    except Exception as e:
        log.error(f"close_app_by_name failed: {e}")
        return {"success": False, "confirmation": f"I couldn't close {app_name}, sir."}


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

async def get_clipboard_text() -> dict:
    script = "Get-Clipboard -Raw"
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        text = stdout.decode(errors="replace").strip()
        if not text:
            return {"success": True, "confirmation": "Clipboard is empty, sir."}
        preview = text[:300].replace("\r", " ").replace("\n", " ")
        return {"success": True, "confirmation": f"Clipboard contains: {preview}"}
    except Exception as e:
        log.error(f"get_clipboard_text failed: {e}")
        return {"success": False, "confirmation": "I couldn't read the clipboard, sir."}


async def clear_clipboard() -> dict:
    success = await _run_detached("powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ''")
    return {"success": success, "confirmation": "Clipboard cleared, sir." if success else "I couldn't clear the clipboard, sir."}

async def copy_text_to_clipboard(text: str) -> dict:
    escaped = text.replace("'", "''")
    script = f"Set-Clipboard -Value '{escaped}'"
    success = await _run_detached("powershell", "-NoProfile", "-Command", script)
    return {"success": success, "confirmation": _pick("success_copy") if success else "I couldn't copy that, sir."}


# ---------------------------------------------------------------------------
# Screenshot / Screen Recording
# ---------------------------------------------------------------------------

async def save_screenshot() -> dict:
    pictures = Path.home() / "Pictures" / "Jarvis"
    pictures.mkdir(parents=True, exist_ok=True)
    path = pictures / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    ps_path = str(path).replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save('{ps_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        success = proc.returncode == 0 and path.exists()
        return {
            "success": success,
            "confirmation": f"Screenshot saved to {path}, sir." if success else "I couldn't save the screenshot, sir.",
        }
    except Exception as e:
        log.error(f"save_screenshot failed: {e}")
        return {"success": False, "confirmation": "I couldn't save the screenshot, sir."}


async def screen_record() -> dict:
    success = await _open_uri_or_path("ms-gamebar:")
    return {"success": success, "confirmation": "Xbox Game Bar is open for screen recording, sir." if success else "I couldn't open screen recording controls, sir."}


async def open_snipping_tool() -> dict:
    success = await _open_uri_or_path("ms-screenclip:")
    if not success:
        success = await _run_detached("snippingtool")
    return {"success": success, "confirmation": "Snipping Tool is ready, sir." if success else "I couldn't open Snipping Tool, sir."}


# ---------------------------------------------------------------------------
# Display / Audio
# ---------------------------------------------------------------------------

async def set_brightness(level: int) -> dict:
    level = max(0, min(100, level))
    script = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        success = proc.returncode == 0
        return {"success": success, "confirmation": f"Brightness set to {level} percent, sir." if success else "Brightness control is unavailable on this display, sir."}
    except Exception as e:
        log.error(f"set_brightness failed: {e}")
        return {"success": False, "confirmation": "Brightness control is unavailable on this display, sir."}


async def set_volume(level: int) -> dict:
    """Set system volume to a specific percentage (0-100)."""
    level = max(0, min(100, level))
    script = (
        f"$obj = New-Object -ComObject WScript.Shell; "
        f"$vol = [math]::Round({level} / 2); "
        f"for ($i=0; $i -lt 50; $i++) {{ $obj.SendKeys([char]174) }}; "
        f"for ($i=0; $i -lt $vol; $i++) {{ $obj.SendKeys([char]175) }}"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=8)
        return {"success": True, "confirmation": f"Volume set to approximately {level} percent, sir."}
    except Exception as e:
        log.error(f"set_volume failed: {e}")
        return {"success": False, "confirmation": "I couldn't set the volume, sir."}


# ---------------------------------------------------------------------------
# System Status
# ---------------------------------------------------------------------------

async def battery_status() -> dict:
    script = """
$b = Get-CimInstance Win32_Battery
if ($null -eq $b) { "No battery detected. Running on AC power." }
else {
  $state = if ($b.BatteryStatus -eq 2) { "charging" } elseif ($b.BatteryStatus -eq 1) { "discharging" } else { "status $($b.BatteryStatus)" }
  "Battery is at $($b.EstimatedChargeRemaining) percent, $state."
}
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        text = stdout.decode(errors="replace").strip()
        return {"success": bool(text), "confirmation": text or "I couldn't read battery status, sir."}
    except Exception as e:
        log.error(f"battery_status failed: {e}")
        return {"success": False, "confirmation": "I couldn't read battery status, sir."}


async def network_status() -> dict:
    script = """
$profile = Get-NetConnectionProfile | Select-Object -First 1
$adapter = Get-NetAdapter | Where-Object Status -eq Up | Select-Object -First 1
if ($profile) { "Network: $($profile.Name), $($profile.NetworkCategory). Adapter: $($adapter.Name)." }
else { "No active network profile detected." }
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6)
        text = stdout.decode(errors="replace").strip()
        return {"success": bool(text), "confirmation": text or "I couldn't read network status, sir."}
    except Exception as e:
        log.error(f"network_status failed: {e}")
        return {"success": False, "confirmation": "I couldn't read network status, sir."}


async def get_time_and_date() -> dict:
    """Return the current time and date."""
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p")
    date_str = now.strftime("%A, %B %d, %Y")
    greeting = _time_greeting()
    return {
        "success": True,
        "confirmation": f"{greeting}, sir. It is {time_str} on {date_str}.",
    }


async def get_ip_address() -> dict:
    """Get local and public IP addresses."""
    try:
        # Local IP
        local_ip = "unknown"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        return {
            "success": True,
            "confirmation": f"Your local IP address is {local_ip}, sir.",
        }
    except Exception as e:
        log.error(f"get_ip_address failed: {e}")
        return {"success": False, "confirmation": "I couldn't retrieve the IP address, sir."}


async def get_public_ip() -> dict:
    """Get the public IP address via PowerShell."""
    script = "(Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing).Content"
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        ip = stdout.decode(errors="replace").strip()
        if ip:
            return {"success": True, "confirmation": f"Your public IP address is {ip}, sir."}
        return {"success": False, "confirmation": "I couldn't retrieve the public IP, sir."}
    except Exception as e:
        log.error(f"get_public_ip failed: {e}")
        return {"success": False, "confirmation": "I couldn't retrieve the public IP, sir."}


async def check_internet_connection() -> dict:
    """Check if internet is reachable."""
    script = "Test-Connection 8.8.8.8 -Count 2 -Quiet"
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        result = stdout.decode(errors="replace").strip().lower()
        connected = result == "true"
        return {
            "success": True,
            "confirmation": "Internet connection is active, sir." if connected else "No internet connection detected, sir.",
        }
    except Exception as e:
        log.error(f"check_internet_connection failed: {e}")
        return {"success": False, "confirmation": "I couldn't check the internet connection, sir."}


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def _run_powershell(script: str, timeout: float = 12, capture: bool = True) -> tuple[bool, str]:
    try:
        if DRY_RUN:
            log.debug(f"DRY_RUN: _run_powershell script={script[:120]!r} timeout={timeout}")
            return True, "(dry-run)"

        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        text = ((stdout or b"") + (b"\n" + stderr if stderr else b"")).decode(errors="replace").strip()
        return proc.returncode == 0, text
    except Exception as e:
        log.error(f"PowerShell action failed: {e}")
        return False, ""


async def open_settings_page(page: str, label: str) -> dict:
    result = await open_path(page)
    return {
        "success": result["success"],
        "confirmation": f"{label} is open, sir." if result["success"] else f"I couldn't open {label}, sir.",
    }


async def power_manager() -> dict:
    ok, text = await _run_powershell(
        "$scheme = powercfg /getactivescheme; "
        "$b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue; "
        "$battery = if ($b) { \"Battery $($b.EstimatedChargeRemaining) percent.\" } else { \"No battery detected.\" }; "
        "\"$battery $scheme\"",
        timeout=8,
    )
    return {"success": ok and bool(text), "confirmation": text or "I couldn't read power status, sir."}


async def set_power_saver(enabled: bool = True) -> dict:
    scheme = "SCHEME_MAX" if enabled else "SCHEME_BALANCED"
    success = await _run_detached("powercfg", "/setactive", scheme)
    return {
        "success": success,
        "confirmation": "Battery saver power plan enabled, sir." if success and enabled else
                        "Balanced power plan enabled, sir." if success else
                        "I couldn't change the power plan, sir.",
    }


async def pc_temperature() -> dict:
    script = """
$temps = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue
if (-not $temps) { "Temperature sensors are unavailable on this PC." }
else {
  $values = $temps | ForEach-Object { [math]::Round(($_.CurrentTemperature / 10) - 273.15, 1) }
  "Temperature readings: " + (($values | ForEach-Object { "$_ C" }) -join ", ")
}
"""
    ok, text = await _run_powershell(script, timeout=8)
    return {"success": ok and "unavailable" not in text.lower(), "confirmation": text or "I couldn't read PC temperature, sir."}


async def disk_cleaner() -> dict:
    cleanmgr = shutil.which("cleanmgr")
    if cleanmgr:
        success = await _run_detached(cleanmgr, "/verylowdisk")
        return {"success": success, "confirmation": "Disk Cleanup has started, sir." if success else "I couldn't start Disk Cleanup, sir."}
    return await open_settings_page("ms-settings:storagesense", "Storage Sense")


async def empty_trash() -> dict:
    ok, text = await _run_powershell("Clear-RecycleBin -Force -ErrorAction Stop", timeout=20)
    return {"success": ok, "confirmation": "Recycle Bin emptied, sir." if ok else text or "I couldn't empty the Recycle Bin, sir."}


async def network_speed() -> dict:
    script = """
$p = Test-Connection 8.8.8.8 -Count 4 -ErrorAction SilentlyContinue
if (-not $p) { "Network speed check failed. No ping response." }
else {
  $avg = [math]::Round(($p | Measure-Object ResponseTime -Average).Average, 1)
  "Network latency averages $avg ms to 8.8.8.8."
}
"""
    ok, text = await _run_powershell(script, timeout=12)
    return {"success": ok and "failed" not in text.lower(), "confirmation": text or "I couldn't test the network, sir."}


async def clear_temp_files() -> dict:
    """Clear Windows temp files."""
    script = """
$temp = $env:TEMP
$count = 0
Get-ChildItem -Path $temp -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    try { Remove-Item $_.FullName -Force -Recurse -ErrorAction SilentlyContinue; $count++ } catch {}
}
"Cleared $count temp items."
"""
    ok, text = await _run_powershell(script, timeout=30)
    return {"success": ok, "confirmation": text or "Temp files cleared, sir." if ok else "I couldn't clear temp files, sir."}


async def flush_dns() -> dict:
    """Flush the DNS resolver cache."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ipconfig", "/flushdns",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=8)
        success = proc.returncode == 0
        return {"success": success, "confirmation": "DNS cache flushed, sir." if success else "I couldn't flush the DNS cache, sir."}
    except Exception as e:
        log.error(f"flush_dns failed: {e}")
        return {"success": False, "confirmation": "I couldn't flush the DNS cache, sir."}


# ---------------------------------------------------------------------------
# File Operations
# ---------------------------------------------------------------------------

async def make_folder(path_or_name: str) -> dict:
    raw = path_or_name.strip() or f"New Folder {time.strftime('%Y%m%d_%H%M%S')}"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = DESKTOP_PATH / raw
    try:
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "confirmation": f"Folder ready at {path}, sir.", "path": str(path)}
    except Exception as e:
        log.error(f"make_folder failed: {e}")
        return {"success": False, "confirmation": "I couldn't create that folder, sir."}


async def create_text_file(path: str, content: str = "") -> dict:
    """Create a text file with optional content."""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = DESKTOP_PATH / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "confirmation": _pick("success_file", path=str(p), name=p.name), "path": str(p)}
    except Exception as e:
        log.error(f"create_text_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't create that file, sir."}


async def write_text_file(path: str, content: str) -> dict:
    """Create or overwrite a text file with explicit content."""
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = DESKTOP_PATH / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "confirmation": f"Updated {p.name}, sir.", "path": str(p)}
    except Exception as e:
        log.error(f"write_text_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't edit that file, sir."}


async def search_files_by_name(query: str, directory: str = "") -> dict:
    """Search for files matching a name pattern."""
    search_dir = Path(directory).expanduser() if directory else Path.home()
    if not search_dir.exists():
        search_dir = Path.home()
    try:
        matches = list(search_dir.rglob(f"*{query}*"))[:20]
        if not matches:
            return {"success": True, "confirmation": f"No files matching '{query}' found, sir."}
        names = ", ".join(str(m) for m in matches[:8])
        extra = len(matches) - 8
        suffix = f", and {extra} more" if extra > 0 else ""
        return {"success": True, "confirmation": f"Found {len(matches)} file(s): {names}{suffix}."}
    except Exception as e:
        log.error(f"search_files_by_name failed: {e}")
        return {"success": False, "confirmation": "I couldn't search for files, sir."}


async def copy_path_to_clipboard(path_text: str) -> dict:
    path = Path(path_text.strip()).expanduser()
    return await copy_text_to_clipboard(str(path))


async def move_file(source: str, destination: str) -> dict:
    """Move a file or folder to a new location."""
    src = Path(source.strip()).expanduser()
    dst = Path(destination.strip()).expanduser()
    if not src.exists():
        return {"success": False, "confirmation": "Source path does not exist, sir."}
    try:
        import shutil as _shutil
        _shutil.move(str(src), str(dst))
        return {"success": True, "confirmation": f"Moved {src.name} to {dst}, sir."}
    except Exception as e:
        log.error(f"move_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't move that file, sir."}


async def copy_file(source: str, destination: str) -> dict:
    """Copy a file or folder to a new location."""
    src = Path(source.strip()).expanduser()
    dst = Path(destination.strip()).expanduser()
    if not src.exists():
        return {"success": False, "confirmation": "Source path does not exist, sir."}
    try:
        import shutil as _shutil
        if src.is_dir():
            _shutil.copytree(str(src), str(dst))
        else:
            _shutil.copy2(str(src), str(dst))
        return {"success": True, "confirmation": f"Copied {src.name} to {dst}, sir."}
    except Exception as e:
        log.error(f"copy_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't copy that file, sir."}


async def get_file_info(path: str) -> dict:
    """Get metadata about a file or folder."""
    p = Path(path.strip()).expanduser()
    if not p.exists():
        return {"success": False, "confirmation": "That path does not exist, sir."}
    try:
        stat = p.stat()
        size_bytes = stat.st_size
        size = f"{size_bytes / (1024**2):.1f} MB" if size_bytes >= 1024**2 else f"{size_bytes / 1024:.1f} KB"
        modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%B %d, %Y at %I:%M %p")
        kind = "folder" if p.is_dir() else "file"
        return {
            "success": True,
            "confirmation": f"{p.name} is a {kind}, {size}, last modified {modified}, sir.",
        }
    except Exception as e:
        log.error(f"get_file_info failed: {e}")
        return {"success": False, "confirmation": "I couldn't get file info, sir."}


async def list_directory(path: str = "") -> dict:
    """List contents of a directory."""
    target = Path(path.strip()).expanduser() if path.strip() else Path.home()
    if not target.exists() or not target.is_dir():
        return {"success": False, "confirmation": "That directory does not exist, sir."}
    try:
        items = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        folders = [i.name for i in items if i.is_dir()][:10]
        files = [i.name for i in items if i.is_file()][:10]
        parts = []
        if folders:
            parts.append(f"Folders: {', '.join(folders)}")
        if files:
            parts.append(f"Files: {', '.join(files)}")
        total = len(list(target.iterdir()))
        return {
            "success": True,
            "confirmation": f"{target.name} contains {total} items. {'. '.join(parts)}.",
        }
    except Exception as e:
        log.error(f"list_directory failed: {e}")
        return {"success": False, "confirmation": "I couldn't list that directory, sir."}


async def zip_files(target: str) -> dict:
    source = Path(target.strip()).expanduser()
    if not source.exists():
        return {"success": False, "confirmation": "That file or folder does not exist, sir."}
    zip_path = source.with_suffix(".zip") if source.is_file() else source.parent / f"{source.name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            if source.is_file():
                archive.write(source, source.name)
            else:
                for item in source.rglob("*"):
                    if item.is_file():
                        archive.write(item, item.relative_to(source.parent))
        return {"success": True, "confirmation": f"Created {zip_path}, sir.", "path": str(zip_path)}
    except Exception as e:
        log.error(f"zip_files failed: {e}")
        return {"success": False, "confirmation": "I couldn't create the zip file, sir."}


async def unzip_files(target: str) -> dict:
    source = Path(target.strip()).expanduser()
    if not source.exists() or source.suffix.lower() != ".zip":
        return {"success": False, "confirmation": "Please provide a valid zip file, sir."}
    dest = source.with_suffix("")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as archive:
            archive.extractall(dest)
        return {"success": True, "confirmation": f"Extracted to {dest}, sir.", "path": str(dest)}
    except Exception as e:
        log.error(f"unzip_files failed: {e}")
        return {"success": False, "confirmation": "I couldn't extract that zip file, sir."}


async def folder_size(target: str) -> dict:
    path = Path(target.strip()).expanduser()
    if not path.exists():
        return {"success": False, "confirmation": "That path does not exist, sir."}
    try:
        total = path.stat().st_size if path.is_file() else sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        size_gb = total / (1024 ** 3)
        size_mb = total / (1024 ** 2)
        size = f"{size_gb:.2f} GB" if size_gb >= 1 else f"{size_mb:.1f} MB"
        return {"success": True, "confirmation": f"{path.name} is {size}, sir."}
    except Exception as e:
        log.error(f"folder_size failed: {e}")
        return {"success": False, "confirmation": "I couldn't calculate the folder size, sir."}


async def rename_file(target: str) -> dict:
    if "|||" in target:
        old_text, _, new_text = target.partition("|||")
    elif " to " in target:
        old_text, new_text = target.rsplit(" to ", 1)
    else:
        return {"success": False, "confirmation": "Tell me the old path and new name, sir."}
    old = Path(old_text.strip()).expanduser()
    if not old.exists():
        return {"success": False, "confirmation": "The original file was not found, sir."}
    new = Path(new_text.strip()).expanduser()
    if not new.is_absolute():
        new = old.with_name(new_text.strip())
    try:
        old.rename(new)
        return {"success": True, "confirmation": f"Renamed to {new.name}, sir.", "path": str(new)}
    except Exception as e:
        log.error(f"rename_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't rename that, sir."}


async def make_shortcut(target: str) -> dict:
    source = Path(target.strip()).expanduser()
    if not source.exists():
        return {"success": False, "confirmation": "That target does not exist, sir."}
    shortcut = DESKTOP_PATH / f"{source.stem}.lnk"
    script = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut({_ps_quote(str(shortcut))}); "
        f"$s.TargetPath = {_ps_quote(str(source))}; "
        "$s.Save()"
    )
    ok, text = await _run_powershell(script, timeout=8)
    return {"success": ok, "confirmation": "Shortcut created on the desktop, sir." if ok else text or "I couldn't create the shortcut, sir."}


async def hide_file(target: str, hidden: bool = True) -> dict:
    path = Path(target.strip()).expanduser()
    if not path.exists():
        return {"success": False, "confirmation": "That path does not exist, sir."}
    flag = "+h" if hidden else "-h"
    success = await _run_detached("attrib", flag, str(path))
    return {"success": success, "confirmation": "Hidden attribute updated, sir." if success else "I couldn't update that file attribute, sir."}


async def show_hidden_files(enable: bool = True) -> dict:
    value = 1 if enable else 2
    script = (
        "Set-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced "
        f"-Name Hidden -Value {value}; Stop-Process -Name explorer -Force"
    )
    ok, text = await _run_powershell(script, timeout=8)
    return {"success": ok, "confirmation": "Hidden file visibility updated, sir." if ok else text or "I couldn't update hidden file visibility, sir."}


async def delete_file(target: str, permanent: bool = False) -> dict:
    path = Path(target.strip()).expanduser()
    if not path.exists():
        return {"success": False, "confirmation": "That path does not exist, sir."}
    try:
        if permanent:
            if path.is_dir():
                return {"success": False, "confirmation": "Permanent folder deletion is blocked for safety, sir."}
            path.unlink()
            return {"success": True, "confirmation": _pick("success_delete")}
        script = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile({_ps_quote(str(path))}, "
            "'OnlyErrorDialogs', 'SendToRecycleBin')"
        )
        ok, text = await _run_powershell(script, timeout=10)
        return {"success": ok, "confirmation": "Moved to Recycle Bin, sir." if ok else text or "I couldn't delete that file, sir."}
    except Exception as e:
        log.error(f"delete_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't delete that file, sir."}


async def shred_file(target: str) -> dict:
    path = Path(target.strip()).expanduser()
    if not path.exists() or not path.is_file():
        return {"success": False, "confirmation": "Please provide a real file to shred, sir."}
    try:
        size = path.stat().st_size
        with path.open("r+b") as f:
            f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
        return {"success": True, "confirmation": "File shredded, sir."}
    except Exception as e:
        log.error(f"shred_file failed: {e}")
        return {"success": False, "confirmation": "I couldn't shred that file, sir."}


async def clean_desktop() -> dict:
    folder = DESKTOP_PATH / f"Jarvis Cleaned Desktop {time.strftime('%Y%m%d_%H%M%S')}"
    try:
        items = [p for p in DESKTOP_PATH.iterdir() if p.name != folder.name and not p.name.startswith(".")]
        movable = [p for p in items if p.is_file()]
        if not movable:
            return {"success": True, "confirmation": "Desktop already looks clean, sir."}
        folder.mkdir(exist_ok=True)
        moved = 0
        for item in movable:
            try:
                item.rename(folder / item.name)
                moved += 1
            except Exception:
                continue
        return {"success": moved > 0, "confirmation": f"Moved {moved} desktop file(s) into {folder.name}, sir."}
    except Exception as e:
        log.error(f"clean_desktop failed: {e}")
        return {"success": False, "confirmation": "I couldn't clean the desktop, sir."}

async def change_wallpaper(target: str) -> dict:
    path = Path(target.strip()).expanduser()
    if not path.exists():
        return {"success": False, "confirmation": "That wallpaper image was not found, sir."}
    try:
        ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)
        return {"success": True, "confirmation": "Wallpaper changed, sir."}
    except Exception as e:
        log.error(f"change_wallpaper failed: {e}")
        return {"success": False, "confirmation": "I couldn't change the wallpaper, sir."}


# ---------------------------------------------------------------------------
# Folder Navigation
# ---------------------------------------------------------------------------

async def open_downloads() -> dict:
    return await open_path(str(Path.home() / "Downloads"))

async def open_documents() -> dict:
    return await open_path(str(Path.home() / "Documents"))

async def open_pictures() -> dict:
    return await open_path(str(Path.home() / "Pictures"))

async def open_music() -> dict:
    return await open_path(str(Path.home() / "Music"))

async def open_videos() -> dict:
    return await open_path(str(Path.home() / "Videos"))

async def go_home() -> dict:
    return await open_path(str(Path.home()))

async def open_desktop_folder() -> dict:
    return await open_path(str(DESKTOP_PATH))

async def open_temp_folder() -> dict:
    temp = os.environ.get("TEMP", str(Path.home() / "AppData" / "Local" / "Temp"))
    return await open_path(temp)

async def open_appdata_folder() -> dict:
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return await open_path(appdata)

async def open_program_files() -> dict:
    pf = os.environ.get("ProgramFiles", "C:\\Program Files")
    return await open_path(pf)

async def open_recycle_bin() -> dict:
    success = await _run_detached("explorer.exe", "shell:RecycleBinFolder")
    return {"success": success, "confirmation": "Recycle Bin is open, sir." if success else "I couldn't open the Recycle Bin, sir."}

async def open_this_pc() -> dict:
    success = await _run_detached("explorer.exe", "shell:MyComputerFolder")
    return {"success": success, "confirmation": "This PC is open, sir." if success else "I couldn't open This PC, sir."}

async def open_onedrive_folder() -> dict:
    onedrive = os.environ.get("OneDrive", str(Path.home() / "OneDrive"))
    if Path(onedrive).exists():
        return await open_path(onedrive)
    return {"success": False, "confirmation": "OneDrive folder not found, sir."}

async def open_startup_folder() -> dict:
    startup = str(Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
    return await open_path(startup)


# ---------------------------------------------------------------------------
# Windows System Tools
# ---------------------------------------------------------------------------

async def open_control_panel() -> dict:
    success = await _run_detached("control")
    return {"success": success, "confirmation": "Control Panel is open, sir." if success else "I couldn't open Control Panel, sir."}

async def open_device_manager() -> dict:
    success = await _run_detached("devmgmt.msc")
    return {"success": success, "confirmation": "Device Manager is open, sir." if success else "I couldn't open Device Manager, sir."}

async def open_event_viewer() -> dict:
    success = await _run_detached("eventvwr.msc")
    return {"success": success, "confirmation": "Event Viewer is open, sir." if success else "I couldn't open Event Viewer, sir."}

async def open_services() -> dict:
    success = await _run_detached("services.msc")
    return {"success": success, "confirmation": "Services manager is open, sir." if success else "I couldn't open Services, sir."}

async def open_resource_monitor() -> dict:
    success = await _run_detached("resmon")
    return {"success": success, "confirmation": "Resource Monitor is open, sir." if success else "I couldn't open Resource Monitor, sir."}

async def open_task_scheduler() -> dict:
    success = await _run_detached("taskschd.msc")
    return {"success": success, "confirmation": "Task Scheduler is open, sir." if success else "I couldn't open Task Scheduler, sir."}

async def open_computer_management() -> dict:
    success = await _run_detached("compmgmt.msc")
    return {"success": success, "confirmation": "Computer Management is open, sir." if success else "I couldn't open Computer Management, sir."}

async def open_credential_manager() -> dict:
    return await open_settings_page("ms-settings:credentialproviders", "Credential Manager")

async def open_disk_management() -> dict:
    success = await _run_detached("diskmgmt.msc")
    return {"success": success, "confirmation": "Disk Management is open, sir." if success else "I couldn't open Disk Management, sir."}

async def open_registry_editor() -> dict:
    success = await _run_detached("regedit")
    return {"success": success, "confirmation": "Registry Editor is open, sir." if success else "I couldn't open Registry Editor, sir."}

async def open_system_properties() -> dict:
    success = await _run_detached("sysdm.cpl")
    return {"success": success, "confirmation": "System Properties is open, sir." if success else "I couldn't open System Properties, sir."}

async def open_environment_variables() -> dict:
    script = "Start-Process sysdm.cpl -ArgumentList ',3'"
    ok, _ = await _run_powershell(script, timeout=5, capture=False)
    return {"success": ok, "confirmation": "Environment Variables dialog is open, sir." if ok else "I couldn't open Environment Variables, sir."}

async def open_windows_security() -> dict:
    return await open_settings_page("windowsdefender:", "Windows Security")

async def open_startup_apps() -> dict:
    return await open_settings_page("ms-settings:startupapps", "Startup Apps settings")

async def open_group_policy() -> dict:
    success = await _run_detached("gpedit.msc")
    return {"success": success, "confirmation": "Group Policy Editor is open, sir." if success else "I couldn't open Group Policy Editor, sir."}

async def open_performance_monitor() -> dict:
    success = await _run_detached("perfmon")
    return {"success": success, "confirmation": "Performance Monitor is open, sir." if success else "I couldn't open Performance Monitor, sir."}

async def open_magnifier() -> dict:
    success = await _run_detached("magnify")
    return {"success": success, "confirmation": "Magnifier is open, sir." if success else "I couldn't open Magnifier, sir."}

async def open_on_screen_keyboard() -> dict:
    success = await _run_detached("osk")
    return {"success": success, "confirmation": "On-Screen Keyboard is open, sir." if success else "I couldn't open the On-Screen Keyboard, sir."}

async def open_narrator() -> dict:
    success = await _run_detached("narrator")
    return {"success": success, "confirmation": "Narrator is running, sir." if success else "I couldn't start Narrator, sir."}

async def open_sticky_notes() -> dict:
    return await open_app("sticky notes")

async def open_onenote() -> dict:
    return await open_app("onenote")

async def open_outlook() -> dict:
    return await open_app("outlook")

async def open_teams() -> dict:
    return await open_app("teams")

async def open_windows_update() -> dict:
    return await open_settings_page("ms-settings:windowsupdate", "Windows Update")

async def open_windows_defender() -> dict:
    return await open_windows_security()

async def open_firewall_settings() -> dict:
    return await open_settings_page("ms-settings:privacy-general", "Windows Firewall")

async def open_network_sharing_center() -> dict:
    success = await _run_detached("control", "/name", "Microsoft.NetworkAndSharingCenter")
    return {"success": success, "confirmation": "Network and Sharing Center is open, sir." if success else "I couldn't open Network and Sharing Center, sir."}

async def open_wifi_settings() -> dict:
    return await open_settings_page("ms-settings:network-wifi", "Wi-Fi settings")

async def open_ethernet_settings() -> dict:
    return await open_settings_page("ms-settings:network-ethernet", "Ethernet settings")

async def open_vpn_settings() -> dict:
    return await open_settings_page("ms-settings:network-vpn", "VPN settings")

async def open_proxy_settings() -> dict:
    return await open_settings_page("ms-settings:network-proxy", "Proxy settings")

async def open_display_settings() -> dict:
    return await open_settings_page("ms-settings:display", "Display settings")

async def open_sound_settings() -> dict:
    return await open_settings_page("ms-settings:sound", "Sound settings")

async def open_power_options() -> dict:
    return await open_settings_page("ms-settings:powersleep", "Power & sleep settings")

async def open_storage_settings() -> dict:
    return await open_settings_page("ms-settings:storagesense", "Storage settings")

async def open_default_apps() -> dict:
    return await open_settings_page("ms-settings:defaultapps", "Default apps settings")

async def open_optional_features() -> dict:
    return await open_settings_page("ms-settings:optionalfeatures", "Optional features settings")

async def open_about_settings() -> dict:
    return await open_settings_page("ms-settings:about", "About settings")

async def open_privacy_settings() -> dict:
    return await open_settings_page("ms-settings:privacy", "Privacy settings")

async def open_accessibility_settings() -> dict:
    return await open_settings_page("ms-settings:easeofaccess", "Accessibility settings")

async def open_language_settings() -> dict:
    return await open_settings_page("ms-settings:regionlanguage", "Language settings")

async def open_time_settings() -> dict:
    return await open_settings_page("ms-settings:dateandtime", "Date and time settings")

async def open_accounts_settings() -> dict:
    return await open_settings_page("ms-settings:accounts", "Accounts settings")

async def open_gaming_settings() -> dict:
    return await open_settings_page("ms-settings:gaming-gamemode", "Gaming settings")

async def open_bluetooth_settings() -> dict:
    return await open_settings_page("ms-settings:bluetooth", "Bluetooth settings")

async def open_mouse_settings() -> dict:
    return await open_settings_page("ms-settings:mousetouchpad", "Mouse settings")

async def open_keyboard_settings() -> dict:
    return await open_settings_page("ms-settings:keyboard", "Keyboard settings")

async def open_notification_settings() -> dict:
    return await open_settings_page("ms-settings:notifications", "Notifications settings")

async def open_night_light() -> dict:
    return await open_settings_page("ms-settings:nightlight", "Night light settings")

async def open_printer_settings() -> dict:
    return await open_settings_page("ms-settings:printers", "Printer settings")


async def open_camera_settings() -> dict:
    return await open_settings_page("ms-settings:privacy-webcam", "Camera settings")

async def open_microphone_settings() -> dict:
    return await open_settings_page("ms-settings:privacy-microphone", "Microphone settings")

async def open_remote_desktop() -> dict:
    return await open_settings_page("ms-settings:remotedesktop", "Remote Desktop settings")

async def open_windows_store() -> dict:
    return await open_app("store")

async def open_maps() -> dict:
    return await open_app("maps")

async def open_weather_app() -> dict:
    return await open_app("weather")

async def open_news_app() -> dict:
    return await open_app("news")

async def open_clock_app() -> dict:
    return await open_app("clock")

async def open_photos_app() -> dict:
    return await open_app("photos")

async def open_calculator_app() -> dict:
    return await open_app("calculator")


# ---------------------------------------------------------------------------
# Windows System Status
# ---------------------------------------------------------------------------

async def windows_system_status() -> dict:
    script = """
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$os = Get-CimInstance Win32_OperatingSystem
$freeRam = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
$totalRam = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeDisk = [math]::Round($disk.FreeSpace / 1GB, 1)
$totalDisk = [math]::Round($disk.Size / 1GB, 1)
"CPU $cpu percent. RAM $freeRam GB free of $totalRam GB. C drive $freeDisk GB free of $totalDisk GB."
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        text = stdout.decode(errors="replace").strip()
        return {"success": bool(text), "confirmation": text or "I couldn't read system status, sir."}
    except Exception as e:
        log.error(f"windows_system_status failed: {e}")
        return {"success": False, "confirmation": "I couldn't read system status, sir."}


# ---------------------------------------------------------------------------
# Window Management
# ---------------------------------------------------------------------------

async def lock_pc() -> dict:
    try:
        ctypes.windll.user32.LockWorkStation()
        return {"success": True, "confirmation": "Workstation locked, sir."}
    except Exception as e:
        log.error(f"lock_pc failed: {e}")
        return {"success": False, "confirmation": "I couldn't lock the workstation, sir."}


async def sleep_pc() -> dict:
    success = await _run_detached("rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0")
    return {"success": success, "confirmation": "Putting the system to sleep, sir." if success else "I couldn't put the system to sleep, sir."}


async def hibernate_pc() -> dict:
    success = await _run_detached("shutdown", "/h")
    return {"success": success, "confirmation": "Hibernating the system, sir." if success else "I couldn't hibernate the system, sir."}


async def open_task_manager() -> dict:
    success = await _run_detached("taskmgr")
    return {"success": success, "confirmation": "Task Manager is open, sir." if success else "I couldn't open Task Manager, sir."}


async def open_settings() -> dict:
    success = await open_path("ms-settings:")
    return {"success": success["success"], "confirmation": "Settings is open, sir." if success["success"] else "I couldn't open Settings, sir."}


async def open_file_explorer() -> dict:
    success = await _run_detached("explorer")
    return {"success": success, "confirmation": "File Explorer is open, sir." if success else "I couldn't open File Explorer, sir."}


async def show_desktop() -> dict:
    script = "(New-Object -ComObject Shell.Application).ToggleDesktop()"
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-Command", script,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    success = proc.returncode == 0
    return {"success": success, "confirmation": "Desktop shown, sir." if success else "I couldn't show the desktop, sir."}


async def switch_window() -> dict:
    success = await _press_vk_combo([0x12, 0x09])  # Alt+Tab
    return {"success": success, "confirmation": "Switched windows, sir." if success else "I couldn't switch windows, sir."}


async def snap_window_left() -> dict:
    success = await _press_vk_combo([0x5B, 0x25])  # Win+Left
    return {"success": success, "confirmation": "Window snapped left, sir." if success else "I couldn't snap the window left, sir."}


async def snap_window_right() -> dict:
    success = await _press_vk_combo([0x5B, 0x27])  # Win+Right
    return {"success": success, "confirmation": "Window snapped right, sir." if success else "I couldn't snap the window right, sir."}


async def minimize_window() -> dict:
    success = await _send_windows_keys("%{SPACE}n")
    return {"success": success, "confirmation": "Window minimized, sir." if success else "I couldn't minimize the window, sir."}


async def maximize_window() -> dict:
    success = await _send_windows_keys("%{SPACE}x")
    return {"success": success, "confirmation": "Window maximized, sir." if success else "I couldn't maximize the window, sir."}


# ---------------------------------------------------------------------------
# Media / Volume
# ---------------------------------------------------------------------------

async def volume_up() -> dict:
    success = await _press_vk_combo([0xAF])
    return {"success": success, "confirmation": "Volume increased, sir." if success else "I couldn't increase the volume, sir."}


async def volume_down() -> dict:
    success = await _press_vk_combo([0xAE])
    return {"success": success, "confirmation": "Volume lowered, sir." if success else "I couldn't lower the volume, sir."}


async def mute_volume() -> dict:
    success = await _press_vk_combo([0xAD])
    return {"success": success, "confirmation": "Volume toggled, sir." if success else "I couldn't toggle mute, sir."}


async def media_play_pause() -> dict:
    success = await _press_vk_combo([0xB3])
    return {"success": success, "confirmation": "Media toggled, sir." if success else "I couldn't toggle media playback, sir."}


async def media_next() -> dict:
    success = await _press_vk_combo([0xB0])
    return {"success": success, "confirmation": "Next track, sir." if success else "I couldn't skip the track, sir."}


async def media_previous() -> dict:
    success = await _press_vk_combo([0xB1])
    return {"success": success, "confirmation": "Previous track, sir." if success else "I couldn't go to the previous track, sir."}


# ---------------------------------------------------------------------------
# Relative volume helpers
# ---------------------------------------------------------------------------
async def change_volume_by(delta_percent: int) -> dict:
    """Change system volume by a relative percentage (positive or negative).

    This approximates volume steps by sending multiple virtual-key volume up/down
    key events. Each key press adjusts roughly ~2% on many systems, so we send
    delta_percent / 2 key presses to achieve the requested change.
    """
    try:
        delta = int(delta_percent)
    except Exception:
        return {"success": False, "confirmation": "I couldn't parse that volume amount, sir."}

    if delta == 0:
        return {"success": True, "confirmation": "Volume unchanged, sir."}

    steps = max(1, abs(round(delta / 2)))
    # Choose SendKeys char: 175 = VK_VOLUME_UP, 174 = VK_VOLUME_DOWN
    char = 175 if delta > 0 else 174
    script = (
        f"$obj = New-Object -ComObject WScript.Shell; "
        f"for ($i=0; $i -lt {steps}; $i++) {{ $obj.SendKeys([char]{char}) }}"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=8)
        verb = "increased" if delta > 0 else "decreased"
        return {"success": True, "confirmation": f"Volume {verb} by approximately {abs(delta)} percent, sir."}
    except Exception as e:
        log.error(f"change_volume_by failed: {e}")
        return {"success": False, "confirmation": "I couldn't adjust the volume, sir."}


async def volume_up_by(percent: int) -> dict:
    return await change_volume_by(abs(int(percent)))


async def volume_down_by(percent: int) -> dict:
    return await change_volume_by(-abs(int(percent)))


# ---------------------------------------------------------------------------
# Tab / Window Close
# ---------------------------------------------------------------------------

async def close_active_tab() -> dict:
    try:
        success = await _send_windows_keys("^w")
        return {"success": success, "confirmation": "Closed the active tab, sir." if success else "I couldn't close the active tab, sir."}
    except Exception as e:
        log.error(f"close_active_tab failed: {e}")
        return {"success": False, "confirmation": "I couldn't close the active tab, sir."}


async def close_active_window() -> dict:
    try:
        success = await _send_windows_keys("%{F4}")
        return {"success": success, "confirmation": "Closed the active window, sir." if success else "I couldn't close the active window, sir."}
    except Exception as e:
        log.error(f"close_active_window failed: {e}")
        return {"success": False, "confirmation": "I couldn't close the active window, sir."}


def _tasklist_process_name(pid: int) -> str:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=2,
        )
        output = result.stdout.decode(errors="replace").strip()
        return output.split('","')[0].strip('"').lower() if output else ""
    except Exception:
        return ""


def _close_windows_browsers_sync() -> int:
    closed = 0
    user32 = ctypes.windll.user32
    browser_names = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
    current_pid = os.getpid()
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        nonlocal closed
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = int(pid.value)
        if pid_value == current_pid:
            return True
        if _tasklist_process_name(pid_value) in browser_names:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            closed += 1
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return closed


async def close_all_browser_windows() -> dict:
    try:
        closed = await asyncio.to_thread(_close_windows_browsers_sync)
        success = closed > 0
        return {
            "success": success,
            "confirmation": f"Closed {closed} browser window{'s' if closed != 1 else ''}, sir." if success else "No browser windows found to close, sir.",
        }
    except Exception as e:
        log.error(f"close_all_browser_windows failed: {e}")
        return {"success": False, "confirmation": "I couldn't close the browser windows, sir."}


def _close_all_windows_sync() -> int:
    """Close all visible top-level windows except the current process."""
    closed = 0
    user32 = ctypes.windll.user32
    current_pid = os.getpid()
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        nonlocal closed
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) == current_pid:
            return True
        if user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        closed += 1
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return closed


async def close_all_windows() -> dict:
    try:
        closed = await asyncio.to_thread(_close_all_windows_sync)
        success = closed > 0
        return {
            "success": success,
            "confirmation": f"Closed {closed} window{'s' if closed != 1 else ''}, sir." if success else "No open windows found to close, sir.",
        }
    except Exception as e:
        log.error(f"close_all_windows failed: {e}")
        return {"success": False, "confirmation": "I couldn't close the windows, sir."}


async def focus_mode() -> dict:
    closed = await close_all_browser_windows()
    await mute_volume()
    opened = await open_app("vs code")
    if opened["success"]:
        return {"success": True, "confirmation": "Focus mode is ready, sir. Browsers closed, volume muted, and VS Code is open."}
    return {"success": False, "confirmation": f"Focus mode partly applied. {closed['confirmation']} VS Code did not open."}


# ---------------------------------------------------------------------------
# Claude / Project Actions
# ---------------------------------------------------------------------------

async def open_claude_in_project(project_dir: str, prompt: str) -> dict:
    claude_md = Path(project_dir) / "CLAUDE.md"
    claude_md.write_text(f"# Task\n\n{prompt}\n\nBuild this completely. If web app, make index.html work standalone.\n")
    skip_flag = " --dangerously-skip-permissions" if _SKIP_PERMISSIONS else ""
    success = await _open_windows_terminal(f"& claude{skip_flag}", project_dir)
    return {
        "success": success,
        "confirmation": "Claude Code is running in PowerShell, sir. You can watch the progress."
        if success
        else "Had trouble spawning Claude Code, sir.",
    }


async def prompt_existing_terminal(project_name: str, prompt: str) -> dict:
    return {
        "success": False,
        "confirmation": f"Couldn't attach to an existing terminal for {project_name}, sir.",
    }


async def get_chrome_tab_info() -> dict:
    return {}


async def monitor_build(project_dir: str, ws=None, synthesize_fn=None) -> None:
    import base64
    output_file = Path(project_dir) / ".jarvis_output.txt"
    start = time.time()
    timeout = 600

    while time.time() - start < timeout:
        await asyncio.sleep(5)
        if output_file.exists():
            content = output_file.read_text()
            if "--- JARVIS TASK COMPLETE ---" in content:
                log.info(f"Build complete in {project_dir}")
                if ws and synthesize_fn:
                    try:
                        msg = "The build is complete, sir."
                        audio_bytes = await synthesize_fn(msg)
                        if audio_bytes:
                            encoded = base64.b64encode(audio_bytes).decode()
                            await ws.send_json({"type": "status", "state": "speaking"})
                            await ws.send_json({"type": "audio", "data": encoded, "text": msg})
                            await ws.send_json({"type": "status", "state": "idle"})
                    except Exception as e:
                        log.warning(f"Build notification failed: {e}")
                return

    log.warning(f"Build timed out in {project_dir}")


# ---------------------------------------------------------------------------
# Utility Helpers
# ---------------------------------------------------------------------------

def _norm_action_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


async def _not_configured(feature: str, requirement: str) -> dict:
    return {"success": False, "confirmation": f"{feature} needs {requirement} configured first, sir."}


async def log_out() -> dict:
    return {"success": False, "confirmation": "Log out is blocked from direct execution for safety, sir. Ask for shutdown or lock screen instead."}


# ---------------------------------------------------------------------------
# handle_feature_action — central dispatcher for feature aliases
# ---------------------------------------------------------------------------

async def handle_feature_action(action: str, target: str = "") -> dict | None:
    """Windows/local feature aliases owned by actions.py.

    Returns None for features owned by server.py, memory.py, security.py,
    browser.py, work_mode.py, frontend voice code, or integration modules.
    """
    name = _norm_action_name(action)

    aliases = {
        # System info
        "system_info": "system_info", "pc_status": "system_info",
        "power_manager": "power_manager",
        # Display / audio
        "volume_control": "volume_control", "brightness_control": "brightness_control",
        "set_volume": "set_volume",
        # Direct volume commands
        "volume": "set_volume",
        "volume_up": "volume_up",
        "volume_down": "volume_down",
        "volume_up_by": "volume_up_by",
        "volume_down_by": "volume_down_by",
        "change_volume": "change_volume",
        # Apps
        "app_launcher": "app_launcher", "file_opener": "file_opener",
        # Power
        "battery_saver": "battery_saver", "pc_temp_check": "pc_temp_check",
        # Maintenance
        "disk_cleaner": "disk_cleaner", "empty_trash": "empty_trash",
        "clear_temp": "clear_temp", "flush_dns": "flush_dns",
        # Network
        "wifi_manager": "wifi_manager", "network_speed": "network_speed",
        "check_internet": "check_internet", "get_ip": "get_ip", "get_public_ip": "get_public_ip",
        "wifi_settings": "wifi_settings", "ethernet_settings": "ethernet_settings",
        "vpn_settings": "vpn_settings", "proxy_settings": "proxy_settings",
        "network_sharing": "network_sharing",
        # Security / lock
        "lock_screen": "lock_screen",
        # Screen
        "screenshot": "screenshot", "screen_record": "screen_record",
        # Input
        "mic_control": "mic_control", "webcam_control": "webcam_control",
        "mouse_speed": "mouse_speed", "keyboard_lights": "keyboard_lights",
        # System settings
        "time_sync": "time_sync", "notifications": "notifications",
        "night_mode": "night_mode", "eye_care": "eye_care",
        "bluetooth_connect": "bluetooth_connect", "printer_setup": "printer_setup",
        "phone_link": "phone_link", "game_mode": "game_mode",
        "task_manager": "task_manager", "auto_update": "auto_update",
        "display_settings": "display_settings", "sound_settings": "sound_settings",
        "power_options": "power_options", "storage_settings": "storage_settings",
        "default_apps": "default_apps", "optional_features": "optional_features",
        "about_settings": "about_settings", "privacy_settings": "privacy_settings",
        "accessibility": "accessibility", "language_settings": "language_settings",
        "time_settings": "time_settings", "accounts_settings": "accounts_settings",
        "gaming_settings": "gaming_settings", "bluetooth_settings": "bluetooth_settings",
        "mouse_settings": "mouse_settings", "keyboard_settings": "keyboard_settings",
        "notification_settings": "notification_settings", "night_light": "night_light",
        "printer_settings": "printer_settings", "camera_settings": "camera_settings",
        "microphone_settings": "microphone_settings", "remote_desktop": "remote_desktop",
        "firewall_settings": "firewall_settings",
        # Windows tools
        "control_panel": "control_panel", "device_manager": "device_manager",
        "event_viewer": "event_viewer", "services": "services",
        "resource_monitor": "resource_monitor", "task_scheduler": "task_scheduler",
        "computer_management": "computer_management", "credential_manager": "credential_manager",
        "disk_management": "disk_management", "registry_editor": "registry_editor",
        "system_properties": "system_properties", "environment_variables": "environment_variables",
        "windows_security": "windows_security", "startup_apps": "startup_apps",
        "group_policy": "group_policy", "performance_monitor": "performance_monitor",
        "magnifier": "magnifier", "on_screen_keyboard": "on_screen_keyboard",
        "narrator": "narrator",
        "sticky_notes": "sticky_notes", "onenote": "onenote",
        "outlook": "outlook", "teams": "teams",
        "windows_update": "windows_update", "windows_store": "windows_store",
        "maps_app": "maps_app", "weather_app": "weather_app",
        "news_app": "news_app", "clock_app": "clock_app",
        "photos_app": "photos_app", "calculator_app": "calculator_app",
        "window_move": "window_move", "auto_scroll": "auto_scroll",
        "remote_control": "remote_control", "clipboard_history": "clipboard_history",
        "pin_to_top": "pin_to_top", "quick_search": "quick_search",
        "folder_maker": "folder_maker",
        "change_wallpaper": "change_wallpaper", "clean_desktop": "clean_desktop",
        "screen_ruler": "screen_ruler", "color_picker": "color_picker",
        "snipping_tool": "snipping_tool", "snap_windows": "snap_windows",
        "multi_monitor": "multi_monitor", "refresh_desktop": "refresh_desktop",
        "delete_file": "delete_file", "copy_path": "copy_path",
        "zip_files": "zip_files", "unzip_files": "unzip_files",
        "hide_files": "hide_files", "show_hidden": "show_hidden",
        "rename_files": "rename_files", "make_shortcut": "make_shortcut",
        "shred_file": "shred_file", "folder_size": "folder_size",
        "sync_folders": "sync_folders", "cloud_backup": "cloud_backup",
        "move_file": "move_file", "copy_file": "copy_file",
        "get_file_info": "get_file_info", "list_directory": "list_directory",
        "create_file": "create_file", "search_files": "search_files",
        "downloads_folder": "downloads_folder", "go_home": "go_home",
        "documents_folder": "documents_folder", "pictures_folder": "pictures_folder",
        "music_folder": "music_folder", "videos_folder": "videos_folder",
        "desktop_folder": "desktop_folder", "temp_folder": "temp_folder",
        "appdata_folder": "appdata_folder", "program_files": "program_files",
        "recycle_bin": "recycle_bin", "this_pc": "this_pc",
        "onedrive_folder": "onedrive_folder", "startup_folder": "startup_folder",
        "get_time": "get_time", "get_date": "get_date",
        "get_local_ip": "get_local_ip",
        "log_out": "log_out",
        "set_alarm": "set_alarm", "stopwatch": "stopwatch", "timer": "timer",
        "pdf_reader": "pdf_reader",
        "excel_helper": "excel_helper", "word_helper": "word_helper",
        "ppt_helper": "ppt_helper", "contacts": "contacts",
        "vscode_link": "vscode_link",
        "open_incognito": "open_incognito",
    }
    feature = aliases.get(name)
    if not feature:
        return None

    if feature == "system_info": return await windows_system_status()
    if feature == "power_manager": return await power_manager()
    if feature in ("get_time", "get_date"): return await get_time_and_date()
    if feature == "volume_control": return await open_settings_page("ms-settings:sound", "Sound settings")
    if feature == "set_volume":
        return await set_volume(int(target.strip())) if target.strip().isdigit() else await open_settings_page("ms-settings:sound", "Sound settings")
    # direct up/down with optional numeric target (percent)
    if feature == "volume_up":
        return await (volume_up_by(int(target.strip())) if target.strip().lstrip("+-%").isdigit() else volume_up())
    if feature == "volume_down":
        return await (volume_down_by(int(target.strip())) if target.strip().lstrip("+-%").isdigit() else volume_down())
    if feature == "volume_up_by":
        return await volume_up_by(int(target.strip()))
    if feature == "volume_down_by":
        return await volume_down_by(int(target.strip()))
    if feature == "change_volume":
        # Accept formats like "-30", "30%", "decrease 30" — try to extract number with sign
        t = target.strip().replace("%", "")
        try:
            val = int(t)
            return await change_volume_by(val)
        except Exception:
            return {"success": False, "confirmation": "I couldn't parse that volume change, sir."}
    if feature == "brightness_control":
        return await set_brightness(int(target.strip())) if target.strip().isdigit() else await open_settings_page("ms-settings:display", "Display settings")
    if feature == "app_launcher": return await open_app(target or "start")
    if feature == "file_opener": return await open_path(target) if target.strip() else await open_file_explorer()
    if feature == "battery_saver": return await set_power_saver(True)
    if feature == "pc_temp_check": return await pc_temperature()
    if feature == "disk_cleaner": return await disk_cleaner()
    if feature == "empty_trash": return await empty_trash()
    if feature == "clear_temp": return await clear_temp_files()
    if feature == "flush_dns": return await flush_dns()
    if feature == "wifi_manager": return await open_wifi_settings()
    if feature == "network_speed": return await network_speed()
    if feature == "check_internet": return await check_internet_connection()
    if feature in ("get_ip", "get_local_ip"): return await get_ip_address()
    if feature == "get_public_ip": return await get_public_ip()
    if feature == "wifi_settings": return await open_wifi_settings()
    if feature == "ethernet_settings": return await open_ethernet_settings()
    if feature == "vpn_settings": return await open_vpn_settings()
    if feature == "proxy_settings": return await open_proxy_settings()
    if feature == "network_sharing": return await open_network_sharing_center()
    if feature == "firewall_settings": return await open_firewall_settings()
    if feature == "lock_screen": return await lock_pc()
    if feature == "screenshot": return await save_screenshot()
    if feature == "screen_record": return await screen_record()
    if feature == "mic_control": return await open_microphone_settings()
    if feature == "webcam_control": return await open_camera_settings()
    if feature == "mouse_speed": return await open_mouse_settings()
    if feature == "keyboard_lights": return await open_keyboard_settings()
    if feature == "time_sync": return await open_time_settings()
    if feature == "notifications": return await open_notification_settings()
    if feature in ("night_mode", "eye_care", "night_light"): return await open_night_light()
    if feature == "bluetooth_connect": return await open_bluetooth_settings()
    if feature == "printer_setup": return await open_printer_settings()
    if feature == "phone_link": return await open_app("phone link")
    if feature == "game_mode": return await open_gaming_settings()
    if feature == "task_manager": return await open_task_manager()
    if feature == "auto_update": return await open_windows_update()
    if feature == "display_settings": return await open_display_settings()
    if feature == "sound_settings": return await open_sound_settings()
    if feature == "power_options": return await open_power_options()
    if feature == "storage_settings": return await open_storage_settings()
    if feature == "default_apps": return await open_default_apps()
    if feature == "optional_features": return await open_optional_features()
    if feature == "about_settings": return await open_about_settings()
    if feature == "privacy_settings": return await open_privacy_settings()
    if feature == "accessibility": return await open_accessibility_settings()
    if feature == "language_settings": return await open_language_settings()
    if feature == "time_settings": return await open_time_settings()
    if feature == "accounts_settings": return await open_accounts_settings()
    if feature == "gaming_settings": return await open_gaming_settings()
    if feature == "bluetooth_settings": return await open_bluetooth_settings()
    if feature == "mouse_settings": return await open_mouse_settings()
    if feature == "keyboard_settings": return await open_keyboard_settings()
    if feature == "notification_settings": return await open_notification_settings()
    if feature == "printer_settings": return await open_printer_settings()
    if feature == "camera_settings": return await open_camera_settings()
    if feature == "microphone_settings": return await open_microphone_settings()
    if feature == "remote_desktop": return await open_remote_desktop()
    if feature == "control_panel": return await open_control_panel()
    if feature == "device_manager": return await open_device_manager()
    if feature == "event_viewer": return await open_event_viewer()
    if feature == "services": return await open_services()
    if feature == "resource_monitor": return await open_resource_monitor()
    if feature == "task_scheduler": return await open_task_scheduler()
    if feature == "computer_management": return await open_computer_management()
    if feature == "credential_manager": return await open_credential_manager()
    if feature == "disk_management": return await open_disk_management()
    if feature == "registry_editor": return await open_registry_editor()
    if feature == "system_properties": return await open_system_properties()
    if feature == "environment_variables": return await open_environment_variables()
    if feature == "windows_security": return await open_windows_security()
    if feature == "startup_apps": return await open_startup_apps()
    if feature == "group_policy": return await open_group_policy()
    if feature == "performance_monitor": return await open_performance_monitor()
    if feature == "magnifier": return await open_magnifier()
    if feature == "on_screen_keyboard": return await open_on_screen_keyboard()
    if feature == "narrator": return await open_narrator()
    if feature == "sticky_notes": return await open_sticky_notes()
    if feature == "onenote": return await open_onenote()
    if feature == "outlook": return await open_outlook()
    if feature == "teams": return await open_teams()
    if feature == "windows_update": return await open_windows_update()
    if feature == "windows_store": return await open_windows_store()
    if feature == "maps_app": return await open_maps()
    if feature == "weather_app": return await open_weather_app()
    if feature == "news_app": return await open_news_app()
    if feature == "clock_app": return await open_clock_app()
    if feature == "photos_app": return await open_photos_app()
    if feature == "calculator_app": return await open_calculator_app()
    if feature == "window_move":
        return await snap_window_right() if "right" in target.lower() else await snap_window_left()
    if feature == "auto_scroll":
        return {"success": False, "confirmation": "Auto scroll needs the target app focused and a scroll direction, sir."}
    if feature == "remote_control": return await open_remote_desktop()
    if feature == "clipboard_history":
        success = await _press_vk_combo([0x5B, 0x56])
        return {"success": success, "confirmation": "Clipboard history opened, sir." if success else "I couldn't open clipboard history, sir."}
    if feature == "pin_to_top": return await _not_configured("Pin to top", "Microsoft PowerToys")
    if feature == "quick_search":
        if target.strip(): return await open_google_search(target)
        success = await _press_vk_combo([0x5B, 0x53])
        return {"success": success, "confirmation": "Windows Search is open, sir." if success else "I couldn't open Windows Search, sir."}
    if feature == "folder_maker": return await make_folder(target)
    if feature == "change_wallpaper": return await change_wallpaper(target)
    if feature == "clean_desktop": return await clean_desktop()
    if feature == "screen_ruler": return await _not_configured("Screen ruler", "Microsoft PowerToys Screen Ruler")
    if feature == "color_picker": return await _not_configured("Color picker", "Microsoft PowerToys Color Picker")
    if feature == "snipping_tool": return await open_snipping_tool()
    if feature == "snap_windows":
        return await snap_window_right() if "right" in target.lower() else await snap_window_left()
    if feature == "multi_monitor": return await open_display_settings()
    if feature == "refresh_desktop":
        success = await _send_windows_keys("{F5}")
        return {"success": success, "confirmation": "Desktop refreshed, sir." if success else "I couldn't refresh the desktop, sir."}
    if feature == "delete_file": return await delete_file(target)
    if feature == "copy_path": return await copy_path_to_clipboard(target)
    if feature == "zip_files": return await zip_files(target)
    if feature == "unzip_files": return await unzip_files(target)
    if feature == "hide_files": return await hide_file(target, True)
    if feature == "show_hidden": return await show_hidden_files(True)
    if feature == "rename_files": return await rename_file(target)
    if feature == "make_shortcut": return await make_shortcut(target)
    if feature == "shred_file": return await shred_file(target)
    if feature == "folder_size": return await folder_size(target)
    if feature == "sync_folders": return await _not_configured("Folder sync", "two folder paths and a sync policy")
    if feature == "cloud_backup": return await open_settings_page("ms-settings:backup", "Windows Backup")
    if feature == "move_file":
        if "|||" in target:
            src, _, dst = target.partition("|||")
            return await move_file(src.strip(), dst.strip())
        return {"success": False, "confirmation": "Provide source and destination separated by |||, sir."}
    if feature == "copy_file":
        if "|||" in target:
            src, _, dst = target.partition("|||")
            return await copy_file(src.strip(), dst.strip())
        return {"success": False, "confirmation": "Provide source and destination separated by |||, sir."}
    if feature == "get_file_info": return await get_file_info(target)
    if feature == "list_directory": return await list_directory(target)
    if feature == "create_file":
        if "|||" in target:
            p, _, c = target.partition("|||")
            return await create_text_file(p.strip(), c.strip())
        return await create_text_file(target)
    if feature == "search_files": return await search_files_by_name(target)
    if feature == "open_incognito": return await open_incognito(target)
    if feature == "downloads_folder": return await open_downloads()
    if feature == "go_home": return await go_home()
    if feature == "documents_folder": return await open_documents()
    if feature == "pictures_folder": return await open_pictures()
    if feature == "music_folder": return await open_music()
    if feature == "videos_folder": return await open_videos()
    if feature == "desktop_folder": return await open_desktop_folder()
    if feature == "temp_folder": return await open_temp_folder()
    if feature == "appdata_folder": return await open_appdata_folder()
    if feature == "program_files": return await open_program_files()
    if feature == "recycle_bin": return await open_recycle_bin()
    if feature == "this_pc": return await open_this_pc()
    if feature == "onedrive_folder": return await open_onedrive_folder()
    if feature == "startup_folder": return await open_startup_folder()
    if feature in ("set_alarm", "stopwatch", "timer"): return await open_app("ms-clock:")
    if feature == "pdf_reader":
        return await open_path(target) if target.strip() else await _not_configured("PDF reader", "a PDF file path")
    if feature == "excel_helper": return await open_app("excel")
    if feature == "word_helper": return await open_app("word")
    if feature == "ppt_helper": return await open_app("powerpoint")
    if feature == "contacts": return await open_app("outlook")
    if feature == "vscode_link": return await open_app("vs code")
    if feature == "log_out": return await log_out()

    return None


# ---------------------------------------------------------------------------
# execute_action — main entry point called by server.py
# ---------------------------------------------------------------------------

async def execute_action(
    intent: dict[str, Any],
    projects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    action = intent.get("action", "chat")
    target = intent.get("target", "")

    feature_result = await handle_feature_action(action, target)
    if feature_result is not None:
        feature_result.setdefault("project_dir", None)
        return feature_result

    if action == "open_terminal":
        claude_cmd = "claude --dangerously-skip-permissions" if _SKIP_PERMISSIONS else "claude"
        result = await open_terminal(claude_cmd)
        result["project_dir"] = None
        return result

    if action == "browse":
        if "youtube" in target.lower():
            q = re.sub(r"\b(on\s+)?youtube\b", "", target, flags=re.I).strip()
            result = await open_youtube_search(q)
            result["project_dir"] = None
            return result
        if target.startswith(("http://", "https://")):
            url = target
        else:
            url = f"https://www.google.com/search?q={quote_plus(target)}"
        browser = "firefox" if "firefox" in target.lower() else "chrome"
        result = await open_browser(url, browser)
        result["project_dir"] = None
        return result

    if action == "build":
        project_name = _generate_project_name(target)
        project_dir = str(DESKTOP_PATH / project_name)
        os.makedirs(project_dir, exist_ok=True)
        result = await open_claude_in_project(project_dir, target)
        result["project_dir"] = project_dir
        return result

    if action in ("youtube_search", "search_youtube"):
        result = await open_youtube_search(target)
        result["project_dir"] = None
        return result

    if action in ("split_tasks", "divide_tasks"):
        tasks = split_into_tasks(target)
        confirmation = (
            f"Divided into {len(tasks)} task(s): {', '.join(tasks[:8])}."
            if tasks else "I couldn't find tasks to divide, sir."
        )
        return {"success": bool(tasks), "confirmation": confirmation, "tasks": tasks, "project_dir": None}

    if action == "get_time":
        result = await get_time_and_date()
        result["project_dir"] = None
        return result

    if action == "get_ip":
        result = await get_ip_address()
        result["project_dir"] = None
        return result

    if action == "get_public_ip":
        result = await get_public_ip()
        result["project_dir"] = None
        return result

    if action == "check_internet":
        result = await check_internet_connection()
        result["project_dir"] = None
        return result

    if action == "open_incognito":
        result = await open_incognito(target)
        result["project_dir"] = None
        return result

    if action == "flush_dns":
        result = await flush_dns()
        result["project_dir"] = None
        return result

    if action == "clear_temp":
        result = await clear_temp_files()
        result["project_dir"] = None
        return result

    return {"success": False, "confirmation": "", "project_dir": None}


def _generate_project_name(prompt: str) -> str:
    quoted = re.search(r'"([^"]+)"', prompt)
    if quoted:
        name = re.sub(r"[^a-zA-Z0-9\s-]", "", quoted.group(1)).strip()
        if name:
            return re.sub(r"[\s]+", "-", name.lower())

    called = re.search(r"(?:called|named)\s+(\S+(?:[-_]\S+)*)", prompt, re.IGNORECASE)
    if called:
        name = re.sub(r"[^a-zA-Z0-9-]", "", called.group(1))
        if len(name) > 3:
            return name.lower()

    words = re.sub(r"[^a-zA-Z0-9\s]", "", prompt.lower()).split()
    skip = {
        "a", "the", "an", "me", "build", "create", "make", "for", "with", "and",
        "to", "of", "i", "want", "need", "new", "project", "directory", "called",
        "on", "desktop", "that", "application", "app", "full", "stack", "simple",
        "web", "page", "site", "named",
    }
    meaningful = [w for w in words if w not in skip and len(w) > 2][:4]
    return "-".join(meaningful) if meaningful else "jarvis-project"

# ---------------------------------------------------------------------------
# WhatsApp Automation
# ---------------------------------------------------------------------------

async def _whatsapp_set_clipboard(text: str) -> None:
    """Copy text to clipboard via PowerShell (handles all characters)."""
    escaped = text.replace("'", "''")
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-Command",
        f"Set-Clipboard -Value '{escaped}'",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    await asyncio.sleep(0.15)


async def whatsapp_open() -> dict:
    """Open WhatsApp Desktop."""
    return await open_app("whatsapp")


async def whatsapp_open_chat(contact_name: str) -> dict:
    """Open WhatsApp Desktop and navigate to a specific contact's chat.

    Strategy:
      1. Launch WhatsApp (or bring it to front).
      2. Press Ctrl+F to open the search bar.
      3. Paste the contact name via clipboard.
      4. Wait for results, then press Down + Enter to open the first match.
    """
    if not contact_name.strip():
        return {"success": False, "confirmation": "Please tell me the contact name, sir."}

    try:
        # Open / focus WhatsApp
        await open_app("whatsapp")
        await asyncio.sleep(2.5)

        # Open search bar (Ctrl+F)
        await _press_vk_combo([0x11, 0x46])  # Ctrl+F
        await asyncio.sleep(0.6)

        # Select-all then paste contact name from clipboard
        await _press_vk_combo([0x11, 0x41])  # Ctrl+A
        await asyncio.sleep(0.1)
        await _whatsapp_set_clipboard(contact_name.strip())
        await _press_vk_combo([0x11, 0x56])  # Ctrl+V
        await asyncio.sleep(1.2)  # Wait for search results

        # Navigate to first result and open it
        await _press_vk_combo([0x28])  # Down arrow
        await asyncio.sleep(0.3)
        await _press_vk_combo([0x0D])  # Enter
        await asyncio.sleep(0.5)

        return {"success": True, "confirmation": f"Opened WhatsApp chat with {contact_name}, sir."}
    except Exception as e:
        log.error(f"whatsapp_open_chat failed: {e}")
        return {"success": False, "confirmation": f"I couldn't open the WhatsApp chat with {contact_name}, sir."}


async def whatsapp_send_message(contact_name: str, message: str) -> dict:
    """Send a WhatsApp message to a contact by name.

    Opens WhatsApp, searches for the contact, then types and sends the message.
    Uses clipboard paste so any Unicode / special characters are preserved.
    """
    if not contact_name.strip():
        return {"success": False, "confirmation": "Please tell me who to message, sir."}
    if not message.strip():
        return {"success": False, "confirmation": "Please tell me what message to send, sir."}

    try:
        # Open the chat
        result = await whatsapp_open_chat(contact_name)
        if not result["success"]:
            return result

        await asyncio.sleep(0.4)

        # Dismiss any open menus / tooltips
        await _press_vk_combo([0x1B])  # Escape
        await asyncio.sleep(0.2)

        # Paste message from clipboard into the message input box
        await _whatsapp_set_clipboard(message.strip())
        await _press_vk_combo([0x11, 0x56])  # Ctrl+V
        await asyncio.sleep(0.3)

        # Send with Enter
        await _press_vk_combo([0x0D])  # Enter
        await asyncio.sleep(0.3)

        return {"success": True, "confirmation": f"Message sent to {contact_name} on WhatsApp, sir."}
    except Exception as e:
        log.error(f"whatsapp_send_message failed: {e}")
        return {"success": False, "confirmation": f"I couldn't send the WhatsApp message to {contact_name}, sir."}


async def whatsapp_send_file(contact_name: str, file_path: str) -> dict:
    """Attach and send a file to a WhatsApp contact.

    Opens the chat, triggers the file-attachment dialog (Ctrl+O in WhatsApp
    Desktop), pastes the full file path, confirms, then sends.
    """
    if not contact_name.strip():
        return {"success": False, "confirmation": "Please tell me who to send the file to, sir."}

    p = Path(file_path.strip()).expanduser()
    if not p.exists():
        return {"success": False, "confirmation": f"File not found: {p}, sir."}

    try:
        # Open the chat
        result = await whatsapp_open_chat(contact_name)
        if not result["success"]:
            return result

        await asyncio.sleep(0.4)

        # Open file-attachment dialog — WhatsApp Desktop shortcut
        await _press_vk_combo([0x11, 0x4F])  # Ctrl+O
        await asyncio.sleep(1.5)  # Wait for the Open dialog

        # Paste the full file path into the dialog's filename field
        await _whatsapp_set_clipboard(str(p))
        await _press_vk_combo([0x11, 0x56])  # Ctrl+V
        await asyncio.sleep(0.3)

        # Confirm file selection
        await _press_vk_combo([0x0D])  # Enter
        await asyncio.sleep(1.5)  # Wait for preview / attachment to load

        # Send the attachment
        await _press_vk_combo([0x0D])  # Enter
        await asyncio.sleep(0.4)

        return {"success": True, "confirmation": f"File '{p.name}' sent to {contact_name} on WhatsApp, sir."}
    except Exception as e:
        log.error(f"whatsapp_send_file failed: {e}")
        return {"success": False, "confirmation": f"I couldn't send the file to {contact_name} on WhatsApp, sir."}


async def whatsapp_get_unread() -> dict:
    """Open WhatsApp Desktop so the user can see unread messages.

    Full unread-count scraping requires accessibility APIs; this opens the app
    and reports that it is ready for the user to check.
    """
    result = await open_app("whatsapp")
    if result["success"]:
        return {"success": True, "confirmation": "WhatsApp is open, sir. Check the left panel for unread messages."}
    return result

# ---------------------------------------------------------------------------
# GUI Automation — Mouse, Keyboard, Screen
# ---------------------------------------------------------------------------
# Uses only ctypes (already imported) + the existing PowerShell helpers.
# No extra pip packages required.

# Mouse-event flags (Win32)
_ME_LEFTDOWN   = 0x0002
_ME_LEFTUP     = 0x0004
_ME_RIGHTDOWN  = 0x0008
_ME_RIGHTUP    = 0x0010
_ME_MIDDLEDOWN = 0x0020
_ME_MIDDLEUP   = 0x0040
_ME_WHEEL      = 0x0800


def _mouse_event_sync(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
    ctypes.windll.user32.mouse_event(flags, dx, dy, data, 0)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


# ── Screen info ──────────────────────────────────────────────────────────────

async def get_screen_size() -> dict:
    """Return the primary monitor resolution."""
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
        return {
            "success": True,
            "confirmation": f"Screen resolution is {w} × {h} pixels, sir.",
            "width": w, "height": h,
        }
    except Exception as e:
        log.error(f"get_screen_size failed: {e}")
        return {"success": False, "confirmation": "I couldn't read the screen size, sir."}


async def get_cursor_position() -> dict:
    """Return the current mouse cursor coordinates."""
    try:
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return {
            "success": True,
            "confirmation": f"Cursor is at {pt.x}, {pt.y}, sir.",
            "x": pt.x, "y": pt.y,
        }
    except Exception as e:
        log.error(f"get_cursor_position failed: {e}")
        return {"success": False, "confirmation": "I couldn't read the cursor position, sir."}


# ── Mouse movement ────────────────────────────────────────────────────────────

async def mouse_move(x: int, y: int) -> dict:
    """Move the mouse cursor to absolute screen coordinates."""
    try:
        await asyncio.to_thread(ctypes.windll.user32.SetCursorPos, x, y)
        return {"success": True, "confirmation": f"Mouse moved to {x}, {y}, sir."}
    except Exception as e:
        log.error(f"mouse_move failed: {e}")
        return {"success": False, "confirmation": "I couldn't move the mouse, sir."}


# ── Mouse clicks ──────────────────────────────────────────────────────────────

async def mouse_click(x: int, y: int, button: str = "left") -> dict:
    """Single click at absolute screen coordinates."""
    try:
        await asyncio.to_thread(ctypes.windll.user32.SetCursorPos, x, y)
        await asyncio.sleep(0.05)
        if button == "right":
            flags = _ME_RIGHTDOWN | _ME_RIGHTUP
        elif button == "middle":
            flags = _ME_MIDDLEDOWN | _ME_MIDDLEUP
        else:
            flags = _ME_LEFTDOWN | _ME_LEFTUP
        await asyncio.to_thread(_mouse_event_sync, flags)
        return {"success": True, "confirmation": f"{button.capitalize()} click at {x}, {y}, sir."}
    except Exception as e:
        log.error(f"mouse_click failed: {e}")
        return {"success": False, "confirmation": "I couldn't click, sir."}


async def mouse_right_click(x: int, y: int) -> dict:
    """Right-click at absolute screen coordinates."""
    return await mouse_click(x, y, "right")


async def mouse_double_click(x: int, y: int) -> dict:
    """Double-click at absolute screen coordinates."""
    try:
        await asyncio.to_thread(ctypes.windll.user32.SetCursorPos, x, y)
        await asyncio.sleep(0.05)
        for _ in range(2):
            await asyncio.to_thread(_mouse_event_sync, _ME_LEFTDOWN | _ME_LEFTUP)
            await asyncio.sleep(0.06)
        return {"success": True, "confirmation": f"Double-clicked at {x}, {y}, sir."}
    except Exception as e:
        log.error(f"mouse_double_click failed: {e}")
        return {"success": False, "confirmation": "I couldn't double-click, sir."}


async def mouse_drag(x1: int, y1: int, x2: int, y2: int) -> dict:
    """Click-drag from (x1, y1) to (x2, y2)."""
    try:
        await asyncio.to_thread(ctypes.windll.user32.SetCursorPos, x1, y1)
        await asyncio.sleep(0.05)
        await asyncio.to_thread(_mouse_event_sync, _ME_LEFTDOWN)
        await asyncio.sleep(0.05)
        steps = 12
        for i in range(1, steps + 1):
            ix = x1 + int((x2 - x1) * i / steps)
            iy = y1 + int((y2 - y1) * i / steps)
            await asyncio.to_thread(ctypes.windll.user32.SetCursorPos, ix, iy)
            await asyncio.sleep(0.02)
        await asyncio.to_thread(_mouse_event_sync, _ME_LEFTUP)
        return {"success": True, "confirmation": f"Dragged from {x1},{y1} to {x2},{y2}, sir."}
    except Exception as e:
        log.error(f"mouse_drag failed: {e}")
        return {"success": False, "confirmation": "I couldn't perform the drag, sir."}


# ── Mouse scroll ──────────────────────────────────────────────────────────────

async def mouse_scroll(direction: str = "down", amount: int = 3) -> dict:
    """Scroll the mouse wheel up or down."""
    try:
        delta = -120 * amount if direction.lower() in ("down", "d") else 120 * amount
        await asyncio.to_thread(_mouse_event_sync, _ME_WHEEL, 0, 0, delta)
        return {"success": True, "confirmation": f"Scrolled {direction} {amount} notch{'es' if amount != 1 else ''}, sir."}
    except Exception as e:
        log.error(f"mouse_scroll failed: {e}")
        return {"success": False, "confirmation": "I couldn't scroll, sir."}


# ── Keyboard typing ───────────────────────────────────────────────────────────

async def keyboard_type(text: str) -> dict:
    """Type arbitrary text at the current cursor position via clipboard paste.

    Using clipboard ensures Unicode, Hinglish, and special characters work.
    """
    if not text:
        return {"success": False, "confirmation": "No text to type, sir."}
    try:
        await _whatsapp_set_clipboard(text)   # reuse the clipboard helper
        await _press_vk_combo([0x11, 0x56])   # Ctrl+V
        return {"success": True, "confirmation": "Text typed, sir."}
    except Exception as e:
        log.error(f"keyboard_type failed: {e}")
        return {"success": False, "confirmation": "I couldn't type the text, sir."}


# ── Key press ─────────────────────────────────────────────────────────────────

_KEY_SENDKEYS_MAP: dict[str, str] = {
    "enter": "{ENTER}", "return": "{ENTER}",
    "escape": "{ESC}", "esc": "{ESC}",
    "tab": "{TAB}",
    "backspace": "{BACKSPACE}", "back": "{BACKSPACE}",
    "delete": "{DELETE}", "del": "{DELETE}",
    "space": " ",
    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
    "home": "{HOME}", "end": "{END}",
    "page up": "{PGUP}", "pageup": "{PGUP}",
    "page down": "{PGDN}", "pagedown": "{PGDN}",
    "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}",
    "f5": "{F5}", "f6": "{F6}", "f7": "{F7}", "f8": "{F8}",
    "f9": "{F9}", "f10": "{F10}", "f11": "{F11}", "f12": "{F12}",
    "print screen": "{PRTSC}", "printscreen": "{PRTSC}",
    "insert": "{INSERT}", "ins": "{INSERT}",
    "caps lock": "{CAPSLOCK}", "capslock": "{CAPSLOCK}",
    "num lock": "{NUMLOCK}", "numlock": "{NUMLOCK}",
    "scroll lock": "{SCROLLLOCK}",
}


async def keyboard_press(key: str) -> dict:
    """Press a named key (enter, escape, tab, f5, arrow keys, etc.)."""
    k = key.lower().strip()
    send_key = _KEY_SENDKEYS_MAP.get(k, key)
    try:
        success = await _send_windows_keys(send_key)
        return {
            "success": success,
            "confirmation": f"Pressed {key}, sir." if success else f"I couldn't press {key}, sir.",
        }
    except Exception as e:
        log.error(f"keyboard_press failed: {e}")
        return {"success": False, "confirmation": f"I couldn't press {key}, sir."}


# ── Keyboard hotkeys ──────────────────────────────────────────────────────────

_VK_MAP: dict[str, int] = {
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B, "windows": 0x5B, "super": 0x5B,
    **{chr(c): 0x41 + (c - ord("a")) for c in range(ord("a"), ord("z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "enter": 0x0D, "return": 0x0D,
    "escape": 0x1B, "esc": 0x1B,
    "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "printscreen": 0x2C,
}


async def keyboard_hotkey(keys: str) -> dict:
    """Press a keyboard shortcut such as 'ctrl+c', 'alt+f4', 'win+d'.

    Accepts '+' or space as separator between key names.
    """
    parts = [k.strip().lower() for k in re.split(r"[+\s]+", keys) if k.strip()]
    vk_codes = [_VK_MAP[p] for p in parts if p in _VK_MAP]
    if not vk_codes:
        return {"success": False, "confirmation": f"I don't recognise the key combination '{keys}', sir."}
    try:
        success = await _press_vk_combo(vk_codes)
        return {
            "success": success,
            "confirmation": f"Pressed {keys}, sir." if success else f"I couldn't press {keys}, sir.",
        }
    except Exception as e:
        log.error(f"keyboard_hotkey failed: {e}")
        return {"success": False, "confirmation": f"I couldn't press {keys}, sir."}


# ── Convenience wrappers ──────────────────────────────────────────────────────

async def gui_select_all() -> dict:
    """Select all text / items in the focused window (Ctrl+A)."""
    return await keyboard_hotkey("ctrl+a")


async def gui_copy() -> dict:
    """Copy selection to clipboard (Ctrl+C)."""
    return await keyboard_hotkey("ctrl+c")


async def gui_paste() -> dict:
    """Paste from clipboard (Ctrl+V)."""
    return await keyboard_hotkey("ctrl+v")


async def gui_undo() -> dict:
    """Undo last action (Ctrl+Z)."""
    return await keyboard_hotkey("ctrl+z")


async def gui_redo() -> dict:
    """Redo last undone action (Ctrl+Y)."""
    return await keyboard_hotkey("ctrl+y")


async def gui_save() -> dict:
    """Save the current document (Ctrl+S)."""
    return await keyboard_hotkey("ctrl+s")


async def gui_close_window() -> dict:
    """Close the active window (Alt+F4)."""
    return await keyboard_hotkey("alt+f4")


async def gui_refresh() -> dict:
    """Refresh the active window (F5)."""
    return await keyboard_press("f5")


async def gui_fullscreen() -> dict:
    """Toggle fullscreen (F11)."""
    return await keyboard_press("f11")


async def gui_zoom_in() -> dict:
    """Zoom in (Ctrl++)."""
    return await keyboard_hotkey("ctrl+=")


async def gui_zoom_out() -> dict:
    """Zoom out (Ctrl+-)."""
    return await keyboard_hotkey("ctrl+-")


async def gui_new_tab() -> dict:
    """Open a new tab (Ctrl+T)."""
    return await keyboard_hotkey("ctrl+t")


async def gui_close_tab() -> dict:
    """Close the current tab (Ctrl+W)."""
    return await keyboard_hotkey("ctrl+w")


async def gui_reopen_tab() -> dict:
    """Reopen the last closed tab (Ctrl+Shift+T)."""
    return await keyboard_hotkey("ctrl+shift+t")


async def gui_find() -> dict:
    """Open find dialog (Ctrl+F)."""
    return await keyboard_hotkey("ctrl+f")


async def gui_address_bar() -> dict:
    """Focus the browser address bar (Ctrl+L)."""
    return await keyboard_hotkey("ctrl+l")
