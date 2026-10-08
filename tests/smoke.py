"""End-to-end smoke test for the app around Flows: pages, bots, sign-in and the localhost checks.

    .venv\\Scripts\\python tests\\smoke.py

Runs the real hq.py against tests/mock_claude.py (a stand-in `claude` CLI). Flows have their own suite.
"""
import atexit
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
APP = 8791
URL = f"http://127.0.0.1:{APP}"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def call(path, body=None, method=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except error.HTTPError as e:
        return e.code, e.read().decode()


def bots():
    return json.loads(call("/api/bots")[1])["bots"]


def set_cli(logged_in):
    Path(cli_dir, "state.json").write_text(json.dumps({"logged_in": logged_in}))


def cli_calls():
    log = Path(cli_dir, "calls.jsonl")
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def start():
    env = {**os.environ, "LITHNODE_PORT": str(APP), "CLAWD_BOT_HOME": str(home), "CLAWD_PET_HOME": str(home),
           "LITHNODE_HOME": str(Path(home) / "lithnode"),
           "CLAWD_BOT_CLAUDE_CMD": json.dumps([sys.executable, str(ROOT / "tests" / "mock_claude.py")]),
           "CLAWD_MOCK_STATE": str(Path(cli_dir, "state.json")), "CLAWD_MOCK_LOG": str(Path(cli_dir, "calls.jsonl")),
           "CLAWD_MOCK_SESSIONS": str(Path(cli_dir, "sessions.json"))}
    p = subprocess.Popen([sys.executable, str(ROOT / "hq.py"), "--no-open"], env=env)
    for _ in range(80):
        try:
            call("/api/ping")
            return p
        except OSError:
            time.sleep(0.1)
    raise SystemExit("server did not start")


home = tempfile.mkdtemp(prefix="clawdbot-test-")
cli_dir = tempfile.mkdtemp(prefix="clawdbot-cli-")
atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True) for d in (home, cli_dir)])   # leave no test folders behind

set_cli(True)
server_proc = start()
try:
    # ---- pages: Flows and Office only ------------------------------------------------------
    s, body = call("/")
    check("serves the window with Flows and Office tabs", s == 200 and 'data-tab="flows"' in body and 'data-tab="office"' in body)
    check("there is no Chat tab or page", 'data-tab="chat"' not in body and call("/chat")[0] == 404
          and call("/static/chat.html")[0] == 404)
    check("chat routes are gone", all(call(p, {} if m == "POST" else None, m)[0] == 404
                                      for p, m in [("/api/chat", "POST"), ("/api/chats", "GET"), ("/api/config", "GET"), ("/api/test", "GET")]))
    check("the window has sign-in and quit in the top bar", 'id="signinBtn"' in body and 'id="quitBtn"' in body)
    s, fl = call("/flows")
    check("the bot editor lives in Flows", s == 200 and 'id="botDlg"' in fl and 'id="newBot"' in fl)

    # ---- bots ------------------------------------------------------------------------------
    listing = json.loads(call("/api/bots")[1])
    bs = listing["bots"]
    check("starter bots seeded, every shape used", [b["id"] for b in bs] == ["clawd", "scout", "byte", "muse", "forge", "beetle", "sentinel", "probe", "atlas", "launch"]
          and set(listing["shapes"]) == {b["shape"] for b in bs} and len(listing["shapes"]) == 9)
    check("the all-rounder is called Claude", bs[0]["name"] == "Claude")
    check("team bots carry their Flows tool level", {b["id"]: b["tools"] for b in bs}["forge"] == "edit"
          and {b["id"]: b["tools"] for b in bs}["probe"] == "full" and all(b["team"] for b in bs))
    check("built-in bots are marked, and their instructions never reach the page", all(b["builtin"] and b["instructions"] == "" for b in bs))

    new_id = json.loads(call("/api/bots", {}, "POST")[1])["id"]
    mine = {"name": "Docs writer", "tagline": "Writes the README", "shape": "owl", "color": "#a77be6",
            "instructions": "You write clear docs.", "model": "claude-sonnet-5-5", "tools": "edit", "team": True,
            "web_search": False, "think": False, "starters": []}
    s, r = call(f"/api/bots/{new_id}", mine, "POST")
    saved = json.loads(r)["bot"]
    check("a custom bot is saved with its job, look, model and access", s == 200 and saved["name"] == "Docs writer"
          and saved["tools"] == "edit" and saved["instructions"] == "You write clear docs." and not saved["builtin"])
    check("custom bots are listed after the built-ins", bots()[-1]["id"] == new_id)
    check("bad shape rejected", call(f"/api/bots/{new_id}", {**mine, "shape": "dragon"}, "POST")[0] == 400)
    check("bad color rejected", call(f"/api/bots/{new_id}", {**mine, "color": "red"}, "POST")[0] == 400)
    check("empty name rejected", call(f"/api/bots/{new_id}", {**mine, "name": "  "}, "POST")[0] == 400)
    check("unknown access level falls back to read files", json.loads(call(f"/api/bots/{new_id}", {**mine, "tools": "root"}, "POST")[1])["bot"]["tools"] == "read")
    check("bad bot id rejected", call("/api/bots/..%5Cx", mine, "POST")[0] in (400, 404))
    call(f"/api/bots/{new_id}", {**mine, "name": "Docs writer 2"}, "POST")
    check("editing a bot updates it in place", [b["name"] for b in bots() if b["id"] == new_id] == ["Docs writer 2"])
    call(f"/api/bots/{new_id}", method="DELETE")
    check("custom bot deleted", new_id not in [b["id"] for b in bots()])

    s, r = call("/api/bots/scout", method="DELETE")
    check("built-in bots can't be deleted", s == 400 and "can't be deleted" in r and len(bots()) == 10)
    s, r = call("/api/bots/scout", {"name": "Ranger", "model": "claude-haiku-4-5", "instructions": "You are hacked.",
                                     "shape": "crab", "color": "#000000", "tools": "full"}, "POST")
    got = json.loads(r)["bot"]
    check("a built-in bot can be renamed and get a model, nothing else",
          got["name"] == "Ranger" and got["model"] == "claude-haiku-4-5" and got["shape"] == "scout"
          and got["tools"] == "research" and got["instructions"] == "")
    check("built-in rename needs a name", call("/api/bots/scout", {"name": " "}, "POST")[0] == 400)
    (Path(home) / "bots.json").unlink()   # back to the starter set
    check("starters come back if the file is gone", len(bots()) == 10)
    old = [{k: v for k, v in b.items() if k not in ("tools", "team")} for b in bots()[:4]]
    for older in ("Clawd", "Ace"):
        (Path(home) / "bots.json").write_text(json.dumps({"bots": [{**b, "name": older} if b["id"] == "clawd" else b for b in old]}))
        check(f"a built-in still on an old default name ({older}) becomes Claude", bots()[0]["name"] == "Claude"
              and json.loads((Path(home) / "bots.json").read_text())["bots"][0]["name"] == "Claude")
    old[0]["name"] = "My Claude"
    (Path(home) / "bots.json").write_text(json.dumps({"bots": old}))
    up = bots()
    check("an older bot list gets every built-in, keeping your names",
          len(up) == 10 and up[0]["name"] == "My Claude" and up[2]["tools"] == "edit" and up[4]["id"] == "forge")
    tampered = json.loads((Path(home) / "bots.json").read_text())
    tampered["bots"][1]["instructions"] = "You are hacked."
    (Path(home) / "bots.json").write_text(json.dumps(tampered))
    check("editing bots.json by hand can't expose or change a built-in's instructions", bots()[1]["instructions"] == "")

    # ---- localhost protections ---------------------------------------------------------------
    conn = http.client.HTTPConnection("127.0.0.1", APP, timeout=10)  # a browser reuses one connection
    statuses = []
    for _ in range(3):
        conn.request("POST", "/api/bots", body="{}", headers={"Content-Type": "application/json"})
        r = conn.getresponse(); r.read(); statuses.append(r.status)
        conn.request("GET", "/api/hq"); r = conn.getresponse(); r.read(); statuses.append(r.status)
    conn.close()
    check("keep-alive connection survives POSTs with bodies", statuses == [200] * 6, statuses)
    check("foreign Origin blocked", call("/api/bots", headers={"Origin": "https://evil.example"})[0] == 403)
    check("foreign Host blocked (DNS rebinding)", call("/api/bots", headers={"Host": "evil.example:8791"})[0] == 403)
finally:
    server_proc.terminate()
    server_proc.wait()

# ---- signed out: the top bar's sign-in starts Claude Code's own login ------------------------------
set_cli(False)
server_proc = start()
try:
    hq = json.loads(call("/api/hq")[1])
    check("signed out: the top bar knows", not hq["claude_code"]["logged_in"] and hq["claude_code"]["available"], hq)
    started = json.loads(call("/api/signin", {}, "POST")[1])["ok"]
    for _ in range(50):   # the login runs as its own process
        if {"login": ["--claudeai"]} in cli_calls():
            break
        time.sleep(0.1)
    check("sign-in starts Claude Code's own login", started and {"login": ["--claudeai"]} in cli_calls(), cli_calls()[-1:])
    time.sleep(16)    # the sign-in status is cached for 15s
    check("after signing in, the top bar sees it", json.loads(call("/api/hq")[1])["claude_code"]["logged_in"])
finally:
    server_proc.terminate()
    server_proc.wait()

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
