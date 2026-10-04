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


# ====================================================================== plugins
@server.tool()
def plugins(action: str = "list", names: list[str] | str | None = None, server: str = "", query: str = "",
            category: str = "", deps: bool = True, dry_run: bool = False, force: bool = False,
            keep_data: bool = True, restart: bool = False) -> str:
    """Plugins of a registered server (default: the active one).

    action:
      catalog  plugins BuildMCP knows by name (filter: category) and ready stacks (lobby, anarchy,
               survival, proxy, proxy-offline).
      search   find plugins on Modrinth, Hangar and SpigotMC by ``query`` for this server's platform.
      info     the build that would be installed for each of ``names`` (version, Minecraft versions,
               dependencies, page) without downloading.
      install  ``names``: catalog aliases (luckperms), stacks (stack:lobby) or specs (modrinth:slug,
               hangar:slug, spigot:id, github:owner/repo#asset-regex, jenkins:job-url#regex,
               url:https://...jar). Picks the build for the platform (Paper/Purpur, Folia, Velocity) and
               the Minecraft version, verifies the checksum and the plugin descriptor, pulls hard
               dependencies (deps=True). force=True reinstalls ones already there. dry_run=True: plan only.
      list     installed plugins, where they come from, and whether they enabled at the last start.
      update   newer builds for ``names`` (default: all whose source is known).
      remove   jars (keep_data=False: also their folders) go to .buildmcp/removed/<time>.
      disable / enable   X.jar <-> X.jar.disabled.
    restart=True: stop a running server before the files change, then start it and report which plugins
    enabled and which failed (and why). Without it, changes load at the next restart.
    """
    try:
        from buildmcp.admin import catalog, installer, process

        a = action.lower().strip()
        if isinstance(names, str):
            names = names.replace(",", " ").split()
        names = [n for n in (names or []) if n and n.strip()]
        if a == "catalog":
            return _fmt({"plugins": catalog.overview(category.strip().lower()),
                         "stacks": {k: v for k, v in catalog.STACKS.items()},
                         "categories": sorted({e["category"] for e in catalog.CATALOG.values()})})
        e = _entry(server)
        platform, mc = installer.platform_of(e), installer.mc_of(e)
        if a == "search":
            q = query.strip() or " ".join(names)
            if not q:
                return "Error: search needs query"
            return _fmt(installer.search(q, platform, mc))
        if a == "info":
            if not names:
                return "Error: info needs names"
            return _fmt(installer.info(names, platform, mc))
        if a == "list":
            log = process.log_lines(e, lines=20000)
            rep = installer.listing(e, log)
            rep["running"] = process.is_running(e)
            return _fmt(rep)
        if a not in ("install", "update", "remove", "disable", "enable"):
            return "Error: action must be catalog | search | info | install | list | update | remove | disable | enable"
        if a != "update" and not names:
            return f"Error: {a} needs names"
        was_running = process.is_running(e)
        stopped: dict = {}

        def before_commit() -> None:
            if restart and was_running and not stopped:
                stopped.update(process.stop(e))

        if a == "install":
            rep = installer.install(e, names, deps=deps, dry_run=dry_run, force=force, before_commit=before_commit)
        elif a == "update":
            rep = installer.update(e, names or None, dry_run=dry_run, before_commit=before_commit)
        elif dry_run:
            return "Error: dry_run is for install and update"
        else:
            before_commit()
            rep = (installer.remove(e, names, keep_data=keep_data) if a == "remove"
                   else installer.set_enabled(e, names, enabled=(a == "enable")))
        if stopped:
            rep["stopped"] = stopped.get("state")
        if dry_run or not rep.get("changed"):
            if stopped:  # nothing changed after all: bring it back
                rep["start"] = _start_report(e, installer, process, [])
            return _fmt(rep)
        touched = [r.get("name") or r.get("want") for r in rep.get("result", []) if isinstance(r, dict)
                   and r.get("status") in ("installed", "updated", "enabled")]
        if restart:
            rep["start"] = _start_report(e, installer, process, touched)
        elif was_running:
            rep["next"] = "the server is running: restart it to load the changes (plugins(..., restart=True) " \
                          "or srv_power(action='restart'))"
        return _fmt(rep)
    except Exception as ex:  # noqa: BLE001
        return _err(ex)


def _start_report(e, installer, process, touched: list[str]) -> dict:
    """Start the server and say how the plugins that just changed fared."""
    try:
        r = process.start(e, wait=True, timeout=300)
    except Exception as ex:  # noqa: BLE001
        return {"state": "not started", "error": str(ex)}
    out = {"state": r.get("state"), "seconds": r.get("seconds")}
    if r.get("problems"):
        out["problems"] = r["problems"][:15]
    report = installer.load_report(process.log_lines(e, lines=20000))
    if touched:
        out["plugins"] = {n: (report.get(str(n).lower()) or {"state": "not seen in the log"})["state"]
                          + ((": " + report[str(n).lower()]["why"]) if report.get(str(n).lower(), {}).get("why")
                             else "") for n in touched}
    bad = {v["name"]: v["state"] + (": " + v["why"] if v.get("why") else "") for v in report.values()
           if v["state"] != "enabled"}
    if bad:
        out["failed_plugins"] = bad
    return out


# ====================================================================== configs
@server.tool()
def config(action: str = "files", file: str = "", path: str = "",
           value: str | int | float | bool | list | dict | None = None, changes: dict | None = None,
           unset: list[str] | None = None, text: str = "", pattern: str = "", server: str = "", under: str = "",
           depth: int = 2, backup: str = "", reveal: bool = False, restart: bool = False) -> str:
    """Config files of a registered server (default: the active one), changed in place with comments kept.

    action:
      files    the config files (under="plugins/LuckPerms" narrows it).
      get      a whole file, or one value with path="proxies.velocity.enabled".
      outline  the key tree of a big file (depth levels) with short values.
      find     keys or values matching the regex ``pattern`` in every config (or only ``file``).
      set      path + value, or changes={"path": value, ...}; unset=[paths] removes keys.
      write    replace (or create) ``file`` with ``text``, after checking it parses.
      diff     what changed since the last backup (or ``backup``); backups lists them;
      restore  brings one back (default: the latest).
    file: a path in the server folder, a shortcut (server, paper-global, paper-world, spigot, bukkit, purpur,
    velocity) or a plugin name (LuckPerms -> plugins/LuckPerms/config.yml). Paths: dots between keys, [n]
    for list items, quotes around keys that contain dots: 'messages."no.permission"'. YAML, TOML, JSON and
    .properties keep comments and order; every write keeps a backup. Secrets (passwords, tokens, the
    forwarding secret) show as *** unless reveal=True. Most configs load at start: restart=True restarts a
    running server after a change (many plugins also reload by command, e.g. server_cmd("lp reload")).
    """
    try:
        from buildmcp.admin import configs, process

        e = _entry(server)
        a = action.lower().strip()
        if a == "files":
            return _fmt(configs.list_files(e, under))
        if a == "find":
            if not pattern:
                return "Error: find needs pattern (a regex)"
            return _fmt(configs.find(e, pattern, [file] if file else None, reveal=reveal))
        if not file:
            return f"Error: {a} needs file"
        if a == "get":
            return _fmt(configs.read(e, file, path, reveal=reveal))
        if a == "outline":
            return _fmt(configs.outline(e, file, depth=max(1, min(depth, 6)), reveal=reveal))
        if a == "backups":
            return _fmt(configs.backups(e, file))
        if a == "diff":
            return _fmt(configs.diff(e, file, backup, reveal=reveal))
        if a == "set":
            ch = dict(changes or {})
            if path:
                ch[path] = value
            if not ch and not unset:
                return "Error: set needs path and value, changes={...} or unset=[...]"
            rep = configs.apply(e, file, ch, unset, create=True)
        elif a == "write":
            if not text:
                return "Error: write needs text"
            rep = configs.write_text(e, file, text)
        elif a == "restore":
            rep = configs.restore(e, file, backup)
        else:
            return "Error: action must be files | get | outline | find | set | write | diff | backups | restore"
        wrote = bool(rep.get("changed") or rep.get("written") or rep.get("restored"))
        if wrote and process.is_running(e):
            if restart:
                r = process.restart(e)
                rep["restart"] = {k: r.get(k) for k in ("state", "seconds", "problems") if r.get(k)}
            else:
                rep["next"] = "the server is running: the change loads at the next restart (restart=True does it)"
        return _fmt(rep)
    except Exception as ex:  # noqa: BLE001
        return _err(ex)


# ====================================================================== network
@server.tool()
def srv_link(proxy: str, backends: list[str] | str | None = None, try_order: list[str] | None = None,
             forced_hosts: dict | None = None, online_mode: bool | None = None, proxy_port: int = 0,
             local_only: bool = True, restart: bool = False) -> str:
    """Wire a Velocity proxy and its backends into one network (modern forwarding), keeping all comments.

    backends: registered Paper/Purpur/Folia servers (default: the ones whose network is this proxy).
    try_order: where players land first and fall back to (default: backends with role lobby/hub, else the
    first). forced_hosts: {"play.example.net": ["lobby"]}. online_mode: the proxy checks accounts with
    Mojang (True: licensed) or not (False: then add auth on the proxy, stack:proxy-offline).
    proxy_port: the public port (usually 25565); a stopped backend holding it moves to a free port.
    local_only: backends listen on 127.0.0.1 only, so nobody can skip the proxy.
    Writes velocity.toml (forwarding, [servers], try, forced hosts, bind), the forwarding secret
    (generated once, copied into every backend's paper-global.yml, never shown), online-mode=false on the
    backends. restart=True (re)starts all of them, backends first, and reports how they came up.
    """
    try:
        from buildmcp.admin import network, process, registry, setup

        p = registry.get(proxy)
        if isinstance(backends, str):
            backends = backends.replace(",", " ").split()
        alls = registry.load_all()
        if backends:
            bs = [registry.get(n) for n in backends]
        else:
            bs = [x for x in alls.values() if not x.is_proxy and x.network == p.name]
            if not bs:
                others = [x.name for x in alls.values() if not x.is_proxy]
                return f"Error: say which backends to link: backends=[...] (registered: {', '.join(others) or 'none'})"
        moved = []
        if proxy_port and p.port != proxy_port:
            holder = next((x for x in alls.values() if x.name != p.name and x.port == proxy_port), None)
            if holder is not None:
                if process.is_running(holder):
                    return f"Error: {holder.name} runs on {proxy_port}: stop it first so it can move"
                taken = {x.port for x in alls.values()} | {proxy_port}
                moved.append(network.move_port(holder, setup.pick_port(25566, taken)))
                bs = [registry.get(x.name) for x in bs]
            if process.is_running(p):
                return f"Error: {p.name} is running: stop it first to change its port"
            moved.append(network.move_port(p, proxy_port))
            p = registry.get(p.name)
        rep = network.link(p, bs, try_order=try_order, forced_hosts=forced_hosts, online_mode=online_mode,
                           local_only=local_only)
        if moved:
            rep["ports"] = moved
        running = [x for x in bs + [p] if process.is_running(x)]
        if restart:
            rep["restart"] = {}
            for x in bs + [p]:
                x = registry.get(x.name)
                r = process.restart(x) if x in running or process.is_running(x) else process.start(x)
                rep["restart"][x.name] = {k: r.get(k) for k in ("state", "seconds", "problems", "java") if r.get(k)}
        elif running:
            rep["next"] = (f"restart {', '.join(x.name for x in running)} to load it (srv_link(..., restart=True) or "
                           "srv_power), backends first")
        else:
            rep["next"] = "start the backends, then the proxy: srv_power(name, 'start')"
        return _fmt(rep)
    except Exception as ex:  # noqa: BLE001
        return _err(ex)


# ====================================================================== own plugins
def _names_list(v) -> list[str]:
    if isinstance(v, str):
        return v.replace(",", " ").split()
    return [x for x in (v or []) if x]


@server.tool()
def devplugin(action: str = "list", name: str = "", server: str = "", platform: str = "", package: str = "",
              description: str = "", commands: list[str] | str | None = None, depend: list[str] | str | None = None,
              softdepend: list[str] | str | None = None, dir: str = "", bump: str = "",
              restart: bool = False) -> str:
    """Your own plugins: make a project, build it against the server, deploy it.

    action:
      new     a Java 21 project: Paper/Folia (plugin.yml, config.yml, a main class with onEnable and the
              ``commands``) or Velocity (@Plugin class). Returns the folder: write the code there with your
              file tools. platform defaults to the server's; depend/softdepend: plugin names it uses.
      build   javac against the server's own jars (its exact API version), the plugins installed there (so
              their APIs can be used) and the project's lib/*.jar. Errors come back as file, line, message
              and the code line.
      deploy  build, then put the jar into the server's plugins/ (the previous build goes to the backup).
              bump="patch" | "minor" | "major" raises the version first. restart=True restarts the server
              and says whether the plugin enabled, or why not.
      list    projects, their builds and where they are deployed.
    """
    try:
        from buildmcp.admin import devplugin as dp
        from buildmcp.admin import installer, process

        a = action.lower().strip()
        if a == "list":
            return _fmt(dp.list_projects() or "no projects yet: devplugin(action='new', name=...)")
        if not name:
            return f"Error: {a} needs name"
        if a == "new":
            plat = platform
            if not plat:
                try:
                    plat = installer.platform_of(_entry(server))
                except Exception:  # noqa: BLE001 - no server registered yet
                    plat = "paper"
            return _fmt(dp.create(name, plat, package, description, _names_list(commands), _names_list(depend),
                                  _names_list(softdepend), dir=dir))
        e = _entry(server)
        if a == "build":
            return _fmt(dp.build(name, e))
        if a != "deploy":
            return "Error: action must be new | build | deploy | list"
        if bump:
            dp.bump(name, bump.lower())
        was_running = process.is_running(e)
        stopped: dict = {}

        def before_commit() -> None:
            if restart and was_running and not stopped:
                stopped.update(process.stop(e))

        rep = dp.deploy(name, e, before_commit=before_commit)
        if not rep.get("changed"):
            if stopped:
                rep["start"] = _start_report(e, installer, process, [])
            return _fmt(rep)
        touched = [r.get("name") for r in rep.get("result", []) if r.get("name")]
        if restart:
            rep["start"] = _start_report(e, installer, process, touched)
        elif was_running:
            rep["next"] = "the server is running: restart it to load the new build (deploy with restart=True)"
        return _fmt(rep)
    except Exception as ex:  # noqa: BLE001
        return _err(ex)


# ====================================================================== helpers
@server.tool()
def delegate(task: str = "", to: str = "auto", kind: str = "text", files: list[str] | str | None = None,
             workdir: str = "", edit: bool = False, model: str = "", action: str = "run",
             timeout: float = 300.0) -> str:
    """Give an undemanding task to a cheaper model and save Claude's limits: the Gemini CLI on this PC or
    the Mistral API. Good for: texts (plugin messages, translations, MOTDs, lore, descriptions), explaining
    a log or a stack trace, drafting or converting configs, small plugin code, bulk edits of text files.
    NEVER building: spawns and structures, and how they look (palette, layout, terrain), are your own
    work with the building tools; Gemini and Mistral build badly (refused here). Do not call the gemini
    CLI from a shell for it either.
    Not for security decisions, the network setup, anything that needs BuildMCP tools, or the final check.

    to: gemini (the default when installed) | mistral (bulk and trivial text; codestral for kind="code") |
    auto. kind: text | code. files: files sent along with the task (read-only).
    edit=True (Gemini): it may change files inside workdir, which must be a devplugin project; the diff
    comes back. action: run | status (what is installed and configured) | usage (calls, tokens per helper).
    The answer comes from a weaker model: read it and check it (compile, validate YAML, try it on the
    server) before using it.
    """
    try:
        from buildmcp.admin import delegate as dg

        a = action.lower().strip()
        if a == "status":
            return _fmt(dg.status())
        if a == "usage":
            return _fmt(dg.usage())
        if a != "run":
            return "Error: action must be run | status | usage"
        fl = [files] if isinstance(files, str) and files else list(files or [])
        return _fmt(dg.run(task, to=to, kind=kind, files=fl, workdir=workdir, edit=edit, model=model,
                           timeout=max(10.0, min(timeout, 1800.0))))
    except Exception as ex:  # noqa: BLE001
        return _err(ex)


# ====================================================================== backups
@server.tool()
def srv_backup(name: str = "", action: str = "create", backup: str = "", note: str = "", keep: int = 10,
               copy_to: str = "") -> str:
    """Backups of a whole server: worlds, configs and plugins, as zips in BuildMCP's data folder.

    action:
      create   works while the server runs (save-off + save-all flush first, then save-on); note=
               becomes part of the name; keeps the newest ``keep``.
      list     the backups with size and date.
      restore  the server must be stopped; the current state is saved first (…-before-restore), so a
               restore can be undone. backup= a name from list (default: the newest).
      delete   one backup. copy: to ``copy_to`` (another disk or a synced folder).
    Make one before big changes: plugin updates, pasting a new spawn into a live world, config experiments.
    """
    try:
        from buildmcp.admin import backups

        e = _entry(name)
        a = action.lower().strip()
        if a == "create":
            return _fmt(backups.create(e, note=note, keep=max(0, keep)))
        if a == "list":
            return _fmt(backups.listing(e) or f"no backups of {e.name} yet")
        if a == "restore":
            return _fmt(backups.restore(e, backup))
        if a == "delete":
            return _fmt(backups.delete(e, backup))
        if a == "copy":
            if not copy_to or not backup:
                return "Error: copy needs backup and copy_to"
            return _fmt(backups.copy_out(e, backup, copy_to))
        return "Error: action must be create | list | restore | delete | copy"
    except Exception as ex:  # noqa: BLE001
        return _err(ex)
