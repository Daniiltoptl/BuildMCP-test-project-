"""API reference for scripts, generated from the code (so it never drifts)."""

from __future__ import annotations

import inspect

INDEX = """\
BuildMCP scripting API — names available inside run_script:

  S / scene   the Scene (put/fill/set/replace/clear/mask/surface/copy/paste/transform/stats/mark...)
  T / theme   current theme (role palettes: T.grass T.rock T.wall T.roof T.leaves ...); themes.get("asian_sakura")
  P           palettes: P.mix P.patches P.gradient P.layers P.field P.checker P.stripes
  Box, Mask   regions; sdf (organic shapes), shapes (lines, splines, circles, polygons, spirals)
  noise       fbm, ridged, worley, hash01 (deterministic)
  terrain     island, ground, cover, pond, waterfall, paint_terrain, decorate_underside
  trees       tree(at, kind=oak_giant|oak|birch|willow|cherry|pine|dead|fungus_giant|bush), forest
  arch        roof, walls, window, door, house, tower, column, arch, battlements, pagoda, torii,
              cone_roof, dome_roof, stairify
  props       lamp_post, bench, fountain, well, market_stall, portal_frame, banner_pole, planter
  rocks       boulder, rock_cluster, spike, crystal, crystal_cluster, stalactites
  paths       path, plaza, steps, bridge
  text        text3d (built-in pixel font incl. Cyrillic, or TTF)
  E           hologram, component, block_display, item_display, sign, banner, head
  image       pixel_art, heightmap;   model: place_model (.obj/.glb/.stl)
  colors      nearest, similar, gradient_between (block colors from real textures)
  finalize()  game-like block updates (fences, walls, stairs corners, leaves...) — run at the end
  lint()      quality/correctness report;  mark(name, pos, kind, yaw) — markers
  print()     goes to the tool output;  np, math, rng (seeded)

Generator functions get the scene (and the project theme) automatically: write
trees.tree((10, 80, 4), "oak_giant"), not trees.tree(S, ...).

Conventions: x = east, y = up, z = south. Boxes are inclusive (x1,y1,z1,x2,y2,z2).
Block (x,y,z) spans [x,x+1) — SDF centers on (x+0.5, y+0.5, z+0.5) sit on block centers.
A "block" argument accepts: "stone_bricks", "oak_stairs[facing=east]", {"stone": 3, "andesite": 1},
["a", "b"], a Palette, or f(x, y, z) -> str. Patterns (only=, replace, mask): "stone|*_log|#leaves|!#air".
Facing strings: north/south/east/west. Yaw (markers, cameras): 0 south, 90 west, 180 north, 270 east.

Topics for api_docs(topic): scene, palette, mask, box, sdf, shapes, noise, terrain, trees, arch,
props, rocks, paths, text, entities, image, model, colors, themes, patterns, workflow.
"""

PATTERNS = """\
Block patterns (only=, S.replace, S.mask, S.count):
  stone                  exact block, any state
  oak_stairs[half=top]   with property constraints
  *_log  *brick*         glob on the name
  #tag                   air liquid water solid opaque transparent leaves logs planks stairs slabs walls
                         fences fence_gates panes doors trapdoors plants flowers carpets glass wool concrete
                         terracotta lights signs banners heads gravity replaceable non_air
  a|b|!c                 alternatives, '!' excludes (e.g. "#solid|!glass")
"""

WORKFLOW = """\
Typical flow per build step:
  1. run_script(code, label)  — each call is a pipeline step (saved in scripts/, undoable)
  2. render(view="sheet") / render(view="player", marker="spawn") — look at it
  3. inspect(what="lint") / inspect(what="walk") — fix issues
  4. history(action="undo") if a step went wrong; steps(action="edit") + rebuild() to change early steps
  5. finalize() at the end of the last step (run_script does not finalize automatically, export does)
  6. export(format="schem") or server_paste() to put it in the world
"""


def _fmt_function(name: str, fn, bound_hint: bool) -> str:
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if bound_hint and params and params[0].name == "scene":
            params = params[1:]
        sig_s = "(" + ", ".join(str(p) for p in params) + ")"
    except (TypeError, ValueError):
        sig_s = "(...)"
    doc = inspect.getdoc(fn) or ""
    doc = doc.strip()
    return f"{name}{sig_s}\n    " + doc.replace("\n", "\n    ") if doc else f"{name}{sig_s}"


def _module_doc(module, bound: bool, names: list[str] | None = None) -> str:
    out = [inspect.getdoc(module) or ""]
    for name, obj in inspect.getmembers(module):
        if name.startswith("_"):
            continue
        if names is not None and name not in names:
            continue
        if inspect.isfunction(obj) and obj.__module__ == module.__name__:
            out.append(_fmt_function(name, obj, bound))
    return "\n\n".join(x for x in out if x)


def _class_doc(cls, skip_private: bool = True) -> str:
    out = [f"class {cls.__name__}: " + (inspect.getdoc(cls) or "")]
    for name, obj in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj) or isinstance(obj, property):
            if isinstance(obj, property):
                out.append(f"{name} (property)" + (f"\n    {inspect.getdoc(obj)}" if inspect.getdoc(obj) else ""))
            else:
                out.append(_fmt_function(name, obj, False).replace("(self, ", "(").replace("(self)", "()"))
    return "\n\n".join(out)


def topic(name: str) -> str:
    from . import themes
    from .gen import arch, entities, image, model, paths, props, rocks, terrain, text, trees
    from .geo import box, mask, sdf, shapes
    from .paint import colors, noise, palette
    from .scene import Scene

    key = (name or "index").lower().strip()
    if key in ("index", "", "help"):
        return INDEX
    if key == "patterns":
        return PATTERNS
    if key == "workflow":
        return WORKFLOW
    if key in ("s", "scene"):
        return _class_doc(Scene)
    if key in ("p", "palette", "palettes"):
        return _module_doc(palette, False)
    if key == "mask":
        return _class_doc(mask.Mask)
    if key == "box":
        return _class_doc(box.Box)
    if key == "sdf":
        return _module_doc(sdf, False) + "\n\n" + _class_doc(sdf.SDF)
    if key == "shapes":
        return _module_doc(shapes, False)
    if key == "noise":
        return _module_doc(noise, False)
    if key == "themes":
        return "\n\n".join(themes.get(n).describe() for n in themes.names())
    mods = {"terrain": terrain, "trees": trees, "arch": arch, "props": props, "rocks": rocks, "paths": paths,
            "text": text, "entities": entities, "e": entities, "image": image, "model": model, "colors": colors}
    if key in mods:
        return _module_doc(mods[key], key != "colors")
    raise KeyError(f"unknown topic '{name}'. Use api_docs('index') for the list.")
