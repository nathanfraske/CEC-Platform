import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_boarddb as boarddb  # noqa: E402


def _database(cache_entries=4):
    return boarddb.BoardDB.from_records(
        routing_layers=("F.Cu", "B.Cu"),
        copper_layer_count=4,
        declared_profile="fixture-profile",
        edge_bbox=(0.0, 0.0, 20.0, 10.0),
        footprints=(
            {"ref": "R1", "x": 5.0, "y": 5.0, "rotation": 0.0},
            {"ref": "U1", "x": 15.0, "y": 5.0, "rotation": 90.0},
        ),
        pads=(
            {"ref": "R1", "pad": "1", "net": "A", "x": 4.0, "y": 5.0,
             "bbox": (3.5, 4.5, 4.5, 5.5), "layers": ("F.Cu",)},
            {"ref": "R1", "pad": "2", "net": "B", "x": 6.0, "y": 5.0,
             "bbox": (5.5, 4.5, 6.5, 5.5), "layers": ("F.Cu",)},
            {"ref": "U1", "pad": "1", "net": "C", "x": 15.0, "y": 4.0,
             "bbox": (14.5, 3.5, 15.5, 4.5),
             "layers": ("F.Cu", "B.Cu")},
        ),
        cache_entries=cache_entries)


def test_translation_invalidates_only_moved_footprint_pads():
    database = _database()
    assert database.copper_layer_count == 4
    assert database.declared_profile == "fixture-profile"
    view = database.view({"R1": (7.0, 6.0, 0.0)})
    assert view.invalidation == {
        "dirty_footprints": ("R1",),
        "dirty_footprint_count": 1,
        "dirty_pad_indices": (0, 1),
        "dirty_pad_count": 2,
    }
    assert view.pad_records[0]["x"] == 6.0
    assert view.pad_records[0]["y"] == 6.0
    assert view.pad_records[0]["bbox"] == (5.5, 5.5, 6.5, 6.5)
    assert view.pad_records[2] == database.view().pad_records[2]


def test_180_rotation_is_exact_about_new_footprint_origin():
    database = _database()
    view = database.view({"R1": (5.0, 5.0, 180.0)})
    assert (view.pad_records[0]["x"], view.pad_records[0]["y"]) == (6.0, 5.0)
    assert view.pad_records[0]["bbox"] == (5.5, 4.5, 6.5, 5.5)
    assert (view.pad_records[1]["x"], view.pad_records[1]["y"]) == (4.0, 5.0)


def test_orthogonal_quarter_turns_transform_pad_and_bbox_exactly():
    database = _database()
    clockwise = database.view({"R1": (5.0, 5.0, 90.0)})
    assert (clockwise.pad_records[0]["x"],
            clockwise.pad_records[0]["y"]) == (5.0, 6.0)
    assert clockwise.pad_records[0]["bbox"] == (4.5, 5.5, 5.5, 6.5)
    counter = database.view({"R1": (5.0, 5.0, 270.0)})
    assert (counter.pad_records[0]["x"],
            counter.pad_records[0]["y"]) == (5.0, 4.0)
    assert counter.pad_records[0]["bbox"] == (4.5, 3.5, 5.5, 4.5)


def test_non_orthogonal_rotation_fails_closed_when_geometry_is_requested():
    database = _database()
    view = database.view({"R1": (5.0, 5.0, 45.0)})
    with pytest.raises(boarddb.UnsupportedTransform):
        _ = view.pad_records


def test_view_cache_and_fingerprint_are_order_independent_and_bounded():
    database = _database(cache_entries=2)
    a = database.view({"U1": (16.0, 5.0, 90.0),
                       "R1": (7.0, 5.0, 0.0)})
    b = database.view({"R1": (7.0, 5.0, 0.0),
                       "U1": (16.0, 5.0, 90.0)})
    assert a is b
    assert a.fingerprint == b.fingerprint
    database.view({"R1": (8.0, 5.0, 0.0)})
    database.view({"R1": (9.0, 5.0, 0.0)})
    assert len(database._views) == 2


def test_spatial_index_is_conservative_and_source_ordered():
    view = _database().view()
    assert view.spatial_index.query_segment(
        "F.Cu", 3.8, 5.0, 6.2, 5.0, margin=0.2) == (0, 1)
    assert view.spatial_index.query_segment(
        "B.Cu", 14.8, 3.8, 15.2, 4.2, margin=0.2) == (2,)
    assert view.spatial_index.query_segment(
        "B.Cu", 1.0, 1.0, 2.0, 2.0, margin=0.2) == ()
