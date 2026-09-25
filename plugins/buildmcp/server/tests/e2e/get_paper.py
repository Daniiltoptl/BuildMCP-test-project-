"""Download a Paper server jar (CI helper).

    python get_paper.py 1.21.4 paper.jar      # exact version
    python get_paper.py latest paper.jar      # newest 1.21.x / 26.x build

Uses the PaperMC Fill API v3 and falls back to the v2 API.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request

UA = {"User-Agent": "BuildMCP-CI (https://github.com/Daniiltoptl/BuildMCP-test-project-)"}


def _get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _vkey(v: str):
    return tuple(int(p) if p.isdigit() else 0 for p in v.replace("-", ".").split("."))


def resolve(version: str) -> str:
    if version != "latest":
        return version
    data = _get("https://fill.papermc.io/v3/projects/paper")
    versions = [v for group in data["versions"].values() for v in group]
    stable = [v for v in versions if all(p.isdigit() for p in v.split(".")) and not v.startswith(("1.20", "1.19"))]
    return max(stable, key=_vkey)


def download(version: str, dest: str) -> str:
    version = resolve(version)
    try:
        b = _get(f"https://fill.papermc.io/v3/projects/paper/versions/{version}/builds/latest")
        d = b["downloads"]["server:default"]
        url, sha = d["url"], d["checksums"]["sha256"]
    except Exception as e:  # noqa: BLE001
        print(f"fill v3 failed ({e}), trying v2", file=sys.stderr)
        builds = _get(f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds")["builds"]
        last = builds[-1]
        name = last["downloads"]["application"]["name"]
        url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{last['build']}/downloads/{name}"
        sha = last["downloads"]["application"]["sha256"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit("checksum mismatch for " + url)
    with open(dest, "wb") as f:
        f.write(data)
    return version


if __name__ == "__main__":
    print(download(sys.argv[1], sys.argv[2]))
