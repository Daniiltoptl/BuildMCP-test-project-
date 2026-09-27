# Сеть на Velocity

```
игроки ──► Velocity :25565 (online-mode, авторизация, Via, TAB, Maintenance)
              │ modern forwarding + секрет
              ├──► lobby   127.0.0.1:25566  (online-mode=false, velocity.enabled)
              └──► anarchy 127.0.0.1:25567
```

## Порядок

1. `srv_setup("proxy", dir, "velocity", memory="1G")`. Первым, чтобы прокси занял 25565.
2. Бэкенды: `srv_setup("lobby", dir, "paper", version, memory="3G", role="lobby", network="proxy", accept_eula=...)`.
   Потом `anarchy` и остальные.
3. `srv_link("proxy", ["lobby", "anarchy"], try_order=["lobby"], online_mode=True, proxy_port=25565, restart=True)`.
   - Если бэкенд уже стоит на 25565, `proxy_port` пересадит его на свободный порт. Перед этим оба сервера нужно остановить.
   - Повторный вызов ничего не ломает. Его можно делать после добавления нового бэкенда.
4. Плагины:
   - прокси: `plugins(action="install", names=["stack:proxy"], server="proxy", restart=True)`;
   - бэкенды: свои наборы.
5. Проверка:
   - `srv_log(name="proxy", problems=True)`;
   - `server_cmd("velocity plugins", server="proxy")`;
   - вход в игру через адрес прокси. В лобби должен работать `/server anarchy` (если есть право `velocity.command.server`).

## Что где ставить

| плагин | прокси | бэкенды |
|---|---|---|
| ViaVersion, ViaBackwards (ViaRewind) | да | нет: в сети они только на прокси |
| LuckPerms | да | да, на каждом |
| TAB | для общего таба на всю сеть | или на каждом свой |
| Maintenance | да: техработы на всю сеть | по желанию |
| Geyser + Floodgate (Bedrock) | да | Floodgate только там, где нужен его API, и с тем же `key.pem` |
| LimboAPI + LimboAuth (пиратки) | да | нет |
| SkinsRestorer | да | нет |
| spark | `stack:proxy` ставит его (`/sparkv`) | уже встроен в Paper 1.21+ (`/spark`) |
| SignedVelocity | да | да, пара «прокси + бэкенды» |

Права LuckPerms в сети:
- **раздельно:** H2 по умолчанию, на каждом сервере свои права. Просто.
- **общие:** одна MySQL/MariaDB. На всех серверах одинаковые `storage-method: mysql` и `data.*`,
  плюс `messaging-service: sql`. Правь через `config(action="set", file="LuckPerms", ...)` на каждом.

## Лицензия или пиратки

- `online_mode=True`: Velocity проверяет аккаунты Mojang. Самое безопасное.
- `online_mode=False`: зайти может кто угодно под любым ником. Поэтому обязательно:
  - `stack:proxy-offline` (LimboAuth — регистрация и вход в лимбо на прокси, SkinsRestorer);
  - при желании FastLogin, чтобы лицензионные игроки входили без пароля.
- Бэкенды всегда `online-mode=false`, это делает `srv_link`. Без прокси на них не зайти:
  - Paper отвергает вход без секрета («This server requires you to connect with Velocity»);
  - `server-ip=127.0.0.1` закрывает бэкенд от внешней сети.

## Порты и доступ снаружи

- Наружу открыт только порт прокси (TCP 25565). Для Bedrock ещё UDP 19132.
- Дома: проброс порта на роутере на этот ПК и разрешение в брандмауэре Windows.
- RCON (25575+) и мост BuildBridge (8765) наружу не открывай никогда.
- Домены: `forced_hosts={"anarchy.example.net": ["anarchy"]}` в `srv_link`. Тогда вход по этому
  адресу ведёт сразу на анархию. DNS: A-запись на IP, для другого порта SRV-запись.

## Перезапуски

- Бэкенды можно перезапускать при работающем прокси. Игроки на них вылетят на сервер из `try` (лобби).
- Прокси перезапускай последним. После правки velocity.toml нужен именно перезапуск прокси.
- Изменил порт или имя бэкенда? Снова вызови `srv_link`.
