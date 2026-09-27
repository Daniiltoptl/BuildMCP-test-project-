"""Run real servers through the admin MCP tools (CI: needs internet and Java 21).

    python tests/e2e/admin_live.py --mc 1.21.8 --dir /tmp/admin-e2e

1. srv_setup: a Paper backend and a Velocity proxy, cores downloaded from the live APIs.
2. plugins install: a lobby set on Paper and the proxy stack on Velocity, dependencies included.
3. plugins restart: the runner starts both; every installed plugin has to enable.
4. console commands through the runner and RCON, plugins list.
5. srv_link: a test client logs in through the proxy and reaches the backend; a direct login to the
   backend is refused. A config change with restart=True. Then srv_power stop.
The report goes to <dir>/admin-e2e.json; the logs stay in the server folders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PAPER_PLUGINS = ["luckperms", "placeholderapi", "worldguard", "tab", "fancynpcs", "fancyholograms", "vault",
                 "essentialsx", "coreprotect", "chunky", "spark", "grimac"]


PROBLEMS: list[str] = []


def call(fn, fatal: bool = True, **kw) -> dict | list | str:
    t0 = time.time()
    out = fn(**kw)
    print(f"--- {fn.__name__}({', '.join(f'{k}={v!r}' for k, v in kw.items())}) {time.time() - t0:.1f}s\n{out[:4000]}",
          flush=True)
    if out.startswith("Error"):
        if fatal:
            raise SystemExit(f"{fn.__name__} failed: {out}")
        PROBLEMS.append(f"{fn.__name__}({kw}): {out[:300]}")
        return out
    try:
        return json.loads(out)
    except ValueError:
        return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", default="1.21.8")
    ap.add_argument("--dir", default="/tmp/admin-e2e")
    a = ap.parse_args()
    base = Path(a.dir)
    base.mkdir(parents=True, exist_ok=True)
    os.environ["BUILDMCP_DATA"] = str(base / "data")
    from buildmcp import admin_tools as T
    from buildmcp import server_tools as S
    from buildmcp.admin import process, registry

    sys.path.insert(0, str(Path(__file__).parent))
    import mc_login

    report: dict = {"mc": a.mc, "problems": PROBLEMS}
    try:
        call(T.srv_setup, name="lobby", dir=str(base / "lobby"), software="paper", version=a.mc, memory="2G",
             accept_eula=True, motd="BuildMCP e2e")
        call(T.srv_setup, name="proxy", dir=str(base / "proxy"), software="velocity", version="latest", memory="512M")
        lst = call(T.srv_list)
        report["servers"] = lst

        # dry run first: the plan names the dependency WorldGuard needs
        plan = call(T.plugins, action="install", names=PAPER_PLUGINS, server="lobby", dry_run=True)
        if not any(r["want"] == "worldedit" for r in plan["plan"]):
            report["problems"].append("dry run did not plan WorldEdit for WorldGuard")

        rep = call(T.plugins, action="install", names=PAPER_PLUGINS, server="lobby", restart=True)
        report["lobby_install"] = rep
        bad = [r for r in rep["result"] if r["status"] not in ("installed", "present")]
        if bad:
            report["problems"].append(f"lobby install: {bad}")
        st = rep.get("start", {})
        if st.get("state") != "running":
            report["problems"].append(f"lobby did not start: {st}")
        for name, state in (st.get("plugins") or {}).items():
            if state != "enabled":
                report["problems"].append(f"lobby plugin {name}: {state}")
        if st.get("failed_plugins"):
            report["problems"].append(f"lobby failed plugins: {st['failed_plugins']}")

        e = registry.get("lobby")
        out = process.console(e, "lp info", wait=3.0)
        report["lp_info"] = out[-10:]
        if not any("LuckPerms" in l for l in out):
            report["problems"].append("'lp info' printed nothing about LuckPerms")
        rcon = call(S.server_cmd, fatal=False, command="plugins", server="lobby")
        report["rcon_plugins"] = rcon
        if "LuckPerms" not in str(rcon):
            report["problems"].append("RCON 'plugins' does not list LuckPerms")
        listing = call(T.plugins, action="list", server="lobby")
        not_enabled = [p for p in listing["plugins"] if p.get("last_start") != "enabled"
                       and p["name"] != "BuildBridge"]
        if not_enabled:
            report["problems"].append(f"plugins list: {not_enabled}")

        # the proxy with its stack
        rep = call(T.plugins, action="install", names=["stack:proxy"], server="proxy", restart=True)
        report["proxy_install"] = rep
        bad = [r for r in rep["result"] if r["status"] not in ("installed", "present")]
        if bad:
            report["problems"].append(f"proxy install: {bad}")
        st = rep.get("start", {})
        if st.get("state") != "running":
            report["problems"].append(f"proxy did not start: {st}")
        for name, state in (st.get("plugins") or {}).items():
            if state != "enabled":
                report["problems"].append(f"proxy plugin {name}: {state}")
        out = call(S.server_cmd, fatal=False, command="velocity plugins", server="proxy")
        report["proxy_plugins"] = out

        # one network: the proxy in front of the lobby (offline mode, so the test client needs no account)
        link = call(T.srv_link, proxy="proxy", backends=["lobby"], online_mode=False, restart=True)
        report["link"] = link
        for n, st in (link.get("restart") or {}).items():
            if st.get("state") != "running":
                report["problems"].append(f"{n} after srv_link: {st}")
        lobby, proxy = registry.get("lobby"), registry.get("proxy")
        cfg = call(T.config, action="get", server="lobby", file="paper-global", path="proxies.velocity")
        if cfg.get("value", {}).get("enabled") is not True or cfg["value"].get("secret") != "***":
            report["problems"].append(f"paper-global after srv_link: {cfg}")
        try:
            proto = mc_login.status("127.0.0.1", lobby.port)["version"]["protocol"]
            report["protocol"] = proto
            via = mc_login.login("127.0.0.1", proxy.port, proto)
            report["login_via_proxy"] = via
            if not via["ok"]:
                report["problems"].append(f"login through the proxy failed: {via}")
            direct = mc_login.login("127.0.0.1", lobby.port, proto)
            report["login_direct"] = direct
            if direct["ok"] or "velocity" not in str(direct.get("reason", "")).lower():
                report["problems"].append(f"a direct login to the backend was not refused: {direct}")
        except Exception as ex:  # noqa: BLE001
            report["problems"].append(f"login test: {type(ex).__name__}: {ex}")
        joined = process.log_lines(lobby, lines=400, grep="BuildMCPTest")
        report["lobby_log_player"] = joined[-5:]

        # a config change with a restart: the view distance comes back from the running server
        ch = call(T.config, action="set", server="lobby", file="server", path="view-distance", value=7, restart=True)
        if (ch.get("restart") or {}).get("state") != "running":
            report["problems"].append(f"restart after config set: {ch}")

        # update finds nothing newer right after the install
        up = call(T.plugins, action="update", server="lobby")
        changed = [r for r in up["result"] if isinstance(r, dict) and r["status"] == "updated"]
        if changed:
            report["problems"].append(f"update right after install changed {changed}")
    finally:
        for n in ("lobby", "proxy"):
            try:
                e = registry.get(n)
                report[f"stop_{n}"] = process.stop(e, timeout=120)
            except Exception as ex:  # noqa: BLE001
                report[f"stop_{n}"] = str(ex)
        (base / "admin-e2e.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), "utf-8")
    print(json.dumps({"problems": report["problems"]}, indent=1, ensure_ascii=False))
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
