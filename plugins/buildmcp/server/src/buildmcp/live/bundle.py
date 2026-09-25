"""BuildMCP bundle: the exchange format between BuildMCP and the BuildBridge plugin.

gzip( "BMCB" | u8 version | i32 header length | header JSON | i32 cell count | u16 cells (big endian)
      | i32 biome grid length | u8 biome grid )

Cells are palette indices in Sponge order (index = x + z*W + y*W*L); palette[0] is "" and means
"leave the world block alone". The biome grid has one entry per column (x + z*W), 255 = keep.
Tiles are [x, y, z, snbt], entities [x, y, z, id, snbt], positions relative to ``min``.
"""

from __future__ import annotations

import gzip
import io
import json
import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"BMCB"
VERSION = 1
BIOME_KEEP = 255
SKIP = ""


@dataclass
class Bundle:
    palette: list[str]  # index 0 = SKIP
    cells: np.ndarray  # (w, h, l) uint16
    min: tuple[int, int, int] = (0, 0, 0)
    tiles: list[tuple[int, int, int, str]] = field(default_factory=list)
    entities: list[tuple[float, float, float, str, str]] = field(default_factory=list)
    biome_palette: list[str] | None = None
    biomes: np.ndarray | None = None  # (w, l) uint8, BIOME_KEEP = keep
    header: dict = field(default_factory=dict)  # extra header keys (world, label, backup, entity_tag...)

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(int(v) for v in self.cells.shape)  # type: ignore[return-value]

    def changed_cells(self) -> int:
        return int((self.cells != 0).sum())

    # ---------------------------------------------------------------- encode
    def to_bytes(self, level: int = 6) -> bytes:
        w, h, l = self.size
        if len(self.palette) > 65536:
            raise ValueError("bundle palette over 65536 entries")
        if not self.palette or self.palette[0] != SKIP:
            raise ValueError("bundle palette[0] must be the skip marker ''")
        hdr = dict(self.header)
        hdr.update({
            "size": [w, h, l], "min": [int(v) for v in self.min], "palette": list(self.palette),
            "tiles": [[int(x), int(y), int(z), str(s)] for x, y, z, s in self.tiles],
            "entities": [[float(x), float(y), float(z), str(i), str(s)] for x, y, z, i, s in self.entities],
        })
        bio = None
        if self.biomes is not None and self.biome_palette:
            hdr["biomes"] = list(self.biome_palette)
            bio = np.ascontiguousarray(self.biomes.astype(np.uint8).T).ravel()  # index x + z*W
        else:
            hdr.pop("biomes", None)
        hb = json.dumps(hdr, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        flat = np.ascontiguousarray(np.transpose(self.cells.astype(np.uint16), (1, 2, 0))).ravel()
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level, mtime=0) as gz:
            gz.write(MAGIC + bytes([VERSION]) + struct.pack(">i", len(hb)) + hb)
            gz.write(struct.pack(">i", flat.size))
            gz.write(flat.astype(">u2").tobytes())
            if bio is not None:
                gz.write(struct.pack(">i", bio.size) + bio.tobytes())
            else:
                gz.write(struct.pack(">i", 0))
        return buf.getvalue()

    # ---------------------------------------------------------------- decode
    @classmethod
    def from_bytes(cls, data: bytes) -> "Bundle":
        raw = gzip.decompress(data)
        if raw[:4] != MAGIC:
            raise ValueError("not a BuildMCP bundle")
        if raw[4] != VERSION:
            raise ValueError(f"unsupported bundle version {raw[4]}")
        (hlen,) = struct.unpack(">i", raw[5:9])
        hdr = json.loads(raw[9:9 + hlen].decode("utf-8"))
        pos = 9 + hlen
        w, h, l = (int(v) for v in hdr["size"])
        (n,) = struct.unpack(">i", raw[pos:pos + 4])
        pos += 4
        if n != w * h * l:
            raise ValueError("cell count does not match the size")
        flat = np.frombuffer(raw[pos:pos + 2 * n], dtype=">u2").astype(np.uint16)
        pos += 2 * n
        cells = np.transpose(flat.reshape(h, l, w), (2, 0, 1)).copy()
        (bl,) = struct.unpack(">i", raw[pos:pos + 4])
        pos += 4
        biomes = None
        bpal = hdr.get("biomes")
        if bl:
            biomes = np.frombuffer(raw[pos:pos + bl], dtype=np.uint8).reshape(l, w).T.copy()
        palette = [str(p) for p in hdr.pop("palette")]
        tiles = [(int(a[0]), int(a[1]), int(a[2]), str(a[3])) for a in hdr.pop("tiles", [])]
        ents = [(float(a[0]), float(a[1]), float(a[2]), str(a[3]), str(a[4]) if len(a) > 4 else "{}")
                for a in hdr.pop("entities", [])]
        mn = tuple(int(v) for v in hdr.pop("min", (0, 0, 0)))
        hdr.pop("size", None)
        hdr.pop("biomes", None)
        return cls(palette=palette, cells=cells, min=mn, tiles=tiles, entities=ents,
                   biome_palette=list(bpal) if bpal and biomes is not None else None,
                   biomes=biomes if bpal else None, header=hdr)

    # ------------------------------------------------------------- convert
    def to_structure(self):
        """Bundle read from the world -> StructureData (palette entry '' becomes air)."""
        import nbtlib

        from ..io.nbtutil import compound
        from ..io.structure_data import StructureData

        airs = (SKIP, "minecraft:cave_air", "minecraft:void_air")
        pal = ["minecraft:air" if p.split("[", 1)[0] in airs else p for p in self.palette]
        bes = {}
        for x, y, z, snbt in self.tiles:
            nbt = _parse_snbt(snbt)
            bid = str(nbt.pop("id", ""))
            for k in ("x", "y", "z"):
                nbt.pop(k, None)
            if not bid:
                from ..io.nbtutil import block_entity_id

                bid = block_entity_id(pal[int(self.cells[x, y, z])])
            bes[(x, y, z)] = (bid, compound(nbt))
        ents = []
        for x, y, z, eid, snbt in self.entities:
            nbt = _parse_snbt(snbt)
            for k in ("UUID", "Pos", "id"):
                nbt.pop(k, None)
            ents.append((eid, (x, y, z), nbtlib.Compound(nbt)))
        bio_pal = list(self.biome_palette) if self.biome_palette else None
        bio = None
        if self.biomes is not None and bio_pal:
            bio = self.biomes.copy()
            bio[bio == BIOME_KEEP] = 0
        return StructureData(palette=pal, data=self.cells.astype(np.uint32), min=self.min, origin=self.min,
                             block_entities=bes, entities=ents, biome_palette=bio_pal, biomes=bio,
                             data_version=int(self.header.get("data_version", 0)))


def _parse_snbt(snbt: str):
    import nbtlib

    from ..io.snbt import parse_snbt

    try:
        tag = parse_snbt(snbt)  # 1.21.5+ prints escapes and mixed lists that nbtlib alone rejects
    except Exception:  # noqa: BLE001 - unreadable SNBT: keep the block, drop the NBT
        return nbtlib.Compound()
    return nbtlib.Compound(tag) if isinstance(tag, nbtlib.Compound) else nbtlib.Compound()
