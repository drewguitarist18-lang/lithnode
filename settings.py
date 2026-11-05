"""App-wide settings, in settings.json in Lithnode's folder: what new flows start with, and whether to check for updates.

The theme lives in the window itself (it has to apply before the page draws), so it isn't here.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any

import flows

LIMITS = [250_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000]   # the choices the Settings window offers
DEFAULTS: dict[str, Any] = {"limit": flows.DEFAULT_LIMIT, "roles": True, "check_updates": True}
_lock = threading.Lock()


def clean(raw: Any) -> dict[str, Any]:
    """Known keys only, each a sane value; anything missing or junk falls back to its default."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    if "limit" in raw:
        out["limit"] = flows.clean_limit(raw["limit"])
    for key in ("roles", "check_updates"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    return out


def load(root: str | Path) -> dict[str, Any]:
    try:
        return clean(json.loads((Path(root) / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(root: str | Path, changes: dict[str, Any]) -> dict[str, Any]:
    """Merge changes into what's saved and write it (atomically, so a crash can't leave half a file)."""
    with _lock:
        merged = clean({**load(root), **(changes if isinstance(changes, dict) else {})})
        path = Path(root) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return merged
