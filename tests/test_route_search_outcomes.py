"""Durable outcome hints change scheduling, never native placement authority."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import cec_certificate_repair as repair
import cec_full_pipeline as pipeline
import cec_final_residual as residual
import cec_synth_pipeline as synth
import cec_operation_budget as budget
from test_route_residual_resume import grade


def attempt(net, *, kind='timeout', variant=0):
    return dict(stage='atomic_negotiation', window={'net': net}, variant=variant,
        decision={'timeout': 'blocked_net_search_timeout', 'refusal': 'blocked_net_still_refused',
                  'close': 'support_restoration_refused', 'startup': 'worker_error'}[kind],
        phases={'close': {'completion': dict(closed=1 if kind=='close' else 0,
                                           timed_out=kind=='timeout')}} if kind!='startup' else {})


@pytest.mark.parametrize('net,ref', [('/RAIL_A','R8'), ('/UNRELATED_NAME','C912')])
def test_timeout_survives_compact_round_trip_and_only_reorders_matching_support(net, ref):
    raw = [attempt(net)]
    history = repair.route_search_history({}, raw)
    payload = json.loads(json.dumps({'route_search_history': history}))
    fresh = dict(targets=[dict(ref=ref, target_net=net), dict(ref='other', target_net='/NEW')])
    windows = dict(windows=[dict(net=net, priority=[0]), dict(net='/NEW', priority=[1])])
    original = copy.deepcopy((fresh, windows, payload))
    schedule = repair._support_relocation_schedule(fresh, windows, payload)
    assert schedule['eligible'] == [fresh['targets'][0]]
    assert schedule['deferred'] == [fresh['targets'][1]]
    assert not schedule['release_authority'] and not schedule['exhaustion_is_no_path_proof']
    assert (fresh, windows, payload) == original
    ordered, report = repair._prioritize_windows_by_proven_close(windows['windows'], payload)
    assert ordered == list(reversed(windows['windows']))
    assert report['timed_out_nets'] == [net]
    assert repair.route_search_history(payload)['negotiation_outcomes'] == history['negotiation_outcomes']


def test_proven_close_survives_and_dominates_old_timeout_without_dropping_windows():
    first = repair.route_search_history({}, [attempt('/A')])
    second = repair.route_search_history({'route_search_history': first}, [attempt('/A',kind='close')])
    windows = [dict(net=net, priority=[i]) for i, net in enumerate(('/NEW','/A','/A'))]
    rows, evidence = repair._prioritize_windows_by_proven_close(windows, {'route_search_history':second})
    assert rows == [windows[1], windows[0], windows[2]]
    assert evidence['proven_close_nets'] == ['/A'] and evidence['timed_out_nets'] == []


@pytest.mark.parametrize('stop,variants,extra,expected', [
    ('no_admissible_negotiation', [0,1], None, ['/A']),
    ('no_admissible_negotiation', [0,0], None, []),
    ('wall_budget', [0,1], None, []),
    ('no_admissible_negotiation', [0,1], 'timeout', []),
    ('no_admissible_negotiation', [0,1], 'startup', []),
])
def test_finite_exhaustion_requires_distinct_completed_topologies(stop, variants, extra, expected):
    rows = [attempt('/A', kind='refusal',variant=v) for v in variants]
    if extra: rows.append(attempt('/A',kind=extra))
    history = repair.route_search_history({}, rows, negotiation_stop=stop)
    restored = repair.route_search_history({'route_search_history': json.loads(json.dumps(history))})
    assert restored['negotiation_outcomes']['exhausted_nets'] == expected


@pytest.mark.parametrize('row', [
    attempt('/A', kind='startup'),
    dict(stage='atomic_negotiation', window={'net':'/A'},decision='blocked_net_search_timeout'),
    dict(stage='atomic_negotiation', window=[], phases={'close':None}),
    dict(stage='atomic_negotiation', window={'net':'/A'}, phases={'close':[]}),
    dict(stage='atomic_negotiation', window={'net':'/A'},
         phases={'close': {'completion': {'closed': '0', 'timed_out': 'false'}}}),
])
def test_malformed_or_unmeasured_attempt_cannot_release_deferral(row):
    history = repair.route_search_history({}, [row])
    assert all(not rows for rows in history['negotiation_outcomes'].values())


@pytest.mark.parametrize('revision', ['obsolete', None])
def test_outdated_outcomes_cannot_override_fresh_search(revision):
    history = repair.route_search_history({}, [attempt('/A')])
    history['algorithm_revision'] = revision
    result = repair.route_search_history({'route_search_history': history})
    assert not result['negotiation_visits']
    assert all(not rows for rows in result['negotiation_outcomes'].values())


def test_outcome_storage_fits_sidecar_reader_even_for_long_unicode_names():
    rows = [attempt(('α'*300) + str(i)) for i in range(400)]
    rows += [dict(stage=stage,net=row['window']['net']) for row in rows[:400]
             for stage in ('broad_canonical_closure','deep_route_portfolio')]
    result = repair.route_search_history({}, rows)
    assert len(json.dumps(result, indent=2).encode()) <= 48*1024
    assert result['storage_truncated']
    assert len(result['negotiation_visits']) <= 256
    assert not result['release_authority']


def test_compact_history_crosses_real_coordinator_writer_and_reader(tmp_path, monkeypatch):
    source = tmp_path/'authored.kicad_pcb'; source.write_text('immutable authored source')
    out = tmp_path/'owned'; out.mkdir()
    selected = out/'board.kicad_pcb'; selected.write_bytes(source.read_bytes())
    cfg = SimpleNamespace(params={'route_residual_resume_rounds':1})
    baseline = grade(selected)
    sampled = []
    def worker(board, completion, *args, **kwargs):
        schedule = repair._support_relocation_schedule(
            {'targets':[dict(ref='X_SUPPORT',target_net='/RENAMED')]},
            {'windows':[dict(net='/RENAMED',priority=[0])]}, completion)
        sampled.append(bool(schedule['eligible']))
        return board, dict(changed=False,
            route_search_history=repair.route_search_history(completion,[attempt('/RENAMED')]))
    monkeypatch.setattr(synth,'_route_oracle_certificate_repair', worker)
    monkeypatch.setattr(residual,'measure',lambda path,**k:dict(unconnected_count=4,
        source_board_sha256=pipeline.sha256_file(path)))
    monkeypatch.setattr(residual,'valid_snapshot',lambda _:True)
    monkeypatch.setattr(budget,'optional_work_admission',lambda *a,**k:dict(start=True))
    _, first = pipeline._resume_route_residuals(baseline,out/'wave-0',cfg,seed=1,thermal='lazy')
    files = pipeline._persist_route_search_history(baseline,first,out)
    assert files == [str(selected.with_suffix('.route-search.json'))]
    saved = Path(files[0]).read_bytes()
    _, second = pipeline._resume_route_residuals(baseline,out/'wave-1',cfg,seed=1,thermal='lazy')
    assert sampled == [False,True]
    assert first['stop'] == second['stop'] == 'no_progress'
    assert not second['changed'] and not second['release_authority']
    assert source.read_bytes() == selected.read_bytes()
    assert Path(files[0]).read_bytes() == saved


def test_history_writer_refuses_external_source_family(tmp_path):
    source = tmp_path/'source.kicad_pcb'; source.write_text('source')
    with pytest.raises(pipeline.PipelineBlocked, match='external board'):
        pipeline._persist_route_search_history(grade(source),
            {'route_search_history':repair.route_search_history({},[attempt('/A')])}, tmp_path/'owned')
    assert not source.with_suffix('.route-search.json').exists()
