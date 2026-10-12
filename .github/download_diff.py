"""For the download-alerts workflow: compare release download counts with the last run's.
Reads the GitHub releases JSON on stdin, keeps the counts in counts.json, prints one line per file whose count went up.
The first run (no counts.json yet) only remembers."""
import json
import sys
from pathlib import Path

releases = json.load(sys.stdin)
now = {f"{r['tag_name']} {a['name']}": a["download_count"] for r in releases for a in r["assets"]}
store = Path("counts.json")
old = json.loads(store.read_text()) if store.exists() else None
store.write_text(json.dumps(now))
if old is not None:
    new = [(k, n - old.get(k, 0), n) for k, n in now.items() if n > old.get(k, 0)]
    for k, plus, n in new:
        print(f"{k}: +{plus} ({n} total)")
    if new:
        print(f"\nAll downloads so far: {sum(now.values())}")
