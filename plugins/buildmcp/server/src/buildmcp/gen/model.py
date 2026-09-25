"""3D models (.obj/.glb/.gltf/.stl/.ply) into blocks — statues, dragons, emblems.

Colors come from the model's texture/vertex colors (matched to the nearest blocks), or a
single palette when the model has none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..geo.mask import Mask


def voxelize(path, height: int, *, rotate_y: float = 0.0, up: str = "y") -> tuple[np.ndarray, np.ndarray | None, float]:
    """(filled bool grid (x, y, z), per-voxel RGB or None, pitch). The model is scaled to ``height`` blocks."""
    import trimesh

    scene_or_mesh = trimesh.load(str(Path(path)), force="scene")
    mesh = scene_or_mesh.dump(concatenate=True) if isinstance(scene_or_mesh, trimesh.Scene) else scene_or_mesh
    if up == "z":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    if rotate_y:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(rotate_y), [0, 1, 0]))
    ext = mesh.bounds[1] - mesh.bounds[0]
    pitch = float(ext[1]) / max(1, height)
    vox = mesh.voxelized(pitch=pitch)
    try:
        vox = vox.fill()
    except Exception:  # noqa: BLE001 - non-watertight meshes keep their shell
        pass
    grid = np.asarray(vox.matrix, bool)
    colors = None
    try:
        # surface colors: sample the mesh at each voxel center
        centers = vox.points
        visual = mesh.visual
        if hasattr(visual, "to_color"):
            visual = visual.to_color()
        vc = getattr(visual, "vertex_colors", None)
        if vc is not None and len(vc) == len(mesh.vertices):
            _, _, tri = trimesh.proximity.closest_point(mesh, centers)
            face_cols = vc[mesh.faces[tri]].mean(axis=1)[:, :3]
            colors = np.zeros(grid.shape + (3,), np.uint8)
            idx = vox.points_to_indices(centers)
            colors[idx[:, 0], idx[:, 1], idx[:, 2]] = face_cols.astype(np.uint8)
    except Exception:  # noqa: BLE001
        colors = None
    return grid, colors, pitch


def place_model(scene, path, at, height: int, *, palette=None, blocks: str = "concrete+terracotta+wool+stone",
                rotate_y: float = 0.0, up: str = "y", hollow: bool = True) -> Mask:
    """Voxelize a 3D model into the scene with its bottom-center at ``at``.

    palette: block/palette for the whole model (ignores model colors); otherwise colors are matched.
    hollow: keep only the outer 2 layers (fewer blocks, same look).
    """
    grid, colors, _ = voxelize(path, height, rotate_y=rotate_y, up=up)
    m = Mask((0, 0, 0), grid)
    if hollow:
        m = m - m.erode(2)
    sx, sy, sz = grid.shape
    ox, oy, oz = int(at[0]) - sx // 2, int(at[1]), int(at[2]) - sz // 2
    m = m.translate(ox, oy, oz)
    if palette is not None or colors is None:
        scene.put(m, palette or "stone")
        return m
    from ..paint.colors import image_to_blocks

    xs, ys, zs = np.nonzero(grid)
    cols = colors[xs, ys, zs]
    names = image_to_blocks(cols.reshape(-1, 1, 3), scene.version, blocks, dither=False)[:, 0]
    keep = m.to_box(m.extent)
    for (x, y, z), n in zip(zip(xs, ys, zs), names):
        p = (x + ox, y + oy, z + oz)
        if m.contains(p):
            scene.set(*p, n)
    return m
