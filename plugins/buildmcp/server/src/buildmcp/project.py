"""Build projects on disk: scene, reproducible script pipeline, undo history, renders, exports.

    builds/<name>/project.json     metadata + step list
    builds/<name>/scene.bin        current scene
    builds/<name>/scripts/NN_*.py  pipeline steps (every change is code, so rebuild() replays it)
    builds/<name>/history/*.bin    undo snapshots
    builds/<name>/renders/, exports/
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from . import themes as themes_mod
from .blocks.registry import resolve_version
from .scene import Scene

MAX_HISTORY = 30


def builds_dir() -> Path:
    env = os.environ.get("BUILDMCP_BUILDS_DIR", "").strip()
    if env and not env.startswith("${"):
        p = Path(env).expanduser()
    else:
        p = Path.home() / "BuildMCP" / "builds"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip().lower(), flags=re.UNICODE).strip("_")
    return s or "project"


class Project:
    def __init__(self, root: Path, meta: dict, scene: Scene):
        self.root = root
        self.meta = meta
        self.scene = scene
        self._history: list[tuple[str, bytes]] = []
        self._load_history_index()

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, name: str, version: str | None = None, theme: str = "fantasy_medieval", description: str = "",
               seed: int = 0, base: Path | None = None) -> "Project":
        root = (base or builds_dir()) / _slug(name)
        if (root / "project.json").exists():
            raise FileExistsError(f"project '{name}' already exists — open it or pick another name")
        themes_mod.get(theme)  # validate
        v = resolve_version(version)
        meta = {"name": name, "slug": root.name, "version": v, "theme": themes_mod.get(theme).name,
                "description": description, "seed": int(seed), "created": time.time(), "updated": time.time(),
                "steps": []}
        for d in ("scripts", "history", "renders", "exports"):
            (root / d).mkdir(parents=True, exist_ok=True)
        p = cls(root, meta, Scene(v))
        p.save()
        return p

    @classmethod
    def open(cls, name: str, base: Path | None = None) -> "Project":
        root = (base or builds_dir()) / _slug(name)
        if not (root / "project.json").exists():
            raise FileNotFoundError(f"no project '{name}' in {root.parent}")
        meta = json.loads((root / "project.json").read_text("utf-8"))
        scene_file = root / "scene.bin"
        scene = Scene.load(scene_file) if scene_file.exists() else Scene(meta["version"])
        return cls(root, meta, scene)

    @staticmethod
    def list_all(base: Path | None = None) -> list[dict]:
        out = []
        for p in sorted((base or builds_dir()).glob("*/project.json")):
            try:
                m = json.loads(p.read_text("utf-8"))
                out.append({"name": m["name"], "version": m["version"], "theme": m["theme"],
                            "steps": len(m.get("steps", [])), "updated": m.get("updated")})
            except (OSError, json.JSONDecodeError, KeyError):
                continue
        return out

    def save(self) -> None:
        self.meta["updated"] = time.time()
        (self.root / "project.json").write_text(json.dumps(self.meta, indent=1, ensure_ascii=False), "utf-8")
        self.scene.save(self.root / "scene.bin")

    # ------------------------------------------------------------ properties
    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def version(self) -> str:
        return self.meta["version"]

    @property
    def theme(self) -> str:
        return self.meta["theme"]

    @property
    def seed(self) -> int:
        return int(self.meta.get("seed", 0))

    @property
    def renders_dir(self) -> Path:
        d = self.root / "renders"
        d.mkdir(exist_ok=True)
        return d

    @property
    def exports_dir(self) -> Path:
        d = self.root / "exports"
        d.mkdir(exist_ok=True)
        return d

    def set_theme(self, theme: str) -> None:
        self.meta["theme"] = themes_mod.get(theme).name
        self.save()

    # ------------------------------------------------------------ history
    def _load_history_index(self) -> None:
        hdir = self.root / "history"
        if not hdir.exists():
            return
        for f in sorted(hdir.glob("*.bin"))[-MAX_HISTORY:]:
            label = f.stem.split("_", 1)[1] if "_" in f.stem else f.stem
            self._history.append((label, f.read_bytes()))

    def checkpoint(self, label: str) -> None:
        blob = self.scene.to_bytes()
        self._history.append((label, blob))
        hdir = self.root / "history"
        hdir.mkdir(exist_ok=True)
        idx = int(time.time() * 1000)
        (hdir / f"{idx}_{_slug(label)[:40]}.bin").write_bytes(blob)
        files = sorted(hdir.glob("*.bin"))
        for f in files[:-MAX_HISTORY]:
            f.unlink(missing_ok=True)
        self._history = self._history[-MAX_HISTORY:]

    def history(self) -> list[str]:
        return [label for label, _ in self._history]

    def undo(self, steps: int = 1) -> str:
        """Restore the state before the last ``steps`` changes (pipeline steps they created are removed)."""
        if not self._history:
            raise ValueError("nothing to undo")
        steps = max(1, min(steps, len(self._history)))
        undone = self._history[-steps:]
        label, blob = undone[0]
        self.scene.restore(blob)
        self._history = self._history[:-steps]
        hdir = self.root / "history"
        for f in sorted(hdir.glob("*.bin"))[-steps:]:
            f.unlink(missing_ok=True)
        for lbl, _ in reversed(undone):
            m = re.match(r"#(\d+) ", lbl)
            if m and int(m.group(1)) == len(self.meta["steps"]):
                self.delete_step(int(m.group(1)))
        self.save()
        return label

    # ------------------------------------------------------------ pipeline
    def _step_path(self, n: int, label: str) -> Path:
        return self.root / "scripts" / f"{n:02d}_{_slug(label)[:40]}.py"

    def add_step(self, code: str, label: str) -> dict:
        n = len(self.meta["steps"]) + 1
        path = self._step_path(n, label or f"step{n}")
        path.parent.mkdir(exist_ok=True)
        path.write_text(code, "utf-8")
        st = {"n": n, "label": label or f"step{n}", "file": path.name}
        self.meta["steps"].append(st)
        return st

    def step_code(self, n: int) -> str:
        st = self.meta["steps"][n - 1]
        return (self.root / "scripts" / st["file"]).read_text("utf-8")

    def replace_step(self, n: int, code: str) -> None:
        st = self.meta["steps"][n - 1]
        (self.root / "scripts" / st["file"]).write_text(code, "utf-8")
        self.save()

    def delete_step(self, n: int) -> None:
        st = self.meta["steps"].pop(n - 1)
        (self.root / "scripts" / st["file"]).unlink(missing_ok=True)
        # renumber the rest
        for i, s in enumerate(self.meta["steps"], start=1):
            if s["n"] != i:
                old = self.root / "scripts" / s["file"]
                new = self._step_path(i, s["label"])
                if old.exists():
                    old.rename(new)
                s["n"] = i
                s["file"] = new.name
        self.save()

    def execute(self, code: str, label: str = "", *, save_step: bool = True, timeout: float = 180.0) -> dict:
        """Run build code against the scene (with undo checkpoint). Returns a result dict."""
        from . import scripting

        before_ids = self.scene.data.copy()
        before_origin = self.scene.origin.copy()
        before_ents = len(self.scene.entities)
        next_n = len(self.meta["steps"]) + 1
        self.checkpoint(f"#{next_n} {label or 'script'}" if save_step else (label or "edit"))
        out = io.StringIO()
        ns = scripting.namespace(self, out)
        t0 = time.time()
        ok, err = scripting.run(code, ns, timeout)
        dt = time.time() - t0
        if not ok:
            # roll back a failed script completely
            label_, blob = self._history.pop()
            self.scene.restore(blob)
            hdir = self.root / "history"
            files = sorted(hdir.glob("*.bin"))
            if files:
                files[-1].unlink(missing_ok=True)
            return {"ok": False, "error": err, "output": out.getvalue()[-4000:], "seconds": round(dt, 2)}
        changed = _count_changes(before_ids, before_origin, self.scene)
        step = self.add_step(code, label) if save_step else None
        self.save()
        return {"ok": True, "output": out.getvalue()[-4000:], "seconds": round(dt, 2), "changed": changed,
                "entities_added": len(self.scene.entities) - before_ents, "step": step["n"] if step else None,
                "bbox": self.scene.bbox().as_tuple() if self.scene.bbox() else None}

    def rebuild(self, upto: int | None = None, timeout: float = 600.0) -> dict:
        """Re-run the pipeline from an empty scene (after editing earlier steps)."""
        from . import scripting

        self.checkpoint("before rebuild")
        self.scene.restore(Scene(self.version).to_bytes())
        log = []
        steps = self.meta["steps"][: upto or len(self.meta["steps"])]
        for st in steps:
            out = io.StringIO()
            ns = scripting.namespace(self, out)
            ok, err = scripting.run(self.step_code(st["n"]), ns, timeout)
            log.append(f"step {st['n']} {st['label']}: {'ok' if ok else 'FAILED'}")
            if not ok:
                log.append(err)
                break
        self.save()
        return {"log": log, "bbox": self.scene.bbox().as_tuple() if self.scene.bbox() else None}

    def summary(self) -> dict:
        s = self.scene
        b = s.bbox()
        return {
            "name": self.name, "version": self.version, "data_version": s.reg.data_version, "theme": self.theme,
            "description": self.meta.get("description", ""), "bbox": b.as_tuple() if b else None,
            "size": b.size if b else None, "blocks": s.stats()["blocks"] if b else 0, "entities": len(s.entities),
            "markers": {n: {"kind": m.kind, "pos": m.pos, "yaw": m.yaw} for n, m in s.markers.items()},
            "steps": [f"{st['n']}. {st['label']}" for st in self.meta["steps"]], "undo_available": len(self._history),
            "path": str(self.root),
        }


def _count_changes(before: np.ndarray, before_origin: np.ndarray, scene: Scene) -> int:
    after = scene.data
    if before.size == 0:
        return int((after != 0).sum())
    if np.array_equal(before_origin, scene.origin) and before.shape == after.shape:
        return int((before != after).sum())
    # align on the new (larger) extent
    lo = before_origin - scene.origin
    padded = np.zeros_like(after)
    sx, sy, sz = before.shape
    try:
        padded[lo[0]:lo[0] + sx, lo[1]:lo[1] + sy, lo[2]:lo[2] + sz] = before
    except ValueError:
        return int((after != 0).sum())
    return int((padded != after).sum())
