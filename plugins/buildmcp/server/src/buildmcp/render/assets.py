"""Vanilla client assets (blockstates, block models, textures) for the renderer.

Assets are never committed to the repository: on first use they are downloaded into
the cache (``$BUILDMCP_DATA/assets/<version>``):
  1. from Mojang (the official client.jar of that version), or
  2. from the InventivetalentDev/minecraft-assets mirror on GitHub (fallback).
"""

from __future__ import annotations

import io
import json
import os
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MIRROR = "https://raw.githubusercontent.com/InventivetalentDev/minecraft-assets/{version}/assets/minecraft/"
PREFIX = "assets/minecraft/"
TEXTURE_DIRS = ("textures/block/", "textures/colormap/", "textures/item/")


def data_dir() -> Path:
    env = os.environ.get("BUILDMCP_DATA", "").strip()
    if env and not env.startswith("${"):
        p = Path(env).expanduser()
    else:
        p = Path.home() / ".buildmcp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _client():
    import httpx

    try:
        import ssl

        import truststore

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return httpx.Client(timeout=60, follow_redirects=True, verify=ctx)
    except Exception:  # pragma: no cover - fall back to certifi/env
        return httpx.Client(timeout=60, follow_redirects=True)


class AssetError(RuntimeError):
    pass


class AssetStore:
    """Loaded assets of one Minecraft version."""

    _instances: dict[str, "AssetStore"] = {}
    _lock = threading.Lock()

    def __init__(self, version: str, root: Path):
        self.version = version
        self.root = root
        self.blockstates: dict[str, dict] = json.loads((root / "blockstates.json").read_text("utf-8"))
        self.models: dict[str, dict] = json.loads((root / "models.json").read_text("utf-8"))
        self._tex_cache: dict[str, np.ndarray | None] = {}

    # ----------------------------------------------------------- factory
    @classmethod
    def get(cls, version: str) -> "AssetStore":
        with cls._lock:
            inst = cls._instances.get(version)
            if inst is None:
                root = data_dir() / "assets" / version
                if not (root / ".complete").exists():
                    download(version, root)
                inst = cls(version, root)
                cls._instances[version] = inst
            return inst

    # ----------------------------------------------------------- access
    def blockstate(self, name: str) -> dict | None:
        return self.blockstates.get(name.removeprefix("minecraft:"))

    def model(self, ref: str) -> dict | None:
        ref = ref.removeprefix("minecraft:")
        if "/" not in ref:
            ref = "block/" + ref
        return self.models.get(ref)

    def texture(self, ref: str) -> np.ndarray | None:
        """RGBA uint8 array (first animation frame) for 'block/stone' / 'minecraft:block/stone'."""
        ref = ref.removeprefix("minecraft:")
        if ref in self._tex_cache:
            return self._tex_cache[ref]
        path = self.root / "textures" / (ref + ".png")
        arr = None
        if path.exists():
            img = Image.open(path).convert("RGBA")
            a = np.asarray(img, dtype=np.uint8)
            h, w = a.shape[:2]
            if h > w and h % w == 0:  # animated strip: first frame
                a = a[:w]
            arr = np.ascontiguousarray(a)
        self._tex_cache[ref] = arr
        return arr

    def colormap(self, name: str) -> np.ndarray | None:
        return self.texture(f"colormap/{name}")


def download(version: str, root: Path) -> None:
    """Fetch assets into ``root`` (Mojang first, GitHub mirror as fallback)."""
    root.mkdir(parents=True, exist_ok=True)
    errors = []
    for fn in (_from_mojang, _from_mirror):
        try:
            fn(version, root)
            (root / ".complete").write_text(fn.__name__, "utf-8")
            return
        except Exception as e:  # noqa: BLE001 - try the next source
            errors.append(f"{fn.__name__}: {e}")
    raise AssetError("Could not download Minecraft assets for the renderer: " + " | ".join(errors))


def _from_mojang(version: str, root: Path) -> None:
    with _client() as c:
        manifest = c.get(MANIFEST).raise_for_status().json()
        entry = next((v for v in manifest["versions"] if v["id"] == version), None)
        if entry is None:
            raise AssetError(f"version {version} not in Mojang manifest")
        vjson = c.get(entry["url"]).raise_for_status().json()
        url = vjson["downloads"]["client"]["url"]
        jar = c.get(url).raise_for_status().content
    blockstates: dict[str, dict] = {}
    models: dict[str, dict] = {}
    with zipfile.ZipFile(io.BytesIO(jar)) as z:
        for name in z.namelist():
            if not name.startswith(PREFIX):
                continue
            rel = name[len(PREFIX):]
            if rel.startswith("blockstates/") and rel.endswith(".json"):
                blockstates[rel[len("blockstates/"):-5]] = json.loads(z.read(name))
            elif rel.startswith("models/") and rel.endswith(".json"):
                models[rel[len("models/"):-5]] = json.loads(z.read(name))
            elif rel.startswith(TEXTURE_DIRS) and rel.endswith(".png"):
                out = root / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(name))
    _write_json(root, blockstates, models)


def _from_mirror(version: str, root: Path) -> None:
    base = MIRROR.format(version=version)
    with _client() as c:
        bs = c.get(base + "blockstates/_all.json").raise_for_status().json()
        models: dict[str, dict] = {}
        for sub in ("block", "item"):
            r = c.get(base + f"models/{sub}/_all.json")
            if r.status_code == 200:
                for k, v in r.json().items():
                    models[f"{sub}/{k}"] = v
        files: list[str] = []
        for d in TEXTURE_DIRS:
            r = c.get(base + d + "_list.json")
            if r.status_code != 200:
                continue
            files.extend(d + f for f in r.json().get("files", []) if f.endswith(".png"))

        failed: list[str] = []

        def fetch(rel: str) -> None:
            out = root / rel
            if out.exists():
                return
            for attempt in range(4):
                try:
                    resp = c.get(base + rel)
                    if resp.status_code == 200:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(resp.content)
                        return
                    if resp.status_code == 404:
                        return
                except Exception:  # noqa: BLE001 - transient network errors
                    pass
                time.sleep(0.5 * (2 ** attempt))
            failed.append(rel)

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(fetch, files))
        if len(failed) > max(10, len(files) // 50):
            raise AssetError(f"{len(failed)} of {len(files)} textures failed to download")
    _write_json(root, {k.removesuffix(".json"): v for k, v in bs.items()},
                {k.removesuffix(".json"): v for k, v in models.items()})


def _write_json(root: Path, blockstates: dict, models: dict) -> None:
    if not blockstates or not models:
        raise AssetError("empty asset set")
    (root / "blockstates.json").write_text(json.dumps(blockstates), "utf-8")
    (root / "models.json").write_text(json.dumps(models), "utf-8")
