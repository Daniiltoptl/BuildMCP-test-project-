"""MCP server entry point for BuildMCP: the tools Claude uses to build spawns."""

from __future__ import annotations

import io
import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from buildmcp import __version__

INSTRUCTIONS = """\
BuildMCP — build Minecraft spawns at top-server quality, see them, check them, paste them.
Load the spawn-builder skill for the workflow and design rules. Core loop:
project_new/project_open -> run_script (procedural code, one pipeline step per call) ->
render (look!) -> inspect (lint/walk) -> fix -> export / server_paste.
Call api_docs() once per session before writing scripts.
"""

server = MCPServer(name="buildmcp", version=__version__, instructions=INSTRUCTIONS)


class _State:
    project = None
    render_counter = 0
    warm = {"done": False, "seconds": None, "error": None}


STATE = _State()


def _project():
    if STATE.project is None:
        raise RuntimeError("No project is open. Use project_new(name, theme) or project_open(name).")
    return STATE.project


def _err(e: Exception) -> str:
    from buildmcp.blocks.registry import BlockError

    if isinstance(e, (BlockError, ValueError, KeyError, FileNotFoundError, FileExistsError, RuntimeError)):
        return f"Error: {e}"
    return "Error: " + "".join(traceback.format_exception_only(type(e), e)).strip()


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _save_render(img, view: str) -> str:
    p = STATE.project
    STATE.render_counter += 1
    if p is None:
        return ""
    path = p.renders_dir / f"{int(time.time())}_{STATE.render_counter:03d}_{view}.png"
    img.save(path)
    return str(path)


def _fmt(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


# ====================================================================== projects
@server.tool()
def project_new(name: str, theme: str = "fantasy_medieval", version: str = "auto", description: str = "",
                seed: int = 0) -> str:
    """Create and open a new build project.

    theme: fantasy_medieval | asian_sakura | dark_infernal | winter_north (palettes + generator defaults).
    version: Minecraft version of the server (e.g. "1.21.4"); "auto" = configured/connected server version.
    """
    try:
        from buildmcp.project import Project

        STATE.project = Project.create(name, version, theme, description, seed)
        return f"Created project '{name}' (Minecraft {STATE.project.version}, theme {STATE.project.theme}) at {STATE.project.root}"
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def project_open(name: str) -> str:
    """Open an existing project (its scene, pipeline steps and undo history)."""
    try:
        from buildmcp.project import Project

        STATE.project = Project.open(name)
        return _fmt(STATE.project.summary())
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def project_list() -> str:
    """List saved projects."""
    from buildmcp.project import Project, builds_dir

    items = Project.list_all()
    return _fmt({"builds_dir": str(builds_dir()), "projects": items})


@server.tool()
def project_info() -> str:
    """Summary of the open project: version, theme, size, blocks, markers, pipeline steps."""
    try:
        return _fmt(_project().summary())
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def project_theme(theme: str) -> str:
    """Switch the project theme used by generators (does not repaint existing blocks)."""
    try:
        _project().set_theme(theme)
        from buildmcp import themes

        return themes.get(theme).describe()
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ====================================================================== building
@server.tool()
def run_script(code: str, label: str = "", save_step: bool = True, render: str = "", timeout: float = 180.0):
    """Run Python build code against the project scene — the main building tool.

    The namespace has the whole API (see api_docs): S (scene), T (theme), P (palettes), sdf, shapes,
    terrain, trees, arch, props, rocks, paths, text, E (entities), image, model, colors, noise, np,
    finalize(), lint(), mark(), print(). Generators get the scene/theme automatically.
    Each call is a pipeline step (saved to scripts/, undoable with history(action="undo")); a failing
    script is rolled back completely. save_step=False for throwaway experiments.
    render: optional view to return right away ("iso", "sheet", "top", "player"...).
    """
    try:
        p = _project()
        res = p.execute(code, label, save_step=save_step, timeout=timeout)
        text = _fmt(res)
        if res.get("ok") and render:
            from buildmcp.render.api import render_view

            img = render_view(p.scene, render, width=1200, height=760)
            path = _save_render(img, render)
            return [text + f"\nrender saved: {path}", Image(data=_png(img), format="png")]
        return text
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def edit(ops: list[dict]) -> str:
    """Quick edits without writing a script (recorded as one pipeline step). Each op is a dict:
    {"op":"fill","box":[x1,y1,z1,x2,y2,z2],"block":"stone","hollow":false,"walls":false,"only":null}
    {"op":"set","pos":[x,y,z],"block":"oak_stairs[facing=east]"}
    {"op":"replace","from":"stone","to":{"andesite":2,"tuff":1},"box":[...]}   (box optional)
    {"op":"clear","box":[...],"only":"#plants"}
    {"op":"copy","box":[...],"to":[x,y,z],"rotate":1,"mirror":"x","air":false}
    {"op":"move","box":[...],"by":[dx,dy,dz]}   {"op":"stack","box":[...],"by":[dx,dy,dz],"count":3}
    {"op":"transform","box":[...],"rotate":1,"mirror":null}
    {"op":"mark","name":"spawn","pos":[x,y,z],"kind":"spawn","yaw":180}
    """
    try:
        lines = []
        for o in ops:
            op = o.get("op")
            box = tuple(o["box"]) if "box" in o and o["box"] is not None else None
            if op == "fill":
                lines.append(f"S.fill({box!r}, {o['block']!r}, hollow={bool(o.get('hollow'))}, walls={bool(o.get('walls'))}, "
                             f"only={o.get('only')!r}, keep={bool(o.get('keep'))})")
            elif op == "set":
                x, y, z = o["pos"]
                lines.append(f"S.set({int(x)}, {int(y)}, {int(z)}, {o['block']!r})")
            elif op == "replace":
                lines.append(f"S.replace({o['from']!r}, {o['to']!r}, where={box!r})")
            elif op == "clear":
                lines.append(f"S.clear({box!r}, only={o.get('only')!r})")
            elif op == "copy":
                lines.append(f"S.paste(S.copy({box!r}), {tuple(o['to'])!r}, rotate={int(o.get('rotate', 0))}, "
                             f"mirror={o.get('mirror')!r}, air={bool(o.get('air'))})")
            elif op == "move":
                dx, dy, dz = o["by"]
                lines.append(f"S.move({box!r}, {int(dx)}, {int(dy)}, {int(dz)})")
            elif op == "stack":
                dx, dy, dz = o["by"]
                lines.append(f"S.stack({box!r}, {int(dx)}, {int(dy)}, {int(dz)}, count={int(o.get('count', 1))})")
            elif op == "transform":
                lines.append(f"S.transform({box!r}, rotate={int(o.get('rotate', 0))}, mirror={o.get('mirror')!r})")
            elif op == "mark":
                lines.append(f"S.mark({o['name']!r}, {tuple(o['pos'])!r}, {o.get('kind', 'point')!r}, "
                             f"yaw={float(o.get('yaw', 0))}, pitch={float(o.get('pitch', 0))})")
            else:
                return f"Error: unknown op '{op}'"
        res = _project().execute("\n".join(lines), "edit", save_step=True)
        return _fmt(res)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def steps(action: str = "list", n: int = 0, code: str = "") -> str:
    """Manage pipeline steps: action list | show (n) | edit (n, code; then call rebuild) | delete (n)."""
    try:
        p = _project()
        if action == "list":
            return "\n".join(f"{st['n']}. {st['label']} ({st['file']})" for st in p.meta["steps"]) or "no steps yet"
        if action == "show":
            return p.step_code(n)
        if action == "edit":
            p.replace_step(n, code)
            return f"step {n} updated — call rebuild() to apply"
        if action == "delete":
            p.delete_step(n)
            return f"step {n} deleted — call rebuild() to apply"
        return "Error: action must be list|show|edit|delete"
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def rebuild(upto: int = 0) -> str:
    """Rebuild the scene from scratch by replaying the pipeline (after editing/deleting steps).
    upto: stop after this step (0 = all)."""
    try:
        return _fmt(_project().rebuild(upto or None))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def history(action: str = "list", count: int = 1) -> str:
    """Undo history: action list | undo (count = how many changes to revert)."""
    try:
        p = _project()
        if action == "list":
            return "\n".join(f"{i + 1}. {lbl}" for i, lbl in enumerate(p.history())) or "empty"
        if action == "undo":
            label = p.undo(count)
            return f"Reverted to the state before '{label}'."
        return "Error: action must be list|undo"
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ====================================================================== seeing
@server.tool()
def render(view: str = "sheet", direction: str = "se", time_of_day: str = "day", width: int = 1280, height: int = 800,
           region: list[int] | None = None, eye: list[float] | None = None, target: list[float] | None = None,
           marker: str | None = None, pos: list[float] | None = None, yaw: float | None = None, pitch: float = 0.0,
           fov: float = 70.0, y: int | None = None, highlight: list[int] | None = None, supersample: int = 1):
    """Render the scene with real Minecraft models/textures and return the image.

    view: iso (direction se|sw|ne|nw) | top (map + coordinate grid + markers) | section (y=cut height, floor
    plan + block legend) | elev (direction north|south|east|west) | persp (eye, target) | player (marker or pos
    + yaw/pitch: exactly what a player sees) | orbit (4 views) | sheet (overview: iso se/nw, top, spawn view).
    time_of_day: day | sunset | night (night shows real block light — check lighting!).
    region: [x1,y1,z1,x2,y2,z2] to render part of the scene. highlight: box to tint magenta.
    supersample: 2 for smoother final images.
    """
    try:
        from buildmcp.geo.box import Box
        from buildmcp.render.api import render_view

        p = _project()
        img = render_view(p.scene, view, direction=direction, time=time_of_day, width=width, height=height,
                          region=tuple(region) if region else None, eye=eye, target=target, pos=pos, yaw=yaw,
                          pitch=pitch, marker=marker, fov=fov, y=y, ss=max(1, min(3, supersample)),
                          highlight=Box.of(highlight) if highlight else None)
        path = _save_render(img, view)
        return [f"{view} {img.size[0]}x{img.size[1]} saved: {path}", Image(data=_png(img), format="png")]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def inspect(what: str = "stats", region: list[int] | None = None, pos: list[int] | None = None, y: int | None = None,
            start: str = "spawn") -> str:
    """Text analysis of the scene.

    what: stats (block counts, size) | lint (quality/correctness issues with coordinates) |
    walk (can players walk from the 'spawn' marker to every npc/portal/warp marker) |
    layer (y=..., ASCII map of one layer) | column (pos=[x,z]) | blocks (region: list non-air blocks,
    small regions only) | markers | entities | theme (current theme palettes).
    """
    try:
        p = _project()
        S = p.scene
        reg = tuple(region) if region else None
        if what == "stats":
            return _fmt(S.stats(reg))
        if what == "lint":
            from buildmcp.analyze.lint import format_issues, lint

            return format_issues(lint(S, reg))
        if what == "walk":
            from buildmcp.analyze.walk import reachability

            return _fmt(reachability(S, start))
        if what == "markers":
            return _fmt({n: vars(m) for n, m in S.markers.items()})
        if what == "entities":
            return _fmt([{"id": e.id, "pos": e.pos} for e in S.entities][:200])
        if what == "theme":
            from buildmcp import themes

            return themes.get(p.theme).describe()
        if what == "column":
            x, z = int(pos[0]), int(pos[-1])
            b = S.bbox()
            out = []
            for yy in range(b.y2, b.y1 - 1, -1):
                st = S.get(x, yy, z)
                if st != "minecraft:air":
                    out.append(f"y={yy}: {st.removeprefix('minecraft:')}")
            return "\n".join(out) or "empty column"
        if what == "layer":
            return _layer_ascii(S, y, reg)
        if what == "blocks":
            from buildmcp.geo.box import Box

            b = Box.of(reg) if reg else S.bbox()
            if b.volume > 4096:
                return "Error: region too large for a block list (max 4096 cells); use layer/section render"
            out = []
            for yy in range(b.y1, b.y2 + 1):
                for zz in range(b.z1, b.z2 + 1):
                    for xx in range(b.x1, b.x2 + 1):
                        st = S.get(xx, yy, zz)
                        if st != "minecraft:air":
                            out.append(f"{xx},{yy},{zz} {st.removeprefix('minecraft:')}")
            return "\n".join(out) or "all air"
        return "Error: what must be stats|lint|walk|layer|column|blocks|markers|entities|theme"
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _layer_ascii(S, y, region) -> str:
    from buildmcp.geo.box import Box

    b = Box.of(region) if region else S.bbox()
    if y is None:
        return "Error: layer needs y"
    if b.size[0] > 120 or b.size[2] > 120:
        return "Error: layer region too big for ASCII (max 120x120) — use render(view='section', y=...)"
    ids = S.ids(Box(b.x1, y, b.z1, b.x2, y, b.z2))[:, 0, :]
    legend: dict[int, str] = {}
    chars = "#@%&*+=o0x$ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwyz123456789"
    for i in sorted(set(ids.ravel().tolist())):
        if i == 0:
            continue
        legend[i] = chars[len(legend) % len(chars)]
    rows = []
    for zz in range(ids.shape[1]):
        rows.append("".join(legend.get(int(ids[xx, zz]), ".") for xx in range(ids.shape[0])))
    leg = "\n".join(f"{c} = {S.palette[i].removeprefix('minecraft:')}" for i, c in legend.items())
    return f"layer y={y}, x {b.x1}..{b.x2} (left->right), z {b.z1}..{b.z2} (top->bottom = north->south)\n" + \
        "\n".join(rows) + "\n\n" + leg


# ====================================================================== knowledge
@server.tool()
def blocks(query: str, limit: int = 40) -> str:
    """Search valid block names for the project's Minecraft version (words must all match)."""
    try:
        from buildmcp.blocks.registry import get_registry

        reg = get_registry(STATE.project.version if STATE.project else None)
        res = reg.search(query, limit)
        return "\n".join(f"{b.name}  (since {b.since})" + (f" props: {', '.join(b.prop_names)}" if b.props else "")
                         for b in res) or "no matches"
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def block_info(block: str) -> str:
    """Properties, defaults, light level, since-version and texture colors of a block."""
    try:
        from buildmcp.blocks import families as F
        from buildmcp.blocks.registry import get_registry

        reg = get_registry(STATE.project.version if STATE.project else None)
        info = reg.info(block)
        fam = F.family(reg, info.name)
        out = {
            "name": info.name, "since": info.since, "properties": {p: list(v) for p, v in info.props},
            "default": info.default_props(), "light": info.light, "transparent": info.transparent,
            "full_cube": reg.is_full_cube(info.name), "kind": F.KIND_NAMES.get(F.kind_of(reg, info.name)),
            "family": {k: v for k, v in vars(fam).items() if v and k != "extra"},
        }
        try:
            from buildmcp.paint.colors import block_colors

            c = block_colors(reg.version).get(info.name)
            if c:
                out["color"] = {"top": c["top"], "side": c["side"]}
        except Exception:  # noqa: BLE001
            pass
        return _fmt(out)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def palette(action: str, a: str = "", b: str = "", steps: int = 6, color: list[int] | None = None,
            sets: str = "all", k: int = 8) -> str:
    """Block color tools (colors measured from the real textures).

    action: gradient (a -> b in `steps` blocks) | similar (blocks close to a) | nearest (color=[r,g,b]) |
    theme (describe theme a or the project theme) | themes (list). sets: all | concrete+wool+terracotta |
    stone | wood | natural | glazed.
    """
    try:
        from buildmcp import themes
        from buildmcp.paint import colors

        v = STATE.project.version if STATE.project else None
        from buildmcp.blocks.registry import resolve_version

        v = resolve_version(v)
        if action == "gradient":
            return " -> ".join(colors.gradient_between(v, a, b, steps, sets))
        if action == "similar":
            return "\n".join(f"{n} (ΔE {d})" for n, d in colors.similar(v, a, k, sets))
        if action == "nearest":
            return ", ".join(colors.nearest(v, color or [128, 128, 128], sets, k=k))
        if action == "theme":
            return themes.get(a or (STATE.project.theme if STATE.project else "fantasy_medieval")).describe()
        if action == "themes":
            return "\n".join(f"{n}: {themes.get(n).title} — {themes.get(n).notes}" for n in themes.names())
        return "Error: action must be gradient|similar|nearest|theme|themes"
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def api_docs(topic: str = "index") -> str:
    """Reference for the scripting API. Start with topic='index'; then e.g. 'trees', 'arch', 'scene',
    'palette', 'terrain', 'sdf', 'patterns', 'workflow', 'themes'."""
    try:
        from buildmcp import docs

        return docs.topic(topic)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def markers(action: str = "list", name: str = "", pos: list[float] | None = None, kind: str = "point",
            yaw: float = 0.0, pitch: float = 0.0) -> str:
    """Named points: action list | set (name, pos, kind, yaw) | remove (name).
    kind: spawn | npc | portal | hologram | viewpoint | warp | anchor | point. Yaw: 0 south, 90 west,
    180 north, 270 east. 'spawn' is where players appear; 'anchor' (else 'spawn') is the paste anchor."""
    try:
        S = _project().scene
        if action == "list":
            return _fmt({n: vars(m) for n, m in S.markers.items()}) if S.markers else "no markers"
        if action == "set":
            S.mark(name, pos, kind, yaw=yaw, pitch=pitch)
            _project().save()
            return f"marker '{name}' set"
        if action == "remove":
            S.markers.pop(name, None)
            _project().save()
            return f"marker '{name}' removed"
        return "Error: action must be list|set|remove"
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ====================================================================== in/out
@server.tool()
def import_asset(path: str, kind: str = "auto", at: list[int] | None = None, rotate: int = 0, mirror: str | None = None,
                 air: bool = False, width: int | None = None, height: int | None = None, facing: str = "south",
                 flat: bool = False, blocks_set: str = "concrete+wool+terracotta") -> str:
    """Bring files into the scene (as a pipeline step).

    kind: auto | schem (.schem/.schematic) | nbt (vanilla structure) | litematic | image (pixel art; width/height,
    facing, flat) | heightmap (grayscale image -> terrain; height = max height) | model (.obj/.glb/.stl; height).
    at: where the min corner / bottom-center goes (structures default to their saved position).
    """
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"Error: file not found: {p}"
        ext = p.suffix.lower()
        if kind == "auto":
            kind = {".schem": "schem", ".schematic": "schem", ".nbt": "nbt", ".litematic": "litematic",
                    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".obj": "model",
                    ".glb": "model", ".gltf": "model", ".stl": "model", ".ply": "model"}.get(ext, "")
        spath = str(p).replace("\\", "/")
        if kind in ("schem", "nbt", "litematic"):
            code = (f"from buildmcp.io.other_formats import read_any\nfrom buildmcp.io.structure_data import to_scene\n"
                    f"_sd = read_any({spath!r})\n_box, _w = to_scene(_sd, S, at={tuple(at) if at else None!r}, "
                    f"rotate={int(rotate)}, mirror={mirror!r}, air={bool(air)})\nprint('placed', _box, _w[:10])")
        elif kind == "image":
            code = (f"image.pixel_art({spath!r}, {tuple(at or (0, 64, 0))!r}, width={width!r}, height={height!r}, "
                    f"facing={facing!r}, flat={bool(flat)}, blocks={blocks_set!r})")
        elif kind == "heightmap":
            code = f"image.heightmap({spath!r}, {tuple(at or (0, 64, 0))!r}, width={width!r}, max_height={height or 32})"
        elif kind == "model":
            code = (f"model.place_model({spath!r}, {tuple(at or (0, 64, 0))!r}, {int(height or 20)}, "
                    f"rotate_y={float(rotate) * 90.0}, blocks={blocks_set!r})")
        else:
            return "Error: unknown kind; use schem|nbt|litematic|image|heightmap|model"
        return _fmt(_project().execute(code, f"import {p.name}", save_step=True))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def export(format: str = "schem", name: str = "", region: list[int] | None = None, anchor: list[int] | None = None,
           finalize_blocks: bool = True) -> str:
    """Export the build for the server.

    format: schem (Sponge v3: WorldEdit 7.3+/FAWE) | schem_v2 (older WorldEdit) | nbt (vanilla structure).
    anchor: world point that lands at your feet on //paste (default: 'anchor' marker, else 'spawn', else the
    bottom center). finalize_blocks runs game-like block updates first (fences, stairs corners, leaves...).
    """
    try:
        from buildmcp.blocks.finalize import finalize
        from buildmcp.io.other_formats import write_structure
        from buildmcp.io.schem import write_schem
        from buildmcp.io.structure_data import from_scene

        p = _project()
        if finalize_blocks:
            changes = finalize(p.scene, tuple(region) if region else None)
            p.save()
        else:
            changes = {}
        sd = from_scene(p.scene, tuple(region) if region else None, tuple(anchor) if anchor else None)
        fname = (name or p.meta["slug"])
        if format in ("schem", "schem_v3", "schem_v2"):
            path = write_schem(sd, p.exports_dir / f"{fname}.schem", version=2 if format == "schem_v2" else 3,
                               name=fname)
            howto = (f"Copy {path.name} to plugins/WorldEdit/schematics/ (or plugins/FastAsyncWorldEdit/schematics/). "
                     f"In game stand where the anchor {sd.origin} should be, then: //schem load {fname}  and  //paste -a -e -b "
                     f"(-a skips air, -e entities, -b biomes). Or use server_paste to let me do it.")
        elif format == "nbt":
            path = write_structure(sd, p.exports_dir / f"{fname}.nbt")
            howto = "Put it in <world>/datapacks/<pack>/data/<ns>/structure/ and /place template <ns>:<name>."
        else:
            return "Error: format must be schem|schem_v2|nbt"
        return _fmt({"file": str(path), "size": sd.size, "anchor": sd.origin, "min": sd.min,
                     "blocks": int((sd.data != 0).sum()), "block_entities": len(sd.block_entities),
                     "entities": len(sd.entities), "data_version": sd.data_version, "finalize": changes,
                     "how_to_paste": howto})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ====================================================================== setup
@server.tool()
def setup_check() -> str:
    """Diagnostics: versions, folders, renderer assets/JIT status, server connection settings."""
    import platform
    import sys

    from buildmcp.project import builds_dir
    from buildmcp.render.assets import data_dir

    info = {
        "buildmcp": __version__, "python": sys.version.split()[0], "platform": platform.platform(),
        "builds_dir": str(builds_dir()), "data_dir": str(data_dir()),
        "mc_version_setting": os.environ.get("BUILDMCP_MC_VERSION", "auto"),
        "renderer": STATE.warm,
        "project": STATE.project.name if STATE.project else None,
    }
    try:
        import numba

        info["numba"] = numba.__version__
    except Exception as e:  # noqa: BLE001
        info["numba"] = f"missing: {e}"
    assets = sorted(p.name for p in (data_dir() / "assets").glob("*") if (p / ".complete").exists()) \
        if (data_dir() / "assets").exists() else []
    info["assets_downloaded"] = assets
    return _fmt(info)


def _warmup() -> None:
    try:
        from buildmcp.render.api import warmup

        STATE.warm["seconds"] = round(warmup(), 1)
        STATE.warm["done"] = True
    except Exception as e:  # noqa: BLE001 - renderer problems are reported by setup_check/render
        STATE.warm["error"] = str(e)


@server.tool()
def ping() -> str:
    """Health check: returns the BuildMCP version."""
    return f"buildmcp {__version__} ok"


def main() -> None:
    if os.environ.get("BUILDMCP_NO_WARMUP") != "1":
        threading.Thread(target=_warmup, daemon=True).start()
    try:
        from buildmcp import server_tools  # noqa: F401 - registers server_* tools
    except ImportError:
        pass
    server.run()


if __name__ == "__main__":
    from buildmcp.mcp_server import main as _main  # run the package module so server_tools registers on it

    _main()
