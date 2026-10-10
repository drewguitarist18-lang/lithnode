"""lithnode-shot: a screenshot of a web page or HTML file, so an agent can look at what it made.

    lithnode-shot <file or URL> [seconds] [--size 1280x800]

Saves a PNG under .lithnode-shots/ in the current folder and prints its path; the agent then reads that image.
For an HTML file, `seconds` freezes its CSS animations at that moment, so an animated ad can be checked frame by
frame (pages driven by JavaScript timers show their state after that long). Uses Microsoft Edge or Chrome, headless.
Lithnode puts this command on the agents' PATH (see bin_dir); the packaged app runs it as `lithnode-cli shot`.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BROWSERS = [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
FLATPAK = bool(os.environ.get("FLATPAK_ID")) and os.name != "nt"
NAMES = ("msedge", "chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
FREEZE = ("<script>addEventListener('load',function(){var t=%d;setTimeout(function(){document.getAnimations().forEach("
          "function(a){try{a.pause();a.currentTime=t}catch(e){}})},0)})</script>")


def browser():
    if FLATPAK:   # the Linux Flatpak: use the browser on your system, outside the sandbox
        import claude_code
        claude_code.fix_path()
        return next(filter(None, map(claude_code.which, NAMES)), None)
    for b in BROWSERS:
        path = os.path.expandvars(b)
        if "%" not in path and os.path.exists(path):
            return path
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def shot(target, seconds=2.0, size="1280x800", out_dir=None):
    """Returns the PNG's path. Raises RuntimeError with a plain reason if it can't."""
    exe = browser()
    if not exe:
        raise RuntimeError("No Chrome, Edge or Chromium on this computer to take the screenshot with.")
    if not re.fullmatch(r"\d{2,4}x\d{2,4}", size):
        raise RuntimeError("Size must look like 1280x800.")
    out_dir = Path(out_dir or Path.cwd() / ".lithnode-shots")
    out_dir.mkdir(parents=True, exist_ok=True)
    temp = None
    if re.match(r"https?://", target):
        url, name = target, re.sub(r"\W+", "-", target.split("://", 1)[1]).strip("-")[:40] or "page"
    else:
        path = Path(target).resolve()
        if not path.is_file():
            raise RuntimeError(f"There's no file at {path}.")
        name = path.stem
        for stale in path.parent.glob(".lithnode-shot-*"):   # copies left behind by a run that was cut off
            if time.time() - stale.stat().st_mtime > 300:
                stale.unlink(missing_ok=True)
        if path.suffix.lower() in (".html", ".htm"):
            # a copy beside the original (so its relative links still work) that freezes animations at `seconds`
            html = path.read_text(encoding="utf-8", errors="replace")
            freeze = FREEZE % int(seconds * 1000)
            html = re.sub(r"</body\s*>", freeze + "</body>", html, count=1, flags=re.I) if re.search(r"</body\s*>", html, re.I) else html + freeze
            temp = path.with_name(f".lithnode-shot-{os.getpid()}-{path.name}")
            temp.write_text(html, encoding="utf-8")
            url = temp.as_uri()
        else:
            url = path.as_uri()
    out = out_dir / f"{name}-{seconds:g}s.png"
    out.unlink(missing_ok=True)   # so an old picture is never mistaken for this one
    w, h = size.split("x")
    host = (lambda a: a)
    if FLATPAK:
        import claude_code
        host = claude_code.host
    profile = tempfile.mkdtemp(prefix="lithnode-shot-", dir=claude_code.shared_tmp() if FLATPAK else None)
    try:
        subprocess.run(host([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
                        f"--user-data-dir={profile}", f"--window-size={w},{h}", f"--virtual-time-budget={int(seconds * 1000) + 800}",
                        f"--screenshot={out}", url]), capture_output=True, timeout=60, creationflags=NO_WINDOW)
        # Edge hands the work to a background process and returns at once: wait for the picture to land
        deadline = time.time() + seconds + 30
        while time.time() < deadline and not (out.exists() and out.stat().st_size > 0):
            time.sleep(0.25)
        time.sleep(0.3)   # let it finish writing
    except subprocess.TimeoutExpired:
        raise RuntimeError("The browser took too long to draw the page.")
    finally:
        if temp:
            for _ in range(10):   # the browser may still hold the file for a moment
                try:
                    temp.unlink()
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    time.sleep(0.2)
        shutil.rmtree(profile, ignore_errors=True)
    if not out.exists():
        raise RuntimeError("The browser didn't save a screenshot.")
    return out


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    size = "1280x800"
    if "--size" in args:
        i = args.index("--size")
        size = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    try:
        seconds = float(args[1]) if len(args) > 1 else 2.0
        print(shot(args[0], max(0.0, min(seconds, 120.0)), size))
        return 0
    except ValueError:
        print("Seconds must be a number, like 3 or 4.5.", file=sys.stderr)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
    return 1


def bin_dir(home, command):
    """Writes the `lithnode-shot` command (a shell script for Git Bash, a .cmd for Windows shells) into home/bin and
    returns that folder, for the agents' PATH. `command` is how to run this tool, as a list."""
    folder = Path(home) / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    posix = " ".join(f'"{Path(c).as_posix()}"' if i == 0 or c.endswith(".py") else c for i, c in enumerate(command))
    sh = folder / "lithnode-shot"
    sh.write_text(f'#!/bin/sh\nexec {posix} "$@"\n', encoding="utf-8", newline="\n")
    sh.chmod(0o755)
    win = " ".join(f'"{c}"' if i == 0 or c.endswith(".py") else c for i, c in enumerate(command))
    (folder / "lithnode-shot.cmd").write_text(f"@echo off\r\n{win} %*\r\n", encoding="utf-8", newline="")
    return folder


if __name__ == "__main__":
    sys.exit(main())
