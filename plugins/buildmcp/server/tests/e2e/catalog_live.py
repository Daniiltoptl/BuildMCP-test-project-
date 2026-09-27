"""Check the plugin catalog and the core downloads against the live sources (CI, needs internet).

    python tests/e2e/catalog_live.py --mc 1.21.8 --out report.json

For every catalog entry and every platform it lists, each source is resolved, downloaded (checksum
verified) and its jar read: the descriptor has to fit the platform. An entry fails when none of its
sources gives a working jar for a platform. Also checks that Paper/Purpur/Folia/Velocity cores resolve
and that search works on every source. Writes a JSON report and, in GitHub Actions, a summary table.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from buildmcp.admin import catalog, jarinfo, net, software, sources


def check_source(spec: str, platform: str, mc: str, tmp: Path) -> dict:
    t0 = time.time()
    try:
        r = sources.resolve(spec, platform, mc)
        dest = tmp / f"{abs(hash((spec, platform))) % 10**8}-{r.filename}"
        got = net.download(r.url, dest, sha256=r.hashes.get("sha256"), sha512=r.hashes.get("sha512"),
                           sha1=r.hashes.get("sha1"))
        info = jarinfo.read(dest, platform)
        bad = jarinfo.fits(info, platform)
        dest.unlink(missing_ok=True)
        out = {"ok": bad is None, "version": r.version, "file": r.filename, "name": info.name,
               "plugin_version": info.version, "depend": info.depend, "mb": round(got["size"] / 1e6, 2),
               "checksum": ",".join(sorted(r.hashes)) or "none", "note": r.note, "s": round(time.time() - t0, 1)}
        if bad:
            out["error"] = bad
        return out
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "s": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", default="1.21.8", help="Minecraft version the Paper plugins are picked for")
    ap.add_argument("--out", default="catalog-report.json")
    ap.add_argument("--only", default="", help="comma-separated aliases")
    a = ap.parse_args()
    only = {x for x in a.only.split(",") if x}
    folia_mc = ""
    report: dict = {"mc": a.mc, "cores": {}, "search": {}, "plugins": {}}
    for sw in ("paper", "purpur", "folia", "velocity"):
        try:
            r = software.resolve(sw, "latest")
            report["cores"][sw] = {"ok": True, "version": r["version"], "build": r["build"], "name": r["name"]}
            if sw == "folia":
                folia_mc = r["version"]
        except Exception as e:  # noqa: BLE001
            report["cores"][sw] = {"ok": False, "error": str(e)[:300]}
    try:
        r = software.resolve("paper", a.mc)
        report["cores"][f"paper {a.mc}"] = {"ok": True, "version": r["version"], "build": r["build"]}
    except Exception as e:  # noqa: BLE001
        report["cores"][f"paper {a.mc}"] = {"ok": False, "error": str(e)[:300]}
    for name, fn in (("modrinth", lambda: sources.modrinth_search("luckperms", "paper", a.mc)),
                     ("hangar", lambda: sources.hangar_search("ViaVersion", "paper")),
                     ("spigot", lambda: sources.spigot_search("Vault"))):
        try:
            hits = fn()
            report["search"][name] = {"ok": bool(hits), "first": hits[0]["spec"] if hits else None}
        except Exception as e:  # noqa: BLE001
            report["search"][name] = {"ok": False, "error": str(e)[:300]}

    failed = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for alias, e in catalog.CATALOG.items():
            if only and alias not in only:
                continue
            per = {}
            for platform in e["platforms"]:
                mc = {"paper": a.mc, "folia": folia_mc, "velocity": ""}[platform]
                res = {spec: check_source(spec, platform, mc, tmp) for spec in e["sources"]}
                first = next((s for s, v in res.items() if v["ok"]), None)
                per[platform] = {"ok": first is not None, "used": first, "sources": res}
                if first is None:
                    failed.append(f"{alias} ({platform})")
                status = "ok " if first else "FAIL"
                print(f"{status} {alias:22} {platform:8} "
                      + "; ".join(f"{s}: {v.get('version') or v.get('error', '')[:90]}" for s, v in res.items()),
                      flush=True)
            report["plugins"][alias] = per
    report["failed"] = failed
    report["cores_failed"] = [k for k, v in report["cores"].items() if not v["ok"]]
    report["search_failed"] = [k for k, v in report["search"].items() if not v["ok"]]
    Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False), "utf-8")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [f"## Plugin catalog against live sources (Paper {a.mc})", "",
                 "| plugin | platform | source used | version | other sources |", "|---|---|---|---|---|"]
        for alias, per in report["plugins"].items():
            for platform, v in per.items():
                used = v["used"] or "**none**"
                ver = v["sources"][v["used"]]["version"] if v["used"] else ""
                others = "; ".join(f"{s}: {'ok' if r['ok'] else r.get('error', '')[:80]}"
                                   for s, r in v["sources"].items() if s != v["used"])
                lines.append(f"| {alias} | {platform} | {used} | {ver} | {others} |")
        lines += ["", "### Cores", ""] + [f"- {k}: {v.get('version', v.get('error'))} {v.get('build', '')}"
                                          for k, v in report["cores"].items()]
        lines += ["", "### Search", ""] + [f"- {k}: {v.get('first', v.get('error'))}" for k, v in report["search"].items()]
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    print(json.dumps({"failed": failed, "cores_failed": report["cores_failed"],
                      "search_failed": report["search_failed"]}, indent=1))
    return 1 if failed or report["cores_failed"] or report["search_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
