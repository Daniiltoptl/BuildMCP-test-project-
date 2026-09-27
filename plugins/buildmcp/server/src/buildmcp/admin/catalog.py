"""Plugins BuildMCP knows by name, with where to get them (tried in order), and ready sets (stacks)
for typical servers. Anything else is installed by spec (modrinth:slug, hangar:slug, ...) after
plugins(action="search"). CI resolves and downloads every entry against the live sources."""

from __future__ import annotations

# alias: (display name, names in plugin.yml | velocity id, [sources], platforms, category, what it is for,
#         [requires: aliases, "a|b" = either])
_P = {
    # ---- core libraries and permissions
    "luckperms": ("LuckPerms", "LuckPerms", ["modrinth:luckperms"], "paper folia velocity", "core",
                  "права, группы, префиксы (ставится на каждый сервер сети и на прокси)", []),
    "vault": ("Vault", "Vault", ["github:MilkBowl/Vault#^Vault\\.jar$", "spigot:34315"], "paper", "core",
              "мост экономики и прав для других плагинов", []),
    "placeholderapi": ("PlaceholderAPI", "PlaceholderAPI", ["hangar:PlaceholderAPI", "spigot:6245"], "paper", "core",
                       "плейсхолдеры %...% для TAB, голограмм, меню", []),
    "protocollib": ("ProtocolLib", "ProtocolLib", ["github:dmulloy2/ProtocolLib#^ProtocolLib\\.jar$",
                                                   "hangar:ProtocolLib", "spigot:1997"], "paper", "core",
                    "библиотека пакетов (нужна части плагинов)", []),
    "packetevents": ("packetevents", "packetevents", ["modrinth:packetevents"], "paper folia velocity", "core",
                     "библиотека пакетов", []),
    # ---- essentials, chat, admin
    "essentialsx": ("EssentialsX", "Essentials", ["modrinth:essentialsx",
                                                   "github:EssentialsX/Essentials#^EssentialsX-[0-9.]+\\.jar$"],
                    "paper", "essentials", "базовые команды: /spawn /home /tpa /kit /msg, варпы, экономика", []),
    "essentialsx-chat": ("EssentialsX Chat", "EssentialsChat",
                         ["github:EssentialsX/Essentials#^EssentialsXChat-[0-9.]+\\.jar$"], "paper", "chat",
                         "формат чата с префиксами", ["essentialsx"]),
    "essentialsx-spawn": ("EssentialsX Spawn", "EssentialsSpawn",
                          ["github:EssentialsX/Essentials#^EssentialsXSpawn-[0-9.]+\\.jar$"], "paper", "essentials",
                          "спавн при входе и после смерти", ["essentialsx"]),
    "huskhomes": ("HuskHomes", "HuskHomes", ["modrinth:huskhomes"], "paper", "essentials",
                  "дома, варпы, /tpa, работает по сети", []),
    "maintenance": ("Maintenance", "Maintenance", ["modrinth:maintenance"], "paper velocity", "admin",
                    "режим техработ с MOTD и белым списком", []),
    "advancedban": ("AdvancedBan", "AdvancedBan", ["spigot:8695"], "paper", "admin", "баны, муты, варны", []),
    "plan": ("Plan", "Plan", ["modrinth:plan"], "paper velocity", "admin", "аналитика игроков в браузере", []),
    "discordsrv": ("DiscordSRV", "DiscordSRV", ["modrinth:discordsrv", "spigot:18494"], "paper", "admin",
                   "мост чата с Discord", []),
    "spark": ("spark", "spark", ["modrinth:spark"], "paper folia velocity", "perf",
              "профайлер: лаги, TPS, память (/spark profiler)", []),
    # ---- compatibility
    "viaversion": ("ViaVersion", "ViaVersion", ["modrinth:viaversion", "hangar:ViaVersion"], "paper velocity",
                   "compat", "вход с более новых клиентов (в сети — только на прокси)", []),
    "viabackwards": ("ViaBackwards", "ViaBackwards", ["modrinth:viabackwards", "hangar:ViaBackwards"],
                     "paper velocity", "compat", "вход со старых клиентов", ["viaversion"]),
    "viarewind": ("ViaRewind", "ViaRewind", ["modrinth:viarewind", "hangar:ViaRewind"], "paper velocity", "compat",
                  "клиенты 1.7–1.8", ["viabackwards"]),
    "geyser": ("Geyser", "Geyser-Spigot|Geyser-Velocity|geyser", ["modrinth:geyser"], "paper velocity", "compat", "вход с Bedrock", []),
    "floodgate": ("Floodgate", "floodgate", ["modrinth:floodgate"], "paper velocity", "compat",
                  "Bedrock-игроки без Java-аккаунта", []),
    # ---- world
    "worldedit": ("WorldEdit", "WorldEdit", ["modrinth:worldedit"], "paper", "build", "редактирование мира", []),
    "fastasyncworldedit": ("FastAsyncWorldEdit", "FastAsyncWorldEdit", ["modrinth:fastasyncworldedit"], "paper",
                           "build", "быстрый WorldEdit (ставится вместо WorldEdit)", []),
    "worldguard": ("WorldGuard", "WorldGuard", ["modrinth:worldguard", "hangar:WorldGuard"], "paper", "protect",
                   "регионы и флаги: защита спавна, pvp, мобы", ["worldedit|fastasyncworldedit"]),
    "coreprotect": ("CoreProtect", "CoreProtect", ["modrinth:coreprotect"], "paper", "protect",
                    "логи блоков и откат гриферства", []),
    "griefprevention": ("GriefPrevention", "GriefPrevention", ["hangar:GriefPrevention", "spigot:1884"], "paper",
                        "protect", "приваты золотой лопатой", []),
    "multiverse-core": ("Multiverse-Core", "Multiverse-Core", ["modrinth:multiverse-core", "hangar:Multiverse-Core"],
                        "paper", "world", "несколько миров", []),
    "voidgen": ("VoidGen", "VoidGen", ["modrinth:voidgen", "spigot:25391"], "paper", "world",
                "генератор пустых миров для лобби", []),
    "chunky": ("Chunky", "Chunky", ["modrinth:chunky", "hangar:Chunky"], "paper folia", "world",
               "прегенерация мира (меньше лагов при исследовании)", []),
    "chunkyborder": ("ChunkyBorder", "ChunkyBorder", ["modrinth:chunkyborder"], "paper", "world",
                     "граница мира кругом или квадратом", ["chunky"]),
    "bluemap": ("BlueMap", "BlueMap", ["modrinth:bluemap"], "paper", "world", "3D-карта мира в браузере", []),
    # ---- look and feel
    "tab": ("TAB", "TAB", ["modrinth:tab-was-taken"], "paper velocity", "ui",
            "таблист, ники с префиксами, скорборд, боссбар", []),
    "decentholograms": ("DecentHolograms", "DecentHolograms", ["modrinth:decentholograms", "spigot:96927"], "paper",
                        "ui", "голограммы", []),
    "fancyholograms": ("FancyHolograms", "FancyHolograms", ["modrinth:fancyholograms"], "paper", "ui",
                       "голограммы на display-сущностях", []),
    "fancynpcs": ("FancyNpcs", "FancyNpcs", ["modrinth:fancynpcs"], "paper folia", "ui",
                  "NPC с действиями: команды, сообщения, отправка на сервер сети", []),
    "citizens": ("Citizens", "Citizens", ["jenkins:https://ci.citizensnpcs.co/job/Citizens2#^Citizens-.*\\.jar$"],
                 "paper", "ui", "NPC (классика, много дополнений)", []),
    "deluxemenus": ("DeluxeMenus", "DeluxeMenus", ["spigot:11734"], "paper", "ui",
                    "меню из предметов, селектор серверов", []),
    "deluxehub": ("DeluxeHub", "DeluxeHub", ["spigot:49425"], "paper", "lobby",
                  "лобби: предметы, селектор, двойной прыжок, защита", []),
    "ajleaderboards": ("ajLeaderboards", "ajLeaderboards", ["modrinth:ajleaderboards"], "paper", "ui",
                       "топы игроков для голограмм и табличек", ["placeholderapi"]),
    "simple-voice-chat": ("Simple Voice Chat", "voicechat", ["modrinth:simple-voice-chat"], "paper", "fun",
                          "голосовой чат (нужен мод у игроков)", []),
    # ---- auth (offline-mode servers)
    "skinsrestorer": ("SkinsRestorer", "SkinsRestorer", ["modrinth:skinsrestorer"], "paper velocity", "auth",
                      "скины на offline-mode", []),
    "authmereloaded": ("AuthMeReloaded", "AuthMe", ["github:AuthMe/AuthMeReloaded#AuthMe.*\\.jar$", "spigot:6269"],
                       "paper", "auth", "регистрация и вход на offline-mode (одиночный сервер)", []),
    "limboapi": ("LimboAPI", "limboapi", ["modrinth:limboapi"], "velocity", "auth", "виртуальный лимбо на прокси", []),
    "limboauth": ("LimboAuth", "limboauth", ["modrinth:limboauth"], "velocity", "auth",
                  "регистрация и вход на прокси для offline-mode сети", ["limboapi"]),
    "fastlogin": ("FastLogin", "FastLogin", ["github:TuxCoding/FastLogin#FastLoginBukkit.*\\.jar$"], "paper", "auth",
                  "авто-вход лицензионных игроков вместе с AuthMe", []),
    # ---- anti-cheat and anarchy
    "grimac": ("GrimAC", "GrimAC", ["modrinth:grimac"], "paper folia", "anticheat", "античит", []),
    "anarchyexploitfixes": ("AnarchyExploitFixes", "AnarchyExploitFixes", ["modrinth:anarchyexploitfixes"],
                            "paper folia", "anarchy", "защита от крашей, дюпов и лаг-машин", []),
    "antipopup": ("AntiPopup", "AntiPopup", ["modrinth:antipopup"], "paper", "chat",
                  "убирает окно «Chat reports» у игроков", []),
    "freedomchat": ("FreedomChat", "FreedomChat", ["modrinth:freedomchat"], "paper", "chat",
                    "чат без подписей: никаких жалоб в Mojang", []),
    "signedvelocity": ("SignedVelocity", "SignedVelocity", ["modrinth:signedvelocity"], "paper velocity", "chat",
                       "правильная подпись чата через Velocity", []),
}

CATALOG: dict[str, dict] = {
    alias: {"alias": alias, "name": v[0], "plugin_names": v[1].split("|"), "sources": v[2],
            "platforms": v[3].split(), "category": v[4], "about": v[5], "requires": v[6]}
    for alias, v in _P.items()
}

# plugins that stand in for others (their plugin.yml says "provides")
PROVIDES: dict[str, list[str]] = {"fastasyncworldedit": ["worldedit"]}

STACKS: dict[str, dict] = {
    "proxy": {"about": "Velocity: права, техработы, вход с разных версий, профайлер",
              "plugins": ["luckperms", "maintenance", "viaversion", "viabackwards", "spark"]},
    "proxy-offline": {"about": "Velocity для пираток (offline-mode): + авторизация на прокси и скины",
                      "plugins": ["luckperms", "maintenance", "viaversion", "viabackwards", "spark", "limboapi",
                                  "limboauth", "skinsrestorer"]},
    "lobby": {"about": "лобби/хаб: права, NPC и голограммы, таб, защита, инструменты стройки",
              "plugins": ["luckperms", "placeholderapi", "fancynpcs", "fancyholograms", "tab", "worldedit",
                          "worldguard", "spark"]},
    "anarchy": {"about": "анархия: защита от крашей и дюпов, античит, прегенерация, чат без жалоб",
                "plugins": ["luckperms", "placeholderapi", "tab", "anarchyexploitfixes", "grimac", "chunky",
                            "freedomchat", "spark"]},
    "survival": {"about": "выживание: EssentialsX, приваты, логи, защита, экономика",
                 "plugins": ["luckperms", "vault", "placeholderapi", "essentialsx", "essentialsx-chat",
                             "essentialsx-spawn", "coreprotect", "worldedit", "worldguard", "griefprevention", "tab",
                             "chunky", "spark"]},
}


def names(entry: dict) -> set[str]:
    """Lower-case names an installed plugin of this entry can have (plugin.yml name, velocity id...)."""
    return {entry["alias"], entry["name"].lower(), *(n.lower() for n in entry["plugin_names"])}


def find(name: str) -> dict | None:
    """Catalog entry by alias, display name or plugin.yml name (case-insensitive)."""
    key = name.strip().lower()
    if key in CATALOG:
        return CATALOG[key]
    return next((e for e in CATALOG.values() if key in names(e)), None)


def overview(category: str = "") -> list[dict]:
    return [{"alias": e["alias"], "name": e["name"], "category": e["category"], "platforms": e["platforms"],
             "about": e["about"]} for e in CATALOG.values() if not category or e["category"] == category]
