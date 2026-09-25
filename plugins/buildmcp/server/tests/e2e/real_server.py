"""End to end on a real Paper server (CI): BuildBridge pastes, read-back, undo, the RCON fallback
and "finalize parity" (our game-like block updates vs what the game computes itself).

    python real_server.py --paper paper.jar --bridge BuildBridge.jar --dir /tmp/srv --version 1.21.4

Exit code 0 = everything matched. A report is printed and written to <dir>/e2e-report.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from buildmcp.blocks import families as F
from buildmcp.blocks.finalize import finalize
from buildmcp.blocks.registry import get_registry, parse_state, resolve_version
from buildmcp.gen import entities as E
from buildmcp.live.bridge import BridgeClient, BridgeError
from buildmcp.live.bundle import Bundle
from buildmcp.live.connector import RconConnection
from buildmcp.live.deploy import build_bundle, entity_tag_for
from buildmcp.live.placer import plan_commands, run_plan
from buildmcp.live.rcon import RconClient
from buildmcp.scene import Scene

TOKEN = "e2e-token-0123456789"
RCON_PASSWORD = "e2e-rcon"


# ------------------------------------------------------------------ server
class Server:
    def __init__(self, paper: Path, bridge: Path, root: Path, port: int = 8765, rcon_port: int = 25575):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "plugins" / "BuildBridge").mkdir(parents=True, exist_ok=True)
        shutil.copy2(paper, root / "paper.jar")
        shutil.copy2(bridge, root / "plugins" / bridge.name)
        (root / "eula.txt").write_text("eula=true\n")
        (root / "server.properties").write_text("\n".join([
            "online-mode=false", "enable-rcon=true", f"rcon.password={RCON_PASSWORD}", f"rcon.port={rcon_port}",
            "broadcast-rcon-to-ops=false", "level-type=minecraft\\:flat", "generate-structures=false",
            "spawn-protection=0", "view-distance=4", "simulation-distance=4", "max-tick-time=-1",
            "spawn-monsters=false", "spawn-animals=false", "motd=BuildMCP e2e", "server-port=25565", ""]))
        (root / "plugins" / "BuildBridge" / "config.yml").write_text(
            f'bind: 127.0.0.1\nport: {port}\ntoken: "{TOKEN}"\nallowed-ips: []\nmax-tick-millis: 25\n'
            "max-upload-mb: 256\nmax-cells: 20000000\nbackups:\n  enabled: true\n  keep: 30\n")
        self.port, self.rcon_port = port, rcon_port
        self.log = open(root / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(["java", "-Xms1G", "-Xmx3G", "-jar", "paper.jar", "--nogui"], cwd=root,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        self.lines: list[str] = []
        self.ready = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.log.write(line)
            self.log.flush()
            self.lines.append(line.rstrip())
            if "Done (" in line and "For help" in line:
                self.ready.set()

    def wait_ready(self, timeout: float = 600.0):
        if not self.ready.wait(timeout):
            raise SystemExit("server did not start:\n" + "\n".join(self.lines[-60:]))

    def stop(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
                self.proc.wait(120)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        self.log.close()


# ------------------------------------------------------------------- scenes
def showcase(version: str) -> Scene:
    """Many block kinds, block entities and entities in a small area."""
    from buildmcp.gen import arch, props, trees

    S = Scene(version)
    S.fill((0, 0, 0, 31, 0, 31), "grass_block")
    S.fill((2, 1, 2, 29, 1, 3), "stone_bricks")
    arch.house(S, (6, 1, 8, 15, 6, 15), theme="fantasy_medieval", seed=1)
    for x in (4, 12, 20, 28):
        props.lamp_post(S, (x, 1, 28), theme="fantasy_medieval")
    trees.tree(S, (24, 0, 14), kind="oak", seed=3, theme="fantasy_medieval")
    E.sign(S, (3, 1, 5), ["BuildMCP", "e2e тест"], rotation=4)
    E.sign(S, (3, 2, 3), ["Стена"], facing="south")
    E.banner(S, (5, 1, 5), "red", [("stripe_center", "yellow"), ("border", "black")], rotation=8)
    E.head(S, (7, 2, 3), rotation=0, name="Notch")
    E.hologram(S, (16.5, 4, 16.5), ["Добро пожаловать", "на сервер"])
    E.block_display(S, (12.5, 3, 12.5), "lantern", scale=2.0)
    E.item_display(S, (14.5, 3, 12.5), "diamond_sword", scale=1.5)
    S.fill((18, 0, 20, 22, 0, 24), "water")
    S.set(10, 1, 20, "chest[facing=north]")
    S.set(11, 1, 20, "barrel[facing=up]")
    S.set(12, 1, 20, "campfire[lit=true]")
    S.set(13, 1, 20, "lantern[hanging=false]")
    S.set(14, 1, 20, "candle[candles=3,lit=true]")
    S.set_biome((0, 0, 0, 15, 0, 31), "cherry_grove")
    finalize(S)
    return S


def parity_scene(version: str, seed: int = 7) -> Scene:
    """Raw (un-finalized) blocks whose final state depends on neighbours."""
    rng = np.random.default_rng(seed)
    S = Scene(version)
    S.fill((0, 0, 0, 47, 0, 47), "stone")
    # fences, panes, bars, walls on random masks, with solid blocks and walls/fences above
    kinds = ["oak_fence", "nether_brick_fence", "glass_pane", "iron_bars", "cobblestone_wall", "mossy_stone_brick_wall",
             "red_stained_glass_pane"]
    for k, name in enumerate(kinds):
        x0 = 2 + (k % 4) * 11
        z0 = 2 + (k // 4) * 11
        m = rng.random((8, 8)) < 0.55
        for dx in range(8):
            for dz in range(8):
                if m[dx, dz]:
                    S.set(x0 + dx, 1, z0 + dz, name)
                    if name.endswith("_wall") and rng.random() < 0.3:
                        S.set(x0 + dx, 2, z0 + dz, rng.choice(["stone", name, "torch", "oak_fence"]))
                elif rng.random() < 0.15:
                    S.set(x0 + dx, 1, z0 + dz, "stone_bricks")
    # fence gates between walls and fences
    S.set(40, 1, 30, "cobblestone_wall")
    S.set(41, 1, 30, "oak_fence_gate[facing=north]")
    S.set(42, 1, 30, "cobblestone_wall")
    S.set(40, 1, 33, "oak_fence")
    S.set(41, 1, 33, "oak_fence_gate[facing=north]")
    S.set(42, 1, 33, "oak_fence")
    # stairs clusters (corners)
    for i in range(36):
        x, z = 2 + i % 6, 26 + i // 6
        if rng.random() < 0.8:
            f = rng.choice(["north", "south", "east", "west"])
            h = "top" if rng.random() < 0.3 else "bottom"
            S.set(x, 1, z, f"oak_stairs[facing={f},half={h}]")
    # snow on grass
    S.fill((12, 1, 26, 17, 1, 31), "grass_block")
    for x in range(12, 18):
        for z in range(26, 32):
            if rng.random() < 0.5:
                S.set(x, 2, z, f"snow[layers={int(rng.integers(1, 4))}]")
    # mushroom blocks
    for x in range(20, 25):
        for y in range(1, 4):
            for z in range(26, 31):
                if rng.random() < 0.6:
                    S.set(x, y, z, "brown_mushroom_block")
    # dripstone columns hanging from a ceiling
    S.fill((28, 8, 26, 34, 8, 32), "dripstone_block")
    for x in range(28, 35, 2):
        for z in range(26, 33, 2):
            n = int(rng.integers(1, 5))
            for k in range(n):
                S.set(x, 7 - k, z, "pointed_dripstone[vertical_direction=down]")
    # weeping vines and cave vines columns
    S.fill((36, 8, 36, 44, 8, 44), "netherrack")
    for x in range(36, 45, 2):
        n = int(rng.integers(1, 5))
        for k in range(n):
            S.set(x, 7 - k, 36, "weeping_vines")
            S.set(x, 7 - k, 40, "cave_vines")
    return S


def norm(state: str):
    name, props, _ = parse_state(state)
    return name, tuple(sorted(props.items()))


PARITY_KINDS = {F.FENCE, F.PANE, F.WALL, F.FENCE_GATE, F.STAIRS, F.MUSHROOM_BLOCK, F.DRIPSTONE, F.HANGING_PLANT}


# -------------------------------------------------------------------- tests
class Report:
    def __init__(self):
        self.results: list[dict] = []

    def check(self, name: str, ok: bool, **details):
        self.results.append({"name": name, "ok": bool(ok), **details})
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + json.dumps(details, ensure_ascii=False)[:2000]),
              flush=True)

    @property
    def ok(self) -> bool:
        return all(r["ok"] for r in self.results)


def compare_region(client: BridgeClient, S: Scene, offset, region=None):
    b = S.bbox() if region is None else region
    ox, oy, oz = offset
    rb = client.region((b.x1 + ox, b.y1 + oy, b.z1 + oz, b.x2 + ox, b.y2 + oy, b.z2 + oz), tiles=True, entities=True)
    sd = rb.to_structure()
    reg = get_registry(S.version)
    bad = []
    for x in range(b.x1, b.x2 + 1):
        for y in range(b.y1, b.y2 + 1):
            for z in range(b.z1, b.z2 + 1):
                want = S.get(x, y, z)
                got = sd.palette[int(sd.data[x - b.x1, y - b.y1, z - b.z1])]
                if norm(got) != norm(reg.canonical(want)):
                    bad.append({"pos": [x, y, z], "want": want, "got": got})
    return sd, bad


def dump_log(srv: "Server", why: str) -> None:
    """Print what the server said about the plugin (CI artifacts are not always reachable)."""
    print(f"==== {why}; BuildBridge lines and the last 80 server log lines ====", flush=True)
    for ln in srv.lines:
        if "BuildBridge" in ln or "plugin.yml" in ln or "Could not load" in ln:
            print("  " + ln)
    print("  ----")
    for ln in srv.lines[-80:]:
        print("  " + ln)
    sys.stdout.flush()


def run(args) -> Report:
    rep = Report()
    version = resolve_version(args.version)
    srv = Server(Path(args.paper), Path(args.bridge), Path(args.dir))
    try:
        return _run(args, rep, version, srv)
    except BaseException:
        dump_log(srv, "e2e crashed")
        raise
    finally:
        srv.stop()


def _run(args, rep: Report, version: str, srv: "Server") -> Report:
    srv.wait_ready()
    client = BridgeClient(f"http://127.0.0.1:{srv.port}", TOKEN, timeout=60)
    for _ in range(60):
        try:
            client.ping()
            break
        except BridgeError:
            time.sleep(1)
    else:
        raise RuntimeError(f"BuildBridge did not start listening on port {srv.port}")
    st = client.status()
    rep.check("status", st["data_version"] == get_registry(version).data_version, status=st)
    version = resolve_version(st["minecraft"])
    rep.check("bridge enabled without errors", not any("BuildBridge" in ln and ("ERROR" in ln or "Exception" in ln)
                                                      for ln in srv.lines))

    # 1. showcase paste + read back
    S = showcase(version)
    tag = entity_tag_for("e2e")
    off = (1000, 70, 1000)
    b, snap, info = build_bundle(S, off, version, world="world", label="e2e showcase", entity_tag=tag)
    j = client.wait(client.paste(b)["id"], timeout=600)
    rep.check("paste showcase", j["phase"] == "done" and j["placed"] == info["blocks"] and not j["warnings"],
              job=j, info=info)
    sd, bad = compare_region(client, S, off)
    rep.check("showcase blocks read back 1:1", not bad, mismatches=bad[:40], count=len(bad))
    rep.check("block entities kept", len(sd.block_entities) >= len(S.block_entities),
              got=len(sd.block_entities), want=len(S.block_entities))
    signs = [str(n) for (bid, n) in sd.block_entities.values() if bid.endswith("sign")]
    rep.check("sign text kept", any("BuildMCP" in s for s in signs) and any("Стена" in s for s in signs),
              signs=signs[:3])
    rep.check("entities placed", len([e for e in sd.entities if tag in str(e[2].get("Tags", ""))]) == len(S.entities),
              got=[e[0] for e in sd.entities], want=len(S.entities))
    rep.check("biomes", "minecraft:cherry_grove" in (client.region((off[0], off[1], off[2], off[0] + 3, off[1],
                                                                      off[2] + 3)).biome_palette or []))

    # 2. identical re-paste changes nothing but block entities
    j2 = client.wait(client.paste(b)["id"], timeout=600)
    rep.check("re-paste is a no-op", j2["phase"] == "done" and j2["placed"] == len(b.tiles), job=j2)

    # 3. undo twice -> flat world again
    for k in range(2):
        u = client.wait(client.undo()["id"], timeout=600)
        rep.check(f"undo {k + 1}", u["phase"] == "done", job=u)
    after = client.region((off[0], off[1] + 1, off[2], off[0] + 31, off[1] + 12, off[2] + 31)).to_structure()
    rep.check("undo restores the world", set(after.palette[int(v)] for v in np.unique(after.data)) == {"minecraft:air"}
              and not after.entities, palette=after.palette[:10], entities=len(after.entities))

    # 4. finalize parity: the game computes shapes itself when placing without strict mode
    raw = parity_scene(version)
    expected = Scene.from_bytes(raw.to_bytes())
    finalize(expected)
    poff = (2000, 70, 2000)
    rb, _, _ = build_bundle(raw, poff, version, world="world", backup=False)
    # /setblock and /fill do not work out the shape of the block they place, but every placement
    # updates its neighbours (and changed neighbours update theirs). So the connecting blocks go
    # first (raw) and everything else after: each later neighbour makes the game recompute them.
    kinds_b = raw.kind_lut()
    connecting = np.zeros(len(rb.palette), dtype=bool)
    for i, st in enumerate(rb.palette):
        if i and st:
            try:
                connecting[i] = int(kinds_b[raw.id_of(st)]) in PARITY_KINDS
            except Exception:  # noqa: BLE001
                pass
    first = Bundle(palette=rb.palette, cells=np.where(connecting[rb.cells], rb.cells, 0).astype(np.uint16),
                   min=rb.min, header=dict(rb.header))
    second = Bundle(palette=rb.palette, cells=np.where(connecting[rb.cells], 0, rb.cells).astype(np.uint16),
                    min=rb.min, header=dict(rb.header))
    rc = RconClient("127.0.0.1", srv.rcon_port, RCON_PASSWORD)
    rc.connect()
    placed = [run_plan(rc, plan_commands(b, version, strict=False)) for b in (first, second)]
    rep.check("parity scene placed over RCON", all(r["failures"] == 0 for r in placed), result=placed)
    time.sleep(1.5)  # leaves/dripstone settle through scheduled ticks
    sd, _ = compare_region(client, raw, poff)
    kinds = expected.kind_lut()
    bb = raw.bbox()

    def game(x, y, z):
        if not (bb.x1 <= x <= bb.x2 and bb.y1 <= y <= bb.y2 and bb.z1 <= z <= bb.z2):
            return "?"
        return sd.palette[int(sd.data[x - bb.x1, y - bb.y1, z - bb.z1])].removeprefix("minecraft:")

    mism = {}
    for x in range(bb.x1, bb.x2 + 1):
        for y in range(bb.y1, bb.y2 + 1):
            for z in range(bb.z1, bb.z2 + 1):
                idx = expected.get_id(x, y, z)
                name = parse_state(expected.palette[idx])[0]
                if int(kinds[idx]) not in PARITY_KINDS and name not in ("grass_block", "oak_leaves"):
                    continue
                got = game(x, y, z)
                if norm("minecraft:" + got) != norm(expected.palette[idx]):
                    nbs = {d: game(x + dx, y + dy, z + dz) for d, (dx, dy, dz) in
                           {"N": (0, 0, -1), "S": (0, 0, 1), "E": (1, 0, 0), "W": (-1, 0, 0), "U": (0, 1, 0),
                            "D": (0, -1, 0)}.items()}
                    mism.setdefault(F.KIND_NAMES.get(int(kinds[idx]), name), []).append(
                        {"pos": [x, y, z], "finalize": expected.palette[idx].removeprefix("minecraft:"), "game": got,
                         "game_neighbours": nbs})
    rep.check("finalize parity", not mism, counts={k: len(v) for k, v in mism.items()},
              examples={k: v[:3] for k, v in mism.items()})

    # 5. RCON fallback paste (strict when the server supports it)
    conn = RconConnection(rc, version)
    R = showcase(version)
    roff = (3000, 70, 3000)
    rbun, _, _ = build_bundle(R, roff, version, world="world", entity_tag=entity_tag_for("e2e-rcon"))
    res = conn.paste(rbun)
    sd, bad = compare_region(client, R, roff)
    rep.check("rcon paste", res.get("failures") == 0 and (not bad if conn.strict_supported() else True),
              result=res, mismatches=bad[:30], strict=conn.strict_supported())

    # 6. heightmap of the flat world
    hm = client.heightmap((-20, -20, -11, -11))
    rep.check("heightmap", len(set(hm["heights"])) == 1, heights=sorted(set(hm["heights"])))
    rep.check("server log has no BuildBridge errors",
              not [ln for ln in srv.lines if "BuildBridge" in ln and ("SEVERE" in ln or "Exception" in ln)],
              lines=[ln for ln in srv.lines if "BuildBridge" in ln][-20:])
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--bridge", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--version", default="1.21.4")
    args = ap.parse_args()
    rep = run(args)
    Path(args.dir, "e2e-report.json").write_text(json.dumps(rep.results, indent=1, ensure_ascii=False, default=str))
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
