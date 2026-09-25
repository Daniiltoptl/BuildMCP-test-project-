# BuildMCP

Плагин для Claude Code, с которым Claude строит Minecraft-спавны уровня топ-серверов: пишет процедурные скрипты постройки, смотрит на результат через рендер с настоящими текстурами, проверяет качество и сам вставляет готовое на сервер.

> Статус: в разработке. План: [docs/PLAN.md](docs/PLAN.md).

## Что внутри

- **MCP-сервер `buildmcp`** (Python): движок блоков, генераторы (острова, деревья, крыши, башни, дороги, 3D-текст), рендер, экспорт `.schem`, вставка на сервер.
- **Skill `spawn-builder`**: методичка по про-спавнам (композиция, палитры, глубина, органика, свет).
- **Агент `build-critic`**: смотрит рендеры и говорит, что исправить.
- **Мост BuildBridge** (плагин для Paper 1.21.x, WorldEdit не нужен): через него Claude вставляет постройки на сервер 1:1, с бэкапом и отменой, читает мир и видит, где стоит игрок.

## Установка (Claude Code на ПК)

1. Поставь [uv](https://docs.astral.sh/uv/getting-started/installation/):
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. В Claude Code:
   ```
   /plugin marketplace add Daniiltoptl/BuildMCP-test-project-
   /plugin install buildmcp@buildmcp
   ```
3. Перезапусти Claude Code. Первый запуск ставит зависимости (около минуты).

## Подключение к серверу

Лучший способ — мост **BuildBridge** (плагин для Paper и его форков, 1.21.x):

- вставка 1:1: точные состояния блоков без физики и обновлений соседей (ничего не падает, не течёт, заборы и ступени остаются как задумано), таблички, головы, баннеры, display-сущности, биомы;
- перед каждой вставкой делается бэкап, отмена — `server_undo` или `/bb undo` в игре;
- вставка идёт порциями по тикам (по умолчанию до 20 мс за тик), без лагов; совпадающие блоки пропускаются, поэтому повторная вставка после правок отправляет только изменения;
- Claude читает мир (рельеф, старый спавн), позицию игрока и его выделение WorldEdit и может телепортировать игрока к точкам обзора.

Если сервер на этом же ПК, попроси Claude: «поставь мост на сервер в папке …». Он вызовет `bridge_install`: положит `BuildBridge.jar` в `plugins/`, а после перезапуска сервера сам прочитает токен. Иначе скачай jar из [Releases](https://github.com/Daniiltoptl/BuildMCP-test-project-/releases), положи в `plugins/`, перезапусти сервер и впиши адрес и токен из `plugins/BuildBridge/config.yml` в настройки плагина (`/plugin` → buildmcp → configure). Для удалённого сервера используй SSH-туннель: `ssh -L 8765:127.0.0.1:8765 user@host`.

Запасной путь без плагина — **RCON** (`enable-rcon=true` и `rcon.password` в `server.properties`). Он медленнее, без бэкапа и чтения мира; до 1.21.5 блоки ставятся с обновлениями соседей.

Всегда доступен экспорт `.schem` для WorldEdit/FAWE.

## Разработка

```bash
cd plugins/buildmcp/server
uv sync
uv run pytest            # с JDK 21 тесты гоняют настоящий код моста в поддельном Paper-сервере

cd ../bridge
./gradlew jar            # BuildBridge-*.jar в build/libs (компиляция против paper-api)
```

CI (`.github/workflows/bridge.yml`) собирает мост и прогоняет его на настоящих серверах Paper 1.21.1, 1.21.4, 1.21.8 и последней версии: вставка, чтение и сравнение, отмена, RCON и сверка наших правил соединения блоков с тем, как их считает игра. Тег `bridge-v*` публикует jar в Releases.
