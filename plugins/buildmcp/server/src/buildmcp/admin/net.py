"""HTTP for the admin tools: one client with a proper User-Agent, JSON GETs and checked downloads.

Tests swap the transport (``set_transport``) for recorded answers, so nothing here talks to the
network in the unit tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from buildmcp import __version__

USER_AGENT = f"Daniiltoptl/BuildMCP/{__version__} (+https://github.com/Daniiltoptl/BuildMCP-test-project-)"
_TRANSPORT = None  # httpx transport override (tests)
_CLIENT = None


class NetError(RuntimeError):
    pass


def set_transport(transport) -> None:
    """Route every request through ``transport`` (an httpx.MockTransport in tests); None = network."""
    global _TRANSPORT, _CLIENT
    _TRANSPORT = transport
    if _CLIENT is not None:
        _CLIENT.close()
    _CLIENT = None


def client():
    global _CLIENT
    if _CLIENT is None:
        import httpx

        kw = {"timeout": httpx.Timeout(60.0, connect=20.0), "follow_redirects": True,
              "headers": {"User-Agent": USER_AGENT}}
        if _TRANSPORT is not None:
            kw["transport"] = _TRANSPORT
        else:
            try:
                import ssl

                import truststore

                kw["verify"] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            except Exception:  # noqa: BLE001 - certifi / environment settings
                pass
        _CLIENT = httpx.Client(**kw)
    return _CLIENT


def get_json(url: str, params: dict | None = None, headers: dict | None = None, ok404: bool = False):
    """GET and decode JSON. ok404: return None for 404 instead of raising."""
    try:
        r = client().get(url, params=params, headers=headers)
    except Exception as e:  # noqa: BLE001
        raise NetError(f"{url}: {e}") from e
    if ok404 and r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise NetError(f"{url}: HTTP {r.status_code} {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise NetError(f"{url}: not JSON ({r.text[:120]!r})") from e


def download(url: str, dest: Path, *, sha256: str | None = None, sha512: str | None = None,
             sha1: str | None = None, md5: str | None = None, headers: dict | None = None,
             max_bytes: int = 512 * 1024 * 1024) -> dict:
    """Stream ``url`` into ``dest`` (via a temporary file), checking the given hashes.
    Returns {"path", "size", "sha256"}."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    hs = {"sha256": hashlib.sha256(), "sha512": hashlib.sha512(), "sha1": hashlib.sha1(), "md5": hashlib.md5()}
    size = 0
    try:
        with client().stream("GET", url, headers=headers) as r:
            if r.status_code >= 400:
                raise NetError(f"{url}: HTTP {r.status_code}")
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise NetError(f"{url}: bigger than {max_bytes // 1024 // 1024} MB")
                    f.write(chunk)
                    for h in hs.values():
                        h.update(chunk)
    except NetError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise NetError(f"{url}: {e}") from e
    for name, want in (("sha256", sha256), ("sha512", sha512), ("sha1", sha1), ("md5", md5)):
        if want and hs[name].hexdigest().lower() != want.lower():
            tmp.unlink(missing_ok=True)
            raise NetError(f"{url}: {name} mismatch (the file is damaged or was replaced)")
    tmp.replace(dest)
    return {"path": str(dest), "size": size, "sha256": hs["sha256"].hexdigest()}
