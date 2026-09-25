import numpy as np
import pytest

from buildmcp import themes
from buildmcp.blocks.finalize import finalize
from buildmcp.blocks.registry import get_registry
from buildmcp.analyze.lint import lint
from buildmcp.gen import arch, entities as E, paths, props, rocks, terrain, text, trees
from buildmcp.geo import sdf, shapes
from buildmcp.paint import palette as P
from buildmcp.scene import Scene


@pytest.mark.parametrize("version", ["1.21", "1.21.4", "1.21.11"])
def test_themes_valid_blocks(version):
    reg = get_registry(version)
    for name in themes.names():
        for st in themes.get(name).states():
            reg.canonical(st)


def test_sdf_shapes():
    assert sdf.sphere((0.5, 0.5, 0.5), 5).mask().count > 400
    rock = sdf.ellipsoid((0, 0, 0), (6, 4, 5)).displace(1.2, scale=4, seed=1).mask()
    assert rock.count > 200
    assert sdf.lathe((0, 0, 0), [(4, 0), (2, 6), (0.5, 10)]).mask().count > 50
    assert shapes.circle((0, 64, 0), 6).count > 90
    assert len(shapes.catmull_rom([(0, 0, 0), (10, 0, 5), (20, 0, 0)])) > 10


@pytest.mark.parametrize("theme", ["fantasy_medieval", "asian_sakura", "dark_infernal", "winter_north"])
def test_island_and_cover(theme):
    S = Scene("1.21.4")
    isl = terrain.island(S, (0, 80, 0), 18, theme=theme, seed=2)
    assert isl.body.count > 3000
    assert isl.height_at(0, 0) is not None
    n = terrain.cover(S, isl.surface, theme, density=0.3, seed=1)
    assert n > 20
    finalize(S)
    errors = [i for i in lint(S) if i.severity == "error"]
    assert not errors, errors


@pytest.mark.parametrize("kind", trees.KINDS)
def test_tree_kinds(kind):
    S = Scene("1.21.4")
    S.fill((-20, 0, -20, 20, 0, 20), "grass_block")
    res = trees.tree(S, (0, 0, 0), kind, seed=1)
    assert res.wood.count > 0
    assert S.count("#non_air") > 441 + 10


def test_architecture_pieces():
    S = Scene("1.21.4")
    S.fill((-30, 0, -30, 60, 0, 30), "grass_block")
    arch.house(S, (0, 1, 0, 10, 7, 8), theme="fantasy_medieval")
    arch.house(S, (20, 1, 0, 30, 6, 8), theme="winter_north", roof_style="nordic")
    arch.tower(S, (-15, 1, -15), 4, 16, roof="cone")
    arch.tower(S, (45, 1, -15), 4, 14, shape="octagon", roof="battlements", theme="dark_infernal")
    arch.pagoda(S, (40, 1, 15), tiers=2, base=9)
    arch.torii(S, (-15, 0, 15), "south")
    arch.arch(S, (0, 1, 20), 5, 7)
    finalize(S)
    assert S.count("#stairs") > 100
    assert S.count("#doors") >= 4


def test_paths_props_text_entities():
    S = Scene("1.21.4")
    S.fill((-30, 0, -30, 60, 0, 30), "grass_block")
    paths.path(S, [(-20, 0, 0), (0, 0, 5), (20, 0, 0)], width=4)
    paths.plaza(S, (30, 0, 10), 6)
    props.lamp_post(S, (0, 0, -10))
    props.fountain(S, (30, 0, -15), 4)
    props.portal_frame(S, (45, 0, 20), "south", label=E.component("PvP", "red"))
    rocks.boulder(S, (-10, 0, -10), 3)
    rocks.crystal_cluster(S, (-20, 0, -20), 6)
    t = text.text3d(S, "SPAWN", (0, 5, 25), facing="south", outline="black_concrete")
    assert t["face"].count > 50
    E.hologram(S, (0.5, 3, 0.5), ["Hello"])
    E.block_display(S, (5, 3, 5), "stone", scale=2)
    E.sign(S, (10, 1, 10), ["a", "b"])
    E.head(S, (12, 1, 10), texture="e3RleHR1cmVzOnt9fQ==")
    finalize(S)
    assert len(S.entities) >= 3
    assert S.nbt(12, 1, 10) is not None
