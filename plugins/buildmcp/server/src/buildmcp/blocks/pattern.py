"""Block patterns used by ``only=``, ``replace`` and scene queries.

Syntax (alternatives separated by ``|``):
  ``stone``                 exact block (any state)
  ``oak_stairs[half=top]``  block with property constraints
  ``*_log`` / ``*brick*``   glob on the block name
  ``#leaves``               tag (see TAGS)
  ``!pattern``              exclusion, e.g. ``#solid|!glass``
An empty/None pattern matches every non-air block.
"""

from __future__ import annotations

import fnmatch
import functools
from typing import Callable

from . import families as F
from .registry import BlockRegistry, parse_state

_LOG_SUFFIX = ("_log", "_wood", "_stem", "_hyphae")


def _tag(reg: BlockRegistry, tag: str) -> Callable[[str, dict], bool]:
    k = lambda n: F.kind_of(reg, n)  # noqa: E731
    info = reg.info
    tags: dict[str, Callable[[str, dict], bool]] = {
        "air": lambda n, p: k(n) == F.AIR,
        "liquid": lambda n, p: k(n) == F.LIQUID,
        "water": lambda n, p: n == "water",
        "solid": lambda n, p: k(n) in (F.FULL, F.LOG) and not n.endswith("_leaves"),
        "opaque": lambda n, p: k(n) in (F.FULL, F.LOG) and not info(n).transparent,
        "transparent": lambda n, p: info(n).transparent,
        "leaves": lambda n, p: k(n) == F.LEAVES,
        "logs": lambda n, p: n.endswith(_LOG_SUFFIX),
        "planks": lambda n, p: n.endswith("_planks"),
        "stairs": lambda n, p: k(n) == F.STAIRS,
        "slabs": lambda n, p: k(n) == F.SLAB,
        "walls": lambda n, p: k(n) == F.WALL,
        "fences": lambda n, p: k(n) == F.FENCE,
        "fence_gates": lambda n, p: k(n) == F.FENCE_GATE,
        "panes": lambda n, p: k(n) == F.PANE,
        "doors": lambda n, p: k(n) == F.DOOR,
        "trapdoors": lambda n, p: k(n) == F.TRAPDOOR,
        "plants": lambda n, p: k(n) in (F.PLANT, F.DOUBLE_PLANT),
        "flowers": lambda n, p: k(n) in (F.PLANT, F.DOUBLE_PLANT) and _is_flower(n),
        "carpets": lambda n, p: k(n) == F.CARPET,
        "glass": lambda n, p: "glass" in n,
        "wool": lambda n, p: n.endswith("_wool"),
        "concrete": lambda n, p: n.endswith("_concrete"),
        "terracotta": lambda n, p: n.endswith("terracotta"),
        "lights": lambda n, p: info(n).light > 0 or (n == "light"),
        "signs": lambda n, p: k(n) in (F.SIGN, F.WALL_SIGN, F.HANGING_SIGN),
        "banners": lambda n, p: k(n) in (F.BANNER, F.WALL_BANNER),
        "heads": lambda n, p: k(n) in (F.HEAD, F.WALL_HEAD),
        "gravity": lambda n, p: n in F.GRAVITY_BLOCKS or n.endswith("_concrete_powder"),
        "replaceable": lambda n, p: k(n) in (F.AIR, F.LIQUID, F.PLANT, F.DOUBLE_PLANT, F.VINE)
        or (n == "snow" and p.get("layers") == "1"),
        "non_air": lambda n, p: k(n) != F.AIR,
    }
    if tag not in tags:
        raise ValueError(f"Unknown tag '#{tag}'. Tags: " + ", ".join("#" + t for t in sorted(tags)))
    return tags[tag]


TAGS = (
    "air liquid water solid opaque transparent leaves logs planks stairs slabs walls fences fence_gates panes "
    "doors trapdoors plants flowers carpets glass wool concrete terracotta lights signs banners heads gravity "
    "replaceable non_air"
).split()

_FLOWER_WORDS = ("flower", "tulip", "orchid", "allium", "bluet", "daisy", "dandelion", "poppy", "lily",
                 "rose", "lilac", "peony", "petals", "torchflower", "pitcher", "eyeblossom", "cornflower")


def _is_flower(n: str) -> bool:
    return any(w in n for w in _FLOWER_WORDS)


def _single(reg: BlockRegistry, term: str) -> Callable[[str, dict], bool]:
    term = term.strip()
    if term.startswith("#"):
        return _tag(reg, term[1:].strip())
    name, props, _ = parse_state(term) if ("[" in term or ":" in term) else (term, {}, None)
    name = name.removeprefix("minecraft:")
    if any(ch in name for ch in "*?"):
        def glob_match(n: str, p: dict, _name=name, _props=props) -> bool:
            return fnmatch.fnmatchcase(n, _name) and all(p.get(a) == b for a, b in _props.items())
        return glob_match
    canonical_name = reg.info(name).name  # validates + resolves renames

    def exact(n: str, p: dict, _name=canonical_name, _props=props) -> bool:
        return n == _name and all(p.get(a) == b for a, b in _props.items())

    return exact


@functools.lru_cache(maxsize=512)
def _compile_cached(reg_id: int, pattern: str) -> Callable[[str], bool]:
    reg = _REGS[reg_id]
    terms = [t for t in pattern.split("|") if t.strip()]
    pos = [_single(reg, t) for t in terms if not t.strip().startswith("!")]
    neg = [_single(reg, t.strip()[1:]) for t in terms if t.strip().startswith("!")]

    def match(state: str) -> bool:
        n, p, _ = parse_state(state)
        if pos and not any(f(n, p) for f in pos):
            return False
        if not pos and n in ("air", "cave_air", "void_air"):
            return False
        return not any(f(n, p) for f in neg)

    return match


_REGS: dict[int, BlockRegistry] = {}


def compile_pattern(reg: BlockRegistry, pattern: str | list | tuple | None) -> Callable[[str], bool]:
    """Compile a pattern into ``match(state_string) -> bool``."""
    if pattern is None or pattern == "" or pattern == "*":
        return lambda s: not s.startswith("minecraft:air") and not s.startswith("minecraft:cave_air") \
            and not s.startswith("minecraft:void_air")
    if isinstance(pattern, (list, tuple, set)):
        pattern = "|".join(pattern)
    _REGS[id(reg)] = reg
    return _compile_cached(id(reg), pattern)
