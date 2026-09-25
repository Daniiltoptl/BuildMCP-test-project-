"""A fake Minecraft RCON server that applies the vanilla commands BuildMCP sends to a Scene.

It follows the real protocol quirks: one packet per socket read, packets over 1460 bytes break the
connection, commands need loaded chunks, fill is limited to 32768 blocks.
"""

from __future__ import annotations

import re
import socket
import struct
import threading

import nbtlib

from buildmcp.blocks.registry import BlockError
from buildmcp.scene import Scene


class FakeRcon:
    def __init__(self, password: str = "pw", version: str = "1.21.5", strict: bool = True):
        self.password = password
        self.world = Scene(version)
        self.strict = strict
        self.loaded: set[tuple[int, int]] = set()
        self.entities: list[dict] = []
        self.biomes: dict[tuple[int, int, int], str] = {}
        self.gamerules = {"logAdminCommands": "true"}
        self.player = {"name": "Steve", "pos": [0.5, 64.0, 0.5], "rot": [0.0, 0.0]}
        self.log: list[str] = []
        self.max_packet = 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self) -> None:
        self._stop = True
        self.sock.close()

    # ------------------------------------------------------------ protocol
    def _accept(self) -> None:
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _client(self, c: socket.socket) -> None:
        authed = False
        with c:
            while True:
                try:
                    data = c.recv(1460)
                except OSError:
                    return
                if len(data) < 10:
                    return
                (length,) = struct.unpack("<i", data[:4])
                self.max_packet = max(self.max_packet, len(data))
                if length != len(data) - 4:  # vanilla: exactly one whole packet per read
                    return
                rid, ptype = struct.unpack("<ii", data[4:12])
                body = data[12:-2].decode("utf-8")
                if ptype == 3:
                    authed = body == self.password
                    self._send(c, rid if authed else -1, 2, "")
                elif ptype == 2 and authed:
                    self.log.append(body)
                    try:
                        out = self.run(body)
                    except Exception as e:  # noqa: BLE001
                        out = f"Error executing: {body} ({e})"
                    self._send(c, rid, 0, out)
                else:
                    self._send(c, rid, 0, f"Unknown request {ptype:x}")

    @staticmethod
    def _send(c, rid, ptype, text) -> None:
        raw = text.encode("utf-8")
        chunks = [raw[i:i + 4096] for i in range(0, len(raw), 4096)] or [b""]
        for ch in chunks:
            c.sendall(struct.pack("<iii", len(ch) + 10, rid, ptype) + ch + b"\x00\x00")

    # ------------------------------------------------------------ commands
    def _is_loaded(self, x: int, z: int) -> bool:
        return (x >> 4, z >> 4) in self.loaded

    def run(self, cmd: str) -> str:
        if cmd.endswith(" strict") and not self.strict:
            return "Incorrect argument for command"
        m = re.match(r"execute in (\S+) run (.*)$", cmd)
        if m:
            return self.run(m.group(2))
        a = cmd.split(" ")
        c = a[0]
        if c == "execute" and a[1] == "if" and a[2] == "loaded":
            return "Test passed" if self._is_loaded(int(a[3]), int(a[5])) else "Test failed"
        if c == "execute" and a[1] == "if" and a[2] == "block":
            return "Test failed"
        if c == "forceload":
            x1, z1, x2, z2 = (int(v) for v in a[2:6])
            keys = {(cx, cz) for cx in range(x1 >> 4, (x2 >> 4) + 1) for cz in range(z1 >> 4, (z2 >> 4) + 1)}
            if len(keys) > 256:
                return "Too many chunks in the specified area (maximum 256, specified %d)" % len(keys)
            if a[1] == "add":
                self.loaded |= keys
            else:
                self.loaded -= keys
            return f"Marked {len(keys)} chunks"
        if c == "gamerule":
            if len(a) == 3:
                self.gamerules[a[1]] = a[2]
                return f"Gamerule {a[1]} is now set to: {a[2]}"
            return f"Gamerule {a[1]} is currently set to: {self.gamerules.get(a[1], 'true')}"
        if c == "list":
            return f"There are 1 of a max of 20 players online: {self.player['name']}"
        if c == "fill":
            x1, y1, z1, x2, y2, z2 = (int(v) for v in a[1:7])
            vol = (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)
            if vol > 32768:
                return f"Too many blocks in the specified area (maximum 32768, specified {vol})"
            if not all(self._is_loaded(x, z) for x in (x1, x2) for z in (z1, z2)):
                return "That position is not loaded"
            try:
                self.world.fill((x1, y1, z1, x2, y2, z2), a[7])
            except BlockError as e:
                return f"Unknown block type: {e}"
            return f"Successfully filled {vol} block(s)"
        if c == "setblock":
            x, y, z = (int(v) for v in a[1:4])
            if not self._is_loaded(x, z):
                return "That position is not loaded"
            rest = " ".join(a[4:])
            for mode in (" strict", " replace", " keep", " destroy"):
                if rest.endswith(mode):
                    rest = rest[: -len(mode)]
            state, _, nbt = rest.partition("{")
            self.world.set(x, y, z, state)
            if nbt:
                self.world.set_nbt(x, y, z, nbtlib.parse_nbt("{" + nbt))
            return f"Changed the block at {x}, {y}, {z}"
        if c == "data" and a[1] == "merge" and a[2] == "block":
            x, y, z = (int(v) for v in a[3:6])
            add = nbtlib.parse_nbt(" ".join(a[6:]))
            cur = nbtlib.Compound(self.world.nbt(x, y, z) or {})
            cur.update(add)
            self.world.set_nbt(x, y, z, cur)
            return f"Modified block data of {x}, {y}, {z}"
        if c == "data" and a[1] == "merge" and a[2] == "entity":
            tag = re.search(r"tag=([^,\]]+)", a[3]).group(1)
            for e in self.entities:
                if tag in e["tags"]:
                    e["nbt"].update(nbtlib.parse_nbt(" ".join(a[4:])))
                    return "Modified entity data of entity"
            return "No entity was found"
        if c == "data" and a[1] == "get" and a[2] == "entity":
            p = self.player
            if a[4] == "Pos":
                return f"{p['name']} has the following entity data: [{p['pos'][0]}d, {p['pos'][1]}d, {p['pos'][2]}d]"
            if a[4] == "Rotation":
                return f"{p['name']} has the following entity data: [{p['rot'][0]}f, {p['rot'][1]}f]"
            return f'{p["name"]} has the following entity data: "minecraft:overworld"'
        if c == "summon":
            nbt = nbtlib.parse_nbt(" ".join(a[5:])) if len(a) > 5 else nbtlib.Compound()
            tags = [str(t) for t in nbt.get("Tags", [])]
            self.entities.append({"id": a[1], "pos": tuple(float(v) for v in a[2:5]), "nbt": nbt, "tags": tags})
            return "Summoned new entity"
        if c == "tag":
            tag = re.search(r"tag=([^,\]]+)", a[1]).group(1)
            for e in self.entities:
                if tag in e["tags"] and a[2] == "remove":
                    e["tags"].remove(a[3])
            return "Removed tag"
        if c == "kill":
            tag = re.search(r"tag=([^,\]]+)", a[1]).group(1)
            before = len(self.entities)
            self.entities = [e for e in self.entities if tag not in e["tags"]]
            return f"Killed {before - len(self.entities)} entities"
        if c == "fillbiome":
            x1, y1, z1, x2, y2, z2 = (int(v) for v in a[1:7])
            n = 0
            for qx in range(x1 // 4, x2 // 4 + 1):
                for qy in range(y1 // 4, y2 // 4 + 1):
                    for qz in range(z1 // 4, z2 // 4 + 1):
                        self.biomes[(qx, qy, qz)] = a[7]
                        n += 1
            return f"{n} biome entries set"
        if c == "tp":
            self.player["pos"] = [float(v) for v in a[2:5]]
            if len(a) > 6:
                self.player["rot"] = [float(a[5]), float(a[6])]
            return f"Teleported {a[1]}"
        return "Unknown or incomplete command, see below for error"
