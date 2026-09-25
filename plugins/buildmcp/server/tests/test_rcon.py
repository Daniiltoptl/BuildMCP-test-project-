"""RCON fallback: protocol, cuboid packing and a full paste into a fake server."""

import numpy as np
import pytest

from buildmcp.blocks.registry import parse_state
from buildmcp.gen import entities as E
from buildmcp.live.deploy import build_bundle, entity_tag_for
from buildmcp.live.placer import FILL_LIMIT, greedy_boxes, plan_commands, run_plan
from buildmcp.live.rcon import RconClient, RconError
from buildmcp.scene import Scene

from fake_rcon import FakeRcon


@pytest.fixture
def fake():
    f = FakeRcon()
    yield f
    f.close()


def test_protocol(fake):
    with pytest.raises(RconError, match="password"):
        RconClient("127.0.0.1", fake.port, "nope").connect()
    with RconClient("127.0.0.1", fake.port, "pw") as r:
        assert "Steve" in r.command("list")
        fake.run = lambda cmd: "x" * 9000  # long answers arrive in several packets
        assert len(r.command("anything")) == 9000
        with pytest.raises(RconError, match="too long"):
            r.command("say " + "a" * 2000)


def test_greedy_boxes_cover_exactly():
    rng = np.random.default_rng(3)
    vals = rng.integers(1, 4, size=(20, 12, 17)).astype(np.uint16)
    vals[rng.random(vals.shape) < 0.3] = 0
    vals[2:15, 0:6, 1:16] = 2  # a big uniform block
    include = vals != 0
    boxes = greedy_boxes(vals, include, 500)
    seen = np.zeros(vals.shape, dtype=int)
    for x1, y1, z1, x2, y2, z2, v in boxes:
        assert (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1) <= 500
        assert (vals[x1:x2 + 1, y1:y2 + 1, z1:z2 + 1] == v).all()
        seen[x1:x2 + 1, y1:y2 + 1, z1:z2 + 1] += 1
    assert (seen == include).all()
    assert len(boxes) < include.sum() / 2
    solid = np.full((40, 10, 40), 7, dtype=np.uint16)
    assert len(greedy_boxes(solid, solid != 0, FILL_LIMIT)) == 1
    assert len(greedy_boxes(solid, solid != 0, 4000)) == 5  # 2 layers of 40x40 per box


def _norm(state):
    name, props, _ = parse_state(state)
    return name, tuple(sorted(props.items()))


def _scene():
    S = Scene("1.21.5")
    S.fill((0, 0, 0, 40, 0, 40), "stone_bricks")  # 1681 blocks: several fills, one per 32768
    S.fill((0, 1, 0, 40, 2, 0), "oak_planks")
    S.set(3, 1, 3, "oak_stairs[facing=east]")
    S.set(4, 1, 3, "torch")
    S.set(6, 1, 6, "water")
    E.sign(S, (5, 1, 5), ["Line one", "Line two"], rotation=8)
    long = ["Очень длинная строка текста номер %d " % i * 3 for i in range(4)]
    E.sign(S, (7, 1, 5), long, rotation=0)  # NBT too long for one RCON packet
    E.hologram(S, (10.5, 3, 10.5), ["Длинный заголовок " * 12, "и ещё строка " * 10])
    E.hologram(S, (12.5, 3, 12.5), ["PvP"])
    S.set_biome((0, 0, 0, 15, 0, 40), "snowy_taiga")
    return S


def test_paste_over_rcon(fake):
    S = _scene()
    tag = entity_tag_for("rcon test")
    b, _, info = build_bundle(S, (1000, 64, -500), "1.21.5", entity_tag=tag, label="t")
    plan = plan_commands(b, "1.21.5", entity_tag=tag)
    assert plan.strict and all(c.endswith(" strict") for name, cs in plan.phases
                               if name in ("solid blocks", "attached blocks", "fluids") for c in cs)
    fills = [c for _, cs in plan.phases for c in cs if c.startswith("fill")]
    assert fills and all(len(c.encode()) <= 1446 for _, cs in plan.phases for c in cs)
    fake.entities.append({"id": "minecraft:text_display", "pos": (1005.5, 67, -495.5), "nbt": {}, "tags": [tag]})
    with RconClient("127.0.0.1", fake.port, "pw") as r:
        res = run_plan(r, plan)
    assert res["failures"] == 0, res["warnings"]
    assert fake.max_packet <= 1460 and not fake.loaded and fake.gamerules["logAdminCommands"] == "true"
    # blocks
    bb = S.bbox()
    for x in range(bb.x1, bb.x2 + 1):
        for y in range(bb.y1, bb.y2 + 1):
            for z in range(bb.z1, bb.z2 + 1):
                want = S.get(x, y, z)
                got = fake.world.get(x + 1000, y + 64, z - 500)
                assert _norm(got) == _norm(want), (x, y, z, got, want)
    # block entities (the long sign arrived in parts)
    for (x, y, z) in S.block_entities:
        got = fake.world.nbt(x + 1000, y + 64, z - 500)
        assert got is not None and "front_text" in got
    assert "номер 3" in str(fake.world.nbt(1007, 65, -495)["front_text"]["messages"][3])
    # entities: the old one was killed, both holograms exist with their full text and our tag only
    assert len(fake.entities) == 2
    assert all(e["tags"] == ["buildmcp", tag] for e in fake.entities)
    assert any("Длинный заголовок" in str(e["nbt"].get("text")) for e in fake.entities)
    # biomes
    assert "minecraft:snowy_taiga" in set(fake.biomes.values())


def test_paste_without_strict(fake):
    fake.strict = False
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 5, 0, 5), "grass_block")
    b, _, _ = build_bundle(S, (0, 70, 0), "1.21.4")
    plan = plan_commands(b, "1.21.4")
    assert not plan.strict
    with RconClient("127.0.0.1", fake.port, "pw") as r:
        res = run_plan(r, plan)
    assert res["failures"] == 0 and _norm(fake.world.get(3, 70, 3))[0] == "grass_block"


def test_hanging_columns_go_top_down():
    # without strict mode a stalactite placed before the block it hangs from falls (seen on Paper)
    S = Scene("1.21.4")
    S.fill((0, 5, 0, 4, 5, 4), "dripstone_block")
    for y in (1, 2, 3, 4):
        S.set(1, y, 1, "pointed_dripstone[vertical_direction=down]")
        S.set(3, y, 1, "pointed_dripstone[vertical_direction=down]")
        S.set(2, y, 3, "weeping_vines")
    S.set(0, 0, 0, "stone")
    S.set(0, 1, 0, "pointed_dripstone[vertical_direction=up]")  # stalagmites grow from the floor
    b, _, _ = build_bundle(S, (0, 70, 0), "1.21.4")
    plan = plan_commands(b, "1.21.4")
    names = [n for n, _ in plan.phases]
    assert names.index("solid blocks") < names.index("hanging blocks (top-down)")
    hang = dict(plan.phases)["hanging blocks (top-down)"]
    ys = [int(c.split()[2]) for c in hang]
    assert ys == sorted(ys, reverse=True) and len(set(ys)) == 4, hang
    assert all(c.split()[2] == c.split()[5] for c in hang if c.startswith("fill")), hang  # one layer per fill
    others = [c for n, cs in plan.phases if n != "hanging blocks (top-down)" for c in cs]
    assert not any("vertical_direction=down" in c or "weeping_vines" in c for c in others)
    assert any("vertical_direction=up" in c for c in dict(plan.phases)["attached blocks"])


def test_connector_over_rcon(fake, monkeypatch, tmp_path):
    from buildmcp.live import connector

    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path))
    monkeypatch.setenv("BUILDMCP_BRIDGE_TOKEN", "")
    monkeypatch.setenv("BUILDMCP_RCON_PORT", str(fake.port))
    monkeypatch.setenv("BUILDMCP_RCON_PASSWORD", "pw")
    monkeypatch.setenv("BUILDMCP_MC_VERSION", "auto")
    conn = connector.connect(fresh=True)
    try:
        assert conn.kind == "rcon" and conn.version() == "1.21.5"
        assert conn.status()["players_online"] == ["Steve"]
        p = conn.player()
        assert p["pos"] == [0.5, 64.0, 0.5] and p["world"] == "minecraft:overworld"
        conn.teleport("", (5, 70, 5), yaw=90, pitch=0)
        assert fake.player["pos"] == [5.0, 70.0, 5.0]
        with pytest.raises(connector.NotConnected, match="BuildBridge"):
            conn.need("undo")
    finally:
        connector.forget()
    assert FILL_LIMIT == 32768
