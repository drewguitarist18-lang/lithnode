"""One pipeline agent = one real Claude Code session (`claude -p`).

Unlike a chat, a pipeline agent may get file tools, keeps Claude Code's own system prompt
(its role is appended), and runs to completion on its own. We read its stream-json output to
show what it is doing right now, then keep only its final report and cost.
"""
import json
import os
import signal
import subprocess
import threading
import uuid
from pathlib import Path

import claude_code
import engines

# The longest one session may run before it's killed, so a hung CLI can't hold up its run forever.
TIMEOUT = float(os.environ.get("LITHNODE_AGENT_TIMEOUT") or 4 * 3600)

# What each tool level lets an agent touch. Reviewers get read-only; builders can edit.
TOOLSETS = {
    "none": [],
    "read": ["Read", "Glob", "Grep"],
    "web": ["WebSearch", "WebFetch"],
    "research": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
    "edit": ["Read", "Glob", "Grep", "Edit", "Write"],
    "full": ["Read", "Glob", "Grep", "Edit", "Write", "Bash"],
}
WRITES = {"edit", "full"}          # agents at these levels never run side by side in one folder
LOOKS = {"read", "research", "edit"}   # levels that also get lithnode-shot, to look at pages and HTML they make or check
EFFORTS = ("low", "medium", "high", "xhigh", "max")   # what `claude --effort` accepts


def build_args(command, *, model, effort, tools, system, session_id, max_turns=0, connectors=(), known=(), clis=()):
    names = list(TOOLSETS[tools])
    cli_rules = []
    if tools in LOOKS:
        clis = [*clis, "lithnode-shot"]
    if clis and "Bash" not in names:
        # The team's command-line tools: Bash, but only `<cli> ...` is allowed. Claude Code denies any other
        # command in a headless session (read-only ones like `ls` still run).
        names.append("Bash")
        cli_rules = [f"Bash({c}:*)" for c in clis]
    use = [s for s in connectors if s in known]
    if use:
        # The team's own connectors: every other server is blocked by name, and their tools load only when
        # the agent searches for one (ToolSearch + claude_code.connectors_env), so the context stays small.
        blocked = [claude_code.tool_prefix(s) for s in known if s not in use]
        mcp_args = ["--disallowedTools", ",".join(blocked)] if blocked else []
        tool_list, allowed = names + ["ToolSearch"], names + [claude_code.tool_prefix(s) for s in use]
    else:
        # No MCP servers or claude.ai connectors (see claude_code.NO_CONNECTORS_*): they can add ~200k tokens.
        mcp_args, tool_list, allowed = claude_code.NO_CONNECTORS_ARGS, names, names
    if cli_rules:
        allowed = [t for t in allowed if t != "Bash"] + cli_rules
    # No skills listing either. Hooks, CLAUDE.md and your sign-in still load.
    args = [*command, "-p", "--output-format", "stream-json", "--verbose",
            "--append-system-prompt", system, "--model", model, "--session-id", session_id,
            *mcp_args, "--disable-slash-commands", "--tools", ",".join(tool_list)]
    if allowed:
        args += ["--allowedTools", ",".join(allowed)]
    if tools in WRITES:
        args += ["--permission-mode", "acceptEdits"]
    if effort in EFFORTS and not model.startswith("claude-haiku"):
        args += ["--effort", effort]
    if max_turns:
        args += ["--max-turns", str(int(max_turns))]
    return args


def describe(name, args):
    """A short human line for a tool call, shown on the agent's desk."""
    a = args or {}
    short = lambda p: Path(str(p)).name or str(p)   # noqa: E731
    if name == "Read":
        return f"Reading {short(a.get('file_path', ''))}"
    if name in ("Edit", "MultiEdit"):
        return f"Editing {short(a.get('file_path', ''))}"
    if name == "Write":
        return f"Writing {short(a.get('file_path', ''))}"
    if name == "Grep":
        return f"Searching for '{str(a.get('pattern', ''))[:40]}'"
    if name == "Glob":
        return f"Finding {a.get('pattern', 'files')}"
    if name == "Bash":
        return f"Running: {str(a.get('command', ''))[:60]}"
    if name == "WebSearch":
        return f"Searching the web: {a.get('query', '')}"
    if name == "WebFetch":
        return f"Reading {a.get('url', 'a page')}"
    if name == "ToolSearch":
        return f"Looking for a tool: {str(a.get('query', ''))[:40]}"
    if str(name).startswith("mcp__"):     # mcp__claude_ai_Vercel__list_projects -> "Vercel: list projects"
        server, _, tool = str(name)[5:].partition("__")
        return f"{server.removeprefix('claude_ai_').replace('_', ' ')}: {tool.replace('_', ' ')}"
    return f"Using {name}"


def report_of(text, limit):
    """The part of an agent's answer that is handed on: after 'REPORT:' if it wrote one."""
    text = (text or "").strip()
    marker = text.upper().rfind("REPORT:")
    if marker >= 0:
        text = text[marker + len("REPORT:"):].strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "\n[...cut to save credits]"


def kill_tree(proc):
    """Kill a session and everything it started: its Bash commands outlive a plain kill()."""
    if not claude_code.WINDOWS:   # Mac and Linux: each agent leads its own process group (NEW_GROUP)
        try:
            if claude_code.FLATPAK:   # flatpak-spawn hands SIGTERM on to what it started outside the sandbox
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            pass
    else:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           timeout=15, creationflags=claude_code.NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        proc.kill()
    except OSError:
        pass


class Agent:
    """Runs one session. `on_update` is called (with no arguments) whenever its state changes."""

    def __init__(self, *, model, effort, tools, system, prompt, cwd, on_update, max_turns=0, connectors=(), known=(), clis=(),
                 engine="claude", engine_model=""):
        self.model, self.effort, self.tools, self.clis = model, effort, tools, list(clis)
        self.engine, self.engine_model = engine if engine in engines.ENGINES else "claude", engine_model
        self.connectors, self.known = [s for s in connectors if s in known], list(known)
        self.system, self.prompt, self.cwd = system, prompt, Path(cwd)
        self.max_turns = max_turns
        self.on_update = on_update
        self.session_id = str(uuid.uuid4())
        self.step = ""
        self.steps = []
        self.text = ""
        self.error = None
        self.cost = 0.0
        self.turns = 0
        self.proc = None
        self.stopped = False
        self.timed_out = False
        self._lock = threading.Lock()

    def stop(self):
        with self._lock:
            self.stopped = True
            if self.proc and self.proc.poll() is None:
                kill_tree(self.proc)

    def _time_out(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.timed_out = True
                kill_tree(self.proc)

    def _feed(self, proc):
        """Send the prompt over stdin (prompts with handoffs are too long for a command line)."""
        try:
            proc.stdin.write(self.prompt)
            proc.stdin.close()
        except OSError:      # the agent was stopped before it read its prompt
            pass

    def _set_step(self, line):
        self.step = line
        self.steps = (self.steps + [line])[-30:]
        self.on_update()

    def run(self):
        """Blocks until the session ends. Returns True on success."""
        if self.engine != "claude":
            return self._run_other()
        command = claude_code.find_command()
        if not command:
            self.error = "Claude Code isn't installed on this computer."
            return False
        try:
            self.cwd.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.error = f"Couldn't use the folder {self.cwd}: {exc}"
            return False
        args = build_args(command, model=self.model, effort=self.effort, tools=self.tools,
                          system=self.system, session_id=self.session_id, max_turns=self.max_turns,
                          connectors=self.connectors, known=self.known, clis=self.clis)
        with self._lock:
            if self.stopped:
                return False
            try:
                env = claude_code.connectors_env() if self.connectors else claude_code.lean_env()
                self.proc = subprocess.Popen(
                    claude_code.host(args, env, str(self.cwd)), cwd=str(self.cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                    creationflags=claude_code.NO_WINDOW, **claude_code.NEW_GROUP, env=env)
            except OSError as exc:
                self.error = f"Couldn't start Claude Code: {exc}"
                return False
        proc = self.proc
        stderr_tail = []
        threading.Thread(target=lambda: stderr_tail.extend(proc.stderr.readlines()[-20:]), daemon=True).start()
        threading.Thread(target=self._feed, args=(proc,), daemon=True).start()
        timer = threading.Timer(TIMEOUT, self._time_out)
        timer.daemon = True
        timer.start()
        self._set_step("Starting up")
        final, texts = None, []
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                kind = obj.get("type")
                if kind == "assistant" and not obj.get("parent_tool_use_id"):
                    msg = obj.get("message") or {}
                    parts = msg.get("content") or []
                    said = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
                    if msg.get("model") == "<synthetic>":    # Claude Code's own notices, e.g. "Not logged in"
                        self.error = self.error or said
                        continue
                    for p in parts:
                        if isinstance(p, dict) and p.get("type") == "tool_use":
                            self._set_step(describe(p.get("name"), p.get("input")))
                    if said:
                        texts.append(said)
                        if not any(isinstance(p, dict) and p.get("type") == "tool_use" for p in parts):
                            self._set_step("Writing the report")
                elif kind == "result":
                    final = obj
            proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            timer.cancel()
            if proc.poll() is None:
                kill_tree(proc)

        if final:
            self.cost = float(final.get("total_cost_usd") or 0)
            self.turns = int(final.get("num_turns") or 0)
            result = final.get("result") if isinstance(final.get("result"), str) else ""
            if final.get("is_error") or str(final.get("subtype", "")).startswith("error"):
                self.error = self.error or result or str(final.get("subtype")) or "Claude Code reported an error."
            else:
                self.text = result or "\n\n".join(texts)
        if self.stopped:
            self.error = "Stopped"
        elif self.timed_out:
            self.error = f"Timed out after {TIMEOUT / 60:g} minutes, so it was stopped."
        elif not final and not self.error:
            tail = "".join(stderr_tail)[-300:].strip()
            self.error = "The session ended without a result." + (f" {tail}" if tail else "")
        if self.error and ("Not logged in" in self.error or "/login" in self.error):
            self.error = "Claude Code isn't signed in. Run `claude auth login` once, then try again."
        self.step = "Done" if not self.error else "Failed"
        self.on_update()
        return not self.error

    def _run_other(self):
        """The same session on Codex or Cursor: their own command line and JSON events, same steps and report."""
        name = engines.LABELS[self.engine]
        command = engines.FINDERS[self.engine]()
        if not command:
            self.error = f"{name} isn't installed on this computer."
            return False
        try:
            self.cwd.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.error = f"Couldn't use the folder {self.cwd}: {exc}"
            return False
        args = engines.build_args(self.engine, command, tools=self.tools, model=self.engine_model)
        self.prompt = engines.wrap_prompt(self.system, self.prompt)
        with self._lock:
            if self.stopped:
                return False
            try:
                env = claude_code.lean_env()
                self.proc = subprocess.Popen(claude_code.host(args, env, str(self.cwd)), cwd=str(self.cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                             creationflags=claude_code.NO_WINDOW, **claude_code.NEW_GROUP, env=env)
            except OSError as exc:
                self.error = f"Couldn't start {name}: {exc}"
                return False
        proc = self.proc
        stderr_tail = []
        threading.Thread(target=lambda: stderr_tail.extend(proc.stderr.readlines()[-20:]), daemon=True).start()
        threading.Thread(target=self._feed, args=(proc,), daemon=True).start()
        timer = threading.Timer(TIMEOUT, self._time_out)
        timer.daemon = True
        timer.start()
        self._set_step("Starting up")
        out = {"texts": [], "final": None, "error": ""}
        parse = engines.PARSERS[self.engine]
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    step = parse(json.loads(line), out)
                except (ValueError, AttributeError, TypeError):
                    continue
                if step:
                    self._set_step(step)
            proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            timer.cancel()
            if proc.poll() is None:
                kill_tree(proc)
        tail = "".join(stderr_tail).strip()
        self.turns = out.get("turns", 0)
        if out["error"]:
            self.error = out["error"]
        elif out["final"] is not None:
            self.text = out["final"]
        elif out["texts"] and proc.returncode == 0:
            self.text = "\n\n".join(out["texts"])
        if self.stopped:
            self.error = "Stopped"
        elif self.timed_out:
            self.error = f"Timed out after {TIMEOUT / 60:g} minutes, so it was stopped."
        elif not self.text and not self.error:
            self.error = f"The {name} session ended without a result." + (f" {tail[-300:]}" if tail else "")
        if self.error:
            self.error = engines.friendly_error(self.engine, self.error + (" " + tail[-300:] if "limit" in tail.lower() else ""))
        self.step = "Done" if not self.error else "Failed"
        self.on_update()
        return not self.error
