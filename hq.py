"""Lithnode: Flows (teams of Claude Code agents you draw and run) and the Office (live sessions), in one window.

    python hq.py              # opens the app window
    python hq.py --no-open    # just run the server

Everything is served on localhost only.
  Flows   node pipelines of Claude Code agents (flows.py, agents.py)
  Office  every open Claude Code session and every flow agent at a desk (office_feed.py)
  Bots    the built-in teams and your own, used as starting points in Flows
Lithnode runs only on Claude Code and your Claude sign-in: there are no API keys. Your sign-in never
reaches the page. Bots live in ~/.clawd-bot; flows and runs live in ~/.lithnode.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest

import claude_code
import flows
import office_feed

HOST, PORT = "127.0.0.1", int(os.environ.get("LITHNODE_PORT", 8790))
URL = f"http://{HOST}:{PORT}"
STATIC = Path(__file__).with_name("static")
PAGES = {"/": "shell.html", "/flows": "flows.html", "/office": "office.html"}
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".html": "text/html; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}
_home = Path.home() / ".lithnode"
for _old_home in (Path.home() / ".relay", Path.home() / ".clawd-hq"):   # the app used to be Relay, and Clawd HQ before
    if not os.environ.get("LITHNODE_HOME") and _old_home.is_dir() and not _home.exists():
        try:
            _old_home.rename(_home)      # keep your flows and runs
        except OSError:
            pass
HQ_STORE = flows.Store(os.environ.get("LITHNODE_HOME") or _home)
RUNNER = flows.Runner(HQ_STORE)


def _backfill_tasks():
    """Flows saved before the Run menu remembered tasks open with their newest run's task."""
    latest = {}
    for r in HQ_STORE.list_runs(limit=5000):   # newest first
        if r.get("flow_id") and r.get("task"):
            latest.setdefault(r["flow_id"], r["task"])
    for f in HQ_STORE.list_flows():
        flow = HQ_STORE.get_flow(f["id"])
        if flow and "task" not in flow and flow["id"] in latest:
            flow["task"] = latest[flow["id"]][:4000]
            HQ_STORE.save_flow(flow)


# Flow clusters made from a built-in bot use its hidden role at run time.
RUNNER.bot_roles = lambda: {b["id"]: b["instructions"] for b in load_bots() if b.get("builtin")}
FLOW_ID_RE = re.compile(r"^[0-9a-f]{12}$")
STORE = Path(os.environ.get("CLAWD_BOT_HOME") or Path.home() / ".clawd-bot")

MODELS = [
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "blurb": "Most capable everyday model"},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "blurb": "Fast and capable"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "blurb": "Deepest reasoning, slower"},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5", "blurb": "Fastest and cheapest"},
]

PERSONA = (
    "You are Claude, an all-round assistant. Be direct and concise: answer first, "
    "explain after. Be warm, with a little dry humor when it fits, and never preachy. Say plainly "
    "when you're unsure or don't know. Use markdown, with code blocks for code. When you used web "
    "search, ground your claims in what you found."
)

# ------------------------------------------------------------------------ bots
BOTS = STORE / "bots.json"
SHAPES = flows.SHAPES   # the pixel shapes the pages can draw
BOT_ID_RE = re.compile(r"^[a-z0-9-]{1,32}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

STARTER_BOTS = [
    {"id": "clawd", "name": "Claude", "tagline": "All-rounder", "shape": "crab", "color": "#D97757",
     "instructions": PERSONA, "model": "", "web_search": True, "think": False,
     "starters": ["What's in the news today?", "Explain how async/await works, with a short example.",
                  "Brainstorm five side projects I could build with LLMs."]},
    {"id": "scout", "name": "Scout", "tagline": "Researcher that cites its sources", "shape": "scout", "color": "#2fb5a0",
     "instructions": (
         "You are Scout, a research analyst. For anything that could have changed recently, search first, "
         "then answer. Lead with a three-line summary, then the details. Keep facts and your own inference "
         "clearly apart, name your sources inline, and say how confident you are. If sources disagree, show "
         "both sides. Keep it tight: no filler, no hype."),
     "model": "claude-opus-5-5", "web_search": True, "think": True,
     "starters": ["Brief me on the biggest AI news this week.", "Compare the top three options for local LLMs.",
                  "What changed in the latest Python release?"]},
    {"id": "byte", "name": "Byte", "tagline": "Senior engineer for code and debugging", "shape": "byte", "color": "#5b8def",
     "instructions": (
         "You are Byte, a senior software engineer pairing with a developer. Give working code first and "
         "keep explanations short. Ask a question only when you're truly blocked; otherwise state your "
         "assumption and go. Point out bugs, edge cases and tradeoffs you notice. Prefer small, readable "
         "solutions and match the user's language and style. Put all code in fenced blocks."),
     "model": "claude-opus-5-5", "web_search": False, "think": True,
     "starters": ["Review this function for bugs and edge cases.", "Write a Python script that renames files by date.",
                  "Explain this stack trace and how to fix it."]},
    {"id": "muse", "name": "Muse", "tagline": "Writing partner and idea generator", "shape": "muse", "color": "#a77be6",
     "instructions": (
         "You are Muse, a creative writing partner. Offer several distinct options instead of one safe "
         "answer. Use vivid, specific language and a real voice, never corporate filler. When a request is "
         "vague, make a bold choice and ask at most one clarifying question at the end. Match the tone the "
         "user wants, whether that's funny, warm or sharp."),
     "model": "claude-sonnet-5-5", "web_search": False, "think": False,
     "starters": ["Give me ten name ideas for a pixel-art crab mascot.", "Help me write a short, friendly message declining a meeting.",
                  "Write a punchy two-line product tagline for a local-first chat app."]},
]

# Bots made for Flows teams. They're added once to existing bot lists too (see load_bots).
TEAM_BOTS = [
    {"id": "forge", "name": "Forge", "tagline": "Builder that writes the code", "shape": "golem", "color": "#e0823d",
     "instructions": (
         "You are Forge, a builder. Implement the requested change in this codebase with focused, readable edits "
         "that match the existing style. Don't refactor unrelated code. When you're done, list exactly which files "
         "you changed and why."),
     "model": "claude-opus-5-5", "web_search": False, "think": True, "tools": "edit", "team": True,
     "starters": ["Add a settings page with a dark mode toggle.", "Fix the failing test in this project.",
                  "Add input validation to the signup form."]},
    {"id": "beetle", "name": "Beetle", "tagline": "Bug hunter", "shape": "bug", "color": "#6cc070",
     "instructions": (
         "You are Beetle, a bug hunter. Read the code and find real bugs: logic errors, edge cases, off-by-ones, "
         "unhandled errors, race conditions. For each one give the file and line, what goes wrong, and a fix. "
         "Skip style nits. Don't edit files."),
     "model": "claude-sonnet-5-5", "web_search": False, "think": True, "tools": "read", "team": True,
     "starters": ["Find bugs in this function.", "What could break here under load?", "Review my last change for bugs."]},
    {"id": "sentinel", "name": "Sentinel", "tagline": "Security reviewer", "shape": "guard", "color": "#e5566e",
     "instructions": (
         "You are Sentinel, a security reviewer. Look for injection, broken auth or access control, secrets in "
         "code, unsafe input handling, path traversal, unsafe deserialization and risky dependencies. Rate each "
         "finding critical, high, medium or low, with the file and line and a fix. Don't edit files."),
     "model": "claude-sonnet-5-5", "web_search": False, "think": True, "tools": "read", "team": True,
     "starters": ["Security-review this endpoint.", "Is this safe to expose to the internet?", "Check this code for secrets."]},
    {"id": "probe", "name": "Probe", "tagline": "Tester that runs the code", "shape": "scout", "color": "#e0af68",
     "instructions": (
         "You are Probe, a tester. Run the project's tests, write missing tests for the change, and try the "
         "edge cases. Report exactly what you ran and what happened. Never claim something works without "
         "running it."),
     "model": "claude-sonnet-5-5", "web_search": False, "think": False, "tools": "full", "team": True,
     "starters": ["Write tests for this function.", "Run the tests and explain any failures.", "What edge cases are untested?"]},
    {"id": "atlas", "name": "Atlas", "tagline": "Planner that breaks work down", "shape": "owl", "color": "#7aa2f7",
     "instructions": (
         "You are Atlas, a planner. Turn a goal into a short, concrete plan: the steps in order, the files each "
         "step touches, the risks, and how we'll know it's done. Keep it tight. Don't write the code."),
     "model": "claude-opus-5-5", "web_search": False, "think": True, "tools": "read", "team": True,
     "starters": ["Plan how to add user accounts.", "Break this feature into steps.", "What's the riskiest part of this change?"]},
    {"id": "launch", "name": "Launch", "tagline": "Ship-ready check", "shape": "rocket", "color": "#bb9af7",
     "instructions": (
         "You are Launch. Judge whether this is ready to ship: error handling, logging, config, performance hot "
         "spots, docs, and anything that breaks on a clean machine. End with a clear ship or don't ship, and the "
         "must-fix list."),
     "model": "claude-sonnet-5-5", "web_search": False, "think": False, "tools": "read", "team": True,
     "starters": ["Is this ready to ship?", "What would break on a fresh install?", "Give me a pre-release checklist."]},
]
# Tool levels the original bots get in Flows.
STARTER_FLOW_TOOLS = {"clawd": ("read", True), "scout": ("research", True), "byte": ("edit", True),
                      "muse": ("none", True)}
STARTER_BOTS += TEAM_BOTS
for _b in STARTER_BOTS:
    _b.setdefault("tools", STARTER_FLOW_TOOLS.get(_b["id"], ("read", True))[0])
    _b.setdefault("team", STARTER_FLOW_TOOLS.get(_b["id"], ("read", True))[1])


# Built-in bots are locked: you can rename them and pick their model, nothing else. Their
# instructions come from this file every time (so updates ship), and never go to the page.
BUILTIN = {b["id"]: b for b in STARTER_BOTS}
BUILTIN_EDITABLE = ("name", "model")
OLD_DEFAULT_NAMES = {"clawd": ("Clawd", "Ace")}   # renamed built-ins: an old default name means "never renamed"


def load_bots():
    """All bots, built-ins first. Built-ins always exist and always use their own settings."""
    try:
        saved = json.loads(BOTS.read_text(encoding="utf-8")).get("bots")
        saved = [b for b in saved if isinstance(b, dict) and b.get("id")] if isinstance(saved, list) else []
    except (OSError, ValueError):
        saved = []
    mine = {b["id"]: b for b in saved}
    for bid, old in OLD_DEFAULT_NAMES.items():
        if mine.get(bid, {}).get("name") in old:
            mine[bid] = {**mine[bid], "name": BUILTIN[bid]["name"]}
    bots = [{**base, **{k: mine[bid][k] for k in BUILTIN_EDITABLE if mine.get(bid, {}).get(k) is not None},
             "builtin": True} for bid, base in BUILTIN.items()]
    bots += [{**b, "builtin": False} for b in saved if b["id"] not in BUILTIN]
    if [b["id"] for b in saved] != [b["id"] for b in bots] or any(
            b.get("id") in OLD_DEFAULT_NAMES and b.get("name") in OLD_DEFAULT_NAMES[b["id"]] for b in saved):
        save_bots(bots)   # first run, or a built-in was missing: write the full list once
    return bots


def public_bot(bot):
    """What the page may see: a built-in bot's instructions stay on the server."""
    return {**bot, "instructions": ""} if bot.get("builtin") else bot


def save_bots(bots):
    STORE.mkdir(parents=True, exist_ok=True)
    tmp = BOTS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"bots": bots}, indent=2), encoding="utf-8")
    tmp.replace(BOTS)


def clean_bot(bot_id, raw):
    """A validated bot dict from page input; raises ValueError with a readable reason."""
    def text(key, limit, required=False):
        value = str(raw.get(key) or "").strip()
        if required and not value:
            raise ValueError(f"{key} is required")
        return value[:limit]

    if raw.get("shape") not in SHAPES:
        raise ValueError("unknown shape")
    if not COLOR_RE.match(str(raw.get("color") or "")):
        raise ValueError("color must look like #rrggbb")
    starters = [str(s).strip()[:200] for s in (raw.get("starters") or []) if str(s).strip()][:4]
    return {
        "id": bot_id, "name": text("name", 30, required=True), "tagline": text("tagline", 80),
        "shape": raw["shape"], "color": raw["color"], "instructions": text("instructions", 8000),
        "model": text("model", 60), "web_search": bool(raw.get("web_search")),
        "think": bool(raw.get("think")), "starters": starters,
        # Flows only: the tool level a cluster made from this bot starts with, and whether it's offered there
        "tools": raw.get("tools") if raw.get("tools") in flows.agents.TOOLSETS else "read",
        "team": raw.get("team") is not False,
    }


# --------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Lithnode/1.0"

    # -- plumbing ----------------------------------------------------------
    def log_message(self, *args):
        pass

    def trusted(self):
        """Only talk to our own page: blocks other sites and DNS-rebinding tricks."""
        if self.headers.get("Host", "") not in (f"{HOST}:{PORT}", f"localhost:{PORT}"):
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}")

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        return json.loads(self.raw_body or b"{}")

    def route(self, method):
        # Always consume the request body, even for routes that ignore it: on a
        # keep-alive connection, unread bytes would corrupt the next request.
        length = int(self.headers.get("Content-Length") or 0)
        if length > 5_000_000:
            self.close_connection = True
            return self.send_json({"error": "body too large"}, 413)
        self.raw_body = self.rfile.read(length) if length else b""
        if not self.trusted():
            return self.send_json({"error": "forbidden"}, 403)
        path = self.path.split("?")[0]
        try:
            if method == "GET" and (path in PAGES or path.startswith("/static/")):
                return self.send_static(PAGES.get(path) or path[len("/static/"):])
            handler = getattr(self, f"{method}_{'_'.join(p for p in path.split('/') if p).replace('-', '_') or 'index'}", None)
            if handler:
                return handler()
            if path.startswith("/api/flows/"):
                return self.flow_item(method, path.split("/")[3:])
            if path.startswith("/api/runs/"):
                return self.run_item(method, path.split("/")[3:])
            if path.startswith("/api/bots/"):
                return self.bot_item(method, path.rsplit("/", 1)[1])
            self.send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # keep the server alive; tell the page
            try:
                self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            except OSError:
                pass

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    # -- pages and settings --------------------------------------------------
    def send_static(self, name):
        path = (STATIC / name).resolve()
        if path.parent != STATIC.resolve() or path.suffix not in STATIC_TYPES or not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES[path.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def GET_api_ping(self):
        self.send_json({"app": "lithnode"})

    def GET_api_connectors(self):
        """Connectors a team can be given (a free check, cached; ?refresh=1 checks again)."""
        info = claude_code.list_connectors(force="refresh=1" in self.path)
        self.send_json({k: info[k] for k in ("ok", "connectors", "error")})

    def GET_api_clis(self):
        """Command-line tools installed on this computer that a team can be allowed to run."""
        self.send_json({"clis": claude_code.list_clis()})

    # -- office ----------------------------------------------------------------
    def GET_api_sessions(self):
        self.send_json(office_feed.snapshot(RUNNER))

    def GET_api_hq(self):
        """Little numbers for the tab badges."""
        active = RUNNER.active()
        waiting = sum(1 for r in active for st in r.nodes.values() if st["status"] == "approval")
        working = sum(1 for r in active for st in r.nodes.values() for a in st["agents"] if a["status"] == "running")
        self.send_json({"runs": len(active), "approvals": waiting, "agents": working,
                        "claude_code": claude_code.auth_status()})

    # -- flows -------------------------------------------------------------------
    def flow_payload(self, flow):
        return {"flow": flow, "estimate": flows.estimate(flow), "problems": flows.check_runnable(flow)}

    def GET_api_flows(self):
        self.send_json({"flows": HQ_STORE.list_flows(),
                        "templates": [{"id": t["id"], "name": t["name"], "blurb": t["blurb"]} for t in flows.TEMPLATES],
                        "models": MODELS, "tools": list(flows.agents.TOOLSETS), "shapes": list(flows.SHAPES),
                        "max_agents": flows.MAX_AGENTS})

    def POST_api_flows(self):
        body = self.read_json()
        flow = flows.from_template(body["template"]) if body.get("template") else None
        if body.get("template") and not flow:
            return self.send_json({"error": "unknown template"}, 400)
        if not flow:
            flow = {"id": uuid.uuid4().hex[:12], "name": "New flow", "folder": "", "edges": [], "dir": "lr",
                    "nodes": [{"id": "master", "type": "master", "x": 60, "y": 220, "name": "Start"},
                              {"id": "done", "type": "done", "x": 600, "y": 220, "name": "Complete"}]}
        flow = {**flows.clean_flow(flow), "id": flow["id"]}
        HQ_STORE.save_flow(flow)
        self.send_json(self.flow_payload(flow))

    def POST_api_flows_design(self):
        """Describe a team in words; one agent drafts the flow, which is saved as a new flow."""
        prompt = str(self.read_json().get("prompt") or "").strip()[:4000]
        if not prompt:
            return self.send_json({"error": "Describe the team you want first."}, 400)
        bots = [public_bot(b) for b in load_bots()]
        agent = flows.agents.Agent(model=flows.DESIGNER_MODEL, effort="low", tools="none",
                                   system=flows.designer_system(bots, MODELS), prompt=prompt,
                                   cwd=HQ_STORE.work_dir / "_designer", on_update=lambda: None)
        if not agent.run():
            return self.send_json({"error": agent.error or "The designer failed."}, 502)
        try:
            flow = flows.build_design(flows.parse_design(agent.text), bots)
        except (ValueError, TypeError, KeyError) as exc:
            return self.send_json({"error": str(exc)}, 422)
        flow["id"] = uuid.uuid4().hex[:12]
        flow["task"] = prompt   # the Run menu opens with what you asked for
        HQ_STORE.save_flow(flow)
        self.send_json({**self.flow_payload(flow), "cost": round(agent.cost, 4)})

    def flow_item(self, method, parts):
        if not parts or not FLOW_ID_RE.match(parts[0]):
            return self.send_json({"error": "bad id"}, 400)
        flow_id, action = parts[0], (parts[1] if len(parts) > 1 else "")
        if method == "DELETE" and not action:
            HQ_STORE.delete_flow(flow_id)
            return self.send_json({"ok": True})
        if method == "POST" and not action:
            try:
                flow = {**flows.clean_flow(self.read_json()), "id": flow_id}
            except (ValueError, TypeError) as exc:
                return self.send_json({"error": str(exc)}, 400)
            HQ_STORE.save_flow(flow)
            return self.send_json(self.flow_payload(flow))
        flow = HQ_STORE.get_flow(flow_id)
        if not flow:
            return self.send_json({"error": "not found"}, 404)
        try:   # a hand-edited or copied-in file gets the same checks as page input
            flow = {**flows.clean_flow(flow), "id": flow_id}
        except (ValueError, TypeError) as exc:
            return self.send_json({"error": f"This flow's file is damaged: {exc}"}, 400)
        if method == "GET" and not action:
            return self.send_json(self.flow_payload(flow))
        if method == "POST" and action == "run":
            body = self.read_json()
            task = str(body.get("task") or "").strip()
            if not task:
                return self.send_json({"error": "Type a task for the flow."}, 400)
            problems = flows.check_runnable(flow)
            if problems:
                return self.send_json({"error": " ".join(problems)}, 400)
            folder = str(body.get("folder") or flow.get("folder") or "").strip().strip('"')
            if folder and not Path(folder).is_dir():
                return self.send_json({"error": f"That folder doesn't exist: {folder}"}, 400)
            if folder != flow.get("folder", "") or task[:4000] != flow.get("task", ""):
                flow["folder"], flow["task"] = folder, task[:4000]   # the next run starts from this one
                HQ_STORE.save_flow(flow)
            run = RUNNER.start(flow, task[:20000], folder)
            return self.send_json({"run": run.id})
        self.send_json({"error": "not found"}, 404)

    # -- folders ------------------------------------------------------------------
    def POST_api_pick_folder(self):
        """Open the normal Windows folder dialog on this computer and return the folder picked ("" if cancelled)."""
        if os.environ.get("LITHNODE_PICKER"):            # tests: a fixed answer instead of a window
            return self.send_json({"folder": os.environ["LITHNODE_PICKER"]})
        script = ("import tkinter as tk; from tkinter import filedialog; r = tk.Tk(); r.withdraw(); "
                  "r.attributes('-topmost', True); print(filedialog.askdirectory(title='Pick the folder your agents work in') or '')")
        command = ([str(Path(sys.executable).with_name("lithnode-cli.exe")), "pick-folder"]   # the installed app
                   if getattr(sys, "frozen", False) else [sys.executable, "-c", script])
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=600, creationflags=claude_code.NO_WINDOW)
            folder = str(Path(done.stdout.strip())) if done.stdout.strip() else ""
        except (OSError, subprocess.TimeoutExpired):
            folder = ""
        self.send_json({"folder": folder})

    def GET_api_folders(self):
        """Folders you've run flows in, newest first, for the folder box's suggestions."""
        seen, out = set(), []
        for r in HQ_STORE.list_runs(limit=200):
            rec = HQ_STORE.get_run(r["id"]) or {}
            folder = rec.get("folder") or ""
            if folder and folder.lower() not in seen and Path(folder).is_dir() and "workspaces" not in Path(folder).parts:
                seen.add(folder.lower())
                out.append(folder)
        self.send_json({"folders": out[:10]})

    # -- runs ---------------------------------------------------------------------
    def GET_api_runs(self):
        self.send_json({"runs": HQ_STORE.list_runs()})

    def run_item(self, method, parts):
        if not parts or not FLOW_ID_RE.match(parts[0]):
            return self.send_json({"error": "bad id"}, 400)
        run_id, action = parts[0], (parts[1] if len(parts) > 1 else "")
        if method == "GET" and not action:
            snap = RUNNER.snapshot(run_id)
            return self.send_json(snap) if snap else self.send_json({"error": "not found"}, 404)
        run = RUNNER.get(run_id)
        if not run:
            return self.send_json({"error": "That run isn't active."}, 404)
        if method == "POST" and action == "stop":
            run.stop()
            return self.send_json({"ok": True})
        if method == "POST" and action == "decide":
            body = self.read_json()
            ok = run.decide(str(body.get("node") or ""), bool(body.get("approved")), str(body.get("note") or ""))
            return self.send_json({"ok": ok}) if ok else self.send_json({"error": "Nothing is waiting there."}, 400)
        self.send_json({"error": "not found"}, 404)

    # -- bots ----------------------------------------------------------------
    def GET_api_bots(self):
        self.send_json({"bots": [public_bot(b) for b in load_bots()], "shapes": list(SHAPES)})

    def POST_api_bots(self):
        self.send_json({"id": "bot-" + uuid.uuid4().hex[:10]})

    def bot_item(self, method, bot_id):
        if not BOT_ID_RE.match(bot_id):
            return self.send_json({"error": "bad id"}, 400)
        bots = load_bots()
        if method == "DELETE":
            if bot_id in BUILTIN:
                return self.send_json({"error": "Built-in bots can't be deleted. You can rename them."}, 400)
            save_bots([b for b in bots if b["id"] != bot_id])
            return self.send_json({"ok": True})
        raw = self.read_json()
        if bot_id in BUILTIN:   # only the name and model change; everything else stays built in
            name = str(raw.get("name") or "").strip()[:30]
            if not name:
                return self.send_json({"error": "name is required"}, 400)
            model = str(raw.get("model") or "").strip()[:60]
            bot = {**BUILTIN[bot_id], "name": name, "model": model, "builtin": True}
        else:
            try:
                bot = {**clean_bot(bot_id, raw), "builtin": False}
            except ValueError as exc:
                return self.send_json({"error": str(exc)}, 400)
        save_bots([bot if b["id"] == bot_id else b for b in bots] if any(b["id"] == bot_id for b in bots) else bots + [bot])
        self.send_json({"ok": True, "bot": public_bot(bot)})

    def POST_api_signin(self):
        """Start Claude Code's sign-in. The user completes it in the window and browser it opens."""
        if claude_code.start_login():
            return self.send_json({"ok": True})
        self.send_json({"ok": False, "error": "Claude Code isn't installed on this computer."})

    def POST_api_quit(self):
        self.send_json({"ok": True})
        threading.Timer(0.3, self.server.shutdown).start()


# ---------------------------------------------------------------------- launch

def app_window_command():
    """Edge or Chrome in app mode (no tabs or address bar), like a desktop program."""
    candidates = [shutil.which("msedge"), shutil.which("chrome")]
    for root in filter(None, (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                              os.environ.get("LOCALAPPDATA"))):
        candidates += [
            Path(root) / "Microsoft/Edge/Application/msedge.exe",
            Path(root) / "Google/Chrome/Application/chrome.exe",
        ]
    for path in candidates:
        if path and Path(path).exists():
            # A dark window frame, so the title bar isn't a white strip over the dark app (page colors are
            # unaffected). Its own small browser profile makes that stick even when Edge is already open,
            # and keeps it apart from your normal browsing.
            return [str(path), f"--app={URL}", "--window-size=1440,900", "--force-dark-mode",
                    f"--user-data-dir={HQ_STORE.root / 'window'}", "--no-first-run", "--no-default-browser-check"]
    return None


def open_window():
    command = app_window_command()
    if command:
        subprocess.Popen(command)
    else:
        webbrowser.open(URL)


def already_running():
    try:
        with urlrequest.urlopen(URL + "/api/ping", timeout=1.5) as resp:
            return json.loads(resp.read()).get("app") == "lithnode"
    except (OSError, ValueError):
        return False


def main():
    if already_running():
        if "--no-open" not in sys.argv:
            open_window()
        return
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    # Only now does this process own the port: touching runs and flows any earlier could clobber a live server's.
    RUNNER.mark_interrupted()
    try:
        _backfill_tasks()
    except (OSError, ValueError, KeyError):
        pass
    if "--no-open" not in sys.argv:
        open_window()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        RUNNER.stop_all()   # Quit and Ctrl+C: no agent keeps running (and spending) after the app is gone


if __name__ == "__main__":
    main()
