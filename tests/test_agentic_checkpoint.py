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
            / next(iter(raw["selected_children"][0]["reviewed_native_plots"].values()))["path"]
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


@pytest.fixture
def synthetic_intakes(tmp_path, monkeypatch):
    """Control-plane fixtures only; no native CAD/qualification claims."""
    import cec_pipeline.workbench as controller

    repository = tmp_path / "repository"
    (repository / "checkpoints").mkdir(parents=True)
    receipts = []
    for name in ("A", "B"):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(dict(
            complete=True,
            boards=[dict(board="board-" + str(index), path=name + "-untouched-" + str(index),
                         sha256=name * 64,
                         counts=dict(opens=0, errors=0, warnings=0, exclusions=0))
                    for index in range(9)],
        )))
        receipts.append(path)

    def verify(path, expected):
        if checkpoint.sha(path) != expected:
            raise ValueError("synthetic_receipt_identity_changed")
        return json.loads(Path(path).read_text())

    def pin(path):
        (repository / "checkpoints/current.json").write_text(json.dumps(
            dict(receipt=str(path), sha256=checkpoint.sha(path))))

    monkeypatch.setattr(controller, "ROOT", repository)
    monkeypatch.setattr(controller.inspection, "verify_receipt", verify)
    pin(receipts[0])
    return receipts[0], receipts[1], pin


@pytest.mark.parametrize("explicit", [False, True])
def test_workspace_reopen_uses_bound_receipt_after_default_pin_advances(
    tmp_path, synthetic_intakes, explicit
):
    first, later, pin = synthetic_intakes
    workspace = tmp_path / "jobs"
    options = dict(checkpoint=first, checkpoint_sha256=checkpoint.sha(first)) if explicit else {}
    original = Workbench(workspace, **options)
    binding = (workspace / "source-checkpoint.json").read_bytes()
    pin(later)
    reopened = Workbench(workspace)
    assert reopened.manifest["source_receipt"] == str(first)
    assert reopened.manifest["source_receipt_sha256"] == checkpoint.sha(first)
    assert reopened.receipt == original.receipt
    assert all(row["path"].startswith("A-untouched-") for row in reopened.receipt["boards"])
    assert (workspace / "source-checkpoint.json").read_bytes() == binding


def test_workspace_explicit_different_receipt_or_path_refuses_without_rebinding(
    tmp_path, synthetic_intakes
):
    first, later, _ = synthetic_intakes
    workspace = tmp_path / "jobs"
    Workbench(workspace, checkpoint=first, checkpoint_sha256=checkpoint.sha(first))
    binding = (workspace / "source-checkpoint.json").read_bytes()
    relocated = tmp_path / "same-bytes-different-path.json"
    relocated.write_bytes(first.read_bytes())
    for other in (later, relocated):
        with pytest.raises(ValueError, match="workspace_source_checkpoint_changed"):
            Workbench(workspace, checkpoint=other, checkpoint_sha256=checkpoint.sha(other))
        assert (workspace / "source-checkpoint.json").read_bytes() == binding
    Workbench(workspace, checkpoint=first, checkpoint_sha256=checkpoint.sha(first))


def test_bound_receipt_bytes_are_reverified_on_reopen(tmp_path, synthetic_intakes):
    first, _, _ = synthetic_intakes
    workspace = tmp_path / "jobs"
    Workbench(workspace)
    first.write_text(first.read_text() + "\n")
    with pytest.raises(ValueError, match="receipt_identity_changed"):
        Workbench(workspace)


def test_legacy_workspace_requires_explicit_matching_intake(tmp_path, synthetic_intakes):
    first, later, pin = synthetic_intakes
    workspace = tmp_path / "legacy"
    directory = workspace / ("a" * 24)
    directory.mkdir(parents=True)
    job = directory / "job.json"
    job.write_text(json.dumps(dict(source_receipt_sha256=checkpoint.sha(first))))
    pin(later)
    with pytest.raises(ValueError, match="legacy_workspace_requires_explicit"):
        Workbench(workspace)
    assert not (workspace / "source-checkpoint.json").exists()
    with pytest.raises(ValueError, match="legacy_job_source_checkpoint_mismatch"):
        Workbench(workspace, checkpoint=later, checkpoint_sha256=checkpoint.sha(later))
    assert not (workspace / "source-checkpoint.json").exists()
    bound = Workbench(workspace, checkpoint=first, checkpoint_sha256=checkpoint.sha(first))
    assert Workbench(workspace).manifest == bound.manifest


@pytest.mark.parametrize("second_base", [None, "different"])
def test_legacy_mixed_or_missing_job_bases_cannot_bind(tmp_path, synthetic_intakes, second_base):
    first, later, _ = synthetic_intakes
    workspace = tmp_path / "legacy"
    for token, base in (("a" * 24, checkpoint.sha(first)),
                        ("b" * 24, checkpoint.sha(later) if second_base else None)):
        directory = workspace / token
        directory.mkdir(parents=True)
        (directory / "job.json").write_text(json.dumps(dict(source_receipt_sha256=base)))
    with pytest.raises(ValueError, match="legacy_job_source_checkpoint_mismatch"):
        Workbench(workspace, checkpoint=first, checkpoint_sha256=checkpoint.sha(first))
    assert not (workspace / "source-checkpoint.json").exists()


@pytest.mark.parametrize("base", [None, "b" * 64])
def test_persisted_job_must_match_workspace_base_before_other_evidence_reads(
    tmp_path, synthetic_intakes, base
):
    workspace = tmp_path / "jobs"
    workbench = Workbench(workspace)
    token = "a" * 24
    (workspace / token).mkdir()
    (workspace / token / "job.json").write_text(json.dumps(dict(source_receipt_sha256=base)))
    with pytest.raises(ValueError, match="job_source_checkpoint_differs_from_workspace_intake"):
        workbench._job(token)


def test_explicit_published_index_is_also_bound_to_its_receipt(
    tmp_path, synthetic_intakes, monkeypatch
):
    import cec_pipeline.workbench as controller

    first, later, _ = synthetic_intakes
    selected = [first]
    monkeypatch.setattr(controller.inspection, "_published", lambda index: (
        selected[0].parent,
        dict(source_receipt=str(selected[0]), source_receipt_sha256=checkpoint.sha(selected[0])),
    ))
    workspace = tmp_path / "jobs"
    Workbench(workspace, index="explicit-index")
    selected[0] = later
    assert Workbench(workspace).manifest["source_receipt"] == str(first)
    with pytest.raises(ValueError, match="workspace_source_checkpoint_changed"):
        Workbench(workspace, index="explicit-index")


def test_checkpoint_identity_cannot_be_supplied_without_its_path(tmp_path, synthetic_intakes):
    with pytest.raises(ValueError, match="checkpoint_sha256_requires_explicit_checkpoint"):
        Workbench(tmp_path / "jobs", checkpoint_sha256="a" * 64)


def test_checklist_worker_reopens_durable_intake_not_current_pin(
    tmp_path, synthetic_intakes, monkeypatch
):
    from cec_pipeline import execution
    from cec_pipeline.identity import code_identity, family

    first, later, pin = synthetic_intakes
    workspace = tmp_path / "jobs"
    Workbench(workspace)
    source = tmp_path / "synthetic-source.fixture"
    source.write_text("not native CAD evidence")
    table = tmp_path / "synthetic-table.fixture"
    table.write_text("not native library evidence")
    token = "a" * 24
    (workspace / token).mkdir()
    job = dict(token=token, source_receipt_sha256=checkpoint.sha(first), source=str(source),
               source_sha256=checkpoint.sha(source), source_family=family(source),
               code_identity=code_identity(), footprint_table=str(table),
               footprint_table_sha256=checkpoint.sha(table), candidate=str(source))
    (workspace / token / "job.json").write_text(json.dumps(job))
    pin(later)
    observations = []

    def run(worker, requested, step):
        assert worker._job(requested)[1] == job
        assert worker.manifest["source_receipt_sha256"] == checkpoint.sha(first)
        observations.append(step)
        return dict(complete=True, result=dict(ok=True, complete=True, ordinary_only=True))

    monkeypatch.setattr(execution, "run", run)
    monkeypatch.setattr(Workbench, "verdict", lambda *args: dict(ok=True))
    execution.validate_worker(workspace / token / "job.json")
    result = json.loads((workspace / token / "validate.json").read_text())
    assert result["ok"] and result["complete"]
    assert observations[0] == "construct"
    assert set(observations[1:]) == set(execution.required_gates(dict(ordinary_only=True)))


@pytest.mark.parametrize("value", [None, [], {}, dict(schema=1, source_receipt="relative")])
def test_malformed_existing_binding_is_never_silently_replaced(
    tmp_path, synthetic_intakes, value
):
    workspace = tmp_path / "jobs"
    workspace.mkdir()
    binding = workspace / "source-checkpoint.json"
    binding.write_text(json.dumps(value))
    original = binding.read_bytes()
    with pytest.raises(ValueError, match="invalid_workspace_source_checkpoint_binding"):
        Workbench(workspace)
    assert binding.read_bytes() == original


def test_portable_export_retains_all_layers_and_crops_not_only_the_last(tmp_path):
    plots = {}
    for face, view in (("F", "a" * 16), ("B", "b" * 16), ("F", "c" * 16)):
        for side in ("before", "after"):
            name = side + "-" + face + "-Cu-" + view + ".svg"
            path = tmp_path / name
            path.write_text("<svg>synthetic distinct " + name + "</svg>")
            plots[name] = dict(path=str(path), sha256=checkpoint.sha(path))
    original = dict(boards=[dict(board="arbitrary", sha256="child")],
                    selected_children=[dict(board="arbitrary", candidate_sha256="child",
                                            reviewed_native_plots=plots)])
    output = tmp_path / "export"
    output.mkdir()
    result = checkpoint.export_reviews(original, output)
    copied = result[0]["reviewed_native_plots"]
    assert set(copied) == set(plots) and len(copied) == 6
    assert result[0]["historical_receiving_not_relabelled_as_current"]
    for key, row in copied.items():
        assert checkpoint.sha(output / row["path"]) == plots[key]["sha256"]
    hostile = copy.deepcopy(original)
    hostile["selected_children"][0]["reviewed_native_plots"] = {"../escape": next(iter(plots.values()))}
    with pytest.raises(ValueError, match="exact_native_review_plot_required"):
        checkpoint.export_reviews(hostile, output)
