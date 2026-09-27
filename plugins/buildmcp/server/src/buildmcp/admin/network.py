"""A network on this PC: a Velocity proxy in front of Paper backends.

link() writes what a working network needs and keeps every comment:
- velocity.toml: modern forwarding, [servers] = the backends at 127.0.0.1:<port>, the try order,
  forced hosts that only name existing servers, the bind port; the forwarding secret file
  (generated when missing);
- each backend: config/paper-global.yml proxies.velocity (enabled, online-mode, secret),
  server.properties online-mode=false and server-ip=127.0.0.1 (players only come in through the
  proxy), spigot.yml settings.bungeecord=false.
A proxy that never started gets velocity.toml from the template inside its jar, and a backend that
never started gets a paper-global.yml with just these keys (Paper fills in the rest), so nothing has
to run first.
"""

from __future__ import annotations

import secrets
import string
import zipfile
from pathlib import Path

from . import configs, props, registry
from .registry import ServerEntry


class NetworkError(RuntimeError):
    pass


def velocity_toml(proxy: ServerEntry) -> Path:
    """velocity.toml of the proxy; written from the jar's default-velocity.toml if it is not there yet."""
    p = proxy.path / "velocity.toml"
    if p.exists():
        return p
    jar = proxy.path / proxy.jar
    try:
        with zipfile.ZipFile(jar) as z:
            text = z.read("default-velocity.toml").decode("utf-8")
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise NetworkError(f"{p.name} does not exist and {jar.name} has no template ({e}): start the proxy "
                           "once so it writes its config") from e
    p.write_text(text, "utf-8")
    return p


def _secret(proxy: ServerEntry, doc) -> tuple[str, str]:
    """(secret, file name): the proxy's forwarding secret, generated if missing or empty."""
    name = str(doc.get("forwarding-secret-file") or "forwarding.secret")
    p = (proxy.path / name).resolve()
    if not p.is_relative_to(proxy.path.resolve()):
        raise NetworkError(f"forwarding-secret-file '{name}' points outside the proxy folder")
    try:
        s = p.read_text("utf-8").strip()
    except OSError:
        s = ""
    if not s:
        s = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))
        p.write_text(s, "utf-8")
    return s, name


def _try_order(backends: list[ServerEntry]) -> list[str]:
    lobbies = [b.name for b in backends if b.role.lower() in ("lobby", "hub", "auth", "limbo")]
    return lobbies or [backends[0].name]


def link(proxy: ServerEntry, backends: list[ServerEntry], try_order: list[str] | None = None,
         forced_hosts: dict | None = None, online_mode: bool | None = None, local_only: bool = True) -> dict:
    import tomlkit

    if not proxy.is_proxy:
        raise NetworkError(f"{proxy.name} is {proxy.software}, not a proxy (Velocity)")
    if not backends:
        raise NetworkError("no backends to link")
    names = [b.name for b in backends]
    for b in backends:
        if b.is_proxy:
            raise NetworkError(f"{b.name} is a proxy: a backend has to be Paper, Purpur or Folia")
    ports = [b.port for b in backends] + [proxy.port]
    if len(set(ports)) != len(ports):
        raise NetworkError(f"two servers share a port: {', '.join(f'{b.name}={b.port}' for b in backends)}, "
                           f"{proxy.name}={proxy.port}; move one with srv_link(..., proxy_port=) or srv_setup")
    order = try_order or _try_order(backends)
    bad = [n for n in order if n not in names]
    if bad:
        raise NetworkError(f"try names servers that are not linked: {bad}")

    report: dict = {"proxy": proxy.name, "backends": names, "try": order, "files": []}
    vt = velocity_toml(proxy)
    text = vt.read_text("utf-8")
    doc = tomlkit.parse(text)
    secret, secret_file = _secret(proxy, doc)
    changed = []

    def put(key: str, value) -> None:
        old = configs.plain(doc.get(key))
        if old != value:
            doc[key] = value
            changed.append({"path": key, "old": old, "new": value})

    mode = str(doc.get("player-info-forwarding-mode", "")).upper()
    if mode != "MODERN":
        put("player-info-forwarding-mode", "MODERN")
    if online_mode is not None:
        put("online-mode", bool(online_mode))
    proxy_online = bool(configs.plain(doc.get("online-mode", True)))
    bind = str(doc.get("bind", "0.0.0.0:25565"))
    host = bind.rsplit(":", 1)[0] if ":" in bind else "0.0.0.0"
    put("bind", f"{host}:{proxy.port}")

    servers = doc.get("servers")
    if servers is None:
        servers = tomlkit.table()
        doc["servers"] = servers
    for k in list(servers.keys()):
        if k != "try" and k not in names:
            changed.append({"path": f"servers.{k}", "old": configs.plain(servers[k]), "new": "(removed)"})
            del servers[k]
    for b in backends:
        addr = f"127.0.0.1:{b.port}"
        if configs.plain(servers.get(b.name)) != addr:
            changed.append({"path": f"servers.{b.name}", "old": configs.plain(servers.get(b.name)), "new": addr})
            servers[b.name] = addr
    if configs.plain(servers.get("try")) != order:
        changed.append({"path": "servers.try", "old": configs.plain(servers.get("try")), "new": order})
        if "try" in servers:
            del servers["try"]
        servers["try"] = order

    fh = doc.get("forced-hosts")
    if fh is not None:
        for h in list(fh.keys()):
            targets = configs.plain(fh[h]) or []
            if h.endswith(".example.com") or any(t not in names for t in targets):
                changed.append({"path": f'forced-hosts."{h}"', "old": targets, "new": "(removed)"})
                del fh[h]
    for h, targets in (forced_hosts or {}).items():
        targets = [targets] if isinstance(targets, str) else list(targets)
        miss = [t for t in targets if t not in names]
        if miss:
            raise NetworkError(f"forced host {h} names servers that are not linked: {miss}")
        if fh is None:
            fh = tomlkit.table()
            doc["forced-hosts"] = fh
        if configs.plain(fh.get(h)) != targets:
            changed.append({"path": f'forced-hosts."{h}"', "old": configs.plain(fh.get(h)), "new": targets})
            fh[h] = targets

    new_text = tomlkit.dumps(doc)
    if new_text != text:
        configs.validate("toml", new_text)
        b = configs._write(proxy, vt, new_text)
        report["files"].append({"server": proxy.name, "file": "velocity.toml", "changed": changed, "backup": b})
    report["forwarding_secret"] = f"{secret_file} (kept on the proxy, copied to every backend)"

    for b in backends:
        p = b.path / "server.properties"
        want = {"online-mode": False}
        if local_only:
            want["server-ip"] = "127.0.0.1"
        cur = props.read(p)
        if any(cur.get(k) != props.fmt(v) for k, v in want.items()):
            report["files"].append({"server": b.name, **configs.apply(b, "server.properties", want, create=True)})
        report["files"].append({"server": b.name, **configs.apply(b, "config/paper-global.yml", {
            "proxies.velocity.enabled": True, "proxies.velocity.online-mode": proxy_online,
            "proxies.velocity.secret": secret}, create=True)})
        sp = b.path / "spigot.yml"
        if sp.exists():
            _, sdoc, _ = configs.load(sp)
            try:
                bungee = configs.plain(configs.get_value(sdoc, ["settings", "bungeecord"]))
            except KeyError:
                bungee = False
            if bungee:
                report["files"].append({"server": b.name,
                                        **configs.apply(b, "spigot.yml", {"settings.bungeecord": False})})
        if b.network != proxy.name:
            b.network = proxy.name
            registry.put(b)
    if proxy.role != "proxy":
        proxy.role = "proxy"
        registry.put(proxy)
    report["files"] = [f for f in report["files"] if f.get("changed")]
    report["online_mode"] = proxy_online
    if not proxy_online:
        report["warning"] = ("offline-mode network: anyone can join with any name unless the proxy has an auth "
                             "plugin: plugins(action='install', names=['stack:proxy-offline'], server=proxy)")
    report["connect"] = f"players join the proxy at <this PC>:{proxy.port}"
    return report


def move_port(entry: ServerEntry, port: int) -> dict:
    """Give a server another port (server.properties server-port, or velocity.toml bind)."""
    old = entry.port
    if entry.is_proxy:
        import tomlkit

        vt = velocity_toml(entry)
        text = vt.read_text("utf-8")
        doc = tomlkit.parse(text)
        bind = str(doc.get("bind", "0.0.0.0:25565"))
        host = bind.rsplit(":", 1)[0] if ":" in bind else "0.0.0.0"
        doc["bind"] = f"{host}:{port}"
        configs._write(entry, vt, tomlkit.dumps(doc))
    else:
        configs.apply(entry, "server.properties", {"server-port": port}, create=True)
    entry.port = port
    registry.put(entry)
    return {"server": entry.name, "port": f"{old} -> {port}"}


def ensure_bind(proxy: ServerEntry) -> str:
    """Before the first start: velocity.toml from the jar template, bound to the registered port."""
    import tomlkit

    vt = velocity_toml(proxy)
    text = vt.read_text("utf-8")
    doc = tomlkit.parse(text)
    bind = str(doc.get("bind", "0.0.0.0:25565"))
    host = bind.rsplit(":", 1)[0] if ":" in bind else "0.0.0.0"
    want = f"{host}:{proxy.port}"
    if bind != want:
        doc["bind"] = want
        vt.write_text(tomlkit.dumps(doc), "utf-8")
    return want
