"""JARVIS Windows screen awareness."""

import asyncio
import base64
import ctypes
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("jarvis.screen")


def _decode_process_output(data: bytes) -> str:
    return data.decode(errors="replace").strip()


def _get_process_name(pid: int) -> str:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=2,
        )
        output = _decode_process_output(result.stdout)
        if result.returncode == 0 and output and "INFO:" not in output.upper():
            return output.split('","')[0].strip('"')
    except Exception:
        pass
    return f"pid:{pid}"


def _get_active_windows_sync() -> list[dict]:
    user32 = ctypes.windll.user32
    windows: list[dict] = []
    foreground = user32.GetForegroundWindow()
    process_cache: dict[int, str] = {}
    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title_len = user32.GetWindowTextLengthW(hwnd)
        if title_len <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(title_len + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_len + 1)
        title = title_buffer.value.strip()
        if not title:
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = int(pid.value)
        if pid_value not in process_cache:
            process_cache[pid_value] = _get_process_name(pid_value)
        windows.append({
            "app": process_cache[pid_value],
            "title": title,
            "frontmost": hwnd == foreground,
        })
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return windows


async def get_active_windows() -> list[dict]:
    return await asyncio.to_thread(_get_active_windows_sync)


async def get_running_apps() -> list[str]:
    windows = await get_active_windows()
    return sorted({w["app"] for w in windows if w.get("app")})


async def take_screenshot(display_only: bool = True) -> str | None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    ps_path = tmp_path.replace("'", "''")
    ps_display_only = "$true" if display_only else "$false"
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = if ({ps_display_only}) {{
    [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
}} else {{
    [System.Windows.Forms.SystemInformation]::VirtualScreen
}}
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
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        path = Path(tmp_path)
        if proc.returncode != 0 or not path.exists():
            log.warning(f"Windows screenshot failed: {_decode_process_output(stderr)[:200]}")
            return None
        return base64.b64encode(path.read_bytes()).decode()
    except Exception as e:
        log.warning(f"Windows screenshot error: {e}")
        return None
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


async def collect_screen_state(include_screenshot: bool = False) -> dict:
    windows, apps = await asyncio.gather(
        get_active_windows(),
        get_running_apps(),
        return_exceptions=False,
    )
    state = {
        "platform": "Windows",
        "windows": windows,
        "apps": apps,
        "active_window": next((w for w in windows if w.get("frontmost")), None),
        "can_capture_screenshot": True,
    }
    if include_screenshot:
        screenshot = await take_screenshot()
        state["screenshot_b64"] = screenshot
        state["can_capture_screenshot"] = bool(screenshot)
    return state


def screen_capabilities() -> list[str]:
    return [
        "list open windows",
        "identify the active window",
        "list visible apps",
        "capture screenshots for vision analysis",
        "summarize windows when vision is unavailable",
    ]


async def describe_screen(anthropic_client) -> str:
    screenshot_b64 = await take_screenshot()
    if screenshot_b64 and anthropic_client:
        try:
            response = await anthropic_client.chat.completions.create(
                model="phi3:mini",
                max_tokens=120,
                messages=[{
                    "role": "user",
                    "content": "Describe this Windows desktop in 2-4 concise sentences. No markdown.",
                }],
            )
            return response.choices[0].message.content
        except Exception as e:
            log.warning(f"Vision call failed, falling back to window list: {e}")

    windows = await get_active_windows()
    if not windows:
        return "I wasn't able to read your windows or capture the screen, sir."
    active = next((w for w in windows if w.get("frontmost")), None)
    result = f"You have {len(windows)} windows open across {len(set(w['app'] for w in windows))} apps."
    if active:
        result += f" Currently focused on {active['app']}: {active['title']}."
    return result


def format_windows_for_context(windows: list[dict]) -> str:
    if not windows:
        return ""
    lines = ["Currently open on your Windows desktop:"]
    for w in windows:
        marker = " (active)" if w.get("frontmost") else ""
        lines.append(f"  - {w['app']}: {w['title']}{marker}")
    return "\n".join(lines)
