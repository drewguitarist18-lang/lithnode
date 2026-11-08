"""Lithnode's MCP server: lets Claude (Claude Code, the Claude desktop app, any MCP client) build and run flows.

It speaks MCP over stdio and passes each tool call to the Lithnode app already running on this computer
(http://127.0.0.1:8790, or LITHNODE_PORT). Nothing here runs agents itself, so everything shows up live in
Lithnode, and a run Claude starts can be watched, approved or stopped there too.

Run it:   python mcp_server.py           (from source)
          lithnode-cli mcp               (the installed app)
Add it:   claude mcp add lithnode -- lithnode-cli mcp
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

try:
    from version import VERSION
except ImportError:   # pragma: no cover
    VERSION = "0"

PORT = int(os.environ.get("LITHNODE_PORT", 8790))
BASE = f"http://127.0.0.1:{PORT}"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
NOT_RUNNING = "Lithnode isn't open. Open the Lithnode app on this computer, then try again."


class LithnodeError(Exception):
    pass


def call(path: str, body: dict[str, Any] | None = None, timeout: float = 30) -> dict[str, Any]:
    """One request to the running app. Raises LithnodeError with words a person can act on."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read() or b"{}").get("error") or ""
        except ValueError:
            msg = ""
        raise LithnodeError(msg or f"Lithnode answered {exc.code}.") from None
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc):
            raise LithnodeError("Lithnode took too long to answer.") from None
        raise LithnodeError(NOT_RUNNING) from None


# ------------------------------------------------------------------ what Claude sees

def _team(n: dict[str, Any]) -> str:
    if n.get("type") == "master":
        return "Start"
    if n.get("type") == "done":
        return "Complete"
    if n.get("type") != "cluster":
        return f"{n.get('name') or n.get('type')} ({n.get('type')})"
    engine = n.get("engine") or "claude"
    model = n.get("engine_model") if engine != "claude" else n.get("model")
    bits = [f"{n.get('count', 1)} agent{'s' if n.get('count', 1) != 1 else ''}", engine + (f" {model}" if model else "")]
    if n.get("role"):
        bits.append(f"role {n['role']}")
    if n.get("tools"):
        bits.append(f"tools {n['tools']}")
    return f"{n.get('name') or 'Team'} ({', '.join(bits)})"


def _order(flow: dict[str, Any]) -> list[dict[str, Any]]:
    """Nodes in the order work moves through them (Start first), then anything not wired in."""
    nodes = {n["id"]: n for n in flow.get("nodes", [])}
    nxt: dict[str, list[str]] = {}
    for e in flow.get("edges", []):
        nxt.setdefault(e["from"], []).append(e["to"])
    seen, out, todo = set(), [], [n["id"] for n in flow.get("nodes", []) if n.get("type") == "master"]
    while todo:
        nid = todo.pop(0)
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        out.append(nodes[nid])
        todo += nxt.get(nid, [])
    return out + [n for nid, n in nodes.items() if nid not in seen]


def describe_flow(payload: dict[str, Any]) -> str:
    flow = payload.get("flow") or payload
    lines = [f"Flow \"{flow.get('name', 'Flow')}\" (id {flow.get('id')})"]
    if flow.get("folder"):
        lines.append(f"Folder: {flow['folder']}")
    lines.append("Steps, in order:")
    lines += [f"  {i}. {_team(n)}" for i, n in enumerate(_order(flow), 1)]
    if payload.get("problems"):
        lines.append("Can't run yet: " + " ".join(payload["problems"]))
    return "\n".join(lines)


def describe_run(snap: dict[str, Any]) -> str:
    lines = [f"Run {snap.get('id')} of \"{snap.get('flow_name', 'Flow')}\": {snap.get('status')}",
             f"Task: {snap.get('task', '')}", f"Folder: {snap.get('folder', '')}", f"Tokens used: {snap.get('tokens', 0):,}"]
    flow = snap.get("flow") or {}
    states = snap.get("nodes") or {}
    lines.append("Steps:")
    for n in _order(flow):
        st = states.get(n["id"]) or {}
        mark = st.get("status", "waiting")
        extra = f" - {st['error']}" if st.get("error") else (" - waiting for your approval (use decide)" if mark == "approval" else "")
        lines.append(f"  [{mark}] {n.get('name') or n.get('type')} (node {n['id']}){extra}")
    if snap.get("files"):
        lines.append("Files it changed: " + ", ".join(snap["files"][:30]))
    if snap.get("final"):
        lines.append("\nFinal report:\n" + snap["final"][:12000])
    elif snap.get("log"):
        lines.append("Latest: " + str(snap["log"][-1].get("text", "")))
    return "\n".join(lines)


def _str(args: dict[str, Any], key: str, required: bool = True) -> str:
    v = str(args.get(key) or "").strip()
    if required and not v:
        raise LithnodeError(f"{key} is required.")
    return v


def t_status(args: dict[str, Any]) -> str:
    v = call("/api/version")
    en = call("/api/engines").get("engines", [])
    ready = [e["name"] for e in en if e.get("installed") and e.get("signed_in")]
    active = [r for r in call("/api/runs").get("runs", []) if r.get("status") in ("running", "waiting")]
    return (f"Lithnode {v.get('version')} is open at {BASE}.\nEngines ready: {', '.join(ready) or 'none (sign one in from Lithnode Settings)'}."
            f"\nRuns going now: {len(active)}.")


def t_list_flows(args: dict[str, Any]) -> str:
    d = call("/api/flows")
    lines = [f"- {f['name']} (id {f['id']}, {f['nodes']} nodes)" for f in d.get("flows", [])]
    tpl = [f"- {t['name']} (template {t['id']}): {t['blurb']}" for t in d.get("templates", [])]
    return ("Your flows:\n" + ("\n".join(lines) or "  none yet")) + ("\n\nTemplates for create_flow:\n" + "\n".join(tpl) if tpl else "")


def t_get_flow(args: dict[str, Any]) -> str:
    return describe_flow(call(f"/api/flows/{_str(args, 'flow_id')}"))


def t_create_flow(args: dict[str, Any]) -> str:
    desc, tpl = _str(args, "description", False), _str(args, "template", False)
    if not desc and not tpl:
        raise LithnodeError("Give a description of the team, or a template id from list_flows.")
    d = call("/api/flows/design", {"prompt": desc}, timeout=600) if desc else call("/api/flows", {"template": tpl})
    return describe_flow(d) + "\n\nIt's saved in Lithnode. Run it with run_flow and this flow id."


def t_run_flow(args: dict[str, Any]) -> str:
    body: dict[str, Any] = {"task": _str(args, "task")}
    if _str(args, "folder", False):
        body["folder"] = _str(args, "folder")
    d = call(f"/api/flows/{_str(args, 'flow_id')}/run", body)
    return (f"Started run {d['run']}. It's running in Lithnode now, where you can watch it."
            " Check on it with get_run; runs take minutes, so wait between checks.")


def t_get_run(args: dict[str, Any]) -> str:
    return describe_run(call(f"/api/runs/{_str(args, 'run_id')}"))


def t_list_runs(args: dict[str, Any]) -> str:
    runs = call("/api/runs").get("runs", [])[:15]
    return "Recent runs:\n" + ("\n".join(f"- {r['id']}: {r.get('flow_name', 'Flow')} - {r.get('status')} - {str(r.get('task', ''))[:80]}"
                                         for r in runs) or "  none yet")


def t_decide(args: dict[str, Any]) -> str:
    call(f"/api/runs/{_str(args, 'run_id')}/decide",
         {"node": _str(args, "node"), "approved": bool(args.get("approved")), "note": _str(args, "note", False)})
    return "Approved, the run goes on." if args.get("approved") else "Turned down. The note goes back to the team."


def t_stop_run(args: dict[str, Any]) -> str:
    call(f"/api/runs/{_str(args, 'run_id')}/stop", {})
    return "Stopped. The work finished so far is kept."


def _schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


S = {"type": "string"}
TOOLS: dict[str, tuple[Any, dict[str, Any]]] = {
    "lithnode_status": (t_status, {"title": "Lithnode status", "readOnlyHint": True,
        "description": "Whether Lithnode is open, its version, which engines are signed in, and how many runs are going.",
        "inputSchema": _schema({}, [])}),
    "list_flows": (t_list_flows, {"title": "List flows", "readOnlyHint": True,
        "description": "Your saved flows (teams of AI agents wired together) and the templates you can start one from.",
        "inputSchema": _schema({}, [])}),
    "get_flow": (t_get_flow, {"title": "Read a flow", "readOnlyHint": True,
        "description": "One flow's steps in order: each team, its engine and model, and anything stopping it from running.",
        "inputSchema": _schema({"flow_id": S}, ["flow_id"])}),
    "create_flow": (t_create_flow, {"title": "Create a flow",
        "description": "Make a new flow. Either describe the team in plain words (Lithnode's designer drafts it, about a minute) "
                       "or pass a template id from list_flows. It is saved, not run.",
        "inputSchema": _schema({"description": {**S, "description": "The team you want, e.g. 'build the feature, review it, test it'"},
                                "template": {**S, "description": "A template id from list_flows"}}, [])}),
    "run_flow": (t_run_flow, {"title": "Run a flow",
        "description": "Start a flow on a task. Its agents work in the folder (they can change files there) and use your "
                       "signed-in plans or keys. Returns a run id right away; the run goes on in Lithnode.",
        "inputSchema": _schema({"flow_id": S, "task": {**S, "description": "What the team should do"},
                                "folder": {**S, "description": "Absolute path of the folder to work in. Default: the flow's last folder"}},
                               ["flow_id", "task"])}),
    "get_run": (t_get_run, {"title": "Check a run", "readOnlyHint": True,
        "description": "A run's status, each step's state, approvals waiting, files changed and, once done, the final report.",
        "inputSchema": _schema({"run_id": S}, ["run_id"])}),
    "list_runs": (t_list_runs, {"title": "List runs", "readOnlyHint": True,
        "description": "Recent runs, newest first.", "inputSchema": _schema({}, [])}),
    "decide": (t_decide, {"title": "Approve or turn down",
        "description": "Answer an approval step a run is waiting on (get_run shows which node). Only approve when the user agrees.",
        "inputSchema": _schema({"run_id": S, "node": S, "approved": {"type": "boolean"}, "note": {**S, "description": "Why, for the team"}},
                               ["run_id", "node", "approved"])}),
    "stop_run": (t_stop_run, {"title": "Stop a run", "destructiveHint": True,
        "description": "Stop a run that's going. Finished work is kept.", "inputSchema": _schema({"run_id": S}, ["run_id"])}),
}


# ------------------------------------------------------------------ JSON-RPC over stdio

def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:   # a notification (initialized, cancelled): nothing to answer
        return None

    def ok(result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "lithnode", "title": "Lithnode", "version": VERSION},
                   "instructions": "Lithnode runs teams of AI agents (flows) on this computer. list_flows or create_flow, then "
                                   "run_flow with a task and folder, then get_run now and then until it's done. The user can "
                                   "watch every run live in the Lithnode app."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": name, **{k: v for k, v in meta.items() if k in ("title", "description", "inputSchema")},
                              "annotations": {k: v for k, v in meta.items() if k.endswith("Hint")}}
                             for name, (_, meta) in TOOLS.items()]})
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        try:
            text, err = TOOLS[name][0](params.get("arguments") or {}), False
        except LithnodeError as exc:
            text, err = str(exc), True
        except Exception as exc:  # a bug here must not end the session
            text, err = f"{type(exc).__name__}: {exc}", True
        return ok({"content": [{"type": "text", "text": text}], "isError": err})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip().lstrip("﻿")   # a BOM from some shells
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply: Any = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = [r for r in map(handle, msg) if r] if isinstance(msg, list) else handle(msg)
        if reply:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
