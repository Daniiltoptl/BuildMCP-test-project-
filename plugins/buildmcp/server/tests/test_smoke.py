from buildmcp import __version__
from buildmcp.mcp_server import ping


def test_ping():
    assert ping() == f"buildmcp {__version__} ok"
