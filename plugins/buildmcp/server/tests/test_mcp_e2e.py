"""End-to-end: start the MCP server over stdio and drive the main tools like Claude would."""

import asyncio
import json
import os
import sys

import pytest

pytest.importorskip("mcp")


async def _session(tmp_path, fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["BUILDMCP_BUILDS_DIR"] = str(tmp_path / "builds")
    env["BUILDMCP_NO_WARMUP"] = "1"
    params = StdioServerParameters(command=sys.executable, args=["-m", "buildmcp.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _text(res) -> str:
    return "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")


def test_mcp_tools_flow(tmp_path):
    async def flow(s):
        tools = await s.list_tools()
        names = {t.name for t in tools.tools}
        for needed in ("project_new", "run_script", "render", "inspect", "export", "api_docs", "edit", "history"):
            assert needed in names, needed
        r = await s.call_tool("project_new", {"name": "Test Spawn", "theme": "fantasy_medieval", "version": "1.21.4"})
        assert "Created project" in _text(r)
        r = await s.call_tool("api_docs", {"topic": "index"})
        assert "trees" in _text(r)
        code = (
            "isl = terrain.island((0, 80, 0), 14, seed=1)\n"
            "trees.tree(isl.on_top(3, 3), 'oak')\n"
            "mark('spawn', isl.on_top(0, 6), 'spawn', yaw=180)\n"
            "print('top', isl.height_at(0, 0))\n"
            "finalize()\n"
        )
        r = await s.call_tool("run_script", {"code": code, "label": "island"})
        out = json.loads(_text(r))
        assert out["ok"] and out["changed"] > 1000, out
        r = await s.call_tool("run_script", {"code": "S.set(0, 0, 0, 'not_a_block')", "label": "bad"})
        assert "Unknown block" in _text(r)
        r = await s.call_tool("edit", {"ops": [{"op": "fill", "box": [-2, 90, -2, 2, 90, 2], "block": "stone"}]})
        assert json.loads(_text(r))["ok"]
        r = await s.call_tool("history", {"action": "undo"})
        assert "Reverted" in _text(r)
        r = await s.call_tool("inspect", {"what": "lint"})
        assert "[error]" not in _text(r), _text(r)
        r = await s.call_tool("export", {"format": "schem"})
        out = json.loads(_text(r))
        assert out["file"].endswith(".schem") and out["blocks"] > 1000
        r = await s.call_tool("steps", {"action": "list"})
        assert "island" in _text(r)
        return True

    assert asyncio.run(_session(tmp_path, flow))


def test_mcp_render_returns_image(tmp_path):
    from buildmcp.render.assets import AssetError, AssetStore

    try:
        AssetStore.get("1.21.4")
    except AssetError as e:
        pytest.skip(f"assets unavailable: {e}")

    async def flow(s):
        await s.call_tool("project_new", {"name": "R", "version": "1.21.4"})
        await s.call_tool("run_script", {"code": "S.fill((0,0,0,8,0,8), T.grass)", "label": "floor"})
        r = await s.call_tool("render", {"view": "iso", "width": 320, "height": 200})
        kinds = [c.type for c in r.content]
        assert "image" in kinds, kinds
        return True

    assert asyncio.run(_session(tmp_path, flow))
