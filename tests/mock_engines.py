"""Stand-ins for the Codex and Cursor CLIs, for the tests. `mock_engines.py codex ...` or `mock_engines.py cursor ...`.

They answer the sign-in and sandbox checks, and for a run they read the prompt from stdin, log the call
to CLAWD_MOCK_LOG, print a few JSON events the way the real CLIs do, and end with a REPORT.
"""
import json
import os
import sys
from pathlib import Path

engine, args = sys.argv[1], sys.argv[2:]
LOG = Path(os.environ["CLAWD_MOCK_LOG"])


def out(obj):
    print(json.dumps(obj), flush=True)


if engine == "codex" and args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT")
    sys.exit(0)
if engine == "codex" and args[:1] == ["sandbox"]:
    print("windows sandbox failed: helper_unknown_error" if os.environ.get("MOCK_CODEX_NO_SANDBOX") else "lithnode-sandbox-ok")
    sys.exit(0)
if engine == "cursor" and args[:1] == ["status"]:
    print("Logged in as someone@example.com")
    sys.exit(0)

prompt = sys.stdin.read()
with LOG.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"engine": engine, "args": args, "prompt": prompt, "cwd": os.getcwd(),
                        "agent_env": os.environ.get("LITHNODE_AGENT")}) + "\n")
stage = prompt.split('" stage of')[0].split('"')[-1] if '" stage of' in prompt else "?"
report = f"Done.\n\nREPORT: {stage} report from {engine}."

if engine == "codex":
    if "LIMITME" in prompt:
        out({"type": "turn.failed", "error": {"message": "You've hit your usage limit."}})
        sys.exit(1)
    out({"type": "thread.started", "thread_id": "t1"})
    out({"type": "turn.started"})
    out({"type": "item.started", "item": {"id": "i0", "type": "command_execution",
                                          "command": '"C:\\\\WINDOWS\\\\powershell.exe" -Command Get-Content app.py', "status": "in_progress"}})
    out({"type": "item.completed", "item": {"id": "i0", "type": "command_execution", "exit_code": 0}})
    out({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": report}})
    out({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}})
else:
    out({"type": "system", "subtype": "init", "model": "Auto"})
    out({"type": "tool_call", "subtype": "started", "tool_call": {"readToolCall": {"args": {"path": "C:/proj/app.py"}}}})
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": report}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": report})
