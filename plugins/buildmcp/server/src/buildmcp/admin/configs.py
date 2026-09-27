"""Read and change a server's config files without losing their comments: YAML (Paper, Bukkit and most
plugins) through a ruamel round trip, TOML (Velocity) through tomlkit, JSON and .properties.

Keys are addressed by paths: "proxies.velocity.enabled", "servers.lobby", "worlds[0].name",
'messages."no.permission"'. Every write keeps the previous file in .buildmcp/config-backups/<file>/
(the last 20), so diff and restore can undo it. Files outside the server folder are refused, and
values of keys that look like secrets (password, secret, token, key) are masked unless asked.
"""

from __future__ import annotations

import difflib
import io
import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from . import props
from .registry import ServerEntry

KINDS = {".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".json": "json", ".properties": "properties",
         ".conf": "text", ".txt": "text", ".secret": "text", ".cfg": "text", ".ini": "text"}
# folders that are not configuration: worlds, logs, libraries, caches, our own state
SKIP_DIRS = {"logs", "libraries", "libs", "cache", "versions", ".paper-remapped", ".buildmcp", "crash-reports",
             "bundler", "debug", "update", "backups", "backup", ".git", "web", "data", "storage", "lang",
             "translations", "locales", "playerdata", "players", "userdata", "users", "stats", "advancements",
             "region", "entities", "poi", "DIM-1", "DIM1", "schematics", "schems", "dumps", "heapdumps"}
MAX_LISTED = 400
SHORTCUTS = {
    "server": "server.properties", "properties": "server.properties", "server.properties": "server.properties",
    "paper": "config/paper-global.yml", "paper-global": "config/paper-global.yml",
    "paper-world": "config/paper-world-defaults.yml", "paper-world-defaults": "config/paper-world-defaults.yml",
    "spigot": "spigot.yml", "bukkit": "bukkit.yml", "commands": "commands.yml", "permissions": "permissions.yml",
    "purpur": "purpur.yml", "velocity": "velocity.toml", "pufferfish": "pufferfish.yml",
    "ops": "ops.json", "whitelist": "whitelist.json", "banned-players": "banned-players.json",
}
SECRET_KEY = re.compile(r"(?i)(pass(word|wd|phrase)?|secret|token|api[-_]?key|private[-_]?key|webhook-?url|"
                        r"client[-_]?secret|credentials?|jdbc-?url|connection-?string)$")
MASK = "***"
KEEP_BACKUPS = 20
MAX_BYTES = 4 * 1024 * 1024


class ConfigError(ValueError):
    pass


# ------------------------------------------------------------------ files
def _is_world(d: Path) -> bool:
    return (d / "level.dat").exists()


def resolve_file(entry: ServerEntry, file: str, must_exist: bool = True) -> Path:
    """A config file of the server by relative path, shortcut (paper-global, velocity, server...) or
    plugin name (LuckPerms -> plugins/LuckPerms/config.yml). Never outside the server folder."""
    root = entry.path.resolve()
    f = file.strip().replace("\\", "/")
    if not f:
        raise ConfigError("file is empty")
    cand = [SHORTCUTS.get(f.lower(), f)]
    if "/" not in f and "." not in f:  # a plugin name
        pdir = root / "plugins"
        if pdir.is_dir():
            match = next((d for d in pdir.iterdir() if d.is_dir() and d.name.lower() == f.lower()), None)
            if match:
                for name in ("config.yml", "config.yaml", "config.toml", "config.json", "config.conf",
                             "settings.yml", "settings.conf"):
                    if (match / name).exists():
                        cand.insert(0, f"plugins/{match.name}/{name}")
                        break
    for c in cand:
        p = (root / c).resolve()
        if not p.is_relative_to(root):
            raise ConfigError(f"{file}: outside the server folder")
        if p.suffix.lower() == ".jar":
            raise ConfigError(f"{file}: a jar is not a config")
        if p.exists() or not must_exist:
            if p.exists() and p.stat().st_size > MAX_BYTES:
                raise ConfigError(f"{file}: bigger than {MAX_BYTES // 1024 // 1024} MB, not a config")
            return p
    raise ConfigError(f"{file}: no such file in {entry.name} (config(action='files') lists them)")


def kind_of(p: Path) -> str:
    if p.name == "forwarding.secret":
        return "text"
    return KINDS.get(p.suffix.lower(), "text")


def rel(entry: ServerEntry, p: Path) -> str:
    return p.resolve().relative_to(entry.path.resolve()).as_posix()


def list_files(entry: ServerEntry, under: str = "") -> list[dict]:
    root = entry.path.resolve()
    base = (root / under).resolve() if under else root
    if not base.is_relative_to(root) or not base.is_dir():
        raise ConfigError(f"{under}: not a folder of the server")
    out = []

    def walk(d: Path, depth: int) -> None:
        try:
            items = sorted(d.iterdir(), key=lambda p: (p.is_dir(), p.name.lower()))
        except OSError:
            return
        for p in items:
            if p.is_dir():
                if p.name in SKIP_DIRS or p.name.startswith(".") or _is_world(p) or depth >= 4:
                    continue
                walk(p, depth + 1)
            elif p.suffix.lower() in KINDS or p.name == "forwarding.secret":
                if p.name in ("usercache.json", "version_history.json", "usernamecache.json", "help.yml") \
                        or p.stat().st_size > MAX_BYTES:
                    continue
                out.append({"file": rel(entry, p), "kind": kind_of(p), "kb": round(p.stat().st_size / 1024, 1),
                            "changed": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))})

    walk(base, 0)
    if len(out) > MAX_LISTED:
        out = out[:MAX_LISTED] + [{"file": f"... {len(out) - MAX_LISTED} more: pass under='plugins/<Name>'"}]
    return out


# ------------------------------------------------------------------ yaml / toml / json
def _guess_indent(text: str) -> tuple[int, int, int]:
    """(mapping indent, sequence indent, dash offset) the file uses: Paper writes lists flush with the
    key ("key:\\n- a"), many plugins indent them ("key:\\n  - a")."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    maps, seqs = Counter(), Counter()
    for prev, cur in zip(lines, lines[1:]):
        p = prev.strip()
        if not p.endswith(":") or p.startswith("- "):
            continue
        pi, ci = len(prev) - len(prev.lstrip(" ")), len(cur) - len(cur.lstrip(" "))
        c = cur.strip()
        if c == "-" or c.startswith("- "):
            if ci >= pi:
                seqs[ci - pi] += 1
        elif ci > pi:
            maps[ci - pi] += 1
    m = maps.most_common(1)[0][0] if maps else 2
    o = seqs.most_common(1)[0][0] if seqs else 0
    return m, max(o + 2, 2), o


def _yaml(text: str):
    from ruamel.yaml import YAML

    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    m, s, o = _guess_indent(text)
    y.indent(mapping=m, sequence=s, offset=o)
    return y


def load(p: Path) -> tuple[str, object, str]:
    """(kind, document, text). The document keeps comments for YAML and TOML."""
    kind = kind_of(p)
    text = p.read_text("utf-8-sig") if p.exists() else ""
    try:
        if kind == "yaml":
            doc = _yaml(text).load(text) if text.strip() else None
            if doc is None:
                from ruamel.yaml.comments import CommentedMap

                doc = CommentedMap()
        elif kind == "toml":
            import tomlkit

            doc = tomlkit.parse(text)
        elif kind == "json":
            doc = json.loads(text) if text.strip() else {}
        elif kind == "properties":
            doc = props.read(p) if p.exists() else {}
        else:
            doc = text
    except Exception as e:  # noqa: BLE001 - any parser error
        raise ConfigError(f"{p.name} does not parse as {kind}: {str(e)[:300]}") from e
    return kind, doc, text


def dumps(kind: str, doc, old_text: str) -> str:
    if kind == "yaml":
        buf = io.StringIO()
        _yaml(old_text).dump(doc, buf)
        return buf.getvalue()
    if kind == "toml":
        import tomlkit

        return tomlkit.dumps(doc)
    if kind == "json":
        m = re.search(r"\n([ \t]+)\S", old_text)
        indent = m.group(1) if m else 2
        return json.dumps(doc, indent=indent, ensure_ascii=False) + "\n"
    raise ConfigError(f"no structured writer for {kind}")


def validate(kind: str, text: str) -> None:
    try:
        if kind == "yaml":
            from ruamel.yaml import YAML

            YAML(typ="safe", pure=True).load(text)
        elif kind == "toml":
            import tomlkit

            tomlkit.parse(text)
        elif kind == "json":
            json.loads(text)
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"not valid {kind}: {str(e)[:300]}") from e


# ------------------------------------------------------------------ key paths
_SEG = re.compile(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'|([^.\[\]]+)|\[(-?\d+)\]')


def parse_path(path: str) -> list:
    """'a.b[0]."c.d"' -> ['a', 'b', 0, 'c.d']."""
    out: list = []
    s = path.strip()
    i = 0
    while i < len(s):
        if s[i] == ".":
            i += 1
            continue
        m = _SEG.match(s, i)
        if not m:
            raise ConfigError(f"bad key path '{path}' at {i}")
        dq, sq, bare, idx = m.groups()
        if idx is not None:
            out.append(int(idx))
        elif dq is not None:
            out.append(dq.replace('\\"', '"'))
        elif sq is not None:
            out.append(sq)
        else:
            out.append(bare.strip())
        i = m.end()
    if not out:
        raise ConfigError("empty key path")
    return out


def _is_map(x) -> bool:
    return hasattr(x, "keys") and hasattr(x, "__getitem__") and not isinstance(x, (str, bytes))


def _is_seq(x) -> bool:
    return isinstance(x, list)


def _key_in(m, k):
    """Keys in YAML may be ints or bools (1: x, true: y); match a path segment against them."""
    if k in m:
        return k
    for kk in m.keys():
        if str(kk) == str(k):
            return kk
    return None


def get_value(doc, path: list):
    cur = doc
    for i, k in enumerate(path):
        if _is_map(cur):
            kk = _key_in(cur, k)
            if kk is None:
                raise KeyError(_fmt_path(path[:i + 1]))
            cur = cur[kk]
        elif _is_seq(cur) and isinstance(k, int):
            if not -len(cur) <= k < len(cur):
                raise KeyError(_fmt_path(path[:i + 1]))
            cur = cur[k]
        else:
            raise KeyError(_fmt_path(path[:i + 1]))
    return cur


def _new_map(doc):
    try:
        from ruamel.yaml.comments import CommentedMap

        if isinstance(doc, CommentedMap):
            return CommentedMap()
    except ImportError:  # pragma: no cover
        pass
    if type(doc).__module__.startswith("tomlkit"):
        import tomlkit

        return tomlkit.table()
    return {}


def set_value(doc, path: list, value) -> object:
    """Set (creating missing mappings). Returns the old value or None."""
    cur = doc
    for k in path[:-1]:
        if _is_map(cur):
            kk = _key_in(cur, k)
            if kk is None:
                cur[k] = _new_map(doc)
                kk = k
            cur = cur[kk]
        elif _is_seq(cur) and isinstance(k, int) and -len(cur) <= k < len(cur):
            cur = cur[k]
        else:
            raise ConfigError(f"cannot go into {k!r}: the value there is {type(cur).__name__}")
    last = path[-1]
    if _is_map(cur):
        kk = _key_in(cur, last)
        old = cur[kk] if kk is not None else None
        cur[kk if kk is not None else last] = value
        return old
    if _is_seq(cur) and isinstance(last, int):
        if last == len(cur):
            cur.append(value)
            return None
        if -len(cur) <= last < len(cur):
            old = cur[last]
            cur[last] = value
            return old
    raise ConfigError(f"cannot set {_fmt_path(path)}")


def unset_value(doc, path: list) -> object:
    parent = get_value(doc, path[:-1]) if len(path) > 1 else doc
    last = path[-1]
    if _is_map(parent):
        kk = _key_in(parent, last)
        if kk is None:
            raise KeyError(_fmt_path(path))
        old = parent[kk]
        del parent[kk]
        return old
    if _is_seq(parent) and isinstance(last, int):
        return parent.pop(last)
    raise KeyError(_fmt_path(path))


def _fmt_path(path: list) -> str:
    out = ""
    for k in path:
        if isinstance(k, int):
            out += f"[{k}]"
        else:
            s = str(k)
            s = f'"{s}"' if ("." in s or "[" in s or " " in s) else s
            out += ("." if out else "") + s
    return out


def plain(x):
    """ruamel / tomlkit values -> plain JSON-able Python."""
    if _is_map(x):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if hasattr(x, "unwrap"):
        try:
            return plain(x.unwrap())
        except Exception:  # noqa: BLE001
            pass
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return float(x)
    return str(x) if not isinstance(x, str) else str(x)


def flatten(x, prefix: list | None = None, out: list | None = None, depth: int = 0) -> list[tuple[list, object]]:
    prefix = prefix or []
    out = [] if out is None else out
    if _is_map(x) and depth < 12:
        if not x and prefix:
            out.append((prefix, {}))
        for k, v in x.items():
            flatten(v, prefix + [k], out, depth + 1)
    elif isinstance(x, list) and x and all(_is_map(v) for v in x) and depth < 12:
        for i, v in enumerate(x):
            flatten(v, prefix + [i], out, depth + 1)
    else:
        out.append((prefix, x))
    return out


def is_secret_key(path: list) -> bool:
    last = next((str(k) for k in reversed(path) if not isinstance(k, int)), "")
    return bool(SECRET_KEY.search(last.replace("_", "-")))


def mask(path: list, value):
    if is_secret_key(path) and isinstance(value, str) and value not in ("", "''", '""'):
        return MASK
    if _is_map(value):
        return {k: mask(path + [k], v) for k, v in value.items()}
    return value


_LINE_SECRET = re.compile(r"""^(\s*["']?[\w.\-]*?(?:pass(?:word|wd)?|secret|token|api[-_]?key|private[-_]?key|"""
                          r"""webhook-?url|client[-_]?secret|credentials?)["']?\s*[:=]\s*)(\S.*)$""", re.I)


def mask_text(text: str, p: Path | None = None) -> str:
    if p is not None and p.name == "forwarding.secret":
        return MASK + "\n" if text.strip() else text
    out = []
    for line in text.splitlines(keepends=True):
        m = _LINE_SECRET.match(line.rstrip("\r\n"))
        if m and m.group(2).strip() not in ("''", '""', "", "null", "~") and not m.group(2).lstrip().startswith("#"):
            nl = line[len(line.rstrip("\r\n")):]
            line = m.group(1) + "'" + MASK + "'" + nl
        out.append(line)
    return "".join(out)


# ------------------------------------------------------------------ backups
def _backup_root(entry: ServerEntry, p: Path) -> Path:
    return entry.state_dir() / "config-backups" / rel(entry, p)


def backup(entry: ServerEntry, p: Path) -> Path | None:
    if not p.exists():
        return None
    d = _backup_root(entry, p)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest, i = d / stamp, 1
    while dest.exists():
        i += 1
        dest = d / f"{stamp}-{i}"
    shutil.copy2(p, dest)
    olds = sorted(d.iterdir(), key=lambda x: x.name)
    for old in olds[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return dest


def backups(entry: ServerEntry, file: str) -> list[dict]:
    p = resolve_file(entry, file, must_exist=False)
    d = _backup_root(entry, p)
    if not d.is_dir():
        return []
    return [{"backup": b.name, "kb": round(b.stat().st_size / 1024, 1)} for b in sorted(d.iterdir(), reverse=True)]


def _write(entry: ServerEntry, p: Path, text: str) -> str | None:
    """Back up and write; returns the backup name."""
    b = backup(entry, p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".buildmcp-tmp")
    tmp.write_text(text, "utf-8", newline="")
    tmp.replace(p)
    return b.name if b else None


# ------------------------------------------------------------------ actions
def read(entry: ServerEntry, file: str, path: str = "", reveal: bool = False, max_chars: int = 30000) -> dict:
    p = resolve_file(entry, file)
    kind, doc, text = load(p)
    out: dict = {"file": rel(entry, p), "kind": kind}
    if path:
        if kind == "text":
            raise ConfigError(f"{out['file']} is plain text: read it without path")
        keys = [path.strip()] if kind == "properties" else parse_path(path)
        try:
            v = plain(get_value(doc, keys))
        except KeyError as e:
            raise ConfigError(f"{out['file']}: no key {e.args[0]}") from None
        out["path"] = path.strip() if kind == "properties" else _fmt_path(keys)
        out["value"] = v if reveal else mask(keys, v)
        return out
    shown = text if reveal else mask_text(text, p)
    if len(shown) > max_chars:
        out["truncated"] = f"showing {max_chars} of {len(shown)} characters: use path=, action='find' or 'outline'"
        shown = shown[:max_chars]
    out["text"] = shown
    return out


def outline(entry: ServerEntry, file: str, depth: int = 2, reveal: bool = False) -> dict:
    """The key tree down to ``depth`` with short values: a map of a big config."""
    p = resolve_file(entry, file)
    kind, doc, _ = load(p)
    if kind == "text":
        raise ConfigError(f"{rel(entry, p)} is plain text")
    lines: list[str] = []

    def walk(x, pre: list, d: int) -> None:
        if not _is_map(x):
            return
        for k, v in x.items():
            path = pre + [k]
            name = str(k) if kind == "properties" else _fmt_path(path)
            if _is_map(v):
                if d + 1 >= depth:
                    lines.append(f"{name}: {{{len(v)} keys}}")
                else:
                    walk(v, path, d + 1)
            else:
                val = plain(v)
                val = val if reveal else mask(path, val)
                s = json.dumps(val, ensure_ascii=False, default=str)
                lines.append(f"{name} = {s[:80] + '…' if len(s) > 80 else s}")
            if len(lines) > 600:
                return

    walk(doc, [], 0)
    return {"file": rel(entry, p), "kind": kind, "keys": lines}


def find(entry: ServerEntry, pattern: str, files: list[str] | None = None, limit: int = 60,
         reveal: bool = False) -> dict:
    """Keys or values matching a regex across the server's configs (or the given files)."""
    rx = re.compile(pattern, re.I)
    targets = [resolve_file(entry, f) for f in files] if files else [entry.path / f["file"] for f in list_files(entry)]
    hits, errors = [], {}
    for p in targets:
        try:
            kind, doc, text = load(p)
        except ConfigError as e:
            errors[rel(entry, p)] = str(e)[:160]
            continue
        if kind == "text":
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append({"file": rel(entry, p), "line": i,
                                 "text": (line if reveal else mask_text(line, p)).strip()[:200]})
            continue
        for path, v in flatten(doc):
            ps = str(path[0]) if kind == "properties" else _fmt_path(path)
            val = plain(v)
            if rx.search(ps) or (not _is_map(val) and not isinstance(val, list) and rx.search(str(val))):
                shown = val if reveal else mask(path, val)
                hits.append({"file": rel(entry, p), "path": ps, "value": shown})
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    out: dict = {"pattern": pattern, "hits": hits[:limit]}
    if len(hits) >= limit:
        out["more"] = f"stopped at {limit}: narrow the pattern or pass files"
    if errors:
        out["unreadable"] = errors
    return out


def apply(entry: ServerEntry, file: str, changes: dict | None = None, unset: list[str] | None = None,
          create: bool = False) -> dict:
    """Set values by key path (and remove keys), keeping comments. Returns what changed."""
    p = resolve_file(entry, file, must_exist=not create)
    kind, doc, text = load(p)
    if kind == "text":
        raise ConfigError(f"{rel(entry, p)} is plain text: use action='write'")
    changed = []
    if kind == "properties":
        vals = dict(changes or {})
        gone = [k for k in unset or [] if k in doc]
        if not gone and all(doc.get(k) == props.fmt(v) for k, v in vals.items()):
            return {"file": rel(entry, p), "changed": [], "note": "already so: nothing written"}
        b = backup(entry, p)
        for k, old, new in props.update(p, vals, remove=gone):
            changed.append({"path": k, "old": mask([k], old), "new": mask([k], new) if new is not None
                            else "(removed)"})
        return {"file": rel(entry, p), "changed": changed, "backup": b.name if b else None}
    for key, value in (changes or {}).items():
        keys = parse_path(key)
        try:
            old = plain(get_value(doc, keys))
        except KeyError:
            old = None
        if old == value and old is not None:
            continue
        set_value(doc, keys, value)
        changed.append({"path": _fmt_path(keys), "old": mask(keys, old), "new": mask(keys, value)})
    for key in unset or []:
        keys = parse_path(key)
        try:
            old = plain(unset_value(doc, keys))
            changed.append({"path": _fmt_path(keys), "old": mask(keys, old), "new": "(removed)"})
        except KeyError:
            pass
    if not changed:
        return {"file": rel(entry, p), "changed": [], "note": "already so: nothing written"}
    new_text = dumps(kind, doc, text)
    validate(kind, new_text)
    b = _write(entry, p, new_text)
    return {"file": rel(entry, p), "changed": changed, "backup": b}


def write_text(entry: ServerEntry, file: str, text: str) -> dict:
    """Replace a whole file (or create one), after checking it parses."""
    p = resolve_file(entry, file, must_exist=False)
    kind = kind_of(p)
    validate(kind, text)
    old = p.read_text("utf-8-sig") if p.exists() else ""
    if old == text:
        return {"file": rel(entry, p), "note": "same content: nothing written"}
    b = _write(entry, p, text)
    d = list(difflib.unified_diff(old.splitlines(), text.splitlines(), lineterm="", n=1))
    return {"file": rel(entry, p), "written": len(text), "backup": b, "diff_lines": len(d),
            "diff": [mask_text(x) for x in d[:80]]}


def diff(entry: ServerEntry, file: str, backup_name: str = "", reveal: bool = False) -> dict:
    p = resolve_file(entry, file)
    d = _backup_root(entry, p)
    bs = sorted(d.iterdir(), reverse=True) if d.is_dir() else []
    if not bs:
        return {"file": rel(entry, p), "diff": [], "note": "no backups of this file yet"}
    b = next((x for x in bs if x.name == backup_name), None) if backup_name else bs[0]
    if b is None:
        raise ConfigError(f"no backup {backup_name} (have: {', '.join(x.name for x in bs[:10])})")
    old, new = b.read_text("utf-8-sig", errors="replace"), p.read_text("utf-8-sig", errors="replace")
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"backup {b.name}", "now", lineterm="",
                                      n=2))
    if not reveal:
        lines = [mask_text(x, p) for x in lines]
    return {"file": rel(entry, p), "against": b.name, "diff": lines[:400]}


def restore(entry: ServerEntry, file: str, backup_name: str = "") -> dict:
    p = resolve_file(entry, file, must_exist=False)
    d = _backup_root(entry, p)
    bs = sorted(d.iterdir(), reverse=True) if d.is_dir() else []
    b = next((x for x in bs if x.name == backup_name), None) if backup_name else (bs[0] if bs else None)
    if b is None:
        raise ConfigError(f"no backup to restore for {rel(entry, p)}")
    text = b.read_text("utf-8-sig", errors="replace")
    cur = _write(entry, p, text)
    return {"file": rel(entry, p), "restored": b.name, "previous_saved_as": cur}
