"""Other agent CLIs a team can run on: OpenAI's Codex CLI and Cursor's agent CLI.

Claude Code is the default engine and lives in agents.py and claude_code.py. This file covers the rest: finding
each CLI, checking its sign-in, the command line for one headless session, and turning its live JSON output
into Lithnode's steps and final report. Both sign in with the person's own account, like Claude Code.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import claude_code

NO_WINDOW = claude_code.NO_WINDOW
ENGINES = ("claude", "codex", "cursor")
LABELS = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor"}
STATUS_TTL = 60


# ------------------------------------------------------------------- finding them

def codex_command():
    """`codex`, as installed by npm (`npm i -g @openai/codex`). LITHNODE_CODEX_CMD (a JSON list) replaces it."""
    override = os.environ.get("LITHNODE_CODEX_CMD")
    if override:
        return json.loads(override)
    found = shutil.which("codex")
    return [found] if found else None


def cursor_command():
    """Cursor's agent CLI. On Windows its launcher is a PowerShell script, so run its node.exe and index.js
    directly (that also keeps stdin, where the prompt goes, intact). LITHNODE_CURSOR_CMD replaces it."""
    override = os.environ.get("LITHNODE_CURSOR_CMD")
    if override:
        return json.loads(override)
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "versions"
    if os.name == "nt" and root.is_dir():
        for version in sorted((p for p in root.iterdir() if (p / "index.js").exists()), key=lambda p: p.name, reverse=True):
            node = version / "node.exe"
            if node.exists():
                return [str(node), str(version / "index.js")]
    found = shutil.which("cursor-agent")
    return [found] if found else None


FINDERS = {"codex": codex_command, "cursor": cursor_command}

_status = {}
_status_lock = threading.Lock()


def _run(cmd, *args, timeout=40):
    try:
        out = subprocess.run([*cmd, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, cwd=str(Path.home()))
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def status(engine, force=False):
    """{"installed", "signed_in", "note"} for codex or cursor: free local checks, cached for a minute.
    For Codex it also says whether its Windows sandbox works ("sandbox"): when it doesn't, Codex can only run
    commands with full access."""
    with _status_lock:
        hit = _status.get(engine)
        if hit and not force and time.time() - hit[0] < STATUS_TTL:
            return hit[1]
        cmd = FINDERS[engine]()
        value = {"installed": bool(cmd), "signed_in": False, "note": ""}
        if not cmd:
            value["note"] = {"codex": "Not installed. Install it with: npm i -g @openai/codex",
                             "cursor": "Not installed. See cursor.com/cli to install it."}[engine]
        elif engine == "codex":
            _, out = _run(cmd, "login", "status")
            value["signed_in"] = "logged in" in out.lower() and "not logged in" not in out.lower()
            if not value["signed_in"]:
                value["note"] = "Not signed in. Run: codex login"
            elif os.name == "nt" and not os.environ.get("LITHNODE_CODEX_SANDBOX"):
                # Codex's Windows sandbox can't run commands yet: its setup tries to re-permission the command
                # runner (node_repl.exe) while that runner is already running, and fails. Its own check
                # (`codex sandbox`) can pass anyway, so don't trust it. LITHNODE_CODEX_SANDBOX=1 tries the sandbox.
                value["sandbox"] = False
                value["note"] = ("Codex's Windows sandbox can't run commands yet (a Codex bug), so Codex teams "
                                 "run with full access. Lithnode asks you to confirm first.")
            else:
                value["sandbox"] = True
        else:
            _, out = _run(cmd, "status")
            value["signed_in"] = "logged in" in out.lower() and "not logged in" not in out.lower()
            if not value["signed_in"]:
                value["note"] = "Not signed in. Run: cursor-agent login"
        _status[engine] = (time.time(), value)
        return value


_models = {}
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))


def models(engine, force=False):
    """The models this account can pick on an engine, [{"id", "label"}], from the CLI itself (free, no tokens).
    Cached for 10 minutes. Empty when the CLI can't say; the team then uses the CLI's own default."""
    hit = _models.get(engine)
    if hit and not force and time.time() - hit[0] < 600:
        return hit[1]
    cmd, found = FINDERS[engine](), []
    if cmd and engine == "codex":
        code, out = _run(cmd, "debug", "models", timeout=30)
        try:
            data = json.loads(out[out.find("{"):]) if code == 0 else {}
            found = [{"id": m["slug"], "label": m.get("display_name") or m["slug"]} for m in data.get("models", [])
                     if m.get("visibility", "list") == "list"]
        except (ValueError, KeyError, TypeError):
            found = []
    elif cmd and engine == "cursor":
        code, out = _run(cmd, "models", timeout=30)
        for line in out.translate(ZERO_WIDTH).splitlines() if code == 0 else []:
            mid, sep, label = line.strip().partition(" - ")
            if sep and " " not in mid:
                found.append({"id": mid, "label": " ".join(label.replace("(current, default)", "").split())})
    _models[engine] = (time.time(), found)
    return found


def all_status(force=False):
    return {"claude": {"installed": bool(claude_code.find_command()), "signed_in": True, "note": ""},
            **{e: status(e, force) for e in ("codex", "cursor")}}


# ------------------------------------------------------------------- one session

CODEX_SANDBOX = {"none": "read-only", "read": "read-only", "web": "read-only", "research": "read-only",
                 "edit": "workspace-write", "full": "danger-full-access"}


def codex_sandbox(tools):
    """The sandbox for a tool level. If the Windows sandbox is broken, only full access can run anything."""
    info = status("codex")
    if info.get("sandbox") is False:
        return "danger-full-access"
    return CODEX_SANDBOX.get(tools, "read-only")


def build_args(engine, command, *, tools, model=""):
    if engine == "codex":
        search = ["--search"] if tools in ("web", "research") else []   # a top-level option: before `exec`
        args = [*command, *search, "exec", "--json", "--skip-git-repo-check", "--ephemeral", "--sandbox", codex_sandbox(tools)]
        if model:
            args += ["--model", model]
        return args + ["-"]          # the prompt comes on stdin
    if engine == "cursor":
        args = [*command, "-p", "--output-format", "stream-json", "--trust"]
        if tools in ("edit", "full"):
            args.append("--force")   # without it, file changes are only proposed
        if model:
            args += ["--model", model]
        return args
    raise ValueError(engine)


def wrap_prompt(system, prompt):
    """Neither CLI takes an extra system prompt on the command line, so the role goes first in the prompt."""
    return f"# Your instructions\n{system}\n\n{prompt}"


def short(path):
    return Path(str(path)).name or str(path)


def codex_event(obj, out):
    """Feed one Codex JSON event into `out` = {"steps": [], "texts": [], "final": None, "error": ""}.
    Returns a step line to show, if any."""
    kind = obj.get("type")
    item = obj.get("item") or {}
    itype = item.get("type") or item.get("item_type")
    if kind == "item.completed" and itype in ("agent_message", "assistant_message", "command_execution", "file_change",
                                               "mcp_tool_call", "web_search"):
        out["turns"] = out.get("turns", 0) + 1
    if kind == "item.started":
        if itype == "command_execution":
            cmd = str(item.get("command", ""))
            if "-Command " in cmd:               # Codex wraps Windows commands in powershell.exe -Command ...
                cmd = cmd.split("-Command ", 1)[1]
            return f"Running: {cmd.strip().strip(chr(34))[:60]}"
        if itype == "mcp_tool_call":
            return f"{item.get('server', 'tool')}: {str(item.get('tool', '')).replace('_', ' ')}"
        if itype == "web_search":
            query = item.get("query") or (item.get("action") or {}).get("query") or ""
            return f"Searching the web: {query}"[:80] if query else "Searching the web"
    elif kind == "item.completed":
        if itype in ("agent_message", "assistant_message"):
            out["texts"].append(item.get("text", ""))
            return "Writing the report"
        if itype == "file_change":
            files = [c.get("path", "") for c in item.get("changes") or []]
            return f"Editing {', '.join(short(f) for f in files[:2])}" if files else "Editing files"
    elif kind == "turn.completed":
        out["final"] = "\n\n".join(t for t in out["texts"] if t).strip()
        out["texts"] = [out["texts"][-1]] if out["texts"] else []
    elif kind == "turn.failed":
        out["error"] = str((obj.get("error") or {}).get("message") or "Codex reported an error.")
    elif kind == "error" and "reconnecting" not in str(obj.get("message", "")).lower():
        out["error"] = str(obj.get("message") or "Codex reported an error.")
    return None


CURSOR_TOOLS = {"readToolCall": "Reading", "editToolCall": "Editing", "writeToolCall": "Writing", "deleteToolCall": "Deleting",
                "grepToolCall": "Searching", "globToolCall": "Finding", "lsToolCall": "Listing", "shellToolCall": "Running"}


def cursor_event(obj, out):
    """Same as codex_event, for Cursor's stream-json (shaped much like Claude Code's)."""
    kind = obj.get("type")
    if kind == "assistant":
        out["turns"] = out.get("turns", 0) + 1
        parts = (obj.get("message") or {}).get("content") or []
        said = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
        if said:
            out["texts"].append(said)
            return "Writing the report"
    elif kind == "tool_call" and obj.get("subtype") == "started":
        call = obj.get("tool_call") or {}
        for key, verb in CURSOR_TOOLS.items():
            if key in call:
                args = (call[key] or {}).get("args") or {}
                what = args.get("command") or args.get("path") or args.get("pattern") or args.get("globPattern") or ""
                return f"{verb}: {str(what)[:60]}" if verb == "Running" else f"{verb} {short(what) if verb in ('Reading', 'Editing', 'Writing') else what}".strip()
        return "Using a tool"
    elif kind == "result":
        if obj.get("is_error") or str(obj.get("subtype", "")).startswith("error"):
            out["error"] = str(obj.get("result") or "Cursor reported an error.")
        else:
            out["final"] = obj.get("result") if isinstance(obj.get("result"), str) else "\n\n".join(out["texts"])
    return None


PARSERS = {"codex": codex_event, "cursor": cursor_event}


def friendly_error(engine, text):
    """Plain words for the errors people actually hit."""
    low = (text or "").lower()
    if "usage limit" in low or "rate limit" in low or "quota" in low:
        return f"Your {LABELS[engine]} plan has hit its usage limit, so this agent couldn't run."
    if "not logged in" in low or "login" in low and "required" in low or "unauthorized" in low:
        return f"{LABELS[engine]} isn't signed in. Run `{'codex login' if engine == 'codex' else 'cursor-agent login'}` once, then try again."
    return text
