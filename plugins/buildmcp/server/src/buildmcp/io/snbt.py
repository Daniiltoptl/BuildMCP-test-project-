"""A forgiving SNBT reader for what servers print (``/data get``), in every 1.21+ flavour.

nbtlib reads the classic syntax. Minecraft 1.21.5+ also prints escapes such as ``\\n`` in strings
(multi-line text components), ``true``/``false`` and lists whose elements have different types
(``["", {text: "a"}]``). Those lists are stored the way the game stores them in binary NBT: every
element that is not a compound is wrapped as ``{"": element}``.
"""

from __future__ import annotations

import re

import nbtlib

__all__ = ["parse_snbt", "SnbtError"]


class SnbtError(ValueError):
    pass


_UNQUOTED = re.compile(r"[0-9A-Za-z_\-.+]+")
_NUMBER = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([bBsSlLfFdD]?)$")
_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "s": " "}
_INT_TYPES = {"b": nbtlib.Byte, "s": nbtlib.Short, "l": nbtlib.Long}
_ARRAYS = {"B": nbtlib.ByteArray, "I": nbtlib.IntArray, "L": nbtlib.LongArray}


def parse_snbt(text: str):
    """Parse SNBT into nbtlib tags. Tries nbtlib first, then this parser."""
    try:
        return nbtlib.parse_nbt(text)
    except Exception:  # noqa: BLE001 - newer syntax, fall through
        pass
    p = _Parser(text)
    value = p.value()
    p.ws()
    if p.i != len(p.s):
        raise SnbtError(f"unexpected {p.s[p.i:p.i + 20]!r} at {p.i}")
    return value


class _Parser:
    def __init__(self, s: str):
        self.s, self.i = s, 0

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            raise SnbtError(f"expected {ch!r} at {self.i}, got {self.s[self.i:self.i + 20]!r}")
        self.i += 1

    def value(self):
        c = self.peek()
        if c == "{":
            return self.compound()
        if c == "[":
            return self.list_or_array()
        if c in "\"'":
            return nbtlib.String(self.quoted())
        return self.scalar(self.word())

    def word(self) -> str:
        self.ws()
        m = _UNQUOTED.match(self.s, self.i)
        if not m:
            raise SnbtError(f"unexpected {self.s[self.i:self.i + 20]!r} at {self.i}")
        self.i = m.end()
        return m.group(0)

    def key(self) -> str:
        return self.quoted() if self.peek() in "\"'" else self.word()

    def quoted(self) -> str:
        q = self.s[self.i]
        self.i += 1
        out = []
        while True:
            if self.i >= len(self.s):
                raise SnbtError("unterminated string")
            ch = self.s[self.i]
            if ch == q:
                self.i += 1
                return "".join(out)
            if ch != "\\":
                out.append(ch)
                self.i += 1
                continue
            e = self.s[self.i + 1:self.i + 2]
            if e in _ESCAPES:
                out.append(_ESCAPES[e])
                self.i += 2
            elif e in ("x", "u", "U"):
                n = {"x": 2, "u": 4, "U": 8}[e]
                out.append(chr(int(self.s[self.i + 2:self.i + 2 + n], 16)))
                self.i += 2 + n
            elif e == "N" and self.s[self.i + 2:self.i + 3] == "{":
                end = self.s.index("}", self.i)
                import unicodedata

                out.append(unicodedata.lookup(self.s[self.i + 3:end]))
                self.i = end + 1
            else:
                raise SnbtError(f"bad escape \\{e} at {self.i}")

    def scalar(self, w: str):
        lw = w.lower()
        if lw == "true":
            return nbtlib.Byte(1)
        if lw == "false":
            return nbtlib.Byte(0)
        m = _NUMBER.match(w)
        if m:
            num, suf = m.group(1), m.group(2).lower()
            try:
                if suf in _INT_TYPES:
                    return _INT_TYPES[suf](int(num))
                if suf == "f":
                    return nbtlib.Float(float(num))
                if suf == "d" or any(ch in num for ch in ".eE"):
                    return nbtlib.Double(float(num))
                v = int(num)
                if -2 ** 31 <= v < 2 ** 31:
                    return nbtlib.Int(v)
            except (ValueError, OverflowError):
                pass
        return nbtlib.String(w)

    def compound(self):
        self.expect("{")
        out = nbtlib.Compound()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            k = self.key()
            self.expect(":")
            out[k] = self.value()
            c = self.peek()
            self.i += 1
            if c == "}":
                return out
            if c != ",":
                raise SnbtError(f"expected ',' or '}}' at {self.i - 1}")

    def list_or_array(self):
        self.expect("[")
        m = re.match(r"\s*([BIL])\s*;", self.s[self.i:])
        if m:
            self.i += m.end()
            items = []
            if self.peek() != "]":
                while True:
                    items.append(int(re.sub(r"[bBsSlL]$", "", self.word())))
                    c = self.peek()
                    self.i += 1
                    if c == "]":
                        break
                    if c != ",":
                        raise SnbtError(f"expected ',' or ']' at {self.i - 1}")
            else:
                self.i += 1
            return _ARRAYS[m.group(1)](items)
        items = []
        if self.peek() == "]":
            self.i += 1
            return nbtlib.List([])
        while True:
            items.append(self.value())
            c = self.peek()
            self.i += 1
            if c == "]":
                break
            if c != ",":
                raise SnbtError(f"expected ',' or ']' at {self.i - 1}")
        kinds = {nbtlib.List if isinstance(v, nbtlib.List) else type(v) for v in items}
        if len(kinds) > 1:  # heterogeneous: wrap like the game's binary format
            items = [v if isinstance(v, nbtlib.Compound) else nbtlib.Compound({"": v}) for v in items]
            return nbtlib.List[nbtlib.Compound](items)
        return nbtlib.List[kinds.pop()](items)
