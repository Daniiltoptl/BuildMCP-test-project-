import numpy as np
import pytest

from buildmcp.blocks.finalize import finalize
from buildmcp.scene import Scene


@pytest.fixture(scope="module")
def assets_ok():
    from buildmcp.render.assets import AssetError, AssetStore

    try:
        AssetStore.get("1.21.4")
    except AssetError as e:  # no network for assets
        pytest.skip(f"assets unavailable: {e}")
    return True


def _scene():
    S = Scene("1.21.4")
    S.fill((0, 0, 0, 15, 0, 15), "grass_block")
    S.fill((4, 1, 4, 8, 4, 8), "stone_bricks", hollow=True)
    for x in range(4, 9):
        S.set(x, 5, 3, "stone_brick_stairs[facing=south]")
    S.set(12, 1, 12, "lantern")
    S.fill((10, 1, 2, 13, 1, 5), "water")
    S.set(2, 1, 12, "oak_fence")
    S.set(3, 1, 12, "oak_fence")
    S.mark("spawn", (8, 1, 14), "spawn", yaw=180)
    S.add_entity("text_display", (8.5, 7, 8.5), {"text": '"Hello"', "billboard": "center"})
    finalize(S)
    return S


@pytest.mark.parametrize("view,kw", [("iso", {}), ("top", {}), ("section", {"y": 2}), ("elev", {"direction": "south"}),
                                     ("player", {}), ("persp", {}), ("sheet", {})])
def test_views_render(assets_ok, view, kw):
    from buildmcp.render.api import render_view

    img = render_view(_scene(), view, width=320, height=200, **kw)
    a = np.asarray(img)
    assert a.shape[0] >= 200 and a.shape[1] >= 320
    assert a.std() > 5  # not a blank image


def test_top_view_colors(assets_ok):
    from buildmcp.render.api import render_view

    S = Scene("1.21.4")
    S.fill((0, 0, 0, 9, 0, 9), "stone")
    img = np.asarray(render_view(S, "top", width=200, height=200, grid=False, show_markers=False))
    center = img[90:110, 90:110].reshape(-1, 3).mean(axis=0)
    assert abs(center[0] - center[1]) < 12 and 70 < center.mean() < 200  # gray stone


def test_night_is_darker(assets_ok):
    from buildmcp.render.api import render_view

    S = _scene()
    day = np.asarray(render_view(S, "iso", width=200, height=150, show_markers=False)).mean()
    night = np.asarray(render_view(S, "iso", width=200, height=150, show_markers=False, time="night")).mean()
    assert night < day * 0.6


def test_camera_underground_is_lifted(assets_ok):
    from buildmcp.render.api import render_view

    S = Scene("1.21.4")
    S.fill((0, 0, 0, 20, 10, 20), "stone")
    img = np.asarray(render_view(S, "player", pos=(10, 2, 10), yaw=0, width=160, height=100))
    assert img.mean() > 30
