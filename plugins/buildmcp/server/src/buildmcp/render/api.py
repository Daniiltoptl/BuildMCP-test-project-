"""One entry point for all views: ``render_view(scene, view=..., ...) -> PIL.Image``.

Views
  iso      orthographic 3/4 view from se|sw|ne|nw (default se)
  top      map straight down with coordinate grid and markers (north is up)
  section  top-down cut at height ``y`` (floor plan) with a block legend
  elev     orthographic facade from north|south|east|west
  persp    perspective camera: ``eye`` -> ``target``
  player   what a player sees: from ``marker`` (or ``pos``) with ``yaw``/``pitch``
  orbit    4 perspective views around the build (contact sheet)
  sheet    overview contact sheet: iso se, iso nw, top map, player view from 'spawn'
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from ..geo.box import Box
from ..geo.mask import as_mask
from .views import (
    Renderer, average_colors, elevation_camera, iso_camera, legend, overlay_grid_top, overlay_markers,
    perspective, player_camera, sheet, top_camera,
)

VIEWS = ("iso", "top", "section", "elev", "persp", "player", "orbit", "sheet")
STUDIO_BG = (0.60, 0.66, 0.73)
MAP_BG = (0.10, 0.11, 0.13)

_renderers: dict[int, Renderer] = {}


def renderer_for(scene) -> Renderer:
    r = _renderers.get(id(scene))
    if r is None or r.scene is not scene:
        r = Renderer(scene)
        _renderers.pop(id(scene), None)
        _renderers[id(scene)] = r
        while len(_renderers) > 4:  # a renderer keeps its scene alive: only the recent ones
            _renderers.pop(next(iter(_renderers)))
    return r


def _region(scene, region) -> Box:
    if region is not None:
        b = as_mask(region).bbox
        if b is None:
            raise ValueError("region is empty")
        return b
    b = scene.bbox()
    for e in scene.entities:
        p = Box.of([int(math.floor(c)) for c in e.pos])
        b = p if b is None else b.union(p)
    if b is None:
        raise ValueError("scene is empty — nothing to render")
    return b


def _marker_pos(scene, marker: str):
    m = scene.markers.get(marker)
    if m is None:
        raise ValueError(f"no marker named '{marker}' (markers: {', '.join(scene.markers) or 'none'})")
    return m


def _free_eye(scene, p, eye_height: float = 1.62):
    """Lift a camera position out of solid blocks (so a player view never starts underground)."""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    for _ in range(64):
        cell = scene.get(int(math.floor(x)), int(math.floor(y + eye_height)), int(math.floor(z)))
        if scene.reg.is_full_cube(cell.split("{", 1)[0]) and not cell.endswith("_leaves") and "glass" not in cell:
            y += 1.0
            continue
        break
    return (x, y, z)


def warmup(version: str | None = None) -> float:
    """Compile (or load from cache) the render kernels on a tiny scene. Returns seconds taken."""
    import time

    from ..scene import Scene

    t = time.time()
    s = Scene(version)
    s.fill((0, 0, 0, 2, 0, 2), "grass_block")
    s.set(1, 1, 1, "oak_stairs")
    s.set(1, 1, 0, "water")
    s.add_entity("text_display", (1.5, 2.5, 1.5), {"text": '"hi"', "billboard": "center"})
    render_view(s, "iso", width=24, height=16)
    render_view(s, "persp", width=24, height=16)
    return time.time() - t


def render_view(scene, view: str = "iso", *, direction: str = "se", time: str = "day", width: int = 1280,
                height: int = 800, region=None, eye=None, target=None, pos=None, yaw: float | None = None,
                pitch: float = 0.0, marker: str | None = None, fov: float = 70.0, y: int | None = None,
                ss: int = 1, grid: bool = True, show_markers: bool = True, highlight=None,
                elevation: float = 32.0) -> Image.Image:
    view = view.lower()
    if view not in VIEWS:
        raise ValueError(f"unknown view '{view}'. Views: {', '.join(VIEWS)}")
    r = renderer_for(scene)
    box = _region(scene, region)
    reg_box = box if region is not None else None
    hl = as_mask(highlight) if highlight is not None else None
    markers = list(scene.markers.values()) if show_markers else []

    if view == "iso":
        cam = iso_camera(box, direction, elevation, width, height)
        img, depth = r.render(cam, width, height, time, ss, reg_box, highlight=hl, background=STUDIO_BG
                              if time == "day" else None)
        return overlay_markers(img, cam, markers) if markers else img
    if view == "top":
        cam = top_camera(box, width, height)
        img, _ = r.render(cam, width, height, time, ss, reg_box, highlight=hl, background=MAP_BG)
        if grid:
            img = overlay_grid_top(img, cam, box)
        return overlay_markers(img, cam, markers) if markers else img
    if view == "section":
        if y is None:
            raise ValueError("section view needs y=<height of the cut>")
        cut = Box(box.x1, box.y1, box.z1, box.x2, min(box.y2, y), box.z2)
        cam = top_camera(cut, width, height)
        img, _ = r.render(cam, width, height, "day", ss, reg_box, y_cut=y, highlight=hl, background=MAP_BG)
        if grid:
            img = overlay_grid_top(img, cam, cut)
        layer = scene.ids(Box(box.x1, y, box.z1, box.x2, y, box.z2))
        ids, counts = np.unique(layer[layer != 0], return_counts=True)
        cols = average_colors(r)
        order = np.argsort(-counts)[:24]
        items = [(scene.palette[ids[i]].removeprefix("minecraft:"), cols.get(int(ids[i]), (128, 128, 128)),
                  int(counts[i])) for i in order]
        return legend(img, items, f"layer y={y}")
    if view == "elev":
        side = direction if direction in ("north", "south", "east", "west") else "south"
        cam = elevation_camera(box, side, width, height)
        img, _ = r.render(cam, width, height, time, ss, reg_box, highlight=hl, background=STUDIO_BG
                          if time == "day" else None)
        return img
    if view == "persp":
        if eye is None or target is None:
            c = np.array(box.center)
            size = max(box.size)
            eye = c + np.array([size * 0.9, size * 0.55, size * 0.9]) if eye is None else eye
            target = c if target is None else target
        cam = perspective(eye, target, fov)
        img, _ = r.render(cam, width, height, time, ss, reg_box, highlight=hl)
        return overlay_markers(img, cam, markers) if markers else img
    if view == "player":
        if marker is not None:
            m = _marker_pos(scene, marker)
            p = m.pos
            yaw_v = m.yaw if yaw is None else yaw
            pitch_v = m.pitch if pitch == 0.0 else pitch
        else:
            if pos is None:
                if "spawn" in scene.markers:
                    m = scene.markers["spawn"]
                    p, yaw_v, pitch_v = m.pos, m.yaw if yaw is None else yaw, m.pitch if pitch == 0.0 else pitch
                else:
                    raise ValueError("player view needs marker=, pos= or a 'spawn' marker")
            else:
                p, yaw_v, pitch_v = pos, (yaw or 0.0), pitch
        p = _free_eye(scene, (p[0] + 0.5 if float(p[0]).is_integer() else p[0], p[1],
                              p[2] + 0.5 if float(p[2]).is_integer() else p[2]))
        cam = player_camera(p, yaw_v, pitch_v, fov)
        img, _ = r.render(cam, width, height, time, ss, reg_box, highlight=hl)
        return img
    if view == "orbit":
        c = np.array(box.center)
        size = max(box.size)
        shots = []
        for name, (sx, sz) in (("SE", (1, 1)), ("SW", (-1, 1)), ("NW", (-1, -1)), ("NE", (1, -1))):
            e = c + np.array([sx * size * 0.75, size * 0.5, sz * size * 0.75])
            cam = perspective(e, c, fov)
            img, _ = r.render(cam, width // 2, height // 2, time, ss, reg_box, highlight=hl)
            shots.append((name, img))
        return sheet(shots, cols=2)
    # sheet
    w2, h2 = width // 2, height // 2
    shots = [("iso SE", render_view(scene, "iso", direction="se", width=w2, height=h2, region=region, time=time)),
             ("iso NW", render_view(scene, "iso", direction="nw", width=w2, height=h2, region=region, time=time)),
             ("top", render_view(scene, "top", width=w2, height=h2, region=region))]
    if "spawn" in scene.markers:
        shots.append(("from spawn", render_view(scene, "player", marker="spawn", width=w2, height=h2, time=time)))
    else:
        shots.append(("night", render_view(scene, "iso", direction="se", width=w2, height=h2, region=region,
                                           time="night")))
    return sheet(shots, cols=2)


def save(img: Image.Image, path) -> str:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    return str(p)
