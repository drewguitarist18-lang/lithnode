"""Fast checks of the pure helpers: no server, no agents, no network. Runs in about a second.

    .venv\\Scripts\\python tests\\unit_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents  # noqa: E402
import engines  # noqa: E402
import flows  # noqa: E402
import settings  # noqa: E402
import updates  # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def raises(fn, kind=ValueError):
    try:
        fn()
    except kind:
        return True
    return False


# ---- agents: what an agent hands on, and how its steps read --------------------------------------------------
check("report: only what follows REPORT: is handed on", agents.report_of("thinking...\nREPORT: all good", 500) == "all good")
check("report: the last REPORT: wins", agents.report_of("REPORT: draft\nmore\nREPORT: final", 500) == "final")
check("report: **REPORT:** leaves no stray **", agents.report_of("**REPORT:** all good", 500) == "all good")
check("report: bold right after the marker is kept", agents.report_of("REPORT: **Found** a bug", 500) == "**Found** a bug")
check("report: _REPORT:_ and __REPORT:__ too", agents.report_of("__REPORT:__ ok", 500) == "ok" and agents.report_of("*REPORT:* fine", 500) == "fine")
check("report: no marker hands on the whole answer", agents.report_of("just text", 500) == "just text")
long = agents.report_of("REPORT: " + "x" * 50, 10)
check("report: a long one is cut and says so", long.startswith("x" * 10) and "cut to save credits" in long, long)
check("report: empty is empty", agents.report_of("", 500) == "" and agents.report_of(None, 500) == "")

check("tokens read short", (agents.short_tokens(1234), agents.short_tokens(291_000), agents.short_tokens(2_500_000))
      == ("1k tokens", "291k tokens", "2.5M tokens"))
check("a Read step names the file, not the path", agents.describe("Read", {"file_path": "C:/x/session.ts"}) == "Reading session.ts")
check("a web search shows its query", agents.describe("WebSearch", {"query": "rust async"}) == "Searching the web: rust async")

# ---- flows: what gets saved and what can run --------------------------------------------------------------------
check("token limit: junk falls back to 1M", flows.clean_limit("abc") == 1_000_000)
check("token limit: clamped to 50k..100M", flows.clean_limit(5) == 50_000 and flows.clean_limit(10**12) == 100_000_000)
check("token limit: a sane one is kept", flows.clean_limit(500_000) == 500_000)
check("focuses: a list from a drafted flow becomes one line per agent", flows._focuses(["Logic", "Security  holes"]) == "Logic\nSecurity holes")
check("focuses: a list an older version saved as text is mended", flows._focuses("['Hooks, surprises', 'Trims']") == "Hooks, surprises\nTrims")
check("focuses: plain lines and odd text are left alone", flows._focuses("a\nb") == "a\nb" and flows._focuses("[not a list") == "[not a list"
      and flows._focuses(None) == "")
check("a loop is caught", flows._has_cycle(["a", "b"], [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]))
check("a straight line isn't a loop", not flows._has_cycle(["a", "b"], [{"from": "a", "to": "b"}]))
ship = flows.from_template("ship-it")
check("the ship-it template is ready to run", ship and len(ship["nodes"]) == 9 and flows.check_runnable(ship) == [], ship and flows.check_runnable(ship))
check("an unknown template is None", flows.from_template("nope") is None)
_teams = {"nodes": [{"id": "s", "type": "master", "mode": "pass"},
                    {"id": "c", "type": "cluster", "role": "think", "engine": "codex", "engine_model": "old"},
                    {"id": "k", "type": "cluster", "role": "run", "engine": "cursor"},
                    {"id": "h", "type": "cluster", "role": "", "engine": "codex", "engine_model": "gpt-hand"}],
          "engine_models": {"codex": {"think": "gpt-5.5", "build": "bad model!"}}}
_cf = {n["id"]: n for n in flows.clean_flow(_teams)["nodes"]}
check("a Codex role takes the flow's pick for that role", _cf["c"]["engine_model"] == "gpt-5.5", _cf["c"])
check("a role with no pick uses the CLI's own default", _cf["k"]["engine_model"] == "", _cf["k"])
check("a model picked by hand is kept", _cf["h"]["engine_model"] == "gpt-hand", _cf["h"])
check("a bad role model is dropped", flows.clean_flow(_teams)["engine_models"]["codex"]["build"] == "")
# every engine, every role: the flow's pick for that role reaches the CLI's command line
_picks = {"codex": {"think": "gpt-6-luna", "build": "gpt-5.6-terra", "run": "gpt-5.6-luna"},
          "cursor": {"think": "claude-4.5-opus-thinking", "build": "gpt-5.1-codex", "run": "composer-1"},
          "ollama": {"think": "qwen3:14b", "build": "llama3.2:latest", "run": "hf.co/unsloth/gemma-3:Q4"}}
_all = flows.clean_flow({"engine_models": _picks, "nodes": [{"id": f"{e}-{r}", "type": "cluster", "role": r, "engine": e}
                                                            for e in _picks for r in ("think", "build", "run")]})
_got = {n["id"]: n["engine_model"] for n in _all["nodes"]}
check("roles: each engine's team gets its role's model", all(_got[f"{e}-{r}"] == m for e in _picks for r, m in _picks[e].items()), _got)
check("roles: Codex and Cursor get it as --model", all(
    engines.build_args(e, ["x"], tools="read", model=_got[f"{e}-{r}"])[-3:-1] == ["--model", _picks[e][r]] if e == "codex"
    else engines.build_args(e, ["x"], tools="read", model=_got[f"{e}-{r}"])[-2:] == ["--model", _picks[e][r]]
    for e in ("codex", "cursor") for r in ("think", "build", "run")))
_off = flows.clean_flow({"roles": False, "nodes": [{"id": "t", "type": "cluster", "role": "think", "model": "claude-haiku-4-5"}]})
check("with roles off a team keeps its own model and has no role", _off["roles"] is False
      and (_off["nodes"][0]["role"], _off["nodes"][0]["model"]) == ("", "claude-haiku-4-5"), _off["nodes"][0])
check("roles are on by default", flows.clean_flow({"nodes": []})["roles"] is True)
check("every template is ready to run", all(flows.check_runnable(flows.from_template(t["id"])) == [] for t in flows.TEMPLATES),
      [t["id"] for t in flows.TEMPLATES if flows.check_runnable(flows.from_template(t["id"]))])
check("an unknown node type is refused", raises(lambda: flows.clean_node({"id": "a", "type": "bogus"})))
check("model names can't be command-line flags", flows.MODEL_RE.match("--help") is None and flows.MODEL_RE.match("claude-sonnet-5-5"))

fence = "```"
check("items: a fenced list is read", flows.parse_items(f"x\n{fence}items\n[{{\"title\": \"a\"}}]\n{fence}") == [{"title": "a"}])
check("items: the fence is stripped from the text", flows.strip_items(f"hi\n{fence}items\n[]\n{fence}") == "hi")
check("webhooks: https is fine, file: isn't", flows.webhook_ok("https://ntfy.sh/x") and not flows.webhook_ok("file:///c:/x"))
check("design: no JSON is a friendly error", raises(lambda: flows.parse_design("no json here")))
_codex_design = flows.build_design({"name": "Codex flow", "nodes": [
    {"id": "master", "type": "master", "mode": "brief"},
    {"id": "work", "type": "cluster", "name": "Work", "instructions": "Do the job."},
    {"id": "merge", "type": "checkpoint", "mode": "summarize"},
    {"id": "done", "type": "done"}],
    "edges": [["master", "work"], ["work", "merge"], ["merge", "done"]]}, [], engine="codex")
check("design: a Codex-built flow keeps Codex for every agent stage",
      all(n.get("engine") == "codex" for n in _codex_design["nodes"] if n["type"] in ("master", "cluster", "checkpoint")), _codex_design)

# ---- ollama: a free local model, through a stand-in Ollama server on this computer ------------------------------
import json  # noqa: E402
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

_asked = []


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": "tiny:latest"}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        _asked.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        for piece in ("Red, ", "blue, ", "yellow."):
            self.wfile.write(json.dumps({"message": {"content": piece}, "done": False}).encode() + b"\n")
        self.wfile.write(b'{"done": true}\n')


_srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
engines.OLLAMA_URL = f"http://127.0.0.1:{_srv.server_address[1]}"
_st = engines.status("ollama", force=True)
check("ollama: ready once its server has a model", _st["installed"] and _st["signed_in"] and _st.get("local"), _st)
check("ollama: its downloaded models are the choices", engines.models("ollama", force=True) == [{"id": "tiny:latest", "label": "tiny"}])
_ag = agents.Agent(model="", effort="low", tools="none", system="Be terse.", prompt="Three colors?", cwd=".", on_update=lambda: None, engine="ollama")
check("ollama: a session streams the model's answer into the report", _ag.run() and _ag.text == "Red, blue, yellow.", (_ag.text, _ag.error))
check("ollama: it uses the first downloaded model, with the role as the system message",
      _asked and _asked[0]["model"] == "tiny:latest" and _asked[0]["messages"][0] == {"role": "system", "content": "Be terse."}, _asked)
_ag = agents.Agent(model="", effort="low", tools="none", system="x", prompt="y", cwd=".", on_update=lambda: None, engine="ollama",
                   engine_model="qwen3:14b")
check("ollama: a role's model is the one asked", _ag.run() and _asked[-1]["model"] == "qwen3:14b", _asked[-1])
_srv.shutdown()
engines.OLLAMA_URL = "http://127.0.0.1:9"
_st = engines.status("ollama", force=True)
check("ollama: no server means not ready", not _st["signed_in"] and _st["note"], _st)

# ---- engine jobs: install / sign-in run hidden in the background; the card reads their link, progress and errors ---
import os  # noqa: E402
import time  # noqa: E402

_py = sys.executable
engines._start_job("codex", "login", [_py, "-c", "import time; print('Open https://auth.example.com/x?y=1 to sign in'); "
                                                 "print('pulling 42%', end='\\r', flush=True); time.sleep(5)"])
for _ in range(40):   # the child prints within a moment; a busy machine can take a few seconds to start Python
    _js = engines.job_state("codex")
    if _js["url"] and _js["pct"] is not None:
        break
    time.sleep(0.1)
check("jobs: a running sign-in shows its link and progress", _js["busy"] and _js["url"] == "https://auth.example.com/x?y=1" and _js["pct"] == 42, _js)
check("jobs: the engines status carries the job", engines.all_status()["codex"].get("job", {}).get("kind") == "login")
for _ in range(100):
    if not engines.job_state("codex")["busy"]:
        break
    time.sleep(0.1)
check("jobs: a finished sign-in leaves no error", engines.job_state("codex") == {"kind": "login", "busy": False, "url": "", "pct": None, "error": ""},
      engines.job_state("codex"))
engines._start_job("cursor", "install", [_py, "-c", "import sys; print('network is down'); sys.exit(3)"])
for _ in range(100):
    if not engines.job_state("cursor")["busy"]:
        break
    time.sleep(0.1)
check("jobs: a failed install says what it last printed", engines.job_state("cursor")["error"] == "The install didn't finish: network is down",
      engines.job_state("cursor"))
os.environ["LITHNODE_CODEX_CMD"] = json.dumps([_py, "-c", "import sys; sys.exit(0 if sys.argv[1:] == ['logout'] else 1)"])
check("sign out: runs the CLI's own logout", engines.sign_out("codex") == (True, "Signed out of Codex.") and engines.job_state("codex") is None)
os.environ["LITHNODE_CODEX_CMD"] = json.dumps([_py, "-c", "import sys; print('no session'); sys.exit(1)"])
check("sign out: a failure says why", engines.sign_out("codex") == (False, "Couldn't sign out of Codex: no session"))
del os.environ["LITHNODE_CODEX_CMD"]
check("sign out: Ollama has no account", not engines.sign_out("ollama")[0])

# ---- Antigravity: agy reads one JSON message on stdin and streams step_update events, then a result ---------------
import tempfile  # noqa: E402

_fake_agy = Path(tempfile.mkdtemp()) / "agy.py"
_fake_agy.write_text(r'''
import json, sys
if sys.argv[1:] == ["models"]:
    print("Fetching available models...\ngemini-x-high\tGemini X (High)\nclaude-y\tClaude Y"); sys.exit(0)
msg = json.loads(sys.stdin.readline())
open(sys.argv[0] + ".seen", "w").write(json.dumps({"args": sys.argv[1:], "msg": msg}))
ev = lambda **k: print(json.dumps(k), flush=True)
ev(event="init", init={"cwd": "."})
ev(event="step_update", step_update={"step_type": "tool", "state": "ACTIVE", "tool_name": "read_file", "tool_info": {"parameters": {"Path": "C:\\w\\notes.md"}}})
ev(event="step_update", step_update={"step_type": "agent_response", "state": "ACTIVE", "text_delta": "All "})
ev(event="step_update", step_update={"step_type": "agent_response", "state": "DONE", "text_delta": "good."})
ev(event="result", result={"status": "SUCCESS", "response": "All good.\n"})
''')
os.environ["LITHNODE_AGY_CMD"] = json.dumps([_py, str(_fake_agy)])
check("antigravity: its models come from `agy models`", engines.models("antigravity", force=True)
      == [{"id": "gemini-x-high", "label": "Gemini X (High)"}, {"id": "claude-y", "label": "Claude Y"}])
_steps = []
_ag = agents.Agent(model="", effort="low", tools="read", system="Review it.", prompt="Check notes.md", cwd=".",
                   on_update=lambda: _steps.append(_ag.step), engine="antigravity", engine_model="gemini-x-high")
check("antigravity: a session's answer is the report", _ag.run() and _ag.text == "All good.", (_ag.text, _ag.error))
_seen = json.loads(Path(str(_fake_agy) + ".seen").read_text())
check("antigravity: the prompt goes in as one JSON user message, role first",
      _seen["msg"]["event"] == "user" and _seen["msg"]["message"]["content"].startswith("# Your instructions\nReview it."), _seen["msg"])
check("antigravity: the role's model is passed", _seen["args"][-2:] == ["--model", "gemini-x-high"], _seen["args"])
_rules = json.loads(_seen["args"][_seen["args"].index("--settings") + 1])["permissions"]
check("antigravity: a read-only team can't write, run commands or browse", {"write_file(*)", "command(*)", "read_url(*)"} <= set(_rules["deny"])
      and "--dangerously-skip-permissions" not in _seen["args"], _seen["args"])
check("antigravity: its tool use shows as a step", "Reading notes.md" in _steps, _steps)
_full = engines.build_args("antigravity", ["agy"], tools="all")
check("antigravity: an all-tools team runs without prompts and no deny rules", "--dangerously-skip-permissions" in _full and "--settings" not in _full, _full)
check("antigravity: an edit team auto-accepts edits but can't run commands",
      "accept-edits" in engines.build_args("antigravity", ["agy"], tools="edit") and "command(*)" in engines.AGY_RULES["edit"]["deny"])
_out = {"texts": [], "final": None, "error": ""}
engines.agy_event({"event": "result", "result": {"status": "ERROR", "error": "authentication required"}}, _out)
check("antigravity: a failed run reports its error, in plain words when signed out",
      "isn't signed in" in engines.friendly_error("antigravity", _out["error"]), _out)
del os.environ["LITHNODE_AGY_CMD"]

# ---- updates: is the release on GitHub newer than this one ---------------------------------------------------
check("updates: versions read as numbers", updates.parse("v0.1.21") == (0, 1, 21) and updates.parse("0.2") == (0, 2))
check("updates: 0.1.100 is newer than 0.1.21 (not a string compare)", updates.newer("v0.1.100", "0.1.21"))
check("updates: same or older isn't newer", not updates.newer("v0.1.21", "0.1.21") and not updates.newer("v0.1.9", "0.1.21"))
check("updates: junk tags are never newer", not updates.newer("nightly", "0.1.21") and not updates.newer("", "0.1.21"))
check("updates: each OS gets its own installer", updates.download_url("v1.0.0", "win32").endswith("/v1.0.0/LithnodeSetup.exe")
      and updates.download_url("v1.0.0", "darwin").endswith(".dmg") and updates.download_url("v1.0.0", "linux").endswith(".flatpak"))

# ---- Update now (Windows): download the installer, then run it with no windows; it reopens Lithnode -------------
import io  # noqa: E402
import subprocess  # noqa: E402

GOOD = f"https://github.com/{updates.REPO}/releases/download/v9.9.9/LithnodeSetup.exe"
check("update: a copy that isn't the Windows install says to download instead", not updates.start_update(GOOD)[0])
real_can, real_open, real_popen, launched = updates.can_self_update, updates.urlrequest.urlopen, subprocess.Popen, []


class FakeResp(io.BytesIO):
    headers = {"Content-Length": "0"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_update(body, url=GOOD):
    launched.clear()
    updates._job.update(state="", pct=0, error="")
    resp = FakeResp(body)
    resp.headers = {"Content-Length": str(len(body))}
    updates.urlrequest.urlopen = lambda req, timeout=0: resp
    ok, _ = updates.start_update(url)
    for _ in range(100):
        if updates.job()["state"] not in ("downloading",):
            break
        time.sleep(0.05)
    return ok, updates.job()


try:
    updates.can_self_update = lambda: True
    subprocess.Popen = lambda argv, **kw: launched.append(argv)
    ok, j = run_update(b"MZ" + b"\0" * 5000)
    check("update: downloads the installer and runs it silently, reopening Lithnode", ok and j["state"] == "installing"
          and launched and {"/VERYSILENT", "/SUPPRESSMSGBOXES", "/RELAUNCH=1"} <= set(launched[0])
          and any(a in ("/PET=yes", "/PET=no") for a in launched[0]), (j, launched))
    ok, j = run_update(b"<html>not an installer</html>")
    check("update: a download that isn't a program is never run", j["state"] == "failed" and not launched, (j, launched))
    check("update: only Lithnode's own GitHub releases", not updates.start_update("https://evil.example/LithnodeSetup.exe")[0])
finally:
    updates.can_self_update, updates.urlrequest.urlopen, subprocess.Popen = real_can, real_open, real_popen
    updates._job.update(state="", pct=0, error="")

# ---- sign-in links: Cursor's CLI updates itself first and may print a Git for Windows link before its own ---------
said = ("Done\nGit for Windows is required. Install it from https://git-scm.com/download/win and include Git Bash.\n"
        "Open a browser and navigate to this link: https://cursor.com/loginDeepControl?challenge=x&uuid=y")
check("cursor sign-in: shows the cursor.com link, not the Git one",
      engines._job_link("cursor", "login", said) == "https://cursor.com/loginDeepControl?challenge=x&uuid=y")
check("cursor sign-in: no link yet while only the Git notice is out", engines._job_link("cursor", "login", said.split("Open")[0]) == "")

# ---- settings: what the Settings window saves --------------------------------------------------------------------
check("settings: nothing saved means the defaults", settings.clean(None) == settings.DEFAULTS)
check("settings: junk is dropped, a sane value is kept", settings.clean({"limit": "x", "roles": "yes", "check_updates": False, "evil": 1})
      == {**settings.DEFAULTS, "check_updates": False})
check("settings: the token limit is clamped like a flow's", settings.clean({"limit": 5})["limit"] == 50_000)
check("settings: every offered limit survives cleaning", all(settings.clean({"limit": n})["limit"] == n for n in settings.LIMITS))

# ---- too-heavy warning: how many project files a folder has --------------------------------------------------------
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    for rel in ("a.py", "src/b.py", "src/c.js", ".env", "node_modules/x/y.js", ".git/HEAD", "dist/out.js"):
        (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(tmp) / rel).write_text("x", encoding="utf-8")
    check("folder size: counts the project's files, skips dependencies, build output and dotfiles", flows.count_files(tmp) == 3)
    check("folder size: stops at the cap", flows.count_files(tmp, cap=2) == 2)
check("folder size: a missing folder is zero", flows.count_files(Path(tempfile.gettempdir()) / "no-such-lithnode-folder") == 0)

# ---- wiring: work that never reaches Done ------------------------------------------------------------------------
def _wired(edges):
    return flows.clean_flow({"name": "W", "nodes": [{"id": "master", "type": "master", "mode": "pass"}, {"id": "a", "type": "cluster", "name": "Sorter"},
                                                     {"id": "b", "type": "cluster", "name": "Debugger"}, {"id": "done", "type": "done"}],
                             "edges": [{"from": x, "to": y} for x, y in edges]})


check("wiring: a team wired into nothing is a problem, named", any("Debugger isn't wired into anything" in p
      for p in flows.check_runnable(_wired([("master", "a"), ("a", "b"), ("master", "done")]))))
check("wiring: everything reaching Done is fine", flows.check_runnable(_wired([("master", "a"), ("a", "b"), ("b", "done")])) == [])
_fixed = flows.build_design({"name": "Sort", "nodes": [{"id": "master", "type": "master", "mode": "pass"}, {"id": "a", "type": "cluster", "name": "Sorter"},
                                                      {"id": "b", "type": "cluster", "name": "Debugger"}, {"id": "done", "type": "done"}],
                             "edges": [["master", "a"], ["a", "b"], ["master", "done"]]}, [])
check("wiring: a designed flow's loose end goes into Done, and Start no longer skips the teams",
      {(e["from"], e["to"]) for e in _fixed["edges"]} == {("master", "a"), ("a", "b"), ("b", "done")} and flows.check_runnable(_fixed) == [])

_early = {"name": "Early", "nodes": [{"id": "master", "type": "master", "mode": "pass"}, {"id": "cp", "type": "checkpoint", "name": "Collect Results"},
                                    {"id": "a", "type": "cluster", "name": "Sorter"}, {"id": "done", "type": "done"}],
          "edges": [{"from": "master", "to": "cp"}, {"from": "cp", "to": "a"}, {"from": "a", "to": "done"}]}
check("wiring: a checkpoint before any team has nothing to collect, and says so",
      any("Collect Results comes before any team" in p for p in flows.check_runnable(flows.clean_flow(_early))))
_cut = flows.build_design({**_early, "edges": [[e["from"], e["to"]] for e in _early["edges"]]}, [])
check("wiring: the designer cuts such a checkpoint out and joins the wires",
      [n["type"] for n in _cut["nodes"]] == ["master", "cluster", "done"] and {(e["from"], e["to"]) for e in _cut["edges"]} == {("master", "a"), ("a", "done")})

# ---- widgets: extras pinned to the canvas, saved with the flow ---------------------------------------------------------
_w = flows.clean_flow({**_early, "widgets": [{"id": "Note 1!", "type": "note", "x": 10, "y": 20, "w": 5, "h": "x", "text": "hi", "color": "red"},
                                             {"type": "output", "node": "a"}, {"type": "output", "node": "gone"}, {"type": "evil"}, "junk"]})["widgets"]
check("widgets: kept with the flow, sizes and colors made sane, unknown kinds dropped",
      [(w["id"], w["type"]) for w in _w] == [("note1", "note"), ("w2", "output"), ("w3", "output")]
      and _w[0] == {"id": "note1", "type": "note", "x": 10, "y": 20, "w": 150, "h": 170, "text": "hi", "color": flows.WIDGET_COLORS[0]}, _w)
check("widgets: live output keeps its team only while that team exists", (_w[1]["node"], _w[2]["node"]) == ("a", ""))
check("widgets: a flow without any still loads", flows.clean_flow(_early)["widgets"] == [])
import agents as _agents  # noqa: E402

check("tokens: re-reading the conversation from the cache counts a tenth toward a limit",
      _agents.used_tokens({"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 400_000}) == 41_700
      and _agents.used_tokens({}) == 0)
# ---- a follow-up for one team, and what a live run wants from you ----------------------------------------------------
import types  # noqa: E402

_whole = flows.clean_flow({"name": "W", "nodes": [{"id": "s", "type": "master"}, {"id": "b", "type": "cluster", "name": "Builders", "retry": 2},
                                                  {"id": "c", "type": "cluster", "name": "Checkers"}, {"id": "d", "type": "done"}],
                           "edges": [{"from": "s", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}]})
_one = flows.only_team({**_whole, "id": "abc"}, "c")
check("one team: the cut flow says it is one team", _one.get("only") == "c")
check("follow-up: one team alone is Start, that team, Done, and can run",
      [n["id"] for n in _one["nodes"]] == ["s", "c", "d"] and _one["edges"] == [{"from": "s", "to": "c"}, {"from": "c", "to": "d"}]
      and _one["id"] == "abc" and not flows.check_runnable(_one), _one)
try:
    flows.only_team(_whole, "d")
    _bad = False
except ValueError:
    _bad = True
check("follow-up: a step that isn't a team is refused", _bad)
_live = types.SimpleNamespace(id="r1", flow={"name": "Ship", "nodes": [{"id": "ok", "name": "Your call", "message": "Approve to ship."}, {"id": "b", "name": "Builders"}]},
                              nodes={"ok": {"status": "approval", "started": 5, "agents": []},
                                     "b": {"status": "running", "agents": [{"name": "Builder 1", "status": "running", "started": 100, "seen": 100},
                                                                           {"name": "Builder 2", "status": "running", "started": 100, "seen": 690}]}})
_needs, _quiet = flows.attention([_live], now=700)
check("alerts: a waiting approval says which flow and what it asks",
      [(n["kind"], n["flow"], n["text"], n["run"]) for n in _needs] == [("approval", "Ship", "Approve to ship.", "r1")], _needs)
check("alerts: only the agent that has shown nothing for five minutes counts as quiet",
      [(q["who"], q["minutes"]) for q in _quiet] == [("Builder 1", 10)], _quiet)
_live.nodes["ok"]["question"] = {"agent": "Builder 1", "text": "Which file?"}
_n2 = flows.attention([_live], now=700)[0]
check("alerts: an agent's question is told apart from an approval, with its own key",
      _n2[0]["kind"] == "question" and _n2[0]["who"] == "Builder 1" and _n2[0]["key"] != _needs[0]["key"], _n2)
_w2 = {w["type"]: w for w in flows.clean_flow({**_early, "widgets": [
    {"type": "checklist", "items": [{"text": "  Tests   pass ", "done": True}, {"text": ""}, "junk", {"text": "x" * 300}], "pin": "a", "px": 30, "py": -40},
    {"type": "group", "text": "G" * 90, "pin": "a"}, {"type": "file", "file": "out.md", "pin": "gone"}, {"type": "approve"}]})["widgets"]}
check("widgets: a checklist keeps clean items, a pin holds only to a step that exists, and groups are gone",
      _w2["checklist"]["items"] == [{"text": "Tests pass", "done": True}, {"text": "x" * 120, "done": False}]
      and (_w2["checklist"]["pin"], _w2["checklist"]["px"], _w2["checklist"]["py"]) == ("a", 30, -40)
      and "pin" not in _w2["file"] and "group" not in _w2 and _w2["file"]["file"] == "out.md"
      and "approve" in _w2, _w2)
with tempfile.TemporaryDirectory() as _pd:
    _pp = Path(_pd)
    (_pp / "a.txt").write_text("hello", encoding="utf-8")
    (_pp / "b.bin").write_bytes(b"\0\1\2")
    (_pp / "c.png").write_bytes(b"\x89PNG")
    check("file preview: text as text, a picture as a data URL, anything else says why not",
          flows.read_for_preview(_pp / "a.txt") == {"text": "hello"} and "error" in flows.read_for_preview(_pp / "b.bin")
          and flows.read_for_preview(_pp / "c.png")["image"].startswith("data:image/png;base64,") and "error" in flows.read_for_preview(_pp / "gone.txt"))

# ---- fix-it, saved jobs, schedules, history, follow-ups, previews --------------------------------------------------
_bad = flows.clean_flow({"name": "Bad", "nodes": [{"id": "master", "type": "master", "mode": "pass"}, {"id": "cp", "type": "checkpoint", "name": "Collect"},
                                                  {"id": "a", "type": "cluster", "name": "Sorter"}, {"id": "b", "type": "cluster", "name": "Debugger"},
                                                  {"id": "done", "type": "done"}],
                         "edges": [{"from": "master", "to": "cp"}, {"from": "cp", "to": "a"}, {"from": "a", "to": "b"}, {"from": "master", "to": "done"}]})
_good, _did = flows.repair(_bad)
check("fix it: the checkpoint goes, the loose end is wired in, Start stops skipping the teams, and it says what it did",
      {(e["from"], e["to"]) for e in _good["edges"]} == {("master", "a"), ("a", "b"), ("b", "done")} and len(_did) == 3
      and flows.check_runnable(flows.clean_flow(_good)) == [], _did)
check("fix it: a good flow is left alone", flows.repair(flows.clean_flow(_good))[1] == [])
_j = flows.clean_flow({**_early, "jobs": [{"task": "Sort the weekly export by date", "folder": "C:/data"}, {"name": "Sort the weekly export by", "task": "x y"},
                                          {"name": "Empty", "task": " "}, "junk"], "schedule": {"on": True, "every": "weekday", "at": "9:5", "task": "Do it"}})
check("saved jobs: named from the task when unnamed, no duplicates, no empty ones",
      _j["jobs"] == [{"name": "Sort the weekly export by", "task": "Sort the weekly export by date", "folder": "C:/data"}], _j["jobs"])
check("schedule: a bad time falls back, and it needs a job to be on", _j["schedule"] == {"on": True, "every": "weekday", "at": "09:00", "task": "Do it", "folder": ""}
      and flows.clean_schedule({"on": True})["on"] is False)
from datetime import datetime  # noqa: E402

_s = {"on": True, "every": "weekday", "at": "09:00", "task": "x", "folder": ""}
check("schedule: fires in its slot once, not before, not hours late, not at the weekend",
      flows.schedule_due(_s, datetime(2026, 11, 16, 9, 3)) == "2026-11-16" and flows.schedule_due(_s, datetime(2026, 11, 16, 9, 3), "2026-11-16") == ""
      and flows.schedule_due(_s, datetime(2026, 11, 16, 8, 59)) == "" and flows.schedule_due(_s, datetime(2026, 11, 16, 13, 0)) == ""
      and flows.schedule_due(_s, datetime(2026, 11, 14, 9, 3)) == "" and flows.schedule_due({**_s, "on": False}, datetime(2026, 11, 16, 9, 3)) == "")
check("schedule: hourly fires each hour at its minute", flows.schedule_due({**_s, "every": "hour", "at": "00:30"}, datetime(2026, 11, 14, 15, 31)) == "2026-11-14 15"
      and flows.schedule_due({**_s, "every": "hour", "at": "00:30"}, datetime(2026, 11, 14, 15, 29)) == "")
_runs = [{"flow_id": "f", "status": "done", "tokens": t, "started": 0, "ended": s} for t, s in ((100, 10), (300, 30), (200, 20))] + [
    {"flow_id": "f", "status": "failed", "tokens": 9, "started": 0, "ended": 1}, {"flow_id": "g", "status": "done", "tokens": 5, "started": 0, "ended": 1},
    {"flow_id": "f", "status": "done", "tokens": 7, "started": 0, "ended": 1, "only": "c"}]   # a one-team follow-up doesn't count
check("history: what this flow's finished runs used", flows.run_history(_runs, "f") == {"runs": 3, "tokens": 200, "low": 100, "high": 300, "seconds": 20}
      and flows.run_history(_runs, "none") == {})
check("follow-up: carries the earlier job and result", "## The earlier job\nSort it" in flows.follow_up("Now chart it", {"task": "Sort it", "final": "Sorted."})
      and "## What that run produced\nSorted." in flows.follow_up("Now chart it", {"task": "Sort it", "final": "Sorted."}))
_f1 = flows.follow_up("Now chart it", {"task": "Sort it", "final": "Sorted."})
_f2 = flows.follow_up("Add a legend", {"task": _f1, "final": "Charted."})
check("follow-up: shows only what you typed, and a second one doesn't nest the first", flows.job_of(_f1) == "Now chart it"
      and flows.job_of("Plain job") == "Plain job" and _f2.count(flows.FOLLOW_MARK) == 1 and "## The earlier job\nNow chart it\n" in _f2)
check("preview: read from the answer, junk refused", flows.parse_dryrun('ok {"steps": [{"team": "Sorter", "does": "Sorts it."}, {"team": ""}], "watch": "x"}', _bad)
      == {"steps": [{"team": "Sorter", "does": "Sorts it."}], "watch": "x"} and raises(lambda: flows.parse_dryrun("nope", _bad)))

# ---- what a run changed, and putting it back ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    proj, pic = Path(tmp) / "proj", Path(tmp) / "pic"
    for rel, body in (("a.txt", "one\ntwo\n"), ("keep.txt", "same\n"), ("gone.txt", "bye\n"), ("node_modules/x.js", "dep")):
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text(body, encoding="utf-8")
    check("changes: a before-picture is taken of the folder's own files", flows.snapshot_folder(proj, pic) and (pic / "files" / "a.txt").is_file()
          and not (pic / "files" / "node_modules").exists())
    check("changes: nothing changed means nothing listed", flows.folder_changes(proj, pic) == [])
    (proj / "a.txt").write_text("one\nTWO\nthree\n", encoding="utf-8")
    (proj / "new.txt").write_text("hi\n", encoding="utf-8")
    (proj / "gone.txt").unlink()
    _ch = {c["file"]: c for c in flows.folder_changes(proj, pic)}
    check("changes: new, changed and deleted files, with line counts", {f: (c["kind"], c["added"], c["removed"]) for f, c in _ch.items()}
          == {"a.txt": ("changed", 2, 1), "gone.txt": ("deleted", 0, 1), "new.txt": ("new", 1, 0)} and "+TWO" in _ch["a.txt"]["diff"], _ch)
    check("changes: undo puts every file back", flows.undo_changes(proj, pic) == 3 and (proj / "a.txt").read_text(encoding="utf-8") == "one\ntwo\n"
          and (proj / "gone.txt").is_file() and not (proj / "new.txt").exists() and flows.folder_changes(proj, pic) == [])
check("changes: no folder, no picture", flows.snapshot_folder(Path(tempfile.gettempdir()) / "no-such-lithnode-folder", Path(tempfile.gettempdir()) / "x") is False)

# ---- the check before a run: what it asks, and how answers reach the team ---------------------------------------------
check("precheck: questions are read out of the answer, at most 3", flows.parse_precheck(
    'Sure: {"ok": false, "questions": [{"q": "Where  are the columns?", "kind": "folder"}, {"q": "By what?", "kind": "weird"}, "And?", {"q": "4"}]}')
      == [{"q": "Where are the columns?", "kind": "folder"}, {"q": "By what?", "kind": "text"}, {"q": "And?", "kind": "text"}])
check("precheck: ok, junk or no questions all mean start the run",
      [flows.parse_precheck(s) for s in ('{"ok": true}', "no json here", '{"ok": false}', '{"ok": false, "questions": []}', "{broken")] == [[]] * 5)
check("precheck: answers are added to the job, blanks left out", flows.with_answers("Sort it", [{"q": "Where?", "a": " C:/data "}, {"q": "How?", "a": ""}])
      == "Sort it\n\nAsked before the run started, and the user's answers:\n- Where?\n  C:/data")
check("precheck: no answers leaves the job alone", flows.with_answers("Sort it", None) == "Sort it" and flows.with_answers("Sort it", [{"q": "x"}]) == "Sort it")
with tempfile.TemporaryDirectory() as tmp:
    for rel in ("data.csv", "src/a.py", ".env", "node_modules/x.js"):
        (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(tmp) / rel).write_text("x", encoding="utf-8")
    check("precheck: the folder is shown by its top level, folders first, junk skipped", flows.folder_glance(tmp) == "src/, data.csv")
    said = flows.precheck_prompt({"nodes": [{"type": "cluster", "name": "Sorter", "tools": "edit"}]}, "Sort the columns", tmp)
    check("precheck: the checker sees the job, the folder and what the team can do", "Sort the columns" in said and "data.csv" in said and "Sorter (edits files)" in said)
check("precheck: no folder is said plainly", "empty scratch folder" in flows.precheck_prompt({"nodes": []}, "x", ""))
check("settings: the pre-run check is on by default and can be turned off", settings.DEFAULTS["precheck"] is True and settings.clean({"precheck": False})["precheck"] is False)

print()
if failures:
    print(f"{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1)
print("ALL PASSED")
