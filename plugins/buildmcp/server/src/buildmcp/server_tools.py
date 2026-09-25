"""MCP tools that talk to the live Minecraft server (BuildBridge plugin, or RCON as a fallback)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from pathlib import Path

from buildmcp.mcp_server import STATE, _err, _fmt, server


def _conn(method: str = "auto"):
    from buildmcp.live.connector import connect

    hint = STATE.project.version if STATE.project else None
    return connect(method, version_hint=hint)


def _record(conn):
    """Deploy record of the open project on this server (or None)."""
    if STATE.project is None:
        return None
    from buildmcp.live.deploy import load_record

    return load_record(STATE.project, conn.key)


def _progress_line(j: dict) -> str:
    total = j.get("total") or 0
    return f"{j.get('phase')}: {j.get('done', 0)}/{total}" if total else str(j.get("phase"))


# ====================================================================== status
@server.tool()
def server_status(method: str = "auto") -> str:
    """Check the server connection: bridge or RCON, Minecraft version, TPS, worlds, players, and where
    the open project was last pasted on this server. method: auto | bridge | rcon."""
    try:
        from buildmcp.live.connector import connect, load_settings

        conn = connect(method, version_hint=STATE.project.version if STATE.project else None, fresh=True)
        st = conn.status()
        out = {"connected_via": conn.describe(), "server": st}
        v = conn.version()
        out["minecraft_version_used"] = v
        if STATE.project is not None:
            pv = STATE.project.version
            out["project_version"] = pv
            if pv != v:
                out["note"] = (f"project targets {pv}, server is {v}: pastes are translated to {v} "
                               f"(renamed blocks converted, unknown ones skipped)")
            rec = _record(conn)
            if rec:
                out["last_paste"] = rec
        if conn.kind == "rcon":
            out["hint"] = ("RCON works, but BuildBridge gives 1:1 pastes without block updates, backups/undo, "
                           "world reading and player tracking. Run bridge_install.")
        out["settings"] = load_settings().public()
        return _fmt(out)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def server_player(name: str = "") -> str:
    """Where a player is (default: the first one online): position, look direction, the block they
    look at and their WorldEdit selection — also in scene coordinates when the open project is pasted
    on this server. Use it to place things "where I stand" or to read an area the player selected."""
    try:
        conn = _conn()
        p = conn.player(name)
        rec = _record(conn)
        if rec:
            from buildmcp.live.deploy import to_scene

            off = rec["offset"]
            p["scene_pos"] = [round(v, 2) for v in to_scene(p["pos"], off)]
            if "target" in p:
                p["scene_target"] = [int(v) for v in to_scene(p["target"], off)]
            if "selection" in p:
                s = p["selection"]
                p["scene_selection"] = [int(v) for v in to_scene(s[:3], off)] + [int(v) for v in to_scene(s[3:], off)]
            p["note"] = "scene_* = project coordinates (world - offset of the last paste)"
        return _fmt(p)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ======================================================================= paste
@server.tool()
def server_paste(at: str | list[float] = "last", world: str = "", region: list[int] | None = None,
                 finalize_blocks: bool = True, clear_removed: bool = True, backup: bool = True,
                 biomes: str = "auto", dry_run: bool = False, wait: bool = True, method: str = "auto",
                 timeout: float = 1200.0) -> str:
    """Paste the open project into the live world.

    at: where the project's anchor (marker 'anchor', else 'spawn', else bottom center) goes:
      "last" = same place as the previous paste on this server | "player" / "player:<name>" = at the
      player's feet (like //paste) | [x, y, z] world coordinates | "scene" = scene coordinates as-is.
    world: target world (bridge: world name, RCON: dimension id); default = the player's / last one.
    With BuildBridge the paste is exact (no physics or neighbour updates), backed up first (undo with
    server_undo), unchanged blocks are skipped and the previous paste's entities are replaced.
    clear_removed: blocks that the previous paste placed and the build no longer has become air.
    dry_run: only report the target box, block counts and warnings.
    """
    try:
        from buildmcp.blocks.finalize import finalize
        from buildmcp.live.deploy import (build_bundle, entity_tag_for, load_snapshot, save_record, scene_anchor,
                                          to_world)

        p = STATE.project
        if p is None:
            return "Error: open a project first"
        conn = _conn(method)
        rec = _record(conn)
        anchor = scene_anchor(p.scene)
        # where does it go?
        if isinstance(at, str) and at.strip().startswith("["):
            import json as _json

            at = _json.loads(at)
        if isinstance(at, (list, tuple)):
            if len(at) != 3:
                return "Error: at must be [x, y, z]"
            offset = [int(round(float(at[i]))) - anchor[i] for i in range(3)]
            wname = world or (rec or {}).get("world") or None
        elif at == "last":
            if not rec:
                return ("Error: this project was never pasted on this server. Use at='player' (stand where the "
                        "spawn point should be), at=[x,y,z] or at='scene'.")
            offset, wname = rec["offset"], world or rec.get("world")
        elif at == "scene":
            offset, wname = [0, 0, 0], world or (rec or {}).get("world") or None
        elif at.startswith("player"):
            name = at.split(":", 1)[1] if ":" in at else ""
            pl = conn.player(name)
            offset = [int(pl["block"][i]) - anchor[i] for i in range(3)]
            wname = world or pl.get("world")
        else:
            return "Error: at must be last | player | player:<name> | scene | [x, y, z]"
        if finalize_blocks:
            changes = finalize(p.scene, tuple(region) if region else None)
            if any(changes.values()):
                p.save()
        version = conn.version()
        prev = load_snapshot(p, conn.key) if clear_removed and rec and rec.get("offset") == list(offset) else None
        tag = entity_tag_for(p.meta["slug"])
        bundle, snap, info = build_bundle(p.scene, offset, version, world=wname, label=p.name, entity_tag=tag,
                                          backup=backup, region=tuple(region) if region else None, previous=prev,
                                          biomes={"auto": "auto", "true": True, "false": False}.get(str(biomes).lower(),
                                                                                                    "auto"))
        summary = {"method": conn.kind, "server": conn.describe(), "world": wname, "offset": list(offset),
                   "anchor_scene": list(anchor), "anchor_world": list(to_world(anchor, offset)),
                   "minecraft": version, **info}
        if dry_run:
            summary["dry_run"] = True
            summary["bundle_bytes"] = len(bundle.to_bytes())
            return _fmt(summary)
        t0 = time.time()
        res = conn.paste(bundle, wait=wait, timeout=timeout)
        summary["result"] = res
        summary["seconds"] = round(time.time() - t0, 1)
        ok = res.get("phase") == "done" if wait else res.get("phase") not in ("failed", "cancelled")
        if ok:
            save_record(p, conn.key, {"server": conn.describe(), "world": wname, "offset": list(offset),
                                      "anchor_world": list(to_world(anchor, offset)), "box": [info["world_min"],
                                                                                              info["world_max"]],
                                      "job": res.get("id"), "backup": res.get("backup"), "method": conn.kind,
                                      "entity_tag": tag}, snap)
        if not wait and conn.kind == "bridge":
            summary["next"] = f"job {res.get('id')} is running: server_job(job='{res.get('id')}')"
        if conn.kind == "rcon":
            summary["note"] = "pasted over RCON: no backup/undo. BuildBridge (bridge_install) is safer and exact."
        return _fmt(summary)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def server_job(job: str = "", action: str = "status") -> str:
    """BuildBridge jobs: action status (job id, default = latest) | list | cancel (job id) | backups."""
    try:
        conn = _conn()
        conn.need("jobs")
        c = conn.client
        if action == "list":
            return _fmt([{k: j.get(k) for k in ("id", "label", "phase", "done", "total", "error", "backup")}
                         for j in c.jobs()[-20:]])
        if action == "backups":
            return _fmt(c.backups())
        if not job:
            jobs = c.jobs()
            if not jobs:
                return "no jobs yet"
            job = jobs[-1]["id"]
        if action == "cancel":
            return _fmt(c.cancel(job))
        return _fmt(c.job(job))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def server_undo(backup: str = "last", wait: bool = True) -> str:
    """Undo a paste on the server: restores the blocks, block entities, entities and biomes that were
    there before (BuildBridge backups). backup: "last" or a backup id from server_job(action="backups")."""
    try:
        conn = _conn()
        conn.need("undo")
        job = conn.client.undo(backup)
        if not wait:
            return _fmt(job)
        res = conn.client.wait(job["id"])
        if res.get("phase") == "done" and STATE.project is not None:
            from buildmcp.live.deploy import _deploy_dir

            snap = _deploy_dir(STATE.project) / f"{conn.key}.npz"
            if snap.exists() and backup == "last":
                snap.unlink()  # the world no longer holds the last paste
        return _fmt(res)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ======================================================================== read
@server.tool()
def server_read(box: list[int], world: str = "", into_scene: bool = True, name: str = "", tiles: bool = True,
                entities: bool = True, at: list[int] | None = None) -> str:
    """Read a box of the live world [x1,y1,z1,x2,y2,z2] (world coordinates) — terrain to build on, an
    old spawn to rework, a player's build. Saved as a .schem in the project; into_scene adds a pipeline
    step that places it (at: scene position of the box min; default = world position minus the offset
    of the last paste, or the same coordinates)."""
    try:
        from buildmcp.io.schem import write_schem

        p = STATE.project
        if p is None:
            return "Error: open a project first"
        conn = _conn()
        conn.need("read")
        b = conn.client.region(box, world or None, tiles=tiles, entities=entities)
        sd = b.to_structure()
        imports = Path(p.root) / "imports"
        imports.mkdir(exist_ok=True)
        fname = name or f"world_{box[0]}_{box[1]}_{box[2]}"
        path = write_schem(sd, imports / f"{fname}.schem", version=3, name=fname)
        import numpy as np

        air_ids = [i for i, s in enumerate(sd.palette) if s == "minecraft:air"]
        info = {"file": str(path), "world_min": list(b.min), "size": list(b.size),
                "blocks": int((~np.isin(sd.data, air_ids)).sum()), "block_states": len(sd.palette),
                "block_entities": len(sd.block_entities), "entities": len(sd.entities)}
        if into_scene:
            rec = _record(conn)
            if at is None:
                off = rec["offset"] if rec else [0, 0, 0]
                at = [b.min[i] - off[i] for i in range(3)]
            spath = str(path).replace("\\", "/")
            code = (f"from buildmcp.io.other_formats import read_any\nfrom buildmcp.io.structure_data import to_scene\n"
                    f"_sd = read_any({spath!r})\n_box, _w = to_scene(_sd, S, at={tuple(int(v) for v in at)!r})\n"
                    f"print('placed', _box, _w[:10])")
            info["step"] = p.execute(code, f"import world {fname}", save_step=True)
        return _fmt(info)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def server_heightmap(rect: list[int], world: str = "") -> str:
    """Ground height of the live world in a rectangle [x1, z1, x2, z2] (leaves ignored) and the top block
    of each column. Returns a summary and a coarse grid; the full map is saved in the project
    (imports/heightmap_*.npz: heights, top palette/indices) for terrain scripts."""
    try:
        import numpy as np

        conn = _conn()
        conn.need("heightmap")
        hm = conn.client.heightmap(rect, world or None)
        w, l = hm["w"], hm["l"]
        heights = np.array(hm["heights"], dtype=np.int32).reshape(l, w).T  # (x, z)
        tops = np.array(hm["top"], dtype=np.int32).reshape(l, w).T
        pal = hm["top_palette"]
        out = {"x1": hm["x1"], "z1": hm["z1"], "size": [w, l], "min_y": int(heights.min()), "max_y": int(heights.max()),
               "mean_y": round(float(heights.mean()), 1)}
        counts = np.bincount(tops.ravel(), minlength=len(pal))
        out["top_blocks"] = {pal[i].removeprefix("minecraft:"): int(c) for i, c in
                             sorted(enumerate(counts), key=lambda t: -t[1])[:12] if c}
        step = max(1, int(np.ceil(max(w, l) / 24)))
        grid = heights[::step, ::step]
        out["grid_step"] = step
        out["grid"] = "\n".join(" ".join(f"{int(v):4d}" for v in grid[:, z]) for z in range(grid.shape[1]))
        if STATE.project is not None:
            d = Path(STATE.project.root) / "imports"
            d.mkdir(exist_ok=True)
            f = d / f"heightmap_{hm['x1']}_{hm['z1']}_{w}x{l}.npz"
            np.savez_compressed(f, heights=heights, tops=tops, palette=np.array(pal), origin=np.array([hm["x1"], hm["z1"]]))
            out["file"] = str(f)
        return _fmt(out)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# =================================================================== commands
@server.tool()
def server_tp(marker: str = "", pos: list[float] | None = None, player: str = "", yaw: float | None = None,
              pitch: float | None = None) -> str:
    """Teleport a player (default: the first online) to a project marker (e.g. a 'viewpoint' or 'spawn',
    with its look direction) or to scene coordinates pos=[x,y,z] — to show them the build in game.
    Needs a previous paste on this server to convert scene to world coordinates."""
    try:
        from buildmcp.live.deploy import to_world

        conn = _conn()
        rec = _record(conn)
        if rec is None:
            return "Error: the open project has not been pasted on this server yet (server_paste first)"
        if marker:
            mk = STATE.project.scene.markers.get(marker)
            if mk is None:
                return f"Error: no marker '{marker}' (markers: {', '.join(STATE.project.scene.markers) or 'none'})"
            spos, yaw = mk.pos, mk.yaw if yaw is None else yaw
            pitch = mk.pitch if pitch is None else pitch
        elif pos is not None:
            spos = pos
        else:
            return "Error: give marker or pos"
        wpos = to_world(spos, rec["offset"])
        return _fmt(conn.teleport(player, wpos, yaw, pitch, rec.get("world")))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def server_cmd(command: str, world: str = "") -> str:
    """Run a server console command and return its output, e.g. "setworldspawn 0 80 0",
    "rg define spawn", "gamerule doDaylightCycle false". world: run it in that world's dimension."""
    try:
        conn = _conn()
        out = conn.command(command.strip().removeprefix("/"), world or None)
        return "\n".join(out) if out else "(no output)"
    except Exception as e:  # noqa: BLE001
        return _err(e)


# ===================================================================== install
def _plugin_root() -> Path:
    env = os.environ.get("BUILDMCP_PLUGIN_ROOT", "").strip()
    if env and not env.startswith("${") and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parents[3]


def _find_jar(explicit: str = "") -> tuple[Path | None, str]:
    if explicit:
        p = Path(explicit).expanduser()
        return (p, "given path") if p.is_file() else (None, f"no file {p}")
    root = _plugin_root()
    built = sorted(glob.glob(str(root / "bridge" / "build" / "libs" / "BuildBridge-*.jar")))
    if built:
        return Path(built[-1]), "built from source"
    from buildmcp.render.assets import data_dir

    cached = sorted(glob.glob(str(data_dir() / "bridge" / "BuildBridge-*.jar")))
    if cached:
        return Path(cached[-1]), "downloaded earlier"
    # latest GitHub release of this repository
    try:
        import httpx

        r = httpx.get("https://api.github.com/repos/Daniiltoptl/BuildMCP-test-project-/releases", timeout=20,
                      follow_redirects=True)
        if r.status_code == 200:
            for rel in r.json():
                for a in rel.get("assets", []):
                    if a["name"].startswith("BuildBridge") and a["name"].endswith(".jar"):
                        dst = data_dir() / "bridge" / a["name"]
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        with httpx.stream("GET", a["browser_download_url"], timeout=60, follow_redirects=True) as s:
                            s.raise_for_status()
                            with open(dst, "wb") as f:
                                for chunk in s.iter_bytes():
                                    f.write(chunk)
                        return dst, f"GitHub release {rel.get('tag_name')}"
    except Exception:  # noqa: BLE001 - offline or rate limited: try building
        pass
    # build with the Gradle wrapper (needs a JDK 21+)
    bridge = root / "bridge"
    gradlew = bridge / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if gradlew.exists() and shutil.which("javac"):
        try:
            subprocess.run([str(gradlew), "--no-daemon", "-q", "jar"], cwd=bridge, check=True, timeout=900,
                           capture_output=True)
        except (subprocess.SubprocessError, OSError) as e:
            return None, f"gradle build failed: {e}"
        built = sorted(glob.glob(str(bridge / "build" / "libs" / "BuildBridge-*.jar")))
        if built:
            return Path(built[-1]), "built from source now"
    return None, ("no BuildBridge jar: no GitHub release reachable and no JDK 21 to build it "
                  "(install Temurin JDK 21 and run bridge_install again, or build plugins/buildmcp/bridge with gradlew jar)")


def _read_props(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text("utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def _read_bridge_config(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text("utf-8").splitlines():
            s = line.split("#", 1)[0].strip()
            for key in ("bind", "port", "token"):
                if s.startswith(key + ":"):
                    out[key] = s.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return out


@server.tool()
def bridge_install(server_dir: str = "", jar: str = "") -> str:
    """Install BuildBridge into a server on this PC and connect to it.

    server_dir: the server folder (with server.properties and plugins/); default = the configured one.
    Copies BuildBridge.jar into plugins/ (from a local build, a GitHub release, or builds it with Gradle),
    then — once the server has started with it — reads the token from plugins/BuildBridge/config.yml
    and RCON settings from server.properties, and saves them for BuildMCP.
    """
    try:
        from buildmcp.live.connector import forget, load_settings, save_settings

        sdir = Path(server_dir or load_settings().server_dir).expanduser() if (server_dir or load_settings().server_dir) else None
        if sdir is None or not sdir.is_dir():
            return "Error: give server_dir (the folder with server.properties and plugins/)"
        if not (sdir / "server.properties").exists() and not (sdir / "plugins").is_dir():
            return f"Error: {sdir} does not look like a server folder (no server.properties / plugins/)"
        report = {"server_dir": str(sdir)}
        plugins = sdir / "plugins"
        plugins.mkdir(exist_ok=True)
        existing = sorted(plugins.glob("BuildBridge*.jar"))
        src, how = _find_jar(jar)
        if src is not None:
            for old in existing:
                if old.name != src.name:
                    old.unlink()
            shutil.copy2(src, plugins / src.name)
            report["jar"] = f"{plugins / src.name} ({how})"
        elif existing:
            report["jar"] = f"{existing[-1]} (already installed; {how})"
        else:
            return "Error: " + how
        save_settings(server_dir=str(sdir))
        props = _read_props(sdir / "server.properties")
        if props.get("enable-rcon") == "true" and props.get("rcon.password"):
            save_settings(rcon_host="127.0.0.1", rcon_port=int(props.get("rcon.port", "25575") or 25575),
                          rcon_password=props["rcon.password"])
            report["rcon"] = "enabled on the server: saved as the fallback"
        cfg = _read_bridge_config(plugins / "BuildBridge" / "config.yml")
        if cfg.get("token"):
            host = cfg.get("bind", "127.0.0.1")
            host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
            save_settings(bridge_url=f"http://{host}:{cfg.get('port', '8765')}", bridge_token=cfg["token"])
            forget()
            report["token"] = "found in plugins/BuildBridge/config.yml and saved"
            try:
                conn = _conn("bridge")
                report["status"] = f"connected: {conn.describe()}, Minecraft {conn.version()}"
            except Exception as e:  # noqa: BLE001
                report["status"] = f"not reachable yet ({e}). Restart the server if it was running while installing."
        else:
            report["next"] = ("Restart the server (a full restart, not /reload) so BuildBridge creates its token, "
                              "then run bridge_install again (or server_status).")
        return _fmt(report)
    except Exception as e:  # noqa: BLE001
        return _err(e)
