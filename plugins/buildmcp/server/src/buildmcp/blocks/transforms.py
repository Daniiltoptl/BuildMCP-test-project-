"""Rotate and mirror block states (property-aware, like the game's Rotation/Mirror).

Conventions (x = east, z = south, viewed from above):
- ``rotate_state(s, turns)``: ``turns`` quarter turns clockwise (north -> east -> south -> west).
  Positions transform as (x, z) -> (-z, x) per turn.
- ``mirror_state(s, "x")`` flips the x axis (east <-> west); ``"z"`` flips z (north <-> south).
"""

from __future__ import annotations

import functools

from .registry import format_state, parse_state

H_DIRS = ["north", "east", "south", "west"]
_CONN = ("north", "east", "south", "west")


def rotate_dir(d: str, turns: int) -> str:
    if d not in H_DIRS:
        return d
    return H_DIRS[(H_DIRS.index(d) + turns) % 4]


def mirror_dir(d: str, axis: str) -> str:
    if axis == "x":
        return {"east": "west", "west": "east"}.get(d, d)
    return {"north": "south", "south": "north"}.get(d, d)


def _map_rail(shape: str, fn) -> str:
    if shape.startswith("ascending_"):
        return "ascending_" + fn(shape.removeprefix("ascending_"))
    parts = shape.split("_")
    if len(parts) == 2 and all(p in H_DIRS for p in parts):
        a, b = fn(parts[0]), fn(parts[1])
        # Canonical rail names: north_south, east_west, and corners "south_east", "south_west", "north_west", "north_east"
        pair = {a, b}
        if pair == {"north", "south"}:
            return "north_south"
        if pair == {"east", "west"}:
            return "east_west"
        ns = "north" if "north" in pair else "south"
        ew = "east" if "east" in pair else "west"
        return f"{ns}_{ew}"
    return shape


def _map_orientation(o: str, fn) -> str:
    # jigsaw / crafter: "<front>_<top>", e.g. "down_east", "north_up"
    parts = o.split("_")
    if len(parts) == 2:
        return f"{fn(parts[0])}_{fn(parts[1])}"
    return o


def _transform_props(name: str, props: dict[str, str], dir_fn, *, turns: int = 0, mirror: str | None = None) -> dict[str, str]:
    out = dict(props)
    for key in ("facing", "horizontal_facing"):
        if key in out:
            out[key] = dir_fn(out[key])
    if "axis" in out and turns % 2 == 1:
        out["axis"] = {"x": "z", "z": "x"}.get(out["axis"], out["axis"])
    if "rotation" in out:
        r = int(out["rotation"])
        if mirror == "x":
            r = (16 - r) % 16
        elif mirror == "z":
            r = (8 - r) % 16
        else:
            r = (r + 4 * turns) % 16
        out["rotation"] = str(r)
    if any(k in out for k in _CONN):
        old = {k: props[k] for k in _CONN if k in props}
        for k, v in old.items():
            out[dir_fn(k)] = v
    if "orientation" in out:
        out["orientation"] = _map_orientation(out["orientation"], dir_fn)
    if "shape" in out:
        s = out["shape"]
        if name.endswith("rail"):
            out["shape"] = _map_rail(s, dir_fn)
        elif mirror and ("left" in s or "right" in s):
            out["shape"] = s.replace("left", "@").replace("right", "left").replace("@", "right")
    if mirror:
        if out.get("hinge") in ("left", "right"):
            out["hinge"] = "right" if out["hinge"] == "left" else "left"
        if out.get("type") in ("left", "right"):
            out["type"] = "right" if out["type"] == "left" else "left"
    return out


@functools.lru_cache(maxsize=65536)
def rotate_state(state: str, turns: int) -> str:
    turns %= 4
    if turns == 0:
        return state
    name, props, nbt = parse_state(state)
    if not props:
        return state
    new = _transform_props(name, props, lambda d: rotate_dir(d, turns), turns=turns)
    return format_state(name, new, tuple(props.keys())) + (nbt or "")


@functools.lru_cache(maxsize=65536)
def mirror_state(state: str, axis: str) -> str:
    if axis not in ("x", "z"):
        raise ValueError("mirror axis must be 'x' or 'z'")
    name, props, nbt = parse_state(state)
    if not props:
        return state
    new = _transform_props(name, props, lambda d: mirror_dir(d, axis), mirror=axis)
    return format_state(name, new, tuple(props.keys())) + (nbt or "")


def rotate_xz(x, z, turns: int):
    """Rotate coordinates (numpy arrays or ints) ``turns`` quarter turns clockwise around the origin."""
    turns %= 4
    for _ in range(turns):
        x, z = -z, x
    return x, z


def rotate_yaw(yaw: float, turns: int) -> float:
    """Entity yaw (0 = south, 90 = west) after rotating the structure clockwise."""
    return (yaw + 90.0 * turns) % 360.0


def mirror_yaw(yaw: float, axis: str) -> float:
    return (-yaw) % 360.0 if axis == "x" else (180.0 - yaw) % 360.0
