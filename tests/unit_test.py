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
time.sleep(0.8)
_js = engines.job_state("codex")
check("jobs: a running sign-in shows its link and progress", _js["busy"] and _js["url"] == "https://auth.example.com/x?y=1" and _js["pct"] == 42, _js)
check("jobs: the engines status carries the job", engines.all_status()["codex"].get("job", {}).get("busy") is True)
for _ in range(50):
    if not engines.job_state("codex")["busy"]:
        break
    time.sleep(0.1)
check("jobs: a finished sign-in leaves no error", engines.job_state("codex") == {"kind": "login", "busy": False, "url": "", "pct": None, "error": ""},
      engines.job_state("codex"))
engines._start_job("cursor", "install", [_py, "-c", "import sys; print('network is down'); sys.exit(3)"])
for _ in range(50):
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

# ---- settings: what the Settings window saves --------------------------------------------------------------------
check("settings: nothing saved means the defaults", settings.clean(None) == settings.DEFAULTS)
check("settings: junk is dropped, a sane value is kept", settings.clean({"limit": "x", "roles": "yes", "check_updates": False, "evil": 1})
      == {**settings.DEFAULTS, "check_updates": False})
check("settings: the token limit is clamped like a flow's", settings.clean({"limit": 5})["limit"] == 50_000)
check("settings: every offered limit survives cleaning", all(settings.clean({"limit": n})["limit"] == n for n in settings.LIMITS))

print()
if failures:
    print(f"{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1)
print("ALL PASSED")
