"""HTTP client for the BuildBridge Paper plugin."""

from __future__ import annotations

import time
import urllib.parse

import httpx

from .bundle import Bundle


class BridgeError(RuntimeError):
    pass


class BridgeClient:
    def __init__(self, url: str, token: str, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout, trust_env=False)

    def close(self) -> None:
        self._http.close()

    # -------------------------------------------------------------- plumbing
    def _req(self, method: str, path: str, *, json=None, content: bytes | None = None, auth: bool = True,
             timeout: float | None = None, raw: bool = False):
        headers = {"Authorization": f"Bearer {self.token}"} if auth else {}
        if content is not None:
            headers["Content-Type"] = "application/octet-stream"
        try:
            r = self._http.request(method, self.url + path, json=json, content=content, headers=headers,
                                   timeout=timeout or self.timeout)
        except httpx.TimeoutException as e:
            raise BridgeError(f"BuildBridge at {self.url} did not answer in time ({path})") from e
        except httpx.HTTPError as e:
            raise BridgeError(f"cannot reach BuildBridge at {self.url}: {e}") from e
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except ValueError:
                msg = r.text[:300]
            raise BridgeError(f"BuildBridge {r.status_code} on {path}: {msg}")
        return r.content if raw else r.json()

    # ------------------------------------------------------------- endpoints
    def ping(self) -> dict:
        return self._req("GET", "/v1/ping", auth=False, timeout=5.0)

    def status(self) -> dict:
        return self._req("GET", "/v1/status")

    def players(self) -> list[dict]:
        return self._req("GET", "/v1/players")["players"]

    def player(self, name: str = "") -> dict:
        return self._req("GET", "/v1/players/" + urllib.parse.quote(name or "@", safe=""))

    def paste(self, bundle: Bundle | bytes) -> dict:
        data = bundle.to_bytes() if isinstance(bundle, Bundle) else bundle
        return self._req("POST", "/v1/paste", content=data, timeout=max(self.timeout, 120.0))

    def job(self, job_id: str) -> dict:
        return self._req("GET", "/v1/jobs/" + urllib.parse.quote(job_id, safe=""))

    def jobs(self) -> list[dict]:
        return self._req("GET", "/v1/jobs")["jobs"]

    def cancel(self, job_id: str) -> dict:
        return self._req("POST", "/v1/jobs/" + urllib.parse.quote(job_id, safe="") + "/cancel")

    def wait(self, job_id: str, timeout: float = 900.0, on_progress=None, poll: float = 0.25) -> dict:
        """Poll a job until it ends (or the timeout passes; then the last status is returned)."""
        end = time.time() + timeout
        last = None
        while True:
            j = self.job(job_id)
            if on_progress and (last is None or (j["phase"], j["done"]) != last):
                on_progress(j)
                last = (j["phase"], j["done"])
            if j["phase"] in ("done", "failed", "cancelled"):
                return j
            if time.time() > end:
                return j
            time.sleep(poll)
            poll = min(1.0, poll * 1.3)

    def backups(self) -> list[dict]:
        return self._req("GET", "/v1/backups")["backups"]

    def undo(self, backup: str = "last") -> dict:
        return self._req("POST", "/v1/undo", json={"backup": backup})

    def region(self, box, world: str | None = None, tiles: bool = True, entities: bool = True) -> Bundle:
        data = self._req("POST", "/v1/region", json={"world": world, "box": [int(v) for v in box], "tiles": tiles,
                                                      "entities": entities}, timeout=900.0, raw=True)
        return Bundle.from_bytes(data)

    def heightmap(self, rect, world: str | None = None) -> dict:
        return self._req("POST", "/v1/heightmap", json={"world": world, "rect": [int(v) for v in rect]},
                         timeout=900.0)

    def command(self, command: str, world: str | None = None) -> dict:
        return self._req("POST", "/v1/command", json={"command": command, "world": world})

    def teleport(self, player: str, pos, yaw: float | None = None, pitch: float | None = None,
                 world: str | None = None) -> dict:
        body = {"player": player, "pos": [float(v) for v in pos], "world": world}
        if yaw is not None:
            body["yaw"] = float(yaw)
        if pitch is not None:
            body["pitch"] = float(pitch)
        return self._req("POST", "/v1/teleport", json=body)
