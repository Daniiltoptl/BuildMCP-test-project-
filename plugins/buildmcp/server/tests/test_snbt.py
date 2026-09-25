"""SNBT as servers print it: the classic syntax and the 1.21.5+ additions."""

import nbtlib
import numpy as np
import pytest

from buildmcp.io.snbt import SnbtError, parse_snbt
from buildmcp.live.bundle import Bundle


def test_classic_syntax_is_unchanged():
    s = '{id: "minecraft:chest", Items: [{Slot: 0b, count: 1, id: "minecraft:apple"}], x: 1, big: 5L, f: 0.5f}'
    assert parse_snbt(s) == nbtlib.parse_nbt(s)


def test_newer_syntax():
    # a text_display read back from 1.21.8: multi-line text with an escaped newline and a mixed list
    s = ('{Tags: ["buildmcp", "buildmcp.e2e"], billboard: "center", see_through: false, '
         'text: {extra: [{color: "gold", text: "Добро пожаловать"}, "\\n", {text: "на сервер"}], text: ""}, '
         'UUID: [I; 1, -2, 3, 4], Rotation: [0.0f, 0.0f]}')
    with pytest.raises(Exception):
        nbtlib.parse_nbt(s)
    t = parse_snbt(s)
    assert [str(v) for v in t["Tags"]] == ["buildmcp", "buildmcp.e2e"]
    assert t["see_through"] == nbtlib.Byte(0)
    extra = t["text"]["extra"]
    assert extra[1] == nbtlib.Compound({"": nbtlib.String("\n")})  # wrapped like the game's binary NBT
    assert str(extra[0]["text"]) == "Добро пожаловать"
    assert t["UUID"] == nbtlib.IntArray([1, -2, 3, 4])
    assert nbtlib.serialize_tag(t)  # writable again


def test_escapes_and_numbers():
    t = parse_snbt("{a: 'it\\'s', b: \"tab\\there\", c: \"\\u00e9\\x41\", d: 1.5e2, e: -3s, g: true, h: [L; 1L, 2L]}")
    assert str(t["a"]) == "it's" and str(t["b"]) == "tab\there" and str(t["c"]) == "éA"
    assert t["d"] == nbtlib.Double(150.0) and t["e"] == nbtlib.Short(-3) and t["g"] == nbtlib.Byte(1)
    assert t["h"] == nbtlib.LongArray([1, 2])
    with pytest.raises(SnbtError):
        parse_snbt("{a: \"\\q\"}")


def test_bundle_keeps_entity_tags_from_new_servers():
    cells = np.zeros((1, 1, 1), dtype=np.uint16)
    snbt = '{Tags: ["buildmcp", "buildmcp.x"], text: ["", "\\n"], UUID: [I; 1, 2, 3, 4], Pos: [0.5d, 0.0d, 0.5d]}'
    b = Bundle(palette=[""], cells=cells, min=(0, 0, 0), entities=[(0.5, 0.0, 0.5, "minecraft:text_display", snbt)])
    (eid, pos, nbt), = b.to_structure().entities
    assert eid == "minecraft:text_display" and "buildmcp.x" in [str(v) for v in nbt["Tags"]]
    assert "UUID" not in nbt and "Pos" not in nbt
