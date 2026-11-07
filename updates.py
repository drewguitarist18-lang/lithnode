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
                "checked": bool(tag), "error": _cache.get("error", "")}
