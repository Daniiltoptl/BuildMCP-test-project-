"""Whole-server backups: worlds, configs and plugins in one zip in <data>/backups/<server>/.

A running server is told to stop saving and flush everything to disk first (save-off, save-all flush,
then save-on), so the copy is consistent. What the server can make again (libraries/, versions/,
cache/, logs/, crash reports, Paper's remapped plugins) stays out. Restore needs the server stopped and
first saves the current state, so a restore can be undone too.
"""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from pathlib import Path

from .registry import ServerEntry

SKIP_TOP = {"libraries", "versions", "cache", "logs", "crash-reports", "bundler", "debug", "heapdumps"}
SKIP_ANY = {".paper-remapped", "__pycache__"}
SKIP_STATE = {"removed", "staging", "console.log", "console.log.1", "runner.json", "run.json"}
STORED = {".mca", ".mcc", ".jar", ".zip", ".gz", ".png", ".jpg", ".ogg", ".xz", ".7z"}


class BackupError(RuntimeError):
    pass


def _sorted(entry: ServerEntry) -> list[Path]:
    """Oldest first, by the time they were made (names alone tie within one second)."""
    return sorted(backups_dir(entry).glob("*.zip"), key=lambda b: (b.stat().st_mtime, b.name))


def backups_dir(entry: ServerEntry) -> Path:
    from ..render.assets import data_dir

    d = data_dir() / "backups" / entry.name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _included(rel: Path) -> bool:
    parts = rel.parts
    if not parts:
        return False
    if parts[0] in SKIP_TOP or any(p in SKIP_ANY for p in parts):
        return False
    if parts[0] == ".buildmcp" and len(parts) > 1 and parts[1] in SKIP_STATE:
        return False
    return True


def _files(root: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel_d = d.relative_to(root)
        dirnames[:] = [n for n in dirnames if _included(rel_d / n)]
        for f in filenames:
            rel = rel_d / f
            if _included(rel) and not f.endswith((".lock", ".buildmcp-tmp")) and f != "session.lock":
                out.append(d / f)
    return out


def _flush(entry: ServerEntry) -> bool:
    """Ask a running server to write everything and stop saving until the copy is done."""
    from . import process

    if entry.is_proxy or not process.is_running(entry):
        return False
    process.console(entry, "save-off", wait=0.5)
    off = process._log_size(entry)
    process.console(entry, "save-all flush", wait=0.5)
    t0 = time.time()
    while time.time() - t0 < 120:
        if any("Saved the game" in l or "Saved the world" in l for l in process.read_from(entry, off)):
            break
        time.sleep(0.5)
    return True


def create(entry: ServerEntry, note: str = "", keep: int = 10) -> dict:
    from . import process

    root = entry.path
    if not root.is_dir():
        raise BackupError(f"{root} does not exist")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tail = "-" + "".join(c for c in note if c.isalnum() or c in "-_")[:40] if note else ""
    dest, i = backups_dir(entry) / f"{stamp}{tail}.zip", 1
    while dest.exists() or dest.with_suffix(".part").exists():  # two in one second never share a name
        i += 1
        dest = backups_dir(entry) / f"{stamp}-{i}{tail}.zip"
    flushed = _flush(entry)
    t0 = time.time()
    total = count = 0
    skipped: list[str] = []
    try:
        with zipfile.ZipFile(dest.with_suffix(".part"), "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in _files(root):
                rel = f.relative_to(root).as_posix()
                try:
                    comp = zipfile.ZIP_STORED if f.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
                    z.write(f, rel, compress_type=comp)
                    total += f.stat().st_size
                    count += 1
                except (OSError, ValueError) as ex:  # vanished, or locked by another program
                    skipped.append(f"{rel}: {type(ex).__name__}")
        dest.with_suffix(".part").replace(dest)
    finally:
        if flushed:
            process.console(entry, "save-on", wait=0.2)
        dest.with_suffix(".part").unlink(missing_ok=True)
    old = [b for b in _sorted(entry) if "before-restore" not in b.name]
    removed = []
    if keep > 0:
        for b in old[:-keep]:
            b.unlink(missing_ok=True)
            removed.append(b.name)
    return {"server": entry.name, "backup": dest.name, "path": str(dest), "files": count,
            "mb": round(total / 1e6, 1), "zip_mb": round(dest.stat().st_size / 1e6, 1),
            "seconds": round(time.time() - t0, 1), "consistent": "flushed while running" if flushed else "server stopped",
            **({"pruned": removed} if removed else {}),
            **({"skipped": skipped[:20], "warning": f"{len(skipped)} files could not be read"} if skipped else {})}


def listing(entry: ServerEntry) -> list[dict]:
    return [{"backup": b.name, "mb": round(b.stat().st_size / 1e6, 1),
             "made": time.strftime("%Y-%m-%d %H:%M", time.localtime(b.stat().st_mtime))}
            for b in reversed(_sorted(entry))]


def restore(entry: ServerEntry, backup: str = "") -> dict:
    from . import process

    if process.is_running(entry):
        raise BackupError(f"{entry.name} is running: stop it first (srv_power stop)")
    bs = list(reversed(_sorted(entry)))
    b = next((x for x in bs if x.name == backup), None) if backup else next(
        (x for x in bs if "before-restore" not in x.name), None)
    if b is None:
        raise BackupError(f"no backup {backup or ''} for {entry.name} (have: {', '.join(x.name for x in bs[:8])})")
    with zipfile.ZipFile(b) as z:
        bad = z.testzip()
        if bad:
            raise BackupError(f"{b.name} is damaged ({bad})")
        names = z.namelist()
    safety = create(entry, note="before-restore", keep=0)
    root = entry.path
    for f in _files(root):
        f.unlink(missing_ok=True)
    for dirpath, dirnames, _ in os.walk(root, topdown=False):
        d = Path(dirpath)
        if d != root and _included(d.relative_to(root)) and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass
    with zipfile.ZipFile(b) as z:
        for n in names:
            target = (root / n).resolve()
            if not target.is_relative_to(root.resolve()):
                raise BackupError(f"{b.name}: {n} points outside the server folder")
        z.extractall(root)
    return {"server": entry.name, "restored": b.name, "files": len(names), "undo": safety["backup"],
            "next": "start the server (srv_power start)"}


def delete(entry: ServerEntry, backup: str) -> dict:
    p = backups_dir(entry) / backup
    if not backup or not p.exists() or p.suffix != ".zip":
        raise BackupError(f"no backup {backup}")
    p.unlink()
    return {"server": entry.name, "deleted": backup}


def copy_out(entry: ServerEntry, backup: str, dest: str) -> dict:
    """Copy a backup somewhere else (another disk, a cloud-synced folder)."""
    p = backups_dir(entry) / backup
    if not p.exists():
        raise BackupError(f"no backup {backup}")
    d = Path(dest).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, d / p.name)
    return {"copied": str(d / p.name)}
