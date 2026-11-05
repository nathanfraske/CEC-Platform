"""A portable control is exact geometry, rules and real library bytes."""

import copy
import json
from pathlib import Path
import shutil

import pytest

from cec_pipeline import checkpoint
from cec_pipeline.workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]


def test_pinned_nine_board_checkpoint_is_self_contained_and_retains_native_closure(
    tmp_path,
):
    pin = json.loads((ROOT / "checkpoints/current.json").read_text())
    source = ROOT / pin["receipt"]
    clone = tmp_path / "relocated"
    shutil.copytree(
        source.parent, clone, ignore=shutil.ignore_patterns("*.kicad_prl", "*.lck")
    )
    result = checkpoint.normalize(clone / "receipt.json", pin["sha256"])
    assert len(result["boards"]) == 9
    assert result["totals"] == dict(opens=0, errors=0, warnings=283, exclusions=0)
    assert not result["manufacturing_or_current_qualified"]
    for row in result["boards"]:
        assert Path(row["path"]).is_relative_to(clone)
        checkpoint.verify_producer(row)
    workbench = Workbench(
        tmp_path / "jobs",
        checkpoint=clone / "receipt.json",
        checkpoint_sha256=pin["sha256"],
    )
    assert len(workbench.boards()["boards"]) == 9
    # The library parser uses tuples; persisted jobs use JSON lists. Exact
    # canonical identity must survive that normal transport conversion.
    job = workbench._make_job("hub-standard-rev2", dict(kind="inspect"))
    expected = next(
        row["sha256"] for row in result["boards"] if row["board"] == "hub-standard-rev2"
    )
    assert workbench._job(job)[1]["source_sha256"] == expected
    assert (tmp_path / "jobs/campaign.sqlite3").is_file() or list(
        (tmp_path / "jobs").glob("*.sqlite*")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "pcb",
        "project",
        "custom_rules",
        "library",
        "report",
        "origin",
        "escape",
        "duplicate",
        "review_plot",
    ],
)
def test_portable_control_rejects_changed_context_or_escaped_asset(tmp_path, fault):
    pin = json.loads((ROOT / "checkpoints/current.json").read_text())
    source = ROOT / pin["receipt"]
    clone = tmp_path / "clone"
    shutil.copytree(source.parent, clone)
    path = clone / "receipt.json"
    raw = json.loads(path.read_text())
    row = raw["boards"][0]
    if fault == "pcb":
        target = clone / row["path"]
    elif fault == "project":
        target = (clone / row["path"]).with_suffix(".kicad_pro")
    elif fault == "custom_rules":
        target = (clone / row["path"]).with_suffix(".kicad_dru")
    elif fault == "library":
        target = (clone / row["footprint_table"]["path"]).parent / next(
            iter(row["footprint_table"]["referenced_assets"])
        )
    elif fault == "report":
        target = clone / row["result"]
    elif fault == "origin":
        target = clone / raw["origin_receipt"]
    elif fault == "review_plot":
        target = (
            clone
            / raw["selected_children"][0]["reviewed_native_plots"]["after"]["path"]
        )
    elif fault == "escape":
        row["path"] = "../outside.kicad_pcb"
        (tmp_path / "outside.kicad_pcb").write_text("not a control")
        target = None
    else:
        raw["boards"].append(copy.deepcopy(row))
        target = None
    if target is not None:
        target.write_bytes(target.read_bytes() + b"\nchanged\n")
    else:
        path.write_text(json.dumps(raw))
    with pytest.raises((ValueError, FileNotFoundError)):
        checkpoint.normalize(path, checkpoint.sha(path))
