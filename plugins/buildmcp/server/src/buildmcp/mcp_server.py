"""MCP server entry point for BuildMCP."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from buildmcp import __version__

INSTRUCTIONS = """\
BuildMCP — движок для постройки Minecraft-спавнов уровня топ-серверов.
Пиши процедурные скрипты (run_script), смотри результат (render), проверяй (inspect)
и вставляй на сервер (server_paste). Перед работой загрузи skill spawn-builder.
"""

server = MCPServer(name="buildmcp", version=__version__, instructions=INSTRUCTIONS)


@server.tool()
def ping() -> str:
    """Health check: returns the BuildMCP version."""
    return f"buildmcp {__version__} ok"


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
