"""Install, update, remove, disable and list the plugins of a registered server.

Names are catalog aliases (luckperms), stacks (stack:lobby) or source specs (modrinth:slug, hangar:slug,
spigot:id, github:owner/repo#regex, jenkins:job-url#regex, url:https://...). Every jar is downloaded into
a staging folder and checked (the checksum the source publishes, the plugin descriptor, the platform,
Folia support) before it is moved into plugins/. Hard dependencies from plugin.yml are pulled in too.

What BuildMCP installed is remembered in .buildmcp/plugins.lock.json (source, version, checksum), so
update knows where each plugin comes from. Replaced and removed jars go to .buildmcp/removed/<time>/,
never deleted.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import catalog, jarinfo, net, sources
from .jarinfo import PluginInfo
from .registry import ServerEntry
from .sources import Release, SourceError


class InstallError(RuntimeError):
    pass


# ------------------------------------------------------------------ server facts
def platform_of(entry: ServerEntry) -> str:
    """paper | folia | velocity: what the server's plugins have to be built for (Purpur runs Paper ones)."""
    if entry.is_proxy:
        return "velocity"
    return "folia" if entry.software == "folia" else "paper"


def mc_of(entry: ServerEntry) -> str:
    """Minecraft version plugins are picked for; a proxy's plugins do not depend on one."""
    return "" if entry.is_proxy else entry.version


def plugins_dir(entry: ServerEntry) -> Path:
    return entry.path / "plugins"


# ------------------------------------------------------------------ installed jars
@dataclass
class Installed:
    path: Path
    info: PluginInfo
    disabled: bool = False


def scan(entry: ServerEntry) -> tuple[list[Installed], list[dict]]:
    """Plugin jars in plugins/ (also the ones renamed to .jar.disabled), and the jars that are not plugins."""
    d = plugins_dir(entry)
    found, bad = [], []
    if not d.is_dir():
        return found, bad
    for p in sorted(d.iterdir(), key=lambda p: p.name.lower()):
        if not p.is_file():
            continue
        disabled = p.name.endswith(".jar.disabled")
        if not (p.name.endswith(".jar") or disabled):
            continue
        try:
            found.append(Installed(p, jarinfo.read(p, platform_of(entry)), disabled))
        except jarinfo.NotAPlugin as e:
            bad.append({"file": p.name, "problem": str(e)})
    return found, bad


def _active_names(found: list[Installed]) -> set[str]:
    out: set[str] = set()
    for p in found:
        if not p.disabled:
            out |= p.info.names
    return out


def _match(found: list[Installed], name: str) -> Installed | None:
    """The installed plugin a name means: plugin.yml name or id, a catalog alias, or the file name."""
    key = name.strip().lower()
    cat = catalog.find(key)
    want = catalog.names(cat) if cat else {key}
    for p in found:
        stem = p.path.name.lower().removesuffix(".disabled").removesuffix(".jar")
        if p.info.own_names & want or stem == key:
            return p
    return None


def _catalog_of(info: PluginInfo) -> dict | None:
    return next((c for c in catalog.CATALOG.values() if catalog.names(c) & info.own_names), None)


# ------------------------------------------------------------------ lock file
def _lock_file(entry: ServerEntry) -> Path:
    return entry.state_dir() / "plugins.lock.json"


def load_lock(entry: ServerEntry) -> dict:
    try:
        data = json.loads(_lock_file(entry).read_text("utf-8"))
        return data.get("plugins", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_lock(entry: ServerEntry, lock: dict) -> None:
    _lock_file(entry).write_text(json.dumps({"plugins": lock}, indent=1, ensure_ascii=False, sort_keys=True),
                                 "utf-8")


def _backup_dir(entry: ServerEntry) -> Path:
    base = entry.state_dir() / "removed" / time.strftime("%Y%m%d-%H%M%S")
    d, i = base, 1
    while d.exists():
        i += 1
        d = base.with_name(f"{base.name}-{i}")
    return d


# ------------------------------------------------------------------ what to install
@dataclass
class Item:
    want: str                              # what was asked for: alias, spec, dependency name
    specs: list[str]                       # sources to try, in order
    alias: str = ""                        # catalog alias, if it is a catalog plugin
    by: str = "requested"                  # requested | stack X | dependency of X | update
    update: bool = False                   # replace the installed version if the source has another one
    current: Installed | None = None       # the installed jar this one replaces
    release: Release | None = None
    staged: Path | None = None
    info: PluginInfo | None = None
    sha256: str = ""
    status: str = "planned"
    detail: str = ""
    tried: list[str] = field(default_factory=list)
    file: str = ""

    @property
    def key(self) -> str:
        if self.alias:
            return self.alias
        return self.specs[0].lower() if self.specs else self.want.lower()

    def names(self) -> set[str]:
        if self.info:
            return self.info.names
        cat = catalog.CATALOG.get(self.alias)
        return catalog.names(cat) | set(catalog.PROVIDES.get(self.alias, [])) if cat else set()

    def row(self) -> dict:
        r = {"want": self.want, "status": self.status}
        if self.info:
            r.update(name=self.info.name, version=self.info.version)
        elif self.release:
            r.update(name=self.release.name, version=self.release.version)
        if self.file:
            r["file"] = self.file
        if self.release:
            r["source"] = f"{self.release.source}:{self.release.project}"
            if self.release.note:
                r["note"] = self.release.note
        if self.current and self.status in ("updated", "planned") and self.current.info.version:
            r["from"] = self.current.info.version
        if self.by != "requested":
            r["by"] = self.by
        if self.status == "planned" and self.release and self.release.dependencies:
            r["source_deps"] = [d["spec"] for d in self.release.dependencies if d.get("required")]
        if self.detail:
            r["detail"] = self.detail
        if self.tried:
            r["tried" if self.status in ("failed", "skipped") else "fell_back_after"] = self.tried
        return r


def expand(names: list[str], platform: str) -> tuple[list[Item], list[dict]]:
    """Turn names (aliases, stack:X, specs) into items; unknown names come back as errors."""
    items, errors = [], []
    for raw in names:
        n = raw.strip()
        if not n:
            continue
        low = n.lower()
        stack = low[6:] if low.startswith("stack:") else (low if low in catalog.STACKS and not catalog.find(low)
                                                          else "")
        if stack:
            st = catalog.STACKS.get(stack)
            if not st:
                errors.append({"want": n, "status": "failed",
                               "detail": f"no stack '{stack}' (have: {', '.join(catalog.STACKS)})"})
                continue
            items += [_catalog_item(a, f"stack {stack}") for a in st["plugins"]]
            continue
        cat = catalog.find(n)
        if cat:
            items.append(_catalog_item(cat["alias"], "requested"))
            continue
        try:
            kind, _, _ = sources.parse_spec(n)
        except SourceError as e:
            errors.append({"want": n, "status": "failed", "detail": f"{e}. Not in the catalog either: "
                           "plugins(action='search', query=...) finds the spec"})
            continue
        items.append(Item(n, [n if kind != "url" or low.startswith("url:") else f"url:{n}"]))
    return items, errors


def _catalog_item(alias: str, by: str) -> Item:
    e = catalog.CATALOG[alias]
    return Item(alias, list(e["sources"]), alias=alias, by=by)


# ------------------------------------------------------------------ resolve, download, check
def _resolve(it: Item, platform: str, mc: str) -> None:
    last = None
    for spec in it.specs:
        try:
            it.release = sources.resolve(spec, platform, mc)
            return
        except (SourceError, net.NetError, ValueError, KeyError) as e:
            last = e
            it.tried.append(f"{spec}: {str(e)[:160]}")
    raise SourceError(f"no source had a build for {platform} {mc}".strip() + (f" (last: {last})" if last else ""))


def _safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._+-]", "_", name.split("/")[-1].split("\\")[-1]).strip("._") or "plugin.jar"
    return name if name.endswith(".jar") else name + ".jar"


def _stage(it: Item, entry: ServerEntry, platform: str, staging: Path) -> None:
    """Download the release (trying the next source when one fails) and check the jar."""
    specs = list(it.specs)
    while True:
        r = it.release
        assert r is not None
        dest = staging / f"{len(list(staging.iterdir())):02d}-{_safe_name(r.filename)}"
        try:
            got = net.download(r.url, dest, sha256=r.hashes.get("sha256"), sha512=r.hashes.get("sha512"),
                               sha1=r.hashes.get("sha1"))
            info = jarinfo.read(dest, platform)
            bad = jarinfo.fits(info, platform)
            if bad:
                raise InstallError(bad)
            it.staged, it.info, it.sha256 = dest, info, got["sha256"]
            return
        except (net.NetError, jarinfo.NotAPlugin, InstallError) as e:
            dest.unlink(missing_ok=True)
            it.tried.append(f"{r.source}:{r.project}: {str(e)[:200]}")
            # the next source of the item, if any
            used = next((i for i, s in enumerate(specs) if _spec_is(s, r)), None)
            rest = specs[used + 1:] if used is not None else []
            it.release = None
            for spec in rest:
                try:
                    it.release = sources.resolve(spec, platform, mc_of(entry))
                    specs = rest[rest.index(spec):]
                    break
                except (SourceError, net.NetError, ValueError, KeyError) as e2:
                    it.tried.append(f"{spec}: {str(e2)[:160]}")
            if it.release is None:
                raise InstallError(str(e)) from e


def _spec_is(spec: str, r: Release) -> bool:
    try:
        kind, project, _ = sources.parse_spec(spec)
    except SourceError:
        return False
    return kind == r.source and (project == r.project or project.lower() == r.project.lower()
                                 or project.split("/")[-1].lower() == r.project.lower())


# ------------------------------------------------------------------ install / update
def install(entry: ServerEntry, names: list[str], deps: bool = True, dry_run: bool = False, force: bool = False,
            before_commit: Callable[[], None] | None = None) -> dict:
    """Install plugins by alias, stack or spec. force=True reinstalls ones that are already there."""
    platform = platform_of(entry)
    items, errors = expand(names, platform)
    if force:
        for it in items:
            it.update = True
    return _run(entry, items, errors, deps=deps, dry_run=dry_run, before_commit=before_commit)


def update(entry: ServerEntry, names: list[str] | None = None, dry_run: bool = False,
           before_commit: Callable[[], None] | None = None) -> dict:
    """Newer builds for the named plugins (default: every plugin whose source BuildMCP knows)."""
    found, _ = scan(entry)
    lock = load_lock(entry)
    items, errors = [], []
    targets = []
    if names:
        for n in names:
            p = _match(found, n)
            if p is None:
                errors.append({"want": n, "status": "failed", "detail": "not installed"})
            else:
                targets.append(p)
    else:
        targets = [p for p in found if not p.disabled]
    for p in targets:
        entry_lock = lock.get(p.info.name) or {}
        cat = _catalog_of(p.info)
        if entry_lock.get("spec"):
            specs = [entry_lock["spec"]] + [s for s in (cat["sources"] if cat else []) if s != entry_lock["spec"]]
        elif cat:
            specs = list(cat["sources"])
        else:
            why = ("BuildMCP's own bridge: bridge_install updates it" if p.info.name == "BuildBridge"
                   else "source unknown (installed by hand): install it by spec once to track it")
            errors.append({"want": p.info.name, "status": "skipped", "detail": why})
            continue
        it = Item(p.info.name, specs, alias=cat["alias"] if cat else "", by="update", update=True, current=p)
        items.append(it)
    return _run(entry, items, errors, deps=True, dry_run=dry_run, before_commit=before_commit, updating=True)


def _run(entry: ServerEntry, queue: list[Item], errors: list[dict], deps: bool, dry_run: bool,
         before_commit: Callable[[], None] | None, updating: bool = False) -> dict:
    platform, mc = platform_of(entry), mc_of(entry)
    found, _ = scan(entry)
    have = _active_names(found)
    lock = load_lock(entry)
    staging = entry.state_dir() / "staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    done: list[Item] = []
    seen: set[str] = set()

    def planned(name: str) -> bool:
        n = name.lower()
        return any(n in x.names() for x in done + queue if x.status in ("planned", "staged"))

    try:
        while queue:
            it = queue.pop(0)
            if it.key in seen:
                continue
            seen.add(it.key)
            done.append(it)
            cat = catalog.CATALOG.get(it.alias)
            if cat and platform not in cat["platforms"]:
                if cat["builtin"].get(platform):
                    it.status, it.detail = "present", cat["builtin"][platform]
                else:
                    it.status = "skipped"
                    it.detail = f"{cat['name']} runs on {', '.join(cat['platforms'])}, this server is {platform}"
                continue
            cur = it.current or (_match(found, it.alias) if it.alias else None)
            if cur and cur.disabled:
                it.status, it.detail = "skipped", f"installed but disabled ({cur.path.name}): action='enable'"
                continue
            if cur and not it.update:
                it.status, it.current = "present", cur
                it.detail = f"already installed: {cur.info.name} {cur.info.version} ({cur.path.name})"
                continue
            if cat and not cur and not it.update:
                prov = next((p for p in found if not p.disabled and catalog.names(cat) & p.info.names), None)
                if prov:
                    it.status, it.detail = "present", f"provided by {prov.info.name} {prov.info.version}"
                    continue
            it.current = cur
            if deps and cat:
                for req in cat["requires"]:
                    alts = req.split("|")
                    if not any(a in have or catalog.names(catalog.CATALOG[a]) & have or planned(a) for a in alts):
                        queue.append(_catalog_item(alts[0], f"needed by {cat['name']}"))
            try:
                _resolve(it, platform, mc)
            except SourceError as e:
                it.status, it.detail = "failed", str(e)
                continue
            if it.update and cur and _same_release(lock.get(cur.info.name), it.release):
                it.status, it.detail = "up to date", f"{cur.info.name} {cur.info.version}"
                continue
            if dry_run:
                continue
            try:
                _stage(it, entry, platform, staging)
            except InstallError as e:
                it.status, it.detail = "failed", str(e)
                continue
            assert it.info is not None
            other = next((x for x in done if x is not it and x.status == "staged" and x.names() & it.info.names), None)
            if other:
                it.status, it.detail = "skipped", f"same plugin as {other.want}"
                continue
            if not it.current:
                it.current = next((p for p in found if p.info.names & it.info.names), None)
            if it.current and it.current.disabled:
                it.status, it.detail = "skipped", f"installed but disabled ({it.current.path.name}): action='enable'"
                continue
            if it.current and not it.update:
                it.status = "present"
                it.detail = (f"already installed: {it.current.info.name} {it.current.info.version} "
                             "(force=True or action='update' replaces it)")
                continue
            if it.by == "update" and it.current and it.current.info.version == it.info.version:
                it.status, it.detail = "up to date", f"{it.info.name} {it.info.version}"
                continue
            it.status = "staged"
            if deps:
                for dep in it.info.depend:
                    if dep.lower() in have or planned(dep):
                        continue
                    dcat = catalog.find(dep)
                    if dcat:
                        queue.append(_catalog_item(dcat["alias"], f"dependency of {it.info.name}"))
                        continue
                    extra = [d["spec"] for d in (it.release.dependencies if it.release else []) if d.get("required")
                             and d["spec"].lower() not in seen]
                    if extra:
                        queue += [Item(s, [s], by=f"dependency of {it.info.name}") for s in extra]
                    # else: reported as missing below
        # a plugin whose hard dependency is not there would not load: keep it out
        ok = [x for x in done if x.status == "staged"]
        changed = True
        while changed:
            changed = False
            avail = have | set().union(*(x.info.names for x in ok if x.info)) if ok else set(have)
            for x in list(ok):
                miss = [d for d in x.info.depend if d.lower() not in avail] if x.info else []
                if miss and deps:
                    x.status = "skipped"
                    x.detail = (f"needs {', '.join(miss)}: not in the catalog and the source names no build; "
                                "find it with action='search' and install it first")
                    failed_dep = [d for d in done if d.status == "failed" and d.names() & {m.lower() for m in miss}]
                    if failed_dep:
                        x.detail = f"needs {', '.join(miss)}, which failed to install"
                    ok.remove(x)
                    changed = True
                elif miss:
                    x.detail = f"needs {', '.join(miss)} (not installed: deps=False)"
        if dry_run:
            rows = [x.row() for x in done]
            return {"server": entry.name, "platform": f"{platform} {mc}".strip(), "dry_run": True,
                    "plan": rows + errors,
                    "note": "dependencies declared in plugin.yml are only known after the download"}
        if ok and before_commit:
            before_commit()
        backup = _backup_dir(entry)
        pdir = plugins_dir(entry)
        pdir.mkdir(parents=True, exist_ok=True)
        for x in ok:
            try:
                x.file, note = _put(x, pdir, backup, platform)
            except InstallError as e:
                x.status, x.detail = "failed", str(e)
                continue
            x.status = "updated" if x.current else "installed"
            if note:
                x.detail = (x.detail + "; " if x.detail else "") + note
            assert x.info is not None and x.release is not None
            if x.current and x.current.info.name != x.info.name:
                lock.pop(x.current.info.name, None)
            lock[x.info.name] = {"alias": x.alias, "spec": _spec_of(x), "version": x.info.version, "file": x.file,
                                 "sha256": x.sha256, "url": x.release.url, "page": x.release.page,
                                 "source_version": x.release.version, "by": x.by,
                                 "at": time.strftime("%Y-%m-%d %H:%M")}
        save_lock(entry, lock)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    rows = [x.row() for x in done] + errors
    changed_any = any(x.status in ("installed", "updated") for x in done)
    out = {"server": entry.name, "platform": f"{platform} {mc}".strip(), "result": rows, "changed": changed_any}
    if backup.exists():
        out["backup"] = str(backup)
    if updating and not rows:
        out["result"] = "nothing to update"
    return out


def _same_release(locked: dict | None, r: Release | None) -> bool:
    """The lock remembers the URL (and version) of what was installed: the same one means up to date."""
    return bool(locked and r and locked.get("url") == r.url and locked.get("source_version", "") == r.version)


def _spec_of(it: Item) -> str:
    r = it.release
    assert r is not None
    return next((s for s in it.specs if _spec_is(s, r)), f"{r.source}:{r.project}")


def _put(it: Item, pdir: Path, backup: Path, platform: str) -> tuple[str, str]:
    """Move the staged jar into plugins/, the replaced one into the backup. Returns (file name, note)."""
    assert it.staged is not None and it.release is not None and it.info is not None
    cur = it.current
    if cur is not None:
        try:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(cur.path), str(backup / cur.path.name))
        except PermissionError as e:
            if platform == "velocity":
                raise InstallError(f"the running proxy holds {cur.path.name}: stop it first "
                                   "(or pass restart=True)") from e
            upd = pdir / "update"
            upd.mkdir(exist_ok=True)
            shutil.move(str(it.staged), str(upd / cur.path.name))
            return cur.path.name, ("the running server holds the old jar: the new one waits in plugins/update "
                                   "and replaces it at the next start")
    target = pdir / _safe_name(it.release.filename)
    if target.exists():
        v = re.sub(r"[^A-Za-z0-9._+-]", "_", it.info.version) or str(int(time.time()))
        target = pdir / f"{target.stem}-{v}.jar"
    shutil.move(str(it.staged), str(target))
    return target.name, ""


# ------------------------------------------------------------------ remove / disable / enable
def remove(entry: ServerEntry, names: list[str], keep_data: bool = True) -> dict:
    """Move plugin jars (and with keep_data=False their data folders) to .buildmcp/removed/<time>/."""
    found, _ = scan(entry)
    lock = load_lock(entry)
    backup = _backup_dir(entry)
    rows = []
    for n in names:
        p = _match(found, n)
        if p is None:
            rows.append({"want": n, "status": "failed", "detail": "not installed"})
            continue
        users = [q.info.name for q in found if q is not p and not q.disabled
                 and {d.lower() for d in q.info.depend} & p.info.names]
        backup.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(p.path), str(backup / p.path.name))
        except PermissionError:
            rows.append({"want": n, "status": "failed",
                         "detail": f"the running server holds {p.path.name}: stop it first (or restart=True)"})
            continue
        row = {"want": n, "status": "removed", "name": p.info.name, "file": p.path.name}
        data = plugins_dir(entry) / p.info.name
        if not keep_data and data.is_dir():
            shutil.move(str(data), str(backup / data.name))
            row["data"] = "moved to the backup"
        elif data.is_dir():
            row["data"] = f"kept in plugins/{data.name}"
        if users:
            row["warning"] = f"{', '.join(users)} depend on it and will not load"
        lock.pop(p.info.name, None)
        found.remove(p)
        rows.append(row)
    save_lock(entry, lock)
    out = {"server": entry.name, "result": rows, "changed": any(r["status"] == "removed" for r in rows)}
    if backup.exists():
        out["backup"] = str(backup)
    return out


def set_enabled(entry: ServerEntry, names: list[str], enabled: bool) -> dict:
    """disable: X.jar -> X.jar.disabled (the server skips it); enable: back."""
    found, _ = scan(entry)
    lock = load_lock(entry)
    rows = []
    for n in names:
        p = _match(found, n)
        if p is None:
            rows.append({"want": n, "status": "failed", "detail": "not installed"})
            continue
        if p.disabled == (not enabled):
            rows.append({"want": n, "status": "unchanged", "name": p.info.name, "file": p.path.name})
            continue
        new = p.path.with_name(p.path.name.removesuffix(".disabled") if enabled else p.path.name + ".disabled")
        try:
            p.path.rename(new)
        except PermissionError:
            rows.append({"want": n, "status": "failed",
                         "detail": f"the running server holds {p.path.name}: stop it first (or restart=True)"})
            continue
        if p.info.name in lock:
            lock[p.info.name]["file"] = new.name
        rows.append({"want": n, "status": "enabled" if enabled else "disabled", "name": p.info.name,
                     "file": new.name})
    save_lock(entry, lock)
    return {"server": entry.name, "result": rows,
            "changed": any(r["status"] in ("enabled", "disabled") for r in rows)}


# ------------------------------------------------------------------ what the log says
# the first line of a run: the runner's own note, Paper's bootstrap line, Velocity's banner
_START_RE = re.compile(r"\[BuildMCP [\d:]+\] starting: |\[bootstrap\] Running Java|Booting up Velocity")
_STOP_RE = re.compile(r"Stopping (?:the )?server\b|Shutting down the proxy|Closing endpoint")
_ENABLING_RE = re.compile(r"\bEnabling (\S+) v?\S*")
_VLOADED_RE = re.compile(r"\bLoaded plugin (\S+) \S+")
_ENABLE_ERR_RE = re.compile(r"Error occurred while enabling (\S+)")
_NOT_LOADED_RE = re.compile(r"Could not load (?:plugin )?'([^']+)'")
_MISSING_RE = re.compile(r"missing dependency plugins: \[([^\]]*)\]\. Please download and install these plugins "
                         r"to run '([^']+)'", re.I)
_VFAIL_RE = re.compile(r"(?:Can't create plugin|Unable to load plugin|Couldn't pass \w+ to) (\S+)")
_DISABLING_RE = re.compile(r"\bDisabling (\S+) v?\S*")
_CAUSE_RE = re.compile(r"^\s*(?:Caused by: )?([\w.$]+(?:Exception|Error)\b.*)")


def load_report(lines: list[str]) -> dict[str, dict]:
    """How each plugin fared at the last start: {lower name or jar: {"name", "state", "why"}}.
    state: enabled | failed | not loaded | disabled itself."""
    start = max((i for i, l in enumerate(lines) if _START_RE.search(l)), default=0)
    out: dict[str, dict] = {}
    stopping = False
    run = lines[start:]
    for i, l in enumerate(run):
        if _STOP_RE.search(l):
            stopping = True
        m = _MISSING_RE.search(l)
        if m:
            out[m.group(2).lower()] = {"name": m.group(2), "state": "not loaded",
                                       "why": f"missing dependency: {m.group(1)}"}
            continue
        m = _ENABLE_ERR_RE.search(l)
        if m:
            out[m.group(1).lower()] = {"name": m.group(1), "state": "failed", "why": _cause(run, i) or l.strip()[-200:]}
            continue
        m = _NOT_LOADED_RE.search(l)
        if m:
            jar = m.group(1).replace("\\", "/").split("/")[-1]
            cause = _cause(run, i)
            if jar.lower() not in out:
                out[jar.lower()] = {"name": jar, "state": "not loaded", "why": cause or l.strip()[-200:]}
            continue
        m = _VFAIL_RE.search(l)
        if m:
            out[m.group(1).lower()] = {"name": m.group(1), "state": "failed", "why": _cause(run, i) or l.strip()[-200:]}
            continue
        m = _ENABLING_RE.search(l) or _VLOADED_RE.search(l)
        if m and not stopping:
            out.setdefault(m.group(1).lower(), {"name": m.group(1), "state": "enabled"})
            continue
        m = _DISABLING_RE.search(l)
        if m and not stopping and out.get(m.group(1).lower(), {}).get("state") == "enabled":
            out[m.group(1).lower()] = {"name": m.group(1), "state": "disabled itself",
                                       "why": "the plugin turned itself off during start: read the lines above it"}
    return out


def _cause(lines: list[str], i: int) -> str:
    for l in lines[i + 1:i + 25]:
        m = _CAUSE_RE.match(l)
        if m:
            return m.group(1).strip()[:240]
    return ""


def _state_for(report: dict[str, dict], p: Installed) -> dict | None:
    for n in p.info.names:
        if n in report:
            return report[n]
    return report.get(p.path.name.lower())


# ------------------------------------------------------------------ listing, search, info
def listing(entry: ServerEntry, log: list[str] | None = None) -> dict:
    found, bad = scan(entry)
    lock = load_lock(entry)
    report = load_report(log) if log else {}
    have = _active_names(found)
    rows = []
    for p in found:
        row = {"name": p.info.name, "version": p.info.version, "file": p.path.name}
        if p.disabled:
            row["disabled"] = True
        L = lock.get(p.info.name)
        cat = _catalog_of(p.info)
        row["source"] = L["spec"] if L else (f"catalog:{cat['alias']}" if cat else "by hand")
        st = _state_for(report, p) if report and not p.disabled else None
        if st:
            row["last_start"] = st["state"] + (f": {st['why']}" if st.get("why") else "")
        elif report and not p.disabled:
            row["last_start"] = "not seen in the log"
        miss = [d for d in p.info.depend if d.lower() not in have]
        if miss and not p.disabled:
            row["missing"] = miss
        rows.append(row)
    out = {"server": entry.name, "platform": f"{platform_of(entry)} {mc_of(entry)}".strip(), "plugins": rows}
    if bad:
        out["not_plugins"] = bad
    extra = [v for k, v in report.items() if v["state"] != "enabled"
             and not any(k in p.info.names or k == p.path.name.lower() for p in found)]
    if extra:
        out["log_problems"] = extra
    return out


def search(query: str, platform: str = "paper", mc: str = "", limit: int = 8) -> dict:
    words = [w for w in query.lower().split() if w]
    cat = [dict(alias=e["alias"], name=e["name"], about=e["about"], platforms=e["platforms"])
           for e in catalog.CATALOG.values()
           if words and all(w in f"{e['alias']} {e['name']} {e['about']} {e['category']}".lower() for w in words)]
    out: dict = {"catalog": cat}
    errors = {}
    finders = {"modrinth": lambda: sources.modrinth_search(query, platform, mc, limit),
               "hangar": lambda: sources.hangar_search(query, platform, limit),
               "spigot": lambda: sources.spigot_search(query, limit)}
    for name, fn in finders.items():
        try:
            out[name] = fn()
        except (net.NetError, SourceError, ValueError, KeyError) as e:
            errors[name] = str(e)[:200]
    if errors:
        out["unreachable"] = errors
    out["how"] = "install with plugins(action='install', names=['<alias or spec>'])"
    return out


def info(names: list[str], platform: str, mc: str) -> list[dict]:
    out = []
    items, errors = expand(names, platform)
    for it in items:
        row: dict = {"want": it.want}
        cat = catalog.CATALOG.get(it.alias)
        if cat:
            row.update(name=cat["name"], about=cat["about"], platforms=cat["platforms"], requires=cat["requires"],
                       sources=cat["sources"])
            if platform not in cat["platforms"]:
                row["warning"] = f"not for {platform}"
        try:
            _resolve(it, platform, mc)
            assert it.release is not None
            row["release"] = it.release.to_dict()
        except SourceError as e:
            row["error"] = str(e)
        if it.tried:
            row["tried"] = it.tried
        out.append(row)
    return out + errors
