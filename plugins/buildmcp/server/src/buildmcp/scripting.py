"""Script execution for run_script: a namespace with the whole building API bound to the
current scene and theme, captured output, and a watchdog timeout.
"""

from __future__ import annotations

import ctypes
import inspect
import io
import math
import threading
import traceback
import types

import numpy as np

from . import themes as themes_mod
from .blocks.finalize import finalize
from .geo import sdf, shapes
from .geo.box import Box
from .geo.mask import Mask
from .paint import noise, palette as P


class ScriptTimeout(Exception):
    pass


class Bound:
    """Module proxy: functions whose first parameter is ``scene`` get the current scene;
    functions with a ``theme`` parameter get the project theme unless given."""

    def __init__(self, module: types.ModuleType, scene, theme):
        self._m = module
        self._scene = scene
        self._theme = theme

    def __getattr__(self, name):
        obj = getattr(self._m, name)
        if not callable(obj) or isinstance(obj, type):
            return obj
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            return obj
        params = list(sig.parameters)
        takes_scene = bool(params) and params[0] == "scene"
        takes_theme = "theme" in sig.parameters

        def wrapper(*args, **kwargs):
            if takes_theme and kwargs.get("theme") is None:
                kwargs["theme"] = self._theme
            if takes_scene:
                return obj(self._scene, *args, **kwargs)
            return obj(*args, **kwargs)

        wrapper.__doc__ = obj.__doc__
        wrapper.__name__ = name
        return wrapper

    def __dir__(self):
        return [n for n in dir(self._m) if not n.startswith("_")]


def namespace(project, out: io.StringIO) -> dict:
    from .analyze import lint as lint_mod
    from .gen import arch, entities, image, model, paths, props, rocks, terrain, text, trees
    from .paint import colors

    S = project.scene
    T = themes_mod.get(project.theme)

    def _print(*a, **k):
        k.pop("file", None)
        print(*a, file=out, **k)

    ns = {
        "S": S, "scene": S, "T": T, "theme": T, "themes": themes_mod,
        "P": P, "noise": noise, "np": np, "math": math, "Box": Box, "Mask": Mask, "sdf": sdf, "shapes": shapes,
        "terrain": Bound(terrain, S, T), "trees": Bound(trees, S, T), "arch": Bound(arch, S, T),
        "props": Bound(props, S, T), "rocks": Bound(rocks, S, T), "paths": Bound(paths, S, T),
        "text": Bound(text, S, T), "E": Bound(entities, S, T), "image": Bound(image, S, T),
        "model": Bound(model, S, T), "colors": colors,
        "finalize": lambda where=None, rules=None: finalize(S, where, rules),
        "lint": lambda where=None: lint_mod.format_issues(lint_mod.lint(S, where)),
        "mark": S.mark, "print": _print, "rng": np.random.default_rng(project.seed),
        "project": project,
    }
    return ns


def _async_raise(thread: threading.Thread, exc_type) -> None:
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), ctypes.py_object(exc_type))


def run(code: str, ns: dict, timeout: float = 180.0) -> tuple[bool, str]:
    """Execute ``code`` in ``ns``. Returns (ok, error_text)."""
    result: dict = {}

    def target():
        try:
            compiled = compile(code, "<script>", "exec")
            exec(compiled, ns)  # noqa: S102 - scripts are the user's own build code
            result["ok"] = True
        except ScriptTimeout:
            result["err"] = f"Script stopped: exceeded {timeout:.0f} s."
        except Exception:  # noqa: BLE001 - report any script error back to the caller
            tb = traceback.format_exc()
            lines = [ln for ln in tb.splitlines() if "scripting.py" not in ln]
            result["err"] = "\n".join(lines[-12:])

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        _async_raise(th, ScriptTimeout)
        th.join(10)
        if "err" not in result:
            result["err"] = f"Script stopped: exceeded {timeout:.0f} s."
    return bool(result.get("ok")), result.get("err", "")
