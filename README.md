# BuildMCP

Плагин для Claude Code, с которым Claude строит Minecraft-спавны уровня топ-серверов: пишет процедурные скрипты постройки, смотрит на результат через рендер с настоящими текстурами, проверяет качество и сам вставляет готовое на сервер.

> Статус: в разработке. План: [docs/PLAN.md](docs/PLAN.md).

## Что внутри

- **MCP-сервер `buildmcp`** (Python): движок блоков, генераторы (острова, деревья, крыши, башни, дороги, 3D-текст), рендер, экспорт `.schem`, вставка на сервер.
- **Skill `spawn-builder`**: методичка по про-спавнам (композиция, палитры, глубина, органика, свет).
- **Агент `build-critic`**: смотрит рендеры и говорит, что исправить.
- **Мост BuildBridge** (Paper 1.21 + WorldEdit/FAWE): через него Claude вставляет постройки на сервер 1:1, с бэкапом и отменой.

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

Подключение к серверу описано в разделе про BuildBridge (появится после этапа 5).

## Разработка

```bash
cd plugins/buildmcp/server
uv sync
uv run pytest
```
