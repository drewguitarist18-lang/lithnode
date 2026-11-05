"""Fast checks of the pure helpers: no server, no agents, no network. Runs in about a second.

    .venv\\Scripts\\python tests\\unit_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agents  # noqa: E402
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
