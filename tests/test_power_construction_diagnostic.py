"""Construction diagnosis is board-neutral and cannot grant admission."""
import copy
from types import SimpleNamespace
from unittest import mock
import pytest
import cec_full_pipeline as pipeline
import cec_power_failure as failure


def blocked(ref='ARBITRARY_OWNER'):
    return dict(ok=False, errors=[], force_rail=dict(schema=1, applicable=True,
        ok=False, total=4, laid=1, refused={ref: 'native obstacle'}))


def eligible(craft=None, **changes):
    options=dict(physical_gates=[True]*5, requires_authority=True, routed=False)
    options.update(changes)
    return failure.construction_probe_eligible(craft or blocked(),
        dict(ok=False, blockers=['force_rail placement evidence failed']), **options)


@pytest.mark.parametrize('ref', ['UNRELATED', 'RENAMED_OWNER', 'OTHER_PART'])
def test_only_typed_construction_failure_schedules_private_probe(ref):
    assert eligible(blocked(ref))


@pytest.mark.parametrize('changes', [dict(routed=True), dict(requires_authority=False),
    dict(physical_gates=[True, False]), dict(physical_gates=[]),
    dict(physical_gates=[True, None]), dict(physical_gates=[1])])
def test_other_gate_failures_and_routed_boards_are_not_probed(changes):
    assert not eligible(**changes)


@pytest.mark.parametrize('change', [dict(error='missing'), dict(total=0), dict(laid=4),
    dict(laid=-1), dict(laid=True), dict(schema=2), dict(refused={}), dict(ok=True)])
def test_invalid_or_stale_evidence_is_not_a_plan(change):
    craft=blocked(); craft['force_rail'].update(change)
    assert not eligible(craft)


def test_other_craft_failure_is_not_hidden():
    assert not failure.construction_probe_eligible(blocked(),
        dict(ok=False, blockers=['force_rail placement evidence failed',
                                'native_geometry placement evidence failed']),
        requires_authority=True, physical_gates=[True], routed=False)


@pytest.mark.parametrize('mode', ['pass', 'refuse', 'raise', 'source_changed'])
def test_probe_never_admits_or_mutates_source_recipe(tmp_path, mode):
    board=tmp_path/'input.kicad_pcb'; board.write_text('incumbent')
    cfg=SimpleNamespace(params={'approved_current': 23.7})
    original=copy.deepcopy(cfg.params)
    def construct(private_cfg, candidate, **options):
        assert candidate != board and candidate.parent != board.parent
        assert private_cfg.params['priority_operation_timeout_s']==120
        private_cfg.params['approved_current']=999
        candidate.write_text('private constructed geometry')
        if mode=='source_changed': board.write_text('external change')
        if mode=='raise': raise RuntimeError('incomplete worker')
        return dict(ok=mode=='pass', state=str(candidate.with_suffix('.json')))
    with mock.patch.object(pipeline, '_placement_authority_family', return_value=[board]), \
         mock.patch.object(pipeline, '_copy_sidecars',
             side_effect=lambda source,target: target.write_bytes(source.read_bytes())), \
         mock.patch.object(pipeline, '_ensure_placement_route_authority', side_effect=construct):
        result=pipeline._diagnose_power_construction(cfg, board)
    assert result['release_authority'] is False and result['route_admission'] is False
    assert cfg.params==original
    assert result['exact_power_ok'] is (mode=='pass')
    if mode=='source_changed':
        assert result['reason']=='diagnostic_input_family_changed'
    else:
        assert board.read_text()=='incumbent' and result['input_families_unchanged']
