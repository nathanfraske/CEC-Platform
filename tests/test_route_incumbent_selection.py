"""Keep equally closed incumbent copper without bypassing physical authority."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_full_pipeline as pipeline
import cec_search_policy as policy
from route_candidate_test_support import run_candidate_in_process


def grade(path, *, origin="proposal", vias=7, length=30., opens=4, seed=0):
    return dict(routed=str(path), gate=False, sort_key=[1, 0, 0, 0, 0, opens, 1e6],
        drc=0, unconnected=opens, unconn_critical=[], vias=vias, length=length,
        gate_terms={"routing_complete": False, "pairs_ok": True}, seed=seed,
        candidate_origin=origin, blocker_summary={"blocking_count": opens})


@pytest.mark.parametrize("delta", [(1, 0), (0, 2.6), (0, 0)])
@pytest.mark.parametrize("seed", [0, 41, 9001])
def test_equal_closure_never_buys_more_copper_or_replaces_exact_tie(delta, seed):
    baseline = grade("original", origin="incumbent", seed=seed)
    trial = grade("trial", vias=7 + delta[0], length=30 + delta[1])
    assert policy.select_candidate([trial, baseline]) == baseline
    assert policy.select_candidate([baseline, trial]) == baseline


def test_real_connectivity_gain_precedes_copper_and_seed():
    baseline = grade("original", origin="incumbent")
    trial = grade("trial", vias=90, length=900, opens=3, seed=500)
    assert policy.select_candidate([baseline, trial]) == trial


@pytest.mark.parametrize("missing", [False, True])
def test_fewer_opens_cannot_trade_away_an_incumbent_gate(missing):
    baseline = grade("original", origin="incumbent")
    trial = grade("trial", opens=0)
    if missing:
        trial["gate_terms"].pop("pairs_ok")
    else:
        trial["gate_terms"]["pairs_ok"] = False
    assert policy.incumbent_gate_regressions(trial, baseline) == ["pairs_ok"]
    assert policy.select_candidate([trial, baseline]) == baseline


def test_gate_clean_improvement_precedes_copper_cost():
    baseline = grade("original", origin="incumbent")
    trial = grade("trial", vias=100, length=1000, opens=0)
    trial.update(gate=True, sort_key=[0, 20, 100, 0, 1000, 0])
    trial["gate_terms"]["routing_complete"] = True
    assert policy.select_candidate([baseline, trial]) == trial


@pytest.mark.parametrize("field", ["sort_key", "unconn_critical", "drc", "blocker_summary"])
def test_safety_and_fault_counts_precede_copper(field):
    baseline = grade("original", origin="incumbent", vias=100, length=1000)
    trial = grade("trial", vias=0, length=0)
    trial[field] = {"sort_key": [1, 1, 0, 0, 0, 4, 1e6],
        "unconn_critical": ["/RENAMED_CRITICAL"], "drc": 1,
        "blocker_summary": {"blocking_count": 5}}[field]
    assert policy.select_candidate([trial, baseline]) == baseline


@pytest.mark.parametrize("invalid", [None, -1, float("nan"), float("inf"), "unknown"])
@pytest.mark.parametrize("field", ["vias", "length"])
def test_unknown_copper_is_not_zero_cost(field, invalid):
    baseline = grade("original", origin="incumbent")
    trial = grade("trial")
    trial[field] = invalid
    assert policy.select_candidate([trial, baseline]) == baseline


def fixture(tmp_path, *, tracks=True):
    source = tmp_path / "source.kicad_pcb"
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, "/ARBITRARY_SIGNAL", 1)
    board.Add(net)
    if tracks:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(1000000, 2000000))
        track.SetEnd(pcbnew.VECTOR2I(8000000, 2000000))
        track.SetWidth(200000)
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(net)
        board.Add(track)
    pcbnew.SaveBoard(str(source), board)
    source.with_suffix(".kicad_dru").write_text("(version 1)\n")
    cfg = SimpleNamespace(board="neutral-case", dir=str(tmp_path),
        params={"automatic_pin_escape_tier": True})
    return source, cfg


def test_unrouted_native_input_not_mislabelled_as_route(tmp_path):
    import cec_synth_pipeline as synth
    source, cfg = fixture(tmp_path, tracks=False)
    with mock.patch.object(synth, "route_oracle_grade") as oracle:
        assert pipeline._grade_route_incumbent(source, tmp_path / "work", cfg,
                                               seed=4, thermal="lazy") is None
    oracle.assert_not_called()


@pytest.mark.parametrize("mutation", ["board", "sidecar", "source", "none"])
def test_native_incumbent_immutable_full_family(tmp_path, mutation):
    import cec_synth_pipeline as synth
    source, cfg = fixture(tmp_path)
    before = source.read_bytes()

    def oracle(path, **kwargs):
        assert kwargs["route"] is False and kwargs["craft_gates"] is True
        assert kwargs["cfg"] is cfg and kwargs["precision"] is True
        target = Path(path)
        if mutation == "board":
            target.write_text("changed")
        elif mutation == "sidecar":
            target.with_suffix(".kicad_dru").write_text("changed rules")
        elif mutation == "source":
            source.write_text("concurrent change")
        return grade(path)

    with mock.patch.object(synth, "route_oracle_grade", side_effect=oracle):
        if mutation != "none":
            with pytest.raises(pipeline.PipelineBlocked, match="changed"):
                pipeline._grade_route_incumbent(source, tmp_path / "work", cfg,
                                                seed=4, thermal="lazy")
        else:
            result = pipeline._grade_route_incumbent(source, tmp_path / "work", cfg,
                                                     seed=4, thermal="lazy")
            assert result["candidate_origin"] == "incumbent"
            assert Path(result["routed"]).read_bytes() == before
            assert source.read_bytes() == before
            assert result["incumbent_identity"]["read_only"]


@pytest.mark.parametrize("fault", ["wrong_artifact", "no_rank", "error", "no_terms"])
def test_missing_or_unbound_grade_cannot_drop_incumbent_silently(tmp_path, fault):
    import cec_synth_pipeline as synth
    source, cfg = fixture(tmp_path)

    def oracle(path, **kwargs):
        result = grade(path)
        if fault == "wrong_artifact": result["routed"] = str(source)
        if fault == "no_rank": result.pop("sort_key")
        if fault == "error": result["error"] = "grading failed"
        if fault == "no_terms": result.pop("gate_terms")
        return result

    with mock.patch.object(synth, "route_oracle_grade", side_effect=oracle):
        with pytest.raises(pipeline.PipelineBlocked, match="grading failed"):
            pipeline._grade_route_incumbent(source, tmp_path / "work", cfg,
                                            seed=4, thermal="lazy")


@pytest.mark.parametrize("candidates", [1, 3])
@pytest.mark.parametrize("proposal", ["worse", "failed", "improved", "source_changed"])
@mock.patch('cec_route_checkpoint.preservation', new=lambda *a, **k: {'ok': True})
@mock.patch('cec_operation_budget.run', new=run_candidate_in_process)
def test_canonical_route_coordinator_keeps_or_improves_real_input(tmp_path, proposal, candidates):
    import cec_synth_pipeline as synth
    import cec_fab_repair
    import cec_dimension_repair
    source, cfg = fixture(tmp_path)
    before = source.read_bytes()
    calls = []

    def oracle(path, **kwargs):
        calls.append(kwargs)
        if kwargs.get("route") is False:
            return grade(path)
        if proposal == "failed":
            return dict(gate=False, routed=None, error="no legal route")
        target = tmp_path / "proposal.kicad_pcb"
        target.write_bytes(before + b"\n")
        if proposal == "source_changed":
            source.write_bytes(before + b"\n")
        return grade(target, vias=8, length=33, seed=kwargs['seed'],
                     opens=3 if proposal == "improved" else 4)

    def replay_cohort(pool, payloads, workers, *, results, **kwargs):
        for payload in payloads:
            results.append(oracle(payload["board"], seed=payload["seed"]))

    with mock.patch.object(synth, "route_oracle_grade", side_effect=oracle), \
            mock.patch.object(pipeline, "_route_candidate_cohorts", side_effect=replay_cohort), \
            mock.patch.object(cec_fab_repair, "repair_admitted", return_value={}) as polish, \
            mock.patch.object(cec_dimension_repair, "repair_admitted", return_value={}) as dimension:
        if proposal == "source_changed":
            with pytest.raises(pipeline.PipelineBlocked, match="identity changed"):
                pipeline._route_stage(source, tmp_path / "work", cfg,
                    passes=1, opt=1, seed=22, timeout=1, thermal="lazy", candidates=candidates)
            return
        result = pipeline._route_stage(source, tmp_path / "work", cfg,
            passes=1, opt=1, seed=22, timeout=1, thermal="lazy", candidates=candidates)
    assert len(calls) == candidates + 1 and calls[0]["route"] is False
    assert source.read_bytes() == before
    summary = json.loads(Path(result["candidate_summary"]).read_text())
    assert summary["requested"] == candidates and len(summary["candidates"]) == candidates + 1
    assert result["candidate_budget"] == candidates and not result["gate"]
    assert not summary["candidates"][-1]["gate"]
    if proposal != "improved":
        assert result["winner_origin"] == "incumbent"
        assert Path(result["board"]).read_bytes() == before
        assert Path(result["board"]) != source
        assert Path(result["board"]).with_suffix(".kicad_dru").is_file()
        polish.assert_called_once()
        dimension.assert_called_once()
        assert result["incumbent_finish_admission"]["reason"] == "incumbent_finish_unchanged"
    else:
        assert result["winner_origin"] == "proposal" and result["unconnected"] == 3
        polish.assert_called_once()
        dimension.assert_called_once()


@pytest.mark.parametrize("outcome", ["improves", "worsens", "exception", "gate_loss"])
@mock.patch('cec_route_checkpoint.preservation', new=lambda *a, **k: {'ok': True})
@mock.patch('cec_operation_budget.run', new=run_candidate_in_process)
def test_retained_incumbent_can_still_receive_verified_finishing(tmp_path, outcome):
    import cec_synth_pipeline as synth
    import cec_fab_repair
    import cec_dimension_repair
    source, cfg = fixture(tmp_path)
    before = source.read_bytes()

    def oracle(path, **kwargs):
        if kwargs.get("route") is not False:
            return dict(gate=False, routed=None, error="router refused")
        if "finish-comparison" not in str(path):
            return grade(path)
        if outcome == "exception":
            raise RuntimeError("test grade failure")
        result = grade(path, length=25 if outcome in ("improves", "gate_loss") else 35)
        if outcome == "gate_loss":
            result["gate_terms"]["pairs_ok"] = False
        return result

    def finish(path):
        target = Path(path)
        target.write_bytes(target.read_bytes() + b"\n")
        return dict(adopted=True)

    with mock.patch.object(synth, "route_oracle_grade", side_effect=oracle), \
            mock.patch.object(cec_fab_repair, "repair_admitted", side_effect=finish), \
            mock.patch.object(cec_dimension_repair, "repair_admitted", return_value={}):
        result = pipeline._route_stage(source, tmp_path / "work", cfg,
            passes=1, opt=1, seed=22, timeout=1, thermal="lazy")
    assert source.read_bytes() == before
    receipt = result["incumbent_finish_admission"]
    assert receipt["changed"] and receipt["admitted"] == (outcome == "improves")
    if outcome == "improves":
        assert result["winner_origin"] == "incumbent_polish"
        assert Path(result["board"]).read_bytes() == before + b"\n"
    else:
        assert result["winner_origin"] == "incumbent"
        assert Path(result["board"]).read_bytes() == before


@pytest.mark.parametrize('failure_at', ['returned_candidate', 'finishing'])
@mock.patch('cec_operation_budget.run', new=run_candidate_in_process)
def test_normal_proposals_cannot_bypass_continuation_ownership(tmp_path, monkeypatch, failure_at):
    import cec_synth_pipeline as synth
    import cec_route_checkpoint as checkpoint
    import cec_fab_repair, cec_dimension_repair
    source, cfg = fixture(tmp_path)
    before = source.read_bytes()
    trial = tmp_path / 'proposal.kicad_pcb'
    trial.write_bytes(before + b'\n')
    def oracle(path, **kwargs):
        if kwargs.get('route') is False:
            return grade(path)
        return grade(trial, opens=3, seed=kwargs['seed'])
    calls = []
    def preserve(parent, child, _cfg):
        calls.append((str(parent), str(child)))
        return {'ok': failure_at == 'finishing' and len(calls) == 1}
    def polish(path):
        path = Path(path)
        path.write_bytes(path.read_bytes() + b'\n')
        return {'adopted': True}
    monkeypatch.setattr(synth, 'route_oracle_grade', oracle)
    monkeypatch.setattr(checkpoint, 'preservation', preserve)
    monkeypatch.setattr(cec_dimension_repair, 'repair_admitted', lambda *a, **k: {})
    monkeypatch.setattr(cec_fab_repair, 'repair_admitted', polish)
    result = pipeline._route_stage(source, tmp_path / 'work', cfg,
        passes=1, opt=1, seed=4, timeout=1, thermal='lazy')
    assert source.read_bytes() == before
    if failure_at == 'returned_candidate':
        assert result['winner_origin'] == 'incumbent'
        assert result['unconnected'] == 4
        assert Path(result['board']).read_bytes() == before
    else:
        assert result['winner_origin'] == 'proposal'
        assert result['unconnected'] == 3
        assert Path(result['board']).read_bytes() == before + b'\n'
        assert result['incumbent_finish_admission']['baseline_origin'] == 'proposal'
        assert not result['incumbent_finish_admission']['admitted']
