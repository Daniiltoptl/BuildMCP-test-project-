import pytest

import javakit


@pytest.fixture(scope="module")
def fake_bridge(tmp_path_factory):
    """The real BuildBridge plugin running in the fake Paper server (one per test module)."""
    try:
        srv = javakit.FakeServer(tmp_path_factory.mktemp("fake-server"))
    except javakit.Unavailable as e:
        pytest.skip(str(e))
    yield srv
    srv.stop()
