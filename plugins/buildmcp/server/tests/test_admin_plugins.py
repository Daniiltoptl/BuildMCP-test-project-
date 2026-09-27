"""Plugins: descriptors, release picking, and the installer against fake Modrinth / Hangar / Spiget /
GitHub answers serving generated plugin jars (dependencies, fallbacks, checksums, platforms, update,
remove, disable), the log report, and the plugins tool restarting a fake server."""

import hashlib
import io
import json
import sys
import textwrap
import zipfile

import httpx
import pytest

from buildmcp.admin import catalog, installer, jarinfo, net, registry, sources


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    for var in ("BUILDMCP_SERVER_DIR", "BUILDMCP_RCON_PASSWORD", "BUILDMCP_BRIDGE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.setenv(var, "")
    from buildmcp.live import connector

    connector.forget()
    yield tmp_path
    net.set_transport(None)


def make_jar(plugin_yml: str = "", velocity: dict | None = None, paper_yml: str = "", bungee: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if plugin_yml:
            z.writestr("plugin.yml", textwrap.dedent(plugin_yml))
        if paper_yml:
            z.writestr("paper-plugin.yml", textwrap.dedent(paper_yml))
        if velocity is not None:
            z.writestr("velocity-plugin.json", json.dumps(velocity))
        if bungee:
            z.writestr("bungee.yml", bungee)
        z.writestr("com/example/Main.class", b"\xca\xfe\xba\xbe")
    return buf.getvalue()


def yml(name: str, version: str, depend: list[str] | None = None, extra: str = "") -> str:
    s = f"name: {name}\nversion: '{version}'\nmain: com.example.Main\napi-version: '1.21'\n"
    if depend:
        s += f"depend: [{', '.join(depend)}]\n"
    return s + extra


# ------------------------------------------------------------------ descriptors
def test_jarinfo_reads_every_descriptor(tmp_path):
    p = tmp_path / "fawe.jar"
    p.write_bytes(make_jar(yml("FastAsyncWorldEdit", "2.12", extra="provides: [WorldEdit]\nfolia-supported: true\n")))
    i = jarinfo.read(p)
    assert (i.name, i.version, i.kind, i.provides) == ("FastAsyncWorldEdit", "2.12", "bukkit", ["WorldEdit"])
    assert i.names == {"fastasyncworldedit", "worldedit"} and jarinfo.fits(i, "folia") is None

    pp = tmp_path / "pp.jar"
    pp.write_bytes(make_jar(paper_yml="""
        name: Shiny
        version: 1.0
        main: a.B
        dependencies:
          server:
            Vault: {load: BEFORE, required: true}
            PlaceholderAPI: {load: BEFORE, required: false}
    """))
    s = jarinfo.read(pp)
    assert s.kind == "paper" and s.depend == ["Vault"] and s.softdepend == ["PlaceholderAPI"]
    assert "does not declare folia-supported" in jarinfo.fits(s, "folia")

    uni = tmp_path / "via.jar"  # ViaVersion-style: one jar for Paper and Velocity
    uni.write_bytes(make_jar(yml("ViaVersion", "5.2.0"), velocity={"id": "viaversion", "name": "ViaVersion",
                                                                   "version": "5.2.0", "main": "a.V"}))
    assert jarinfo.read(uni, "velocity").kind == "velocity" and jarinfo.read(uni, "paper").kind == "bukkit"
    assert jarinfo.fits(jarinfo.read(uni, "velocity"), "velocity") is None
    assert jarinfo.fits(jarinfo.read(uni), "paper") is None

    vel = tmp_path / "lp-velocity.jar"
    vel.write_bytes(make_jar(velocity={"id": "luckperms", "name": "LuckPerms", "version": "5.4",
                                       "dependencies": [{"id": "limboapi", "optional": False},
                                                        {"id": "tab", "optional": True}]}))
    v = jarinfo.read(vel, "velocity")
    assert v.id == "luckperms" and v.depend == ["limboapi"] and v.softdepend == ["tab"]
    assert "install it on the proxy" in jarinfo.fits(v, "paper")
    bungee = tmp_path / "b.jar"
    bungee.write_bytes(make_jar(bungee="name: B\nmain: a.B\n"))
    assert "not for Paper" in jarinfo.fits(jarinfo.read(bungee), "paper")
    assert "not a Velocity one" in jarinfo.fits(jarinfo.read(p), "velocity")
    junk = tmp_path / "lib.jar"
    junk.write_bytes(make_jar())
    with pytest.raises(jarinfo.NotAPlugin):
        jarinfo.read(junk)
    (tmp_path / "text.jar").write_text("nope")
    with pytest.raises(jarinfo.NotAPlugin):
        jarinfo.read(tmp_path / "text.jar")


def test_pick_release_for_the_minecraft_version():
    R = sources.Release
    rs = [R("modrinth", "x", "X", "3.0-beta", "x3.jar", "u3", mc_versions=["1.21.5"], channel="beta"),
          R("modrinth", "x", "X", "2.0", "x2.jar", "u2", mc_versions=["1.21.3", "1.21.4"]),
          R("modrinth", "x", "X", "1.0", "x1.jar", "u1", mc_versions=["1.20.6"])]
    assert sources.pick(rs, "1.21.4").version == "2.0"
    assert sources.pick(rs, "1.20.6").version == "1.0"
    r = sources.pick(rs, "1.21.8")
    assert r.version == "2.0" and "up to 1.21.4" in r.note          # same line, with a note
    r = sources.pick(rs, "26.1")
    assert r.version == "2.0" and "not 26.1" in r.note               # newest stable, with a warning
    assert sources.pick([], "1.21.4") is None
    assert sources._hangar_range_has("1.8-1.21.4", "1.20.1") and not sources._hangar_range_has("1.8-1.20", "1.21")
    assert sources.parse_spec("github:MilkBowl/Vault#^Vault\\.jar$") == ("github", "MilkBowl/Vault", "^Vault\\.jar$")
    assert sources.parse_spec("https://x.org/a.jar") == ("url", "https://x.org/a.jar", "")
    with pytest.raises(sources.SourceError):
        sources.parse_spec("luckperms")


def test_catalog_is_consistent():
    for alias, e in catalog.CATALOG.items():
        assert e["sources"] and e["platforms"] and e["about"], alias
        assert set(e["platforms"]) <= {"paper", "folia", "velocity"}, alias
        for spec in e["sources"]:
            sources.parse_spec(spec)
        for req in e["requires"]:
            for a in req.split("|"):
                assert a in catalog.CATALOG, (alias, a)
    for name, st in catalog.STACKS.items():
        for a in st["plugins"]:
            assert a in catalog.CATALOG, (name, a)
        if name.startswith("proxy"):
            assert all("velocity" in catalog.CATALOG[a]["platforms"] for a in st["plugins"]), name
    assert catalog.find("WorldEdit")["alias"] == "worldedit" and catalog.find("Essentials")["alias"] == "essentialsx"
    assert catalog.find("geyser-velocity")["alias"] == "geyser" and catalog.find("nope") is None


# ------------------------------------------------------------------ a fake plugin world
class Repo:
    """Fake Modrinth, Hangar, Spiget, GitHub and Jenkins answering from dicts; counts downloads."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.modrinth: dict[str, dict] = {}
        self.hangar: dict[str, dict] = {}
        self.spigot: dict[str, dict] = {}
        self.github: dict[str, list] = {}
        self.downloads: list[str] = []
        self.fail: set[str] = set()   # URL prefixes answering 500

    def file(self, url: str, content: bytes) -> dict:
        self.files[url] = content
        return {"sha512": hashlib.sha512(content).hexdigest(), "sha1": hashlib.sha1(content).hexdigest()}

    def add_modrinth(self, slug: str, versions: list[dict], pid: str = "") -> None:
        """versions: {"v", "mc": [...], "loaders": [...], "jar": bytes, "file", "deps": [...], "type", "bad_hash"}"""
        out = []
        for v in versions:
            url = f"https://cdn.modrinth.com/data/{slug}/{v['file']}"
            h = self.file(url, v["jar"])
            if v.get("bad_hash"):
                h = {"sha512": "0" * 128}
            files = [{"filename": v["file"], "url": url, "primary": True, "hashes": h}]
            for extra in v.get("extra_files", []):
                eu = f"https://cdn.modrinth.com/data/{slug}/{extra['file']}"
                files.append({"filename": extra["file"], "url": eu, "primary": False,
                              "hashes": self.file(eu, extra["jar"])})
            out.append({"version_number": v["v"], "game_versions": v.get("mc", []), "loaders": v["loaders"],
                        "version_type": v.get("type", "release"), "files": files,
                        "dependencies": v.get("deps", [])})
        self.modrinth[slug] = {"slug": slug, "id": pid or slug.upper(), "title": slug.title(), "versions": out}

    def handler(self, req: httpx.Request) -> httpx.Response:
        u = str(req.url).split("?")[0]
        if any(u.startswith(p) for p in self.fail):
            return httpx.Response(500, text="boom")
        if u in self.files:
            self.downloads.append(u)
            return httpx.Response(200, content=self.files[u])
        path = req.url.path
        if req.url.host == "api.modrinth.com":
            if path == "/v2/search":
                hits = [{"slug": s, "title": p["title"], "description": f"{s} plugin", "downloads": 10}
                        for s, p in self.modrinth.items() if req.url.params["query"] in s]
                return httpx.Response(200, json={"hits": hits})
            parts = path.split("/")  # /v2/project/<id>[/version]
            proj = next((p for s, p in self.modrinth.items() if parts[3] in (s, p["id"])), None)
            if proj is None:
                return httpx.Response(404, json={"error": "not_found"})
            if len(parts) == 4:
                return httpx.Response(200, json={"slug": proj["slug"], "id": proj["id"], "title": proj["title"]})
            loaders = set(json.loads(req.url.params["loaders"]))
            return httpx.Response(200, json=[v for v in proj["versions"] if loaders & set(v["loaders"])])
        if req.url.host == "hangar.papermc.io":
            parts = path.split("/")  # /api/v1/projects/<slug>[/versions]
            if path == "/api/v1/projects":
                return httpx.Response(200, json={"result": [
                    {"name": s, "namespace": {"owner": "o", "slug": s}, "description": "d", "stats": {"downloads": 5}}
                    for s in self.hangar if req.url.params["q"].lower() in s.lower()]})
            proj = self.hangar.get(parts[4])
            if proj is None:
                return httpx.Response(404, json={"message": "not found"})
            if len(parts) == 5:
                return httpx.Response(200, json={"name": parts[4], "namespace": {"owner": "o", "slug": parts[4]}})
            return httpx.Response(200, json={"result": proj["versions"]})
        if req.url.host == "api.spiget.org":
            parts = path.split("/")  # /v2/resources/<id>[/versions/latest]
            if parts[2] == "search":
                return httpx.Response(200, json=[{"id": int(k), "name": v["name"], "tag": "t", "downloads": 1}
                                                 for k, v in self.spigot.items()])
            res = self.spigot.get(parts[3])
            if res is None:
                return httpx.Response(404, json={"error": "resource not found"})
            if len(parts) == 4:
                return httpx.Response(200, json=res)
            if parts[4] == "versions":
                return httpx.Response(200, json={"name": res["version"]})
        if req.url.host == "api.github.com":
            repo = "/".join(path.split("/")[2:4])
            if repo in self.github:
                return httpx.Response(200, json=self.github[repo])
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404, text="no such thing")


def add_spigot(repo: Repo, rid: str, name: str, version: str, jar: bytes, premium=False):
    repo.spigot[rid] = {"id": int(rid), "name": name, "version": version, "premium": premium,
                        "file": {"type": ".jar"}, "testedVersions": ["1.20", "1.21"]}
    repo.files[f"https://api.spiget.org/v2/resources/{rid}/download"] = jar


PAPER_LOADERS = ["bukkit", "spigot", "paper", "purpur"]


@pytest.fixture
def repo(data):
    r = Repo()
    lp_bukkit = make_jar(yml("LuckPerms", "5.4.141"))
    lp_velocity = make_jar(velocity={"id": "luckperms", "name": "LuckPerms", "version": "5.4.141"})
    r.add_modrinth("luckperms", [
        {"v": "v5.4.141-bukkit", "mc": ["1.21.4", "1.21.5"], "loaders": PAPER_LOADERS + ["folia"],
         "file": "LuckPerms-Bukkit-5.4.141.jar", "jar": lp_bukkit},
        {"v": "v5.4.141-velocity", "mc": ["1.21.4"], "loaders": ["velocity"], "file": "LuckPerms-Velocity-5.4.141.jar",
         "jar": lp_velocity}])
    r.add_modrinth("worldedit", [{"v": "7.3.10", "mc": ["1.21.4"], "loaders": PAPER_LOADERS,
                                  "file": "worldedit-bukkit-7.3.10.jar", "jar": make_jar(yml("WorldEdit", "7.3.10"))}])
    r.add_modrinth("fastasyncworldedit", [{"v": "2.12.3", "mc": ["1.21.4"], "loaders": PAPER_LOADERS,
                                           "file": "FastAsyncWorldEdit-Paper-2.12.3.jar",
                                           "jar": make_jar(yml("FastAsyncWorldEdit", "2.12.3",
                                                               extra="provides: [WorldEdit]\n"))}])
    r.add_modrinth("worldguard", [{"v": "7.0.13", "mc": ["1.21.4"], "loaders": PAPER_LOADERS,
                                   "file": "worldguard-bukkit-7.0.13.jar",
                                   "jar": make_jar(yml("WorldGuard", "7.0.13", ["WorldEdit"]))}])
    via = make_jar(yml("ViaVersion", "5.2.0"), velocity={"id": "viaversion", "name": "ViaVersion", "version": "5.2.0"})
    r.add_modrinth("viaversion", [{"v": "5.2.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS + ["velocity"],
                                   "file": "ViaVersion-5.2.0.jar", "jar": via}])
    # Geyser-style: one version, a jar per platform
    r.add_modrinth("geyser", [{"v": "2.6.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS + ["velocity"],
                               "file": "Geyser-Spigot.jar", "jar": make_jar(yml("Geyser-Spigot", "2.6.0")),
                               "extra_files": [{"file": "Geyser-Velocity.jar", "jar": make_jar(
                                   velocity={"id": "geyser", "name": "Geyser", "version": "2.6.0"})}]}])
    r.add_modrinth("coollib", [{"v": "1.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS, "file": "CoolLib-1.0.jar",
                                "jar": make_jar(yml("CoolLib", "1.0"))}], pid="CLIB1")
    r.add_modrinth("coolplugin", [{"v": "2.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS, "file": "Cool-2.0.jar",
                                   "jar": make_jar(yml("CoolPlugin", "2.0", ["CoolLib"])),
                                   "deps": [{"project_id": "CLIB1", "dependency_type": "required"},
                                            {"project_id": "OPT1", "dependency_type": "optional"}]}])
    r.add_modrinth("ghostly", [{"v": "1.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS, "file": "Ghostly.jar",
                                "jar": make_jar(yml("Ghostly", "1.0", ["Ghost"]))}])
    r.add_modrinth("damaged", [{"v": "1.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS, "file": "Damaged.jar",
                                "jar": make_jar(yml("Damaged", "1.0")), "bad_hash": True}])
    r.add_modrinth("proxyonly", [{"v": "1.0", "mc": ["1.21.4"], "loaders": PAPER_LOADERS, "file": "ProxyOnly.jar",
                                  "jar": make_jar(velocity={"id": "proxyonly", "name": "ProxyOnly", "version": "1"})}])
    add_spigot(r, "34315", "Vault", "1.7.3", make_jar(yml("Vault", "1.7.3")))
    add_spigot(r, "99999", "Paid", "1.0", b"", premium=True)
    # PlaceholderAPI on Hangar
    papi = make_jar(yml("PlaceholderAPI", "2.11.6"))
    r.files["https://hangar.papermc.io/api/v1/projects/PlaceholderAPI/versions/2.11.6/PAPER/download"] = papi
    r.hangar["PlaceholderAPI"] = {"versions": [{
        "name": "2.11.6", "channel": {"name": "Release"},
        "platformDependencies": {"PAPER": ["1.8-1.21.4"]}, "pluginDependencies": {},
        "downloads": {"PAPER": {"fileInfo": {"name": "PlaceholderAPI-2.11.6.jar",
                                             "sha256Hash": hashlib.sha256(papi).hexdigest()},
                                "downloadUrl": "https://hangar.papermc.io/api/v1/projects/PlaceholderAPI/versions/"
                                               "2.11.6/PAPER/download"}}}]}
    net.set_transport(httpx.MockTransport(r.handler))
    return r


def server(data, name="lobby", software="paper", version="1.21.4") -> registry.ServerEntry:
    d = data / name
    (d / "plugins").mkdir(parents=True)
    e = registry.ServerEntry(name=name, dir=str(d), software=software, version=version, jar="core.jar")
    registry.put(e)
    return registry.get(name)


def rows(rep) -> dict:
    return {r["want"]: r for r in rep["result"]}


# ------------------------------------------------------------------ install
def test_install_pulls_dependencies_and_writes_the_lock(repo, data):
    e = server(data)
    rep = installer.install(e, ["worldguard"])
    got = rows(rep)
    assert got["worldguard"]["status"] == "installed" and got["worldguard"]["version"] == "7.0.13"
    assert got["worldedit"]["status"] == "installed" and got["worldedit"]["by"] == "needed by WorldGuard"
    names = sorted(p.name for p in (e.path / "plugins").iterdir())
    assert names == ["worldedit-bukkit-7.3.10.jar", "worldguard-bukkit-7.0.13.jar"]
    lock = installer.load_lock(e)
    assert lock["WorldGuard"]["spec"] == "modrinth:worldguard" and lock["WorldEdit"]["version"] == "7.3.10"
    assert rep["changed"] and not (e.state_dir() / "staging").exists()
    # the second time nothing is downloaded
    n = len(repo.downloads)
    again = rows(installer.install(e, ["worldguard"]))
    assert again["worldguard"]["status"] == "present" and len(repo.downloads) == n


def test_fawe_provides_worldedit_in_any_order(repo, data):
    for order in (["fastasyncworldedit", "worldguard"], ["worldguard", "fastasyncworldedit"]):
        e = server(data, name="s" + str(len(order[0])))
        got = rows(installer.install(e, order))
        assert "worldedit" not in got, got
        assert got["worldguard"]["status"] == got["fastasyncworldedit"]["status"] == "installed"


def test_dependencies_named_by_the_source_and_unknown_ones(repo, data):
    e = server(data)
    got = rows(installer.install(e, ["modrinth:coolplugin", "modrinth:ghostly"]))
    assert got["modrinth:coolplugin"]["status"] == "installed"
    assert got["modrinth:CLIB1"]["status"] == "installed" and got["modrinth:CLIB1"]["name"] == "CoolLib"
    assert "modrinth:OPT1" not in got                              # optional ones are not pulled
    assert got["modrinth:ghostly"]["status"] == "skipped" and "needs Ghost" in got["modrinth:ghostly"]["detail"]
    assert not (e.path / "plugins" / "Ghostly.jar").exists()
    # deps=False installs it anyway and says what is missing
    got = rows(installer.install(e, ["modrinth:ghostly"], deps=False))
    assert got["modrinth:ghostly"]["status"] == "installed" and "needs Ghost" in got["modrinth:ghostly"]["detail"]


def test_fallback_source_checksum_and_refusals(repo, data):
    e = server(data)
    got = rows(installer.install(e, ["vault", "modrinth:damaged", "spigot:99999", "modrinth:proxyonly", "nonsense"]))
    v = got["vault"]
    assert v["status"] == "installed" and v["source"] == "spigot:34315"
    assert v["fell_back_after"][0].startswith("github:MilkBowl/Vault")  # github 404 was tried first
    assert (e.path / "plugins" / "Vault.jar").exists()
    assert got["modrinth:damaged"]["status"] == "failed" and "sha512 mismatch" in got["modrinth:damaged"]["detail"]
    assert got["spigot:99999"]["status"] == "failed" and "premium" in got["spigot:99999"]["detail"]
    assert "install it on the proxy" in got["modrinth:proxyonly"]["detail"]
    assert got["nonsense"]["status"] == "failed" and "search" in got["nonsense"]["detail"]
    assert sorted(p.name for p in (e.path / "plugins").iterdir()) == ["Vault.jar"]
    assert installer.load_lock(e)["Vault"]["spec"] == "spigot:34315"


def test_platforms_velocity_and_folia(repo, data):
    proxy = server(data, "proxy", "velocity", "3.4.0-SNAPSHOT")
    got = rows(installer.install(proxy, ["luckperms", "viaversion", "geyser", "essentialsx"]))
    assert got["luckperms"]["status"] == "installed" and got["luckperms"]["file"] == "LuckPerms-Velocity-5.4.141.jar"
    assert got["viaversion"]["status"] == "installed"
    assert got["geyser"]["file"] == "Geyser-Velocity.jar"            # the velocity jar of a multi-jar version
    assert got["essentialsx"]["status"] == "skipped" and "velocity" in got["essentialsx"]["detail"]
    lobby = server(data, "lobby")
    assert rows(installer.install(lobby, ["geyser"]))["geyser"]["file"] == "Geyser-Spigot.jar"
    folia = server(data, "folia", "folia")
    got = rows(installer.install(folia, ["worldedit", "modrinth:coolplugin"]))
    assert got["worldedit"]["status"] == "skipped"
    assert got["modrinth:coolplugin"]["status"] == "failed"         # no folia build on the source


def test_stack_and_hangar(repo, data):
    proxy = server(data, "proxy", "velocity", "3.4.0")
    rep = installer.install(proxy, ["stack:proxy"], dry_run=True)
    assert rep["dry_run"] and {r["want"] for r in rep["plan"]} >= {"luckperms", "viaversion", "spark"}
    assert not list((proxy.path / "plugins").iterdir()) and not installer.load_lock(proxy)
    lobby = server(data, "lobby")
    got = rows(installer.install(lobby, ["placeholderapi"]))
    assert got["placeholderapi"]["status"] == "installed" and got["placeholderapi"]["source"] == "hangar:PlaceholderAPI"
    plan = rows({"result": installer.install(lobby, ["worldguard"], dry_run=True)["plan"]})
    assert plan["worldguard"]["status"] == "planned" and plan["worldedit"]["by"] == "needed by WorldGuard"


def test_update_disable_enable_remove(repo, data):
    e = server(data)
    old = e.path / "plugins" / "LuckPerms-Bukkit-5.4.100.jar"
    old.write_bytes(make_jar(yml("LuckPerms", "5.4.100")))
    assert rows(installer.install(e, ["luckperms"]))["luckperms"]["status"] == "present"
    rep = installer.update(e)
    got = rows(rep)
    assert got["LuckPerms"]["status"] == "updated" and got["LuckPerms"]["from"] == "5.4.100"
    assert not old.exists() and (e.path / "plugins" / "LuckPerms-Bukkit-5.4.141.jar").exists()
    assert list((e.state_dir() / "removed").rglob("LuckPerms-Bukkit-5.4.100.jar"))
    n = len(repo.downloads)
    got = rows(installer.update(e, ["luckperms"]))
    assert got["LuckPerms"]["status"] == "up to date" and len(repo.downloads) == n   # known from the lock
    (e.path / "plugins" / "Handmade.jar").write_bytes(make_jar(yml("Handmade", "1")))
    got = rows(installer.update(e))
    assert got["Handmade"]["status"] == "skipped" and "source unknown" in got["Handmade"]["detail"]

    assert rows(installer.set_enabled(e, ["luckperms"], False))["luckperms"]["status"] == "disabled"
    assert (e.path / "plugins" / "LuckPerms-Bukkit-5.4.141.jar.disabled").exists()
    assert rows(installer.install(e, ["luckperms"]))["luckperms"]["status"] == "skipped"
    assert rows(installer.set_enabled(e, ["LuckPerms"], True))["LuckPerms"]["status"] == "enabled"
    assert installer.load_lock(e)["LuckPerms"]["file"] == "LuckPerms-Bukkit-5.4.141.jar"

    installer.install(e, ["worldguard"])
    (e.path / "plugins" / "WorldEdit").mkdir()
    rep = installer.remove(e, ["worldedit"])
    r = rows(rep)["worldedit"]
    assert r["status"] == "removed" and "WorldGuard" in r["warning"] and r["data"].startswith("kept")
    assert "WorldEdit" not in installer.load_lock(e)
    lst = installer.listing(e)
    wg = next(p for p in lst["plugins"] if p["name"] == "WorldGuard")
    assert wg["missing"] == ["WorldEdit"] and wg["source"] == "modrinth:worldguard"
    assert next(p for p in lst["plugins"] if p["name"] == "Handmade")["source"] == "by hand"


def test_search_merges_sources_and_names_the_unreachable(repo, data):
    repo.hangar["ViaBackwards"] = {"versions": []}
    repo.fail.add("https://api.spiget.org/")
    out = installer.search("via", "paper", "1.21.4")
    assert [h["spec"] for h in out["modrinth"]] == ["modrinth:viaversion"]
    assert [h["spec"] for h in out["hangar"]] == ["hangar:ViaBackwards"]
    assert "spigot" in out["unreachable"] and {c["alias"] for c in out["catalog"]} >= {"viaversion", "viabackwards"}
    info = installer.info(["worldguard"], "paper", "1.21.4")
    assert info[0]["release"]["version"] == "7.0.13" and info[0]["requires"] == ["worldedit|fastasyncworldedit"]


# ------------------------------------------------------------------ the log report
PAPER_LOG = """\
[10:00:00 INFO]: [bootstrap] Running Java 21 (OpenJDK 64-Bit Server VM 21.0.5) on Linux
[10:00:01 ERROR]: [ModernPluginLoadingStrategy] Could not load plugin 'Broken.jar' in folder 'plugins'
org.bukkit.plugin.InvalidDescriptionException: Invalid plugin.yml
	at io.papermc.paper.Something(Something.java:1)
[10:00:01 ERROR]: [ModernPluginLoadingStrategy] Could not load 'plugins/WorldGuard.jar' in 'plugins'
org.bukkit.plugin.UnknownDependencyException: Unknown/missing dependency plugins: [WorldEdit]. Please download and install these plugins to run 'WorldGuard'.
[10:00:02 INFO]: Starting minecraft server version 1.21.4
[10:00:05 INFO]: [LuckPerms] Enabling LuckPerms v5.4.141
[10:00:05 INFO]: [Essentials] Enabling Essentials v2.21.0
[10:00:06 ERROR]: Error occurred while enabling TAB v5.0.3 (Is it up to date?)
java.lang.NoClassDefFoundError: org/bukkit/Something
	at me.neznamy.tab.Plugin.onEnable(Plugin.java:10)
[10:00:06 INFO]: [Essentials] Disabling Essentials v2.21.0
[10:00:07 INFO]: Done (7.123s)! For help, type "help"
[10:05:00 INFO]: Stopping server
[10:05:00 INFO]: [LuckPerms] Disabling LuckPerms v5.4.141
"""


def test_load_report_reads_a_paper_start():
    rep = installer.load_report(("[09:00:00 INFO]: [LuckPerms] Enabling Old v1\n" + PAPER_LOG).splitlines())
    assert "old" not in rep                                            # an older run is ignored
    assert rep["luckperms"]["state"] == "enabled"
    assert rep["essentials"]["state"] == "disabled itself"
    assert rep["tab"]["state"] == "failed" and "NoClassDefFoundError" in rep["tab"]["why"]
    assert rep["worldguard"]["state"] == "not loaded" and "WorldEdit" in rep["worldguard"]["why"]
    assert rep["broken.jar"]["state"] == "not loaded" and "InvalidDescriptionException" in rep["broken.jar"]["why"]
    vel = installer.load_report(["[10:00:00 INFO]: Booting up Velocity 3.4.0-SNAPSHOT...",
                                 "[10:00:01 INFO]: Loaded plugin luckperms 5.4.141 by Luck",
                                 "[10:00:01 ERROR]: Can't create plugin limboauth",
                                 "java.lang.IllegalStateException: no LimboAPI"])
    assert vel["luckperms"]["state"] == "enabled" and vel["limboauth"]["state"] == "failed"
    assert "IllegalStateException" in vel["limboauth"]["why"]


# ------------------------------------------------------------------ the tool, with a fake server
FAKE_SERVER = textwrap.dedent('''
    import pathlib, sys, zipfile
    print("[10:00:00 INFO]: [bootstrap] Running Java 21 (fake)", flush=True)
    for jar in sorted(pathlib.Path("plugins").glob("*.jar")):
        text = zipfile.ZipFile(jar).read("plugin.yml").decode()
        meta = dict(l.split(": ", 1) for l in text.splitlines() if ": " in l)
        name, ver = meta["name"], meta["version"].strip("'")
        if "depend" in meta:
            print(f"[10:00:01 ERROR]: Error occurred while enabling {name} v{ver} (Is it up to date?)", flush=True)
            print("java.lang.IllegalStateException: fake failure", flush=True)
        else:
            print(f"[10:00:01 INFO]: [{name}] Enabling {name} v{ver}", flush=True)
    print('[10:00:02 INFO]: Done (1.5s)! For help, type "help"', flush=True)
    for line in sys.stdin:
        if line.strip() == "stop":
            print("[10:00:09 INFO]: Stopping server", flush=True)
            sys.exit(0)
''')


def test_plugins_tool_installs_and_restarts(repo, data):
    from buildmcp import admin_tools
    from buildmcp.admin import process

    e = server(data)
    (e.path / "fake_server.py").write_text(FAKE_SERVER)
    (e.path / "eula.txt").write_text("eula=true\n")
    e.command = [sys.executable, "-u", "fake_server.py"]
    e.port = 45177
    registry.put(e, make_active=True)
    e = registry.get("lobby")
    try:
        cat = json.loads(admin_tools.plugins(action="catalog", category="protect"))
        assert {p["alias"] for p in cat["plugins"]} >= {"worldguard", "coreprotect"} and "anarchy" in cat["stacks"]
        assert process.start(e, wait=True, timeout=30)["state"] == "running"
        out = json.loads(admin_tools.plugins(action="install", names=["luckperms", "worldguard"], restart=True))
        assert out["stopped"] == "stopped" and out["start"]["state"] == "running", out
        st = out["start"]["plugins"]
        assert st["LuckPerms"] == "enabled" and st["WorldEdit"] == "enabled"
        assert st["WorldGuard"].startswith("failed") and "fake failure" in st["WorldGuard"]
        lst = json.loads(admin_tools.plugins(action="list"))
        assert lst["running"] and {p["name"]: p["last_start"] for p in lst["plugins"]}["LuckPerms"] == "enabled"
        out = json.loads(admin_tools.plugins(action="remove", names=["worldguard"]))
        assert out["result"][0]["status"] == "removed" and "restart" in out["next"]
        assert admin_tools.plugins(action="install").startswith("Error")
    finally:
        process.kill(e)
