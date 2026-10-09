"""The Office feed: every open Claude Code session, plus every agent a flow is running.

Sessions come from Claude Pet's hooks (~/.claude-pet/sessions.json) when the pet is
installed. Flow agents come straight from the runner, so they show up even without the pet,
drawn as their cluster's sprite. When both know the same session, they are merged.
"""
import ctypes
import json
import os
import time
from pathlib import Path

PET_DIR = Path(os.environ.get("CLAWD_PET_HOME") or Path.home() / ".claude-pet")
STALE_AFTER = 12 * 3600


def pid_alive(pid):
    try:
        k32 = ctypes.windll.kernel32
    except AttributeError:        # not Windows: trust the timestamp instead
        return True
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def hook_sessions():
    """{session id: entry} for live sessions the pet's hooks know about."""
    try:
        data = json.loads((PET_DIR / "sessions.json").read_text())
    except (OSError, ValueError):
        return {}
    now, live = time.time(), {}
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if val.get("pid"):
            if pid_alive(val["pid"]):
                live[key] = val
        elif now - val.get("ts", 0) < STALE_AFTER:
            live[key] = val
    return live


def flow_agents(runner):
    """{session id: office entry} for agents of active runs that are still working."""
    out = {}
    for run in runner.active() if runner else []:
        snap = run.snapshot()
        for nid, st in snap["nodes"].items():
            node = run.by_id[nid]
            for a in st["agents"]:
                if a["status"] != "running":
                    continue
                out[a["session_id"]] = {
                    "id": a["session_id"],
                    "bot": {"id": nid, "name": a["name"], "shape": a["shape"], "color": a["color"]},
                    "project": a["name"], "cwd": snap["folder"], "status": "working",
                    "status_ts": a["started"], "detail": a["step"] or "Thinking…",
                    "tokens": 0, "window": 0, "tools": len(a["steps"]), "done": 0,
                    "started": a["started"], "last": time.time(), "subagents": [],
                    "flow": {"run": snap["id"], "name": snap["flow_name"], "stage": node["name"]},
                    "engine": a.get("engine") or "claude",
                }
            if st["status"] == "approval":
                out[f"approval-{snap['id']}-{nid}"] = {
                    "id": f"approval-{snap['id']}-{nid}",
                    "bot": {"id": nid, "name": node["name"], "shape": "crab", "color": "#D97757"},
                    "project": node["name"], "cwd": snap["folder"], "status": "waiting",
                    "status_ts": st["started"] or time.time(), "detail": node.get("message") or "Needs your approval",
                    "tokens": 0, "window": 0, "tools": 0, "done": 0, "started": st["started"] or time.time(),
                    "last": time.time(), "subagents": [],
                    "flow": {"run": snap["id"], "name": snap["flow_name"], "stage": node["name"]},
                }
    return out


def snapshot(runner=None):
    agents = flow_agents(runner)
    sessions = []
    for sid, s in hook_sessions().items():
        entry = {
            "id": sid, "bot": None,
            "cwd": s.get("cwd", ""), "status": s.get("status", "idle"),
            "status_ts": s.get("status_ts", s.get("started", time.time())), "detail": s.get("detail", ""),
            "tokens": s.get("tokens", 0), "window": s.get("window", 0), "tools": s.get("tools", 0),
            "done": s.get("done", 0), "started": s.get("started", time.time()), "last": s.get("ts", 0),
            "flow": None, "engine": "claude",   # hook sessions come from Claude Code
            "subagents": [{"id": k, "type": v.get("type", "agent"), "detail": v.get("detail", ""),
                           "tools": v.get("tools", 0), "started": v.get("ts", time.time())}
                          for k, v in (s.get("subagents") or {}).items()],
        }
        mine = agents.pop(sid, None)
        if mine:   # the hook saw a flow agent: keep its live numbers, but draw it as the agent
            entry.update(bot=mine["bot"], flow=mine["flow"], engine=mine.get("engine", "claude"), detail=entry["detail"] or mine["detail"])
        entry["project"] = (entry["bot"] or {}).get("name") or s.get("project") or "session"
        sessions.append(entry)
    sessions += agents.values()
    sessions.sort(key=lambda s: s["started"])
    return {"now": time.time(), "sessions": sessions, "pet": (PET_DIR / "sessions.json").exists()}
