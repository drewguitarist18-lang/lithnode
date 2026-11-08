"""Other engines a team can run on: OpenAI's Codex CLI, Cursor's agent CLI and Ollama's local models.

Claude Code is the default engine and lives in agents.py and claude_code.py. This file covers the rest: finding
each CLI, checking its sign-in, the command line for one headless session, and turning its live JSON output
into Lithnode's steps and final report. Both sign in with the person's own account, like Claude Code.
Ollama needs no account: it runs free open-source models on this computer, answering from the prompt alone (no tools).
"""
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import claude_code

NO_WINDOW = claude_code.NO_WINDOW
ENGINES = ("claude", "codex", "cursor", "ollama")
LABELS = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor", "ollama": "Ollama"}
OLLAMA_URL = os.environ.get("LITHNODE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
LOCAL = Path(os.environ.get("LOCALAPPDATA", ""))
STATUS_TTL = 60


# ------------------------------------------------------------------- finding them

def codex_command() -> list[str] | None:
    """`codex`, as installed by npm (`npm i -g @openai/codex`). LITHNODE_CODEX_CMD (a JSON list) replaces it."""
    override = os.environ.get("LITHNODE_CODEX_CMD")
    if override:
        return json.loads(override)
    found = claude_code.which("codex")
    return [found] if found else None


def cursor_command() -> list[str] | None:
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
    found = claude_code.which("cursor-agent") or claude_code.which("agent")   # newer installs name it `agent`
    return [found] if found else None


def cursor_app_installed() -> bool:
    """The Cursor editor (not its agent CLI, which Lithnode needs)."""
    return bool(claude_code.which("cursor")) or (os.name == "nt" and (LOCAL / "Programs" / "cursor" / "Cursor.exe").exists())


def ollama_command() -> list[str] | None:
    """`ollama`, which also starts its local server. On Windows it may not be on PATH until a new sign-in."""
    found = claude_code.which("ollama")
    if not found and os.name == "nt" and (LOCAL / "Programs" / "Ollama" / "ollama.exe").exists():
        found = str(LOCAL / "Programs" / "Ollama" / "ollama.exe")
    return [found] if found else None


def ollama_tags() -> list[dict[str, Any]] | None:
    """The models downloaded into Ollama, or None when its server isn't answering."""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as resp:
            return list(json.loads(resp.read()).get("models") or [])
    except (OSError, ValueError, urllib.error.URLError):
        return None


FINDERS = {"codex": codex_command, "cursor": cursor_command}

_status = {}
_status_lock = threading.Lock()


def _run(cmd: list[str], *args: str, timeout: float = 40) -> tuple[int, str]:
    try:
        out = subprocess.run(claude_code.host([*cmd, *args]), capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, cwd=str(Path.home()))
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def status(engine: str, force: bool = False) -> dict[str, Any]:
    """{"installed", "signed_in", "note"} for codex or cursor: free local checks, cached for a minute.
    For Codex it also says whether Windows can restrict it to the selected folder ("sandbox"): if not, Codex
    runs with full access to the computer."""
    with _status_lock:
        hit = _status.get(engine)
        if hit and not force and time.time() - hit[0] < STATUS_TTL:
            return hit[1]
        if engine == "ollama":
            value = _ollama_status()
            _status[engine] = (time.time(), value)
            return value
        cmd = FINDERS[engine]()
        value = {"installed": bool(cmd), "signed_in": False, "note": ""}
        if not cmd and engine == "cursor" and cursor_app_installed():
            value["note"] = "You have the Cursor app, but flows need Cursor's command-line agent too. Click Install."
        elif not cmd:
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
                value["note"] = ("This Windows setup can't restrict Codex to the selected folder. Codex teams "
                                 "run with full access to your computer, and Lithnode asks you to confirm first.")
            else:
                value["sandbox"] = True
        else:
            _, out = _run(cmd, "status")
            value["signed_in"] = "logged in" in out.lower() and "not logged in" not in out.lower()
            if not value["signed_in"]:
                value["note"] = "Not signed in. Run: cursor-agent login"
        _status[engine] = (time.time(), value)
        return value


def _ollama_status() -> dict[str, Any]:
    """Ollama has no sign-in: it's ready once its server answers and at least one model is downloaded."""
    tags = ollama_tags()
    if tags is None and ollama_command():
        return {"installed": True, "signed_in": False, "note": "Ollama is installed but not running. Click Start."}
    if tags is None:
        return {"installed": False, "signed_in": False, "note": "Not installed. Click Install, or get it from ollama.com."}
    if not tags:
        return {"installed": True, "signed_in": False, "note": "No model downloaded yet. Click Get a model to download llama3.2 (2 GB)."}
    return {"installed": True, "signed_in": True, "local": True,
            "note": "Free and runs on this computer. Local models answer from what they're given: no web, files or tools."}


_models = {}
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))


def models(engine: str, force: bool = False) -> list[dict[str, Any]]:
    """The models this account can pick on an engine, [{"id", "label"}], from the CLI itself (free, no tokens).
    Cached for 10 minutes. Empty when the CLI can't say; the team then uses the CLI's own default."""
    hit = _models.get(engine)
    if hit and not force and time.time() - hit[0] < 600:
        return hit[1]
    if engine == "ollama":
        found = [{"id": m["name"], "label": m["name"].removesuffix(":latest")} for m in ollama_tags() or [] if m.get("name")]
        _models[engine] = (time.time() - 540, found)   # downloads show up within a minute
        return found
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


def all_status(force: bool = False) -> dict[str, dict[str, Any]]:
    claude = claude_code.auth_status(force=force)
    return {"claude": {"installed": bool(claude.get("available")), "signed_in": bool(claude.get("logged_in")), "note": ""},
            **{e: status(e, force) for e in ("codex", "cursor", "ollama")}}


def available_engine(force: bool = False) -> str | None:
    """The first engine ready to design or run a flow on this computer."""
    info = all_status(force)
    return next((engine for engine in ENGINES if info[engine]["installed"] and info[engine]["signed_in"]), None)


INSTALL = {   # what Install runs in a terminal: each engine's own official installer
    "codex": "npm i -g @openai/codex",
    "cursor": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"irm 'https://cursor.com/install?win32=true' | iex\"",
    "ollama": "winget install --id Ollama.Ollama -e --accept-package-agreements",
}
INSTALL_UNIX = {"codex": "npm i -g @openai/codex", "cursor": "curl https://cursor.com/install -fsS | bash",
                "ollama": "curl -fsSL https://ollama.com/install.sh | sh"}
STARTER_MODEL = "llama3.2"


def start_install(engine: str) -> tuple[bool, str]:
    """Open a terminal that installs an engine with its official installer (or, for Ollama, downloads a model)."""
    if engine not in INSTALL:
        return False, "Choose Codex, Cursor or Ollama."
    if engine == "ollama" and ollama_command() and ollama_tags() is None:   # installed, not running: start its server
        try:
            subprocess.Popen([*ollama_command(), "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=NO_WINDOW, **claude_code.NEW_GROUP)
        except OSError as exc:
            return False, f"Couldn't start Ollama: {exc}"
        with _status_lock:
            _status.pop(engine, None)
        return True, "Ollama is starting. Click Check again in a few seconds."
    if engine == "ollama" and ollama_command():
        line = subprocess.list2cmdline([*ollama_command(), "pull", STARTER_MODEL])
        done = "When the download finishes, click Check again."
    else:
        line = INSTALL[engine] if os.name == "nt" else INSTALL_UNIX[engine]
        done = "When it finishes, click Check again" + (" and then Sign in." if engine != "ollama" else ".")
    if os.name != "nt":
        return False, f"Run `{line}` in a terminal. {done}"
    try:
        subprocess.Popen(["cmd.exe", "/k", line], cwd=str(Path.home()), creationflags=subprocess.CREATE_NEW_CONSOLE)
        with _status_lock:
            _status.pop(engine, None)
        return True, f"A terminal opened. {done}"
    except OSError as exc:
        return False, f"Couldn't start the {LABELS[engine]} install: {exc}"


def start_login(engine: str) -> tuple[bool, str]:
    """Open an interactive Codex or Cursor sign-in on platforms where Lithnode can do so."""
    if engine not in FINDERS:
        return False, "Choose Codex or Cursor."
    command = FINDERS[engine]()
    if not command:
        return False, f"{LABELS[engine]} isn't installed on this computer."
    if os.name != "nt":
        return False, f"Run `{'codex login' if engine == 'codex' else 'cursor-agent login'}` in a terminal, then check again."
    try:
        login = subprocess.list2cmdline([*command, "login"])
        subprocess.Popen(["cmd.exe", "/k", login], cwd=str(Path.home()))
        return True, "A terminal opened for sign-in. Finish there, then click Check again."
    except OSError as exc:
        return False, f"Couldn't open {LABELS[engine]} sign-in: {exc}"


# ------------------------------------------------------------------- one session

CODEX_SANDBOX = {"none": "read-only", "read": "read-only", "web": "read-only", "research": "read-only",
                 "edit": "workspace-write", "full": "danger-full-access", "all": "danger-full-access"}


def codex_sandbox(tools: str) -> str:
    """The sandbox for a tool level. If the Windows sandbox is broken, only full access can run anything."""
    info = status("codex")
    if info.get("sandbox") is False:
        return "danger-full-access"
    return CODEX_SANDBOX.get(tools, "read-only")


def build_args(engine: str, command: list[str], *, tools: str, model: str = "") -> list[str]:
    if engine == "codex":
        search = ["--search"] if tools in ("web", "research", "all") else []   # a top-level option: before `exec`
        args = [*command, *search, "exec", "--json", "--skip-git-repo-check", "--ephemeral", "--sandbox", codex_sandbox(tools)]
        if model:
            args += ["--model", model]
        return args + ["-"]          # the prompt comes on stdin
    if engine == "cursor":
        args = [*command, "-p", "--output-format", "stream-json", "--trust"]
        if tools in ("edit", "full", "all"):
            args.append("--force")   # without it, file changes are only proposed
        if model:
            args += ["--model", model]
        return args
    raise ValueError(engine)


def wrap_prompt(system: str, prompt: str) -> str:
    """Neither CLI takes an extra system prompt on the command line, so the role goes first in the prompt."""
    return f"# Your instructions\n{system}\n\n{prompt}"


def short(path: Any) -> str:
    return Path(str(path)).name or str(path)


def codex_event(obj: dict[str, Any], out: dict[str, Any]) -> str | None:
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


def cursor_event(obj: dict[str, Any], out: dict[str, Any]) -> str | None:
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


def ollama_chat(model: str, system: str, prompt: str, on_text: Any, stopped: Any, timeout: float) -> tuple[str, str]:
    """One streamed answer from a local Ollama model. `on_text(total_so_far)` sees it grow; `stopped()` ends it early.
    Returns (text, error). Local models get the prompt only: no tools, files or web."""
    if not model:
        tags = ollama_tags() or []
        if not tags:
            return "", "Ollama has no model downloaded. Click Get a model in Agent engines, then try again."
        model = tags[0]["name"]
    body = json.dumps({"model": model, "stream": True, "options": {"num_ctx": 16384},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    text = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                if stopped():
                    return "".join(text), "Stopped"
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("error"):
                    return "".join(text), str(obj["error"])
                piece = (obj.get("message") or {}).get("content") or ""
                if piece:
                    text.append(piece)
                    on_text("".join(text))
                if obj.get("done"):
                    break
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        return "", f"Ollama couldn't run {model}: {detail[:200] or exc.reason}"
    except (OSError, urllib.error.URLError) as exc:
        return "".join(text), f"Couldn't reach Ollama at {OLLAMA_URL}. Is it running? ({exc})"
    return "".join(text).strip(), ""


def friendly_error(engine: str, text: str | None) -> str | None:
    """Plain words for the errors people actually hit."""
    low = (text or "").lower()
    if "usage limit" in low or "rate limit" in low or "quota" in low:
        return f"Your {LABELS[engine]} plan has hit its usage limit, so this agent couldn't run."
    if "not logged in" in low or "login" in low and "required" in low or "unauthorized" in low:
        return f"{LABELS[engine]} isn't signed in. Run `{'codex login' if engine == 'codex' else 'cursor-agent login'}` once, then try again."
    if engine == "ollama" and "not found" in low:
        return f"That model isn't downloaded in Ollama. {text}"
    return text
