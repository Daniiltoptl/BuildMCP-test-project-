"""Server backups: what goes in and what stays out, a consistent copy of a running server (save-off /
save-all flush / save-on through the runner), restore with an undo, pruning."""

import json
import sys
import textwrap
import zipfile

import pytest

from buildmcp.admin import backups, process, registry


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    for var in ("BUILDMCP_SERVER_DIR", "BUILDMCP_RCON_PASSWORD", "BUILDMCP_BRIDGE_TOKEN"):
        monkeypatch.setenv(var, "")
    from buildmcp.live import connector

    connector.forget()
    d = tmp_path / "anarchy"
    for rel, data in {"world/level.dat": b"L1", "world/region/r.0.0.mca": b"R" * 5000, "world_nether/level.dat": b"N",
                      "plugins/LuckPerms.jar": b"PK", "plugins/LuckPerms/config.yml": b"storage-method: h2\n",
                      "plugins/.paper-remapped/x.jar": b"cache", "server.properties": b"motd=A\n",
                      "eula.txt": b"eula=true\n", "logs/latest.log": b"log", "libraries/a/b.jar": b"lib",
                      "versions/1.21.8/paper.jar": b"v", ".buildmcp/plugins.lock.json": b"{}",
                      ".buildmcp/console.log": b"console", "world/session.lock": b"lock"}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(data)
    registry.put(registry.ServerEntry(name="anarchy", dir=str(d), software="paper", version="1.21.8", jar="paper.jar",
                                      port=45180))
    return registry.get("anarchy")


def test_backup_restore_and_prune(srv):
    rep = backups.create(srv, note="before update")
    assert rep["consistent"] == "server stopped" and rep["backup"].endswith("-beforeupdate.zip")
    with zipfile.ZipFile(rep["path"]) as z:
        names = set(z.namelist())
        assert z.getinfo("world/region/r.0.0.mca").compress_type == zipfile.ZIP_STORED
    assert {"world/level.dat", "world/region/r.0.0.mca", "world_nether/level.dat", "plugins/LuckPerms.jar",
            "plugins/LuckPerms/config.yml", "server.properties", "eula.txt", ".buildmcp/plugins.lock.json"} <= names
    for gone in ("logs/latest.log", "libraries/a/b.jar", "versions/1.21.8/paper.jar", "plugins/.paper-remapped/x.jar",
                 ".buildmcp/console.log", "world/session.lock"):
        assert gone not in names

    # the world changes, a plugin appears; restore brings the old state back and keeps an undo
    (srv.path / "world" / "level.dat").write_bytes(b"L2")
    (srv.path / "plugins" / "Griefer.jar").write_bytes(b"bad")
    res = backups.restore(srv, rep["backup"])
    assert (srv.path / "world" / "level.dat").read_bytes() == b"L1"
    assert not (srv.path / "plugins" / "Griefer.jar").exists()
    assert (srv.path / "libraries" / "a" / "b.jar").exists()               # what the server rebuilds stays
    assert "before-restore" in res["undo"]
    backups.restore(srv, res["undo"])
    assert (srv.path / "world" / "level.dat").read_bytes() == b"L2"

    for i in range(3):
        backups.create(srv, note=f"n{i}", keep=2)
    names = [b["backup"] for b in backups.listing(srv)]
    assert len([n for n in names if "before-restore" not in n]) == 2 and any("before-restore" in n for n in names)
    with pytest.raises(backups.BackupError):
        backups.restore(srv, "nope.zip")


FAKE = textwrap.dedent('''
    import sys
    print('[10:00:00 INFO]: Done (0.50s)! For help, type "help"', flush=True)
    for line in sys.stdin:
        line = line.strip()
        if line == "save-all flush":
            print("[10:00:01 INFO]: Saving the game (this may take a moment!)", flush=True)
            print("[10:00:01 INFO]: Saved the game", flush=True)
        elif line in ("save-off", "save-on"):
            print("[10:00:01 INFO]: " + ("Automatic saving is now disabled" if line == "save-off"
                                         else "Automatic saving is now enabled"), flush=True)
        elif line == "stop":
            sys.exit(0)
''')


def test_backup_of_a_running_server_flushes_first(srv):
    from buildmcp import admin_tools

    (srv.path / "fake.py").write_text(FAKE)
    srv.command = [sys.executable, "-u", "fake.py"]
    registry.put(srv)
    e = registry.get("anarchy")
    try:
        assert process.start(e, wait=True, timeout=30)["state"] == "running"
        out = json.loads(admin_tools.srv_backup(name="anarchy", action="create"))
        assert out["consistent"] == "flushed while running"
        log = "\n".join(process.log_lines(e, lines=50))
        assert log.index("disabled") < log.index("Saved the game") < log.index("now enabled")
        assert admin_tools.srv_backup(name="anarchy", action="restore").startswith("Error: anarchy is running")
    finally:
        process.kill(e)
