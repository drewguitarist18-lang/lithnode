"""lithnode-shot: look at a web page or HTML file, or use it, so an agent can check what it made.

    lithnode-shot <file or URL> [seconds] [--size 1280x800]
        A screenshot. Saves a PNG under .lithnode-shots/ and prints its path; read that image.
        For an HTML file, `seconds` freezes its CSS animations at that moment, so an animated ad can be checked
        frame by frame (pages driven by JavaScript timers show their state after that long).

    lithnode-shot <HTML file> --do "<step>" [--do "<step>" ...] [--size 1280x800]
        Uses the page like a person would, then prints what happened at each step, any JavaScript errors, the
        text on the page, and screenshots (one after the last step, plus one wherever a step says `shot`).
        Steps (several can go in one --do, split by ;):
          click <CSS selector | text=Button words | x,y>    move <x,y | selector>    type <CSS selector> <text>
          press <key>    hold <key>    release <key>    wait <seconds>    reload    shot
        Keys: Enter, Space, Escape, Tab, Backspace, ArrowUp/Down/Left/Right, or a letter. x,y are pixels in the
        screenshot (1280x800 unless --size). Each run starts fresh, with empty storage.

Uses Microsoft Edge or Chrome, headless. Lithnode puts this command on the agents' PATH (see bin_dir); the
packaged app runs it as `lithnode-cli shot`.
"""
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BROWSERS = [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe", r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
FLATPAK = bool(os.environ.get("FLATPAK_ID")) and os.name != "nt" and "org.freedesktop.Flatpak=talk" in (
    Path("/.flatpak-info").read_text(encoding="utf-8", errors="replace") if Path("/.flatpak-info").exists() else "")
NAMES = ("msedge", "chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
FREEZE = ("<script>addEventListener('load',function(){var t=%d;setTimeout(function(){document.getAnimations().forEach("
          "function(a){try{a.pause();a.currentTime=t}catch(e){}})},0)})</script>")
STEP_RE = re.compile(r"^(click|move|type|press|hold|release|wait|reload|shot)\b\s*(.*)$", re.I | re.S)
MAX_STEPS, MAX_SHOTS = 40, 4

# Runs inside the page: does the steps one by one (carrying on across a `reload`), notes errors, then sends a
# report back to the little server that served the page. Events are synthetic, so they reach the page's own
# handlers the way a person's clicks and keys would.
ACT_JS = r"""<script>(function(){
var STEPS=__STEPS__, REPORT=__REPORT__, KEY='__lithnode_act', st=null;
try{st=JSON.parse(sessionStorage.getItem(KEY)||'null')}catch(e){}
if(!st)st={i:0,out:[],errors:[]};
function save(){try{sessionStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function note(t){if(st.errors.length<20)st.errors.push(String(t).slice(0,300))}
var ce=console.error;console.error=function(){note([].map.call(arguments,function(a){return a&&a.stack||String(a)}).join(' '));return ce.apply(console,arguments)};
addEventListener('error',function(e){if(e.message)note(e.message+(e.lineno?' (line '+e.lineno+')':''));else if(e.target&&e.target.src)note('Could not load '+e.target.src)},true);
addEventListener('unhandledrejection',function(e){note('Unhandled promise: '+(e.reason&&e.reason.message||e.reason))});
function shown(e){var r=e.getBoundingClientRect();return r.width>0&&r.height>0}
function words(e){return (e.innerText||e.value||e.getAttribute('aria-label')||'').trim()}
function find(s){
  if(/^text=/i.test(s)){var t=s.slice(5).trim().toLowerCase(),best=null;
    document.querySelectorAll('button,a,label,summary,[role=button],[onclick],input[type=submit],input[type=button],li,td,span,div,p,h1,h2,h3,h4').forEach(function(e){
      var x=words(e).toLowerCase();if(!shown(e)||x.indexOf(t)<0)return;
      if(!best||x.length<words(best).length)best=e});
    return best}
  try{return document.querySelector(s)}catch(e){throw Error('"'+s+'" is not a valid CSS selector')}}
function xy(s){var m=/^\s*(\d+)\s*,\s*(\d+)\s*$/.exec(s);return m?[+m[1],+m[2]]:null}
function target(s){
  var p=xy(s);if(p){var el=document.elementFromPoint(p[0],p[1]);if(!el)throw Error('nothing on the page at '+s);return [el,p]}
  var el=find(s);if(!el)throw Error('nothing matches "'+s+'"');el.scrollIntoView({block:'center'});
  var r=el.getBoundingClientRect();return [el,[r.left+r.width/2,r.top+r.height/2]]}
function mouse(el,type,p){
  var o={bubbles:true,cancelable:true,composed:true,clientX:p[0],clientY:p[1],button:0,buttons:/down/.test(type)?1:0,view:window};
  if(/^pointer/.test(type)&&window.PointerEvent){o.pointerId=1;o.pointerType='mouse';o.isPrimary=true;return el.dispatchEvent(new PointerEvent(type,o))}
  return el.dispatchEvent(new MouseEvent(type,o))}
var CODES={Enter:13,Tab:9,Escape:27,Backspace:8,ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40,Space:32,' ':32};
function key(type,k){
  var name=k==='Space'?' ':k,code=k==='Space'||k===' '?'Space':k.length===1?(/[a-z]/i.test(k)?'Key'+k.toUpperCase():/\d/.test(k)?'Digit'+k:k):k;
  var e=new KeyboardEvent(type,{key:name,code:code,bubbles:true,cancelable:true,composed:true});
  var kc=CODES[k]||(k.length===1?k.toUpperCase().charCodeAt(0):0);
  Object.defineProperty(e,'keyCode',{get:function(){return kc}});Object.defineProperty(e,'which',{get:function(){return kc}});
  return (document.activeElement||document.body).dispatchEvent(e)}
function step(s){
  var m=/^(\w+)\s*([\s\S]*)$/.exec(s.trim()),verb=m[1].toLowerCase(),arg=m[2].trim();
  if(verb==='click'){var t=target(arg),el=t[0],p=t[1];
    ['pointerover','mouseover','pointermove','mousemove','pointerdown','mousedown'].forEach(function(n){mouse(el,n,p)});
    if(el.focus)el.focus();
    ['pointerup','mouseup','click'].forEach(function(n){mouse(el,n,p)});return 0}
  if(verb==='move'){var t=target(arg);['pointerover','mouseover','pointermove','mousemove'].forEach(function(n){mouse(t[0],n,t[1])});return 0}
  if(verb==='type'){var mm=/^(\S+)\s+([\s\S]*)$/.exec(arg);if(!mm)throw Error('type needs a selector and some text');
    var el=find(mm[1]);if(!el)throw Error('nothing matches "'+mm[1]+'"');el.focus();
    var proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,d=Object.getOwnPropertyDescriptor(proto,'value');
    if(el.isContentEditable)el.textContent=mm[2];else if(d&&d.set)d.set.call(el,mm[2]);else el.value=mm[2];
    el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return 0}
  if(verb==='press'){if(!arg)throw Error('press needs a key');var go=key('keydown',arg);if(arg.length===1||arg==='Enter')key('keypress',arg);key('keyup',arg);
    var a=document.activeElement;
    if(go&&arg==='Enter'&&a&&a.form&&a.tagName==='INPUT'){if(a.form.requestSubmit)a.form.requestSubmit();else a.form.submit()}
    if(go&&(arg==='Space'||arg===' '||arg==='Enter')&&a&&/^(BUTTON|A|SUMMARY)$/.test(a.tagName)&&arg!=='Enter'?1:0)a.click();
    return 0}
  if(verb==='hold'){key('keydown',arg);return 0}
  if(verb==='release'){key('keyup',arg);return 0}
  if(verb==='wait'){var sec=parseFloat(arg);if(!(sec>=0))throw Error('wait needs seconds, like wait 2');return Math.min(sec,120)*1000}
  if(verb==='reload'){return -1}
  throw Error('unknown step "'+verb+'"')}
function finish(){
  if(!REPORT)return;
  var text=(document.body&&document.body.innerText||'').replace(/\n{3,}/g,'\n\n').trim();
  var body=JSON.stringify({steps:st.out,errors:st.errors,title:document.title,text:text.slice(0,2500)});
  try{sessionStorage.removeItem(KEY)}catch(e){}
  fetch('/__lithnode__/report',{method:'POST',body:body,keepalive:true})}
function next(){
  if(st.i>=STEPS.length){setTimeout(finish,400);return}
  var s=STEPS[st.i],delay=150;
  try{delay=step(s);st.out.push([s,'ok']);st.i++}
  catch(e){st.out.push([s,String(e.message||e)]);st.i=STEPS.length;save();setTimeout(finish,300);return}
  save();
  if(delay<0){location.reload();return}
  setTimeout(next,Math.max(150,delay))}
if(document.readyState==='complete')setTimeout(next,300);else addEventListener('load',function(){setTimeout(next,300)});
})();</script>"""


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


def _capture(exe, url, out, budget_ms, size, wait_for=None):
    """Opens url in a fresh headless browser, lets it run for budget_ms of page time, and saves a screenshot to out.
    `wait_for` (a threading.Event) also waits for the page's report to arrive."""
    w, h = size.split("x")
    host = (lambda a: a)
    if FLATPAK:
        import claude_code
        host = claude_code.host
    profile = tempfile.mkdtemp(prefix="lithnode-shot-", dir=__import__("claude_code").shared_tmp() if FLATPAK else None)
    out.unlink(missing_ok=True)   # so an old picture is never mistaken for this one
    try:
        subprocess.run(host([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
                        f"--user-data-dir={profile}", f"--window-size={w},{h}", f"--virtual-time-budget={int(budget_ms)}",
                        f"--screenshot={out}", url]), capture_output=True, timeout=60 + budget_ms / 1000, creationflags=NO_WINDOW)
        # Edge hands the work to a background process and returns at once: wait for the picture (and report) to land
        deadline = time.time() + budget_ms / 1000 + 30
        while time.time() < deadline and not (out.exists() and out.stat().st_size > 0 and (wait_for is None or wait_for.is_set())):
            time.sleep(0.25)
        time.sleep(0.3)   # let it finish writing
    except subprocess.TimeoutExpired:
        raise RuntimeError("The browser took too long to draw the page.")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not out.exists():
        raise RuntimeError("The browser didn't save a screenshot.")
    return out


def _check(size, exe):
    if not exe:
        raise RuntimeError("No Chrome, Edge or Chromium on this computer to take the screenshot with.")
    if not re.fullmatch(r"\d{2,4}x\d{2,4}", size):
        raise RuntimeError("Size must look like 1280x800.")


def shot(target, seconds=2.0, size="1280x800", out_dir=None):
    """Returns the PNG's path. Raises RuntimeError with a plain reason if it can't."""
    exe = browser()
    _check(size, exe)
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
    try:
        return _capture(exe, url, out_dir / f"{name}-{seconds:g}s.png", seconds * 1000 + 800, size)
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


def parse_steps(raw):
    """--do values -> a list of steps, each checked. Raises RuntimeError on one it doesn't know."""
    steps = []
    for value in raw:
        for part in value.split(";"):
            part = part.strip()
            if not part:
                continue
            if not STEP_RE.match(part):
                raise RuntimeError(f'"{part}" isn\'t a step. Start each one with click, move, type, press, hold, release, '
                                   "wait, reload or shot.")
            steps.append(part)
    if not steps:
        raise RuntimeError("Give at least one step, like --do \"click text=Start\".")
    if len(steps) > MAX_STEPS:
        raise RuntimeError(f"At most {MAX_STEPS} steps at a time.")
    return steps


def _budget(steps, seconds):
    """How much page time a list of steps needs, in ms."""
    ms = 1500 + seconds * 1000
    for s in steps:
        verb, arg = STEP_RE.match(s).group(1).lower(), STEP_RE.match(s).group(2)
        try:
            ms += min(float(arg), 120) * 1000 if verb == "wait" else 1200 if verb == "reload" else 200
        except ValueError:
            ms += 200
    return ms


def _serve(root, page, steps, report):
    """A server on 127.0.0.1 for root's files that adds the step script to `page`. Returns (server, report box)."""
    box = {"report": None, "event": threading.Event()}
    script = (ACT_JS.replace("__STEPS__", json.dumps(steps).replace("</", "<\\/"))
              .replace("__REPORT__", "true" if report else "false"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            if urlparse(self.path).path == "/__lithnode__/report":
                body = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 200_000))
                try:
                    box["report"] = json.loads(body)
                except ValueError:
                    box["report"] = {"steps": [], "errors": ["The page sent back a report that couldn't be read."]}
                box["event"].set()
            self.send_response(204)
            self.end_headers()

        def do_GET(self):
            rel = unquote(urlparse(self.path).path).lstrip("/")
            path = (root / rel).resolve() if rel else page
            if path != page and (root not in path.parents or not path.is_file()):
                self.send_response(404)
                self.end_headers()
                return
            body = path.read_bytes()
            if path == page:
                html = body.decode("utf-8", errors="replace")
                m = re.search(r"<head[^>]*>", html, re.I)
                html = html[:m.end()] + script + html[m.end():] if m else script + html
                body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if path == page
                             else mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, box


def act(target, steps, size="1280x800", out_dir=None):
    """Uses an HTML file through `steps`. Returns {'steps', 'errors', 'title', 'text', 'shots': [(label, path)]}."""
    exe = browser()
    _check(size, exe)
    path = Path(target).resolve()
    if re.match(r"https?://", target) or path.suffix.lower() not in (".html", ".htm"):
        raise RuntimeError("--do works on HTML files (a page you made), not URLs or other files.")
    if not path.is_file():
        raise RuntimeError(f"There's no file at {path}.")
    out_dir = Path(out_dir or Path.cwd() / ".lithnode-shots")
    out_dir.mkdir(parents=True, exist_ok=True)
    marks = [i for i, s in enumerate(steps) if s.lower() == "shot"][:MAX_SHOTS]
    plain = [s for s in steps if s.lower() != "shot"]
    shots = []
    for n, i in enumerate(marks, 1):   # a fresh run up to each `shot`, photographed there
        before = [s for s in steps[:i] if s.lower() != "shot"]
        server, _ = _serve(path.parent, path, before, False)
        try:
            out = _capture(exe, f"http://127.0.0.1:{server.server_port}/{path.name}", out_dir / f"{path.stem}-shot{n}.png",
                           _budget(before, 0.5), size)
            shots.append((f"after step {len(before)}", out))
        finally:
            server.shutdown()
    server, box = _serve(path.parent, path, plain, True)
    try:
        out = _capture(exe, f"http://127.0.0.1:{server.server_port}/{path.name}", out_dir / f"{path.stem}-after.png",
                       _budget(plain, 0.5), size, wait_for=box["event"])
        shots.append(("after the last step", out))
    finally:
        server.shutdown()
    report = box["report"] or {"steps": [], "errors": ["The page never finished the steps: it may have frozen, "
                                                        "navigated away, or a step took longer than its wait."]}
    report["shots"] = shots
    return report


def describe(report):
    lines = ["Steps:"]
    done = report.get("steps") or []
    for n, (step, result) in enumerate(done, 1):
        lines.append(f"  {n}. {step}: {result}")
    if not done:
        lines.append("  (none ran)")
    errors = report.get("errors") or []
    lines.append("JavaScript errors: " + ("none" if not errors else ""))
    lines += [f"  - {e}" for e in errors]
    lines.append("Screenshots (read them to see the page):")
    lines += [f"  {label}: {p}" for label, p in report.get("shots") or []]
    text = (report.get("text") or "").strip()
    lines.append("Text on the page after the steps:" + ("" if text else " (none; a canvas game draws its text, so look at the screenshots)"))
    if text:
        lines += ["  " + ln for ln in text.splitlines()]
    return "\n".join(lines)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    size, steps = "1280x800", []
    if "--size" in args:
        i = args.index("--size")
        size = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    while "--do" in args:
        i = args.index("--do")
        steps.append(args[i + 1] if i + 1 < len(args) else "")
        del args[i:i + 2]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    for stream in (sys.stdout, sys.stderr):   # page text can hold any character; a Windows console can't show them all
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        if steps:
            print(describe(act(args[0], parse_steps(steps), size)))
            return 0
        try:
            seconds = float(args[1]) if len(args) > 1 else 2.0
        except ValueError:
            print("Seconds must be a number, like 3 or 4.5.", file=sys.stderr)
            return 1
        print(shot(args[0], max(0.0, min(seconds, 120.0)), size))
        return 0
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
