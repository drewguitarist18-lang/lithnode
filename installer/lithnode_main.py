"""Entry point for the installed Lithnode app (built by installer/build.ps1).

lithnode-server.exe (no console) the engine that Lithnode.exe (the app window, installer/app) starts;
                                 `lithnode-server.exe pet` runs Claude Pet.
lithnode-cli.exe  (console)      `hook <Event>`  Claude Pet's Claude Code hook (feeds the pet and the Office)
                                 `pick-folder`   the folder dialog the app opens
                                 `install-pet` / `uninstall-pet`  add or remove the pet's hooks (the installer runs these)
                                 `shot <file or URL> [seconds]`   a screenshot for agents to look at (lithnode-shot)
                                 `mcp`           Lithnode's MCP server, so Claude can build and run flows (mcp_server.py)
"""
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

PET_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Notification",
              "Stop", "SubagentStart", "SubagentStop", "SessionEnd")
PET_ASYNC = set(PET_EVENTS) - {"SessionStart", "SessionEnd"}   # Claude doesn't wait on these; the ends stay in step
SETTINGS = Path.home() / ".claude" / "settings.json"


def _store():
    """Installed from the Microsoft Store (an MSIX package): our files sit in a folder other programs can't run from."""
    if os.name != "nt":
        return False
    import ctypes
    length = ctypes.c_uint32(0)
    # 15700 = APPMODEL_ERROR_NO_PACKAGE: a normal install; anything else (122, buffer too small) means packaged
    return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700


def _cli():
    if _store():   # the package's lithnode-cli alias, which any program (Claude Code's hooks too) can run
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Microsoft" / "WindowsApps" / "lithnode-cli.exe"
    return Path(sys.executable).with_name("lithnode-cli" + (".exe" if os.name == "nt" else ""))


def _is_pet_hook(command, source_too):
    """Our own hook; with source_too also Claude Pet run from source, which the installed copy replaces."""
    c = str(command).replace("\\", "/").lower()
    return "lithnode-cli" in c or (source_too and "claude pet/hook.py" in c)


def _strip(hooks, source_too=False):
    for event in list(hooks):
        kept = []
        for entry in hooks[event] if isinstance(hooks[event], list) else []:
            inner = [h for h in entry.get("hooks", []) if not _is_pet_hook(h.get("command", ""), source_too)]
            if inner:
                kept.append({**entry, "hooks": inner})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]


def _load():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _save(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_suffix(".json.lithnode-tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, SETTINGS)


def install_pet():
    data = _load()   # a settings file that isn't valid JSON raises here: better than overwriting it
    backup = SETTINGS.with_name("settings.json.before-lithnode")
    if SETTINGS.exists() and not backup.exists():
        shutil.copy2(SETTINGS, backup)
    hooks = data.setdefault("hooks", {})
    if "claude-pet-cli" in json.dumps(hooks).lower():
        return   # the standalone Claude Pet app is installed and runs the pet itself
    _strip(hooks, source_too=True)   # one pet only: the installed copy replaces a from-source one
    cli = _cli().as_posix()
    for event in PET_EVENTS:
        # a Store uninstall can't remove these hooks, and then the alias is gone: `|| true` keeps Claude Code quiet
        hook = {"type": "command", "command": f'"{cli}" hook {event}' + (" || true" if _store() else "")}
        if event in PET_ASYNC:
            hook["async"] = True
        hooks.setdefault(event, []).append({"hooks": [hook]})
    _save(data)


def uninstall_pet():
    if not SETTINGS.exists():
        return
    data = _load()
    hooks = data.get("hooks") or {}
    before = json.dumps(hooks)
    _strip(hooks)
    if json.dumps(hooks) != before:
        if not hooks:
            data.pop("hooks", None)
        _save(data)


def pick_folder():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    print(filedialog.askdirectory(title="Pick the folder your agents work in") or "")


def main():
    args = sys.argv[1:]
    cli = Path(sys.executable).stem.lower() == "lithnode-cli"
    if cli and args[:1] == ["hook"]:
        sys.argv = ["hook.py", *args[1:]]
        runpy.run_module("hook", run_name="__main__")
    elif cli and args[:1] == ["pick-folder"]:
        pick_folder()
    elif cli and args[:1] == ["install-pet"]:
        install_pet()
    elif cli and args[:1] == ["uninstall-pet"]:
        uninstall_pet()
    elif cli and args[:1] == ["shot"]:
        import shot
        sys.exit(shot.main(args[1:]))
    elif cli and args[:1] == ["mcp"]:
        import mcp_server
        mcp_server.main()
    elif not cli and args[:1] == ["pet"]:
        sys.argv = ["pet.py"]
        runpy.run_module("pet", run_name="__main__")
    elif not cli:
        import hq
        hq.main()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
