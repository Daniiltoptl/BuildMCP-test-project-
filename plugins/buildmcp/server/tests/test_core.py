import numpy as np
import pytest

from buildmcp.analyze.lint import lint
from buildmcp.blocks import families as F
from buildmcp.blocks.finalize import finalize
from buildmcp.blocks.registry import BlockError, get_registry, resolve_version
from buildmcp.blocks.transforms import mirror_state, rotate_state
from buildmcp.geo.mask import Mask
from buildmcp.io.other_formats import read_structure, write_structure
from buildmcp.io.schem import read_schem, write_schem
from buildmcp.io.structure_data import from_scene, to_scene
from buildmcp.paint import palette as P
from buildmcp.scene import Scene

REG = get_registry("1.21.4")


def test_versions():
    assert resolve_version("1.21.7") == "1.21.7"
    assert resolve_version("1.21.x") == "1.21.11"
    assert get_registry("1.21.4").data_version == 4189
    assert get_registry("1.21.9").canonical("chain").startswith("minecraft:iron_chain")


def test_canonical_and_errors():
    assert REG.canonical("oak_stairs[facing=east]") == \
        "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]"
    with pytest.raises(BlockError, match="Did you mean"):
        REG.canonical("oak_stair")
    with pytest.raises(BlockError, match="allowed"):
        REG.canonical("oak_stairs[facing=up]")


def test_sturdy_faces():
    assert REG.face_sturdy("oak_stairs[facing=north,half=bottom]", "north")
    assert not REG.face_sturdy("oak_stairs[facing=north,half=bottom]", "south")
    assert REG.is_full_cube("glass")
    assert not REG.is_full_cube("oak_fence")


def test_families_and_kinds():
    fam = F.family(REG, "cracked_stone_bricks")
    assert fam.stairs == "stone_brick_stairs" and fam.wall == "stone_brick_wall"
    assert F.family(REG, "oak_log").fence == "oak_fence"
    assert F.kind_of(REG, "stone_brick_wall") == F.WALL
    assert F.kind_of(REG, "tall_grass") == F.DOUBLE_PLANT


@pytest.mark.parametrize("state", [
    "oak_stairs[facing=north,shape=inner_left]", "oak_log[axis=x]", "oak_sign[rotation=3]",
    "stone_brick_wall[north=tall,east=low]", "oak_door[facing=east,hinge=left]", "rail[shape=north_east]",
])
def test_transforms_roundtrip(state):
    s = REG.canonical(state)
    r = s
    for _ in range(4):
        r = rotate_state(r, 1)
    assert REG.canonical(r) == s
    assert REG.canonical(mirror_state(mirror_state(s, "x"), "x")) == s
    assert REG.canonical(mirror_state(mirror_state(s, "z"), "z")) == s


def test_mask_ops():
    a = Mask.box((0, 0, 0, 9, 9, 9))
    b = Mask.box((5, 5, 5, 14, 14, 14))
    assert (a | b).count == 1875 and (a & b).count == 125 and (a - b).count == 875
    s = Mask.from_function((-10, -10, -10, 10, 10, 10), lambda x, y, z: x * x + y * y + z * z <= 100)
    assert s.shell().count < s.count
    assert s.top().count > 0


def test_scene_basics_and_palettes():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 99, 4, 99), P.mix({"stone": 5, "andesite": 3, "cobblestone": 2}))
    top = dict(S.stats()["top"])
    assert abs(top["stone"] / 50000 - 0.5) < 0.02
    S.clear()
    S.fill((0, 0, 0, 99, 4, 99), P.patches({"stone": 5, "andesite": 3, "cobblestone": 2}, size=5))
    top = dict(S.stats()["top"])
    assert abs(top["cobblestone"] / 50000 - 0.2) < 0.05
    S.fill((10, 5, 10, 14, 9, 14), "stone_bricks", hollow=True)
    assert S.get(12, 7, 12) == "minecraft:air"
    assert S.get(10, 7, 12).startswith("minecraft:stone_bricks")
    g = P.gradient(["deepslate", "tuff", "stone"], axis="y", start=0, end=30, jitter=0)
    S.fill((50, 0, 50, 50, 29, 50), g)
    assert S.get(50, 0, 50).startswith("minecraft:deepslate") and S.get(50, 29, 50).startswith("minecraft:stone")


def test_copy_paste_rotate():
    S = Scene("1.21.4")
    S.set(0, 0, 0, "oak_stairs[facing=north]")
    S.set(1, 0, 0, "stone")
    clip = S.copy((0, 0, 0, 1, 0, 0))
    S.paste(clip, (10, 0, 10), rotate=1)
    # clockwise: east -> south, so the stone (east of the stairs) ends up south of them
    assert S.get(10, 0, 10).startswith("minecraft:oak_stairs[facing=east")
    assert S.get(10, 0, 11) == "minecraft:stone"


def test_snapshot_roundtrip():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 5, 5, 5), "stone")
    S.set(2, 6, 2, 'oak_sign[rotation=4]{front_text:{messages:[\'"hi"\',\'""\',\'""\',\'""\']}}')
    S.mark("spawn", (3, 6, 3), "spawn")
    S.add_entity("text_display", (3.5, 8, 3.5), {"text": '"x"'})
    S2 = Scene.from_bytes(S.to_bytes())
    assert np.array_equal(S2.data, S.data) and S2.nbt(2, 6, 2) is not None
    assert S2.markers["spawn"].kind == "spawn" and len(S2.entities) == 1


def test_finalize_rules():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 20, 0, 20), "grass_block")
    for x in range(2, 6):
        S.set(x, 1, 2, "oak_fence")
    for x in range(2, 6):
        S.set(x, 1, 5, "cobblestone_wall")
    S.set(3, 2, 5, "stone")
    S.set(8, 1, 8, "tall_grass")
    S.set(1, 5, 1, "stone")
    S.set(1, 4, 1, "lantern")
    S.set(10, 1, 10, "oak_leaves")
    finalize(S)
    assert "east=true" in S.get(2, 1, 2) and "west=true" in S.get(5, 1, 2)
    assert "east=tall" in S.get(3, 1, 5) and "up=false" in S.get(3, 1, 5)
    assert "up=true" in S.get(2, 1, 5)
    assert S.get(8, 2, 8).startswith("minecraft:tall_grass[half=upper")
    assert "hanging=true" in S.get(1, 4, 1)
    assert "persistent=true" in S.get(10, 1, 10)


def test_wall_under_fence_follows_its_arms():
    # seen on real Paper: a fence above a wall makes the wall sides under its arms tall
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 6, 0, 6), "stone")
    for z in range(1, 5):
        S.set(3, 1, z, "mossy_stone_brick_wall")
    S.set(2, 1, 2, "mossy_stone_brick_wall")
    S.set(4, 1, 2, "mossy_stone_brick_wall")
    for z in (1, 2, 3):
        S.set(3, 2, z, "oak_fence")
    finalize(S)
    w = S.get(3, 1, 2)
    assert "north=tall" in w and "south=tall" in w and "east=low" in w and "west=low" in w, w
    assert "up=false" in w, w  # north and south both tall: no post
    end = S.get(3, 1, 3)  # fence above has only a north arm
    assert "north=tall" in end and "south=low" in end, end


def test_grass_under_cover_turns_to_dirt():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 12, 0, 2), "grass_block")
    cover = ["stone", "oak_slab[type=bottom]", "oak_slab[type=top]", "oak_stairs[half=bottom]",
             "oak_stairs[half=top]", "snow[layers=1]", "snow[layers=3]", "glass", "oak_leaves", "water",
             "water[level=3]", "oak_fence[waterlogged=true]"]
    for x, st in enumerate(cover):
        S.set(x, 1, 1, st)
    finalize(S)
    got = {st: S.get(x, 0, 1).removeprefix("minecraft:").split("[")[0] for x, st in enumerate(cover)}
    assert got == {"stone": "dirt", "oak_slab[type=bottom]": "dirt", "oak_slab[type=top]": "grass_block",
                   "oak_stairs[half=bottom]": "dirt", "oak_stairs[half=top]": "grass_block",
                   "snow[layers=1]": "grass_block", "snow[layers=3]": "dirt", "glass": "grass_block",
                   "oak_leaves": "grass_block", "water": "dirt", "water[level=3]": "grass_block",
                   "oak_fence[waterlogged=true]": "dirt"}, got
    assert "snowy=true" in S.get(5, 0, 1)
    assert S.get(12, 0, 1).startswith("minecraft:grass_block")  # open sky


@pytest.mark.parametrize("version", [2, 3])
def test_schem_roundtrip(tmp_path, version):
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 15, 0, 15), P.patches(["grass_block", "moss_block", "coarse_dirt"], size=4))
    S.set(5, 1, 5, 'oak_sign[rotation=4]{front_text:{messages:[\'"hi"\',\'""\',\'""\',\'""\']}}')
    S.set_biome((0, 0, 0, 7, 0, 15), "cherry_grove")
    S.add_entity("text_display", (8.5, 3, 8.5), {"text": '"Hello"'})
    S.mark("spawn", (8, 1, 8), "spawn")
    sd = from_scene(S)
    p = write_schem(sd, tmp_path / "t.schem", version=version)
    r = read_schem(p)
    assert r.origin == (8, 1, 8) and r.data_version == 4189
    S2 = Scene("1.21.4")
    to_scene(r, S2)
    for x in range(16):
        for z in range(16):
            assert S2.get(x, 0, z) == S.get(x, 0, z)
    assert S2.nbt(5, 1, 5) is not None
    assert len(S2.entities) == 1 and S2.biome_at(1, 1) == "minecraft:cherry_grove"


def test_structure_nbt_roundtrip(tmp_path):
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 5, 3, 5), "stone_bricks", hollow=True)
    r = read_structure(write_structure(from_scene(S), tmp_path / "t.nbt"))
    S2 = Scene("1.21.4")
    to_scene(r, S2, at=(0, 0, 0))
    assert S2.stats()["top"] == S.stats()["top"]


def test_lint_finds_problems():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 30, 0, 30), "grass_block")
    S.fill((5, 1, 5, 20, 12, 5), "stone_bricks")
    S.set(25, 5, 25, "sand")
    kinds = {i.kind for i in lint(S)}
    assert {"unsupported_gravity", "flat_face"} <= kinds


def test_lint_stray_blocks_ignores_lily_pads_and_lights():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 12, 0, 12), "grass_block")
    S.fill((2, 0, 2, 6, 0, 6), "water")
    S.set(3, 1, 3, "lily_pad")
    S.set(9, 6, 9, "light[level=12]")
    assert "stray_blocks" not in {i.kind for i in lint(S)}
    S.set(10, 8, 2, "stone")  # a real leftover
    strays = [i for i in lint(S) if i.kind == "stray_blocks"]
    assert strays and strays[0].count == 1
