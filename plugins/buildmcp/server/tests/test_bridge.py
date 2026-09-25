"""BuildBridge end to end: the real plugin code runs in the fake Paper server (bridge/testkit),
BuildMCP talks to it over HTTP like it would to a real server."""

import numpy as np
import pytest

from buildmcp.blocks.registry import parse_state
from buildmcp.gen import entities as E
from buildmcp.live.bridge import BridgeClient, BridgeError
from buildmcp.live.bundle import BIOME_KEEP, SKIP, Bundle
from buildmcp.live.deploy import build_bundle, entity_tag_for
from buildmcp.scene import Scene



def _norm(state: str) -> tuple:
    name, props, _ = parse_state(state)
    return name, tuple(sorted(props.items()))


def test_bundle_roundtrip():
    cells = np.zeros((5, 4, 3), dtype=np.uint16)
    cells[1, 2, 0] = 1
    cells[4, 3, 2] = 2
    bio = np.full((5, 3), BIOME_KEEP, dtype=np.uint8)
    bio[0, 1] = 0
    b = Bundle(palette=[SKIP, "minecraft:stone", "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]"],
               cells=cells, min=(10, -5, 7), tiles=[(1, 2, 0, "{a: 1b}")], entities=[(0.5, 1.0, 2.25, "minecraft:marker", "{}")],
               biome_palette=["minecraft:cherry_grove"], biomes=bio, header={"world": "world", "label": "x"})
    r = Bundle.from_bytes(b.to_bytes())
    assert r.palette == b.palette and r.min == b.min and r.tiles == b.tiles and r.entities == b.entities
    assert np.array_equal(r.cells, cells) and np.array_equal(r.biomes, bio)
    assert r.header["world"] == "world" and r.biome_palette == ["minecraft:cherry_grove"]


@pytest.fixture(scope="module")
def fake(fake_bridge):
    return fake_bridge


@pytest.fixture(scope="module")
def client(fake):
    c = BridgeClient(fake.url, fake.token)
    yield c
    c.close()


def _stats(client) -> dict:
    line = client.command("testkit stats")["output"][0]
    return dict(kv.split("=", 1) for kv in line.split())


def _build_scene() -> Scene:
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 9, 0, 9), "polished_andesite")
    S.fill((0, 1, 0, 0, 3, 0), "oak_log")
    S.set(3, 1, 3, "oak_stairs[facing=east]")
    S.set(5, 1, 5, "oak_fence[north=true]")
    S.set(2, 1, 7, "lantern[hanging=false]")
    E.sign(S, (6, 1, 2), ["Добро", "пожаловать!"], rotation=4)
    E.hologram(S, (5, 3, 5), ["SPAWN"])
    S.set_biome((0, 0, 0, 3, 0, 9), "cherry_grove")
    return S


def test_status_auth_command(client, fake):
    assert client.ping()["plugin"] == "BuildBridge"
    st = client.status()
    assert st["minecraft"] == "1.21.4" and st["data_version"] == 4189
    assert st["worlds"][0]["name"] == "world"
    with pytest.raises(BridgeError, match="401"):
        BridgeClient(fake.url, "wrong").status()
    assert "[Server] hi" in client.command("say hi")["output"][0]
    p = client.teleport("Steve", (10.5, 70, -3.5), yaw=90, pitch=10)
    assert p["pos"] == [10.5, 70.0, -3.5] and p["yaw"] == 90.0
    assert client.player()["name"] == "Steve"


def test_paste_read_update_undo(client):
    S = _build_scene()
    tag = entity_tag_for("test")
    off = (100, 70, 100)
    b1, snap1, info = build_bundle(S, off, "1.21.4", world="world", label="test", entity_tag=tag)
    assert info["blocks"] == int((S.data != 0).sum()) and info["entities"] == 1 and info["block_entities"] == 1
    assert info["biomes"] == ["minecraft:cherry_grove", "minecraft:plains"] or "minecraft:cherry_grove" in info["biomes"]

    j = client.wait(client.paste(b1)["id"])
    assert j["phase"] == "done", j
    assert j["placed"] == info["blocks"] and j["tiles"] == 1 and j["entities"] == 1 and j["biome_commands"] > 0
    assert j["backup"] and not [w for w in j["warnings"] if "failed" in w], j["warnings"]
    st = _stats(client)
    assert st["tickets"] == "0" and st["violations"] == "0" and st["physics"] == "0", st
    assert st["sync_loads"] == "0", st

    # read the area back: every block, the sign text, the hologram
    box = (100, 70, 100, 109, 73, 109)
    rb = client.region(box)
    sd = rb.to_structure()
    for x in range(10):
        for y in range(4):
            for z in range(10):
                want = S.get(x, y, z)
                got = sd.palette[int(sd.data[x, y, z])]
                assert _norm(got) == _norm(want), (x, y, z, got, want)
    (bid, nbt), = sd.block_entities.values()
    assert bid == "minecraft:sign" and "Добро" in str(nbt["front_text"]["messages"][0])
    assert len(sd.entities) == 1 and sd.entities[0][0] == "minecraft:text_display"
    assert tag in [str(t) for t in sd.entities[0][2]["Tags"]]
    assert "minecraft:cherry_grove" in rb.biome_palette

    # paste the same thing again: nothing changes except the sign that is always refreshed
    j2 = client.wait(client.paste(b1)["id"])
    assert j2["phase"] == "done" and j2["placed"] == 1 and j2["unchanged"] == info["blocks"] - 1, j2
    assert j2["entities_removed"] == 1 and j2["entities"] == 1

    # change the build: remove the log column, add a block; the old log must disappear in the world
    S.clear((0, 1, 0, 0, 3, 0))
    S.set(8, 1, 8, "gold_block")
    b3, snap3, info3 = build_bundle(S, off, "1.21.4", world="world", label="test v2", entity_tag=tag, previous=snap1)
    assert info3["cleared"] == 3
    j3 = client.wait(client.paste(b3)["id"])
    assert j3["phase"] == "done" and j3["placed"] == 1 + 3 + 1, j3  # gold + 3 cleared + refreshed sign
    rb3 = client.region((100, 71, 100, 100, 73, 100), tiles=False, entities=False).to_structure()
    assert {rb3.palette[int(v)] for v in rb3.data.ravel()} == {"minecraft:air"}

    # undo v2: the log column comes back, the gold block goes
    u = client.wait(client.undo()["id"])
    assert u["phase"] == "done", u
    back = client.region((100, 71, 100, 100, 71, 100), tiles=False, entities=False).to_structure()
    assert _norm(back.palette[int(back.data[0, 0, 0])])[0] == "oak_log"
    # undo the first paste: original terrain (air above grass), no sign, no hologram
    client.wait(client.undo()["id"])  # the second (identical) paste
    u1 = client.wait(client.undo()["id"])
    assert u1["phase"] == "done", u1
    orig = client.region((100, 70, 100, 109, 73, 109), entities=True).to_structure()
    assert {orig.palette[int(v)] for v in np.unique(orig.data)} == {"minecraft:air"}
    assert not orig.block_entities and not orig.entities
    with pytest.raises(BridgeError, match="no backup"):
        client.undo()
    st = _stats(client)
    assert st["tickets"] == "0" and st["violations"] == "0" and st["sync_loads"] == "0", st
    assert float(st["max_task_ms"]) < 250, st  # work is spread over ticks (budget 20 ms + GC noise)
    assert all(v < 250 for v in u1["max_tick_ms"].values()), u1["max_tick_ms"]


def test_heightmap_and_invalid_states(client):
    hm = client.heightmap((-5, -5, 4, 4))
    assert hm["w"] == 10 and set(hm["heights"]) == {63}
    assert hm["top_palette"][hm["top"][0]] == "minecraft:grass_block[snowy=false]"
    cells = np.zeros((2, 1, 1), dtype=np.uint16)
    cells[0, 0, 0], cells[1, 0, 0] = 1, 2
    b = Bundle(palette=[SKIP, "minecraft:stone", "minecraft:not_a_block"], cells=cells, min=(0, 80, 0),
               header={"world": "world", "backup": False})
    j = client.wait(client.paste(b)["id"])
    assert j["phase"] == "done" and j["placed"] == 1 and j["invalid"] == 1
    assert any("not_a_block" in w for w in j["warnings"])


def test_bad_requests(client):
    with pytest.raises(BridgeError, match="bad magic|gzip"):
        client.paste(b"hello")
    with pytest.raises(BridgeError, match="404"):
        client.job("nope")
    with pytest.raises(BridgeError, match="world"):
        client.region((0, 0, 0, 1, 1, 1), world="nowhere")
