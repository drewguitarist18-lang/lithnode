"""A stand-in for the `claude` CLI so the Claude Code engine can be tested offline.

It records how it was called, emits the documented `--output-format stream-json` events
(system/init, stream_event with raw API deltas, assistant, user tool_result, result), and replays
the exact "Not logged in" output a real, signed-out CLI produced.

Env: CLAWD_MOCK_STATE (json file: {"logged_in": bool}), CLAWD_MOCK_LOG (jsonl of calls),
     CLAWD_MOCK_SESSIONS (json list of known session ids).
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

STATE = Path(os.environ["CLAWD_MOCK_STATE"])
LOG = Path(os.environ["CLAWD_MOCK_LOG"])
SESSIONS = Path(os.environ["CLAWD_MOCK_SESSIONS"])


def logged_in():
    try:
        return bool(json.loads(STATE.read_text()).get("logged_in"))
    except (OSError, ValueError):
        return True


def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def log(obj):
    """Append one line to the call log. Parallel agents run several mocks at once, so take a lock."""
    lock = LOG.with_suffix(".lock")
    for _ in range(500):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError:
            time.sleep(0.005)
    else:
        fd = None
    try:
        with LOG.open("a") as f:
            f.write(json.dumps(obj) + "\n")
    finally:
        if fd is not None:
            os.close(fd)
            os.unlink(lock)


def parse(argv):
    flags, prompt, i = {}, None, 0
    valued = {"--system-prompt", "--model", "--effort", "--tools", "--allowedTools", "--session-id",
              "--resume", "--output-format", "--append-system-prompt", "--permission-mode", "--max-turns",
              "--disallowedTools", "--debug-file"}
    while i < len(argv):
        a = argv[i]
        if a == "--":
            prompt = argv[i + 1] if i + 1 < len(argv) else None
            break
        if a in valued:
            flags[a] = argv[i + 1]
            i += 2
        else:
            flags[a] = True
            i += 1
    return flags, prompt


argv = sys.argv[1:]
if argv[:2] == ["auth", "login"]:   # pretend the user finished signing in
    STATE.write_text(json.dumps({"logged_in": True}))
    log({"login": argv[2:]})
    sys.exit(0)
if argv[:2] == ["auth", "status"]:
    ok = logged_in()
    print(json.dumps({"loggedIn": ok, "authMethod": "claude.ai" if ok else "none", "apiProvider": "firstParty"}))
    sys.exit(0 if ok else 1)

flags, prompt = parse(argv)
if flags.get("--model") == "lithnode-connector-probe":   # connect the servers, log them, stop before any request
    servers = os.environ.get("CLAWD_MOCK_CONNECTORS", "claude.ai Vercel,claude.ai Notion").split(",")
    lines = [f'[DEBUG] MCP server "{s}": Successfully connected (transport: claudeai-proxy) in 200ms' for s in servers if s]
    lines.append('[DEBUG] MCP server "claude.ai Broken": Connection failed: 401')
    Path(flags["--debug-file"]).write_text("\n".join(lines) + "\n")
    log({"probe": True, "connectors": os.environ.get("ENABLE_CLAUDEAI_MCP_SERVERS"), "toolsearch": os.environ.get("ENABLE_TOOL_SEARCH")})
    print(json.dumps({"type": "result", "is_error": True, "result": "There's an issue with the selected model."}))
    sys.exit(1)
via = "arg"
if prompt is None:
    prompt, via = sys.stdin.read(), "stdin"
session = flags.get("--session-id") or flags.get("--resume") or str(uuid.uuid4())
log({"flags": {k: v for k, v in flags.items()}, "prompt": prompt, "via": via, "cwd": os.getcwd(), "t": time.time(),
     "connectors": os.environ.get("ENABLE_CLAUDEAI_MCP_SERVERS"), "toolsearch": os.environ.get("ENABLE_TOOL_SEARCH")})

known = json.loads(SESSIONS.read_text()) if SESSIONS.exists() else []
base = {"session_id": session}
out({"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": session, "tools": [], "model": flags.get("--model", "?")})

if not logged_in():   # the real signed-out output, shape for shape
    out({"type": "system", "subtype": "status", "status": "requesting", **base})
    out({"type": "assistant", "message": {"model": "<synthetic>", "role": "assistant", "stop_reason": "stop_sequence",
         "content": [{"type": "text", "text": "Not logged in · Please run /login"}]}, **base})
    out({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login",
         "stop_reason": "stop_sequence", "terminal_reason": "api_error", "total_cost_usd": 0, **base})
    sys.exit(1)

if "--resume" in flags and flags["--resume"] not in known:
    out({"type": "result", "subtype": "error_during_execution", "is_error": True,
         "result": f"No conversation found with session ID: {flags['--resume']}", **base})
    sys.exit(1)
if "--session-id" in flags:
    SESSIONS.write_text(json.dumps(known + [flags["--session-id"]]))

# Lithnode pipeline agents append to Claude Code's system prompt and don't stream partial messages.
# Cues: a stage named SLOWSTAGE takes 4s, HANGSTAGE hangs for a minute, FAILSTAGE (or FAILME in the prompt) fails.
if "--append-system-prompt" in flags:
    system = flags["--append-system-prompt"]
    time.sleep(60 if "HANGSTAGE" in system else 4 if "SLOWSTAGE" in system
               else float(os.environ.get("CLAWD_MOCK_WAIT") or 1.0))   # side-by-side agents overlap; CLAWD_MOCK_WAIT slows demos
    if "flow designer for Lithnode" in system:   # the "describe a team" box: answer with a flow draft
        draft = {"name": "Bug sweep", "nodes": [
            {"id": "master", "type": "master", "mode": "pass"},
            {"id": "Bug Hunters!", "type": "cluster", "count": 2, "bot": "beetle", "model": "claude-haiku-4-5",
             "tools": "read", "focuses": "Logic\nErrors"},
            {"id": "merge", "type": "checkpoint", "mode": "summarize", "model": "claude-haiku-4-5"}],
            "edges": [["master", "Bug Hunters!"], ["Bug Hunters!", "merge"]]}
        text = "nope, no flow here" if "BADJSON" in prompt else "Here it is:\n```json\n" + json.dumps(draft) + "\n```"
        out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [{"type": "text", "text": text}]}, **base})
        out({"type": "result", "subtype": "success", "is_error": False, "result": text, "total_cost_usd": 0.02, "num_turns": 1, **base})
        sys.exit(0)
    if "Read" in str(flags.get("--tools", "")):
        out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_r", "name": "Read", "input": {"file_path": os.path.join(os.getcwd(), "app.py")}}]}, **base})
        out({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_r", "content": "print('hi')"}]}, **base})
    if "FAILSTAGE" in system or "FAILME" in prompt:
        out({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "Mock agent blew up",
             "total_cost_usd": 0.005, "num_turns": 1, **base})
        sys.exit(1)
    stage = system.split('" stage of')[0].split('"')[-1] if '" stage of' in system else "lead"
    text = f"Working on it.\n\nREPORT: {stage} report from {session[:8]}."
    if os.environ.get("CLAWD_MOCK_RICH"):   # a report shaped like a real one, for looking at the results page
        text = (f"Done.\n\nREPORT: **{stage}** checked the change to the login flow.\n\n**Found**\n"
                "- `session.ts` refreshes the token after it expires, so a slow request can log you out (line 88).\n"
                "- The retry in `api.ts` has no limit, so a dead server means an endless loop.\n\n"
                "**Fixed**\n- Refresh now runs 60 seconds before expiry.\n- Retries stop after 3 tries with a clear error.\n\n"
                "**Next stage:** check both fixes on a slow network.")
    # A dropship team (the template's stage names): the scout lists products, checkers judge them, the uploader
    # lists the winners. CLAWD_MOCK_PACE slows the steps down so a run can be watched.
    pace = float(os.environ.get("CLAWD_MOCK_PACE") or 0)
    if stage == "Workers":   # long enough that workers running side by side overlap
        time.sleep(0.5)
    if stage in ("Product scout", "Checker", "Uploader"):
        products = [("Mini Portable Blender", "$29.99", "$6.80", 4.7, "7 days"), ("Sunset Projection Lamp", "$24.99", "$5.20", 4.6, "8 days"),
                    ("Posture Corrector", "$12.99", "$4.10", 3.9, "9 days"), ("LED Strip Lights 5m", "$11.99", "$7.90", 4.4, "8 days"),
                    ("Magnetic Phone Mount", "$19.99", "$2.10", 4.8, "6 days"), ("Wireless Earbuds", "$29.99", "$8.50", 4.3, "24 days")]
        steps = {"Product scout": [("WebSearch", {"query": "trending home gadgets 2026"}), ("WebFetch", {"url": "https://www.aliexpress.com/item/1005"}),
                                   ("WebSearch", {"query": "portable blender supplier price"})],
                 "Checker": [("WebSearch", {"query": "posture corrector reviews"}), ("WebFetch", {"url": "https://www.cjdropshipping.com/product/led"})],
                 "Uploader": [("mcp__claude_ai_Store__create_product", {"title": "Mini Portable Blender"})]}[stage]
        for i, (name, args) in enumerate(steps):
            time.sleep(pace)
            out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [
                {"type": "tool_use", "id": f"toolu_s{i}", "name": name, "input": args}]}, **base})
        items = []
        for name, price, cost, rating, ship in products:
            item = {"title": name, "price": price, "rating": rating, "facts": {"Cost": cost, "Shipping": ship},
                    "url": "https://www.aliexpress.com/item/" + str(abs(hash(name)) % 10**6)}
            if stage == "Checker":
                margin = round((1 - float(cost[1:]) / float(price[1:])) * 100)
                if "# Your focus\nMargin" in prompt:   # the first checker looks at money, the second at reviews and shipping
                    item.update(verdict="cut" if margin < 60 else "pass", reason=f"Margin {margin}%")
                else:
                    bad = f"Reviews {rating}★" if rating < 4.5 else "Ships in 24 days" if ship == "24 days" else ""
                    item.update(verdict="cut" if bad else "pass", reason=bad or f"{rating}★, {ship}")
            items.append(item)
        if stage == "Uploader":   # lists what the checkers passed
            items = [dict(i, verdict="pass", reason="Listed as draft") for i in items
                     if not any(w in i["title"] for w in ("Posture", "LED", "Earbuds"))]
        text = (f"Done.\n\nREPORT: {stage}: {len(items)} products.\n\n```items\n" + json.dumps(items) + "\n```")
    out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [{"type": "text", "text": text}]}, **base})
    out({"type": "result", "subtype": "success", "is_error": False, "result": text, "total_cost_usd": 0.01,
         "num_turns": 2, "terminal_reason": "completed", **base})
    log({"end": session, "t": time.time()})
    sys.exit(0)


def event(ev):
    out({"type": "stream_event", "event": ev, "parent_tool_use_id": None, **base})


text_chunks = ["Hello from ", "Claude Code."]
tools_on = "WebSearch" in str(flags.get("--tools", ""))
streaming = "--include-partial-messages" in flags and "NOSTREAM" not in prompt

if tools_on:
    if streaming:
        event({"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "WebSearch", "input": {}}})
        for piece in ['{"que', 'ry": "clawd news"}']:
            event({"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": piece}})
        event({"type": "content_block_stop", "index": 0})
    out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "WebSearch", "input": {"query": "clawd news"}}]}, **base})
    out({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [
        {"type": "text", "text": 'Web search results for query: "clawd news"\n\nLinks: [{"title":"Example A","url":"https://example.com/a"},'
                                 '{"title":"Example B","url":"https://example.org/b"}]\n\nSummary...'}]}]}, **base})
    text_chunks = ["Found it: **", "42**."]

index = 1 if tools_on else 0
if streaming:
    event({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
    for piece in text_chunks:
        event({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": piece}})
    event({"type": "content_block_stop", "index": index})
full = "".join(text_chunks)
out({"type": "assistant", "message": {"model": "claude", "role": "assistant", "content": [{"type": "text", "text": full}]}, **base})
out({"type": "result", "subtype": "success", "is_error": False, "result": full, "terminal_reason": "completed", **base})
