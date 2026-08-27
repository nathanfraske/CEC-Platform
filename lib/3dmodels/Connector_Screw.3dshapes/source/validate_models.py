#!/usr/bin/env python3
"""Print bounding boxes for the Connector_Screw STEP assets."""

from pathlib import Path

import cadquery as cq


MODEL_DIR = Path(__file__).resolve().parents[1]


for name in (
    "XFCN_T34069_native.step",
    "XFCN_TTR32100127-0600_envelope.step",
):
    model = cq.importers.importStep(str(MODEL_DIR / name))
    box = model.val().BoundingBox()
    print(
        f"{name}: "
        f"x=[{box.xmin:.3f},{box.xmax:.3f}] "
        f"y=[{box.ymin:.3f},{box.ymax:.3f}] "
        f"z=[{box.zmin:.3f},{box.zmax:.3f}]"
    )
    z_values = sorted({round(vertex.toTuple()[2], 3) for vertex in model.vertices().vals()})
    print(f"  vertex_z_levels={z_values}")
    for index, face in enumerate(model.faces().vals()):
        if face.geomType() != "CYLINDER":
            continue
        face_box = face.BoundingBox()
        center = face.Center().toTuple()
        print(
            f"  cylinder[{index}] center=({center[0]:.3f},{center[1]:.3f},{center[2]:.3f}) "
            f"bbox=x[{face_box.xmin:.3f},{face_box.xmax:.3f}] "
            f"y[{face_box.ymin:.3f},{face_box.ymax:.3f}] "
            f"z[{face_box.zmin:.3f},{face_box.zmax:.3f}]"
        )
