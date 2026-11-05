"""Reviewer faults retain their exact native objects and source identity."""

from cec_pipeline.issues import compile_map
from cec_pipeline.issues import viewer_findings


def test_viewer_adaptation_keeps_craft_separate_from_native_fault_counts():
    craft = dict(
        issues=[],
        non_octilinear=[dict(type="non_octilinear_segment", uuid="a")],
        power_contours=dict(findings=[dict(type="rounded_landing", zone_uuids=["z"])]),
    )
    items = dict(
        a=dict(net="CTRL", layer="B.Cu", a=[1, 2], b=[3, 4]),
        z=dict(net="BUS", at=[5, 6]),
    )
    rows = viewer_findings(craft, items)
    assert all(row["kind"] == "craft" and row["severity"] == "review" for row in rows)
    assert rows[0]["loci"] == [[2, 3]] and rows[0]["layers"] == ["B.Cu"]
    assert rows[1]["nets"] == ["BUS"] and rows[1]["items"][0]["description"] == "BUS"


def test_issue_map_covers_geometry_contours_native_opens_and_physical_coupling():
    world = dict(
        sha256="a" * 64,
        board="opaque",
        tracks=[dict(uuid="t", net="CTRL", layer_name="F.Cu")],
        zones=[dict(uuid="z", net="POWER")],
        vias=[],
        footprints=[
            dict(uuid="f", ref="U_ANY", pads=[dict(uuid="p", pin="7", net="CTRL")])
        ],
    )
    native = dict(
        violations=[
            dict(
                type="clearance",
                severity="error",
                items=[dict(uuid="t"), dict(uuid="p")],
            )
        ],
        unconnected_items=[dict(items=[dict(uuid="p")])],
    )
    craft = dict(
        issues=[],
        non_octilinear=[dict(uuid="t", type="non_octilinear_segment")],
        power_contours=dict(findings=[dict(type="rounded_landing", zone_uuids=["z"])]),
    )
    fields = dict(interactions=[dict(track_uuids=["t"], blocking=True)])
    report = compile_map(world, native, craft, fields)
    assert len(report["issues"]) == 5 and report["source_sha256"] == "a" * 64
    assert {row["family"] for row in report["issues"]} == {"native", "craft", "field"}
    assert report["issues"][0]["objects"][0]["reference"] == "U_ANY"
    assert report["issues"][3]["objects"][0]["kind"] == "zone"
    assert report["issues"][-1]["objects"][0]["net"] == "CTRL"
    assert report == compile_map(world, native, craft, fields)
    assert not report["release_authority"]
