"""Portable review plots stay distinct through native inspection publication."""

import pytest

import cec_suite_inspection as report


def fixture(tmp_path):
    plots = {}
    for face, token in (("F", "a" * 16), ("B", "b" * 16), ("F", "c" * 16)):
        for side in ("before", "after"):
            key = side + "-" + face + "-Cu-" + token + ".svg"
            path = tmp_path / key
            path.write_text("<svg>synthetic distinct " + key + "</svg>")
            plots[key] = dict(path=str(path), sha256=report.sha(path))
    return dict(selected_children=[dict(board="arbitrary", reviewed_native_plots=plots)])


def test_inspection_retains_all_layer_crop_pairs_and_actual_hashes(tmp_path):
    receipt = fixture(tmp_path)
    assets = {}
    output = tmp_path / "inspection"
    views = report.copy_review_refinements(receipt, output, assets)[0]["plots"]
    original = receipt["selected_children"][0]["reviewed_native_plots"]
    assert set(views) == set(original) and len(views) == len(assets) == 6
    for key, relative in views.items():
        assert report.sha(output / relative) == original[key]["sha256"] == assets[relative]
    source = (report.STATIC / "cec_suite_inspection.js").read_text()
    assert "Object.entries(refinement.plots" in source


@pytest.mark.parametrize("damage", ["hash", "key"])
def test_changed_or_escaped_review_plot_refuses(tmp_path, damage):
    receipt = fixture(tmp_path)
    values = receipt["selected_children"][0]["reviewed_native_plots"]
    if damage == "hash":
        next(iter(values.values()))["sha256"] = "0" * 64
    else:
        receipt["selected_children"][0]["reviewed_native_plots"] = {"../escape": next(iter(values.values()))}
    with pytest.raises(ValueError, match="reviewed_refinement_plot_identity_mismatch"):
        report.copy_review_refinements(receipt, tmp_path / "inspection", {})


def test_legacy_before_after_pair_stays_compatible(tmp_path):
    receipt = fixture(tmp_path)
    old = receipt["selected_children"][0]["reviewed_native_plots"]
    receipt["selected_children"][0]["reviewed_native_plots"] = {
        side: next(value for key, value in old.items() if key.startswith(side))
        for side in ("before", "after")}
    rows = report.copy_review_refinements(receipt, tmp_path / "inspection", {})
    assert set(rows[0]["plots"]) == {"before", "after"}
