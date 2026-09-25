---
name: deploy
description: Вставить готовую постройку BuildMCP на Minecraft-сервер (через мост BuildBridge или RCON) с бэкапом, проверкой и настройкой точки спавна; либо выгрузить .schem.
---

# Сдача на сервер

1. Финальные проверки: `inspect(what="lint")` без error, `inspect(what="walk")` все цели достижимы.
2. `server_status`: доступен ли мост (лучший вариант) или RCON. Если ничего нет, сделай
   `export(format="schem")` и дай инструкцию из результата.
3. Куда вставлять:
   - координаты от пользователя;
   - «где я стою»: `server_player(name)` → позиция ног игрока = якорь;
   - по умолчанию исходные координаты сцены.
   Якорь сцены — маркер `anchor`, иначе `spawn`.
4. `server_paste(at=..., dry_run=True)`: покажи bbox и объём. Предупреди, если зона занята
   (`server_read` небольшого региона или `heightmap`).
5. `server_paste(...)` с бэкапом (по умолчанию). Дождись завершения задачи (`server_job`).
6. Настрой спавн: `server_cmd("setworldspawn x y z yaw")` (или команду spawn-плагина) по маркеру `spawn`.
   При необходимости WorldGuard-регион (`server_cmd`, см. `references/functional.md`).
7. `server_tp(player, marker="spawn")`: попроси пользователя посмотреть и прислать скриншоты.
8. Если не понравилось: `server_undo(job)` вернёт всё как было.
