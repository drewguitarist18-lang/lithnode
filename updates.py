"""Is there a newer Lithnode? Asks GitHub for the latest release, at most every few hours, and never blocks the app:
offline or rate-limited just means "no news". It only tells people; downloading and installing stays theirs.
Also the one anonymous install/update ping per version (ping_once)."""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib import request as urlrequest

from version import VERSION

REPO = "drewguitarist18-lang/lithnode"
API = os.environ.get("LITHNODE_RELEASES_API") or f"https://api.github.com/repos/{REPO}/releases/latest"
EVERY = 6 * 3600
FILES = {"win32": "LithnodeSetup.exe", "darwin": "Lithnode-mac-arm64.dmg"}   # anything else: the Flatpak

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "latest": "", "page": ""}


def parse(v: str) -> tuple[int, ...]:
    """'v0.1.21' -> (0, 1, 21). Anything that isn't a version reads as () so it's never 'newer'."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(v or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def newer(latest: str, current: str = VERSION) -> bool:
    a, b = parse(latest), parse(current)
    return bool(a and b) and a > b


PING = os.environ.get("LITHNODE_PING_URL") or "https://lithnode.com/api/ping"
PING_OS = {"win32": "win", "darwin": "mac"}   # anything else: linux


def ping_once(root, had_data: bool) -> str:
    """The first launch of each version of an installed Lithnode tells lithnode.com, once: 'install' (a new copy) or
    'update', with the version and win/mac/linux. No ID, nothing about you. Settings > 'Count my install' turns it off.
    Runs from source don't ping (unless LITHNODE_PING_URL points somewhere, for testing). Returns what it sent, or ''."""
    if not (getattr(sys, "frozen", False) or os.environ.get("LITHNODE_PING_URL")):
        return ""
    marker = Path(root) / "pinged.json"
    try:
        seen = json.loads(marker.read_text(encoding="utf-8"))
        seen = seen if isinstance(seen, list) else []
    except FileNotFoundError:
        seen = None
    except (OSError, ValueError):
        seen = []
    if seen is not None and VERSION in seen:
        return ""
    kind = "update" if (seen or had_data) else "install"
    body = json.dumps({"kind": kind, "v": VERSION, "os": PING_OS.get(sys.platform, "linux")}).encode()
    req = urlrequest.Request(PING, data=body, method="POST",
                             headers={"Content-Type": "application/json", "User-Agent": f"Lithnode/{VERSION}"})
    try:
        with urlrequest.urlopen(req, timeout=8):
            pass
    except Exception:   # offline: try again next launch
        return ""
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps((seen or []) + [VERSION]), encoding="utf-8")
    except OSError:
        pass
    return kind


def download_url(tag: str, platform: str = sys.platform) -> str:
    name = FILES.get(platform, "Lithnode.flatpak")
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def _fetch() -> tuple[str, str]:
    req = urlrequest.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": f"Lithnode/{VERSION}"})
    with urlrequest.urlopen(req, timeout=6) as r:
        d = json.loads(r.read().decode("utf-8"))
    return str(d.get("tag_name") or ""), str(d.get("html_url") or "")


def status(force: bool = False) -> dict:
    """What the app shows: this version, the latest one, and where to get it if it's newer."""
    with _lock:
        if force or time.time() - _cache["at"] > EVERY:
            try:
                _cache["latest"], _cache["page"] = _fetch()
                _cache["at"] = time.time()
                _cache.pop("error", None)
            except Exception as e:   # offline, rate-limited, GitHub down: try again on the next look
                _cache["error"] = type(e).__name__
                _cache["at"] = time.time() - EVERY + 600   # not before 10 minutes
        tag, page = _cache["latest"], _cache["page"]
        up = newer(tag)
        return {"version": VERSION, "latest": tag.lstrip("v") if tag else "", "newer": up,
                "download": download_url(tag) if up else "", "notes": page if up else "",
                "checked": bool(tag), "error": _cache.get("error", ""), "self_update": up and can_self_update()}


# ---- one-click update on Windows: download the new installer and run it with no windows; it reopens Lithnode
_job: dict = {"state": "", "pct": 0, "error": ""}   # state: "" | downloading | installing | failed


def can_self_update() -> bool:
    r"""Only the Windows installer's own copy ({app}\server\lithnode-server.exe next to {app}\Lithnode.exe)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    exe = Path(sys.executable)
    return exe.parent.name.lower() == "server" and (exe.parent.parent / "Lithnode.exe").exists()


def _pet_on() -> bool:
    """Keep Claude Pet as it is: on if Claude Code's settings have the lithnode-cli hook."""
    try:
        text = (Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8")
    except OSError:
        return False
    return "lithnode-cli" in text.lower()


def job() -> dict:
    with _lock:
        return dict(_job)


def start_update(url: str) -> tuple[bool, str]:
    if not can_self_update():
        return False, "This copy of Lithnode can't update itself. Download the new version instead."
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        return False, "No update to install."
    with _lock:
        if _job["state"] in ("downloading", "installing"):
            return True, "Already updating."
        _job.update(state="downloading", pct=0, error="")
    threading.Thread(target=_update, args=(url,), daemon=True).start()
    return True, "Updating."


def _update(url: str) -> None:
    import subprocess
    import tempfile
    try:
        folder = Path(tempfile.mkdtemp(prefix="lithnode-update-"))
        dest = folder / "LithnodeSetup.exe"
        req = urlrequest.Request(url, headers={"User-Agent": f"Lithnode/{VERSION}"})
        with urlrequest.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                got += len(chunk)
                if total:
                    with _lock:
                        _job["pct"] = min(99, got * 100 // total)
        with open(dest, "rb") as f:
            if f.read(2) != b"MZ" or (total and got != total):
                raise ValueError("the download was incomplete")
        with _lock:
            _job.update(state="installing", pct=100)
        # the installer closes this Lithnode itself, then reopens it (/RELAUNCH); /PET keeps Claude Pet as it was
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: it outlives this app
        subprocess.Popen([str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1",
                          f"/PET={'yes' if _pet_on() else 'no'}"], creationflags=flags, close_fds=True)
    except Exception as e:
        with _lock:
            _job.update(state="failed", error=f"Couldn't update ({type(e).__name__}). Try again, or download it instead.")
