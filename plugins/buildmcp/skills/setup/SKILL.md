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
4. Сервер (Paper/Purpur 1.21.x):
   - поставь WorldEdit или FastAsyncWorldEdit;
   - мост: `bridge_install(server_dir)`, если сервер на этом ПК, или скачай BuildBridge.jar из
     GitHub Releases репозитория и положи в `plugins/`;
   - перезапусти сервер. Токен появится в `plugins/BuildBridge/config.yml`;
   - впиши URL и токен в настройки плагина (`/plugin` → buildmcp → configure), затем
     `server_status`;
   - запасной путь RCON: `enable-rcon=true`, `rcon.port`, `rcon.password` в `server.properties`
     и те же данные в настройках плагина.
5. Сервер на VPS: открой порт моста только для своего IP или используй SSH-туннель
   (`ssh -L 8765:127.0.0.1:8765 user@host`).
