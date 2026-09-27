"""Configs: YAML/TOML/JSON/.properties edits that keep comments, key paths, backups, diff/restore,
secret masking, the file sandbox, and srv_link wiring a Velocity proxy to Paper backends."""

import json
import zipfile

import pytest

from buildmcp.admin import configs, network, props, registry


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    for var in ("BUILDMCP_SERVER_DIR", "BUILDMCP_RCON_PASSWORD", "BUILDMCP_BRIDGE_TOKEN"):
        monkeypatch.setenv(var, "")
    from buildmcp.live import connector

    connector.forget()
    return tmp_path


PAPER_GLOBAL = """\
# This is the global configuration file for Paper.
# As you can see, there's a lot to configure.

_version: 29
anticheat:
  obfuscation:
    items:
      hide-durability: false
    hidden-blocks:
    - copper_ore
    - deepslate_copper_ore
proxies:
  bungee-cord:
    online-mode: true
  proxy-protocol: false
  velocity:
    enabled: false
    online-mode: true
    secret: ''
messages:
  no-permission: '<red>I''m sorry, but you do not have permission to perform this command.'
"""

PLUGIN_CONFIG = """\
# LuckPerms configuration
server: global   # the name of this server

storage-method: h2
data:
  # Uses standard DB engine port by default
  address: localhost
  database: minecraft
  username: root
  password: hunter2
worlds:
  - name: world
    border: 5000
  - name: world_nether
    border: 1000
"""

VELOCITY_TOML = """\
# Config version. Do not change this
config-version = "2.7"

# What port should the proxy be bound to? By default, we'll bind to all addresses on port 25565.
bind = "0.0.0.0:25565"

# Should we authenticate players with Mojang? By default, this is on.
online-mode = true

# Should we forward IP addresses and other data to backend servers?
player-info-forwarding-mode = "NONE"

# If you are using modern or BungeeGuard IP forwarding, configure a file that contains a unique secret here.
forwarding-secret-file = "forwarding.secret"

[servers]
# Configure your servers here. Each key represents the server's name, and the value
# represents the IP address of the server to connect to.
lobby = "127.0.0.1:30066"
factions = "127.0.0.1:30067"
minigames = "127.0.0.1:30068"

# In what order we should try servers when a player logs in or is kicked from a server.
try = [
    "lobby"
]

[forced-hosts]
# Configure your forced hosts here.
"lobby.example.com" = [
    "lobby"
]
"factions.example.com" = [
    "factions"
]

[advanced]
compression-threshold = 256
"""


def server(data, name="lobby", software="paper", port=25566):
    d = data / name
    d.mkdir(parents=True, exist_ok=True)
    e = registry.ServerEntry(name=name, dir=str(d), software=software, version="1.21.8", jar=f"{software}.jar",
                             port=port)
    registry.put(e)
    return registry.get(name)


def test_yaml_edits_keep_comments_and_style(data):
    e = server(data)
    (e.path / "config").mkdir()
    (e.path / "config" / "paper-global.yml").write_text(PAPER_GLOBAL, "utf-8")
    rep = configs.apply(e, "paper-global", {"proxies.velocity.enabled": True, "proxies.velocity.secret": "s3cr3t",
                                            "anticheat.obfuscation.hidden-blocks[2]": "iron_ore",
                                            "chunk-loading.player-max-chunk-load-rate": 100.0})
    changed = {c["path"]: c for c in rep["changed"]}
    assert changed["proxies.velocity.secret"]["new"] == "***" and rep["backup"]
    text = (e.path / "config" / "paper-global.yml").read_text("utf-8")
    # byte for byte the old file with only these changes: comments, list style and quoting are kept
    want = (PAPER_GLOBAL.replace("enabled: false", "enabled: true").replace("secret: ''", "secret: 's3cr3t'")
            .replace("    - deepslate_copper_ore\n", "    - deepslate_copper_ore\n    - iron_ore\n")
            + "chunk-loading:\n  player-max-chunk-load-rate: 100.0\n")
    assert text == want
    assert configs.read(e, "paper-global", "proxies.velocity.secret")["value"] == "***"
    assert configs.read(e, "paper-global", "proxies.velocity.secret", reveal=True)["value"] == "s3cr3t"
    assert configs.apply(e, "paper-global", {"proxies.velocity.enabled": True})["changed"] == []  # already so

    p = e.path / "plugins" / "LuckPerms"
    p.mkdir(parents=True)
    (p / "config.yml").write_text(PLUGIN_CONFIG, "utf-8")
    rep = configs.apply(e, "LuckPerms", {"storage-method": "mysql", "worlds[1].border": 2000,
                                         'data."pool-settings.size"': 10}, unset=["data.username"])
    text = (p / "config.yml").read_text("utf-8")
    assert "server: global   # the name of this server" in text and "  # Uses standard DB engine port" in text
    assert "storage-method: mysql" in text and "    border: 2000" in text and "username" not in text
    assert "  - name: world_nether\n" in text                               # the plugin's list style is kept
    assert "pool-settings.size: 10" in text
    assert {c["path"] for c in rep["changed"]} == {"storage-method", "worlds[1].border", 'data."pool-settings.size"',
                                                   "data.username"}
    got = configs.read(e, "LuckPerms")
    assert "password: '***'" in got["text"] and "hunter2" not in got["text"]
    assert "hunter2" in configs.read(e, "LuckPerms", reveal=True)["text"]
    ol = configs.outline(e, "LuckPerms", depth=2)["keys"]
    assert 'data.password = "***"' in ol and "storage-method = \"mysql\"" in ol

    d = configs.diff(e, "LuckPerms")["diff"]
    assert any(l.startswith("-storage-method: h2") for l in d) and any(l.startswith("+storage-method: mysql") for l in d)
    configs.restore(e, "LuckPerms")
    assert (p / "config.yml").read_text("utf-8") == PLUGIN_CONFIG
    assert len(configs.backups(e, "LuckPerms")) == 2


def test_toml_json_properties_and_text(data):
    e = server(data, "proxy", "velocity", 25565)
    (e.path / "velocity.toml").write_text(VELOCITY_TOML, "utf-8")
    configs.apply(e, "velocity", {"online-mode": False, "advanced.compression-threshold": 512,
                                  "servers.anarchy": "127.0.0.1:25567"})
    t = (e.path / "velocity.toml").read_text("utf-8")
    assert "# Should we authenticate players with Mojang?" in t and "online-mode = false" in t
    assert 'anarchy = "127.0.0.1:25567"' in t and "compression-threshold = 512" in t
    assert configs.read(e, "velocity", "servers.try")["value"] == ["lobby"]

    lobby = server(data)
    (lobby.path / "ops.json").write_text(json.dumps([{"uuid": "u1", "name": "Steve", "level": 4}], indent=2))
    configs.apply(lobby, "ops", {"[0].level": 3})
    assert json.loads((lobby.path / "ops.json").read_text())[0]["level"] == 3
    assert (lobby.path / "ops.json").read_text().startswith("[\n  {\n    \"uuid\"")
    (lobby.path / "server.properties").write_text("#Minecraft server properties\nmotd=A\nrcon.password=pw\n")
    rep = configs.apply(lobby, "server", {"motd": "B", "view-distance": 8}, unset=["rcon.password"])
    assert {c["path"] for c in rep["changed"]} == {"motd", "view-distance", "rcon.password"} and rep["backup"]
    assert props.read(lobby.path / "server.properties") == {"motd": "B", "view-distance": "8"}
    with pytest.raises(configs.ConfigError, match="plain text"):
        configs.apply(lobby, "notes.txt", {"a": 1}, create=True)
    configs.write_text(lobby, "notes.txt", "hello\n")
    with pytest.raises(configs.ConfigError, match="not valid yaml"):
        configs.write_text(lobby, "plugins/X/config.yml", "a: [unclosed\n")
    assert not (lobby.path / "plugins" / "X" / "config.yml").exists()


def test_sandbox_files_and_find(data):
    e = server(data)
    (e.path / "world").mkdir()
    (e.path / "world" / "level.dat").write_bytes(b"\x00")
    (e.path / "world" / "stuff.yml").write_text("a: 1\n")
    (e.path / "logs").mkdir()
    (e.path / "logs" / "x.yml").write_text("a: 1\n")
    (e.path / "spigot.yml").write_text("settings:\n  bungeecord: false\nworld-settings:\n  default:\n"
                                       "    view-distance: default\n")
    (e.path / "server.properties").write_text("view-distance=10\nrcon.password=abc\n")
    (e.path / "paper.jar").write_bytes(b"PK")
    names = {f["file"] for f in configs.list_files(e)}
    assert names == {"spigot.yml", "server.properties"}
    for bad in ("../outside.yml", "/etc/passwd", "paper.jar"):
        with pytest.raises(configs.ConfigError):
            configs.resolve_file(e, bad)
    hits = configs.find(e, "view-distance")["hits"]
    assert {(h["file"], h.get("path")) for h in hits} == {("spigot.yml", "world-settings.default.view-distance"),
                                                          ("server.properties", "view-distance")}
    pw = configs.find(e, "rcon")["hits"]
    assert pw == [{"file": "server.properties", "path": "rcon.password", "value": "***"}]
    assert configs.parse_path('a.b[0]."c.d"') == ["a", "b", 0, "c.d"]


def _velocity_jar(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("default-velocity.toml", VELOCITY_TOML)
        z.writestr("com/velocitypowered/proxy/Velocity.class", b"\xca\xfe\xba\xbe")


def test_link_a_network(data):
    proxy = server(data, "proxy", "velocity", 25565)
    _velocity_jar(proxy.path / "velocity.jar")
    assert network.ensure_bind(proxy) == "0.0.0.0:25565"
    lobby = server(data, "lobby", port=25566)
    lobby.role = "lobby"
    registry.put(lobby)
    anarchy = server(data, "anarchy", port=25567)
    for b in (lobby, anarchy):
        (b.path / "server.properties").write_text("#Minecraft server properties\nonline-mode=true\nserver-port="
                                                  f"{b.port}\n")
    (anarchy.path / "spigot.yml").write_text("# spigot\nsettings:\n  bungeecord: true\n")
    (lobby.path / "config").mkdir()
    (lobby.path / "config" / "paper-global.yml").write_text(PAPER_GLOBAL, "utf-8")

    rep = network.link(registry.get("proxy"), [registry.get("anarchy"), registry.get("lobby")],
                       forced_hosts={"anarchy.example.net": ["anarchy"]})
    assert rep["try"] == ["lobby"] and rep["online_mode"] is True
    t = (proxy.path / "velocity.toml").read_text("utf-8")
    assert 'player-info-forwarding-mode = "MODERN"' in t and "# Should we forward IP addresses" in t
    assert 'lobby = "127.0.0.1:25566"' in t and 'anarchy = "127.0.0.1:25567"' in t
    assert "factions" not in t and "minigames" not in t and "example.com" not in t
    assert '"anarchy.example.net"' in t
    secret = (proxy.path / "forwarding.secret").read_text().strip()
    assert len(secret) == 24 and secret not in json.dumps(rep)          # the secret never shows
    for b in (lobby, anarchy):
        pg = configs.read(b, "paper-global", "proxies.velocity", reveal=True)["value"]
        assert pg == {"enabled": True, "online-mode": True, "secret": secret}
        pr = props.read(b.path / "server.properties")
        assert pr["online-mode"] == "false" and pr["server-ip"] == "127.0.0.1"
        assert registry.get(b.name).network == "proxy"
    assert "# This is the global configuration file" in (lobby.path / "config" / "paper-global.yml").read_text()
    assert configs.read(anarchy, "spigot", "settings.bungeecord")["value"] is False
    # linking again changes nothing
    again = network.link(registry.get("proxy"), [registry.get("anarchy"), registry.get("lobby")],
                         forced_hosts={"anarchy.example.net": ["anarchy"]})
    assert again["files"] == []
    with pytest.raises(network.NetworkError, match="not linked"):
        network.link(registry.get("proxy"), [registry.get("lobby")], try_order=["anarchy"])


def test_srv_link_tool_moves_the_public_port(data):
    from buildmcp import admin_tools

    lobby = server(data, "lobby", port=25565)
    (lobby.path / "server.properties").write_text("server-port=25565\n")
    proxy = server(data, "proxy", "velocity", 25566)
    _velocity_jar(proxy.path / "velocity.jar")
    out = json.loads(admin_tools.srv_link(proxy="proxy", backends=["lobby"], proxy_port=25565, online_mode=False))
    assert registry.get("proxy").port == 25565 and registry.get("lobby").port != 25565
    new = registry.get("lobby").port
    assert props.read(lobby.path / "server.properties")["server-port"] == str(new)
    t = (proxy.path / "velocity.toml").read_text()
    assert 'bind = "0.0.0.0:25565"' in t and f'lobby = "127.0.0.1:{new}"' in t and "online-mode = false" in t
    assert "stack:proxy-offline" in out["warning"] and len(out["ports"]) == 2
    assert admin_tools.srv_link(proxy="lobby", backends=["proxy"]).startswith("Error")
