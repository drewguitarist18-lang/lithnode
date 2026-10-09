# Lithnode

A productivity tool for running complicated work with teams of Claude Code agents. Draw the team as a node graph,
give each team the CLIs and connectors it needs, press Run, and watch them work. Split one big job across several
agents, have another team check their work, and sign off before anything ships.

- **Flows**: a node editor for agent pipelines. Describe a team in one sentence and Lithnode builds the
  nodes for you, or drag them in yourself. Then press Run.
- **Office**: every open Claude Code session and every running flow agent, each at its own desk.

Windows, Python 3, and [Claude Code](https://claude.com/claude-code). Every agent is a real Claude Code
session (`claude -p`) on your own sign-in. No API keys, and nothing to install beyond Python.
Nothing goes through anyone else's server.

## Flows

```
[Start] → [Builders ×1] → ◆ → [Bug reviewers ×3] ┐
                            → [Security ×2] ────┴→ ◆ merge → [Your call] → [Production check] → Done
```

| Node | What it does |
|---|---|
| **Start** | Where your task goes in. Switch on *Write a plan first* and one agent turns it into a short plan every team reads. |
| **Team** | 1–15 agents with one job. Start from a bot or a blank team, then set the model, effort, access, connectors, command-line tools, whether they split the job, and the look. |
| **Checkpoint** | Waits for everything wired into it, then passes the reports on or merges them into one short handoff. |
| **Approval** | Pauses until you click Approve or Reject, with an optional note for the next stage. Can ping a webhook (ntfy, IFTTT, Discord, Slack). |
| **Done** | Where the final result lands. |

- **Describe a team:** type something like *"plan it, build it, then 3 reviewers check for bugs and security"*
  in the box at the top of the canvas. One Sonnet call designs the flow and lays it out. You can change
  anything before you run it.
- **Editing:** drag nodes in from the left. Wire them from a node's right dot to another node's left dot.
  Hover a node or wire and click its **✕** to remove it, drag a wire's end off to disconnect it, or
  right-click anything for more (duplicate, disconnect all, add a node here).
- **Order:** every node waits for all of its inputs, so stages run in order and branches run side by side.
- **Editing agents take turns:** agents that can edit files work one after another, so they never overwrite each
  other. Read-only agents run at the same time.
- **Split the job:** switch it on for a team of 2 or more and each agent takes one equal part of the job (rows,
  records, files, pages) and they work side by side, even when they edit files: each writes only its own part.
  Wire a checker team after them to verify every part.
- **Templates:** *Split a big job* (three workers, then a checker), *Build and deploy* (builder, reviewers, your
  sign-off, then a deployer with git and Vercel), *Build, review, secure, ship* (the full chain),
  *Quick code review* (four Haiku sessions), *Research squad*.

### Bots

Ten built-in bots, each with its own pixel character:

| Bot | Job | In Flows it can |
|---|---|---|
| **Claude** | All-rounder | Read files |
| **Scout** | Researcher that cites sources | Read files + web |
| **Byte** | Senior engineer | Edit files |
| **Muse** | Writing partner and ideas | Think only |
| **Forge** | Builder that writes the code | Edit files |
| **Beetle** | Bug hunter | Read files |
| **Sentinel** | Security reviewer | Read files |
| **Probe** | Tester that runs the code | Edit files and run commands |
| **Atlas** | Planner | Read files |
| **Launch** | Ship-ready check | Read files |

You can rename a built-in bot and pick its model. Its look and instructions are built in, and its
instructions never leave the server. Make your own bots with **Make a bot** at the bottom of the Bots list, and edit them however you like.

### Keeping usage down

- Only each agent's short `REPORT:` moves on to the next stage, never its whole transcript.
  A summarizing checkpoint (Haiku by default) shrinks big clusters further.
- Agents skip your MCP connectors and the slash-command list. In testing this took each agent's starting context
  from about 218k tokens to about 10k.
- The toolbar shows how many agents a flow will start. Each one uses your Claude plan like a normal session,
  so cheaper models (Haiku, Sonnet) and fewer agents go further.

### Items

A team can hand back a list of things (parts of a job, records, ideas, leads, options) instead of only text. Agents put the list
in a fenced ` ```items ` JSON block, and Lithnode shows it as cards: photo, price, rating and facts. A team that
judges a list marks each card pass or cut with a reason; when several agents judge, one cut is enough. During a run
the cards sit in a strip under the flow, and the result page has an **Items** section with "Copy as table". In
*Split a big job*, the checker hands back one card per part, passed or cut.

### Command-line tools

A team can run the CLIs you switch on for it under **Command-line tools** in the right panel: git, gh, vercel, npm,
python, stripe, supabase and more. Lithnode lists the ones installed on this computer, and you can add any other
by name. The team gets Claude Code's Bash tool, but only commands that start with those tools are allowed; any
other command is blocked (simple read-only ones like `ls` still work). A team set to *Edit + run code* can already
run anything, so the list doesn't apply to it. Like connectors, CLIs act for real, so the Run menu asks you to
confirm first.

### Engines: Claude Code, Codex and Cursor

Each team picks what it runs on under **Runs on** in the right panel, so one flow can mix them: Claude builds,
Codex reviews, a Cursor team on Grok double-checks. Every engine uses your own sign-in and plan.

| Engine | Install and sign in | Models |
|---|---|---|
| **Claude Code** (default) | `claude auth login` | Haiku, Sonnet, Opus, Fable |
| **Codex** (OpenAI) | `npm i -g @openai/codex`, then `codex login` | the ones your ChatGPT plan offers |
| **Cursor** | the Cursor CLI from cursor.com/cli, then `cursor-agent login` | every model your Cursor plan offers (GPT, Claude, Grok, Gemini, ...) |

Lithnode shows whether each one is installed and signed in, and lists its models for free (no tokens). Access
levels map to Codex's sandbox (read-only, workspace-write, full access) and to Cursor's `--force`. Connectors and
command-line tool lists are Claude Code features. On some Windows computers Codex's own sandbox doesn't start (a
known Codex bug); Lithnode detects that, runs Codex teams with full access, and asks you to confirm first.

### Connectors

A team can use your claude.ai connectors (Vercel, Notion, and any you add, like Shopify). Switch them on per team
under **Connectors** in the right panel. Only the ones you switch on are reachable. Every other connector stays
blocked, and even the switched-on ones load a tool only when the agent searches for it, so a team with connectors
starts near 15k tokens instead of 200k. The list comes from a free check (no tokens) of what Claude Code can
really load on this computer. Some connectors, such as Google's, only work in the claude.ai app and don't show up.
A team with connectors can change things in those apps for real, so the Run menu asks you to confirm first.

## Run it

1. Install [Claude Code](https://claude.com/claude-code) and sign in once. A browser window opens and
   you finish the sign-in there:
   ```
   claude auth login
   ```
2. Then either:
   - **Install it:** download the Windows installer from [lithnode.com](https://lithnode.com). It's a standalone
     app, with Claude Pet as an optional extra.
   - **Run from source:** double-click **Lithnode.bat**. The first run creates a `.venv`.

The top bar shows whether Claude Code is signed in, plus badges for runs, approvals waiting for you,
and agents at work. The **◐** button switches between dark, light and auto themes.

## Safety

Agents are real Claude Code sessions working in the folder you choose. Read this before you run one.

- **Tool levels:** each team has one. Reviewers default to *read files only*.
  - Teams set to *edit files* can change files in the folder.
  - Teams set to *edit files and run commands* (like Probe) can run any command on your computer.
  - Teams with command-line tools can run those tools (and only those).
  - Lithnode asks you to tick "I understand" before any run that includes any of these, or connectors.
- **Use git.** Run editing flows on a folder whose work is committed, so you can see and undo every
  change.
- **Only point agents at code you trust.** Text inside files, web pages or tool output can try to steer
  an agent (prompt injection). Read-only reviewers can't act on it. Agents that can edit or run
  commands could.
- **It stays local:**
  - The server listens on `127.0.0.1` only, and rejects requests from other websites and hosts.
  - Your Claude sign-in stays inside Claude Code, and Lithnode never sees it.
  - Lithnode has no telemetry.
- **Webhooks** on approval nodes send the flow name and message to the URL you enter. Only use your own.
- **Your account, your usage.** Agents run on your own Claude plan, under Anthropic's
  terms for your account. Don't run Lithnode as a service for other people on your subscription.

### Disclaimer

Lithnode is an independent project. It is not made, endorsed or supported by Anthropic, OpenAI or Cursor. "Claude" and
"Claude Code" are Anthropic's trademarks, "Codex" and "ChatGPT" are OpenAI's, and "Cursor" is Anysphere's; they're
used here only to say what this works with. The
software is provided under the MIT license, **as is, without warranty of any kind**. You're
responsible for what your agents do in your folders and for your use of your Claude account.

## Where things live

| What | Where |
|---|---|
| Flows and run history | `~/.lithnode/` |
| Scratch folders for runs without a folder | `~/.lithnode/workspaces/<flow>/` |
| Bots | `~/.clawd-bot/bots.json` |
| Live sessions for the Office (from Claude Pet's hooks, optional) | `~/.claude-pet/sessions.json` |

If Lithnode is closed in the middle of a run, the run shows as *interrupted* next time, and its finished
reports are kept.

## Files

- `hq.py`: the server and routes, and the built-in bots.
- `flows.py`: flows, validation, templates, the flow designer, and the run engine.
- `agents.py`: one pipeline agent as one `claude -p` session.
- `office_feed.py`: the Office's session list (hook sessions plus flow agents).
- `claude_code.py`: finding Claude Code, signing in, and checking which connectors and CLIs are available.
- `engines.py`: the Codex and Cursor engines: finding them, sign-in, models, command lines and their live output.
- `static/`:
  - pages: `shell.html` (tabs), `flows.html`, `office.html`
  - shared: `sprites.js` (pixel art) and `ui.js` (styled dialogs and right-click menus)
- `installer/`: the Windows build. `build.ps1` runs PyInstaller (the engine), Electron (the window) and
  Inno Setup (the installer) and writes `dist\LithnodeSetup.exe`.
- `site/`: lithnode.com, a static page deployed on Vercel.
- `marketing/`: the ad animations (HTML, rendered to MP4).

## Tests

```
.venv\Scripts\python tests\flows_test.py   # flows, runs, approvals, stop, office feed, the designer, built-in roles
.venv\Scripts\python tests\smoke.py        # the window, bots and locking, sign-in, localhost checks
```

Both suites run the real server against `tests/mock_claude.py`, a stand-in `claude` CLI, so they cost
nothing. Real runs have been tested against Claude Code 2.1.289 with the *Quick code review* template.
