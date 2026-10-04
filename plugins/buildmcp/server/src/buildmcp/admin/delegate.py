"""Undemanding work for cheaper models, so Claude's limits go to what needs Claude: the Gemini CLI on
this PC (headless, JSON output) and the Mistral API (codestral for code, mistral-small for text).

What goes out: texts (plugin messages, translations, MOTDs, descriptions), explanations of logs and
errors, config drafts and conversions, small plugin code. Never building: spawns and structures, and
how they look (palettes, layouts, terrain), are made only by the assistant the owner works with
(Claude or Codex) with the building tools; this module refuses tasks that ask for them.
Gemini answers read-only (approval mode plan); with edit=True it may change files only inside a
devplugin project, and the changed files come back as a diff for Claude to review.
Every call is logged in <data>/delegate-usage.jsonl.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import net

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODELS = {"code": "codestral-latest", "text": "mistral-small-latest"}
MAX_CONTEXT = 120_000        # characters of context files sent with a task
MAX_FILE = 60_000

SYSTEM = (
    "You help the assistant (Claude) of a Minecraft server owner. You get one self-contained task: do exactly "
    "that, completely, without chit-chat or questions. When the task asks for a file, answer with the whole file "
    "in one fenced code block. Keep Minecraft specifics right: YAML indentation and quoting, MiniMessage and "
    "legacy color codes, plugin.yml fields, Paper/Velocity APIs, Java 21. If something is ambiguous, state your "
    "assumption in one line first. Answer in the language of the task unless it says otherwise.")

# asks to produce builds: the BuildMCP scene API, WorldEdit edits, schematics, or "build a spawn/hub/..."
# (but "make a lobby plugin / menu / config" is code or text and may go out)
_NOT_A_BUILD = (r"(?![\s-]*(plugin|config|menu|selector|item|command|message|scoreboard|tab|npc|hologram|"
                r"permission|rank|chat|motd|text|description|defen[cs]e|minigame|game|mode|world ?border|"
                r"плагин|конфиг|меню|предмет|команд|сообщ|текст|описан|табл|голограм|прав|режим|мини-?игр))")
_BUILD_TASK = re.compile(
    r"run_script|\bscene\s*[.\[]|\bgen\.\w+\(|\bpalette\s*[.\[(]|\bsetblock\b|//\s*(set|paste|replace|walls|sphere|cyl|"
    r"stack|copy)\b|\.schem\b|\bschematic|"
    r"\b(build|construct|design|make|create|generate)\w*\s+(me\s+|a\s+|an\s+|the\s+|new\s+|our\s+)*"
    r"(spawn|hub|lobby|castle|tower|island|arena|village|house|temple)s?\b" + _NOT_A_BUILD + "|"
    r"(постро|строи|выстро|сострои|спроектир|сгенерир|сделай|создай)\w*\s+(мне\s+|новый\s+|новую\s+|новое\s+)*"
    r"(спавн|хаб|лобби|замок|башн|остров|арен|деревн|дом|храм|постройк|здани)\w*" + _NOT_A_BUILD,
    re.I)
# asks how a build should look: its palette, layout, massing, facade, terrain... is building too
_BUILD_EN = r"(spawn|hub|lobby|castle|tower|island|arena|village|house|temple|building|structure)s?"
_BUILD_RU = r"(спавн|хаб|лобби|зам(ок|к)|башн|остров|арен|деревн|\bдом(а|ов|у|ом|е)?\b|храм|постройк|здани)"
_LOOK_EN = (r"(palette|layout|blockout|block-?out|massing|silhouette|facade|fa[cç]ade|terrain|landscap\w*|"
            r"(which|what) blocks|block choice)")
_LOOK_RU = r"(палитр|раскладк|компоновк|планировк|силуэт|фасад|рельеф|ландшафт|террейн|каки[ехм] блок)"
_DESIGN_TASK = re.compile(
    rf"\b{_LOOK_EN}\b[^.\n]{{0,60}}\b{_BUILD_EN}\b|\b{_BUILD_EN}\b[^.\n]{{0,60}}\b{_LOOK_EN}|"
    rf"{_LOOK_RU}[^.\n]{{0,60}}{_BUILD_RU}|{_BUILD_RU}[^.\n]{{0,60}}{_LOOK_RU}", re.I)
# ...unless it is plainly about text: chat colors, messages, translations, lore, names
_TEXT_TASK = re.compile(r"(сообщ|чат|motd|цвет|colou?r|message|chat|translat|перев[оеё]д|\blore\b|\bлор|"
                        r"description|описан|\bnames?\b|назван)", re.I)


class DelegateError(RuntimeError):
    pass


def is_build_task(task: str) -> bool:
    """Building, or deciding how a build looks (palette, layout, terrain...): never for another model."""
    return bool(_BUILD_TASK.search(task) or (_DESIGN_TASK.search(task) and not _TEXT_TASK.search(task)))


# ------------------------------------------------------------------ gemini
def gemini_path() -> str | None:
    """The gemini executable: BUILDMCP_GEMINI_CLI, PATH, or npm's global folder."""
    env = os.environ.get("BUILDMCP_GEMINI_CLI", "").strip()
    if env and not env.startswith("${"):
        p = Path(env).expanduser()
        return str(p) if p.exists() else None
    found = shutil.which("gemini")
    if found:
        return found
    cands = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            cands += [Path(appdata) / "npm" / "gemini.cmd", Path(appdata) / "npm" / "gemini.exe"]
    else:
        cands += [Path.home() / ".npm-global" / "bin" / "gemini", Path("/usr/local/bin/gemini"),
                  Path("/opt/homebrew/bin/gemini")]
    return next((str(c) for c in cands if c.exists()), None)


def _clean_env() -> dict:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    return env


def gemini_version() -> str | None:
    exe = gemini_path()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60, env=_clean_env(),
                           encoding="utf-8", errors="replace")
        return (r.stdout.strip() or r.stderr.strip()).splitlines()[-1] if (r.stdout or r.stderr) else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def _json_in(text: str) -> dict | None:
    text = text.strip()
    try:
        d = json.loads(text)
        return d if isinstance(d, dict) else None
    except ValueError:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            d = json.loads(text[a:b + 1])
            return d if isinstance(d, dict) else None
        except ValueError:
            return None
    return None


def run_gemini(prompt: str, cwd: Path, model: str = "", edit: bool = False, timeout: float = 300) -> dict:
    exe = gemini_path()
    if not exe:
        raise DelegateError("Gemini CLI not found: install it (npm i -g @google/gemini-cli), log in once with "
                            "`gemini`, or set its path in the plugin settings (gemini_cli)")
    model = model or os.environ.get("BUILDMCP_GEMINI_MODEL", "").strip()
    if model.startswith("${"):
        model = ""
    # the task goes through stdin: gemini.cmd on Windows mangles quotes and other characters in arguments
    args = [exe, "-p", "Do the task given above.", "-o", "json", "--approval-mode", "auto_edit" if edit else "plan",
            "--skip-trust"]
    if model:
        args += ["-m", model]
    t0 = time.time()
    try:
        r = subprocess.run(args, input=prompt, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           env=_clean_env(), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        raise DelegateError(f"Gemini did not answer in {timeout:.0f} s") from e
    except OSError as e:
        raise DelegateError(f"cannot run {exe}: {e}") from e
    d = _json_in(r.stdout) or {}
    err = d.get("error") if isinstance(d.get("error"), dict) else None
    if err or (r.returncode != 0 and not d.get("response")):
        msg = (err or {}).get("message") or (r.stderr or r.stdout).strip()[-600:] or f"exit code {r.returncode}"
        raise DelegateError(f"Gemini failed: {msg}")
    stats = d.get("stats") or {}
    models = stats.get("models") or {}
    tokens = 0
    for m in models.values():
        t = (m or {}).get("tokens") or {}
        tokens += int(t.get("total") or 0)
    return {"answer": str(d.get("response") or "").strip(), "model": ", ".join(models) or model or "gemini (default)",
            "tokens": tokens, "seconds": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ mistral
def mistral_key() -> str:
    for var in ("BUILDMCP_MISTRAL_API_KEY", "MISTRAL_API_KEY"):
        v = os.environ.get(var, "").strip()
        if v and not v.startswith("${"):
            return v
    return ""


def run_mistral(prompt: str, kind: str = "text", model: str = "", timeout: float = 180,
                max_tokens: int = 8000) -> dict:
    key = mistral_key()
    if not key:
        raise DelegateError("no Mistral API key: set mistral_api_key in the plugin settings "
                            "(or MISTRAL_API_KEY); keys are made at https://console.mistral.ai")
    env_model = os.environ.get("BUILDMCP_MISTRAL_MODEL", "").strip()
    model = model or (env_model if env_model and not env_model.startswith("${") and kind != "code" else "") \
        or MISTRAL_MODELS["code" if kind == "code" else "text"]
    body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    t0 = time.time()
    try:
        r = net.client().post(MISTRAL_URL, json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    except Exception as e:  # noqa: BLE001
        raise DelegateError(f"Mistral API unreachable: {e}") from e
    if r.status_code == 401:
        raise DelegateError("Mistral refused the API key (401): check mistral_api_key")
    if r.status_code == 429:
        raise DelegateError("Mistral rate limit or quota reached (429): wait or use Gemini")
    if r.status_code >= 400:
        raise DelegateError(f"Mistral API: HTTP {r.status_code} {r.text[:300]}")
    d = r.json()
    try:
        answer = d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DelegateError(f"Mistral answered without a message: {str(d)[:300]}") from e
    if isinstance(answer, list):  # content chunks
        answer = "".join(c.get("text", "") for c in answer if isinstance(c, dict))
    usage = d.get("usage") or {}
    return {"answer": str(answer).strip(), "model": d.get("model", model), "tokens": int(usage.get("total_tokens") or 0),
            "seconds": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ the task
def build_prompt(task: str, files: list[Path]) -> str:
    """The task and its files. Passwords, tokens, keys and the forwarding secret in them are masked:
    nothing secret leaves this PC for Google or Mistral."""
    from .configs import mask_text

    parts = [task.strip()]
    total = 0
    for f in files:
        try:
            text = mask_text(f.read_text("utf-8", errors="replace"), f)
        except OSError as e:
            raise DelegateError(f"cannot read {f}: {e}") from e
        if len(text) > MAX_FILE:
            text = text[:MAX_FILE] + f"\n... ({len(text) - MAX_FILE} more characters cut)"
        total += len(text)
        if total > MAX_CONTEXT:
            raise DelegateError(f"the context files are bigger than {MAX_CONTEXT} characters: send fewer or parts")
        parts.append(f"--- FILE {f.name} ---\n{text}\n--- END {f.name} ---")
    return "\n\n".join(parts)


def _snapshot(d: Path) -> dict[str, tuple[str, str]]:
    out = {}
    for p in d.rglob("*"):
        if p.is_file() and not any(part in ("build", ".gradle", ".git") for part in p.relative_to(d).parts):
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if len(data) <= 512 * 1024:
                out[p.relative_to(d).as_posix()] = (hashlib.sha1(data).hexdigest(), data.decode("utf-8", "replace"))
    return out


def _usage_file() -> Path:
    from ..render.assets import data_dir

    return data_dir() / "delegate-usage.jsonl"


def log_usage(row: dict) -> None:
    try:
        with open(_usage_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def usage(days: int = 30) -> dict:
    rows = []
    try:
        for line in _usage_file().read_text("utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    since = time.time() - days * 86400
    rows = [r for r in rows if r.get("t", 0) >= since]
    by: dict = {}
    for r in rows:
        k = r.get("to", "?")
        b = by.setdefault(k, {"calls": 0, "failed": 0, "chars_in": 0, "chars_out": 0, "tokens": 0, "seconds": 0.0})
        b["calls"] += 1
        b["failed"] += 0 if r.get("ok") else 1
        for f in ("chars_in", "chars_out", "tokens"):
            b[f] += int(r.get(f) or 0)
        b["seconds"] = round(b["seconds"] + float(r.get("seconds") or 0), 1)
    return {"days": days, "by": by, "last": rows[-5:]}


def status() -> dict:
    g = gemini_path()
    return {"gemini": {"path": g, "version": gemini_version() if g else None,
                       "model": os.environ.get("BUILDMCP_GEMINI_MODEL", "").strip().lstrip("$") or "CLI default"},
            "mistral": {"key": bool(mistral_key()), "models": MISTRAL_MODELS},
            "rule": "building (spawns, structures) is never delegated"}


def run(task: str, to: str = "auto", kind: str = "text", files: list[str] | None = None, workdir: str = "",
        edit: bool = False, model: str = "", timeout: float = 300) -> dict:
    if not task.strip():
        raise DelegateError("empty task")
    if is_build_task(task):
        raise DelegateError("building stays with you, the assistant the owner works with (Claude or Codex): "
                            "spawns and structures, and how they look (palette, layout, terrain), are made with the "
                            "building tools (run_script, render, inspect), never by Gemini or Mistral. delegate is "
                            "for texts, configs, explanations and small code")
    to = to.lower().strip()
    if to == "auto":
        to = "gemini" if gemini_path() else ("mistral" if mistral_key() else "")
        if not to:
            raise DelegateError("no helper available: install the Gemini CLI or set a Mistral API key")
    if to not in ("gemini", "mistral"):
        raise DelegateError("to: gemini | mistral | auto")
    paths = [Path(f).expanduser() for f in files or []]
    cwd = Path(workdir).expanduser() if workdir else None
    if edit:
        if to != "gemini":
            raise DelegateError("edit=True works with Gemini only (Mistral just answers)")
        from .devplugin import projects_dir, _read_index

        allowed = [projects_dir().resolve()] + [Path(p).resolve() for p in _read_index().values()]
        if cwd is None or not any(cwd.resolve() == a or cwd.resolve().is_relative_to(a) for a in allowed):
            raise DelegateError("edit=True only inside a devplugin project folder (devplugin(action='list'))")
    prompt = build_prompt(task, paths)
    before = _snapshot(cwd) if (edit and cwd) else {}
    ok, res, err = False, {}, ""
    t0 = time.time()
    try:
        if to == "gemini":
            from ..render.assets import data_dir

            wd = cwd or (data_dir() / "delegate")
            wd.mkdir(parents=True, exist_ok=True)
            res = run_gemini(SYSTEM + "\n\n" + prompt, wd, model=model, edit=edit, timeout=timeout)
        else:
            res = run_mistral(prompt, kind=kind, model=model, timeout=timeout)
        ok = True
    except DelegateError as e:
        err = str(e)
        raise
    finally:
        log_usage({"t": time.time(), "to": to, "kind": kind, "model": res.get("model", model), "ok": ok,
                   "chars_in": len(prompt), "chars_out": len(res.get("answer", "")), "tokens": res.get("tokens", 0),
                   "seconds": round(time.time() - t0, 1), "edit": edit, "error": err[:200]})
    out = {"to": to, "model": res["model"], "seconds": res["seconds"], "tokens": res["tokens"], "answer": res["answer"],
           "check": "a weaker model wrote this: read it, compile / validate it, fix what is wrong before using it"}
    if edit and cwd:
        after = _snapshot(cwd)
        changed = sorted(k for k in set(before) | set(after) if before.get(k, ("",))[0] != after.get(k, ("",))[0])
        diff = []
        for k in changed:
            diff += list(difflib.unified_diff(before.get(k, ("", ""))[1].splitlines(),
                                              after.get(k, ("", ""))[1].splitlines(), f"a/{k}", f"b/{k}", lineterm="",
                                              n=2))
        out["changed_files"] = changed
        out["diff"] = diff[:400]
    return out
