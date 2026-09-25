"""Generate the compact block-state data shipped with BuildMCP.

Source: PrismarineJS/minecraft-data (MIT). For every supported Minecraft version we
store, per block: its properties (ordered, with allowed values), the default state,
and a few render/physics flags. Output goes to
plugins/buildmcp/server/src/buildmcp/data/blocks/.

Usage:  python tools/build_block_data.py
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data"
OUT = Path(__file__).resolve().parents[1] / "plugins/buildmcp/server/src/buildmcp/data/blocks"

# Versions with their own entry in minecraft-data's dataPaths (release versions only).
DATA_VERSIONS = [
    "1.21", "1.21.1", "1.21.3", "1.21.4", "1.21.5", "1.21.6", "1.21.8",
    "1.21.9", "1.21.10", "1.21.11", "26.1",
]
# Every release we accept as a target, including patch releases that share block data.
RELEASES = [
    "1.21", "1.21.1", "1.21.2", "1.21.3", "1.21.4", "1.21.5", "1.21.6", "1.21.7", "1.21.8",
    "1.21.9", "1.21.10", "1.21.11", "26.1", "26.1.1", "26.1.2", "26.2", "26.3",
]


def fetch_json(path: str):
    with urllib.request.urlopen(f"{RAW}/{path}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def decode_default(block: dict) -> list[int]:
    """Default state as value indices (minecraft-data: last property varies fastest)."""
    states = block.get("states") or []
    idx = block["defaultState"] - block["minStateId"]
    out = [0] * len(states)
    for i in range(len(states) - 1, -1, -1):
        n = states[i]["num_values"]
        out[i] = idx % n
        idx //= n
    return out


def prop_values(state: dict) -> list[str]:
    if state["type"] == "bool":
        return ["true", "false"]
    return [str(v) for v in state["values"]]


def compact(blocks: list[dict], collision: dict | None) -> dict:
    """{"blocks": {name: entry}, "shapes": {id: [[x1,y1,z1,x2,y2,z2], ...]}}.

    entry["c"] is the collision shape id shared by all states, or a list with one id per
    state index (minecraft-data order: last property varies fastest). Missing collision
    data falls back to a full cube / empty box from the boundingBox flag.
    """
    out = {}
    used: set[int] = set()
    cblocks = (collision or {}).get("blocks", {})
    for b in blocks:
        states = b.get("states") or []
        props = [[s["name"], prop_values(s)] for s in states]
        default = decode_default(b)
        out[b["name"]] = {
            "p": props,
            "d": [props[i][1][default[i]] for i in range(len(props))],
            "t": bool(b.get("transparent", False)),
            "l": int(b.get("emitLight", 0) or 0),
            "f": int(b.get("filterLight", 0) or 0),
            "b": 1 if b.get("boundingBox") == "block" else 0,
            "m": b.get("material", "default"),
        }
        c = cblocks.get(b["name"])
        if c is None:
            c = 1 if b.get("boundingBox") == "block" else 0
        if isinstance(c, list) and len(set(c)) == 1:
            c = c[0]
        out[b["name"]]["c"] = c
        used.update(c if isinstance(c, list) else [c])
    shapes = (collision or {}).get("shapes", {})
    table = {str(i): shapes.get(str(i), [[0, 0, 0, 1, 1, 1]] if i == 1 else []) for i in sorted(used)}
    table.setdefault("0", [])
    table.setdefault("1", [[0.0, 0.0, 0.0, 1.0, 1.0, 1.0]])
    return {"blocks": out, "shapes": table}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    data_paths = fetch_json("dataPaths.json")["pc"]
    protocol = fetch_json("pc/common/protocolVersions.json")
    data_version = {p["minecraftVersion"]: p.get("dataVersion") for p in protocol}

    folder_of: dict[str, str] = {}
    written: set[str] = set()
    for v in DATA_VERSIONS:
        folder = data_paths[v]["blocks"]  # e.g. "pc/1.21.1"
        name = folder.split("/", 1)[1]
        folder_of[v] = name
        if name in written:
            continue
        blocks = fetch_json(f"{folder}/blocks.json")
        cpath = data_paths[v].get("blockCollisionShapes")
        collision = fetch_json(f"{cpath}/blockCollisionShapes.json") if cpath else None
        payload = json.dumps(compact(blocks, collision), separators=(",", ":"), sort_keys=True).encode()
        (OUT / f"{name}.json.gz").write_bytes(gzip.compress(payload, 9, mtime=0))
        written.add(name)
        print(f"{v}: {len(blocks)} blocks -> {name}.json.gz", file=sys.stderr)

    def key(v: str):
        return tuple(int(x) for x in v.split("."))

    releases = {}
    for r in RELEASES:
        base = max((d for d in DATA_VERSIONS if key(d) <= key(r)), key=key)
        releases[r] = {"dataVersion": data_version[r], "blocks": folder_of[base]}

    # First supported version in which each block exists ("since").
    since: dict[str, str] = {}
    for v in DATA_VERSIONS:
        with gzip.open(OUT / f"{folder_of[v]}.json.gz", "rt", encoding="utf-8") as f:
            for n in json.load(f)["blocks"]:
                since.setdefault(n, v)
    index = {"source": "PrismarineJS/minecraft-data (MIT)", "releases": releases, "since": since}
    (OUT / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"releases: {', '.join(releases)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
