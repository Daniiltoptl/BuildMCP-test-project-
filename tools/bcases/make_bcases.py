"""Full BCases setup from a server archive: a donate case (the LuckPerms donor groups, rarities as colored
shulkers spinning on the wheel with the RP prefix above each), a coins case (10k..100k) and a leaves case
(250..1000), a big green RGB message to everyone within 5 blocks of the case, menus, holograms, keys.

    uv run --with pyyaml python make_bcases.py <server archive .tar.gz/.zip or server folder> [options]

Reads plugins/LuckPerms (yaml-storage, json-storage or an `lp export` file), the plugin list (Essentials /
CMI / PlayerPoints / CoinsEngine) and plugins/BCases/blocks.yml if there is one, and writes a ready
plugins/BCases folder into --out. Nothing in the source is changed.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import yaml

# ------------------------------------------------------------------ rarities
RARITIES = [  # name, shulker, hex color, weight of one prize of this rarity in the donate case
    ("Обычный", "gray_shulker_box", "#B4B4B4", 35.0),
    ("Редкий", "blue_shulker_box", "#4D8DFF", 20.0),
    ("Эпический", "purple_shulker_box", "#B45CFF", 10.0),
    ("Мифический", "pink_shulker_box", "#FF6EC7", 4.0),
    ("Легендарный", "yellow_shulker_box", "#FFD23C", 1.5),
]
COINS = [(10_000, 24.0), (20_000, 18.0), (30_000, 14.0), (40_000, 11.0), (50_000, 9.0),
         (60_000, 7.0), (70_000, 6.0), (80_000, 5.0), (90_000, 3.5), (100_000, 2.5)]
LEAVES = [(250, 25.0), (300, 20.0), (400, 15.0), (500, 12.0), (600, 9.0), (700, 7.0), (800, 5.0),
          (900, 4.0), (1000, 3.0)]
STAFF_RE = re.compile(r"(admin|адм|moder|модер|helper|хелп|owner|овнер|влад|dev|разраб|builder|строит|staff|"
                      r"curator|куратор|support|саппорт|mod$|^gm|глав|test|тест|media|медиа|youtube|ютуб)", re.I)
GREEN_A, GREEN_B = "#11998E", "#38EF7D"


# ------------------------------------------------------------------ reading the server
class Source:
    """A server folder or an archive of one; only the small files we need are read."""

    def __init__(self, path: Path):
        self.files: dict[str, bytes] = {}
        self.names: list[str] = []
        want = re.compile(r"(^|/)plugins/(LuckPerms/(yaml-storage|json-storage|hocon-storage)/groups/[^/]+|"
                          r"LuckPerms/[^/]+\.json(\.gz)?|LuckPerms/config\.yml|BCases/.+\.ya?ml|"
                          r"PlayerPoints/config\.yml|CoinsEngine/currencies/[^/]+\.yml|[^/]+\.jar)$", re.I)
        if path.is_dir():
            for p in path.rglob("*"):
                rel = p.relative_to(path).as_posix()
                if p.is_file() and want.search(rel) and p.stat().st_size < 20_000_000:
                    self.files[rel] = b"" if rel.endswith(".jar") else p.read_bytes()
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for i in z.infolist():
                    if want.search(i.filename) and i.file_size < 20_000_000:
                        self.files[i.filename] = b"" if i.filename.endswith(".jar") else z.read(i)
        else:
            with tarfile.open(path, "r:*") as t:
                for m in t:
                    if m.isfile() and want.search(m.name) and m.size < 20_000_000:
                        self.files[m.name] = b"" if m.name.endswith(".jar") else t.extractfile(m).read()
        self.names = list(self.files)

    def find(self, pattern: str) -> list[tuple[str, bytes]]:
        rx = re.compile(pattern, re.I)
        return [(n, b) for n, b in self.files.items() if rx.search(n)]

    def plugins(self) -> set[str]:
        return {re.sub(r"[-_ ]?v?\d.*$", "", n.rsplit("/", 1)[-1][:-4]).lower()
                for n in self.names if re.search(r"(^|/)plugins/[^/]+\.jar$", n)}


def _nodes_to_group(name: str, nodes: list[tuple[str, bool]]) -> dict:
    g = {"name": name, "weight": 0, "prefix": "", "prefix_priority": -1, "display": ""}
    for key, value in nodes:
        if not value:
            continue
        m = re.match(r"^weight\.(\d+)$", key)
        if m:
            g["weight"] = int(m.group(1))
        m = re.match(r"^prefix\.(\d+)\.(.*)$", key, re.S)
        if m and int(m.group(1)) >= g["prefix_priority"]:
            g["prefix_priority"], g["prefix"] = int(m.group(1)), m.group(2)
        m = re.match(r"^displayname\.(.+)$", key)
        if m:
            g["display"] = m.group(1)
    return g


def read_groups(src: Source) -> tuple[list[dict], str]:
    """LuckPerms groups with weight and prefix, and where they came from."""
    groups: dict[str, dict] = {}
    for n, b in src.find(r"LuckPerms/yaml-storage/groups/[^/]+\.ya?ml$"):
        d = yaml.safe_load(b.decode("utf-8", "replace")) or {}
        nodes = []
        for p in d.get("permissions") or []:
            if isinstance(p, str):
                nodes.append((p, True))
            elif isinstance(p, dict):
                for k, v in p.items():
                    nodes.append((k, bool(v.get("value", True)) if isinstance(v, dict) else bool(v)))
        for pref in d.get("prefixes") or []:
            if isinstance(pref, dict):
                for text, meta in pref.items():
                    nodes.append((f"prefix.{(meta or {}).get('priority', 0)}.{text}", True))
        for k, v in (d.get("meta") or {}).items() if isinstance(d.get("meta"), dict) else []:
            if k == "weight":
                nodes.append((f"weight.{v}", True))
        name = str(d.get("name") or Path(n).stem)
        groups[name.lower()] = _nodes_to_group(name, nodes)
    if groups:
        return list(groups.values()), "yaml-storage"
    for n, b in src.find(r"LuckPerms/json-storage/groups/[^/]+\.json$"):
        d = json.loads(b.decode("utf-8", "replace"))
        nodes = []
        for p in d.get("permissions") or []:
            if isinstance(p, dict):
                nodes.append((p.get("permission") or p.get("key", ""), bool(p.get("value", True))))
        for pref in d.get("prefixes") or []:
            if isinstance(pref, dict):
                nodes.append((f"prefix.{pref.get('priority', 0)}.{pref.get('prefix', '')}", True))
        name = str(d.get("name") or Path(n).stem)
        groups[name.lower()] = _nodes_to_group(name, nodes)
    if groups:
        return list(groups.values()), "json-storage"
    for n, b in sorted(src.find(r"LuckPerms/[^/]+\.json(\.gz)?$"), reverse=True):
        try:
            raw = gzip.decompress(b) if n.endswith(".gz") else b
            d = json.loads(raw.decode("utf-8", "replace"))
        except (OSError, ValueError):
            continue
        for name, g in (d.get("groups") or {}).items():
            nodes = [(x.get("key", ""), bool(x.get("value", True))) for x in g.get("nodes", []) if isinstance(x, dict)]
            groups[name.lower()] = _nodes_to_group(name, nodes)
        if groups:
            return list(groups.values()), f"lp export ({Path(n).name})"
    return [], ""


def donors(groups: list[dict], include: list[str], exclude: list[str]) -> list[dict]:
    inc = {x.lower() for x in include}
    exc = {x.lower() for x in exclude} | {"default"}
    out = []
    for g in groups:
        n = g["name"].lower()
        if inc:
            if n in inc:
                out.append(g)
            continue
        if n in exc or STAFF_RE.search(n) or STAFF_RE.search(strip_colors(g["prefix"])) or not g["prefix"]:
            continue
        out.append(g)
    return sorted(out, key=lambda g: (g["weight"], g["name"]))


# ------------------------------------------------------------------ colors and tellraw
def strip_colors(s: str) -> str:
    s = re.sub(r"&#[0-9a-fA-F]{6}|&x(&[0-9a-fA-F]){6}|[&§][0-9a-fk-orA-FK-OR]|<[^>]+>", "", s)
    return s.strip()


_LEGACY = {"0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA", "4": "#AA0000", "5": "#AA00AA",
           "6": "#FFAA00", "7": "#AAAAAA", "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
           "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF"}


def legacy_to_json(s: str, default: str = "#FFFFFF") -> list[dict]:
    """'&8[&#ff0000VIP&8]' -> tellraw components (colors, bold/italic...)."""
    s = re.sub(r"&x((?:&[0-9a-fA-F]){6})", lambda m: "&#" + m.group(1).replace("&", ""), s.replace("§", "&"))
    s = re.sub(r"<#([0-9a-fA-F]{6})>", r"&#\1", s)
    s = re.sub(r"</?[a-z_:#0-9]+>", "", s)  # other MiniMessage tags are dropped
    out, color, fmt, buf = [], default, {}, ""

    def flush():
        nonlocal buf
        if buf:
            out.append({"text": buf, "color": color, **fmt})
            buf = ""
    i = 0
    while i < len(s):
        if s[i] == "&" and i + 1 < len(s):
            if s[i + 1] == "#" and re.fullmatch(r"[0-9a-fA-F]{6}", s[i + 2:i + 8]):
                flush()
                color, fmt = "#" + s[i + 2:i + 8].upper(), {}
                i += 8
                continue
            c = s[i + 1].lower()
            if c in _LEGACY:
                flush()
                color, fmt = _LEGACY[c], {}
                i += 2
                continue
            if c in "lmnok":
                flush()
                fmt = {**fmt, {"l": "bold", "m": "strikethrough", "n": "underlined", "o": "italic",
                               "k": "obfuscated"}[c]: True}
                i += 2
                continue
            if c == "r":
                flush()
                color, fmt = default, {}
                i += 2
                continue
        buf += s[i]
        i += 1
    flush()
    return out or [{"text": "", "color": default}]


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def gradient(text: str, a: str, b: str, **fmt) -> list[dict]:
    n = max(1, len(text) - 1)
    return [{"text": ch, "color": _mix(a, b, i / n), **fmt} for i, ch in enumerate(text)]


def gradient_legacy(text: str, a: str, b: str) -> str:
    n = max(1, len(text) - 1)
    return "".join(f"&{_mix(a, b, i / n)}{ch}" for i, ch in enumerate(text))


def to_bcases(s: str) -> str:
    """Any prefix format (&x&f&f..., <#hex>, MiniMessage) -> the &-codes with &#RRGGBB that BCases shows."""
    s = re.sub(r"&x((?:&[0-9a-fA-F]){6})", lambda m: "&#" + m.group(1).replace("&", ""), s.replace("§", "&"))
    s = re.sub(r"<#([0-9a-fA-F]{6})>", r"&#\1", s)
    s = re.sub(r"<(bold|b)>", "&l", s)
    s = re.sub(r"</?[a-z_:#0-9]+>", "", s)
    return s.strip()


def fmt_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


# ------------------------------------------------------------------ the case pieces
def dimension(world: str) -> str:
    return {"world": "minecraft:overworld", "world_nether": "minecraft:the_nether",
            "world_the_end": "minecraft:the_end"}.get(world, f"minecraft:{world.lower()}")


def near(case: dict) -> str:
    """'execute ... run' that addresses everyone within 5 blocks of the case block."""
    if case.get("pos"):
        x, y, z = case["pos"]
        return f"execute in {dimension(case['world'])} positioned {x + 0.5} {y + 0.5} {z + 0.5} run"
    return "execute at %player_name% run"  # no position known: around the player who opened it


def win_commands(case: dict, prize_json: list[dict], rarity: int, give: list[str], what: str) -> list[str]:
    name, _, color, _ = RARITIES[rarity]
    bar = gradient("✦━━━━━━━━━━━━━━━━━━━━━━━━━━━━✦", GREEN_A, GREEN_B)
    msg = ["", "\n", "  "] + bar + ["\n", "     "] + gradient("✿ УДАЧА! КЕЙС ОТКРЫТ ✿", "#A8FF78", "#78FFD6",
                                                             bold=True)
    msg += ["\n", "\n", {"text": "  ▸ ", "color": GREEN_B}, {"text": "Игрок ", "color": "#B8F5C8"},
            {"text": "%player_name%", "color": "#FFFFFF", "bold": True},
            {"text": f" выбил {what}:", "color": "#B8F5C8"}, "\n", "     "]
    msg += prize_json + [{"text": "  ❰", "color": "#5A7A66"}, {"text": name, "color": color, "italic": True},
                         {"text": "❱", "color": "#5A7A66"}]
    msg += ["\n", {"text": "  ▸ ", "color": GREEN_B}, {"text": "из кейса ", "color": "#B8F5C8"}]
    msg += gradient(case["title"], GREEN_B, "#C6FFDD", bold=True) + ["\n", "  "] + bar + ["\n"]
    sound = "minecraft:ui.toast.challenge_complete" if rarity >= 3 else "minecraft:entity.player.levelup"
    plain = strip_colors(case["title"])
    return give + [
        f"[TITLE] \"{gradient_legacy('Поздравляем!', '#A8FF78', '#38EF7D')}\\n&fТвой приз: {case['last_prize']}\" 10 60 20",
        f"[CONSOLE] {near(case)} tellraw @a[distance=..5] {json.dumps(msg, ensure_ascii=False)}",
        f"[CONSOLE] {near(case)} playsound {sound} master @a[distance=..5] ~ ~ ~ 1 1.1",
        f"[CONSOLE] {near(case)} particle minecraft:happy_villager ~ ~1 ~ 0.8 0.8 0.8 0 40",
    ] + ([f"[BROADCAST] &r", f"[BROADCAST] {gradient_legacy('★ ЛЕГЕНДАРНЫЙ ДРОП ★', '#FFD23C', '#38EF7D')} "
          f"&f%player_name% &7выбил {case['last_prize']} &7из «{plain}»", f"[BROADCAST] &r"] if rarity == 4 and case.get("broadcast") else [])


def prize(case: dict, display: str, rarity: int, weight: float, give: list[str], what: str) -> dict:
    case["last_prize"] = display
    return {"chance": weight, "enchanted": rarity >= 3, "material": RARITIES[rarity][1],
            "display_name": display, "give_commands": win_commands(case, legacy_to_json(display), rarity, give, what)}


def donate_tiers(n: int) -> list[int]:
    if n <= 1:
        return [4] * n
    if n <= 5:
        return [round(i * 4 / (n - 1)) for i in range(n)]
    return [min(4, i * 5 // n) for i in range(n)]


def build(args, src: Source) -> dict:
    groups, origin = read_groups(src)
    report: dict = {"luckperms": origin or "не найдено", "warnings": []}
    don = donors(groups, args.include, args.exclude)
    if not don:
        report["warnings"].append("донат-группы не найдены: нужна папка LuckPerms (yaml/json) или `lp export` "
                                  "(при хранении в H2 или MySQL выполни в консоли `lp export donaty` и положи файл "
                                  "plugins/LuckPerms/donaty.json.gz в архив), либо укажи --include")
    plugins = src.plugins()
    coins_cmd = args.coins_cmd or ("cmi money give %player_name% {amount}" if "cmi" in plugins
                                   else "eco give %player_name% {amount}")
    if not args.coins_cmd and not ({"essentials", "essentialsx", "cmi"} & plugins):
        report["warnings"].append(f"не нашёл Essentials/CMI: монеты выдаются командой `{coins_cmd}`, проверь")
    leaves_cmd = args.leaves_cmd
    if not leaves_cmd:
        cur = [n for n, _ in src.find(r"CoinsEngine/currencies/([^/]*(leaf|leav|лист)[^/]*)\.yml$")]
        if cur:
            leaves_cmd = f"coinsengine:{Path(cur[0]).stem} give %player_name% {{amount}}"
        elif "playerpoints" in plugins:
            leaves_cmd = "points give %player_name% {amount}"
        else:
            leaves_cmd = "points give %player_name% {amount}"
            report["warnings"].append("валюта листиков не найдена (нет PlayerPoints/CoinsEngine с листиками): "
                                      f"стоит команда `{leaves_cmd}`, замени через --leaves-cmd")
    report["coins_cmd"], report["leaves_cmd"] = coins_cmd, leaves_cmd

    old_blocks = {}
    for n, b in src.find(r"plugins/BCases/blocks\.ya?ml$"):
        for blk in (yaml.safe_load(b.decode("utf-8", "replace")) or {}).get("blocks") or []:
            old_blocks.setdefault(blk.get("on_click_menu", ""), blk)

    def pos(arg: str, key: str):
        if arg:
            x, y, z = (int(v) for v in arg.split(","))
            return [x, y, z]
        blk = old_blocks.get(f"bcases:{key}")
        if blk and blk.get("pos"):
            return [int(blk["pos"]["x"]), int(blk["pos"]["y"]), int(blk["pos"]["z"])]
        return None

    cases = {
        "donate": {"title": "Донат-кейс", "hex": ("#FFD23C", "#FF6EC7"), "pos": pos(args.donate_pos, "donate")},
        "coins": {"title": "Кейс с монетами", "hex": ("#FFE259", "#FFA751"), "pos": pos(args.coins_pos, "coins")},
        "leaves": {"title": "Кейс с листиками", "hex": ("#A8E063", "#56AB2F"), "pos": pos(args.leaves_pos, "leaves")},
    }
    for k, c in cases.items():
        c["world"] = args.world
        c["broadcast"] = args.broadcast_legendary
        if not c["pos"]:
            report["warnings"].append(f"координаты кейса {k} не заданы: поставь --{k}-pos x,y,z (сообщение пока "
                                      "уходит игрокам в 5 блоках от открывшего, блок кейса — в 0 100 0)")

    prizes: dict[str, list] = {"donate": [], "coins": [], "leaves": []}
    tiers = donate_tiers(len(don))
    for g, t in zip(don, tiers):
        disp = to_bcases(g["prefix"]) or g["display"] or g["name"]
        give = [f"[CONSOLE] {args.donate_cmd.format(group=g['name'])}"]
        prizes["donate"].append(prize(cases["donate"], disp, t, RARITIES[t][3], give, "донат"))
    for i, (amount, w) in enumerate(COINS):
        t = min(4, i // 2)
        disp = f"&{RARITIES[t][2]}⛃ {fmt_num(amount)} &fмонет"
        give = [f"[CONSOLE] {coins_cmd.format(amount=amount)}"]
        prizes["coins"].append(prize(cases["coins"], disp, t, w, give, "валюту"))
    for i, (amount, w) in enumerate(LEAVES):
        t = [0, 0, 1, 1, 2, 2, 3, 3, 4][i]
        disp = f"&{RARITIES[t][2]}☘ {fmt_num(amount)} &fлистиков"
        give = [f"[CONSOLE] {leaves_cmd.format(amount=amount)}"]
        prizes["leaves"].append(prize(cases["leaves"], disp, t, w, give, "валюту"))
    for c in cases.values():
        c.pop("last_prize", None)
        c.pop("broadcast", None)
    report["donors"] = [{"group": g["name"], "weight": g["weight"], "prefix": g["prefix"], "rarity": RARITIES[t][0]}
                        for g, t in zip(don, tiers)]
    report["chances"] = {k: {strip_colors(p["display_name"]): f"{100 * p['chance'] / sum(q['chance'] for q in v):.1f}%"
                             for p in v} for k, v in prizes.items() if v}
    return {"cases": cases, "prizes": prizes, "report": report, "plugins": sorted(plugins)}


# ------------------------------------------------------------------ writing BCases
def dump(data) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100000, default_flow_style=False)


def write(out: Path, built: dict, args) -> list[str]:
    root = out / "plugins" / "BCases"
    (root / "animations").mkdir(parents=True, exist_ok=True)
    (root / "menu").mkdir(parents=True, exist_ok=True)
    cases, prizes = built["cases"], built["prizes"]
    written = []

    def put(rel: str, text: str):
        p = root / rel
        p.write_text(text, "utf-8")
        written.append(str(p))

    put("prizes.yml", "# Сгенерировано make_bcases.py: донаты из LuckPerms, монеты, листики\n"
        + dump({"prizes": prizes}))
    for k in cases:
        put(f"animations/{k}_wheel.yml", dump({
            "provider": "default:wheel", "id": f"{k}_wheel",
            "settings": {"prize_count": 8, "radius": 1.6, "offsets": {"x": 0, "y": -0.3, "z": 0},
                         "max_speed": 16, "speed_fade": 0.06, "min_speed": 2, "remove_speed": 5,
                         "fake_prize_exponent": 0.5, "type": args.axis}}))
    for k, c in cases.items():
        a, b = c["hex"]
        put(f"menu/{k}.yml", dump({
            "id": f"bcases:{k}", "provider": "bcases:case", "type": "CHEST", "size": 27,
            "title": gradient_legacy(c["title"], a, b),
            "items": {"open": {
                "slot": 13, "material": {"donate": "ender_chest", "coins": "gold_block", "leaves": "oak_leaves"}[k],
                "display_name": " " + gradient_legacy("▶ Открыть " + c["title"].lower(), a, b),
                "lore": ["", f" &7Ключей: &f%bcases_keys_count_of_type_{k}%", "",
                         " &7Внутри — от &#B4B4B4обычных&7 до &#FFD23Cлегендарных&7 призов", ""],
                "on_click": {"requirements": [
                    {"check": f"%bcases_keys_count_of_type_{k}% < 1",
                     "commands": ["[MESSAGE] &#FF5555✘ &fУ тебя нет ключей от этого кейса", "[BREAK]"]},
                    {"check": "{playing} == true",
                     "commands": ["[MESSAGE] &#FF5555✘ &fКейс уже кто-то открывает, подожди", "[CLOSE]", "[BREAK]"],
                     "deny_commands": [f"[TAKE_KEY] {k}", f"[PLAY] {k}_wheel {k}", "[CLOSE]"]}]}}}}))
    lore = ["&eНажми, &fчтобы открыть", "&fПолучен: &6{issue_date}", "&fЗакончится: &6{removal_date}"]
    keylist = {"id": "bcases:key_list", "provider": "bcases:key_list", "type": "CHEST", "size": 54,
               "title": gradient_legacy("Твои ключи", GREEN_A, GREEN_B), "data-slots": "10-16,19-25,28-34,37-43",
               "expired": {"display_name": "&cЭтот ключ просрочен", "material": "barrier", "static": True},
               "crates": {k: {"display_name": gradient_legacy(c["title"], *c["hex"]), "lore": lore,
                              "material": {"donate": "yellow_shulker_box", "coins": "gold_block",
                                           "leaves": "lime_shulker_box"}[k],
                              "on_click": {"requirements": [{"check": "{playing} == true",
                                                             "commands": ["[MESSAGE] &cКто-то уже открывает этот кейс!",
                                                                          "[CLOSE]"],
                                                             "deny_commands": ["[TAKE_THIS_KEY]",
                                                                               f"[PLAY] {k}_wheel {k}", "[CLOSE]"]}]}}
                          for k, c in cases.items()}}
    put("menu/keylist.yml", dump(keylist))
    blocks = []
    for i, (k, c) in enumerate(cases.items()):
        x, y, z = c["pos"] or [i * 4, 100, 0]
        blocks.append({"block": "minecraft:ender_chest", "world": c["world"], "on_click_menu": f"bcases:{k}",
                       "idle_animation": "default:none", "pos": {"x": x, "y": y, "z": z},
                       "hologram": {"offsets": {"x": 0.5, "y": 1.9, "z": 0.5},
                                    "lines": [gradient_legacy("✦ " + c["title"] + " ✦", *c["hex"]),
                                              "&fНажми, чтобы открыть",
                                              f"&7Ключей: &f%bcases_keys_count_of_type_{k}%"]}})
    put("blocks.yml", dump({"blocks": blocks}))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="архив сервера (.tar.gz/.zip) или папка сервера")
    ap.add_argument("--out", default="bcases-out", help="куда положить plugins/BCases")
    ap.add_argument("--world", default="world")
    ap.add_argument("--donate-pos", default="", help="x,y,z блока донат-кейса")
    ap.add_argument("--coins-pos", default="")
    ap.add_argument("--leaves-pos", default="")
    ap.add_argument("--axis", default="Z", choices=["X", "Z"],
                    help="колесо крутится в плоскости X-Y (Z) или Z-Y (X): лицом к игрокам")
    ap.add_argument("--broadcast-legendary", action="store_true",
                    help="о легендарном призе писать ещё и всему серверу")
    ap.add_argument("--include", nargs="*", default=[], help="только эти группы")
    ap.add_argument("--exclude", nargs="*", default=[], help="эти группы не брать")
    ap.add_argument("--donate-cmd", default="lp user %player_name% parent add {group}")
    ap.add_argument("--coins-cmd", default="", help="например 'eco give %%player_name%% {amount}'")
    ap.add_argument("--leaves-cmd", default="", help="например 'points give %%player_name%% {amount}'")
    args = ap.parse_args()
    src = Source(Path(args.source))
    built = build(args, src)
    files = write(Path(args.out), built, args)
    rep = built["report"]
    print(json.dumps({"written": files, **rep}, ensure_ascii=False, indent=1))
    return 0 if rep["donors"] else 2


if __name__ == "__main__":
    sys.exit(main())
