"""API keys: an add-on engine next to the CLI sign-ins. Paste a key for a provider and teams can run on its models.

Keys live in keys.json in Lithnode's folder. On Windows each one is encrypted for your Windows account (DPAPI), so
copying the file to another account or PC doesn't give the key away. Elsewhere the file is readable only by you.
Keys never go into flows, exported team files or anything the page gets back except their last four characters.

Like Ollama, an API team gets one streamed answer from the model: no tools, files or web. It's billed per token by
the provider, on your key.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# kind: "openai" speaks the OpenAI chat-completions API (most providers do); "anthropic" is Anthropic's Messages API
PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"name": "OpenAI", "base": "https://api.openai.com/v1", "kind": "openai", "color": "#10a37f",
               "site": "https://platform.openai.com/api-keys"},
    "anthropic": {"name": "Anthropic", "base": "https://api.anthropic.com/v1", "kind": "anthropic", "color": "#D97757",
                  "site": "https://console.anthropic.com/settings/keys"},
    "gemini": {"name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "kind": "openai",
               "color": "#4fa8ff", "site": "https://aistudio.google.com/apikey"},
    "openrouter": {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "kind": "openai", "color": "#8b7cff",
                   "site": "https://openrouter.ai/keys"},
    "groq": {"name": "Groq", "base": "https://api.groq.com/openai/v1", "kind": "openai", "color": "#ff8a65",
             "site": "https://console.groq.com/keys"},
    "xai": {"name": "xAI", "base": "https://api.x.ai/v1", "kind": "openai", "color": "#ededed", "site": "https://console.x.ai"},
    "deepseek": {"name": "DeepSeek", "base": "https://api.deepseek.com/v1", "kind": "openai", "color": "#5b8def",
                 "site": "https://platform.deepseek.com/api_keys"},
    "mistral": {"name": "Mistral", "base": "https://api.mistral.ai/v1", "kind": "openai", "color": "#ffb547",
                "site": "https://console.mistral.ai/api-keys"},
}
ANTHROPIC_VERSION = "2023-06-01"
MAX_OUTPUT = 8192
ROOT = Path(os.environ.get("LITHNODE_HOME") or Path.home() / ".lithnode")   # hq.py points this at its own folder
_lock = threading.Lock()
_models: dict[str, tuple[float, list[dict[str, str]]]] = {}


def init(root: str | Path) -> None:
    global ROOT
    ROOT = Path(root)


# --------------------------------------------------------------- storage

def _protect(raw: bytes, decrypt: bool = False) -> bytes:
    """Windows: DPAPI, tied to this Windows account. Other systems: as is (the file itself is private)."""
    if os.name != "nt":
        return raw
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(raw, len(raw))
    src, out = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("Windows couldn't " + ("unlock" if decrypt else "lock") + " the key")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _path() -> Path:
    return ROOT / "keys.json"


def _load() -> dict[str, str]:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if k in PROVIDERS and isinstance(v, str)} if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def get_key(provider: str) -> str:
    sealed = _load().get(provider)
    if not sealed:
        return ""
    try:
        return _protect(base64.b64decode(sealed), decrypt=True).decode("utf-8")
    except (OSError, ValueError):
        return ""


def _write(data: dict[str, str]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def set_key(provider: str, key: str) -> None:
    with _lock:
        data = _load()
        data[provider] = base64.b64encode(_protect(key.encode("utf-8"))).decode("ascii")
        _write(data)
    _models.pop(provider, None)


def delete_key(provider: str) -> None:
    with _lock:
        data = _load()
        data.pop(provider, None)
        _write(data)
    _models.pop(provider, None)


def saved() -> list[str]:
    return [p for p in PROVIDERS if _load().get(p)]


def public() -> list[dict[str, Any]]:
    """What the page may see: which providers have a key, and its last four characters."""
    out = []
    for pid, p in PROVIDERS.items():
        key = get_key(pid)
        out.append({"id": pid, "name": p["name"], "color": p["color"], "site": p["site"], "set": bool(key), "last4": key[-4:] if key else ""})
    return out


# --------------------------------------------------------------- talking to providers

def _headers(provider: str, key: str) -> dict[str, str]:
    if PROVIDERS[provider]["kind"] == "anthropic":
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "Content-Type": "application/json"}
    head = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        head.update({"HTTP-Referer": "https://lithnode.com", "X-Title": "Lithnode"})
    return head


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8", "replace"))
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else err if isinstance(err, str) else body.get("message")
        return str(msg or exc.reason)[:300]
    except (OSError, ValueError, AttributeError):
        return str(exc.reason)


def fetch_models(provider: str, key: str | None = None, timeout: float = 20) -> tuple[list[dict[str, str]], str]:
    """([{"id", "label"}], error). Listing models is free on every provider here, so it also checks a key works."""
    key = key if key is not None else get_key(provider)
    if not key:
        return [], "No key saved."
    req = urllib.request.Request(PROVIDERS[provider]["base"] + "/models", headers=_headers(provider, key))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return [], ("That key was turned down: " if exc.code in (401, 403) else f"{PROVIDERS[provider]['name']} said: ") + _error_text(exc)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return [], f"Couldn't reach {PROVIDERS[provider]['name']} ({exc})."
    rows = data.get("data") if isinstance(data, dict) else None
    out = []
    for m in rows if isinstance(rows, list) else []:
        mid = str(m.get("id") or "").removeprefix("models/")
        if mid and not any(skip in mid for skip in ("embed", "whisper", "tts", "dall-e", "moderation", "image", "audio", "transcribe")):
            out.append({"id": mid, "label": str(m.get("display_name") or m.get("name") or mid)})
    return out, ""


def models(force: bool = False) -> list[dict[str, str]]:
    """Every model on every saved key, as "provider:model" ids for the API engine. Cached for 10 minutes."""
    out = []
    for pid in saved():
        hit = _models.get(pid)
        if not hit or force or time.time() - hit[0] > 600:
            found, _ = fetch_models(pid)
            hit = (time.time(), found[:200])
            _models[pid] = hit
        name = PROVIDERS[pid]["name"]
        out += [{"id": f"{pid}:{m['id']}", "label": f"{name} · {m['label']}"} for m in hit[1] if len(pid) + 1 + len(m["id"]) <= 60]
    return out


def split_model(model: str) -> tuple[str, str]:
    pid, _, mid = (model or "").partition(":")
    if pid in PROVIDERS and mid:
        return pid, mid
    keys = saved()   # no model picked: the first saved key, and its first model
    if not keys:
        return "", ""
    first = next((m["id"] for m in models() if m["id"].startswith(keys[0] + ":")), "")
    return keys[0], first.partition(":")[2]


def chat(model: str, system: str, prompt: str, on_text: Any, stopped: Any, timeout: float) -> tuple[str, str, int]:
    """One streamed answer. `on_text(total_so_far)` sees it grow; `stopped()` ends it early. Returns (text, error, tokens)."""
    pid, mid = split_model(model)
    if not pid:
        return "", "No API key saved. Add one in Settings > API keys.", 0
    key = get_key(pid)
    if not key:
        return "", f"There's no {PROVIDERS[pid]['name']} key saved. Add it in Settings > API keys.", 0
    if not mid:
        return "", f"Pick a {PROVIDERS[pid]['name']} model for this team.", 0
    p = PROVIDERS[pid]
    if p["kind"] == "anthropic":
        body = {"model": mid, "max_tokens": MAX_OUTPUT, "stream": True, "system": system, "messages": [{"role": "user", "content": prompt}]}
        url = p["base"] + "/messages"
    else:
        body = {"model": mid, "stream": True, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if pid in ("openai", "openrouter", "groq", "deepseek", "xai"):
            body["stream_options"] = {"include_usage": True}
        url = p["base"] + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_headers(pid, key))
    text: list[str] = []
    tokens = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                if stopped():
                    return "".join(text), "Stopped", tokens
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                piece, used = _piece(p["kind"], obj)
                if isinstance(obj, dict) and obj.get("type") == "error":
                    return "".join(text), str((obj.get("error") or {}).get("message") or "The provider reported an error."), tokens
                tokens = max(tokens, used) if p["kind"] == "openai" else tokens + used
                if piece:
                    text.append(piece)
                    on_text("".join(text))
    except urllib.error.HTTPError as exc:
        return "", f"{p['name']} couldn't run {mid}: {_error_text(exc)}", 0
    except (OSError, urllib.error.URLError) as exc:
        return "".join(text), f"Couldn't reach {p['name']} ({exc}).", tokens
    out = "".join(text).strip()
    if not tokens:   # the provider didn't say: about four characters a token
        tokens = (len(system) + len(prompt) + len(out)) // 4
    return out, "", tokens


def _piece(kind: str, obj: Any) -> tuple[str, int]:
    """(new text, tokens reported) from one streamed event."""
    if not isinstance(obj, dict):
        return "", 0
    if kind == "anthropic":
        t = obj.get("type")
        if t == "content_block_delta":
            return str((obj.get("delta") or {}).get("text") or ""), 0
        if t == "message_start":
            use = (obj.get("message") or {}).get("usage") or {}
            return "", int(use.get("input_tokens") or 0) + int(use.get("output_tokens") or 0)
        if t == "message_delta":
            return "", int((obj.get("usage") or {}).get("output_tokens") or 0)
        return "", 0
    use = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
    choices = obj.get("choices") or []
    delta = (choices[0].get("delta") or {}) if choices and isinstance(choices[0], dict) else {}
    return str(delta.get("content") or ""), int(use.get("total_tokens") or 0)
