""".properties files (server.properties): read, and update in place keeping comments and the order.

Java escapes are understood when reading (``minecraft\\:flat``, ``\\u00e9``); written values escape
only what Java needs (backslashes, line breaks and a leading space), which the server reads back
unchanged and re-saves in its own style on the next start.
"""

from __future__ import annotations

import re
from pathlib import Path

_SEP = re.compile(r"(?<!\\)[=:]|(?<!\\)\s")


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", s[i + 2:i + 6]):
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _escape_value(v: str) -> str:
    v = v.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return "\\" + v if v.startswith(" ") else v


def _split(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s[0] in "#!":
        return None
    m = _SEP.search(s)
    if not m:
        return _unescape(s), ""
    key = s[:m.start()]
    rest = s[m.end():].lstrip()
    if m.group(0).isspace() and rest[:1] in ("=", ":"):
        rest = rest[1:].lstrip()
    return _unescape(key), _unescape(rest)


def read(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = Path(path).read_text("utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        kv = _split(line)
        if kv:
            out[kv[0]] = kv[1]
    return out


def update(path: Path, changes: dict) -> list[tuple[str, str | None, str]]:
    """Set keys (values are converted with str(); True/False become true/false). Existing lines are
    rewritten in place, new keys are appended. Returns [(key, old, new)] for the keys that changed."""
    path = Path(path)
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    want = {k: (("true" if v else "false") if isinstance(v, bool) else str(v)) for k, v in changes.items()}
    done: dict[str, str | None] = {}
    report = []
    for i, line in enumerate(lines):
        kv = _split(line)
        if kv and kv[0] in want and kv[0] not in done:
            k, old = kv
            done[k] = old
            if old != want[k]:
                lines[i] = f"{k}={_escape_value(want[k])}"
                report.append((k, old, want[k]))
    for k, v in want.items():
        if k not in done:
            lines.append(f"{k}={_escape_value(v)}")
            report.append((k, None, v))
    if report or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", "utf-8")
    return report
