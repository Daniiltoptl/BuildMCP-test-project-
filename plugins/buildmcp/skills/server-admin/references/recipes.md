# Рецепты

Ключи конфигов меняются от версии к версии. Перед `config set` найди ключ через
`config(action="find", pattern=...)`. Если ключа нет, почитай документацию плагина, а не придумывай
путь. Команды ниже отправляются через `server_cmd(command, server=...)` без `/`.

## Права: LuckPerms

```
lp creategroup admin
lp group admin permission set * true
lp group admin meta setprefix 100 "&c[Админ] "
lp creategroup vip
lp group vip parent add default
lp group vip meta setprefix 50 "&6[VIP] "
lp user <ник> parent set admin
lp group default permission set essentials.spawn true
```

- Проверка: `lp user <ник> info`, `lp group vip listmembers`.
- Префиксы в чате и табе показывает TAB или EssentialsX Chat, а берут они их из LuckPerms (через Vault или PlaceholderAPI).
- В сети команды выполняются на каждом сервере отдельно, если у LuckPerms нет общей базы (см. `network.md`).

## Спавн и защита

1. Точка спавна после `server_paste`:
   - `setworldspawn X Y Z` (координаты из `anchor_world` отчёта вставки);
   - `gamerule spawnRadius 0`;
   - в `server.properties` поставь `spawn-protection=0`, защиту держит WorldGuard.
2. Регион WorldGuard. Координаты углов возьми из bbox проекта.
   - В игре: владелец выделяет углы топором WorldEdit, потом `rg define spawn`.
   - Из консоли (новый WorldEdit умеет выделять из консоли): `//world world`, `//pos1 x1,y1,z1`, `//pos2 x2,y2,z2`, затем `rg define spawn`.
     Если консоль отказывает, попроси владельца выделить в игре.
3. Флаги (из консоли с `-w world`):
   ```
   rg flag -w world spawn pvp deny
   rg flag -w world spawn mob-spawning deny
   rg flag -w world spawn tnt deny
   rg flag -w world spawn fall-damage deny
   ```
   Строить в регионе и так могут только его участники.
4. Лобби-мир целиком:
   - `gamerule doDaylightCycle false`, `time set 6000`;
   - `gamerule doWeatherCycle false`;
   - `gamerule doMobSpawning false`;
   - `gamerule fallDamage false`;
   - `gamerule keepInventory true`;
   - `gamerule announceAdvancements false`.

## Лобби: NPC ведёт на режим

- Плагины на лобби: `stack:lobby` (FancyNpcs, FancyHolograms, TAB, WorldGuard, LuckPerms, PlaceholderAPI).
- NPC создаёт владелец в игре, стоя на маркере NPC из проекта. Синтаксис зависит от версии, сверь с `/npc help`:
  ```
  /npc create anarchy
  /npc skin anarchy <ник со скином>
  /npc displayname anarchy <gold><bold>АНАРХИЯ
  /npc turn_to_player anarchy true
  /npc action anarchy any_click add send_to_server anarchy
  ```
- Если в постройке уже стоит наша голограмма (text_display), убери её перед голограммой плагина: `kill @e[type=text_display,distance=..4]` рядом с NPC (см. README примера antique_hub).
- Без NPC можно сделать devplugin с командой `/play <сервер>`. Он шлёт игрока через канал BungeeCord, Velocity его понимает: у него по умолчанию `bungee-plugin-message-channel = true`.
  ```java
  getServer().getMessenger().registerOutgoingPluginChannel(this, "BungeeCord");
  // в onCommand:
  ByteArrayDataOutput out = ByteStreams.newDataOutput();   // com.google.common.io, есть в Paper
  out.writeUTF("Connect");
  out.writeUTF(args[0]);
  player.sendPluginMessage(this, "BungeeCord", out.toByteArray());
  ```

## Анархия

1. `stack:anarchy`: AnarchyExploitFixes, GrimAC, Chunky, FreedomChat, TAB, LuckPerms, PlaceholderAPI.
2. `server.properties`:
   - `difficulty=hard`, `spawn-protection=0`;
   - `view-distance=8`, `simulation-distance=6` (подбирай по онлайну и железу);
   - `max-players` по брифу.
3. Производительность, `config/paper-world-defaults.yml` (каждый ключ сверяй через `find`):
   - `environment.optimize-explosions: true`
   - `misc.redstone-implementation: ALTERNATE_CURRENT`
   - `collisions.max-entity-collisions: 2`
   - `chunks.max-auto-save-chunks-per-tick: 8`
   - `entities.armor-stands.tick: false`
   - `tick-rates.grass-spread: 4`

   В `spigot.yml`:
   - `world-settings.default.merge-radius.item: 3.5`
   - `world-settings.default.merge-radius.exp: 4.0`
4. Прегенерация до открытия, долго, пока никого нет:
   ```
   chunky world world
   chunky radius 5000
   chunky start
   ```
   Прогресс: `chunky progress`. Потом `worldborder set 10000`: это диаметр, граница на ±5000.
5. После старта: `srv_log(problems=True)`, `spark tps`, `spark health`.

## Выживание

- `stack:survival`: EssentialsX (+Chat, +Spawn), Vault, LuckPerms, CoreProtect, WorldEdit/Guard, GriefPrevention, TAB, Chunky.
- `/setspawn` EssentialsX ставится в игре. Настройки: `config(action="find", file="Essentials", pattern="spawn|teleport")`.
- Откат гриферства: CoreProtect, `co rollback u:<ник> t:1h r:20`. Выполняется в игре или из консоли с `r:#global`.

## Тексты, MOTD, сообщения

- MOTD сети: `velocity.toml` → `motd` (MiniMessage, например `<gradient:gold:red>АНАРХИЯ</gradient>`).
- MOTD одиночного сервера: `server.properties` → `motd`.
- Перевод и стиль сообщений плагинов отдавай Gemini: `delegate(task="Переведи на русский, сохрани ключи и плейсхолдеры, цвета MiniMessage", files=[".../messages.yml"])`.
  Результат проверь и запиши через `config(action="write", ...)`: он валидирует YAML и делает бэкап.

## Свой плагин (devplugin)

1. `devplugin(action="new", name="HubTools", commands=["play"], softdepend=["PlaceholderAPI"])`.
2. Пиши код своими файловыми инструментами в `src/main/java/...`.
   - API установленных на сервере плагинов уже на classpath.
   - Лишние jar кладутся в `lib/`.
   - Команды из `commands` есть в plugin.yml; для новых допиши `plugin.yml` сам.
3. `devplugin(action="deploy", name="HubTools", restart=True)`:
   - ошибки компиляции приходят файлом, строкой и кодом;
   - после старта в `start.plugins.HubTools` будет `enabled` или причина.
4. Проверка: `server_cmd("play anarchy")` из консоли даст «только для игроков», это нормально. Попроси владельца проверить в игре.
5. Новая версия: `devplugin(action="deploy", name=..., bump="patch", restart=True)`.

Простой код (листенер, команда, конфиг) можно набросать через Gemini:
`delegate(task=..., to="gemini", edit=True, workdir=<папка проекта>)`. Потом сам прочитай diff,
собери и проверь. Архитектуру, работу с потоками и базами данных и всё, что касается безопасности, пиши сам.

## Диагностика

- «Плагин не включился»: причина в `plugins(action="list")` → `last_start`, подробности в `srv_log(grep="ИмяПлагина", lines=80)`.
- «Сервер не стартует»: `srv_power(action="start")` → `problems`. Частые причины:
  - занят порт (`FAILED TO BIND`);
  - нет EULA;
  - старая Java: BuildMCP сам ищет подходящую, иначе поставь Temurin.
- Лаги: `spark profiler start --timeout 120`, потом ссылка из `srv_log(grep="spark")`.
