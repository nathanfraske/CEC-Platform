"""Causal native issue maps for model inspection and reviewer annotations.

Observations retain their exact source identity and qualification boundary.
Placement peers and analytical route opportunities are hints, not DRC errors.
"""

from __future__ import annotations

import hashlib
import json


def identity(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()[:20]


def compile_map(world, native, craft, fields):
    objects = {
        item["uuid"]: dict(kind="track", net=item["net"], layer=item["layer_name"])
        for item in world["tracks"]
    }
    for item in world.get("vias", []):
        objects[item["uuid"]] = dict(kind="via", net=item["net"])
    for item in world.get("zones", []):
        objects[item["uuid"]] = dict(kind="zone", net=item["net"])
    for footprint in world["footprints"]:
        objects[footprint["uuid"]] = dict(kind="footprint", reference=footprint["ref"])
        for pad in footprint["pads"]:
            objects[pad["uuid"]] = dict(
                kind="pad", reference=footprint["ref"], pin=pad["pin"], net=pad["net"]
            )
    rows = []

    def add(family, kind, severity, uuids, detail):
        uuids = sorted(set(uuids))
        members = [dict(uuid=uid, **objects.get(uid, {})) for uid in uuids]
        row = dict(
            family=family, type=kind, severity=severity, objects=members, detail=detail
        )
        row["id"] = identity(row)
        rows.append(row)

    for violation in native.get("violations", []):
        add(
            "native",
            violation["type"],
            violation["severity"],
            [item["uuid"] for item in violation.get("items", []) if item.get("uuid")],
            violation,
        )
    for item in native.get("unconnected_items", []):
        add(
            "native",
            "unconnected",
            "error",
            [q["uuid"] for q in item.get("items", []) if q.get("uuid")],
            item,
        )
    for issue in [
        *craft.get("issues", []),
        *craft.get("non_octilinear", []),
        *craft.get("power_contours", {}).get("findings", []),
    ]:
        uuids = [
            *issue.get("uuids", issue.get("track_uuids", [])),
            *issue.get("zone_uuids", []),
        ]
        if issue.get("uuid"):
            uuids = [*uuids, issue["uuid"]]
        add(
            "craft",
            issue.get("type", "route_craft"),
            issue.get("severity", "review"),
            uuids,
            issue,
        )
        if issue.get("semantic_id"):
            rows[-1]["target_issue_id"] = issue["semantic_id"]
    for issue in fields.get("interactions", []):
        add(
            "field",
            issue.get("type", "coupling"),
            "blocking" if issue.get("blocking") else "review",
            issue.get("track_uuids", issue.get("uuids", [])),
            issue,
        )
    return dict(
        schema=1,
        complete=True,
        source_sha256=world["sha256"],
        board=world["board"],
        issues=rows,
        key=dict(
            native="Saved configured native DRC, not whole fabrication qualification",
            craft="Actual route geometry findings; review inherited debt separately",
            field="Physical field-policy interactions, not a full EMC qualification",
        ),
        release_authority=False,
    )


def viewer_findings(craft, items):
    """Adapt actual craft observations to the existing inspection overlay.

    Locations are bounds of implicated saved objects, not invented defect
    coordinates. A craft finding is review debt, never a native DRC error.
    """
    rows = []
    for issue in [
        *craft.get("issues", []),
        *craft.get("non_octilinear", []),
        *craft.get("power_contours", {}).get("findings", []),
    ]:
        uuids = sorted(
            set(
                [
                    *issue.get("track_uuids", issue.get("uuids", [])),
                    *issue.get("zone_uuids", []),
                    *([issue["uuid"]] if issue.get("uuid") else []),
                ]
            )
        )
        selected = [items[uid] for uid in uuids if uid in items]
        loci = []
        for item in selected:
            if item.get("a") and item.get("b"):
                loci.append([(a + b) / 2 for a, b in zip(item["a"], item["b"])])
            elif item.get("at"):
                loci.append(item["at"])
        rows.append(
            dict(
                id="craft-" + identity(issue),
                kind="craft",
                severity="review",
                type=issue.get("type", "route_craft"),
                description=issue.get(
                    "message", issue.get("type", "Route/power-copper review")
                ),
                uuids=uuids,
                loci=loci,
                layers=sorted(
                    {item["layer"] for item in selected if item.get("layer")}
                ),
                nets=sorted({item["net"] for item in selected if item.get("net")}),
                items=[
                    dict(
                        uuid=uid,
                        description=items.get(uid, {}).get("ref")
                        or items.get(uid, {}).get("net")
                        or uid,
                    )
                    for uid in uuids
                ],
                detail=issue,
                location_kind="bounds of exact implicated saved native objects",
            )
        )
    return rows
