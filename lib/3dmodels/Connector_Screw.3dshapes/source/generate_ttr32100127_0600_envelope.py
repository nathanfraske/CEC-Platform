#!/usr/bin/env python3
"""Generate the CEC collision-envelope STEP model for XFCN TTR32100127-0600.

This is deliberately not represented as manufacturer CAD.  XFCN's drawing
defines the 10 mm x 6 mm x 9 mm installed body envelope, 9 mm pin spacing,
2.0 mm x 1.5 mm PCB slots, and 12.7 mm overall height including the leads.
The public EasyEDA record for LCSC C45384691 does not contain a 3D model.

The simplified solid is conservative for clearance checking.  It includes the
body envelope, M3 clearance bore, and two lead envelopes; it does not attempt
to reproduce bends, radii, stamping reliefs, plating, or thread geometry.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cadquery as cq
from cadquery import exporters


BODY_WIDTH_MM = 10.0
BODY_DEPTH_MM = 6.0
BODY_HEIGHT_MM = 9.0
BODY_Y_MIN_MM = -1.5
BODY_Y_MAX_MM = 4.5
LEAD_SPACING_MM = 9.0
LEAD_X_MM = 1.0
LEAD_Y_MM = 1.5
LEAD_BELOW_BOARD_MM = 3.7
THREAD_CLEARANCE_DIAMETER_MM = 3.0


def build_model() -> cq.Workplane:
    """Return a footprint-aligned collision envelope; PCB plane is Z=0."""

    body_y_center = (BODY_Y_MIN_MM + BODY_Y_MAX_MM) / 2.0
    body = (
        cq.Workplane("XY")
        .box(
            BODY_WIDTH_MM,
            BODY_DEPTH_MM,
            BODY_HEIGHT_MM,
            centered=(True, True, False),
        )
        .translate((0.0, body_y_center, 0.0))
    )

    # The threaded face is vertical at +Y.  The bore is modeled only to make
    # mating direction obvious in KiCad; it is not a thread representation.
    bore = cq.Workplane(obj=cq.Solid.makeCylinder(
        THREAD_CLEARANCE_DIAMETER_MM / 2.0,
        BODY_DEPTH_MM + 0.4,
        cq.Vector(0.0, BODY_Y_MAX_MM + 0.2, BODY_HEIGHT_MM / 2.0),
        cq.Vector(0.0, -1.0, 0.0),
    ))
    body = body.cut(bore)

    lead = (
        cq.Workplane("XY")
        .box(LEAD_X_MM, LEAD_Y_MM, LEAD_BELOW_BOARD_MM, centered=(True, True, False))
        .translate((0.0, 0.0, -LEAD_BELOW_BOARD_MM))
    )
    model = body.union(lead.translate((-LEAD_SPACING_MM / 2.0, 0.0, 0.0)))
    model = model.union(lead.translate((LEAD_SPACING_MM / 2.0, 0.0, 0.0)))
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    default_output = Path(__file__).resolve().parents[1] / "XFCN_TTR32100127-0600_envelope.step"
    parser.add_argument("--output", type=Path, default=default_output)
    args = parser.parse_args()

    model = build_model()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(model, str(args.output))

    box = model.val().BoundingBox()
    print(f"wrote {args.output}")
    print(
        "bbox_mm "
        f"x=[{box.xmin:.3f},{box.xmax:.3f}] "
        f"y=[{box.ymin:.3f},{box.ymax:.3f}] "
        f"z=[{box.zmin:.3f},{box.zmax:.3f}]"
    )


if __name__ == "__main__":
    main()
