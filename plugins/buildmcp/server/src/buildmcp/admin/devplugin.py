"""Your own plugins: a project folder with Java sources, compiled with javac against the target server's
own jars and deployed into its plugins/.

Compiling against the server itself (Paper keeps its patched jar in versions/ and every library in
libraries/, Velocity is one jar) gives exactly that server's API, with no Gradle and no internet. The
plugins installed there are on the classpath too, so a plugin can use the LuckPerms, PlaceholderAPI or
Vault API; extra jars go into the project's lib/. A build.gradle.kts is written as well, for an IDE.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from .registry import ServerEntry

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,31}$")
PKG_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
CMD_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
META = "devplugin.json"
_JAVAC_LINE = re.compile(r"^(.+?\.java):(\d+): (error|warning): (.*)$")
_JAVAC_TOTAL = re.compile(r"^\d+ (errors?|warnings?)$")


class DevError(RuntimeError):
    pass


# ------------------------------------------------------------------ projects
def projects_dir() -> Path:
    from ..render.assets import data_dir

    d = data_dir() / "devplugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index() -> Path:
    return projects_dir() / "projects.json"


def _read_index() -> dict:
    try:
        return json.loads(_index().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def project_dir(name: str) -> Path:
    """A project by name: the ones made in another folder are remembered in projects.json."""
    idx = _read_index()
    if name in idx:
        return Path(idx[name])
    return projects_dir() / name


def load_meta(name: str) -> tuple[Path, dict]:
    d = project_dir(name)
    try:
        return d, json.loads((d / META).read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise DevError(f"no devplugin project '{name}' ({d}): devplugin(action='new', name=...) makes one") from e


def list_projects() -> list[dict]:
    out = []
    names = set(_read_index())
    names |= {p.name for p in projects_dir().iterdir() if (p / META).exists()}
    for n in sorted(names):
        try:
            d, m = load_meta(n)
        except DevError:
            continue
        jars = sorted((d / "build" / "libs").glob("*.jar")) if (d / "build" / "libs").is_dir() else []
        out.append({"name": n, "platform": m.get("platform"), "version": m.get("version"), "dir": str(d),
                    "built": jars[-1].name if jars else None, "deployed_to": m.get("deployed_to", [])})
    return out


def _class_name(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    base = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return base if base.endswith("Plugin") else base + "Plugin"


def _bridge_dir() -> Path | None:
    env = os.environ.get("BUILDMCP_PLUGIN_ROOT", "").strip()
    for root in ([Path(env)] if env and not env.startswith("${") else []) + [Path(__file__).resolve().parents[4]]:
        if (root / "bridge" / "gradlew").exists():
            return root / "bridge"
    return None


def create(name: str, platform: str = "paper", package: str = "", description: str = "",
           commands: list[str] | None = None, depend: list[str] | None = None, softdepend: list[str] | None = None,
           api: str = "", dir: str = "") -> dict:
    if not NAME_RE.match(name):
        raise DevError(f"'{name}' is not a plugin name: letters, digits, - and _, 2-32 long, starting with a letter")
    platform = platform.lower()
    if platform not in ("paper", "folia", "velocity"):
        raise DevError("platform: paper | folia | velocity")
    package = package or "dev.buildmcp." + re.sub(r"[^a-z0-9]", "", name.lower())
    if not PKG_RE.match(package):
        raise DevError(f"'{package}' is not a Java package (lower case, dotted, like dev.me.hubtools)")
    cmds = [c.strip().lower().lstrip("/") for c in (commands or []) if c.strip()]
    bad = [c for c in cmds if not CMD_RE.match(c)]
    if bad:
        raise DevError(f"bad command names: {bad}")
    d = Path(dir).expanduser() / name if dir else projects_dir() / name
    if (d / META).exists() or (d.exists() and any(d.iterdir())):
        raise DevError(f"{d} already exists: pick another name or build that one")
    main = _class_name(name)
    src = d / "src" / "main" / "java" / Path(*package.split(".")) / f"{main}.java"
    res = d / "src" / "main" / "resources"
    src.parent.mkdir(parents=True)
    res.mkdir(parents=True)
    pid = re.sub(r"[^a-z0-9_-]", "", name.lower())
    meta = {"name": name, "id": pid, "platform": platform, "package": package, "main": f"{package}.{main}",
            "version": "1.0.0", "description": description, "commands": cmds, "depend": list(depend or []),
            "softdepend": list(softdepend or []), "created": time.strftime("%Y-%m-%d %H:%M"), "deployed_to": []}
    files = []
    if platform == "velocity":
        src.write_text(_velocity_main(package, main, meta), "utf-8")
    else:
        src.write_text(_paper_main(package, main, meta), "utf-8")
        (res / "plugin.yml").write_text(_plugin_yml(meta), "utf-8")
        (res / "config.yml").write_text(_config_yml(meta), "utf-8")
        files += [str(res / "plugin.yml"), str(res / "config.yml")]
    files.insert(0, str(src))
    (d / "lib").mkdir()
    (d / "lib" / "README.txt").write_text("Extra jars to compile against (APIs that are not on the server).\n", "utf-8")
    _gradle_files(d, meta, api)
    (d / ".gitignore").write_text("build/\n.gradle/\n*.iml\n.idea/\n", "utf-8")
    (d / META).write_text(json.dumps(meta, indent=1, ensure_ascii=False), "utf-8")
    if dir:
        idx = _read_index()
        idx[name] = str(d)
        _index().write_text(json.dumps(idx, indent=1), "utf-8")
    return {"project": str(d), "main": meta["main"], "files": files,
            "next": "write the code with your file tools, then devplugin(action='build' or 'deploy', name=...)"}


def _paper_main(package: str, main: str, meta: dict) -> str:
    cmd_cases = "".join(
        f'''        if (command.getName().equalsIgnoreCase("{c}")) {{
            sender.sendMessage(getConfig().getString("messages.{c}", "{meta['name']}: /{c}"));
            return true;
        }}
''' for c in meta["commands"])
    on_command = f'''
    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {{
{cmd_cases}        return false;
    }}
''' if meta["commands"] else ""
    imports = "import org.bukkit.command.Command;\nimport org.bukkit.command.CommandSender;\n" if meta["commands"] else ""
    return f'''package {package};

{imports}import org.bukkit.plugin.java.JavaPlugin;

/** {meta['description'] or meta['name']} */
public final class {main} extends JavaPlugin {{

    @Override
    public void onEnable() {{
        saveDefaultConfig();
        getLogger().info("{meta['name']} is on");
    }}

    @Override
    public void onDisable() {{
    }}
{on_command}}}
'''


def _velocity_main(package: str, main: str, meta: dict) -> str:
    return f'''package {package};

import com.google.inject.Inject;
import com.velocitypowered.api.event.Subscribe;
import com.velocitypowered.api.event.proxy.ProxyInitializeEvent;
import com.velocitypowered.api.plugin.Plugin;
import com.velocitypowered.api.proxy.ProxyServer;
import org.slf4j.Logger;

/** {meta['description'] or meta['name']} */
@Plugin(id = "{meta['id']}", name = "{meta['name']}", version = "{meta['version']}", authors = {{"BuildMCP"}})
public final class {main} {{
    private final ProxyServer proxy;
    private final Logger logger;

    @Inject
    public {main}(ProxyServer proxy, Logger logger) {{
        this.proxy = proxy;
        this.logger = logger;
    }}

    @Subscribe
    public void onProxyInitialization(ProxyInitializeEvent event) {{
        logger.info("{meta['name']} is on");
    }}
}}
'''


def _plugin_yml(meta: dict) -> str:
    lines = [f"name: {meta['name']}", "version: '${version}'", f"main: {meta['main']}", "api-version: '1.21'",
             f"description: {json.dumps(meta['description'] or meta['name'], ensure_ascii=False)}",
             "authors: [BuildMCP]"]
    if meta["platform"] == "folia":
        lines.append("folia-supported: true")
    if meta["depend"]:
        lines.append(f"depend: [{', '.join(meta['depend'])}]")
    if meta["softdepend"]:
        lines.append(f"softdepend: [{', '.join(meta['softdepend'])}]")
    if meta["commands"]:
        lines.append("commands:")
        for c in meta["commands"]:
            lines += [f"  {c}:", f"    description: /{c} of {meta['name']}", f"    usage: /{c}",
                      f"    permission: {meta['id']}.{c}"]
        lines.append("permissions:")
        for c in meta["commands"]:
            lines += [f"  {meta['id']}.{c}:", f"    description: Use /{c}", "    default: true"]
    return "\n".join(lines) + "\n"


def _config_yml(meta: dict) -> str:
    out = [f"# {meta['name']} settings", "messages:"]
    out += [f"  {c}: '{meta['name']}: /{c} works'" for c in meta["commands"]] or ["  hello: 'Hello'"]
    return "\n".join(out) + "\n"


def _gradle_files(d: Path, meta: dict, api: str) -> None:
    """build.gradle.kts and the wrapper (from BuildMCP's bridge), so the project opens in an IDE."""
    if meta["platform"] == "velocity":
        deps = ('    compileOnly("com.velocitypowered:velocity-api:$velocityApi")\n'
                '    annotationProcessor("com.velocitypowered:velocity-api:$velocityApi")\n')
        props = f"velocityApi={api or '3.4.0-SNAPSHOT'}\n"
        api_line = 'val velocityApi = providers.gradleProperty("velocityApi").get()\n'
        resources = ""
    else:
        deps = '    compileOnly("io.papermc.paper:paper-api:$paperApi")\n'
        props = f"paperApi={api or '1.21.8-R0.1-SNAPSHOT'}\n"
        api_line = 'val paperApi = providers.gradleProperty("paperApi").get()\n'
        resources = '''
tasks.processResources {
    val props = mapOf("version" to project.version)
    inputs.properties(props)
    filesMatching("plugin.yml") { expand(props) }
}
'''
    (d / "build.gradle.kts").write_text(f'''// BuildMCP builds this with javac against the server (devplugin build); Gradle is for an IDE or CI.
plugins {{
    java
}}

group = "{meta['package'].rsplit('.', 1)[0]}"
version = "{meta['version']}"
{api_line}
repositories {{
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}}

dependencies {{
{deps}    compileOnly(fileTree("lib") {{ include("*.jar") }})
}}

tasks.withType<JavaCompile>().configureEach {{
    options.encoding = "UTF-8"
    options.release.set(21)
}}
{resources}
tasks.jar {{
    archiveFileName.set("{meta['name']}-${{project.version}}.jar")
}}
''', "utf-8")
    (d / "settings.gradle.kts").write_text(f'rootProject.name = "{meta["name"]}"\n', "utf-8")
    (d / "gradle.properties").write_text(props, "utf-8")
    bridge = _bridge_dir()
    if bridge:
        for rel in ("gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar",
                    "gradle/wrapper/gradle-wrapper.properties"):
            src = bridge / rel
            if src.exists():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, d / rel)


# ------------------------------------------------------------------ the server's classpath
def _paper_jars(entry: ServerEntry) -> list[Path]:
    root = entry.path
    server_jars = sorted((root / "versions").glob("*/*.jar")) if (root / "versions").is_dir() else []
    libs = sorted((root / "libraries").rglob("*.jar")) if (root / "libraries").is_dir() else []
    return server_jars + libs


def classpath(entry: ServerEntry, skip_plugin: str = "", project: Path | None = None) -> list[Path]:
    """What a plugin for this server compiles against: the server's API and libraries, its installed
    plugins (for their APIs) and the project's lib/."""
    if entry.is_proxy:
        core = [entry.path / entry.jar] if entry.jar and (entry.path / entry.jar).exists() else []
        if not core:
            raise DevError(f"{entry.name}: the Velocity jar is missing")
    else:
        core = _paper_jars(entry)
        if not core:
            _patch_only(entry)
            core = _paper_jars(entry)
        if not core:
            raise DevError(f"{entry.name}: no versions/ and libraries/ in the server folder: start it once "
                           "(srv_power start) so Paper unpacks its jars")
    extra = []
    pdir = entry.path / "plugins"
    if pdir.is_dir():
        from . import jarinfo

        for p in sorted(pdir.glob("*.jar")):
            try:
                if skip_plugin and jarinfo.read(p).name.lower() == skip_plugin.lower():
                    continue
            except jarinfo.NotAPlugin:
                continue
            extra.append(p)
    if project is not None and (project / "lib").is_dir():
        extra += sorted((project / "lib").glob("*.jar"))
    return core + extra


def _patch_only(entry: ServerEntry) -> None:
    """Paperclip unpacks the server jar and its libraries without starting (-Dpaperclip.patchonly)."""
    if not entry.jar or not (entry.path / entry.jar).exists():
        return
    from .process import find_java, java_needed

    found = find_java(java_needed(entry))
    if not found:
        return
    try:
        subprocess.run([found[0], "-Dpaperclip.patchonly=true", "-jar", entry.jar], cwd=str(entry.path),
                       capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        pass


def find_javac(need: int = 21) -> tuple[str, int]:
    """A JDK's javac (a JRE has none): the closest version at least ``need``."""
    from .process import _java_major_cached, java_candidates

    exe = "javac.exe" if os.name == "nt" else "javac"
    best = None
    for j in java_candidates():
        javac = Path(j).parent / exe
        if not javac.exists():
            continue
        v = _java_major_cached(j)
        if v is not None and v >= need and (best is None or v < best[1]):
            best = (str(javac), v)
    if best is None:
        raise DevError(f"no JDK {need}+ with javac found: install Temurin JDK {need} (https://adoptium.net), "
                       "BuildMCP finds it by itself")
    return best


# ------------------------------------------------------------------ build
def parse_javac(out: str, root: Path) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    lines = out.splitlines()
    i = 0
    while i < len(lines):
        m = _JAVAC_LINE.match(lines[i])
        if not m:
            i += 1
            continue
        f = Path(m.group(1))
        try:
            f = f.resolve().relative_to(root.resolve())
        except ValueError:
            pass
        item: dict = {"file": f.as_posix(), "line": int(m.group(2)), "message": m.group(4).strip()}
        j = i + 1
        extra = []
        while j < len(lines) and not _JAVAC_LINE.match(lines[j]) and not _JAVAC_TOTAL.match(lines[j].strip()):
            extra.append(lines[j])
            j += 1
        if extra:
            item["code"] = extra[0].strip()
            detail = [x.strip() for x in extra[2:] if x.strip()]
            if detail:
                item["detail"] = detail[:4]
        (errors if m.group(3) == "error" else warnings).append(item)
        i = j
    return errors, warnings


def _q(p) -> str:
    return '"' + str(p).replace("\\", "/") + '"'


def build(name: str, entry: ServerEntry) -> dict:
    d, meta = load_meta(name)
    from .installer import platform_of

    plat = platform_of(entry)
    if (meta["platform"] == "velocity") != (plat == "velocity"):
        raise DevError(f"{name} is a {meta['platform']} plugin and {entry.name} is {plat}")
    sources = sorted((d / "src" / "main" / "java").rglob("*.java"))
    if not sources:
        raise DevError(f"{d}/src/main/java has no .java files")
    from .process import java_needed

    # a javac that reads the server's own class files (Java 25 for Paper 26.x and the newest Velocity);
    # the plugin itself targets Java 21 (17 on 1.20.4 and older), which every newer server runs
    runtime = java_needed(entry)
    javac, jv = find_javac(runtime)
    release = min(21, runtime) if runtime >= 17 else 17
    cp = classpath(entry, skip_plugin=meta["name"], project=d)
    out = d / "build" / "classes"
    shutil.rmtree(d / "build" / "classes", ignore_errors=True)
    out.mkdir(parents=True)
    args = ["-encoding", "UTF-8", "--release", str(release), "-proc:none", "-g", "-Xmaxerrs", "60",
            "-Xlint:all,-processing,-serial,-classfile,-options,-path", "-d", _q(out),
            "-cp", _q(os.pathsep.join(str(p) for p in cp))] + [_q(s) for s in sources]
    argfile = d / "build" / "javac.args"
    argfile.write_text("\n".join(args) + "\n", "utf-8")
    t0 = time.time()
    env = dict(os.environ)
    env.pop("JAVA_TOOL_OPTIONS", None)
    env.pop("_JAVA_OPTIONS", None)
    try:
        r = subprocess.run([javac, f"@{argfile}"], cwd=str(d), capture_output=True, text=True, timeout=600,
                           env=env, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        raise DevError("javac ran for more than 10 minutes") from e
    errors, warnings = parse_javac(r.stdout + "\n" + r.stderr, d)
    rep: dict = {"project": name, "javac": f"JDK {jv}", "release": release, "seconds": round(time.time() - t0, 1),
                 "classpath": f"{len(cp)} jars from {entry.name}"}
    if r.returncode != 0:
        rep.update(ok=False, errors=errors or [{"message": (r.stderr or r.stdout).strip()[-1500:]}])
        if warnings:
            rep["warnings"] = warnings[:10]
        return rep
    # resources, the descriptor, the jar
    res = d / "src" / "main" / "resources"
    if res.is_dir():
        for f in res.rglob("*"):
            if f.is_file():
                dest = out / f.relative_to(res)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if f.name in ("plugin.yml", "paper-plugin.yml"):
                    dest.write_text(f.read_text("utf-8").replace("${version}", meta["version"]), "utf-8")
                else:
                    shutil.copy2(f, dest)
    if meta["platform"] == "velocity" and not (out / "velocity-plugin.json").exists():
        (out / "velocity-plugin.json").write_text(json.dumps({
            "id": meta["id"], "name": meta["name"], "version": meta["version"], "main": meta["main"],
            "description": meta.get("description", ""), "authors": ["BuildMCP"],
            "dependencies": [{"id": x.lower(), "optional": False} for x in meta.get("depend", [])]
            + [{"id": x.lower(), "optional": True} for x in meta.get("softdepend", [])]}, indent=1), "utf-8")
    libs = d / "build" / "libs"
    shutil.rmtree(libs, ignore_errors=True)
    libs.mkdir(parents=True)
    jar = libs / f"{meta['name']}-{meta['version']}.jar"
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\r\nCreated-By: BuildMCP devplugin\r\n\r\n")
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out).as_posix())
    from . import jarinfo

    try:
        info = jarinfo.read(jar, plat)
    except jarinfo.NotAPlugin as e:
        rep.update(ok=False, errors=[{"message": f"the jar has no plugin descriptor: {e}"}])
        return rep
    bad = jarinfo.fits(info, plat)
    if bad:
        rep.update(ok=False, errors=[{"message": bad}])
        return rep
    rep.update(ok=True, jar=str(jar), plugin=f"{info.name} {info.version}",
               sha256=hashlib.sha256(jar.read_bytes()).hexdigest()[:16])
    if warnings:
        rep["warnings"] = warnings[:10]
    return rep


def deploy(name: str, entry: ServerEntry, before_commit=None) -> dict:
    rep = build(name, entry)
    if not rep.get("ok"):
        return {"build": rep, "deployed": False}
    from .installer import install_local

    d, meta = load_meta(name)
    inst = install_local(entry, Path(rep["jar"]), spec=f"dev:{name}", by="devplugin", before_commit=before_commit)
    if entry.name not in meta.get("deployed_to", []):
        meta.setdefault("deployed_to", []).append(entry.name)
        (d / META).write_text(json.dumps(meta, indent=1, ensure_ascii=False), "utf-8")
    return {"build": {k: v for k, v in rep.items() if k != "classpath"}, **inst}


def bump(name: str, part: str = "patch") -> str:
    """1.0.0 -> 1.0.1 (patch) / 1.1.0 (minor) / 2.0.0 (major); the Velocity @Plugin version follows."""
    d, meta = load_meta(name)
    nums = [int(x) for x in re.findall(r"\d+", meta.get("version", "1.0.0"))[:3]] + [0, 0, 0]
    ma, mi, pa = nums[:3]
    ma, mi, pa = {"major": (ma + 1, 0, 0), "minor": (ma, mi + 1, 0)}.get(part, (ma, mi, pa + 1))
    old, meta["version"] = meta["version"], f"{ma}.{mi}.{pa}"
    (d / META).write_text(json.dumps(meta, indent=1, ensure_ascii=False), "utf-8")
    if meta["platform"] == "velocity":
        for f in (d / "src" / "main" / "java").rglob("*.java"):
            t = f.read_text("utf-8")
            if f'version = "{old}"' in t:
                f.write_text(t.replace(f'version = "{old}"', f'version = "{meta["version"]}"'), "utf-8")
    gb = d / "build.gradle.kts"
    if gb.exists():
        gb.write_text(gb.read_text("utf-8").replace(f'version = "{old}"', f'version = "{meta["version"]}"'), "utf-8")
    return meta["version"]
