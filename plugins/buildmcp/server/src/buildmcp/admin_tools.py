"""MCP tools for running a whole server or network: servers, plugins, configs, own plugins, delegation.

Building (spawns, structures) stays with Claude and the building tools; nothing here hands a build to
another model.
"""

from __future__ import annotations

from buildmcp.mcp_server import _err, _fmt, server


def _entry(name: str = ""):
    from buildmcp.admin import registry

    return registry.get(name)


# ====================================================================== servers
@server.tool()
def srv_setup(name: str, dir: str, software: str = "paper", version: str = "latest", memory: str = "",
              port: int = 0, accept_eula: bool = False, adopt: bool = False, motd: str = "",
              online_mode: bool | None = None, java: str = "", role: str = "", network: str = "",
              initialize: bool = False) -> str:
    """Create a server in ``dir`` on this PC, or adopt=True to register an existing server folder.

    software: paper | purpur | folia | velocity (proxy). version: "latest", "1.21.11" or a line "1.21".
    Downloads the core (checksum verified), writes server.properties with RCON on a free port and a
    random password (kept by BuildMCP), start.sh/start.bat, and registers the server under ``name``
    (a-z, 0-9, -, _). memory: heap like "4G" (default 4G, proxy 1G). port 0 = a free one from 25565
    (proxy 25577). role/network: e.g. role="lobby", network="proxy" for a backend of the proxy "proxy".
    accept_eula=True writes eula=true: only when the owner agreed to https://aka.ms/MinecraftEULA — ask.
    initialize=True: start once and stop, so configs (paper-global.yml, velocity.toml...) exist to edit.
    """
    try:
        from buildmcp.admin import process, registry, setup

        if adopt:
            rep = setup.adopt(name, dir, accept_eula=accept_eula, memory=memory, java=java, role=role,
                              network=network)
        else:
            rep = setup.create(name, dir, software, version, memory=memory, port=port, accept_eula=accept_eula,
                               motd=motd, online_mode=online_mode, java=java, role=role, network=network)
        if initialize:
            e = registry.get(name)
            first = process.start(e, wait=True, timeout=300)
            rep["first_start"] = first
            if first.get("state") == "running":
                rep["first_stop"] = process.stop(e)
        return _fmt(rep)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def srv_list() -> str:
    """Registered servers with their state: running, port, core and version, role/network, which one is
    active (the building tools and server_cmd use the active one)."""
    try:
        from buildmcp.admin import process, registry

        act = registry.active_name()
        out = []
        for n, e in registry.load_all().items():
            row = {"name": n, "active": n == act, "software": e.software, "version": e.version, "port": e.port,
                   "role": e.role, "network": e.network, "dir": e.dir}
            row.update({k: v for k, v in process.status(e).items() if k != "name"})
            out.append(row)
        return _fmt(out if out else "no servers yet: srv_setup(name, dir, ...)")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def srv_use(name: str) -> str:
    """Make ``name`` the active server: server_paste, server_cmd, server_status... work with it."""
    try:
        from buildmcp.admin import registry

        e = registry.use(name)
        return _fmt({"active": e.name, "dir": e.dir, "rcon": bool(e.rcon_password), "bridge": bool(e.bridge_token)})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def srv_power(name: str = "", action: str = "status", wait: bool = True, timeout: float = 240.0) -> str:
    """Run a server: action = start | stop | restart | status | kill (default server: the active one).

    BuildMCP starts the server in the background under a small supervisor: it survives closing Claude
    Code, restarts after a crash and keeps the console for commands. start waits for "Done" and returns
    the problems it saw in the log (plugins that failed to load or enable, exceptions, a busy port).
    """
    try:
        from buildmcp.admin import process

        e = _entry(name)
        a = action.lower().strip()
        if a == "start":
            res = process.start(e, wait=wait, timeout=timeout)
        elif a == "stop":
            res = process.stop(e, timeout=min(timeout, 180.0))
        elif a == "restart":
            res = process.restart(e, timeout=timeout)
        elif a == "kill":
            res = process.kill(e)
        elif a == "status":
            res = process.status(e)
        else:
            return "Error: action must be start | stop | restart | status | kill"
        res["server"] = e.name
        return _fmt(res)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@server.tool()
def srv_log(name: str = "", lines: int = 60, grep: str = "", problems: bool = False) -> str:
    """Tail of the server log (logs/latest.log). grep: regex filter. problems=True: only the lines that look
    like errors (failed plugins, exceptions, bind/EULA/Java problems) from the whole recent log."""
    try:
        from buildmcp.admin import process

        e = _entry(name)
        if problems:
            found = process.problems(process.log_lines(e, lines=20000), limit=max(lines, 10))
            return "\n".join(found) if found else "(no problems in the recent log)"
        out = process.log_lines(e, lines=max(1, min(lines, 2000)), grep=grep)
        return "\n".join(out) if out else "(log is empty)"
    except Exception as e:  # noqa: BLE001
        return _err(e)
