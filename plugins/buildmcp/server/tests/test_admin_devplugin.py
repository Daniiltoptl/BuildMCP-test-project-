"""Own plugins: scaffold, javac against a server's own jars (here the test kit's Bukkit stubs packed like
Paper's versions/ + libraries/, and small Velocity stubs), compile errors with file and line, a plugin
using another installed plugin's API, deploy/bump/replace, and installing a jar from this PC."""

import json
import os
import shutil
import subprocess
import zipfile

import pytest

import javakit
from buildmcp.admin import devplugin, installer, jarinfo, registry

VELOCITY_STUBS = {
    "com/velocitypowered/api/plugin/Plugin.java": "package com.velocitypowered.api.plugin;\n"
    "public @interface Plugin { String id(); String name() default \"\"; String version() default \"\";"
    " String[] authors() default {}; }",
    "com/velocitypowered/api/event/Subscribe.java": "package com.velocitypowered.api.event;\npublic @interface Subscribe {}",
    "com/velocitypowered/api/event/proxy/ProxyInitializeEvent.java":
        "package com.velocitypowered.api.event.proxy;\npublic final class ProxyInitializeEvent {}",
    "com/velocitypowered/api/proxy/ProxyServer.java": "package com.velocitypowered.api.proxy;\npublic interface ProxyServer {}",
    "com/google/inject/Inject.java": "package com.google.inject;\npublic @interface Inject {}",
    "org/slf4j/Logger.java": "package org.slf4j;\npublic interface Logger { void info(String s); }",
}


def _javac(out, sources, cp=()):
    javac = shutil.which("javac")
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([javac, "--release", "21", "-nowarn", "-d", str(out), "-cp",
                        os.pathsep.join(map(str, cp)) or ".", *map(str, sources)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _jar(src_dir, dest, extra: dict | None = None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w") as z:
        for f in src_dir.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(src_dir).as_posix())
        for k, v in (extra or {}).items():
            z.writestr(k, v)


@pytest.fixture
def servers(tmp_path, monkeypatch):
    try:
        libs = javakit.jars()
    except javakit.Unavailable as e:
        pytest.skip(str(e))
    if not shutil.which("javac"):
        pytest.skip("no JDK")
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    from buildmcp.live import connector

    connector.forget()
    # a Paper-like server: the API in versions/, the libraries in libraries/
    paper = tmp_path / "lobby"
    stubs = sorted((javakit.BRIDGE / "testkit" / "api-stubs").rglob("*.java"))
    _javac(tmp_path / "stub-classes", stubs, libs)
    _jar(tmp_path / "stub-classes", paper / "versions" / "1.21.8" / "paper-1.21.8.jar")
    for j in libs:
        (paper / "libraries" / "x").mkdir(parents=True, exist_ok=True)
        shutil.copy2(j, paper / "libraries" / "x" / j.name)
    # an installed plugin with an API other plugins can call
    lib_src = tmp_path / "coollib-src" / "cool" / "lib" / "Api.java"
    lib_src.parent.mkdir(parents=True)
    lib_src.write_text("package cool.lib;\npublic final class Api { public static String hello() { return \"hi\"; } }")
    _javac(tmp_path / "coollib-classes", [lib_src])
    _jar(tmp_path / "coollib-classes", paper / "plugins" / "CoolLib.jar",
         {"plugin.yml": "name: CoolLib\nversion: '1.0'\nmain: cool.lib.Main\n"})
    registry.put(registry.ServerEntry(name="lobby", dir=str(paper), software="paper", version="1.21.8",
                                      jar="paper.jar", port=25566))
    # a Velocity-like proxy: one jar
    proxy = tmp_path / "proxy"
    vs = tmp_path / "vstubs"
    for rel, text in VELOCITY_STUBS.items():
        (vs / rel).parent.mkdir(parents=True, exist_ok=True)
        (vs / rel).write_text(text)
    _javac(tmp_path / "vstub-classes", sorted(vs.rglob("*.java")))
    _jar(tmp_path / "vstub-classes", proxy / "velocity.jar")
    registry.put(registry.ServerEntry(name="proxy", dir=str(proxy), software="velocity", version="3.4.0",
                                      jar="velocity.jar", port=25565))
    return registry.get("lobby"), registry.get("proxy")


def test_paper_plugin_build_errors_deploy(servers):
    lobby, _ = servers
    rep = devplugin.create("HubTools", "paper", commands=["hub", "/spawn"], softdepend=["CoolLib"])
    src = next(p for p in rep["files"] if p.endswith("HubToolsPlugin.java"))
    b = devplugin.build("HubTools", lobby)
    assert b["ok"], b
    with zipfile.ZipFile(b["jar"]) as z:
        names = set(z.namelist())
        yml = z.read("plugin.yml").decode()
    assert "dev/buildmcp/hubtools/HubToolsPlugin.class" in names and "config.yml" in names
    assert "version: '1.0.0'" in yml and "  spawn:" in yml and "softdepend: [CoolLib]" in yml
    assert jarinfo.read(b["jar"]).name == "HubTools"

    # a compile error comes back with the file, the line and the code
    text = open(src).read()
    open(src, "w").write(text.replace('getLogger().info("HubTools is on");', 'getLogger().info("HubTools is on")'))
    b = devplugin.build("HubTools", lobby)
    e0 = b["errors"][0]
    assert not b["ok"] and e0["message"] == "';' expected"
    assert e0["file"] == "src/main/java/dev/buildmcp/hubtools/HubToolsPlugin.java" and e0["line"] > 5
    assert e0["code"] == 'getLogger().info("HubTools is on")'
    open(src, "w").write(text.replace('getLogger().info("HubTools is on");', 'nope(42);'))
    b = devplugin.build("HubTools", lobby)
    e0 = b["errors"][0]
    assert not b["ok"] and e0["message"] == "cannot find symbol" and e0["code"] == "nope(42);"
    assert any("method nope(int)" in x for x in e0["detail"])

    # the API of a plugin installed on the server can be used
    open(src, "w").write(text.replace('getLogger().info("HubTools is on");',
                                      'getLogger().info("HubTools is on " + cool.lib.Api.hello());'))
    d1 = devplugin.deploy("HubTools", lobby)
    assert d1["build"]["ok"] and d1["result"][0]["status"] == "installed"
    assert (lobby.path / "plugins" / "HubTools-1.0.0.jar").exists()
    assert installer.load_lock(lobby)["HubTools"]["spec"] == "dev:HubTools"
    assert devplugin.bump("HubTools") == "1.0.1"
    d2 = devplugin.deploy("HubTools", lobby)
    assert d2["result"][0]["status"] == "updated" and d2["result"][0]["from"] == "1.0.0"
    assert not (lobby.path / "plugins" / "HubTools-1.0.0.jar").exists()
    assert (lobby.path / "plugins" / "HubTools-1.0.1.jar").exists()
    up = {r["want"]: r for r in installer.update(lobby, ["HubTools"])["result"]}
    assert "devplugin(action='deploy', name='HubTools')" in up["HubTools"]["detail"]
    listed = devplugin.list_projects()
    assert listed[0]["name"] == "HubTools" and listed[0]["deployed_to"] == ["lobby"]

    # a jar from this PC (a plugin bought and downloaded by hand)
    rep = installer.install(lobby, [f"file:{d2['build']['jar']}"], force=True)
    assert rep["result"][-1]["status"] == "updated"
    miss = installer.install(lobby, ["file:/nope/x.jar"])
    assert miss["result"][-1]["status"] == "failed"


def test_velocity_plugin_and_platform_checks(servers):
    lobby, proxy = servers
    devplugin.create("NetTools", "velocity")
    b = devplugin.build("NetTools", proxy)
    assert b["ok"], b
    with zipfile.ZipFile(b["jar"]) as z:
        desc = json.loads(z.read("velocity-plugin.json"))
    assert desc["id"] == "nettools" and desc["main"] == "dev.buildmcp.nettools.NetToolsPlugin"
    with pytest.raises(devplugin.DevError, match="velocity plugin"):
        devplugin.build("NetTools", lobby)
    with pytest.raises(devplugin.DevError, match="not a plugin name"):
        devplugin.create("1bad")
    with pytest.raises(devplugin.DevError, match="already exists"):
        devplugin.create("NetTools", "velocity")
    assert devplugin.bump("NetTools", "minor") == "1.1.0"
    src = next(devplugin.project_dir("NetTools").rglob("NetToolsPlugin.java")).read_text()
    assert 'version = "1.1.0"' in src
