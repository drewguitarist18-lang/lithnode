"""Checks a built Lithnode for real, on the machine that built it (CI runs this on Linux and Mac).

    python packaging/check_installed.py <how to start the engine, as a JSON list>

It puts a fake `claude` (tests/mock_claude.py) in ~/.local/bin, the way a real install puts it there, then starts
the packaged engine with no help: it has to find that `claude` itself (on Linux from inside the Flatpak, outside the
sandbox), see that you're signed in, and run a whole flow through it to the end.
"""
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
PORT = 8797
URL = f"http://127.0.0.1:{PORT}"
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{str(detail)[:400]}]" if detail and not ok else ""), flush=True)
    if not ok:
        failures.append(name)


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(URL + path, data=data, method="POST" if body is not None else "GET",
                          headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    engine = json.loads(sys.argv[1])
    # under the home folder: the Flatpak sees your home, not the CI's /tmp
    work = Path(tempfile.mkdtemp(prefix="lithnode-check-", dir=Path.home()))
    project = work / "project"
    project.mkdir()
    (project / "app.py").write_text("print('hi')\n")
    state = work / "state.json"
    state.write_text(json.dumps({"logged_in": True}))
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "claude"
    fake.write_text(f'#!/bin/sh\nexec "{shutil.which("python3") or sys.executable}" "{ROOT / "tests" / "mock_claude.py"}" "$@"\n')
    fake.chmod(0o755)
    env = {**os.environ, "LITHNODE_PORT": str(PORT), "LITHNODE_HOME": str(work / "home"), "CLAWD_BOT_HOME": str(work / "bot"),
           "CLAWD_PET_HOME": str(work / "pet"), "CLAWD_MOCK_STATE": str(state), "CLAWD_MOCK_LOG": str(work / "calls.jsonl"),
           "CLAWD_MOCK_SESSIONS": str(work / "sessions.json"), "LITHNODE_AGENT_TIMEOUT": "60"}
    env["PATH"] = "/usr/bin:/bin"   # like an app opened from a menu: it must find ~/.local/bin/claude by itself
    proc = subprocess.Popen([*engine, "--no-open"], env=env)
    try:
        up = False
        for _ in range(240):
            try:
                request.urlopen(URL + "/api/ping", timeout=1)
                up = True
                break
            except OSError:
                time.sleep(0.25)
        check("the packaged engine starts", up)
        if not up:
            return
        _, hq = call("/api/hq")
        cc = hq.get("claude_code") or {}
        check("it finds Claude Code (~/.local/bin/claude) on its own", cc.get("available"), hq)
        check("it sees you're signed in", cc.get("logged_in"), hq)
        _, d = call("/api/flows", {"template": "review"})
        fid = d["flow"]["id"]
        s, r = call(f"/api/flows/{fid}/run", {"task": "Review app.py", "folder": str(project)})
        check("a flow starts", s == 200 and r.get("run"), r)
        run = {}
        deadline = time.time() + 180
        while time.time() < deadline:
            _, run = call(f"/api/runs/{r.get('run')}")
            if run.get("status") in ("done", "failed", "stopped"):
                break
            time.sleep(0.5)
        check("the whole flow runs to the end", run.get("status") == "done", {k: run.get(k) for k in ("status", "error")})
        calls = [json.loads(l) for l in (work / "calls.jsonl").read_text().splitlines()] if (work / "calls.jsonl").exists() else []
        agents = [c for c in calls if "flags" in c and "--append-system-prompt" in c["flags"]]
        check("its agents really ran Claude Code", len(agents) >= 2, len(agents))
        check("in the project folder", all(c.get("cwd", str(project)).rstrip("/") == str(project) for c in agents),
              [c.get("cwd") for c in agents])
        _, done = call(f"/api/runs/{r.get('run')}")
        check("the result came back", bool(done.get("final")), list(done)[:20])
    finally:
        try:
            call("/api/quit", {})
        except OSError:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        fake.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)
    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: " + ", ".join(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
