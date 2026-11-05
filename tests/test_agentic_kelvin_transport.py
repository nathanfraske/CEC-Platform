"""Bounded transport cannot turn missing or stale native shards into proof."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from cec_pipeline import kelvin
import cec_force_sense_shards as shards
from test_force_sense_shards import bundle


def transport(monkeypatch, bundle, *, fault=None):
    lock = threading.Lock()
    state = dict(active=0, peak=0, calls=[])
    monkeypatch.setattr(shards, "manifest", lambda *a, **kw: deepcopy(bundle["prepared"]))

    def run(command, **kwargs):
        assert 0 < kwargs["timeout"] <= 9.7
        assert kwargs["stdin"] is subprocess.DEVNULL
        stage = command[2]
        arg = lambda name: command[command.index(name) + 1]
        output = Path(arg("--out"))
        assert 0 < float(arg("--timeout-s")) <= 9.1
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            state["calls"].append((stage, output.name))
        try:
            time.sleep(.005)
            if stage == "manifest":
                report = deepcopy(bundle["prepared"])
            elif stage == "legacy":
                report = deepcopy(bundle["legacy"])
            elif stage == "leg":
                if fault == "timeout":
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                if fault == "crash":
                    return SimpleNamespace(returncode=1, stderr="native_worker_failed")
                if fault == "missing":
                    return SimpleNamespace(returncode=0, stderr="")
                report = deepcopy(next(row for row in bundle["legs"]
                                  if row["shard_selector"] == ["leg", arg("--input-ref"), arg("--leg")]))
                if fault == "incomplete":
                    report["shard_complete"] = False
                elif fault == "changed_source":
                    report["source"] += "changed"
                elif fault == "duplicate_leg":
                    report = deepcopy(bundle["legs"][0])
            else:
                assert stage == "assemble"
                read = lambda file: json.loads(Path(file).read_text())
                reports = [read(command[i + 1]) for i, x in enumerate(command) if x == "--leg-report"]
                report = shards.assemble(bundle["path"], read(arg("--manifest")), reports,
                                         read(arg("--legacy-report")), board_hint="fixture")
            output.write_text(json.dumps(report))
            return SimpleNamespace(returncode=0, stderr="")
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(kelvin.subprocess, "run", run)
    return state


def test_parallel_transport_keeps_native_full_denominator_and_join(bundle, tmp_path, monkeypatch):
    import cec_force_sense_evidence as evidence
    state = transport(monkeypatch, bundle)
    reports = kelvin.replay_pair(bundle["path"], bundle["path"], board_hint="fixture",
                                 evidence_dir=tmp_path / "evidence")
    assert state["peak"] == 2 and state["active"] == 0
    assert len(state["calls"]) == 2 * (len(bundle["legs"]) + 3)
    for report in reports:
        proof = evidence.compare_contact_preservation(bundle["ordinary"], report)
        assert proof["comparison_complete"] and proof["same_evidence"], proof
        assert report["sharded_replay"]["physical_legs"] == 4
        assert report["sharded_replay"]["legacy_observations"] == 1
        assert not report["electrical_rating_qualified"] and not report["release_authority"]
    assert len(list((tmp_path / "evidence").glob("*-joined.json"))) == 2


@pytest.mark.parametrize("fault", ["timeout", "crash", "missing", "incomplete",
                                    "changed_source", "duplicate_leg"])
def test_no_partial_or_wrong_identity_transport_acceptance(bundle, tmp_path, monkeypatch, fault):
    state = transport(monkeypatch, bundle, fault=fault)
    with pytest.raises(ValueError):
        kelvin.replay_pair(bundle["path"], bundle["path"], board_hint="fixture",
                           evidence_dir=tmp_path / "evidence")
    assert state["active"] == 0 and state["peak"] <= 2
    assert not list((tmp_path / "evidence").glob("*-joined.json"))


def test_pair_deadline_does_not_start_unbounded_constituents(bundle, tmp_path, monkeypatch):
    state = transport(monkeypatch, bundle)
    monkeypatch.setattr(kelvin, "PAIR_SECONDS", .5)
    with pytest.raises(ValueError, match="checklist_deadline"):
        kelvin.replay_pair(bundle["path"], bundle["path"], board_hint="fixture",
                           evidence_dir=tmp_path / "evidence")
    assert not state["calls"]


def test_existing_evidence_directory_is_not_reused(bundle, tmp_path):
    with pytest.raises(FileExistsError):
        kelvin.replay_pair(bundle["path"], bundle["path"], board_hint="fixture", evidence_dir=tmp_path)


@pytest.mark.parametrize("mutation", ["source", "candidate", "code", "none"])
def test_pair_epoch_spans_replay_and_later_native_comparison(bundle, monkeypatch, mutation):
    from cec_pipeline import safety
    import cec_force_current as force
    import cec_force_sense_evidence as evidence
    families = [{"exact": "source"}, {"exact": "candidate"}]
    epoch = {"code": "exact"}
    # Transport receives real joined native evidence; control only the epoch
    # race around the subsequent independent native comparison.
    monkeypatch.setattr(safety, "_kelvin_noninterference", lambda *a, **kw: None)
    calls = [0]
    def family(*a, **kw):
        i = calls[0] % 2
        calls[0] += 1
        return dict(families[i])
    monkeypatch.setattr(force, "_family", family)
    monkeypatch.setattr(force, "_code_identity", lambda: dict(epoch))
    reports = [deepcopy(bundle["joined"]), deepcopy(bundle["joined"])]
    for i, report in enumerate(reports):
        report.update(source_family_before=dict(families[i]), source_family_after=dict(families[i]),
                      code_before=dict(epoch), code_after=dict(epoch))
    monkeypatch.setattr(kelvin, "replay_pair", lambda *a, **kw: reports)
    def compare(*a, **kw):
        if mutation == "source":
            families[0]["exact"] = "changed-after-replay"
        elif mutation == "candidate":
            families[1]["exact"] = "changed-after-replay"
        elif mutation == "code":
            epoch["code"] = "changed-after-replay"
        return dict(comparison_complete=True, same_evidence=True)
    monkeypatch.setattr(evidence, "compare_contact_preservation", compare)
    if mutation == "none":
        result = safety.kelvin_pair(bundle["path"], bundle["path"], board_hint="fixture")
        assert result["ok"] and result["complete"] and not result["full_kelvin_qualification"]
    else:
        with pytest.raises(ValueError, match="comparison_epoch_changed"):
            safety.kelvin_pair(bundle["path"], bundle["path"], board_hint="fixture")
