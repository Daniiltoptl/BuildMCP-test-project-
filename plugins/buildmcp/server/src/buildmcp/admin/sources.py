"""Where plugins come from: Modrinth, Hangar (PaperMC), Spiget (SpigotMC), GitHub Releases, Jenkins and
plain URLs. Each source turns a project into a Release that fits a platform and a Minecraft version.

A spec is ``source:project`` — modrinth:luckperms, hangar:ViaVersion, spigot:6245,
github:MilkBowl/Vault#^Vault\\.jar$, jenkins:https://ci.example.org/job/X#^X-.*\\.jar$, url:https://...jar
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from . import net

MODRINTH = "https://api.modrinth.com/v2"
HANGAR = "https://hangar.papermc.io/api/v1"
SPIGET = "https://api.spiget.org/v2"
GITHUB = "https://api.github.com"

MODRINTH_LOADERS = {"paper": ["paper", "purpur", "spigot", "bukkit"], "folia": ["folia"], "velocity": ["velocity"]}
HANGAR_PLATFORM = {"paper": "PAPER", "folia": "PAPER", "velocity": "VELOCITY"}


@dataclass
class Release:
    source: str
    project: str
    name: str
    version: str
    filename: str
    url: str
    hashes: dict = field(default_factory=dict)
    mc_versions: list[str] = field(default_factory=list)
    channel: str = "release"
    dependencies: list[dict] = field(default_factory=list)  # [{"spec": "modrinth:<id>", "required": bool, "name"}]
    page: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mc_versions"] = _summarize_versions(self.mc_versions)
        return d


class SourceError(RuntimeError):
    pass


def parse_spec(spec: str) -> tuple[str, str, str]:
    """'github:owner/repo#regex' -> ('github', 'owner/repo', 'regex')."""
    spec = spec.strip()
    if spec.startswith(("http://", "https://")):
        return "url", spec, ""
    if ":" not in spec:
        raise SourceError(f"'{spec}' is not a source spec (modrinth:slug, hangar:slug, spigot:id, github:owner/repo, "
                          "jenkins:job-url, url:https://...)")
    kind, rest = spec.split(":", 1)
    kind = kind.lower()
    pattern = ""
    if kind in ("github", "jenkins") and "#" in rest:
        rest, pattern = rest.split("#", 1)
    return kind, rest, pattern


# ------------------------------------------------------------------ versions
def _mc_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _same_line(a: str, b: str) -> bool:
    ka, kb = _mc_key(a), _mc_key(b)
    return len(ka) >= 2 and len(kb) >= 2 and ka[:2] == kb[:2]


def _summarize_versions(vs: list[str]) -> str:
    if not vs:
        return ""
    s = sorted(set(vs), key=_mc_key)
    return s[0] if len(s) == 1 else f"{s[0]}..{s[-1]}"


def pick(releases: list[Release], mc: str) -> Release | None:
    """Best release for Minecraft ``mc``: the newest stable one that lists mc, else the newest that lists
    the same line (1.21.x), else the newest stable one (with a note)."""
    if not releases:
        return None
    stable = [r for r in releases if r.channel in ("release", "stable", "")] or releases
    if not mc:
        return stable[0]
    exact = [r for r in stable if mc in r.mc_versions]
    if exact:
        return exact[0]
    line = [r for r in stable if any(_same_line(v, mc) for v in r.mc_versions)]
    if line:
        r = line[0]
        top = max((v for v in r.mc_versions if _same_line(v, mc)), key=_mc_key)
        r.note = f"lists Minecraft up to {top}, not {mc} (plugins usually keep working within a line)"
        return r
    r = stable[0]
    r.note = (f"lists Minecraft {_summarize_versions(r.mc_versions)}, not {mc}: check the log after the start"
              if r.mc_versions else "")
    return r


# ------------------------------------------------------------------ modrinth
_PLATFORM_WORDS = {"velocity": ("velocity",), "folia": ("folia", "paper", "bukkit", "spigot"),
                   "paper": ("paper", "bukkit", "spigot", "purpur")}


def _modrinth_file(files: list[dict], platform: str) -> dict | None:
    """The jar of a Modrinth version for the platform: a version may carry one jar per platform
    (Geyser-Spigot.jar and Geyser-Velocity.jar), else the primary file."""
    jars = [f for f in files if str(f.get("filename", "")).endswith(".jar")
            and not any(w in f["filename"].lower() for w in ("-sources", "-javadoc", "-api."))]
    if len(jars) <= 1:
        return jars[0] if jars else None
    for word in _PLATFORM_WORDS.get(platform, ()):
        hit = [f for f in jars if word in f["filename"].lower()]
        if hit:
            return next((f for f in hit if f.get("primary")), hit[0])
    return next((f for f in jars if f.get("primary")), jars[0])


def modrinth_releases(project: str, platform: str, mc: str = "") -> list[Release]:
    info = net.get_json(f"{MODRINTH}/project/{project}", ok404=True)
    if info is None:
        raise SourceError(f"modrinth: no project '{project}'")
    params = {"loaders": json.dumps(MODRINTH_LOADERS.get(platform, ["paper"])), "include_changelog": "false"}
    vers = net.get_json(f"{MODRINTH}/project/{project}/version", params=params) or []
    out = []
    for v in vers:
        f = _modrinth_file(v.get("files") or [], platform)
        if not f:
            continue
        deps = [{"spec": f"modrinth:{d['project_id']}", "required": d.get("dependency_type") == "required"}
                for d in (v.get("dependencies") or []) if d.get("project_id")
                and d.get("dependency_type") in ("required", "optional")]
        out.append(Release("modrinth", info.get("slug") or project, info.get("title") or project,
                           str(v.get("version_number", "")), f["filename"], f["url"], dict(f.get("hashes") or {}),
                           list(v.get("game_versions") or []), str(v.get("version_type", "release")), deps,
                           f"https://modrinth.com/plugin/{info.get('slug') or project}"))
    return out


def modrinth_search(query: str, platform: str, mc: str = "", limit: int = 10) -> list[dict]:
    facets = [["project_type:plugin"], [f"categories:{l}" for l in MODRINTH_LOADERS.get(platform, ["paper"])]]
    if mc:
        facets.append([f"versions:{mc}"])
    data = net.get_json(f"{MODRINTH}/search", params={"query": query, "facets": json.dumps(facets),
                                                      "limit": str(limit), "index": "relevance"})
    return [{"spec": f"modrinth:{h['slug']}", "name": h.get("title"), "about": h.get("description", "")[:160],
             "downloads": h.get("downloads", 0), "updated": str(h.get("date_modified", ""))[:10]}
            for h in (data or {}).get("hits", [])]


# ------------------------------------------------------------------ hangar
def _hangar_range_has(spec: str, mc: str) -> bool:
    """Hangar lists versions and ranges like "1.8-1.21.4"."""
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            if _mc_key(lo) <= _mc_key(mc) <= _mc_key(hi):
                return True
        elif part == mc:
            return True
    return False


def hangar_releases(project: str, platform: str, mc: str = "") -> list[Release]:
    slug = project.split("/")[-1]
    info = net.get_json(f"{HANGAR}/projects/{slug}", ok404=True)
    if info is None:
        raise SourceError(f"hangar: no project '{project}'")
    plat = HANGAR_PLATFORM.get(platform, "PAPER")
    data = net.get_json(f"{HANGAR}/projects/{slug}/versions", params={"limit": "25", "offset": "0", "platform": plat})
    out = []
    for v in (data or {}).get("result", []):
        dl = (v.get("downloads") or {}).get(plat)
        if not dl:
            continue
        fi = dl.get("fileInfo") or {}
        url = dl.get("downloadUrl") or dl.get("externalUrl")
        if not url:
            continue
        ranges = (v.get("platformDependencies") or {}).get(plat) or []
        mcs = []
        for r in ranges:
            if mc and _hangar_range_has(r, mc):
                mcs.append(mc)
            mcs.extend(x for x in re.split(r"[-,]", r) if x.strip())
        deps = [{"spec": f"hangar:{d['name']}", "required": bool(d.get("required")), "name": d.get("name")}
                for d in ((v.get("pluginDependencies") or {}).get(plat) or []) if d.get("name")]
        ch = str((v.get("channel") or {}).get("name", "Release")).lower()
        owner = (info.get("namespace") or {}).get("owner", "")
        out.append(Release("hangar", slug, info.get("name") or slug, str(v.get("name", "")),
                           fi.get("name") or f"{slug}-{v.get('name')}.jar", url,
                           {"sha256": fi["sha256Hash"]} if fi.get("sha256Hash") else {}, mcs,
                           "release" if ch in ("release", "stable") else ch, deps,
                           f"https://hangar.papermc.io/{owner}/{slug}" if owner else f"https://hangar.papermc.io/{slug}"))
    return out


def hangar_search(query: str, platform: str, limit: int = 10) -> list[dict]:
    data = net.get_json(f"{HANGAR}/projects", params={"q": query, "query": query, "limit": str(limit),
                                                      "offset": "0", "platform": HANGAR_PLATFORM.get(platform, "PAPER")})
    out = []
    for p in (data or {}).get("result", []):
        slug = (p.get("namespace") or {}).get("slug") or p.get("name")
        out.append({"spec": f"hangar:{slug}", "name": p.get("name"), "about": str(p.get("description", ""))[:160],
                    "downloads": (p.get("stats") or {}).get("downloads", 0)})
    return out


# ------------------------------------------------------------------ spigot (spiget)
def spigot_releases(project: str, platform: str, mc: str = "") -> list[Release]:
    rid = project.strip()
    info = net.get_json(f"{SPIGET}/resources/{rid}", ok404=True)
    if info is None:
        raise SourceError(f"spigot: no resource {rid}")
    if info.get("premium"):
        raise SourceError(f"spigot {rid} ({info.get('name')}) is premium: it has to be bought and downloaded by hand")
    f = info.get("file") or {}
    if f.get("type") == "external" or info.get("external"):
        raise SourceError(f"spigot {rid} ({info.get('name')}) is hosted elsewhere ({f.get('externalUrl')}); "
                          "use another source")
    ver = net.get_json(f"{SPIGET}/resources/{rid}/versions/latest", ok404=True) or {}
    name = info.get("name") or rid
    return [Release("spigot", rid, name, str(ver.get("name", "")), f"{re.sub(r'[^A-Za-z0-9._-]', '', name)}.jar",
                    f"{SPIGET}/resources/{rid}/download", {}, list(info.get("testedVersions") or []), "release", [],
                    f"https://www.spigotmc.org/resources/{rid}/")]


def spigot_search(query: str, limit: int = 10) -> list[dict]:
    data = net.get_json(f"{SPIGET}/search/resources/{query}", params={"field": "name", "size": str(limit),
                                                                       "sort": "-downloads"}, ok404=True) or []
    return [{"spec": f"spigot:{r['id']}", "name": r.get("name"), "about": str(r.get("tag", ""))[:160],
             "downloads": r.get("downloads", 0), "premium": bool(r.get("premium"))} for r in data]


# ------------------------------------------------------------------ github
def _github_headers() -> dict:
    """GITHUB_TOKEN (any token, no scopes) lifts the 60 requests/hour limit of anonymous calls."""
    import os

    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def github_releases(project: str, pattern: str, platform: str, mc: str = "") -> list[Release]:
    rels = net.get_json(f"{GITHUB}/repos/{project}/releases", params={"per_page": "10"}, ok404=True,
                        headers=_github_headers())
    if rels is None:
        raise SourceError(f"github: no repository {project}")
    rx = re.compile(pattern or r"\.jar$")
    out = []
    for rel in rels:
        if rel.get("draft"):
            continue
        for a in rel.get("assets") or []:
            if rx.search(a.get("name", "")) and a["name"].endswith(".jar"):
                h = {}
                if str(a.get("digest", "")).startswith("sha256:"):
                    h["sha256"] = a["digest"].split(":", 1)[1]
                out.append(Release("github", project, project.split("/")[-1],
                                   str(rel.get("tag_name", "")).lstrip("v"), a["name"], a["browser_download_url"], h,
                                   [], "beta" if rel.get("prerelease") else "release", [],
                                   f"https://github.com/{project}/releases"))
                break
    return out


# ------------------------------------------------------------------ jenkins
def jenkins_releases(job: str, pattern: str, platform: str, mc: str = "") -> list[Release]:
    job = job.rstrip("/")
    b = net.get_json(f"{job}/lastSuccessfulBuild/api/json", ok404=True)
    if b is None:
        raise SourceError(f"jenkins: no job {job}")
    rx = re.compile(pattern or r"\.jar$")
    for a in b.get("artifacts") or []:
        if rx.search(a.get("fileName", "")) and a["fileName"].endswith(".jar"):
            return [Release("jenkins", job, job.split("/job/")[-1].split("/")[0], f"build {b.get('number')}",
                            a["fileName"], f"{job}/lastSuccessfulBuild/artifact/{a['relativePath']}", {}, [], "release",
                            [], job)]
    raise SourceError(f"jenkins {job}: no artifact matching {rx.pattern}")


# ------------------------------------------------------------------ url
def url_releases(url: str) -> list[Release]:
    name = url.split("?")[0].rstrip("/").split("/")[-1] or "plugin.jar"
    if not name.endswith(".jar"):
        name += ".jar"
    return [Release("url", url, name[:-4], "", name, url, {}, [], "release", [], url,
                    "downloaded from a plain URL: no checksum to verify")]


# ------------------------------------------------------------------ dispatch
def releases(spec: str, platform: str, mc: str = "") -> list[Release]:
    kind, project, pattern = parse_spec(spec)
    if kind == "modrinth":
        return modrinth_releases(project, platform, mc)
    if kind == "hangar":
        return hangar_releases(project, platform, mc)
    if kind == "spigot":
        return spigot_releases(project, platform, mc)
    if kind == "github":
        return github_releases(project, pattern, platform, mc)
    if kind == "jenkins":
        return jenkins_releases(project, pattern, platform, mc)
    if kind == "url":
        return url_releases(project)
    raise SourceError(f"unknown source '{kind}' in '{spec}'")


def resolve(spec: str, platform: str, mc: str = "") -> Release:
    rs = releases(spec, platform, mc)
    r = pick(rs, mc)
    if r is None:
        raise SourceError(f"{spec}: no build for {platform} {mc}".strip())
    return r
