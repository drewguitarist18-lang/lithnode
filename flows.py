"""Flows: node pipelines of Claude Code agents.

A flow is a graph you draw in the Flows tab:

    master  -> takes your task and writes a brief that every later agent sees
    cluster -> N agents with one job, model, effort and tool level
    checkpoint -> waits for everything before it, then passes on (or summarizes) the reports
    approval -> pauses the run until you approve it (and can ping a webhook)
    done    -> collects the final reports

Every node waits for all of its inputs, so stages run in order and parallel branches run
side by side. Only short reports travel between stages, which keeps later prompts small.
"""
import json
import math
import re
import threading
import time
import uuid
from datetime import date
from pathlib import Path
from urllib import request as urlrequest
from urllib.parse import urlparse

import agents
import claude_code
import engines

NODE_TYPES = ("master", "cluster", "checkpoint", "approval", "done")
DEFAULT_NAMES = {"master": "Start", "cluster": "Team", "checkpoint": "Checkpoint", "approval": "Approval", "done": "Done"}
SHAPES = ("crab", "scout", "byte", "muse", "golem", "bug", "guard", "owl", "rocket")
ID_RE = re.compile(r"^[a-z0-9-]{1,40}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._\[\]-]{1,60}$")   # model names go on the claude command line
MAX_AGENTS = 15
REPORT_LIMIT = 6000       # characters of each agent's report handed to the next stage
DEFAULT_MODEL = "claude-sonnet-5-5"
SUMMARY_MODEL = "claude-haiku-4-5"

# How heavy each model is relative to Haiku, for the pre-run estimate only. Real costs come
# from Claude Code's own `total_cost_usd` once agents finish.
MODEL_WEIGHT = {"claude-haiku-4-5": 1, "claude-sonnet-5-5": 3, "claude-opus-5-5": 5, "claude-fable-5-1": 8}


class Store:
    """Flows and run records on disk, under one folder (default ~/.lithnode)."""

    def __init__(self, root):
        self.root = Path(root)
        self.flows_dir = self.root / "flows"
        self.runs_dir = self.root / "runs"
        self.work_dir = self.root / "workspaces"
        self._lock = threading.Lock()

    def _write(self, path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
        for attempt in range(10):
            try:
                tmp.replace(path)
                return
            except PermissionError:      # a reader may hold the file for a moment on Windows
                if attempt == 9:
                    tmp.unlink(missing_ok=True)
                    raise                # don't pretend it saved
                time.sleep(0.02 * (attempt + 1))

    # flows
    def list_flows(self):
        out = []
        for path in self.flows_dir.glob("*.json") if self.flows_dir.exists() else []:
            try:
                f = json.loads(path.read_text(encoding="utf-8"))
                out.append({"id": f["id"], "name": f.get("name", "Flow"), "updated": f.get("updated", 0),
                            "nodes": len(f.get("nodes", []))})
            except (OSError, ValueError, KeyError):
                continue
        out.sort(key=lambda f: f["updated"], reverse=True)
        return out

    def get_flow(self, flow_id):
        try:
            return json.loads((self.flows_dir / f"{flow_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_flow(self, flow):
        flow["updated"] = time.time()
        self._write(self.flows_dir / f"{flow['id']}.json", flow)

    def delete_flow(self, flow_id):
        (self.flows_dir / f"{flow_id}.json").unlink(missing_ok=True)

    # runs
    def save_run(self, record):
        self._write(self.runs_dir / f"{record['id']}.json", record)

    def get_run(self, run_id):
        try:
            return json.loads((self.runs_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_runs(self, limit=40):
        items = []
        for path in self.runs_dir.glob("*.json") if self.runs_dir.exists() else []:
            try:
                r = json.loads(path.read_text(encoding="utf-8"))
                row = {k: r.get(k) for k in ("id", "flow_id", "flow_name", "task", "status", "started", "ended", "cost")}
                # the run's latest list of items, counted: what the history shows ("3 passed · 3 cut")
                lists = sorted((st for st in (r.get("nodes") or {}).values() if st.get("items")), key=lambda st: st.get("ended") or 0)
                if lists:
                    its = lists[-1]["items"]
                    row["items"] = {"total": len(its), "pass": sum(i.get("verdict") == "pass" for i in its),
                                    "cut": sum(i.get("verdict") == "cut" for i in its)}
                items.append(row)
            except (OSError, ValueError):
                continue
        items.sort(key=lambda r: r["started"] or 0, reverse=True)
        return items[:limit]


# --------------------------------------------------------------- validation

def _text(raw, key, limit, default=""):
    return str(raw.get(key) if raw.get(key) is not None else default).strip()[:limit]


def _connectors(raw):
    """A team's connectors: server names like "claude.ai Vercel", as Claude Code lists them."""
    out = []
    for c in raw if isinstance(raw, list) else []:
        c = str(c).strip()[:80]
        if c and c not in out and not any(ch in c for ch in "\r\n,\"*"):
            out.append(c)
    return out[:10]


def _clis(raw):
    """A team's command-line tools: plain command names like "gh" or "vercel"."""
    out = []
    for c in raw if isinstance(raw, list) else []:
        c = str(c).strip()
        if claude_code.CLI_RE.match(c) and c not in out:
            out.append(c)
    return out[:12]


def _model(raw, default):
    model = _text(raw, "model", 60, default)
    return model if MODEL_RE.match(model) else default


def _coord(raw, key):
    value = float(raw.get(key) or 0)
    return value if math.isfinite(value) else 0.0


def webhook_ok(url):
    """An http(s) URL with a host: the only kind of webhook Lithnode will call."""
    try:
        parts = urlparse(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not any(ch.isspace() for ch in url)


def clean_node(raw):
    if not isinstance(raw, dict):
        raise ValueError("bad node")
    kind = raw.get("type")
    if kind not in NODE_TYPES:
        raise ValueError(f"unknown node type: {kind}")
    nid = str(raw.get("id") or "")
    if not ID_RE.match(nid):
        raise ValueError("bad node id")
    node = {"id": nid, "type": kind, "x": _coord(raw, "x"), "y": _coord(raw, "y"),
            "name": _text(raw, "name", 40, DEFAULT_NAMES[kind]) or DEFAULT_NAMES[kind]}
    if kind == "master" and node["name"] in ("Lead", "Task in"):   # the block used to be called Lead
        node["name"] = "Start"
    if kind in ("master", "cluster"):
        tools = raw.get("tools") if raw.get("tools") in agents.TOOLSETS else "read"
        effort = raw.get("effort") if raw.get("effort") in agents.EFFORTS else "low"
        node.update(model=_model(raw, DEFAULT_MODEL), tools=tools, effort=effort,
                    instructions=_text(raw, "instructions", 8000),
                    max_turns=max(0, min(200, int(raw.get("max_turns") or 0))))
    if kind == "master":
        node["mode"] = raw.get("mode") if raw.get("mode") in ("brief", "pass") else "brief"
    if kind == "cluster":
        try:
            count = int(raw.get("count") or 1)
        except (TypeError, ValueError):
            count = 1
        node.update(count=max(1, min(MAX_AGENTS, count)),
                    summary=_text(raw, "summary", 80),   # the one line on the team's card
                    focuses=_text(raw, "focuses", 2000),
                    shape=raw.get("shape") if raw.get("shape") in SHAPES else "crab",
                    color=raw.get("color") if COLOR_RE.match(str(raw.get("color") or "")) else "#D97757",
                    bot=_text(raw, "bot", 40),
                    connectors=_connectors(raw.get("connectors")), clis=_clis(raw.get("clis")),
                    split=raw.get("split") is True,
                    engine=raw.get("engine") if raw.get("engine") in engines.ENGINES else "claude",
                    engine_model=_text(raw, "engine_model", 60) if MODEL_RE.match(_text(raw, "engine_model", 60)) else "")
    if kind == "checkpoint":
        node.update(mode=raw.get("mode") if raw.get("mode") in ("pass", "summarize") else "pass",
                    model=_model(raw, SUMMARY_MODEL),
                    on_error=raw.get("on_error") if raw.get("on_error") in ("stop", "continue") else "stop")
    if kind == "approval":
        hook = _text(raw, "webhook", 500)
        if hook and not webhook_ok(hook):
            raise ValueError("webhook must be an http(s) URL")
        node.update(message=_text(raw, "message", 500), webhook=hook)
    return node


def clean_flow(raw):
    """A validated flow dict from page input or disk; raises ValueError with a readable reason."""
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes") or [], list) or not isinstance(raw.get("edges") or [], list):
        raise ValueError("bad flow")
    nodes = [clean_node(n) for n in (raw.get("nodes") or [])][:80]
    ids = [n["id"] for n in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate node ids")
    edges, seen = [], set()
    for e in raw.get("edges") or []:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("from")), str(e.get("to"))
        if a in ids and b in ids and a != b and (a, b) not in seen:
            seen.add((a, b))
            edges.append({"from": a, "to": b})
    kinds = {n["id"]: n["type"] for n in nodes}
    for e in edges:
        if kinds[e["to"]] == "master":
            raise ValueError("nothing can flow into Start")
        if kinds[e["from"]] == "done":
            raise ValueError("a done node can't feed another node")
    if _has_cycle(ids, edges):
        raise ValueError("the flow has a loop; connections must go one way")
    start = next((n["id"] for n in nodes if n["type"] == "master"), None)
    if start:
        edges += [{"from": start, "to": nid} for nid in fed_by_start({"nodes": nodes, "edges": edges})]
    return {"id": raw.get("id"), "name": _text(raw, "name", 60, "Untitled flow") or "Untitled flow",
            "folder": _text(raw, "folder", 500), "nodes": nodes, "edges": edges,
            "task": _text(raw, "task", 4000),   # what the Run menu opens with: your description, or the last task run
            "dir": raw.get("dir") if raw.get("dir") in ("tb", "lr") else "lr",
            "auto": raw.get("auto") is not False}   # auto-arrange: re-lay out the nodes on every change


def _has_cycle(ids, edges):
    out = {i: [] for i in ids}
    for e in edges:
        out[e["from"]].append(e["to"])
    state = {}

    def visit(n):
        if state.get(n) == 1:
            return True
        if state.get(n) == 2:
            return False
        state[n] = 1
        if any(visit(m) for m in out[n]):
            return True
        state[n] = 2
        return False

    return any(visit(i) for i in ids)


def fed_by_start(flow):
    """Steps with no wire coming in but wired onward (say, a planner beside Start). Saving a flow wires Start
    to them, so they get the task. Steps with no wires at all stay loose."""
    into = {e["to"] for e in flow["edges"]}
    out_of = {e["from"] for e in flow["edges"]}
    return [n["id"] for n in flow["nodes"] if n["type"] not in ("master", "done") and n["id"] not in into and n["id"] in out_of]


def check_runnable(flow):
    """Problems that stop a flow from running, as plain sentences (empty list = good to go)."""
    problems = []
    masters = [n for n in flow["nodes"] if n["type"] == "master"]
    if len(masters) != 1:
        problems.append("A flow needs exactly one Start step, where your task goes in.")
    workers = [n for n in flow["nodes"] if n["type"] == "cluster"]
    if not workers:
        problems.append("Add at least one agent cluster.")
    dones = sum(n["type"] == "done" for n in flow["nodes"])
    if dones > 1:
        problems.append("A flow has one Done step. Remove the extra one and wire everything into the other.")
    elif not dones:
        problems.append("Add a Done step at the end, so the results land somewhere.")
    if masters:
        reach, frontier = {masters[0]["id"]}, [masters[0]["id"]]
        while frontier:
            cur = frontier.pop()
            for e in flow["edges"]:
                if e["from"] == cur and e["to"] not in reach:
                    reach.add(e["to"])
                    frontier.append(e["to"])
        loose = [n["name"] for n in flow["nodes"] if n["id"] not in reach]
        if loose:
            problems.append("Not connected to Start: " + ", ".join(loose[:5]) + ".")
    return problems


def estimate(flow):
    """Sessions per model and a relative weight, before anything runs."""
    per_model = {}

    def add(model, n=1):
        per_model[model] = per_model.get(model, 0) + n

    for n in flow["nodes"]:
        if n["type"] == "master" and n.get("mode") == "brief":
            add(n["model"])
        elif n["type"] == "cluster":
            add(n["model"] if n.get("engine", "claude") == "claude" else n["engine"], n["count"])
        elif n["type"] == "checkpoint" and n.get("mode") == "summarize":
            add(n["model"])
    sessions = sum(per_model.values())
    weight = sum(MODEL_WEIGHT.get(m, 3) * c for m, c in per_model.items())
    return {"sessions": sessions, "per_model": per_model, "weight": weight}


# ----------------------------------------------------------------- items
# A team can hand back a list of things (records, parts, ideas, leads, options) as a fenced ```items block of JSON.
# The app shows them as cards; a team that judges them marks each one pass or cut with a reason.

MAX_ITEMS = 24
ITEMS_RE = re.compile(r"```items[^\S\n]*\n(.*?)```", re.S)
VERDICTS = {"pass": "pass", "keep": "pass", "yes": "pass", "approve": "pass", "approved": "pass", "ok": "pass", "listed": "pass",
            "cut": "cut", "reject": "cut", "rejected": "cut", "no": "cut", "drop": "cut", "fail": "cut", "skip": "cut"}


def _clean_url(v):
    v = str(v or "").strip()
    return v if v.startswith("https://") and len(v) <= 1000 and not re.search(r"[\s\"'<>]", v) else ""


def clean_item(raw):
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("name") or "").strip()[:120]
    if not title:
        return None
    item = {"title": title}
    for key, limit in (("subtitle", 160), ("price", 40), ("reason", 140)):
        value = raw.get(key)
        if value is not None and str(value).strip():
            item[key] = str(value).strip()[:limit]
    try:
        rating = float(raw.get("rating"))
        if 0 <= rating <= 5:
            item["rating"] = round(rating, 1)
    except (TypeError, ValueError):
        pass
    for key in ("image", "url"):
        url = _clean_url(raw.get(key))
        if url:
            item[key] = url
    facts = raw.get("facts")
    if isinstance(facts, dict):
        item["facts"] = {str(k).strip()[:30]: str(v).strip()[:60] for k, v in list(facts.items())[:10] if str(k).strip() and str(v).strip()}
    verdict = VERDICTS.get(str(raw.get("verdict") or "").strip().lower())
    if verdict:
        item["verdict"] = verdict
    return item


def parse_items(text):
    """The last ```items block in an agent's answer, cleaned; [] when there isn't one (or it isn't JSON)."""
    blocks = ITEMS_RE.findall(text or "")
    if not blocks:
        return []
    raw = blocks[-1].strip()
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("["), raw.rfind("]")
        try:
            data = json.loads(raw[start:end + 1]) if 0 <= start < end else []
        except ValueError:
            return []
    if isinstance(data, dict):
        data = data.get("items") or []
    if not isinstance(data, list):
        return []
    return [i for i in (clean_item(r) for r in data[:MAX_ITEMS]) if i]


def strip_items(text):
    return ITEMS_RE.sub("", text or "").strip()


def items_block(items):
    return "```items\n" + json.dumps(items, ensure_ascii=False) + "\n```" if items else ""


def merge_items(lists):
    """Several agents' lists as one: first seen order, later details fill gaps, and one cut is enough to cut."""
    merged, order = {}, []
    for items in lists:
        for it in items:
            key = re.sub(r"\W+", " ", it["title"].lower()).strip()
            if key not in merged:
                merged[key] = dict(it)
                order.append(key)
                continue
            cur = merged[key]
            for k, v in it.items():
                if k in ("verdict", "reason"):
                    continue
                cur.setdefault(k, v)
            if it.get("verdict") == "cut" and cur.get("verdict") != "cut":
                cur["verdict"], cur["reason"] = "cut", it.get("reason", "")
            elif it.get("verdict") == cur.get("verdict") and it.get("reason") and it.get("reason") not in cur.get("reason", ""):
                cur["reason"] = (cur.get("reason", "") + "; " + it["reason"]).strip("; ")[:140]
            elif it.get("verdict") and not cur.get("verdict"):
                cur["verdict"], cur["reason"] = it["verdict"], it.get("reason", "")
    return [merged[k] for k in order][:MAX_ITEMS]


ITEMS_NOTE = ('If your stage produces or judges a list of things (parts of a job, records, ideas, leads, options), also put the list '
              'in your REPORT as a fenced block that starts with ```items and holds a JSON array, one object per thing: '
              '{"title", "subtitle", "price", "rating" (0-5), "url", "image" (a direct https image URL, only if you found one), '
              '"facts" {"short label": "value"}, "verdict" ("pass" or "cut", only when your job is to judge them), '
              '"reason" (a few words)}. When you judge a list, return every thing you were given. At most '
              f'{MAX_ITEMS} things; the block doesn\'t count toward the word limit.')


# ----------------------------------------------------------------- templates

def _n(nid, kind, x, y, **kw):
    return {"id": nid, "type": kind, "x": x, "y": y, **kw}


TEMPLATES = [
    {"id": "ship-it", "name": "Build, review, secure, ship",
     "blurb": "A builder, then bug and security reviewers side by side, your sign-off, and a final production check.",
     "nodes": [
         _n("master", "master", 40, 200, name="Start", model="claude-sonnet-5-5", mode="pass", tools="read",
            instructions="Turn the task into a clear brief: goal, constraints, acceptance criteria, and what each stage should watch for."),
         _n("build", "cluster", 300, 200, name="Builders", summary='Build the change in your folder', count=1, model="claude-sonnet-5-5", tools="edit", effort="medium",
            shape="byte", color="#5b8def",
            instructions="You are the builder. Implement the task in this folder. Keep changes focused and readable."),
         _n("cp1", "checkpoint", 560, 200, name="Build done", mode="pass"),
         _n("bugs", "cluster", 780, 80, name="Bug reviewers", summary='Hunt bugs in the new code', count=2, model="claude-sonnet-5-5", tools="read",
            shape="bug", color="#6cc070",
            instructions=("You review the builders' changes for bugs: logic errors, edge cases, broken flows. Verify each finding "
                          "by reading the actual code, and say how confident you are. Don't edit files."),
            focuses="Logic and edge cases\nError handling and failure paths\nData flow and state"),
         _n("sec", "cluster", 780, 320, name="Security", summary='Check for security holes', count=1, model="claude-sonnet-5-5", tools="read",
            shape="guard", color="#e5566e",
            instructions=("You review the changes for security problems. Think like an attacker: injection, auth, secrets, "
                          "unsafe input, risky dependencies. Rate each finding critical, high, medium or low, with the file "
                          "and line. Don't edit files."),
            focuses="Input handling and injection\nSecrets, auth and permissions"),
         _n("cp2", "checkpoint", 1060, 200, name="Reviews merged", mode="summarize", model="claude-haiku-4-5"),
         _n("ok", "approval", 1280, 200, name="Your call", message="Reviews are in. Approve to run the production check."),
         _n("prod", "cluster", 1500, 200, name="Production check", summary="Says ship or don't ship", count=1, model="claude-sonnet-5-5", tools="read",
            shape="rocket", color="#bb9af7",
            instructions=("You give the final production-readiness verdict based on the code and the reviews: error handling, "
                          "config, performance, docs, anything that breaks on a clean machine. End with ship or don't ship.")),
         _n("done", "done", 1760, 200, name="Complete"),
     ],
     "edges": [["master", "build"], ["build", "cp1"], ["cp1", "bugs"], ["cp1", "sec"], ["bugs", "cp2"],
               ["sec", "cp2"], ["cp2", "ok"], ["ok", "prod"], ["prod", "done"]]},
    {"id": "review", "name": "Quick code review",
     "blurb": "Three cheap read-only reviewers look at a folder, one summary comes back. No edits.",
     "nodes": [
         _n("master", "master", 60, 200, name="Start", mode="pass", model="claude-haiku-4-5", tools="read"),
         _n("rev", "cluster", 320, 200, name="Reviewers", count=3, summary='Read the code for bugs and risks', model="claude-haiku-4-5", tools="read",
            shape="scout", color="#2fb5a0",
            instructions="Review the code in this folder for bugs and risky spots. Don't edit files.",
            focuses="Correctness\nSecurity\nReadability and structure"),
         _n("sum", "checkpoint", 600, 200, name="Summary", mode="summarize", model="claude-haiku-4-5"),
         _n("done", "done", 840, 200, name="Complete"),
     ],
     "edges": [["master", "rev"], ["rev", "sum"], ["sum", "done"]]},
    {"id": "batch", "name": "Split a big job",
     "blurb": "Three workers split one big job and do their parts at once, then a checker verifies every part.",
     "nodes": [
         _n("master", "master", 60, 200, name="Start", mode="pass", model="claude-haiku-4-5", tools="none"),
         _n("work", "cluster", 320, 200, name="Workers", summary='Each cleans its own part', count=3, model="claude-haiku-4-5", tools="edit", split=True,
            clis=["python"], shape="byte", color="#5b8def",
            instructions=("Do the task on your part of the input. Use a script when the job is big or repetitive, and "
                          "write your results to a file named for your part, in the format the task asks for.")),
         _n("check", "cluster", 580, 200, name="Checker", count=1, model="claude-sonnet-5-5", summary='Verifies every part, flags gaps', tools="read", clis=["python"],
            shape="bug", color="#6cc070",
            instructions=("You check the workers' output, part by part. Count the records, and look for missing, duplicate or "
                          "malformed ones and for gaps or overlaps between parts. Don't fix anything: say exactly what's "
                          "wrong and where. Return one item per part with verdict pass or cut and a short reason, like "
                          "\"33,334 rows, no gaps\" or \"412 rows missing\".")),
         _n("done", "done", 840, 200, name="Done"),
     ],
     "edges": [["master", "work"], ["work", "check"], ["check", "done"]]},
    {"id": "deploy", "name": "Build and deploy",
     "blurb": "A builder makes the change, two reviewers check it, you approve, a deployer ships it with git and Vercel.",
     "nodes": [
         _n("master", "master", 60, 200, name="Start", mode="pass", model="claude-haiku-4-5", tools="none"),
         _n("build", "cluster", 320, 200, name="Builder", summary='Makes the change', count=1, model="claude-sonnet-5-5", tools="edit", effort="medium",
            shape="byte", color="#5b8def",
            instructions="You are the builder. Make the change in this folder. Keep it focused and readable."),
         _n("rev", "cluster", 580, 200, name="Reviewers", count=2, summary='Check the diff before it ships', model="claude-haiku-4-5", tools="read", clis=["git"],
            shape="bug", color="#6cc070",
            instructions=("Review the builder's change (git diff shows it) for bugs and anything that would break in "
                          "production. Don't edit files. End with ship or don't ship."),
            focuses="Bugs and edge cases\nAnything that breaks the build or the deploy"),
         _n("ok", "approval", 840, 200, name="Ship it?", message="Reviews are in. Approve to commit and deploy."),
         _n("ship", "cluster", 1100, 200, name="Deployer", summary='Commits and deploys to Vercel', count=1, model="claude-haiku-4-5", tools="read", clis=["git", "vercel"],
            shape="rocket", color="#bb9af7",
            instructions=("Commit the change with git (a short, clear message), then deploy with `vercel deploy --prod --yes`. "
                          "Report the commit and the live URL. If a step fails, stop and say why.")),
         _n("done", "done", 1360, 200, name="Done"),
     ],
     "edges": [["master", "build"], ["build", "rev"], ["rev", "ok"], ["ok", "ship"], ["ship", "done"]]},
    {"id": "research", "name": "Research squad",
     "blurb": "Scouts search the web from different angles, then one brief comes back.",
     "nodes": [
         _n("master", "master", 60, 200, name="Start", model="claude-sonnet-5-5", mode="brief", tools="none",
            instructions="Split the question into the angles worth researching and say what a great answer contains."),
         _n("scouts", "cluster", 320, 200, name="Scouts", summary='Search the web from different angles', count=3, model="claude-sonnet-5-5", tools="web",
            shape="scout", color="#2fb5a0",
            instructions="You are a research scout. Search, read, and report facts with their sources.",
            focuses="Latest news and announcements\nExpert and critical opinions\nNumbers, benchmarks and data"),
         _n("sum", "checkpoint", 600, 200, name="Brief", mode="summarize", model="claude-sonnet-5-5"),
         _n("done", "done", 840, 200, name="Complete"),
     ],
     "edges": [["master", "scouts"], ["scouts", "sum"], ["sum", "done"]]},
]


def from_template(template_id):
    t = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not t:
        return None
    nodes = []
    for n in t["nodes"]:
        nodes.append(json.loads(json.dumps(n)))
    flow = {"id": uuid.uuid4().hex[:12], "name": t["name"], "folder": "", "nodes": nodes,
            "edges": [{"from": a, "to": b} for a, b in t["edges"]]}
    _layout(flow, "lr")
    return flow


# ------------------------------------------------------------------ designer
# Type what you want ("plan it, build it, then 3 reviewers check for bugs") and one agent drafts the flow.

DESIGNER_MODEL = "claude-sonnet-5-5"
DESIGNER_SYSTEM = """You are the flow designer for Lithnode, an app that runs teams of Claude Code agents as a node graph.
Turn the user's description into a flow. Reply with ONLY one JSON object, no prose and no code fences:
{"name": "...", "nodes": [...], "edges": [["from-id", "to-id"], ...]}

Node types:
- master: exactly one, id "master". Fields: name, mode ("brief" = an agent writes a plan everyone reads, "pass" = free,
  the task goes straight on), model, tools, instructions. Use "pass" for small flows.
- cluster: a group of agents with one role. Fields: id, name, count (1-15), model, tools, effort (low|medium|high),
  instructions (the role, in second person), summary (what the team does in plain words for its card, max 6 words,
  like "Hunts bugs in the new code"), focuses (one line per agent so they split the work),
  bot (a bot id to base it on, or ""), split (true when the agents should divide one big job into equal parts and
  work side by side, e.g. processing 100,000 rows; then add a checker team after them), clis (command-line tools the
  team may run, from: <<CLIS>>; only the ones the job needs, e.g. ["gh"] to work with GitHub issues).
- checkpoint: waits for everything wired into it. Fields: id, name, mode ("pass" or "summarize"), model.
  Use mode "summarize" with claude-haiku-4-5 after clusters with several agents, before the next stage.
- approval: pauses until the user approves. Fields: id, name, message. Add one only if the user wants to sign off,
  or before a stage that edits files based on reviews.
- done: the end. Fields: id, name.

Tools: none, read, web, research (read files + web), edit (read and edit files), full (edit files + run commands).
Models: <<MODELS>>. Every agent uses the person's plan, so spend carefully: pick the cheapest model that can do each job
(Haiku for checks, merges and simple script work; Sonnet for building, reviewing and research; Opus only when the user
asks for the strongest model), keep teams at 1-2 agents unless more angles clearly help, and use Start mode "pass".
Bots you can base a cluster on (set "bot" and reuse their role): <<BOTS>>

Rules: ids are short, lowercase, with dashes. Every node is reachable from master, and the last stage feeds a done node.
No loops. Keep it lean: 1-3 agents per cluster unless asked for more. Reviewers are read-only (tools "read").
Only builders get "edit"; only testers get "full". Prefer clis over "full" when a team only needs a few tools.
Name the flow in 2-5 words."""


def designer_system(bots, models):
    return (DESIGNER_SYSTEM
            .replace("<<MODELS>>", ", ".join(m["id"] for m in models))
            .replace("<<CLIS>>", ", ".join(c["id"] for c in claude_code.list_clis()) or "none installed")
            .replace("<<BOTS>>", "; ".join(f'{b["id"]} = {b["name"]}, {b.get("tagline", "")} (tools {b.get("tools", "read")})'
                                           for b in bots if b.get("team", True)) or "none"))


def parse_design(text):
    """The JSON object in the designer's answer (it may wrap it in a code fence anyway)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The designer didn't return a flow. Try describing it again.")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        raise ValueError("The designer's flow wasn't valid. Try again, or describe it a bit differently.")


def build_design(raw, bots):
    """Turn a designer draft into a clean, laid-out flow. Raises ValueError with a readable reason."""
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list):
        raise ValueError("The designer's flow had no nodes. Try again.")
    by_bot = {b["id"]: b for b in bots}
    nodes, rename = [], {}
    for i, n in enumerate(raw["nodes"][:40]):
        if not isinstance(n, dict) or n.get("type") not in NODE_TYPES:
            continue
        nid = "master" if n["type"] == "master" else (re.sub(r"[^a-z0-9-]+", "-", str(n.get("id") or "").lower()).strip("-")[:30] or f'{n["type"]}-{i}')
        while nid in rename.values():
            nid = f"{nid}-{i}"
        rename[str(n.get("id"))] = nid
        node = {**n, "id": nid}
        bot = by_bot.get(n.get("bot"))
        if n["type"] == "cluster" and bot:
            node.setdefault("shape", bot["shape"])
            node.setdefault("color", bot["color"])
            node["instructions"] = node.get("instructions") or bot.get("instructions", "")   # empty for built-ins
        nodes.append(node)
    if sum(n["type"] == "master" for n in nodes) != 1:
        nodes = [n for n in nodes if n["type"] != "master"]
        nodes.insert(0, {"id": "master", "type": "master", "name": "Start", "mode": "pass"})
        rename.setdefault("master", "master")
    edges = []
    for e in raw.get("edges") or []:
        a, b = (e if isinstance(e, (list, tuple)) and len(e) == 2 else (e.get("from"), e.get("to")) if isinstance(e, dict) else (None, None))
        if str(a) in rename and str(b) in rename:
            edges.append({"from": rename[str(a)], "to": rename[str(b)]})
    dones = [n["id"] for n in nodes if n["type"] == "done"]
    if len(dones) > 1:   # one Done per flow: keep the first, send everything else's wires to it
        keep = dones[0]
        nodes = [n for n in nodes if n["type"] != "done" or n["id"] == keep]
        edges = [{"from": e["from"], "to": keep if e["to"] in dones else e["to"]} for e in edges if e["from"] not in dones]
        edges = [e for i, e in enumerate(edges) if e not in edges[:i]]
    ids = {n["id"] for n in nodes}
    if not any(n["type"] == "done" for n in nodes):   # make sure the result lands somewhere
        sinks = [n["id"] for n in nodes if n["type"] != "done" and not any(e["from"] == n["id"] for e in edges)]
        nodes.append({"id": "done", "type": "done", "name": "Complete"})
        edges += [{"from": s_, "to": "done"} for s_ in sinks if s_ in ids]
    flow = clean_flow({"name": raw.get("name") or "Designed flow", "nodes": nodes, "edges": edges})
    _layout(flow)
    return flow


WRAP = 5    # columns per row before a left-to-right flow wraps onto the next row
COL_GAP, ROW_H, MAX_ROW_W = 84, 150, 2100   # gap between columns, spacing of side-by-side steps, widest row before wrapping
TEAM_W, TEAM_H, PILL_W, PILL_H = 248, 97, 120, 38   # a team is a card, every other step a pill (static/flows.html)
STACK = 3   # most nodes stacked in one column; a busier stage spreads into extra columns


def _layout(flow, direction="lr"):
    """Neat layout: stages by depth from Start, at most STACK nodes per column, rows that wrap after
    WRAP columns ("lr") or rows going down ("tb"). Nodes with no wires yet wait in a row underneath."""
    flow["dir"] = direction
    nodes, edges = flow["nodes"], flow["edges"]
    wired = {e["from"] for e in edges} | {e["to"] for e in edges}
    loose = [n for n in nodes if n["id"] not in wired and n["type"] != "master"]
    main = [n for n in nodes if n["id"] in wired or n["type"] == "master"]
    depth = {n["id"]: 0 for n in main}
    for _ in range(len(main)):                        # longest path (the graph has no loops)
        for e in edges:
            if e["from"] in depth and e["to"] in depth:
                depth[e["to"]] = max(depth[e["to"]], depth[e["from"]] + 1)
    levels = {}
    for n in main:
        levels.setdefault(depth[n["id"]], []).append(n)
    rank = {}                                         # order within a stage, so wires cross less

    def pull(n):
        ins = [rank[e["from"]] for e in edges if e["to"] == n["id"] and e["from"] in rank]
        return sum(ins) / len(ins) if ins else 0

    stacks = []                                       # one entry per column: up to STACK nodes
    for d in sorted(levels):
        level = sorted(levels[d], key=pull)
        for i, n in enumerate(level):
            rank[n["id"]] = i - (len(level) - 1) / 2
        stacks += [level[i:i + STACK] for i in range(0, len(level), STACK)]

    if direction == "tb":
        y = 40
        for stack in stacks:
            for i, n in enumerate(stack):
                n["x"], n["y"] = round(420 + (i - (len(stack) - 1) / 2) * 250), y
            y += 200
        for i, n in enumerate(loose):
            n["x"], n["y"] = 60 + (i % WRAP) * 250, y + 60 + (i // WRAP) * 170
        return
    size = lambda n: (TEAM_W, TEAM_H) if n["type"] == "cluster" else (PILL_W, PILL_H)   # noqa: E731
    col_w = lambda stack: max(size(n)[0] for n in stack)   # noqa: E731   each column as wide as what's in it
    rows, cur, width = [], [], 0
    for stack in stacks:                              # wrap onto a new row once a row gets too wide
        if cur and width + col_w(stack) > MAX_ROW_W:
            rows.append(cur)
            cur, width = [], 0
        cur.append(stack)
        width += col_w(stack) + COL_GAP
    if cur:
        rows.append(cur)
    if len(rows) > 1 and len(rows[-1]) == 1:          # never leave one step alone on a new row
        rows[-2].append(rows.pop()[0])
    top = 80
    for row in rows:
        tallest = max(len(s) for s in row)
        middle, x = top + (tallest - 1) * ROW_H / 2, 60
        for stack in row:
            cw = col_w(stack)
            for i, n in enumerate(stack):             # centered in its column and on its row
                w, h = size(n)
                n["x"] = round(x + (cw - w) / 2)
                n["y"] = round(middle + (i - (len(stack) - 1) / 2) * ROW_H - h / 2)
            x += cw + COL_GAP
        top += tallest * ROW_H + 90
    for i, n in enumerate(loose):                     # not wired yet: a row underneath
        n["x"], n["y"] = 60 + (i % WRAP) * (TEAM_W + COL_GAP), top + 40 + (i // WRAP) * 170


# --------------------------------------------------------------------- runs

TERMINAL = ("done", "failed", "stopped", "skipped")


class Run:
    """One execution of a flow. Thread-safe; `snapshot()` is what the page polls."""

    def __init__(self, store, flow, task, folder, roles=None):
        self.store = store
        self.id = uuid.uuid4().hex[:12]
        self.flow = flow
        self.task = task
        self.folder = Path(folder) if folder else store.work_dir / flow["id"]
        self.roles = roles or {}      # built-in bots' hidden instructions, by bot id
        self.status = "running"
        self.started = time.time()
        self.ended = None
        self.brief = ""
        self.log = []
        self.lock = threading.RLock()
        self.nodes = {n["id"]: {"status": "waiting", "output": "", "agents": [], "started": None,
                                "ended": None, "error": "", "note": ""} for n in flow["nodes"]}
        self.by_id = {n["id"]: n for n in flow["nodes"]}
        self.inputs = {n["id"]: [e["from"] for e in flow["edges"] if e["to"] == n["id"]] for n in flow["nodes"]}
        self.live_agents = []         # agents.Agent objects still running, for Stop
        self.threads = []             # one per started node; the run ends only after they all return
        self.approvals = {}           # node id -> threading.Event
        self.decisions = {}           # node id -> (approved, note)
        self._last_save = 0.0
        self._save_lock = threading.Lock()
        self._edit_lock = threading.Lock()   # clusters that edit files, in any branch, take turns in the folder
        self._wake = threading.Event()

    # -- bookkeeping ------------------------------------------------------------
    def say(self, text):
        with self.lock:
            self.log.append({"t": time.time(), "text": text})
            self.log = self.log[-200:]
        self.changed()

    def changed(self, force=False):
        self._wake.set()
        now = time.time()
        if force or now - self._last_save > 1.0:
            self._last_save = now
            # One save at a time, each taking its snapshot inside the lock, so an older one never lands last.
            with self._save_lock:
                try:
                    self.store.save_run(self.snapshot())
                except OSError:
                    pass

    @property
    def cost(self):
        return round(sum(a["cost"] for s in self.nodes.values() for a in s["agents"]), 4)

    def snapshot(self):
        with self.lock:
            return {
                "id": self.id, "flow_id": self.flow["id"], "flow_name": self.flow["name"], "flow": self.flow,
                "task": self.task, "folder": str(self.folder), "status": self.status, "started": self.started,
                "ended": self.ended, "cost": self.cost, "brief": self.brief, "log": list(self.log),
                "nodes": json.loads(json.dumps(self.nodes)),
                "final": self.final_output(),
            }

    def final_output(self):
        dones = [nid for nid, n in self.by_id.items() if n["type"] == "done"]
        parts = [self.nodes[nid]["output"] for nid in dones if self.nodes[nid]["output"]]
        return "\n\n".join(parts)

    # -- control ------------------------------------------------------------------
    def start(self):
        self.say(f"Run started in {self.folder}")
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        with self.lock:
            if self.status not in ("running", "waiting"):
                return
            self.status = "stopped"
            for a in list(self.live_agents):
                a.stop()
            for ev in self.approvals.values():
                ev.set()
        self.say("Stopped by you.")

    def decide(self, node_id, approved, note=""):
        with self.lock:
            ev = self.approvals.get(node_id)
            if not ev or self.nodes[node_id]["status"] != "approval":
                return False
            self.decisions[node_id] = (bool(approved), str(note)[:2000])
            ev.set()
        return True

    # -- scheduler ----------------------------------------------------------------
    def _loop(self):
        while True:
            with self.lock:
                if self.status == "stopped":
                    for st in self.nodes.values():
                        if st["status"] in ("waiting", "running", "approval"):
                            st["status"] = "stopped"
                    break
                ready = []
                for nid, st in self.nodes.items():
                    if st["status"] != "waiting":
                        continue
                    ins = [self.nodes[i]["status"] for i in self.inputs[nid]]
                    if any(s in ("failed", "stopped", "skipped") for s in ins):
                        st["status"] = "skipped"
                        st["note"] = "An earlier stage didn't finish."
                    elif all(s == "done" for s in ins):
                        ready.append(nid)
                for nid in ready:
                    self.nodes[nid]["status"] = "running"
                    self.nodes[nid]["started"] = time.time()
                    t = threading.Thread(target=self._run_node, args=(nid,), daemon=True)
                    self.threads.append(t)
                    t.start()
                states = [st["status"] for st in self.nodes.values()]
                if all(s in TERMINAL for s in states) and not any(t.is_alive() for t in self.threads):
                    self.status = "failed" if "failed" in states else "done"
                    break
                self.status = "waiting" if "approval" in states and "running" not in states else "running"
            self._wake.wait(1.0)
            self._wake.clear()
        with self.lock:
            self.ended = time.time()
        self.say({"done": "Finished.", "failed": "The run failed.",
                  "stopped": "Run stopped."}.get(self.status, "Run ended."))
        self.changed(force=True)

    def _run_node(self, nid):
        node, st = self.by_id[nid], self.nodes[nid]
        try:
            kind = node["type"]
            if kind == "master":
                self._master(node, st)
            elif kind == "cluster":
                self._cluster(node, st)
            elif kind == "checkpoint":
                self._checkpoint(node, st)
            elif kind == "approval":
                self._approval(node, st)
            else:   # done: the final result, without "From ..." labels when one stage feeds it
                st["output"] = self._handoff(nid, labels=False)
                st["status"] = "done"
        except Exception as exc:   # one broken node must not hang the run
            st["status"], st["error"] = "failed", f"{type(exc).__name__}: {exc}"
        with self.lock:
            if self.status == "stopped" and st["status"] not in ("done", "failed"):
                st["status"] = "stopped"
            st["ended"] = time.time()
        if st["status"] == "failed":
            self.say(f"{node['name']} failed: {st['error'] or 'see its agents'}")
        elif st["status"] == "done":
            self.say(f"{node['name']} finished.")
        self.changed(force=True)

    # -- prompts ------------------------------------------------------------------
    def _handoff(self, nid, labels=True):
        """The outputs wired into a node. Labels say which stage each came from (skipped for a single input)."""
        outs = [(src, self.nodes[src]["output"].strip()) for src in self.inputs[nid]]
        outs = [(src, out) for src, out in outs if out]
        if not labels and len(outs) == 1:
            return outs[0][1]
        return "\n\n".join(f"## From {self.by_id[src]['name']}\n{out}" for src, out in outs)

    def _connectors_for(self, node, st):
        """The node's connectors this computer really has, plus every server name (to block the rest)."""
        want = node.get("connectors") or []
        if not want:
            return [], []
        if node.get("engine", "claude") != "claude":
            st["note"] = (st.get("note", "") + " Connectors only work on Claude Code teams, so this team runs without them.").strip()
            return [], []
        info = claude_code.list_connectors()
        have = {c["id"] for c in info["connectors"]}
        use = [c for c in want if c in have]
        missing = [c.removeprefix("claude.ai ") for c in want if c not in have]
        if missing:
            note = f"{', '.join(missing)} isn't available to Claude Code right now, so this team runs without it."
            st["note"] = note
            self.say(f"{node['name']}: {note}")
        return use, info["seen"]

    def _clis_for(self, node, st):
        """The node's command-line tools that are installed here; notes the ones that aren't."""
        want = node.get("clis") or []
        if node.get("tools") == "full" or node.get("engine", "claude") != "claude":   # can already run commands, or picks its own
            return []
        use = [c for c in want if claude_code.cli_installed(c)]
        missing = [c for c in want if c not in use]
        if missing:
            note = f"{', '.join(missing)} isn't installed on this computer, so this team runs without it."
            st["note"] = (st.get("note", "") + " " + note).strip()
            self.say(f"{node['name']}: {note}")
        return use

    def _system(self, node, i, n, apps=(), clis=()):
        role = (node.get("instructions") or self.roles.get(node.get("bot") or "")
                or f"You are part of the {node['name']} stage.")
        tool_note = {
            "none": "You have no tools: answer from the material you're given.",
            "read": "You can read files in this folder but not change them.",
            "web": "You can search and read the web, but not touch files.",
            "research": "You can read files here and search the web, but not change files.",
            "edit": "You can read and edit files in this folder. You can't run commands.",
            "full": "You can read and edit files and run commands in this folder.",
        }[node.get("tools", "read")]
        lines = [
            f'You are agent {i} of {n} in the "{node["name"]}" stage of a multi-agent pipeline run by Lithnode.',
            f"Your role: {role}",
        ]
        lines += [
            tool_note,
            *([f"Connected apps you can use: {', '.join(a.removeprefix('claude.ai ') for a in apps)}. Their tools load "
               "on demand: use tool search with the exact action you need (for example \"create product\" or "
               "\"list orders\"), never a whole app. Only change things in these apps when your job says to."]
              if apps else []),
            *([f"Command-line tools you can run with Bash: {', '.join(clis)}. Only commands that start with one of them "
               "are allowed; anything else is blocked, so don't try other commands or chain them with && or pipes. "
               "Only change things with them when your job says to."]
              if clis else []),
            *([f"This team splits one job {n} ways and you do part {i} of {n}. Work out how the whole job divides "
               f"into {n} equal parts (rows, records, files, pages, items: whatever it is made of), then do only part {i}. "
               f"If you write files, write only ones named for your part (for example part-{i}-of-{n}), so you never "
               "touch a teammate's work. Say in your report exactly which range you covered."]
              if node.get("split") and n > 1 else []),
            *(["To look at a web page or HTML file (one you made or one you're checking), run `lithnode-shot <file or URL> "
               "[seconds]`. It saves a screenshot and prints its path; read that image. For anything animated, look at "
               "several moments (like 1, 4 and 8 seconds). Never call visual work good without looking at it: check "
               "that nothing is cut off, overlapping or unreadable."]
              if node.get("tools", "read") in ("read", "research", "edit", "full") else []),
            "Work economically: read only the files you need, prefer Grep and Glob over reading whole files, "
            "and skip exploratory detours.",
            "Do your stage's job only; other stages handle the rest.",
            ITEMS_NOTE,
            'Finish with a section starting with "REPORT:" (under 250 words, plus any list your job produces): what you '
            "did, what you found, and what the next stage must know. Only that report is passed on, and it's what the "
            "user reads: put your actual results in it (the ideas, the answer, the findings, the list), not a "
            "sentence saying you made them. Say plainly what you didn't do, and never describe planned work as done.",
            f"Today's date: {date.today().isoformat()}.",
        ]
        return "\n".join(lines)

    def _prompt(self, nid, focus, teammates=""):
        parts = [f"# Task\n{self.task}"]
        if self.brief:
            parts.append(f"# Brief from the lead\n{self.brief}")
        handoff = self._handoff(nid)
        if handoff:
            parts.append(f"# Handoff from earlier stages\n{handoff}")
        if teammates:
            parts.append(f"# Teammates who went before you in this stage\n{teammates}")
        parts.append(f"# Your focus\n{focus}")
        return "\n\n".join(parts)

    # -- node kinds -----------------------------------------------------------------
    def _agent(self, node, st, label, *, model, effort, tools, system, prompt, max_turns=0, shape=None, color=None,
               connectors=(), known=(), clis=(), engine="claude", engine_model=""):
        """Run one agent to completion, tracked in the node's state. Returns its record."""
        rec = {"name": label, "status": "running", "step": "", "steps": [], "report": "", "items": [], "error": "",
               "cost": 0.0, "turns": 0, "model": model if engine == "claude" else engines.LABELS[engine], "engine": engine, "session_id": "", "started": time.time(), "ended": None,
               "shape": shape or node.get("shape") or "crab", "color": color or node.get("color") or "#D97757"}

        def update():
            with self.lock:
                rec.update(step=agent.step, steps=list(agent.steps))
            self.changed()

        agent = agents.Agent(model=model, effort=effort, tools=tools, system=system, prompt=prompt,
                             cwd=self.folder, on_update=update, max_turns=max_turns,
                             connectors=connectors, known=known, clis=clis, engine=engine, engine_model=engine_model)
        with self.lock:
            rec["session_id"] = agent.session_id
            st["agents"].append(rec)
            if self.status == "stopped":
                rec.update(status="stopped", ended=time.time())
                return rec
            self.live_agents.append(agent)
        try:
            ok = agent.run()
        except Exception as exc:   # still finish the record, so it never shows as running forever
            agent.error, ok = agent.error or f"{type(exc).__name__}: {exc}", False
        with self.lock:
            if agent in self.live_agents:
                self.live_agents.remove(agent)
            rec.update(status="done" if ok else ("stopped" if agent.stopped else "failed"),
                       report=agents.report_of(strip_items(agent.text), REPORT_LIMIT) if ok else "",
                       items=parse_items(agent.text) if ok else [],
                       error=agent.error or "", cost=round(agent.cost, 4), turns=agent.turns,
                       step=agent.step, ended=time.time())
        self.changed(force=True)
        return rec

    def _master(self, node, st):
        if node.get("mode") == "pass":
            st["output"], st["status"] = "", "done"
            st["note"] = "Passed your task straight on (no planning step)."
            return
        system = (
            "You are the lead of a multi-agent pipeline run by Lithnode. You don't do the work yourself: "
            "you write the brief every later agent will read.\n"
            + (f"Extra instructions: {node['instructions']}\n" if node.get("instructions") else "")
            + "The stages after you are: " + self._stage_list() + ".\n"
            "Look at the folder if that helps, then end with a section starting with \"REPORT:\" containing "
            "the brief (under 300 words): goal, constraints, acceptance criteria, and a line for each stage."
        )
        rec = self._agent(node, st, "Planner", model=node["model"], effort=node.get("effort", "low"),
                          tools=node.get("tools", "read"), system=system,
                          prompt=f"# Task\n{self.task}\n\nWrite the brief.", max_turns=node.get("max_turns", 0),
                          shape="crab", color="#D97757")
        if rec["status"] == "done":
            with self.lock:
                self.brief = rec["report"]
            st["output"], st["status"] = "", "done"
        else:
            st["status"], st["error"] = ("stopped" if rec["status"] == "stopped" else "failed"), rec["error"]

    def _stage_list(self):
        names = [n["name"] for n in self.flow["nodes"] if n["type"] == "cluster"]
        return ", ".join(names) or "none"

    def _cluster(self, node, st):
        n = node.get("count", 1)
        focuses = [f.strip() for f in (node.get("focuses") or "").splitlines() if f.strip()]

        def focus(i):
            if node.get("split") and n > 1:
                return f"Part {i} of {n}." + (f" {focuses[(i - 1) % len(focuses)]}" if focuses else "")
            if focuses:
                return focuses[(i - 1) % len(focuses)]
            if n == 1:
                return "Do the whole job for this stage."
            return ("Your teammates have the same role. Work independently and look for what the others "
                    "might miss.")

        apps, known = self._connectors_for(node, st)
        clis = self._clis_for(node, st)
        engine = node.get("engine", "claude")
        if engine == "codex" and engines.status("codex").get("sandbox") is False and node["tools"] != "full":
            st["note"] = (st.get("note", "") + " Codex's sandbox doesn't work on this computer, so this team ran with full access.").strip()

        def one(i, teammates=""):
            return self._agent(node, st, f"{node['name']} {i}" if n > 1 else node["name"],
                               model=node["model"], effort=node.get("effort", "low"), tools=node["tools"],
                               system=self._system(node, i, n, apps, clis), prompt=self._prompt(node["id"], focus(i), teammates),
                               max_turns=node.get("max_turns", 0), connectors=apps, known=known, clis=clis,
                               engine=engine, engine_model=node.get("engine_model", ""))

        # Agents that edit files take turns, so they never overwrite each other. A team that splits the job
        # works side by side instead: each agent only writes its own part.
        if node["tools"] in agents.WRITES and not (node.get("split") and n > 1):
            if n > 1:
                st["note"] = "These agents can edit files, so they take turns in the same folder."
            recs, so_far = [], ""
            with self._edit_lock:   # and a writing team in a parallel branch waits for this one
                for i in range(1, n + 1):
                    if self.status == "stopped":
                        break
                    rec = one(i, so_far)
                    recs.append(rec)
                    if rec["report"]:
                        so_far += f"## {rec['name']}\n{rec['report']}\n\n"
        else:
            def all_at_once():
                threads, results = [], {}
                for i in range(1, n + 1):
                    t = threading.Thread(target=lambda i=i: results.__setitem__(i, one(i)), daemon=True)
                    threads.append(t)
                    t.start()
                for t in threads:
                    t.join()
                return [results[i] for i in sorted(results)]

            if node["tools"] in agents.WRITES:   # a split writing team: side by side, but not beside another writing team
                st["note"] = f"These {n} agents split the job and work side by side, each on its own part."
                with self._edit_lock:
                    recs = all_at_once()
            else:
                recs = all_at_once()

        good = [r for r in recs if r["status"] == "done"]
        if self.status == "stopped":
            st["status"] = "stopped"
        elif not good:
            st["status"] = "failed"
            st["error"] = next((r["error"] for r in recs if r["error"]), "No agent finished.")
        else:
            st["items"] = merge_items([r.get("items") or [] for r in good])
            # one agent's report needs no heading; several get their names, so the next stage can tell them apart
            st["output"] = good[0]["report"] if len(recs) == 1 else "\n\n".join(f"### {r['name']}\n{r['report']}" for r in good)
            if st["items"]:
                st["output"] += "\n\n" + items_block(st["items"])
            if len(good) < len(recs):
                st["note"] = f"{len(recs) - len(good)} of {len(recs)} agents failed; passing on the rest."
            st["status"] = "done"

    def _checkpoint(self, node, st):
        handoff = self._handoff(node["id"])
        if node.get("mode") != "summarize" or not handoff:
            st["output"], st["status"] = handoff, "done"
            return
        system = ("You merge reports from several AI agents into one handoff for the next stage. Remove "
                  "duplicates, keep every concrete finding (with file names), drop filler. End with a section "
                  "starting with \"REPORT:\" containing the merged handoff, under 400 words.")
        rec = self._agent(node, st, "Merger", model=node.get("model", SUMMARY_MODEL), effort="low", tools="none",
                          system=system, prompt=f"# Task\n{self.task}\n\n# Reports\n{handoff}",
                          shape="muse", color="#8d93a8")
        if rec["status"] == "done":
            st["output"], st["status"] = rec["report"], "done"
        elif node.get("on_error") == "continue" and rec["status"] == "failed":
            st["output"], st["status"], st["note"] = handoff, "done", "Summary failed; passed the full reports on."
        else:
            st["status"], st["error"] = ("stopped" if rec["status"] == "stopped" else "failed"), rec["error"]

    def _approval(self, node, st):
        ev = threading.Event()
        with self.lock:
            if self.status == "stopped":   # Stop came first: nothing would ever set this event
                st["status"] = "stopped"
                return
            self.approvals[node["id"]] = ev
            st["status"] = "approval"
        msg = node.get("message") or f"{node['name']} is waiting for your approval."
        self.say(f"Waiting for you: {msg}")
        if node.get("webhook"):
            threading.Thread(target=_ping, args=(node["webhook"], self.flow["name"], msg), daemon=True).start()
        self.changed(force=True)
        ev.wait()
        approved, note = self.decisions.get(node["id"], (False, ""))
        if self.status == "stopped":
            st["status"] = "stopped"
            return
        if approved:
            handoff = self._handoff(node["id"])
            st["output"] = handoff + (f"\n\n## Note from the user\n{note}" if note else "")
            st["status"], st["note"] = "done", "Approved" + (f": {note}" if note else "")
        else:
            st["status"], st["error"] = "failed", "Rejected" + (f": {note}" if note else "")


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None   # a webhook that redirects isn't followed: the new address could be anything


_WEBHOOK_OPENER = urlrequest.build_opener(_NoRedirect)


def _ping(url, flow_name, message):
    """Tell a phone or chat app that a run needs you. Works with ntfy, IFTTT, Discord and Slack webhooks."""
    if not webhook_ok(url):
        return
    body = json.dumps({"text": f"Lithnode · {flow_name}: {message}", "content": f"Lithnode · {flow_name}: {message}",
                       "value1": flow_name, "value2": message}).encode()
    headers = {"Content-Type": "application/json", "Title": "Lithnode needs you"}
    if "ntfy" in (urlparse(url).hostname or ""):
        body, headers = f"{flow_name}: {message}".encode(), {"Title": "Lithnode needs you"}
    try:
        _WEBHOOK_OPENER.open(urlrequest.Request(url, data=body, headers=headers, method="POST"), timeout=10).read()
    except OSError:
        pass


class Runner:
    """All runs in this server process."""

    def __init__(self, store):
        self.store = store
        self.runs = {}
        self.lock = threading.Lock()
        self.bot_roles = dict         # set by the server: {bot id: hidden instructions}

    def mark_interrupted(self):
        """Runs left unfinished by a server that's gone. Call only once this process owns the port,
        or a second launch would mark the live server's runs as interrupted."""
        for item in self.store.list_runs(limit=200):
            if item["status"] in ("running", "waiting"):
                rec = self.store.get_run(item["id"])
                if rec:
                    rec["status"] = "interrupted"
                    for st in rec.get("nodes", {}).values():
                        if st.get("status") in ("waiting", "running", "approval"):
                            st["status"] = "stopped"
                    self.store.save_run(rec)

    def start(self, flow, task, folder):
        flow = {**clean_flow(flow), "id": flow["id"]}   # never trust a flow just because it came from disk
        run = Run(self.store, flow, task, folder, self.bot_roles())
        with self.lock:
            self.runs[run.id] = run
        run.start()
        return run

    def stop_all(self):
        """Stop every live run and its agents (on quit), so no Claude Code session outlives the app."""
        for run in self.active():
            run.stop()

    def get(self, run_id):
        return self.runs.get(run_id)

    def snapshot(self, run_id):
        run = self.runs.get(run_id)
        return run.snapshot() if run else self.store.get_run(run_id)

    def active(self):
        return [r for r in self.runs.values() if r.status in ("running", "waiting")]
