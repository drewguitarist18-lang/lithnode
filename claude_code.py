"""Finding Claude Code on this computer, checking its sign-in, and starting a sign-in.

Lithnode runs every agent through the `claude` CLI on your own Claude sign-in. Sign in once with:
    claude auth login
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: don't flash a console when run from pythonw
# Keep MCP servers and claude.ai connectors (Vercel, Notion, ...) out of these sessions. Their tool lists
# can add ~200k tokens to every request: more than Haiku's whole window, and costly on any model.
NO_CONNECTORS_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
# Set in every session Lithnode starts, so your own hooks can tell its agents apart (and, say, not ding 15 times).
AGENT_ENV = {"LITHNODE_AGENT": "1"}
NO_CONNECTORS_ARGS = ["--strict-mcp-config", "--disallowedTools", "mcp__*"]


TOOLS_BIN = None   # Lithnode's own commands for agents (lithnode-shot), set by setup_tools at startup


def setup_tools(home):
    """Puts `lithnode-shot` (shot.py) in home/bin for the agents' PATH. Returns that folder."""
    global TOOLS_BIN
    import shot
    import sys
    frozen = getattr(sys, "frozen", False)
    command = [str(Path(sys.executable).with_name("lithnode-cli.exe")), "shot"] if frozen else [sys.executable, str(Path(shot.__file__).resolve())]
    TOOLS_BIN = str(shot.bin_dir(home, command))
    return TOOLS_BIN


def _with_tools(env):
    if TOOLS_BIN:
        env["PATH"] = TOOLS_BIN + os.pathsep + env.get("PATH", "")
    return env


def lean_env():
    return _with_tools({**os.environ, **NO_CONNECTORS_ENV, **AGENT_ENV})


def connectors_env():
    """For a team given connectors: claude.ai connectors on, and every tool loaded only when the agent searches
    for it (ENABLE_TOOL_SEARCH). That keeps the context near 15k tokens instead of ~200k."""
    env = {k: v for k, v in os.environ.items() if k != "ENABLE_CLAUDEAI_MCP_SERVERS"}
    env["ENABLE_TOOL_SEARCH"] = "true"
    env.update(AGENT_ENV)
    return _with_tools(env)


def tool_prefix(server):
    """Claude Code names a server's tools mcp__<server>__<tool>, with anything but letters, digits, _ and - as _."""
    return "mcp__" + re.sub(r"[^A-Za-z0-9_-]", "_", server)


CONNECTOR_TTL = 600
PROBE_MODEL = "lithnode-connector-probe"   # not a real model: see list_connectors
_SERVER_RE = re.compile(r'MCP server "([^"]+)": (.*)')
_connectors = {"at": 0.0, "value": None}
_connectors_lock = threading.Lock()


def list_connectors(force=False):
    """The connectors an agent session on this computer really loads: claude.ai ones and other MCP servers.

    Found with a free probe: a session asked for a model that doesn't exist still connects its servers and
    logs them, then stops before sending anything to Claude. (`claude mcp list` isn't enough: it shows
    connectors, such as Google's, that a headless session never loads.) Cached for 10 minutes.
    Returns {"ok", "connectors": [{"id", "name"}], "seen": [every server named], "error"}.
    """
    with _connectors_lock:
        if not force and _connectors["value"] and time.time() - _connectors["at"] < CONNECTOR_TTL:
            return _connectors["value"]
        value = {"ok": False, "connectors": [], "seen": [], "error": ""}
        command = find_command()
        if not command:
            value["error"] = "Claude Code isn't installed on this computer."
        else:
            fd, log = tempfile.mkstemp(prefix="lithnode-probe-", suffix=".txt")
            os.close(fd)
            try:
                subprocess.run([*command, "-p", "--model", PROBE_MODEL, "--output-format", "json", "--tools", "ToolSearch",
                                "--disable-slash-commands", "--debug-file", log], input="hi", capture_output=True,
                               text=True, timeout=90, creationflags=NO_WINDOW, env=connectors_env(), cwd=str(Path.home()))
                seen, live = [], set()
                for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
                    m = _SERVER_RE.search(line)
                    if m:
                        if m.group(1) not in seen:
                            seen.append(m.group(1))
                        if m.group(2).startswith("Successfully connected"):
                            live.add(m.group(1))
                value.update(ok=True, seen=seen,
                             connectors=[{"id": s, "name": s.removeprefix("claude.ai ").strip() or s} for s in seen if s in live])
            except (OSError, subprocess.TimeoutExpired) as exc:
                value["error"] = f"Couldn't check your connectors: {exc}"
            finally:
                try:
                    os.unlink(log)
                except OSError:
                    pass
        _connectors.update(at=time.time(), value=value)
        return value


# Command-line tools a team can be allowed to run. A team gets only the ones switched on: Claude Code allows
# `Bash(<cli>:*)` and denies every other command (read-only ones like `ls` still work).
CLI_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
KNOWN_CLIS = [
    ("git", "Git", "Commits, branches, diffs"), ("gh", "GitHub", "Issues, pull requests, releases"),
    ("vercel", "Vercel", "Deploys, env vars, logs"), ("netlify", "Netlify", "Deploys and sites"),
    ("npm", "npm", "Install, build, test"), ("pnpm", "pnpm", "Install, build, test"), ("yarn", "Yarn", "Install, build, test"),
    ("bun", "Bun", "Run, install, test"), ("node", "Node.js", "Run JavaScript"), ("deno", "Deno", "Run TypeScript"),
    ("python", "Python", "Run scripts, process data"), ("uv", "uv", "Python packages and scripts"),
    ("sqlite3", "SQLite", "Query local databases"), ("psql", "Postgres", "Query Postgres"),
    ("supabase", "Supabase", "Database, auth, functions"), ("firebase", "Firebase", "Hosting and data"),
    ("stripe", "Stripe", "Payments, products, webhooks"), ("shopify", "Shopify", "Themes and apps"),
    ("wrangler", "Cloudflare", "Workers and pages"), ("flyctl", "Fly.io", "Deploy apps"), ("railway", "Railway", "Deploy apps"),
    ("heroku", "Heroku", "Deploy apps"), ("aws", "AWS", "Amazon Web Services"), ("az", "Azure", "Microsoft Azure"),
    ("gcloud", "Google Cloud", "Google Cloud"), ("docker", "Docker", "Containers"), ("kubectl", "Kubernetes", "Clusters"),
    ("terraform", "Terraform", "Infrastructure"), ("ffmpeg", "FFmpeg", "Convert audio and video"),
    ("magick", "ImageMagick", "Edit images"), ("pandoc", "Pandoc", "Convert documents"), ("curl", "curl", "Call web APIs"),
]


def cli_installed(name):
    if not CLI_RE.match(name or ""):
        return False
    fake = os.environ.get("LITHNODE_CLIS")
    return name in fake.split(",") if fake is not None else shutil.which(name) is not None


def list_clis():
    """The known command-line tools installed on this computer: [{"id", "name", "blurb"}].
    LITHNODE_CLIS (comma-separated) replaces the check, for tests."""
    fake = os.environ.get("LITHNODE_CLIS")
    if fake is not None:
        have = set(filter(None, fake.split(",")))
        return [{"id": c, "name": n, "blurb": b} for c, n, b in KNOWN_CLIS if c in have]
    return [{"id": c, "name": n, "blurb": b} for c, n, b in KNOWN_CLIS if shutil.which(c)]


STATUS_TTL = 15
INLINE_PROMPT_LIMIT = 6000   # longer prompts go over stdin (Windows command lines are limited)

_status_cache = {"at": 0.0, "value": None}
_sessions_lock = threading.Lock()


# ------------------------------------------------------------------- the CLI

def find_command():
    """The command that runs Claude Code, as a list, or None if it isn't installed."""
    override = os.environ.get("CLAWD_BOT_CLAUDE_CMD")
    if override:
        return json.loads(override)
    exe = shutil.which("claude")
    shim = exe if exe and Path(exe).suffix.lower() in (".cmd", ".bat") else None
    if exe and not shim:
        return [exe]
    # npm installs claude.cmd, which runs through cmd.exe: that mangles newlines, quotes, & and % in
    # arguments (the appended system prompt has all of them). Run what the shim points at instead.
    unwrapped = unwrap_shim(shim) if shim else None
    if unwrapped:
        return unwrapped
    base = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code"
    found = list(base.glob("*/*/claude.exe")) if base.exists() else []

    def version(path):
        return [int(p) if p.isdigit() else 0 for p in path.parent.parent.name.split(".")]

    if found:
        return [str(sorted(found, key=version)[-1])]
    return [shim] if shim else None


_SHIM_TARGET_RE = re.compile(r'"%~?dp0%?\\(node_modules\\[^"%]+?\.(?:c?js|mjs|exe))"', re.I)


def unwrap_shim(path):
    """What an npm .cmd shim really runs, as a command list, or None if it can't tell."""
    try:
        m = _SHIM_TARGET_RE.search(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not m:
        return None
    target = Path(path).parent / m.group(1)
    if not target.is_file():
        return None
    if target.suffix.lower() == ".exe":
        return [str(target)]
    node = Path(path).parent / "node.exe"
    node = str(node) if node.is_file() else shutil.which("node")
    return [node, str(target)] if node else None


def auth_status(force=False):
    """{'available', 'logged_in', 'method'}; cached briefly because it spawns a process."""
    now = time.time()
    if not force and _status_cache["value"] and now - _status_cache["at"] < STATUS_TTL:
        return _status_cache["value"]
    command = find_command()
    value = {"available": False, "logged_in": False, "method": None}
    if command:
        value["available"] = True
        try:
            done = subprocess.run([*command, "auth", "status"], capture_output=True, text=True,
                                  timeout=20, creationflags=NO_WINDOW)
            data = json.loads(done.stdout or "{}")
            value["logged_in"] = bool(data.get("loggedIn"))
            value["method"] = data.get("authMethod")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    _status_cache.update(at=now, value=value)
    return value


def start_login():
    """Open Claude Code's own sign-in (a console window, then your browser). You finish it there."""
    command = find_command()
    if not command:
        return False
    # The tests swap in a mock CLI; don't pop a console for that.
    flags = NO_WINDOW if os.environ.get("CLAWD_BOT_CLAUDE_CMD") else 0x00000010   # CREATE_NEW_CONSOLE
    try:
        subprocess.Popen([*command, "auth", "login", "--claudeai"], cwd=str(Path.home()), creationflags=flags)
    except OSError:
        return False
    _status_cache["value"] = None   # so the next status check really asks
    return True


SIGN_IN_HINT = ("Claude Code isn't signed in. Click \"Sign in\" at the top right of Lithnode, "
                "or run `claude auth login` once in a terminal.")
