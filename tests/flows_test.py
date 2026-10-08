"""End-to-end tests for Flows: the real hq.py server running pipelines against a mock `claude` CLI.

    .venv\\Scripts\\python tests\\flows_test.py
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
APP, HOOK = 8793, 8794
URL = f"http://127.0.0.1:{APP}"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def call(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}") if "json" in r.headers.get("Content-Type", "") else r.read().decode()
    except error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def cli_calls():
    log = Path(cli_dir, "calls.jsonl")
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def agent_calls(since=0):
    return [c for c in cli_calls()[since:] if "flags" in c and "--append-system-prompt" in c["flags"]]


def ends():
    return {c["end"]: c["t"] for c in cli_calls() if "end" in c}


def wait_run(run_id, until=("done", "failed", "stopped"), timeout=120):   # generous: a busy machine starts agents slowly
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, r = call(f"/api/runs/{run_id}")
        if r.get("status") in until:
            return r
        time.sleep(0.25)
    return r


AGENT_TIMEOUT = 20   # seconds; every mock agent but HANGSTAGE finishes well inside it


def server_env():
    return {**os.environ, "LITHNODE_PORT": str(APP), "LITHNODE_HOME": str(hq_home), "CLAWD_BOT_HOME": str(bot_home),
            "CLAWD_PET_HOME": str(pet_home), "LITHNODE_PICKER": str(project), "LITHNODE_AGENT_TIMEOUT": str(AGENT_TIMEOUT),
            "CLAWD_BOT_CLAUDE_CMD": json.dumps([sys.executable, str(ROOT / "tests" / "mock_claude.py")]),
            "CLAWD_MOCK_STATE": str(Path(cli_dir, "state.json")), "CLAWD_MOCK_LOG": str(Path(cli_dir, "calls.jsonl")),
            "CLAWD_MOCK_SESSIONS": str(Path(cli_dir, "sessions.json")), "LITHNODE_CLIS": "git,gh,vercel"}


def start_server():
    p = subprocess.Popen([sys.executable, str(ROOT / "hq.py"), "--no-open"], env=server_env())
    for _ in range(80):
        try:
            request.urlopen(URL + "/api/ping", timeout=1)
            return p
        except OSError:
            time.sleep(0.1)
    raise SystemExit("server did not start")


# A webhook receiver, standing in for ntfy / IFTTT / Discord
pings, hops = [], []


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        if self.path == "/moved":   # a webhook that redirects somewhere else
            hops.append("POST /moved")
            self.send_response(302)
            self.send_header("Location", "/landed")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        pings.append(body)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        hops.append("GET " + self.path)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", HOOK), Hook).serve_forever, daemon=True).start()

hq_home, bot_home, pet_home = (Path(tempfile.mkdtemp(prefix=p)) for p in ("hq-", "bot-", "pet-"))
cli_dir = tempfile.mkdtemp(prefix="hq-cli-")
project = Path(tempfile.mkdtemp(prefix="hq-project-"))
# leave no test folders behind, even if a check crashes
atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True) for d in (hq_home, bot_home, pet_home, cli_dir, project)])
(project / "app.py").write_text("print('hi')\n")
Path(cli_dir, "state.json").write_text(json.dumps({"logged_in": True}))
server = start_server()
try:
    # ---- pages ------------------------------------------------------------------------------
    for path, needle in [("/", "Lithnode"), ("/flows", "Custom team"), ("/office", "<h1>Office</h1>"), ("/static/sprites.js", "drawClawd")]:
        s, body = call(path)
        check(f"serves {path}", s == 200 and needle in body, s)
    check("static files can't escape the folder", call("/static/..%5Chq.py")[0] == 404 and call("/static/../hq.py")[0] == 404)

    # ---- flows: templates, validation, estimate ---------------------------------------------
    s, listing = call("/api/flows")
    check("templates and models listed", {t["id"] for t in listing["templates"]} == {"ship-it", "review", "batch", "deploy", "research"}
          and any(m["id"] == "claude-haiku-4-5" for m in listing["models"]), listing)
    s, d = call("/api/flows", {"template": "ship-it"}, "POST")
    ship = d["flow"]
    check("ship-it template: 9 nodes, ready to run", len(ship["nodes"]) == 9 and d["problems"] == [], d["problems"])
    by = {n["id"]: n for n in ship["nodes"]}
    check("templates go left to right, parallel stages stacked, long chains wrap to a new row", ship["dir"] == "lr"
          and by["master"]["x"] < by["build"]["x"] < by["bugs"]["x"] == by["sec"]["x"] and by["bugs"]["y"] != by["sec"]["y"]
          and by["ok"]["x"] < by["cp2"]["x"] and by["ok"]["y"] > by["master"]["y"] and by["done"]["y"] == by["ok"]["y"])
    check("estimate counts every agent session", d["estimate"]["sessions"] == 9
          and d["estimate"]["per_model"] == {"claude-sonnet-5-5": 7, "claude-opus-5-5": 1, "claude-haiku-4-5": 1}, d["estimate"])
    s, blank = call("/api/flows", {}, "POST")
    check("a blank flow says what's missing", any("cluster" in p for p in blank["problems"]), blank["problems"])
    two = {**blank["flow"], "nodes": blank["flow"]["nodes"] + [{"id": "done-2", "type": "done", "x": 0, "y": 0}],
           "edges": blank["flow"]["edges"] + [{"from": "master", "to": "done-2"}]}
    check("a second Done step is flagged, so the flow won't run", any("one Done" in p for p in call(f"/api/flows/{blank['flow']['id']}", two, "POST")[1]["problems"]))
    call(f"/api/flows/{blank['flow']['id']}", blank["flow"], "POST")
    check("flows start at a step called Start", blank["flow"]["nodes"][0]["name"] == "Start" and ship["nodes"][0]["name"] == "Start")
    old = {**blank["flow"], "nodes": [{**n, "name": "Lead"} if n["type"] == "master" else n for n in blank["flow"]["nodes"]]}
    check("a flow saved with the old name Lead shows Start", call(f"/api/flows/{blank['flow']['id']}", old, "POST")[1]["flow"]["nodes"][0]["name"] == "Start")
    check("a blank flow starts left to right, auto-arranged", blank["flow"]["dir"] == "lr" and blank["flow"]["auto"] is True)
    check("auto-arrange can be switched off and stays off",
          call(f"/api/flows/{blank['flow']['id']}", {**blank["flow"], "auto": False}, "POST")[1]["flow"]["auto"] is False)
    fid = blank["flow"]["id"]

    base = blank["flow"]
    bad = {**base, "edges": base["edges"] + [{"from": "done", "to": "master"}]}
    check("edge into the master rejected", call(f"/api/flows/{fid}", bad, "POST")[0] == 400)
    loop = {**base, "nodes": base["nodes"] + [
        {"id": "a", "type": "cluster", "x": 0, "y": 0, "name": "A"}, {"id": "b", "type": "cluster", "x": 0, "y": 0, "name": "B"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]}
    s, r = call(f"/api/flows/{fid}", loop, "POST")
    check("loops rejected", s == 400 and "loop" in r["error"], r)
    weird = {**base, "nodes": base["nodes"] + [{"id": "w", "type": "cluster", "x": 0, "y": 0, "name": "W", "count": 99,
                                                  "tools": "root", "shape": "dragon"}]}
    s, r = call(f"/api/flows/{fid}", weird, "POST")
    w = next(n for n in r["flow"]["nodes"] if n["id"] == "w")
    check("node settings are clamped and cleaned", w["count"] == 15 and w["tools"] == "read"
          and w["shape"] == "crab", w)
    check("unconnected nodes reported", any("Not connected" in p for p in r["problems"]), r["problems"])
    hooky = {**base, "nodes": base["nodes"] + [{"id": "ap", "type": "approval", "x": 0, "y": 0, "webhook": "file:///etc/passwd"}]}
    check("non-http webhook rejected", call(f"/api/flows/{fid}", hooky, "POST")[0] == 400)
    check("bad flow id rejected", call("/api/flows/..%5Cx")[0] == 400)
    nodone = {**base, "nodes": [base["nodes"][0], {"id": "c", "type": "cluster", "x": 0, "y": 0}], "edges": [{"from": "master", "to": "c"}]}
    check("a flow with no Done step is flagged", any("Done" in p for p in call(f"/api/flows/{fid}", nodone, "POST")[1]["problems"]))
    check("a node that isn't an object is a clear 400, not a crash", call(f"/api/flows/{fid}", {**base, "nodes": ["x"]}, "POST")[0] == 400)
    s, r = call(f"/api/flows/{fid}", {**base, "nodes": base["nodes"] + [{"id": "m", "type": "cluster", "x": "nan", "model": 'x" & calc'}]}, "POST")
    m = next(n for n in r["flow"]["nodes"] if n["id"] == "m")
    check("odd model names and NaN positions are cleaned", m["model"] == "claude-sonnet-5-5" and m["x"] == 0, m)
    call(f"/api/flows/{fid}", base, "POST")
    # a flow file edited by hand (or copied in) gets the same checks as page input
    _, hand = call("/api/flows", {}, "POST")
    hid = hand["flow"]["id"]
    hpath = hq_home / "flows" / f"{hid}.json"
    raw = json.loads(hpath.read_text(encoding="utf-8"))
    raw["nodes"].append({"id": "x", "type": "cluster", "tools": "root", "model": 'a" & calc'})
    hpath.write_text(json.dumps(raw), encoding="utf-8")
    x = next((n for n in call(f"/api/flows/{hid}")[1].get("flow", {}).get("nodes", []) if n["id"] == "x"), {})
    check("a hand-edited flow file is cleaned on load", x.get("tools") == "read" and x.get("model") == "claude-sonnet-5-5", x)
    raw["nodes"].append({"id": "y", "type": "approval", "webhook": "file:///etc/passwd"})
    hpath.write_text(json.dumps(raw), encoding="utf-8")
    check("a hand-edited flow file with a bad webhook won't load or run",
          call(f"/api/flows/{hid}")[0] == 400 and call(f"/api/flows/{hid}/run", {"task": "x"}, "POST")[0] == 400)
    s, r = call(f"/api/flows/{fid}/run", {"task": "x"}, "POST")
    check("an unrunnable flow refuses to start", s == 400 and "Not connected to Start" in r["error"], r)

    # ---- run: quick review (parallel read-only reviewers -> summary) ---------------------------
    s, d = call("/api/flows", {"template": "review"}, "POST")
    review = d["flow"]
    check("review template is cheap: 4 Haiku sessions", d["estimate"]["per_model"] == {"claude-haiku-4-5": 4}, d["estimate"])
    s, r = call(f"/api/flows/{review['id']}/run", {"task": "Review it", "folder": str(project / "missing")}, "POST")
    check("a folder that doesn't exist is refused", s == 400 and "doesn't exist" in r["error"], r)
    s, r = call(f"/api/flows/{review['id']}/run", {"task": "  "}, "POST")
    check("an empty task is refused", s == 400)
    n0 = len(cli_calls())
    s, r = call(f"/api/flows/{review['id']}/run", {"task": "Review the app", "folder": str(project)}, "POST")
    run = wait_run(r["run"])
    check("review run finishes", run["status"] == "done", run["status"])
    calls = agent_calls(n0)
    reviewers = [c for c in calls if "Reviewers" in c["flags"]["--append-system-prompt"]]
    merger = [c for c in calls if "merge reports" in c["flags"]["--append-system-prompt"]]
    check("3 reviewers + 1 merger, no lead (pass mode)", len(reviewers) == 3 and len(merger) == 1 and len(calls) == 4, len(calls))
    f0 = reviewers[0]["flags"]
    check("reviewers are read-only", f0["--tools"] == "Read,Glob,Grep" and f0["--allowedTools"] == "Read,Glob,Grep"
          and "--permission-mode" not in f0, f0)
    check("agents skip MCP servers, claude.ai connectors and the slash-command list (keeps prompts small)",
          all("--strict-mcp-config" in c["flags"] and c["flags"].get("--disallowedTools") == "mcp__*"
              and c["connectors"] == "false" and "--disable-slash-commands" in c["flags"] for c in calls))
    check("reviewers use the cluster's model, no effort flag on Haiku", f0["--model"] == "claude-haiku-4-5" and "--effort" not in f0)
    check("agents run in the chosen folder", all(Path(c["cwd"]).resolve() == project.resolve() for c in calls))
    check("each reviewer gets its own focus", sorted(c["prompt"].split("# Your focus\n")[1] for c in reviewers)
          == ["Correctness", "Readability and structure", "Security"], [c["prompt"][-60:] for c in reviewers])
    check("every agent is told to work economically", all("Work economically" in c["flags"]["--append-system-prompt"] for c in reviewers))
    check("skills are gone from flows", all("skills" not in n for n in review["nodes"]) and call("/api/skills")[0] == 404)
    check("the task goes over stdin", all(c["via"] == "stdin" and "Review the app" in c["prompt"] for c in calls))
    sessions = [c["flags"]["--session-id"] for c in reviewers]
    finish = ends()
    # when HQ launched each agent (process start-up time on a busy machine doesn't count)
    launched = [a["started"] for a in run["nodes"]["rev"]["agents"]]
    check("read-only reviewers run side by side", max(launched) < min(finish[s] for s in sessions) and max(launched) - min(launched) < 0.5,
          (launched, finish))
    check("merger only starts after every reviewer", merger[0]["t"] >= max(finish[s] for s in sessions))
    check("merger receives all three reports", merger[0]["prompt"].count("Reviewers report from") == 3, merger[0]["prompt"])
    check("final result is the merged handoff", "report from" in run["final"] and run["nodes"]["sum"]["status"] == "done", run["final"])
    check("cost adds up from Claude Code's numbers", abs(run["cost"] - 0.04) < 1e-6, run["cost"])
    rev_agents = run["nodes"]["rev"]["agents"]
    check("agent steps are recorded", any("Reading app.py" in s for a in rev_agents for s in a["steps"]), rev_agents[0]["steps"])
    check("run is listed in history", any(x["id"] == run["id"] and x["status"] == "done" for x in call("/api/runs")[1]["runs"]))

    # ---- connectors: a team gets only the ones switched on, loaded on demand ----------------------
    s, cn = call("/api/connectors")
    check("connectors come from the free probe: only ones that connect are offered",
          s == 200 and cn["ok"] and [c["name"] for c in cn["connectors"]] == ["Vercel", "Notion"], cn)
    probe = [c for c in cli_calls() if c.get("probe")]
    check("the probe runs with connectors and tool search on", probe and probe[-1]["connectors"] is None and probe[-1]["toolsearch"] == "true", probe[-1:])
    n_probe = len(probe)
    call("/api/connectors")
    check("the connector list is cached", len([c for c in cli_calls() if c.get("probe")]) == n_probe)
    call("/api/connectors?refresh=1")
    check("Refresh checks again", len([c for c in cli_calls() if c.get("probe")]) == n_probe + 1)
    s, d = call("/api/flows", {"template": "review"}, "POST")
    shop = d["flow"]
    for nd in shop["nodes"]:
        if nd["id"] == "rev":
            nd.update(count=1, connectors=["claude.ai Vercel", "claude.ai Gone", "claude.ai Vercel", "bad,name"])
    s, d = call(f"/api/flows/{shop['id']}", shop, "POST")
    saved = [nd for nd in d["flow"]["nodes"] if nd["id"] == "rev"][0]
    check("a team's connectors are saved, cleaned and deduplicated", saved["connectors"] == ["claude.ai Vercel", "claude.ai Gone"], saved)
    n0 = len(cli_calls())
    s, r = call(f"/api/flows/{shop['id']}/run", {"task": "List my projects", "folder": str(project)}, "POST")
    run = wait_run(r["run"])
    calls = agent_calls(n0)
    team = [c for c in calls if "Reviewers" in c["flags"]["--append-system-prompt"]]
    other = [c for c in calls if c not in team]
    f = team[0]["flags"] if team else {}
    check("a team with connectors loads them on demand", run["status"] == "done" and len(team) == 1
          and f.get("--tools") == "Read,Glob,Grep,ToolSearch" and "--strict-mcp-config" not in f
          and team[0]["connectors"] is None and team[0]["toolsearch"] == "true", (run["status"], f))
    check("only its own connector is allowed; every other server is blocked by name",
          f.get("--allowedTools") == "Read,Glob,Grep,mcp__claude_ai_Vercel"
          and set(f.get("--disallowedTools", "").split(",")) == {"mcp__claude_ai_Notion", "mcp__claude_ai_Broken"}, f)
    check("the agent is told which apps it has and to search narrowly",
          "Connected apps you can use: Vercel." in f.get("--append-system-prompt", "") and "Gone" not in f.get("--append-system-prompt", ""))
    check("a connector that isn't available is reported, and the team runs without it",
          "Gone isn't available" in (run["nodes"]["rev"].get("note") or "") and any("Gone isn't available" in l["text"] for l in run["log"]), run["nodes"]["rev"])
    check("teams without connectors still load none", other and all("--strict-mcp-config" in c["flags"] and c["flags"]["--disallowedTools"] == "mcp__*"
                                                                      and c["connectors"] == "false" for c in other))

    # ---- CLIs: a team may run only the command-line tools switched on --------------------------------
    s, cl = call("/api/clis")
    check("installed CLIs are listed", s == 200 and [c["id"] for c in cl["clis"]] == ["git", "gh", "vercel"], cl)
    s, d = call("/api/flows", {"template": "review"}, "POST")
    tf = d["flow"]
    for nd in tf["nodes"]:
        if nd["id"] == "rev":
            nd.update(count=1, clis=["gh", "vercel", "gh", "rm -rf", "nothere"])
    s, d = call(f"/api/flows/{tf['id']}", tf, "POST")
    saved = [nd for nd in d["flow"]["nodes"] if nd["id"] == "rev"][0]
    check("a team's CLIs are saved, cleaned and deduplicated", saved["clis"] == ["gh", "vercel", "nothere"], saved)
    n0 = len(cli_calls())
    run = wait_run(call(f"/api/flows/{tf['id']}/run", {"task": "Triage my issues", "folder": str(project)}, "POST")[1]["run"])
    team = [c for c in agent_calls(n0) if "Reviewers" in c["flags"]["--append-system-prompt"]]
    f = team[0]["flags"] if team else {}
    check("a team with CLIs gets Bash, allowed only for those tools", run["status"] == "done"
          and f.get("--tools") == "Read,Glob,Grep,Bash" and f.get("--allowedTools") == "Read,Glob,Grep,Bash(gh:*),Bash(vercel:*)", f)
    check("the agent is told which tools it may run", "Command-line tools you can run with Bash: gh, vercel." in f.get("--append-system-prompt", ""))
    check("a CLI that isn't installed is reported", "nothere isn't installed" in (run["nodes"]["rev"].get("note") or ""), run["nodes"]["rev"])
    for nd in tf["nodes"]:
        if nd["id"] == "rev":
            nd.update(tools="full", clis=["gh"])
    call(f"/api/flows/{tf['id']}", tf, "POST")
    n0 = len(cli_calls())
    wait_run(call(f"/api/flows/{tf['id']}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    f = [c for c in agent_calls(n0) if "Reviewers" in c["flags"]["--append-system-prompt"]][0]["flags"]
    check("a team that can run anything isn't narrowed by its CLI list", f.get("--allowedTools") == "Read,Glob,Grep,Edit,Write,Bash"
          and "Command-line tools" not in f["--append-system-prompt"], f)

    # ---- split: one job cut into parts, done side by side, then checked ---------------------------------
    s, d = call("/api/flows", {"template": "batch"}, "POST")
    batch = d["flow"]
    work = [n for n in batch["nodes"] if n["id"] == "work"][0]
    check("the batch template: workers split the job, then a checker", work["split"] is True and work["count"] == 3
          and work["tools"] == "edit" and work["clis"] == ["python"] and d["problems"] == [], work)
    s, d = call("/api/flows", {"template": "deploy"}, "POST")
    ship_n = [n for n in d["flow"]["nodes"] if n["id"] == "ship"][0]
    check("the deploy template ships with git and vercel only", ship_n["clis"] == ["git", "vercel"] and ship_n["tools"] == "read", ship_n)
    for nd in batch["nodes"]:
        if nd["type"] == "cluster":
            nd["clis"] = []
    call(f"/api/flows/{batch['id']}", batch, "POST")
    n0 = len(cli_calls())
    run = wait_run(call(f"/api/flows/{batch['id']}/run", {"task": "Clean up 100000 song names", "folder": str(project)}, "POST")[1]["run"])
    workers = [c for c in agent_calls(n0) if '"Workers" stage' in c["flags"]["--append-system-prompt"]]
    check("each worker gets its own part", sorted(c["prompt"].split("# Your focus\n")[1][:11] for c in workers) == ["Part 1 of 3", "Part 2 of 3", "Part 3 of 3"]
          and all("you do part" in c["flags"]["--append-system-prompt"] for c in workers), [c["prompt"][-40:] for c in workers])
    wa = run["nodes"]["work"]["agents"]
    starts, finished = [a["started"] for a in wa], [a["ended"] for a in wa]
    check("split writers work side by side, not in turns", run["status"] == "done" and max(starts) < min(finished)
          and "side by side" in run["nodes"]["work"]["note"], run["nodes"]["work"].get("note"))

    # ---- items: a scout lists things, two checkers judge them, an uploader acts on the winners --------
    _, made = call("/api/flows", {}, "POST")
    drop = {"name": "Items check", "nodes": [
        {"id": "master", "type": "master", "x": 0, "y": 0, "mode": "pass"},
        {"id": "scout", "type": "cluster", "x": 0, "y": 0, "name": "Product scout", "count": 1, "model": "claude-haiku-4-5", "tools": "web"},
        {"id": "check", "type": "cluster", "x": 0, "y": 0, "name": "Checker", "count": 2, "model": "claude-haiku-4-5", "tools": "web",
         "focuses": "Margin and price\nReviews, shipping and competition"},
        {"id": "ok", "type": "approval", "x": 0, "y": 0, "name": "Your pick"},
        {"id": "upload", "type": "cluster", "x": 0, "y": 0, "name": "Uploader", "count": 1, "model": "claude-haiku-4-5", "tools": "none"},
        {"id": "done", "type": "done", "x": 0, "y": 0}],
        "edges": [{"from": a, "to": b} for a, b in [("master", "scout"), ("scout", "check"), ("check", "ok"), ("ok", "upload"), ("upload", "done")]]}
    _, d = call(f"/api/flows/{made['flow']['id']}", drop, "POST")
    drop = d["flow"]
    n0 = len(cli_calls())
    s, r = call(f"/api/flows/{drop['id']}/run", {"task": "Find kitchen gadgets under $10", "folder": str(project)}, "POST")
    run = wait_run(r["run"], until=("waiting", "done", "failed", "stopped"))
    scout, checker = run["nodes"]["scout"], run["nodes"]["check"]
    check("the scout's products come back as items, with no verdicts yet",
          [i["title"] for i in scout["items"]][:2] == ["Mini Portable Blender", "Sunset Projection Lamp"] and len(scout["items"]) == 6
          and all("verdict" not in i and i["facts"]["Cost"] for i in scout["items"]), scout.get("items"))
    verdicts = {i["title"]: (i.get("verdict"), i.get("reason")) for i in checker["items"]}
    check("two checkers' verdicts merge: one cut is enough, and each cut keeps its reason",
          verdicts.get("LED Strip Lights 5m") == ("cut", "Margin 34%; Reviews 4.4★") and verdicts.get("Posture Corrector", ("",))[0] == "cut"
          and verdicts.get("Wireless Earbuds") == ("cut", "Reviews 4.3★") and verdicts.get("Mini Portable Blender", ("",))[0] == "pass"
          and len(verdicts) == 6, verdicts)
    calls = agent_calls(n0)
    check("every team is told how to hand back a list", all("```items" in c["flags"]["--append-system-prompt"] for c in calls))
    check("the checkers got the scout's list to judge", all("Mini Portable Blender" in c["prompt"] for c in calls
                                                             if '"Checker" stage' in c["flags"]["--append-system-prompt"]))
    check("reports stay prose: the list lives in items, not in the report text",
          all("```items" not in a["report"] for a in scout["agents"] + checker["agents"]) and "```items" in checker["output"])
    call(f"/api/runs/{run['id']}/decide", {"node": "ok", "approved": True}, "POST")
    run = wait_run(run["id"])
    up = run["nodes"]["upload"]
    check("the uploader lists the winners, and the result carries them", run["status"] == "done"
          and [i["title"] for i in up["items"]] == ["Mini Portable Blender", "Sunset Projection Lamp", "Magnetic Phone Mount"]
          and all(i["reason"] == "Listed as draft" for i in up["items"]) and "```items" in run["final"], up.get("items"))
    check("an agent using a connector tool shows it as a readable step", "Store: create product" in up["agents"][0]["steps"], up["agents"][0]["steps"])

    # ---- run: the full chain with an approval gate and a webhook ping ----------------------------
    ship["nodes"] = [{**n, "webhook": f"http://127.0.0.1:{HOOK}/ping"} if n["type"] == "approval" else n for n in ship["nodes"]]
    s, d = call(f"/api/flows/{ship['id']}", ship, "POST")
    check("ship-it saved with a webhook", s == 200, d)
    n0 = len(cli_calls())
    s, r = call(f"/api/flows/{ship['id']}/run", {"task": "Add a greeting", "folder": str(project)}, "POST")
    run = wait_run(r["run"], until=("waiting", "failed", "done"))
    check("chain pauses at the approval gate", run["status"] == "waiting" and run["nodes"]["ok"]["status"] == "approval", run["status"])
    check("prod check hasn't started yet", run["nodes"]["prod"]["status"] == "waiting")
    time.sleep(0.5)
    check("the webhook was pinged", pings and "waiting" not in pings[0] and "Reviews are in" in pings[0], pings)
    s, hq = call("/api/hq")
    check("tab badge shows an approval waiting", hq["approvals"] == 1 and hq["runs"] == 1, hq)
    calls = agent_calls(n0)
    lead = [c for c in calls if "You are the lead" in c["flags"]["--append-system-prompt"]]
    build = [c for c in calls if '"Builders" stage' in c["flags"]["--append-system-prompt"]]
    bugs = [c for c in calls if '"Bug reviewers" stage' in c["flags"]["--append-system-prompt"]]
    sec = [c for c in calls if '"Security" stage' in c["flags"]["--append-system-prompt"]]
    check("lead, builder, 3 bug reviewers, 2 security, 1 merger so far", (len(lead), len(build), len(bugs), len(sec), len(calls))
          == (1, 1, 3, 2, 8), (len(lead), len(build), len(bugs), len(sec), len(calls)))
    bf = build[0]["flags"]
    check("builder can edit (auto-accepted), with Opus and medium effort",
          bf["--tools"] == "Read,Glob,Grep,Edit,Write" and bf["--permission-mode"] == "acceptEdits"
          and bf["--model"] == "claude-opus-5-5" and bf["--effort"] == "medium", bf)
    check("everyone after the lead gets its brief", all("# Brief from the lead\nlead report from" in c["prompt"] for c in build + bugs + sec))
    check("reviewers get the builder's report as handoff", all("## From Build done" in c["prompt"] and "Builders report from" in c["prompt"] for c in bugs + sec))
    # when Lithnode launched each agent and saw it finish (process start-up on a busy machine doesn't count)
    launched = lambda nid: min(a["started"] for a in run["nodes"][nid]["agents"])   # noqa: E731
    finished = lambda nid: max(a["ended"] for a in run["nodes"][nid]["agents"])     # noqa: E731
    check("bug reviewers and security run in parallel branches (neither waits for the other)",
          launched("sec") < finished("bugs") and launched("bugs") < finished("sec"))
    s, r2 = call(f"/api/runs/{run['id']}/decide", {"node": "nope", "approved": True}, "POST")
    check("deciding on a node that isn't waiting is refused", s == 400)
    call(f"/api/runs/{run['id']}/decide", {"node": "ok", "approved": True, "note": "Ship it but keep it small"}, "POST")
    run = wait_run(run["id"])
    check("approved run finishes", run["status"] == "done", run["status"])
    prod = [c for c in agent_calls(n0) if '"Production check" stage' in c["flags"]["--append-system-prompt"]]
    check("your approval note reaches the next stage", prod and "Ship it but keep it small" in prod[0]["prompt"])
    check("production check sees the merged review", prod and "## From Your call" in prod[0]["prompt"] and "lead report" in prod[0]["prompt"])
    check("final result comes from the production check", "Production check report" in run["final"], run["final"])

    # ---- reject ------------------------------------------------------------------------------
    s, r = call(f"/api/flows/{ship['id']}/run", {"task": "Again", "folder": str(project)}, "POST")
    run = wait_run(r["run"], until=("waiting", "failed"))
    call(f"/api/runs/{run['id']}/decide", {"node": "ok", "approved": False, "note": "not now"}, "POST")
    run = wait_run(run["id"])
    check("rejecting stops the chain", run["status"] == "failed" and run["nodes"]["ok"]["error"] == "Rejected: not now"
          and run["nodes"]["prod"]["status"] == "skipped" and run["nodes"]["done"]["status"] == "skipped", run["nodes"]["prod"])

    # ---- failures ----------------------------------------------------------------------------
    def simple_flow(cluster, **extra):
        flow = {"name": "T", "nodes": [{"id": "master", "type": "master", "x": 0, "y": 0, "mode": "pass"},
                                       {"id": "c", "type": "cluster", "x": 0, "y": 0, **cluster},
                                       {"id": "done", "type": "done", "x": 0, "y": 0}],
                "edges": [{"from": "master", "to": "c"}, {"from": "c", "to": "done"}], **extra}
        _, made = call("/api/flows", {}, "POST")
        _, saved = call(f"/api/flows/{made['flow']['id']}", flow, "POST")
        return saved["flow"]["id"]

    f = simple_flow({"name": "FAILSTAGE", "count": 2, "model": "claude-haiku-4-5"})
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    check("a cluster where every agent fails fails the run", run["status"] == "failed" and run["nodes"]["c"]["status"] == "failed"
          and "blew up" in run["nodes"]["c"]["error"] and run["nodes"]["done"]["status"] == "skipped", run["nodes"]["c"])
    f = simple_flow({"name": "Mixed", "count": 3, "model": "claude-haiku-4-5", "focuses": "fine\nFAILME\nfine"})
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    check("one failed agent out of three: the stage carries on", run["status"] == "done" and "1 of 3 agents failed" in run["nodes"]["c"]["note"]
          and run["nodes"]["c"]["output"].count("report from") == 2, run["nodes"]["c"])

    # ---- writers take turns --------------------------------------------------------------------
    n0 = len(cli_calls())
    f = simple_flow({"name": "Writers", "count": 2, "model": "claude-haiku-4-5", "tools": "edit"})
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    w = agent_calls(n0)
    check("agents that edit files take turns", len(w) == 2 and w[1]["t"] >= ends()[w[0]["flags"]["--session-id"]], w)
    check("the second writer sees the first one's report", "Teammates who went before you" in w[1]["prompt"]
          and "Writers report from" in w[1]["prompt"])
    n0 = len(cli_calls())
    _, made = call("/api/flows", {}, "POST")
    branches = {"name": "T", "nodes": [{"id": "master", "type": "master", "x": 0, "y": 0, "mode": "pass"},
                                       {"id": "l", "type": "cluster", "x": 0, "y": 0, "name": "Left", "model": "claude-haiku-4-5", "tools": "edit"},
                                       {"id": "r", "type": "cluster", "x": 0, "y": 0, "name": "Right", "model": "claude-haiku-4-5", "tools": "edit"},
                                       {"id": "done", "type": "done", "x": 0, "y": 0}],
                "edges": [{"from": "master", "to": "l"}, {"from": "master", "to": "r"}, {"from": "l", "to": "done"}, {"from": "r", "to": "done"}]}
    call(f"/api/flows/{made['flow']['id']}", branches, "POST")
    run = wait_run(call(f"/api/flows/{made['flow']['id']}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    w = sorted(agent_calls(n0), key=lambda c: c["t"])
    check("writers in parallel branches take turns in the folder too", run["status"] == "done" and len(w) == 2
          and w[1]["t"] >= ends()[w[0]["flags"]["--session-id"]], w)

    # ---- an agent that can't start or never ends still finishes its record ---------------------------
    f = simple_flow({"name": "Nowhere", "count": 1, "model": "claude-haiku-4-5"})
    (hq_home / "workspaces").mkdir(parents=True, exist_ok=True)
    (hq_home / "workspaces" / f).write_text("a file where the workspace folder should be")
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go"}, "POST")[1]["run"])
    a = run["nodes"]["c"]["agents"]
    check("an agent whose folder can't be made fails cleanly (not stuck running)", run["status"] == "failed"
          and a and a[0]["status"] == "failed" and "folder" in a[0]["error"], a)
    f = simple_flow({"name": "HANGSTAGE", "count": 1, "model": "claude-haiku-4-5"})
    t0 = time.time()
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"], timeout=AGENT_TIMEOUT + 60)
    a = run["nodes"]["c"]["agents"]
    check("a hung agent is stopped after the time limit", run["status"] == "failed" and a and "Timed out" in a[0]["error"]
          and time.time() - t0 < AGENT_TIMEOUT + 30, (run["status"], a[:1]))

    # ---- built-in bots: a cluster based on one runs with its hidden role ------------------------
    n0 = len(cli_calls())
    f = simple_flow({"name": "Bugs", "count": 1, "model": "claude-haiku-4-5", "bot": "beetle"})
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    sysp = agent_calls(n0)[0]["flags"]["--append-system-prompt"]
    check("a cluster made from a built-in bot uses its hidden role", run["status"] == "done" and "You are Beetle" in sysp, sysp[:160])
    check("the hidden role isn't stored in the flow", call(f"/api/flows/{f}")[1]["flow"]["nodes"][1]["instructions"] == "")
    check("the bot list sent to the page has no built-in instructions",
          all(b["instructions"] == "" for b in call("/api/bots")[1]["bots"] if b["builtin"]))

    # ---- the office shows flow agents, and Stop kills them -------------------------------------
    f = simple_flow({"name": "SLOWSTAGE crew", "count": 2, "model": "claude-haiku-4-5", "shape": "byte", "color": "#5b8def"})
    rid = call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"]
    seen = []
    for _ in range(30):
        seen = [s for s in call("/api/sessions")[1]["sessions"] if s.get("flow")]
        if len(seen) == 2:
            break
        time.sleep(0.2)
    check("running flow agents appear in the office as their cluster's sprite",
          len(seen) == 2 and all(s["bot"]["shape"] == "byte" and s["status"] == "working" for s in seen), seen)
    call(f"/api/runs/{rid}/stop", {}, "POST")
    run = wait_run(rid)
    check("stop ends the run", run["status"] == "stopped" and run["nodes"]["c"]["status"] == "stopped", run["status"])
    time.sleep(4.5)   # a killed agent never reaches its end
    killed = [a["session_id"] for a in run["nodes"]["c"]["agents"]]
    check("stopped agents were killed, not left running", not any(s in ends() for s in killed))
    check("office is empty again", not [s for s in call("/api/sessions")[1]["sessions"] if s.get("flow")])

    # ---- layout rules -----------------------------------------------------------------------
    sys.path.insert(0, str(ROOT))
    import flows as flows_mod  # noqa: E402
    big = {"nodes": [{"id": "master", "type": "master"}, {"id": "done", "type": "done"}, {"id": "spare", "type": "cluster"}]
           + [{"id": f"c{i}", "type": "cluster"} for i in range(7)],
           "edges": [{"from": "master", "to": f"c{i}"} for i in range(7)] + [{"from": f"c{i}", "to": "done"} for i in range(7)]}
    flows_mod._layout(big, "lr")
    at = {n["id"]: (n["x"], n["y"]) for n in big["nodes"]}
    per_column = {}
    for i in range(7):
        per_column[at[f"c{i}"][0]] = per_column.get(at[f"c{i}"][0], 0) + 1
    check("a stage never stacks more than 3 high (7 side by side make 3 columns)", max(per_column.values()) == 3 and len(per_column) == 3, per_column)
    check("nodes with no wires wait in a row underneath", at["spare"][1] > max(y for k, (x, y) in at.items() if k != "spare"), at["spare"])

    # ---- races and webhooks, checked directly -------------------------------------------------------
    early = flows_mod.Run(flows_mod.Store(tempfile.mkdtemp(prefix="hq-unit-")), {"id": "a" * 12, "name": "T", "edges": [],
                          "nodes": [{"id": "ap", "type": "approval", "name": "Ap"}]}, "t", str(project))
    early.stop()
    gate = threading.Thread(target=early._approval, args=(early.by_id["ap"], early.nodes["ap"]), daemon=True)
    gate.start()
    gate.join(3)
    check("Stop before an approval gate opens doesn't leave it waiting forever",
          not gate.is_alive() and early.nodes["ap"]["status"] == "stopped", early.nodes["ap"])
    shutil.rmtree(early.store.root, ignore_errors=True)
    hops.clear()
    flows_mod._ping(f"http://127.0.0.1:{HOOK}/moved", "T", "m")
    check("a webhook's redirect isn't followed", hops == ["POST /moved"], hops)
    import claude_code as cc_mod  # noqa: E402
    shim_dir = Path(tempfile.mkdtemp(prefix="hq-shim-"))
    js = shim_dir / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    js.parent.mkdir(parents=True)
    js.write_text("")
    (shim_dir / "node.exe").write_text("")
    (shim_dir / "claude.cmd").write_text('@ECHO off\r\nIF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n)\r\n'
                                         'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  '
                                         '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js" %*\r\n')
    unwrapped = cc_mod.unwrap_shim(shim_dir / "claude.cmd")
    check("npm's claude.cmd is run as node + cli.js, not through cmd.exe",
          unwrapped and [Path(p).resolve() for p in unwrapped] == [(shim_dir / "node.exe").resolve(), js.resolve()], unwrapped)
    shutil.rmtree(shim_dir, ignore_errors=True)

    # ---- describe a team -> a new flow ------------------------------------------------------------
    n0 = len(cli_calls())
    s, d = call("/api/flows/design", {"prompt": "Two bug hunters review my code, then summarize"}, "POST")
    check("a description becomes a saved flow", s == 200 and d["flow"]["name"] == "Bug sweep"
          and any(f["id"] == d["flow"]["id"] for f in call("/api/flows")[1]["flows"]), d)
    nodes = {n["id"]: n for n in d["flow"]["nodes"]}
    check("draft is cleaned: safe ids and a done node added",
          "bug-hunters" in nodes and "done" in nodes
          and {"from": "merge", "to": "done"} in d["flow"]["edges"], list(nodes))
    check("a cluster based on a bot takes its look", nodes["bug-hunters"]["shape"] == "bug" and nodes["bug-hunters"]["color"] == "#6cc070")
    check("designed flows are laid out left to right", d["flow"]["dir"] == "lr"
          and nodes["master"]["x"] < nodes["bug-hunters"]["x"] < nodes["merge"]["x"] < nodes["done"]["x"])
    check("the designed flow is ready to run", d["problems"] == [], d["problems"])
    check("the Run menu opens with what you asked for", d["flow"]["task"] == "Two bug hunters review my code, then summarize")
    dc = agent_calls(n0)
    designed = d["flow"]
    s, r = call(f"/api/flows/{designed['id']}/run", {"task": "Check the login code", "folder": str(project)}, "POST")
    wait_run(r["run"])
    check("a flow remembers the last task you ran", call(f"/api/flows/{designed['id']}")[1]["flow"]["task"] == "Check the login code")
    check("one cheap designer call, no tools, knows your bots",
          len(dc) == 1 and dc[0]["flags"]["--tools"] == "" and dc[0]["flags"]["--model"] == "claude-sonnet-5-5"
          and "beetle = Beetle" in dc[0]["flags"]["--append-system-prompt"]
          and dc[0]["prompt"] == "Two bug hunters review my code, then summarize", dc)
    s, d = call("/api/flows/design", {"prompt": "BADJSON please"}, "POST")
    check("a draft that isn't a flow gives a clear error", s == 422 and "didn't return a flow" in d["error"], d)
    check("an empty description is refused", call("/api/flows/design", {"prompt": " "}, "POST")[0] == 400)

    # ---- folders ------------------------------------------------------------------------------
    check("Browse returns the folder picked", call("/api/pick-folder", {}, "POST")[1]["folder"] == str(project))
    check("folders you ran flows in are suggested, once each", call("/api/folders")[1]["folders"].count(str(project)) == 1)


    # ---- signed out ------------------------------------------------------------------------------
    Path(cli_dir, "state.json").write_text(json.dumps({"logged_in": False}))
    f = simple_flow({"name": "Anyone", "count": 1, "model": "claude-haiku-4-5"})
    run = wait_run(call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"])
    check("signed-out Claude Code gives a clear message", run["status"] == "failed"
          and "claude auth login" in run["nodes"]["c"]["agents"][0]["error"], run["nodes"]["c"]["agents"][0]["error"])
    Path(cli_dir, "state.json").write_text(json.dumps({"logged_in": True}))

    # ---- a run waiting when HQ closes is marked interrupted --------------------------------------
    rid = call(f"/api/flows/{ship['id']}/run", {"task": "late", "folder": str(project)}, "POST")[1]["run"]
    wait_run(rid, until=("waiting",))
    # opening Lithnode again while it runs just focuses the window: it must not touch the live server's runs
    subprocess.run([sys.executable, str(ROOT / "hq.py"), "--no-open"], env=server_env(), timeout=60)
    on_disk = json.loads((hq_home / "runs" / f"{rid}.json").read_text(encoding="utf-8"))
    check("a second launch leaves the live server's runs alone", on_disk["status"] in ("running", "waiting"), on_disk["status"])
finally:
    server.terminate()
    server.wait()

server = start_server()
try:
    s, r = call(f"/api/runs/{rid}")
    check("after a restart, an unfinished run shows as interrupted", r.get("status") == "interrupted"
          and r["nodes"]["ok"]["status"] == "stopped", r.get("status"))
    check("its saved reports are still there", "Builders report from" in r["nodes"]["build"]["output"])

    # ---- Quit stops the agents that are still working ----------------------------------------------
    f = simple_flow({"name": "SLOWSTAGE crew", "count": 2, "model": "claude-haiku-4-5"})
    rid = call(f"/api/flows/{f}/run", {"task": "go", "folder": str(project)}, "POST")[1]["run"]
    working = []
    for _ in range(30):
        working = [a["session_id"] for a in call(f"/api/runs/{rid}")[1]["nodes"]["c"]["agents"]]
        if len(working) == 2:
            break
        time.sleep(0.2)
    call("/api/quit", {}, "POST")
    server.wait(timeout=30)
    time.sleep(4.5)   # a killed agent never reaches its end
    check("Quit kills the agents still working", len(working) == 2 and not any(s in ends() for s in working), working)
finally:
    server.terminate()
    server.wait()


print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
