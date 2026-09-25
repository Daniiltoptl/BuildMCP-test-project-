"""The server_* MCP tools against the real BuildBridge plugin in the fake Paper server."""

import json

import pytest

from buildmcp import mcp_server as M
from buildmcp.live import connector


@pytest.fixture
def env(fake_bridge, monkeypatch, tmp_path):
    import buildmcp.server_tools as T
    from buildmcp.project import Project

    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("BUILDMCP_BUILDS_DIR", str(tmp_path / "builds"))
    monkeypatch.setenv("BUILDMCP_BRIDGE_URL", fake_bridge.url)
    monkeypatch.setenv("BUILDMCP_BRIDGE_TOKEN", fake_bridge.token)
    monkeypatch.setenv("BUILDMCP_RCON_PASSWORD", "")
    connector.forget()
    M.STATE.project = Project.create("tools test", "1.21.4", "fantasy_medieval")
    yield T
    M.STATE.project = None
    connector.forget()


def _j(text):
    assert not text.startswith("Error"), text
    return json.loads(text)


def test_server_tools_flow(env):
    T = env
    code = ("S.fill((0, 0, 0, 8, 0, 8), 'stone_bricks')\n"
            "S.fill((0, 1, 0, 0, 4, 0), 'spruce_log')\n"
            "S.set(4, 1, 4, 'lantern[hanging=false]')\n"
            "E.hologram((4.5, 3, 4.5), ['Hub'])\n"
            "mark('spawn', (4, 1, 4), 'spawn', yaw=180)\n"
            "mark('view', (8, 3, 8), 'viewpoint', yaw=135, pitch=20)\n")
    assert _j(M.run_script(code=code, label="base"))["ok"]
    st = _j(T.server_status())
    assert st["connected_via"].startswith("bridge") and st["minecraft_version_used"] == "1.21.4"

    assert "never pasted" in T.server_paste()  # at="last" needs a previous paste
    dry = _j(T.server_paste(at=[300, 90, 300], dry_run=True))
    assert dry["dry_run"] and dry["anchor_world"] == [300.0, 90.0, 300.0] and dry["offset"] == [296, 89, 296]
    r = _j(T.server_paste(at=[300, 90, 300]))
    assert r["result"]["phase"] == "done" and r["result"]["placed"] == dry["blocks"]
    assert _j(T.server_status())["last_paste"]["offset"] == [296, 89, 296]

    # remove the log column and paste again at the same place: the column is cleared in the world
    M.run_script(code="S.clear((0, 1, 0, 0, 4, 0))", label="remove log")
    r2 = _j(T.server_paste())
    assert r2["cleared"] == 4 and r2["result"]["phase"] == "done"

    # teleport to a marker, the player then reports scene coordinates
    _j(T.server_tp(marker="view"))
    pl = _j(T.server_player())
    assert pl["scene_pos"] == [8.0, 3.0, 8.0] and pl["yaw"] == 135.0

    # read world terrain next to the build into the project
    rd = _j(T.server_read([290, 62, 290, 294, 64, 294], name="terrain"))
    assert rd["size"] == [5, 3, 5] and rd["blocks"] == 50 and rd["step"]["ok"], rd
    assert M.STATE.project.scene.get(290 - 296, 63 - 89, 290 - 296).endswith("grass_block[snowy=false]")

    hm = _j(T.server_heightmap([290, 290, 299, 299]))
    assert hm["max_y"] >= 89 and hm["min_y"] == 63

    assert "[Server] hello" in T.server_cmd("say hello")
    jobs = _j(T.server_job(action="list"))
    assert len(jobs) >= 2 and all(j["phase"] == "done" for j in jobs)
    u = _j(T.server_undo())
    assert u["phase"] == "done" and u["kind"] == "undo"
