"""Servers: .properties round trip, core downloads (mocked APIs), registry, create/adopt, and the
runner starting, commanding, restarting and stopping a fake server process."""

import hashlib
import json
import sys
import textwrap
import time

import httpx
import pytest

from buildmcp.admin import net, process, props, registry, setup, software


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    for var in ("BUILDMCP_SERVER_DIR", "BUILDMCP_RCON_PASSWORD", "BUILDMCP_BRIDGE_TOKEN"):
        monkeypatch.setenv(var, "")
    from buildmcp.live import connector

    connector.forget()
    yield tmp_path
    net.set_transport(None)


# ------------------------------------------------------------------ properties
def test_properties_round_trip_keeps_comments(tmp_path):
    p = tmp_path / "server.properties"
    p.write_text("#Minecraft server properties\n#Mon Jan 01\nlevel-type=minecraft\\:flat\nmotd=A \\u00e9 server\n"
                 "server-port=25565\n\nonline-mode=true\n", "utf-8")
    d = props.read(p)
    assert d["level-type"] == "minecraft:flat" and d["motd"] == "A é server" and d["server-port"] == "25565"
    ch = props.update(p, {"server-port": 25566, "online-mode": False, "enable-rcon": True, "motd": "A é server"})
    assert ("server-port", "25565", "25566") in ch and ("enable-rcon", None, "true") in ch
    assert not any(k == "motd" for k, _, _ in ch)  # unchanged value, untouched line
    text = p.read_text("utf-8")
    assert text.startswith("#Minecraft server properties\n#Mon Jan 01\n")
    assert "level-type=minecraft\\:flat" in text and "online-mode=false" in text and text.endswith("enable-rcon=true\n")
    assert props.read(p)["server-port"] == "25566"


# ------------------------------------------------------------------ cores
JAR = b"PK\x03\x04 fake paper jar"


def _fill_transport():
    sha = hashlib.sha256(JAR).hexdigest()

    def handler(req: httpx.Request):
        u = str(req.url)
        assert req.headers["user-agent"].startswith("Daniiltoptl/BuildMCP/")
        if u.endswith("/v3/projects/paper"):
            return httpx.Response(200, json={"project": {"id": "paper"},
                                             "versions": {"1.21": ["1.21.11", "1.21.4", "1.21.11-pre1"],
                                                          "1.20": ["1.20.6"]}})
        if u.endswith("/v3/projects/paper/versions/1.21.11/builds/latest"):
            return httpx.Response(200, json={"id": 57, "channel": "STABLE", "downloads": {"server:default": {
                "name": "paper-1.21.11-57.jar", "checksums": {"sha256": sha}, "size": len(JAR),
                "url": "https://fill-data.papermc.io/v1/objects/x/paper-1.21.11-57.jar"}}})
        if u.endswith("/v3/projects/paper/versions/1.20.6/builds/latest"):
            return httpx.Response(200, json={"id": 151, "channel": "STABLE", "downloads": {"server:default": {
                "name": "paper-1.20.6-151.jar", "checksums": {"sha256": "0" * 64}, "size": 3,
                "url": "https://fill-data.papermc.io/v1/objects/y/paper-1.20.6-151.jar"}}})
        if u.endswith("/v3/projects/velocity"):
            return httpx.Response(200, json={"versions": {"3.0.0": ["3.4.0-SNAPSHOT", "3.3.0-SNAPSHOT"]}})
        if u.endswith(".jar"):
            return httpx.Response(200, content=JAR)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def test_pick_version_and_download(data):
    net.set_transport(_fill_transport())
    assert software.versions("paper")[:2] == ["1.21.11", "1.21.4"]  # snapshots and pre-releases are dropped
    assert software.pick_version("paper", "latest") == "1.21.11"
    assert software.pick_version("paper", "1.21") == "1.21.11"
    assert software.pick_version("velocity", "latest") == "3.4.0-SNAPSHOT"
    with pytest.raises(ValueError):
        software.pick_version("paper", "1.8")
    got = software.download("paper", "latest", data / "srv")
    assert got["version"] == "1.21.11" and got["build"] == "57"
    assert (data / "srv" / "paper-1.21.11-57.jar").read_bytes() == JAR
    with pytest.raises(net.NetError, match="sha256 mismatch"):
        software.download("paper", "1.20.6", data / "srv2")
    assert not list((data / "srv2").glob("*.jar*"))  # nothing half-written is left
    assert software.java_required("paper", "1.21.11") == 21 and software.java_required("paper", "26.1") == 25
    assert software.vkey("3.4.0") > software.vkey("3.4.0-SNAPSHOT") and software.vkey("1.21.11") > software.vkey("1.21.4")


def test_create_adopt_and_registry(data):
    net.set_transport(_fill_transport())
    rep = setup.create("Lobby", str(data / "lobby"), "paper", "latest", accept_eula=True, motd="Hub")
    assert rep["core"].startswith("paper 1.21.11")
    lobby = registry.get("lobby")
    assert lobby.jar == "paper-1.21.11-57.jar" and lobby.port >= 25565 and lobby.rcon_port >= 25575
    pr = props.read(data / "lobby" / "server.properties")
    assert pr["enable-rcon"] == "true" and pr["rcon.password"] == lobby.rcon_password and pr["motd"] == "Hub"
    assert "eula=true" in (data / "lobby" / "eula.txt").read_text()
    assert (data / "lobby" / "start.sh").exists() and "--nogui" in (data / "lobby" / "start.bat").read_text()
    # the active server is mirrored into the connection settings the building tools read
    from buildmcp.live.connector import load_settings

    s = load_settings()
    assert s.server_dir == lobby.dir and s.rcon_password == lobby.rcon_password and s.rcon_port == lobby.rcon_port

    # a second server gets other ports and does not get an EULA without consent
    rep2 = setup.create("anarchy", str(data / "anarchy"), "paper", "1.21.11")
    a = registry.get("anarchy")
    assert a.port != lobby.port and a.rcon_port != lobby.rcon_port and "eula" in rep2
    assert not (data / "anarchy" / "eula.txt").exists()
    with pytest.raises(ValueError, match="already exists"):
        setup.create("anarchy", str(data / "x"), "paper")

    # adopt a folder made by hand: detect core, version and the BuildBridge token
    old = data / "old"
    (old / "plugins" / "BuildBridge").mkdir(parents=True)
    (old / "purpur-1.21.4-2400.jar").write_bytes(b"jar")
    (old / "server.properties").write_text("server-port=25600\n")
    (old / "plugins" / "BuildBridge" / "config.yml").write_text('bind: 0.0.0.0\nport: 8799\ntoken: "tok"\n')
    rep3 = setup.adopt("old", str(old), accept_eula=True)
    e = registry.get("old")
    assert (e.software, e.version, e.build, e.port) == ("purpur", "1.21.4", "2400", 25600)
    assert e.bridge_url == "http://127.0.0.1:8799" and e.bridge_token == "tok" and "rcon" in rep3
    assert props.read(old / "server.properties")["enable-rcon"] == "true"

    registry.use("anarchy")
    assert registry.active_name() == "anarchy" and load_settings().rcon_port == a.rcon_port
    assert set(registry.load_all()) == {"lobby", "anarchy", "old"}
    registry.remove("old")
    assert "old" not in registry.load_all()
    with pytest.raises(registry.RegistryError):
        registry.get("nope")


def test_legacy_single_server_becomes_default(data, monkeypatch):
    srv = data / "legacy"
    srv.mkdir()
    (srv / "paper-1.21.4-100.jar").write_bytes(b"jar")
    (srv / "server.properties").write_text("enable-rcon=true\nrcon.port=25590\nrcon.password=pw\n")
    monkeypatch.setenv("BUILDMCP_SERVER_DIR", str(srv))
    e = registry.get()
    assert e.name == "default" and e.version == "1.21.4" and e.rcon_password == "pw" and e.rcon_port == 25590


# ------------------------------------------------------------------ runner
FAKE_SERVER = textwrap.dedent('''
    import sys, time
    print("Starting minecraft server version fake", flush=True)
    time.sleep(0.3)
    print("[12:00:00 ERROR]: Could not load 'plugins/Broken.jar' in folder 'plugins'", flush=True)
    print('[12:00:01 INFO]: Done (0.42s)! For help, type "help"', flush=True)
    for line in sys.stdin:
        line = line.strip()
        if line == "stop":
            print("Stopping the server", flush=True)
            sys.exit(0)
        if line == "crash":
            print("Encountered an unexpected exception", flush=True)
            sys.exit(1)
        print("> ran: " + line, flush=True)
''')


def _fake_entry(data, name="fake"):
    d = data / name
    d.mkdir()
    (d / "fake_server.py").write_text(FAKE_SERVER)
    (d / "eula.txt").write_text("eula=true\n")
    e = registry.ServerEntry(name=name, dir=str(d), software="paper", version="1.21.4", jar="fake_server.py",
                             command=[sys.executable, "-u", "fake_server.py"], port=45123)
    registry.put(e)
    return registry.get(name)


def _wait(pred, timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.2)
    return False


def test_runner_start_command_crash_restart_stop(data):
    e = _fake_entry(data)
    try:
        r = process.start(e, wait=True, timeout=30)
        assert r["state"] == "running", r
        assert any("Could not load" in p for p in r["problems"])
        assert process.status(e)["running"]
        assert process.start(e)["state"] == "already running"
        out = process.console(e, "say hello", wait=1.0)
        assert any("ran: say hello" in l for l in out)

        # a crash is restarted by the runner
        first_pid = process.runner_state(e)["pid"]
        process.console(e, "crash", wait=0.5)
        assert _wait(lambda: (process.runner_state(e) or {}).get("pid") not in (None, first_pid)
                     and (process.runner_state(e) or {}).get("state") == "running")
        assert _wait(lambda: sum("Done (" in l for l in process.read_from(e, 0)) >= 2)
        assert process.runner_state(e)["crashes"] == 1

        s = process.stop(e, timeout=20)
        assert s["state"] == "stopped", s
        st = process.runner_state(e)
        assert st["state"] == "stopped" and not st["server_alive"]
        assert not process.status(e)["running"]
        tail = process.log_lines(e, lines=200)
        assert any("server exited with code 0" in l for l in tail)
    finally:
        process.kill(e)


def test_start_refuses_without_eula(data):
    e = _fake_entry(data, "noeula")
    (e.path / "eula.txt").unlink()
    with pytest.raises(process.ProcessError, match="EULA"):
        process.start(e)


def test_ready_line_of_paper_and_velocity():
    for line in ('[10:00:03 INFO]: Done (3.1s)! For help, type "help"', "[15:05:51 INFO]: Done (7s)!",
                 "[15:05:51 INFO]: Done (3,33s)!"):
        assert process.READY_RE.search(line), line
    assert not process.READY_RE.search("[10:00:00 INFO]: Done preparing level")


def test_problems_filter():
    lines = ["[10:00:00 INFO]: Loading plugins", "[10:00:01 ERROR]: Error occurred while enabling Foo v1.0",
             "\tat org.bukkit.Something(Something.java:1)", "[10:00:02 WARN]: **** FAILED TO BIND TO PORT!",
             "[10:00:03 INFO]: Done (3.1s)!"]
    got = process.problems(lines)
    assert got == ["[10:00:01 ERROR]: Error occurred while enabling Foo v1.0", "[10:00:02 WARN]: **** FAILED TO BIND TO PORT!"]


def test_build_command_flags():
    e = registry.ServerEntry(name="p", dir="/tmp/p", software="paper", version="1.21.4", jar="paper.jar", memory="16G")
    cmd = process.build_command(e)
    assert cmd[1:3] == ["-Xms16384M", "-Xmx16384M"] and "-XX:G1HeapRegionSize=16M" in cmd
    assert cmd[-3:] == ["-jar", "paper.jar", "--nogui"] and "-Dterminal.jline=false" in cmd
    v = registry.ServerEntry(name="v", dir="/tmp/v", software="velocity", version="3.4.0", jar="velocity.jar", memory="1G")
    vc = process.build_command(v)
    assert vc[-2:] == ["-jar", "velocity.jar"] and "-XX:MaxInlineLevel=15" in vc
    assert process.stop_command(v) == "shutdown" and process.memory_mb("2048M") == 2048


def test_java_from_the_jar_and_the_closest_installed_java(tmp_path, monkeypatch):
    import zipfile

    jar = tmp_path / "velocity.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nMain-Class: com.velocitypowered.proxy.Velocity\n")
        z.writestr("com/velocitypowered/proxy/Velocity.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x45" + b"\x00" * 8)
    assert software.java_from_jar(jar) == 25
    e = registry.ServerEntry(name="v", dir=str(tmp_path), software="velocity", version="3.5.0", jar="velocity.jar")
    assert process.java_needed(e) == 25
    majors = {"/j/17/bin/java": 17, "/j/25/bin/java": 25, "/j/21/bin/java": 21, "/broken/java": None}
    monkeypatch.setattr(process, "java_candidates", lambda: list(majors))
    monkeypatch.setattr(process, "_java_major_cached", lambda j: majors[j])
    assert process.find_java(21) == ("/j/21/bin/java", 21)
    assert process.find_java(22) == ("/j/25/bin/java", 25)
    assert process.find_java(26) is None
    hint = process.problems(["Error: java.lang.UnsupportedClassVersionError: com/velocitypowered/proxy/Velocity has "
                             "been compiled by a more recent version of the Java Runtime (class file version 69.0), "
                             "this version of the Java Runtime only recognizes class file versions up to 65.0"] * 3)
    assert len(hint) == 1 and hint[0].startswith("needs Java 25, runs on Java 21")
