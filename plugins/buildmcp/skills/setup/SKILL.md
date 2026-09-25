---
name: setup
description: Установка и диагностика BuildMCP — uv, Python-окружение, ассеты рендера, мост BuildBridge на сервере, RCON, настройки плагина.
---

# Настройка BuildMCP

1. `setup_check`: версии, папки, рендер (прогрев), скачанные ассеты, настройки сервера.
2. Если MCP-сервер `buildmcp` не запускается:
   - нужен `uv`. Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`,
     macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`;
   - затем перезапусти Claude Code. Первый запуск ставит зависимости (~1 мин), потом `/mcp`,
     переподключить `buildmcp`.
3. Ассеты рендера скачиваются при первом рендере с Mojang (запасной источник — зеркало на GitHub).
   Первая компиляция рендера занимает 15–60 с, потом берётся из кэша.
4. Сервер (Paper или его форки: Purpur, Pufferfish; версии 1.21.x). WorldEdit для моста не нужен.
   - Сервер на этом ПК: `bridge_install(server_dir="путь к папке сервера")`. Он положит BuildBridge.jar
     в `plugins/` (из GitHub Releases, или соберёт из исходников, если есть JDK 21).
   - Перезапусти сервер полностью (не `/reload`). Мост создаст токен в `plugins/BuildBridge/config.yml`.
   - Ещё раз `bridge_install(...)`: он прочитает токен (и RCON из `server.properties`) и подключится.
     Либо впиши URL и токен в настройки плагина (`/plugin` → buildmcp → configure).
   - Проверка: `server_status`. В игре: `/bb status`, `/bb undo`, `/bb backups`.
5. Сервер на VPS или хостинге: в `config.yml` моста `bind: 0.0.0.0` и `allowed-ips: [твой IP]`,
   открой порт 8765 только для себя. Лучше SSH-туннель: `ssh -L 8765:127.0.0.1:8765 user@host`, тогда
   адрес моста остаётся `http://127.0.0.1:8765`.
6. Запасной путь без плагина — RCON: `enable-rcon=true`, `rcon.port`, `rcon.password` в
   `server.properties` и те же данные в настройках BuildMCP. Медленнее, без бэкапа и чтения мира.
   До 1.21.5 блоки ставятся с обновлениями соседей (заборы и ступени пересчитает сама игра).
