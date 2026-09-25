"""Turn a bundle into vanilla commands (the RCON fallback when BuildBridge is not installed).

Blocks are merged into uniform cuboids (``fill``, at most 32768 blocks each). Order: solid blocks,
then everything that needs support (plants, torches, doors...), then fluids, then block entities,
entities and biomes. On 1.21.5+ ``strict`` placement skips block updates, like the bridge; older
servers run neighbour updates (fences reconnect, sand falls), so the bridge gives better results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from numba import njit

from ..blocks import families as F
from ..blocks.registry import get_registry, parse_state
from .bundle import SKIP, Bundle
from .rcon import MAX_COMMAND_BYTES, RconClient

FILL_LIMIT = 32768
FORCELOAD_LIMIT = 256
STRICT_DV = 4325  # 1.21.5: "strict" mode for fill/setblock


@njit(cache=True)
def greedy_boxes(vals, include, max_volume):
    """Cover the included cells with cuboids of equal value. Returns an (n, 7) int32 array
    [x1, y1, z1, x2, y2, z2, value]; boxes come out bottom-up."""
    w, h, l = vals.shape
    used = np.zeros((w, h, l), dtype=np.bool_)
    n_inc = 0
    for x in range(w):
        for y in range(h):
            for z in range(l):
                if include[x, y, z]:
                    n_inc += 1
    out = np.empty((n_inc, 7), dtype=np.int32)
    n = 0
    for y in range(h):
        for z in range(l):
            for x in range(w):
                if not include[x, y, z] or used[x, y, z]:
                    continue
                v = vals[x, y, z]
                x2 = x
                while x2 + 1 < w and x2 + 2 - x <= max_volume and include[x2 + 1, y, z] and not used[x2 + 1, y, z] \
                        and vals[x2 + 1, y, z] == v:
                    x2 += 1
                dx = x2 - x + 1
                z2 = z
                while z2 + 1 < l and (z2 + 2 - z) * dx <= max_volume:
                    ok = True
                    for xx in range(x, x2 + 1):
                        if not include[xx, y, z2 + 1] or used[xx, y, z2 + 1] or vals[xx, y, z2 + 1] != v:
                            ok = False
                            break
                    if not ok:
                        break
                    z2 += 1
                dz = z2 - z + 1
                y2 = y
                while y2 + 1 < h and (y2 + 2 - y) * dx * dz <= max_volume:
                    ok = True
                    for zz in range(z, z2 + 1):
                        for xx in range(x, x2 + 1):
                            if not include[xx, y2 + 1, zz] or used[xx, y2 + 1, zz] or vals[xx, y2 + 1, zz] != v:
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                    y2 += 1
                for yy in range(y, y2 + 1):
                    for zz in range(z, z2 + 1):
                        for xx in range(x, x2 + 1):
                            used[xx, yy, zz] = True
                out[n, 0] = x
                out[n, 1] = y
                out[n, 2] = z
                out[n, 3] = x2
                out[n, 4] = y2
                out[n, 5] = z2
                out[n, 6] = v
                n += 1
    return out[:n]


# placement groups
SOLID, SUPPORTED, FLUID = 0, 1, 2


def _group(reg, state: str) -> int:
    name, props, _ = parse_state(state)
    if name in ("water", "lava", "bubble_column") or props.get("waterlogged") == "true":
        return FLUID
    try:
        if reg.is_full_cube(state):
            return SOLID
        kind = F.kind_of(reg, "minecraft:" + name)
    except Exception:  # noqa: BLE001
        return SUPPORTED
    return SOLID if kind in (F.SLAB, F.STAIRS, F.WALL, F.FENCE, F.PANE) else SUPPORTED


@dataclass
class CommandPlan:
    phases: list[tuple[str, list[str]]] = field(default_factory=list)
    chunks: list[tuple[int, int, int, int]] = field(default_factory=list)  # forceload rectangles
    probes: list[tuple[int, int, int]] = field(default_factory=list)  # one block per chunk
    warnings: list[str] = field(default_factory=list)
    strict: bool = False

    @property
    def count(self) -> int:
        return sum(len(c) for _, c in self.phases)


def _fmt(v: float) -> str:
    s = f"{v:.5f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def split_nbt(snbt: str, prefix: str, limit: int = MAX_COMMAND_BYTES) -> list[str]:
    """Split a compound into several partial compounds so ``prefix + part`` fits in one RCON packet."""
    import nbtlib

    if len((prefix + snbt).encode("utf-8")) <= limit:
        return [snbt]
    tag = nbtlib.parse_nbt(snbt)
    parts, cur = [], nbtlib.Compound()
    for k, v in tag.items():
        trial = nbtlib.Compound(cur)
        trial[k] = v
        if len((prefix + nbtlib.serialize_tag(trial)).encode("utf-8")) <= limit:
            cur = trial
            continue
        if cur:
            parts.append(nbtlib.serialize_tag(cur))
        single = nbtlib.Compound({k: v})
        if len((prefix + nbtlib.serialize_tag(single)).encode("utf-8")) > limit:
            raise ValueError(f"NBT field '{k}' alone is too long for RCON ({len(nbtlib.serialize_tag(single))} bytes)")
        cur = single
    if cur:
        parts.append(nbtlib.serialize_tag(cur))
    return parts


def plan_commands(b: Bundle, version: str, dimension: str | None = None, entity_tag: str | None = None,
                  strict: bool | None = None) -> CommandPlan:
    """All commands to place a bundle at b.min. ``dimension`` e.g. 'minecraft:the_nether'."""
    reg = get_registry(version)
    plan = CommandPlan()
    plan.strict = bool(reg.data_version >= STRICT_DV) if strict is None else bool(strict)
    mode = " strict" if plan.strict else ""
    pre = f"execute in {dimension} run " if dimension and dimension != "minecraft:overworld" else ""
    ox, oy, oz = b.min
    w, h, l = b.size

    # chunks to keep loaded
    cx1, cz1, cx2, cz2 = ox >> 4, oz >> 4, (ox + w - 1) >> 4, (oz + l - 1) >> 4
    for bx in range(cx1, cx2 + 1, 16):
        for bz in range(cz1, cz2 + 1, 16):
            ex, ez = min(cx2, bx + 15), min(cz2, bz + 15)
            plan.chunks.append((bx * 16, bz * 16, ex * 16 + 15, ez * 16 + 15))
    for cx in range(cx1, cx2 + 1):
        for cz in range(cz1, cz2 + 1):
            plan.probes.append((cx * 16, oy, cz * 16))

    # old entities of this build
    if entity_tag:
        plan.phases.append(("remove old entities", [
            f"{pre}kill @e[tag={entity_tag},x={ox},y={oy},z={oz},dx={w},dy={h},dz={l}]"]))

    tile_cells = np.zeros(b.cells.shape, dtype=np.bool_)
    tiles_by_pos = {}
    for x, y, z, snbt in b.tiles:
        if 0 <= x < w and 0 <= y < h and 0 <= z < l:
            tile_cells[x, y, z] = True
            tiles_by_pos[(x, y, z)] = snbt

    groups = np.zeros(len(b.palette), dtype=np.int8)
    for i, s in enumerate(b.palette):
        if i and s != SKIP:
            groups[i] = _group(reg, s)
    cell_group = groups[b.cells]
    names = {SOLID: "solid blocks", SUPPORTED: "attached blocks", FLUID: "fluids"}
    for g in (SOLID, SUPPORTED, FLUID):
        include = (b.cells != 0) & (cell_group == g) & ~tile_cells
        if not include.any():
            continue
        boxes = greedy_boxes(b.cells, include, FILL_LIMIT)
        cmds = []
        for x1, y1, z1, x2, y2, z2, v in boxes.tolist():
            state = b.palette[v]
            if (x1, y1, z1) == (x2, y2, z2):
                cmds.append(f"{pre}setblock {ox + x1} {oy + y1} {oz + z1} {state}{mode}")
            else:
                cmds.append(f"{pre}fill {ox + x1} {oy + y1} {oz + z1} {ox + x2} {oy + y2} {oz + z2} {state}"
                            f"{mode or ' replace'}")
        plan.phases.append((names[g], cmds))

    # block entities: block + NBT in one setblock when it fits, else setblock + data merge parts
    cmds = []
    for (x, y, z), snbt in tiles_by_pos.items():
        idx = int(b.cells[x, y, z])
        wx, wy, wz = ox + x, oy + y, oz + z
        if idx:
            one = f"{pre}setblock {wx} {wy} {wz} {b.palette[idx]}{snbt}{mode}"
            if len(one.encode("utf-8")) <= MAX_COMMAND_BYTES:
                cmds.append(one)
                continue
            cmds.append(f"{pre}setblock {wx} {wy} {wz} {b.palette[idx]}{mode}")
        prefix = f"{pre}data merge block {wx} {wy} {wz} "
        try:
            for part in split_nbt(snbt, prefix):
                cmds.append(prefix + part)
        except ValueError as e:
            plan.warnings.append(f"block entity at {wx},{wy},{wz}: {e}")
    if cmds:
        plan.phases.append(("block entities", cmds))

    # entities
    cmds = []
    for n, (x, y, z, eid, snbt) in enumerate(b.entities):
        pos = f"{_fmt(ox + x)} {_fmt(oy + y)} {_fmt(oz + z)}"
        one = f"{pre}summon {eid} {pos} {snbt}"
        if len(one.encode("utf-8")) <= MAX_COMMAND_BYTES:
            cmds.append(one)
            continue
        tmp = f"bmcp_tmp_{int(time.time()) % 100000}_{n}"
        cmds.append(f"{pre}summon {eid} {pos} {{Tags:[\"{tmp}\"]}}")
        prefix = f"{pre}data merge entity @e[tag={tmp},limit=1] "
        try:
            for part in split_nbt(snbt, prefix):
                cmds.append(prefix + part)
        except ValueError as e:
            plan.warnings.append(f"entity {eid} at {pos}: {e}")
        cmds.append(f"{pre}tag @e[tag={tmp}] remove {tmp}")
    if cmds:
        plan.phases.append(("entities", cmds))

    if b.biomes is not None and b.biome_palette:
        cmds = [pre + c for c in biome_commands(b.biome_palette, b.biomes, ox, oz, oy, oy + h - 1)]
        if cmds:
            plan.phases.append(("biomes", cmds))
    return plan


def biome_commands(palette: list[str], grid: np.ndarray, ox: int, oz: int, y1: int, y2: int) -> list[str]:
    """/fillbiome commands for a per-column biome grid (grouped into 4x4 quart columns)."""
    w, l = grid.shape
    qx1, qz1 = ox // 4, oz // 4
    qx2, qz2 = (ox + w - 1) // 4, (oz + l - 1) // 4
    qw, ql = qx2 - qx1 + 1, qz2 - qz1 + 1
    quart = np.full((qw, ql), -1, dtype=np.int32)
    for qx in range(qw):
        for qz in range(ql):
            xs = slice(max(0, (qx1 + qx) * 4 - ox), max(0, min(w, (qx1 + qx) * 4 + 4 - ox)))
            zs = slice(max(0, (qz1 + qz) * 4 - oz), max(0, min(l, (qz1 + qz) * 4 + 4 - oz)))
            vals = grid[xs, zs].ravel()
            vals = vals[vals != 255]
            if vals.size:
                cnt = np.bincount(vals)
                quart[qx, qz] = int(cnt.argmax())
    rows = y2 // 4 - y1 // 4 + 1
    max_area = max(1, FILL_LIMIT // (64 * rows))
    used = np.zeros_like(quart, dtype=bool)
    out = []
    for qz in range(ql):
        for qx in range(qw):
            v = quart[qx, qz]
            if v < 0 or used[qx, qz]:
                continue
            ex = qx
            while ex + 1 < qw and quart[ex + 1, qz] == v and not used[ex + 1, qz] and ex + 2 - qx <= max_area:
                ex += 1
            ez = qz
            while ez + 1 < ql and (ez + 2 - qz) * (ex - qx + 1) <= max_area and \
                    all(quart[x, ez + 1] == v and not used[x, ez + 1] for x in range(qx, ex + 1)):
                ez += 1
            used[qx:ex + 1, qz:ez + 1] = True
            out.append(f"fillbiome {(qx1 + qx) * 4} {y1} {(qz1 + qz) * 4} {(qx1 + ex) * 4 + 3} {y2} "
                       f"{(qz1 + ez) * 4 + 3} {palette[v]}")
    return out


_FAIL_MARKERS = ("unknown", "incorrect", "invalid", "expected", "error", "not loaded", "too many", "unable",
                 "cannot", "could not parse", "failed", "no entity", "is not", "out of the world")
_BENIGN = ("no blocks were filled", "could not set the block", "nothing changed")


def is_failure(out: str) -> bool:
    t = out.lower()
    if any(b in t for b in _BENIGN):
        return False
    return any(m in t for m in _FAIL_MARKERS)


def run_plan(rcon: RconClient, plan: CommandPlan, on_progress=None, load_timeout: float = 60.0) -> dict:
    """Execute a plan over RCON: force-load chunks, run every phase, release the chunks."""
    t0 = time.time()
    warnings = list(plan.warnings)
    failures = 0
    total = plan.count
    done = 0
    admin_log = None
    try:
        out = rcon.command("gamerule logAdminCommands")
        if "true" in out.lower():
            admin_log = True
            rcon.command("gamerule logAdminCommands false")  # no chat spam for operators
    except Exception:  # noqa: BLE001
        pass
    try:
        for x1, z1, x2, z2 in plan.chunks:
            rcon.command(f"forceload add {x1} {z1} {x2} {z2}")
        deadline = time.time() + load_timeout
        pending = list(plan.probes)
        while pending and time.time() < deadline:
            pending = [p for p in pending if "passed" not in rcon.command(f"execute if loaded {p[0]} {p[1]} {p[2]}").lower()]
            if pending:
                time.sleep(0.25)
        if pending:
            warnings.append(f"{len(pending)} chunk(s) did not load in {load_timeout:.0f} s")
        for name, cmds in plan.phases:
            for c in cmds:
                out = rcon.command(c)
                done += 1
                if out and is_failure(out):
                    failures += 1
                    if failures <= 30:
                        warnings.append(f"{c[:120]} -> {out[:200]}")
                if on_progress and done % 250 == 0:
                    on_progress(name, done, total)
    finally:
        for x1, z1, x2, z2 in plan.chunks:
            try:
                rcon.command(f"forceload remove {x1} {z1} {x2} {z2}")
            except Exception:  # noqa: BLE001
                pass
        if admin_log:
            try:
                rcon.command("gamerule logAdminCommands true")
            except Exception:  # noqa: BLE001
                pass
    return {"commands": total, "failures": failures, "seconds": round(time.time() - t0, 1),
            "strict": plan.strict, "warnings": warnings[:60]}
