"""
JARVIS Windows Security Suite
==============================
All-in-one laptop security monitor for Windows.
Features:
  1. Process & memory monitor (suspicious process detection)
  2. Network connection monitor (unknown outbound, C2 beaconing)
  3. File integrity watcher (critical paths, hash baseline)
  4. Login & auth event monitor (failed logins, RDP, sudo)
  5. USB & peripheral guard (whitelist, auto-alert)
  6. Startup / persistence monitor (registry, Task Scheduler, startup folder)
  7. Clipboard sensitive data detector (API keys, passwords, credit cards)
  8. Daily security health briefing (morning spoken report)
  9. VirusTotal file & IOC scanner
 10. Windows Firewall & Defender status checker

Requirements (install once):
    pip install psutil watchdog pyperclip requests colorama plyer pywin32 wmi

Usage:
    python jarvis_security.py

On first run it will:
  - Ask for your VirusTotal API key (free at virustotal.com) — press Enter to skip
  - Create a file baseline of critical Windows paths
  - Start all monitors and open the dashboard in your terminal

Press Ctrl+C to stop. Logs saved to jarvis_security.log
"""

import os
import sys
import time
import json
import hashlib
import sqlite3
import logging
import threading
import subprocess
import re
import shutil
import datetime
import platform
import socket
import struct
import ctypes
import argparse
import ipaddress
from pathlib import Path
from collections import defaultdict, deque

# ── third-party (pip install psutil watchdog pyperclip requests colorama plyer) ──
try:
    import psutil
except ImportError:
    print("[!] Missing: pip install psutil"); sys.exit(1)

try:
    import requests
except ImportError:
    requests = None
    print("[~] requests not found — VirusTotal scanning disabled. pip install requests to enable.")

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    print("[~] watchdog not found — file watcher disabled. pip install watchdog to enable.")

try:
    from colorama import init as colorama_init, Fore as ColoramaFore, Style as ColoramaStyle
    colorama_init(autoreset=True)
    Fore: type = ColoramaFore  # type: ignore
    Style: type = ColoramaStyle  # type: ignore
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

plyer_notify = None
try:
    from plyer import notification as plyer_notify
    PLYER_OK = True
except ImportError:
    PLYER_OK = False

# ─────────────────────────────────────────────
#  CONFIGURATION  (edit these to suit your setup)
# ─────────────────────────────────────────────

CONFIG = {
    # Your VirusTotal free API key (https://virustotal.com)
    "VT_API_KEY": "",

    # Processes whose names are always considered safe (lowercase)
    "PROCESS_WHITELIST": {
        "system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
        "services.exe", "lsass.exe", "svchost.exe", "explorer.exe",
        "taskmgr.exe", "conhost.exe", "dwm.exe", "sihost.exe",
        "python.exe", "pythonw.exe", "code.exe", "chrome.exe",
        "msedge.exe", "firefox.exe", "notepad.exe", "cmd.exe",
        "powershell.exe", "wsl.exe", "wslhost.exe",
    },

    # Known suspicious process name fragments (lowercase)
    "SUSPICIOUS_NAMES": [
        "mimikatz", "meterpreter", "netcat", "nc.exe", "ncat",
        "psexec", "wce.exe", "fgdump", "pwdump", "lazagne",
        "cobaltstrike", "beacon", "empire", "metasploit",
        "xmrig", "minerd", "cpuminer",   # cryptominers
    ],

    # Ports that are almost never legitimate for outbound connections
    "SUSPICIOUS_PORTS": {4444, 5555, 6666, 7777, 8888, 9999, 31337, 1337},

    # USB vendor IDs to whitelist (find yours with: wmic path Win32_USBControllerDevice)
    # Leave empty to alert on ALL new USB devices
    "USB_WHITELIST_VENDORS": set(),

    # Critical file/folder paths to watch for changes
    "WATCH_PATHS": [
        os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"),
        os.path.expandvars(r"%USERPROFILE%\.ssh"),
    ],

    # Registry run keys to monitor for new persistence entries
    "REGISTRY_RUN_KEYS": [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
    ],

    # Sensitive patterns to detect in clipboard content
    "SENSITIVE_PATTERNS": {
        "AWS key":        r"AKIA[0-9A-Z]{16}",
        "Private key":    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "Generic API key":r"(?i)(api[_-]?key|apikey|secret)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}",
        "Credit card":    r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",
        "Password field": r"(?i)password\s*[:=]\s*\S+",
        "JWT token":      r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    },

    # CPU/RAM thresholds for spike alerts
    "CPU_SPIKE_THRESHOLD":  85,   # %
    "RAM_SPIKE_THRESHOLD":  90,   # %

    # How often each monitor polls (seconds)
    "PROCESS_INTERVAL":  5,
    "NETWORK_INTERVAL":  8,
    "USB_INTERVAL":      3,
    "CLIPBOARD_INTERVAL":4,
    "BRIEFING_HOUR":     8,       # 8 AM daily briefing

    # Beaconing detection: flag if same process connects to same IP > N times in window
    "BEACON_COUNT":  6,
    "BEACON_WINDOW": 120,         # seconds

    # DB path for persistent event log
    "DB_PATH": os.path.join(os.path.expanduser("~"), ".jarvis_security.db"),
    "LOG_PATH": "jarvis_security.log",
    "BASELINE_PATH": os.path.join(os.path.expanduser("~"), ".jarvis_baseline.json"),
}

# ─────────────────────────────────────────────
#  LOGGING & DATABASE
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(CONFIG["LOG_PATH"], encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("JARVIS")

_db_lock = threading.Lock()

def db_init():
    with sqlite3.connect(CONFIG["DB_PATH"]) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    DEFAULT (datetime('now','localtime')),
            category  TEXT,
            severity  TEXT,
            title     TEXT,
            detail    TEXT
        );
        CREATE TABLE IF NOT EXISTS connections (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    DEFAULT (datetime('now','localtime')),
            pid       INTEGER,
            proc      TEXT,
            laddr     TEXT,
            raddr     TEXT,
            rport     INTEGER,
            country   TEXT
        );
        CREATE TABLE IF NOT EXISTS usb_devices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    DEFAULT (datetime('now','localtime')),
            device_id TEXT    UNIQUE,
            name      TEXT,
            vendor    TEXT
        );
        """)

def db_event(category, severity, title, detail=""):
    with _db_lock:
        with sqlite3.connect(CONFIG["DB_PATH"]) as con:
            con.execute(
                "INSERT INTO events(category,severity,title,detail) VALUES(?,?,?,?)",
                (category, severity, title, detail)
            )

def db_query(sql, params=()):
    with _db_lock:
        with sqlite3.connect(CONFIG["DB_PATH"]) as con:
            return con.execute(sql, params).fetchall()

# ─────────────────────────────────────────────
#  ALERT SYSTEM
# ─────────────────────────────────────────────

SEVERITY_COLOR = {
    "CRITICAL": Fore.RED + Style.BRIGHT,
    "HIGH":     Fore.YELLOW + Style.BRIGHT,
    "MEDIUM":   Fore.CYAN,
    "INFO":     Fore.GREEN,
}

def alert(severity, category, title, detail=""):
    title = str(title).encode("ascii", errors="replace").decode("ascii")
    detail = str(detail).encode("ascii", errors="replace").decode("ascii")
    color = SEVERITY_COLOR.get(severity, "")
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n{color}[{ts}] [{severity}] [{category}] {title}{Style.RESET_ALL}")
    if detail:
        print(f"  {Fore.WHITE}{detail}{Style.RESET_ALL}")
    db_event(category, severity, title, detail)
    log.warning(f"[{severity}][{category}] {title} | {detail}")
    if PLYER_OK and severity in ("CRITICAL", "HIGH") and plyer_notify:
        try:
            plyer_notify.notify(  # type: ignore
                title=f"JARVIS [{severity}] {category}",
                message=title,
                timeout=8,
            )
        except Exception:
            pass

# ─────────────────────────────────────────────
#  1. PROCESS & MEMORY MONITOR
# ─────────────────────────────────────────────

_seen_pids = set()
_proc_cpu_history = defaultdict(lambda: deque(maxlen=5))

def is_suspicious_proc(proc):
    name = (proc.info.get("name") or "").lower()
    exe  = (proc.info.get("exe")  or "").lower()
    if name in CONFIG["PROCESS_WHITELIST"]:
        return None
    for kw in CONFIG["SUSPICIOUS_NAMES"]:
        if kw in name or kw in exe:
            return f"Suspicious name match: '{kw}'"
    # Unsigned binary in Temp/AppData running as a new process
    temp = os.environ.get("TEMP", "").lower()
    appdata = os.environ.get("APPDATA", "").lower()
    if exe and (temp in exe or (appdata in exe and "\\local\\temp\\" in exe)):
        return f"Executable running from temp: {exe}"
    return None

def check_parent_anomaly(proc):
    """Flag browser/Office spawning cmd/powershell (classic macro/exploit)."""
    bad_children = {"cmd.exe", "powershell.exe", "wscript.exe", "cscript.exe", "mshta.exe"}
    risky_parents = {"winword.exe", "excel.exe", "outlook.exe", "chrome.exe",
                     "msedge.exe", "firefox.exe", "acrobat.exe", "acrord32.exe"}
    try:
        name   = (proc.info.get("name") or "").lower()
        parent = psutil.Process(proc.info["ppid"])
        pname  = (parent.name() or "").lower()
        if name in bad_children and pname in risky_parents:
            return f"{pname} spawned {name} (PID {proc.pid}) — possible macro/exploit"
    except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
        pass
    return None

def monitor_processes():
    log.info("Process monitor started.")
    while True:
        try:
            for proc in psutil.process_iter(["pid", "name", "exe", "ppid", "cpu_percent", "memory_percent"]):
                pid = proc.pid
                reason = is_suspicious_proc(proc)
                if reason and pid not in _seen_pids:
                    _seen_pids.add(pid)
                    alert("HIGH", "PROCESS", f"Suspicious process: {proc.info.get('name')} (PID {pid})", reason)

                anomaly = check_parent_anomaly(proc)
                if anomaly and pid not in _seen_pids:
                    _seen_pids.add(pid)
                    alert("CRITICAL", "PROCESS", "Parent anomaly detected", anomaly)

                # CPU spike per process
                cpu = proc.info.get("cpu_percent", 0) or 0
                _proc_cpu_history[pid].append(cpu)
                if len(_proc_cpu_history[pid]) == 5:
                    avg = sum(_proc_cpu_history[pid]) / 5
                    if avg > CONFIG["CPU_SPIKE_THRESHOLD"]:
                        alert("MEDIUM", "PROCESS",
                              f"CPU spike: {proc.info.get('name')} avg {avg:.0f}%",
                              f"PID {pid} sustained high CPU — possible cryptominer or ransomware")
                        _proc_cpu_history[pid].clear()

            # Overall RAM
            ram = psutil.virtual_memory().percent
            if ram > CONFIG["RAM_SPIKE_THRESHOLD"]:
                alert("MEDIUM", "PROCESS", f"RAM usage critical: {ram:.0f}%",
                      "High memory pressure — check for memory leaks or malware")

        except Exception as e:
            log.error(f"Process monitor error: {e}")
        time.sleep(CONFIG["PROCESS_INTERVAL"])

# ─────────────────────────────────────────────
#  2. NETWORK CONNECTION MONITOR
# ─────────────────────────────────────────────

_known_connections = set()
_beacon_tracker = defaultdict(list)   # (proc, raddr) -> [timestamps]

def geoip_country(ip):
    """Free geoip lookup — no API key needed."""
    try:
        if requests is None:
            return "?"
        r = requests.get(f"https://ipapi.co/{ip}/country/", timeout=3)
        return r.text.strip() if r.status_code == 200 else "?"
    except Exception:
        return "?"

def is_private_ip(ip):
    try:
        parsed = ipaddress.ip_address(ip)
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_multicast:
            return True
    except Exception:
        pass
    try:
        packed = socket.inet_aton(ip)
        addr = struct.unpack("!I", packed)[0]
        ranges = [
            (0xC0A80000, 0xFFFF0000),  # 192.168.x.x
            (0xAC100000, 0xFFF00000),  # 172.16-31.x.x
            (0x0A000000, 0xFF000000),  # 10.x.x.x
            (0x7F000000, 0xFF000000),  # 127.x.x.x
        ]
        return any(addr & mask == net for net, mask in ranges)
    except Exception:
        return False

def monitor_network():
    log.info("Network monitor started.")
    while True:
        try:
            conns = psutil.net_connections(kind="inet")
            for c in conns:
                if c.status != "ESTABLISHED":
                    continue
                if not c.raddr:
                    continue
                rip   = c.raddr.ip
                rport = c.raddr.port
                if is_private_ip(rip):
                    continue
                try:
                    pname = psutil.Process(c.pid).name() if c.pid else "unknown"
                except Exception:
                    pname = "unknown"

                key = (c.pid, rip, rport)
                if key not in _known_connections:
                    _known_connections.add(key)
                    country = geoip_country(rip)
                    sev = "HIGH" if rport in CONFIG["SUSPICIOUS_PORTS"] else "INFO"
                    alert(sev, "NETWORK",
                          f"New connection: {pname} → {rip}:{rport} [{country}]",
                          f"PID {c.pid} | lport {c.laddr.port if c.laddr else '?'}")
                    with _db_lock:
                        with sqlite3.connect(CONFIG["DB_PATH"]) as con:
                            con.execute(
                                "INSERT INTO connections(pid,proc,laddr,raddr,rport,country) VALUES(?,?,?,?,?,?)",
                                (c.pid, pname, str(c.laddr), rip, rport, country)
                            )

                # Beaconing detection
                bkey = (pname, rip)
                now = time.time()
                _beacon_tracker[bkey] = [t for t in _beacon_tracker[bkey]
                                         if now - t < CONFIG["BEACON_WINDOW"]]
                _beacon_tracker[bkey].append(now)
                if len(_beacon_tracker[bkey]) >= CONFIG["BEACON_COUNT"]:
                    alert("HIGH", "NETWORK",
                          f"C2 beaconing suspected: {pname} → {rip}",
                          f"{len(_beacon_tracker[bkey])} connections in {CONFIG['BEACON_WINDOW']}s")
                    _beacon_tracker[bkey].clear()

        except Exception as e:
            log.error(f"Network monitor error: {e}")
        time.sleep(CONFIG["NETWORK_INTERVAL"])

# ─────────────────────────────────────────────
#  3. FILE INTEGRITY WATCHER
# ─────────────────────────────────────────────

def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

def build_baseline():
    baseline = {}
    for watch in CONFIG["WATCH_PATHS"]:
        p = Path(watch)
        if p.is_file():
            h = sha256_file(watch)
            if h:
                baseline[watch] = h
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    h = sha256_file(str(f))
                    if h:
                        baseline[str(f)] = h
    return baseline

def check_baseline():
    bp = CONFIG["BASELINE_PATH"]
    if not os.path.exists(bp):
        log.info("Creating file integrity baseline...")
        baseline = build_baseline()
        with open(bp, "w") as f:
            json.dump(baseline, f, indent=2)
        log.info(f"Baseline saved: {len(baseline)} files")
        return
    with open(bp) as f:
        old = json.load(f)
    current = build_baseline()
    for path, new_hash in current.items():
        if path in old:
            if old[path] != new_hash:
                alert("HIGH", "INTEGRITY",
                      f"File modified: {path}",
                      f"Old: {old[path][:12]}… New: {new_hash[:12]}…")
        else:
            alert("MEDIUM", "INTEGRITY", f"New file appeared: {path}")
    for path in old:
        if path not in current:
            alert("MEDIUM", "INTEGRITY", f"File deleted: {path}")
    # Update baseline
    with open(bp, "w") as f:
        json.dump(current, f, indent=2)

class SecurityFileHandler(FileSystemEventHandler if Observer else object):  # type: ignore
    """File system event handler for monitoring file changes."""
    def on_modified(self, event):  # type: ignore
        if not event.is_directory:
            alert("HIGH", "INTEGRITY",
                  f"File changed: {event.src_path}",
                  "Critical path modified — check immediately")
            h = sha256_file(event.src_path)
            if h and requests and CONFIG["VT_API_KEY"]:
                vt_check_hash(h, label=os.path.basename(event.src_path))

    def on_created(self, event):
        if not event.is_directory:
            alert("MEDIUM", "INTEGRITY", f"New file created: {event.src_path}")

    def on_deleted(self, event):
        if not event.is_directory:
            alert("MEDIUM", "INTEGRITY", f"File deleted: {event.src_path}")

def monitor_files():
    check_baseline()
    if Observer is None:
        log.warning("File watcher disabled (watchdog not installed)")
        return
    observer = Observer()
    for watch in CONFIG["WATCH_PATHS"]:
        p = Path(watch)
        target = str(p.parent) if p.is_file() else str(p)
        if os.path.exists(target):
            observer.schedule(SecurityFileHandler(), target, recursive=True)
    observer.start()
    log.info("File integrity watcher started.")
    try:
        while True:
            time.sleep(30)
    except Exception:
        observer.stop()
    observer.join()

# ─────────────────────────────────────────────
#  4. LOGIN & AUTH EVENT MONITOR  (Windows Event Log)
# ─────────────────────────────────────────────

def monitor_login_events():
    """Poll Windows Security Event Log for login events."""
    log.info("Login event monitor started.")
    try:
        import win32evtlog  # type: ignore
        import win32con  # type: ignore
    except ImportError:
        log.warning("pywin32 not installed — login monitor disabled. pip install pywin32")
        return

    server   = "localhost"
    logtype  = "Security"
    flags    = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    seen_ids = set()

    INTERESTING = {
        4625: ("HIGH",     "LOGIN",   "Failed login attempt"),
        4624: ("INFO",     "LOGIN",   "Successful login"),
        4648: ("MEDIUM",   "LOGIN",   "Login with explicit credentials"),
        4720: ("HIGH",     "AUTH",    "New user account created"),
        4732: ("HIGH",     "AUTH",    "User added to privileged group"),
        4672: ("MEDIUM",   "AUTH",    "Special privileges assigned"),
        4776: ("MEDIUM",   "AUTH",    "Credential validation"),
    }

    while True:
        try:
            hand = win32evtlog.OpenEventLog(server, logtype)
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            for ev in (events or []):
                uid = (ev.RecordNumber, ev.EventID)
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                eid = ev.EventID & 0xFFFF
                if eid in INTERESTING:
                    sev, cat, title = INTERESTING[eid]
                    strings = ev.StringInserts or []
                    detail  = " | ".join(str(s) for s in strings[:6] if s)
                    alert(sev, cat, f"{title} (Event {eid})", detail)
            win32evtlog.CloseEventLog(hand)
        except Exception as e:
            if "required privilege" in str(e).lower() or "1314" in str(e):
                log.warning("Login monitor disabled: run Jarvis as administrator to read the Security Event Log.")
                return
            log.error(f"Login monitor error: {e}")
        time.sleep(10)

# ─────────────────────────────────────────────
#  5. USB & PERIPHERAL GUARD
# ─────────────────────────────────────────────

_known_usb = set()

def get_usb_devices_wmic():
    """Returns list of (device_id, name, vendor) tuples via wmic."""
    devices = []
    try:
        if shutil.which("wmic"):
            out = subprocess.check_output(
                ["wmic", "path", "Win32_PnPEntity",
                 "where", "PNPDeviceID like 'USB%'",
                 "get", "DeviceID,Name,Manufacturer", "/format:csv"],
                stderr=subprocess.DEVNULL, timeout=10
            ).decode(errors="ignore")
        else:
            ps = (
                "Get-PnpDevice -PresentOnly | "
                "Where-Object { $_.InstanceId -like 'USB*' } | "
                "Select-Object InstanceId,FriendlyName,Manufacturer | ConvertTo-Csv -NoTypeInformation"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                stderr=subprocess.DEVNULL, timeout=10
            ).decode(errors="ignore")
        for line in out.splitlines():
            parts = line.strip().split(",")
            if len(parts) >= 4:
                device_id = parts[1].strip().strip('"')
                name      = parts[3].strip().strip('"')
                vendor    = parts[2].strip().strip('"')
                if not device_id or device_id.lower() == "instanceid":
                    continue
                if device_id.lower() == "deviceid":
                    continue
                if device_id:
                    devices.append((device_id, name, vendor))
            elif len(parts) >= 3:
                device_id = parts[0].strip().strip('"')
                name      = parts[1].strip().strip('"')
                vendor    = parts[2].strip().strip('"')
                if device_id and device_id.lower() not in {"instanceid", "deviceid"}:
                    devices.append((device_id, name, vendor))
    except Exception as e:
        log.error(f"USB device query error: {e}")
    return devices

def monitor_usb():
    log.info("USB monitor started.")
    # Seed known devices
    for dev_id, name, vendor in get_usb_devices_wmic():
        _known_usb.add(dev_id)
        with _db_lock:
            with sqlite3.connect(CONFIG["DB_PATH"]) as con:
                con.execute(
                    "INSERT OR IGNORE INTO usb_devices(device_id,name,vendor) VALUES(?,?,?)",
                    (dev_id, name, vendor)
                )
    while True:
        try:
            current = get_usb_devices_wmic()
            for dev_id, name, vendor in current:
                if dev_id not in _known_usb:
                    _known_usb.add(dev_id)
                    sev = "MEDIUM" if CONFIG["USB_WHITELIST_VENDORS"] and \
                          vendor in CONFIG["USB_WHITELIST_VENDORS"] else "HIGH"
                    alert(sev, "USB",
                          f"New USB device: {name}",
                          f"Vendor: {vendor} | ID: {dev_id}")
                    with _db_lock:
                        with sqlite3.connect(CONFIG["DB_PATH"]) as con:
                            con.execute(
                                "INSERT OR IGNORE INTO usb_devices(device_id,name,vendor) VALUES(?,?,?)",
                                (dev_id, name, vendor)
                            )
        except Exception as e:
            log.error(f"USB monitor error: {e}")
        time.sleep(CONFIG["USB_INTERVAL"])

# ─────────────────────────────────────────────
#  6. STARTUP / PERSISTENCE MONITOR
# ─────────────────────────────────────────────

_known_startup = {}

def read_registry_run_keys():
    entries = {}
    try:
        import winreg
        for key_path in CONFIG["REGISTRY_RUN_KEYS"]:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hive, key_path)
                    i = 0
                    while True:
                        try:
                            name, data, _ = winreg.EnumValue(key, i)
                            entries[f"{hive}\\{key_path}\\{name}"] = data
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass
    except ImportError:
        pass
    return entries

def get_scheduled_tasks():
    tasks = {}
    try:
        out = subprocess.check_output(
            ["schtasks", "/query", "/fo", "CSV", "/nh"],
            stderr=subprocess.DEVNULL, timeout=15
        ).decode(errors="ignore")
        for line in out.splitlines():
            parts = line.strip().strip('"').split('","')
            if parts:
                tasks[parts[0]] = parts[1] if len(parts) > 1 else ""
    except Exception:
        pass
    return tasks

def monitor_persistence():
    log.info("Persistence monitor started.")
    _known_startup["registry"] = read_registry_run_keys()
    _known_startup["tasks"]    = get_scheduled_tasks()

    while True:
        try:
            new_reg = read_registry_run_keys()
            for k, v in new_reg.items():
                if k not in _known_startup["registry"]:
                    alert("CRITICAL", "PERSISTENCE",
                          f"New registry run key: {k.split(chr(92))[-1]}",
                          f"Value: {v}")
            _known_startup["registry"] = new_reg

            new_tasks = get_scheduled_tasks()
            for k in new_tasks:
                if k not in _known_startup["tasks"]:
                    alert("HIGH", "PERSISTENCE",
                          f"New scheduled task: {k}",
                          f"Status: {new_tasks[k]}")
            _known_startup["tasks"] = new_tasks

        except Exception as e:
            log.error(f"Persistence monitor error: {e}")
        time.sleep(30)

# ─────────────────────────────────────────────
#  7. CLIPBOARD SENSITIVE DATA DETECTOR
# ─────────────────────────────────────────────

_last_clip = ""

def monitor_clipboard():
    if pyperclip is None:
        log.warning("pyperclip not installed — clipboard monitor disabled.")
        return
    log.info("Clipboard monitor started.")
    global _last_clip
    while True:
        try:
            text = pyperclip.paste()
            if text and text != _last_clip:
                _last_clip = text
                for label, pattern in CONFIG["SENSITIVE_PATTERNS"].items():
                    if re.search(pattern, text):
                        preview = text[:80].replace("\n", " ")
                        alert("HIGH", "CLIPBOARD",
                              f"Sensitive data in clipboard: {label}",
                              f"Preview: {preview}…")
                        break
        except Exception:
            pass
        time.sleep(CONFIG["CLIPBOARD_INTERVAL"])

# ─────────────────────────────────────────────
#  8. VIRUSTOTAL SCANNER
# ─────────────────────────────────────────────

def vt_check_hash(file_hash, label=""):
    if not requests or not CONFIG["VT_API_KEY"]:
        return
    try:
        r = requests.get(
            f"https://www.virustotal.com/api/v3/files/{file_hash}",
            headers={"x-apikey": CONFIG["VT_API_KEY"]},
            timeout=10
        )
        if r.status_code == 200:
            data  = r.json()
            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            mal   = stats.get("malicious", 0)
            total = sum(stats.values())
            sev   = "CRITICAL" if mal > 5 else "HIGH" if mal > 0 else "INFO"
            alert(sev, "VIRUSTOTAL",
                  f"VT scan: {label or file_hash[:12]}",
                  f"Detections: {mal}/{total} engines flagged as malicious")
        elif r.status_code == 404:
            log.info(f"VT: hash not found (new/unknown file) — {label}")
    except Exception as e:
        log.error(f"VT scan error: {e}")

def vt_check_ip(ip):
    if not requests or not CONFIG["VT_API_KEY"]:
        return
    try:
        r = requests.get(
            f"https://www.virustotal.com/api/v3/ip_addresses/{ip}",
            headers={"x-apikey": CONFIG["VT_API_KEY"]},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            mal   = stats.get("malicious", 0)
            sev   = "CRITICAL" if mal > 5 else "HIGH" if mal > 0 else "INFO"
            alert(sev, "VIRUSTOTAL", f"VT IP scan: {ip}",
                  f"Malicious votes: {mal}")
    except Exception as e:
        log.error(f"VT IP scan error: {e}")

# ─────────────────────────────────────────────
#  9. WINDOWS SECURITY HEALTH CHECK
# ─────────────────────────────────────────────

def check_windows_security_health():
    results = []

    # Windows Defender status
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "Get-MpComputerStatus | Select-Object -Property "
             "AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,"
             "BehaviorMonitorEnabled,IoavProtectionEnabled | ConvertTo-Json"],
            stderr=subprocess.DEVNULL, timeout=15
        ).decode(errors="ignore")
        data = json.loads(out)
        for k, v in data.items():
            status = "ON" if v else "OFF"
            sev    = "INFO" if v else "CRITICAL"
            results.append((sev, k.replace("Enabled", ""), status))
    except Exception as e:
        results.append(("MEDIUM", "Defender", f"Could not check: {e}"))

    # Firewall
    try:
        out = subprocess.check_output(
            ["netsh", "advfirewall", "show", "allprofiles", "state"],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode(errors="ignore")
        for profile in ["Domain", "Private", "Public"]:
            if f"{profile} Profile Settings" in out:
                state = "ON" if "State                                 ON" in out else "OFF"
                sev   = "INFO" if state == "ON" else "CRITICAL"
                results.append((sev, f"Firewall {profile}", state))
    except Exception as e:
        results.append(("MEDIUM", "Firewall", f"Could not check: {e}"))

    # BitLocker
    try:
        out = subprocess.check_output(
            ["manage-bde", "-status", "C:"],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode(errors="ignore")
        encrypted = "Protection On" in out
        results.append(("INFO" if encrypted else "HIGH",
                        "BitLocker C:", "ON" if encrypted else "OFF"))
    except Exception:
        results.append(("MEDIUM", "BitLocker", "Could not check (run as admin)"))

    # Auto-update
    try:
        out = subprocess.check_output(
            ["powershell", "-Command",
             "(New-Object -ComObject Microsoft.Update.AutoUpdate).Settings.NotificationLevel"],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode(errors="ignore").strip()
        results.append(("INFO" if out == "4" else "MEDIUM",
                        "Windows Update", f"Notification level {out}"))
    except Exception:
        results.append(("MEDIUM", "Windows Update", "Could not check"))

    return results

def print_health_report():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'═'*60}")
    print(f"  JARVIS SECURITY HEALTH REPORT — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'═'*60}{Style.RESET_ALL}\n")
    results = check_windows_security_health()
    for sev, name, status in results:
        color  = SEVERITY_COLOR.get(sev, "")
        symbol = "✓" if sev == "INFO" else "✗"
        print(f"  {color}{symbol}  {name:<30} {status}{Style.RESET_ALL}")
    print()

# ─────────────────────────────────────────────
# API-friendly helpers used by the FastAPI voice server.
_monitors_started = False

def start_monitors_once():
    """Start security monitors in daemon threads. Safe to call repeatedly."""
    global _monitors_started
    db_init()
    if _monitors_started:
        return "Cyber mode is already running."
    monitors = [
        ("Process monitor", monitor_processes),
        ("Network monitor", monitor_network),
        ("File integrity", monitor_files),
        ("USB guard", monitor_usb),
        ("Persistence monitor", monitor_persistence),
        ("Clipboard monitor", monitor_clipboard),
        ("Login event monitor", monitor_login_events),
        ("Daily briefing", daily_briefing),
    ]
    for name, target in monitors:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        log.info(f"{name} started")
    _monitors_started = True
    return f"Cyber mode online. {len(monitors)} monitors are running."

def security_status_text():
    db_init()
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    conns = [c for c in psutil.net_connections(kind="inet")
             if c.status == "ESTABLISHED" and c.raddr and not is_private_ip(c.raddr.ip)]
    rows = db_query("SELECT severity, COUNT(*) FROM events GROUP BY severity")
    counts = {sev: count for sev, count in rows}
    risk = counts.get("CRITICAL", 0) + counts.get("HIGH", 0)
    return (
        f"CPU {cpu:.0f} percent, RAM {ram.percent:.0f} percent, disk {disk.percent:.0f} percent, "
        f"{len(psutil.pids())} processes, {len(conns)} external connections, {risk} high-risk events recorded."
    )

def security_health_text():
    results = check_windows_security_health()
    warnings = [(sev, name, status) for sev, name, status in results if sev != "INFO"]
    if not warnings:
        return "Defender, Firewall, BitLocker, and Windows Update look healthy."
    details = "; ".join(f"{name}: {status}" for _, name, status in warnings[:5])
    return f"Security health has {len(warnings)} warnings. {details}."

def security_events_text(n=20):
    db_init()
    n = max(1, min(int(n), 200))
    rows = db_query("SELECT ts, severity, category, title FROM events ORDER BY id DESC LIMIT ?", (n,))
    if not rows:
        return "No security events recorded yet."
    counts = defaultdict(int)
    for _, sev, _, _ in rows:
        counts[sev] += 1
    headline = ", ".join(f"{counts[s]} {s.lower()}" for s in ["CRITICAL", "HIGH", "MEDIUM", "INFO"] if counts[s])
    latest = "; ".join(f"{sev} {cat}: {title}" for _, sev, cat, title in rows[:5])
    return f"Last {len(rows)} events: {headline}. Latest: {latest}."

def security_scan_file_text(path):
    path = (path or "").strip().strip('"')
    if not path:
        return "Usage: scan followed by a file path."
    if not os.path.exists(path):
        return f"File not found: {path}"
    h = sha256_file(path)
    if not h:
        return f"Could not hash {path}."
    if CONFIG["VT_API_KEY"]:
        vt_check_hash(h, label=os.path.basename(path))
        return f"SHA-256 {h}. VirusTotal checked."
    return f"SHA-256 {h}. VirusTotal disabled."

def security_ip_text(ip):
    ip = (ip or "").strip()
    if not ip:
        return "Usage: ip followed by an address."
    if CONFIG["VT_API_KEY"]:
        vt_check_ip(ip)
        return f"VirusTotal IP check requested for {ip}."
    return "VirusTotal IP scanning disabled. Set VT_API_KEY to enable it."

def security_connections_text(limit=12):
    conns = [c for c in psutil.net_connections(kind="inet")
             if c.status == "ESTABLISHED" and c.raddr]
    if not conns:
        return "No active external connections."
    parts = []
    for c in conns[:limit]:
        try:
            pname = psutil.Process(c.pid).name() if c.pid else "unknown"
        except Exception:
            pname = "unknown"
        try:
            if isinstance(c.raddr, tuple) and len(c.raddr) >= 2:  # type: ignore
                remote_ip, remote_port = c.raddr[0], c.raddr[1]
            else:
                remote_ip = getattr(c.raddr, 'ip', 'unknown')
                remote_port = getattr(c.raddr, 'port', 'unknown')
            if not is_private_ip(remote_ip):
                parts.append(f"{pname} to {remote_ip}:{remote_port}")
        except (IndexError, AttributeError, TypeError):
            pass
    if not parts:
        return "No active external connections."
    return f"{len(parts)} active external connections. " + "; ".join(parts) + "."

def security_usb_text(limit=20):
    db_init()
    rows = db_query("SELECT ts, name, vendor, device_id FROM usb_devices ORDER BY ts DESC LIMIT ?", (limit,))
    if rows:
        return f"{len(rows)} USB records. " + "; ".join(f"{name} by {vendor}" for _, name, vendor, _ in rows[:5]) + "."
    current = get_usb_devices_wmic()
    if not current:
        return "No USB devices recorded or detected."
    return f"{len(current)} USB devices currently detected. " + "; ".join(f"{name} by {vendor}" for _, name, vendor in current[:5]) + "."

def security_persistence_text():
    reg = read_registry_run_keys()
    tasks = get_scheduled_tasks()
    reg_preview = "; ".join(k.split(chr(92))[-1] for k in list(reg)[:5]) or "none"
    task_preview = "; ".join(list(tasks)[:5]) or "none"
    return f"{len(reg)} registry run entries and {len(tasks)} scheduled tasks. Registry: {reg_preview}. Tasks: {task_preview}."

def security_rebuild_baseline_text():
    bp = CONFIG["BASELINE_PATH"]
    if os.path.exists(bp):
        os.remove(bp)
    baseline = build_baseline()
    with open(bp, "w") as f:
        json.dump(baseline, f, indent=2)
    return f"Security baseline rebuilt with {len(baseline)} files."

#  10. DAILY BRIEFING
# ─────────────────────────────────────────────

def daily_briefing():
    log.info("Daily briefing thread started.")
    last_briefing_day = None
    while True:
        now = datetime.datetime.now()
        if now.hour == CONFIG["BRIEFING_HOUR"] and now.date() != last_briefing_day:
            last_briefing_day = now.date()
            rows = db_query(
                "SELECT severity, category, title FROM events "
                "WHERE ts >= datetime('now','-24 hours','localtime') ORDER BY severity"
            )
            print(f"\n{Fore.CYAN}{Style.BRIGHT}{'═'*60}")
            print(f"  JARVIS MORNING SECURITY BRIEFING — {now:%Y-%m-%d}")
            print(f"{'═'*60}{Style.RESET_ALL}")
            if not rows:
                print(f"  {Fore.GREEN}All clear — no security events in the last 24 hours.{Style.RESET_ALL}")
            else:
                counts = defaultdict(int)
                for sev, cat, title in rows:
                    counts[sev] += 1
                for sev in ["CRITICAL", "HIGH", "MEDIUM", "INFO"]:
                    if counts[sev]:
                        color = SEVERITY_COLOR[sev]
                        print(f"  {color}{sev}: {counts[sev]} events{Style.RESET_ALL}")
                print()
                for sev, cat, title in rows[:10]:
                    color = SEVERITY_COLOR.get(sev, "")
                    print(f"  {color}[{sev}] {cat}: {title}{Style.RESET_ALL}")
            print_health_report()
        time.sleep(60)

# ─────────────────────────────────────────────
#  INTERACTIVE COMMAND PROMPT
# ─────────────────────────────────────────────

COMMANDS = """
  status          — live system snapshot (CPU, RAM, connections, processes)
  health          — Windows Defender / Firewall / BitLocker check
  events [N]      — last N security events (default 20)
  scan <file>     — SHA-256 hash a file and submit to VirusTotal
  ip <address>    — check IP on VirusTotal
  baseline        — rebuild file integrity baseline now
  usb             — list all USB devices ever seen
  connections     — active external connections
  persistence     — show registry run keys & scheduled tasks
  help            — show this menu
  exit            — quit JARVIS Security Suite
"""

def cmd_status():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    conns = [c for c in psutil.net_connections(kind="inet")
             if c.status == "ESTABLISHED" and c.raddr]
    conns_filtered = []
    for c in conns:
        try:
            if isinstance(c.raddr, tuple) and len(c.raddr) >= 1:  # type: ignore
                ip = c.raddr[0]
            else:
                ip = getattr(c.raddr, 'ip', '')
            if ip and not is_private_ip(ip):
                conns_filtered.append(c)
        except (IndexError, AttributeError, TypeError):
            pass
    procs = len(psutil.pids())
    print(f"\n  CPU: {cpu:.0f}%  |  RAM: {ram.percent:.0f}% ({ram.used//1024//1024}MB/{ram.total//1024//1024}MB)")
    print(f"  Disk C:\\: {disk.percent:.0f}% used")
    print(f"  Processes: {procs}  |  External connections: {len(conns_filtered)}")
    if conns_filtered:
        print(f"\n  Active external connections:")
        for c in conns_filtered[:8]:
            try:
                pname = psutil.Process(c.pid).name() if c.pid else "?"
            except Exception:
                pname = "?"
            try:
                if isinstance(c.raddr, tuple) and len(c.raddr) >= 2:  # type: ignore
                    remote_ip, remote_port = c.raddr[0], c.raddr[1]
                else:
                    remote_ip = getattr(c.raddr, 'ip', 'unknown')
                    remote_port = getattr(c.raddr, 'port', 'unknown')
                print(f"    {pname:<20} → {remote_ip}:{remote_port}")
            except (IndexError, AttributeError, TypeError):
                pass
    print()

def cmd_events(n=20):
    rows = db_query(
        "SELECT ts, severity, category, title, detail FROM events ORDER BY id DESC LIMIT ?", (n,)
    )
    if not rows:
        print("  No events recorded yet.")
        return
    for ts, sev, cat, title, detail in rows:
        color = SEVERITY_COLOR.get(sev, "")
        print(f"  {color}[{ts}] [{sev}] [{cat}] {title}{Style.RESET_ALL}")
        if detail:
            print(f"    {Fore.WHITE}{detail[:120]}{Style.RESET_ALL}")

def cmd_scan(path):
    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return
    h = sha256_file(path)
    print(f"  SHA-256: {h}")
    if CONFIG["VT_API_KEY"]:
        vt_check_hash(h, label=os.path.basename(path))
    else:
        print("  (Set VT_API_KEY in CONFIG to enable VirusTotal scan)")

def cmd_connections():
    conns = [c for c in psutil.net_connections(kind="inet")
             if c.status == "ESTABLISHED" and c.raddr]
    conns_filtered = []
    for c in conns:
        try:
            if isinstance(c.raddr, tuple) and len(c.raddr) >= 1:  # type: ignore
                ip = c.raddr[0]
            else:
                ip = getattr(c.raddr, 'ip', '')
            if ip and not is_private_ip(ip):
                conns_filtered.append(c)
        except (IndexError, AttributeError, TypeError):
            pass
    if not conns_filtered:
        print("  No active external connections.")
        return
    print(f"\n  {'Process':<22} {'Remote IP':<18} {'Port':<8} {'PID'}")
    print(f"  {'-'*60}")
    for c in conns_filtered:
        try:
            pname = psutil.Process(c.pid).name() if c.pid else "?"
        except Exception:
            pname = "?"
        try:
            if isinstance(c.raddr, tuple) and len(c.raddr) >= 2:  # type: ignore
                remote_ip, remote_port = c.raddr[0], c.raddr[1]
            else:
                remote_ip = getattr(c.raddr, 'ip', 'unknown')
                remote_port = getattr(c.raddr, 'port', 'unknown')
            print(f"  {pname:<22} {remote_ip:<18} {remote_port:<8} {c.pid}")
        except (IndexError, AttributeError, TypeError):
            pass
    print()

def cmd_usb():
    rows = db_query("SELECT ts, name, vendor, device_id FROM usb_devices ORDER BY ts DESC")
    if not rows:
        print("  No USB devices recorded.")
        return
    for ts, name, vendor, dev_id in rows:
        print(f"  [{ts}] {name} | Vendor: {vendor}")
        print(f"          ID: {dev_id}")

def cmd_persistence():
    print("\n  Registry run keys:")
    reg = read_registry_run_keys()
    for k, v in list(reg.items())[:20]:
        print(f"  {k.split(chr(92))[-1]:<35} {v[:60]}")
    print("\n  Scheduled tasks (first 15):")
    tasks = get_scheduled_tasks()
    for name, status in list(tasks.items())[:15]:
        print(f"  {name:<45} {status}")
    print()

def interactive_shell():
    print(f"\n{Fore.CYAN}{Style.BRIGHT}  JARVIS Security Suite — Interactive Console{Style.RESET_ALL}")
    print(f"  Type {Fore.WHITE}help{Style.RESET_ALL} for commands.\n")
    while True:
        try:
            raw = input(f"{Fore.GREEN}JARVIS>{Style.RESET_ALL} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Shutting down JARVIS Security Suite. Stay safe.")
            os._exit(0)
        if not raw:
            continue
        parts = raw.split(None, 1)
        cmd   = parts[0].lower()
        arg   = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            print(COMMANDS)
        elif cmd == "status":
            cmd_status()
        elif cmd == "health":
            print_health_report()
        elif cmd == "events":
            cmd_events(int(arg) if arg.isdigit() else 20)
        elif cmd == "scan":
            if arg:
                cmd_scan(arg)
            else:
                print("  Usage: scan <filepath>")
        elif cmd == "ip":
            if arg:
                vt_check_ip(arg)
            else:
                print("  Usage: ip <address>")
        elif cmd == "baseline":
            bp = CONFIG["BASELINE_PATH"]
            if os.path.exists(bp):
                os.remove(bp)
            check_baseline()
            print("  Baseline rebuilt.")
        elif cmd == "usb":
            cmd_usb()
        elif cmd == "connections":
            cmd_connections()
        elif cmd == "persistence":
            cmd_persistence()
        elif cmd == "exit":
            print("  Shutting down. Stay safe.")
            os._exit(0)
        else:
            print(f"  Unknown command: {cmd}. Type help.")

# ─────────────────────────────────────────────
#  STARTUP BANNER
# ─────────────────────────────────────────────

BANNER = r"""
     _    _    ____  __     _____ ____
    | |  / \  |  _ \ \ \   / /_ _/ ___|
 _  | | / _ \ | |_) | \ \ / / | |\___ \
| |_| |/ ___ \|  _ <   \ V /  | | ___) |
 \___//_/   \_\_| \_\   \_/  |___|____/

  Windows Security Suite — by a cybersecurity pro, for a cybersecurity pro
"""

def main():
    parser = argparse.ArgumentParser(description="JARVIS Windows Security Suite")
    parser.add_argument("--daemon", action="store_true", help="start monitors without interactive console or prompts")
    parser.add_argument("--vt-key", default=os.getenv("VT_API_KEY", ""), help="VirusTotal API key")
    args = parser.parse_args()
    if args.vt_key:
        CONFIG["VT_API_KEY"] = args.vt_key

    if platform.system() != "Windows":
        print("[!] This script is designed for Windows. Some features may not work on other OS.")

    print(Fore.CYAN + Style.BRIGHT + BANNER + Style.RESET_ALL)

    # First-run API key prompt
    if not args.daemon and not CONFIG["VT_API_KEY"]:
        key = input(
            f"  {Fore.YELLOW}Enter VirusTotal API key{Style.RESET_ALL} "
            f"(free at virustotal.com) or press Enter to skip: "
        ).strip()
        if key:
            CONFIG["VT_API_KEY"] = key

    db_init()
    print_health_report()

    if args.daemon:
        print(f"  {Fore.GREEN}*{Style.RESET_ALL} {start_monitors_once()}")
        print(f"\n  {Fore.CYAN}All monitors active. Watching your laptop.{Style.RESET_ALL}\n")
        print(f"  Logs -> {CONFIG['LOG_PATH']}   |   DB -> {CONFIG['DB_PATH']}\n")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    # ── Launch all monitors as daemon threads ──
    monitors = [
        ("Process monitor",      monitor_processes),
        ("Network monitor",      monitor_network),
        ("File integrity",       monitor_files),
        ("USB guard",            monitor_usb),
        ("Persistence monitor",  monitor_persistence),
        ("Clipboard monitor",    monitor_clipboard),
        ("Login event monitor",  monitor_login_events),
        ("Daily briefing",       daily_briefing),
    ]

    for name, target in monitors:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {name} started")

    print(f"\n  {Fore.CYAN}All monitors active. Watching your laptop.{Style.RESET_ALL}\n")
    print(f"  Logs → {CONFIG['LOG_PATH']}   |   DB → {CONFIG['DB_PATH']}\n")

    # Run interactive shell on the main thread
    interactive_shell()

if __name__ == "__main__":
    main()
