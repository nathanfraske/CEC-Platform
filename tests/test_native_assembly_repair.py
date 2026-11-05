"""Native assembly truth must survive placement craft and repair boundaries."""
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_placement_geometry as geo
import cec_synth_pipeline as synth


def projection(pairs=()):
    return dict(schema=2, domains=['assembly', 'pad_copper', 'pad_edge'],
        ok=not pairs, error=None, violations=[dict(domain='assembly',
        type='courtyards_overlap', members=[dict(ref=a), dict(ref=b)])
        for a,b in pairs])


def test_native_assembly_owners_are_resolved_by_uuid_not_description():
    row=dict(type='pth_inside_courtyard', items=[
        dict(uuid='pad-id', description='localized pad label'),
        dict(uuid='footprint-id', description='localized footprint label')])
    report=geo.classify_drc(dict(violations=[row]),
        {'pad-id':dict(ref='contact',pad='1',net='RETURN')},
        footprint_ids={'footprint-id':dict(ref='neighbor')})
    native=geo.craft_projection(dict(report, source_unchanged=True))
    assert not native['ok'] and not native['error']
    assert geo.assembly_pairs(native)=={('contact','neighbor')}
    assert native['violations'][0]['members'][0]['net']=='RETURN'
    assert not geo.clearance_move_specs(native, {'contact':(0,0,0),'neighbor':(2,0,0)})


def test_missing_assembly_identity_fails_closed_and_legacy_is_not_clean():
    report=geo.classify_drc(dict(violations=[dict(type='courtyards_overlap',
        items=[dict(uuid='x'),dict(uuid='y')])]), {})
    native=geo.craft_projection(dict(report,source_unchanged=True))
    assert native['error']=='native_assembly_identity_unavailable'
    assert geo.assembly_pairs(native) is None
    assert geo.assembly_pairs(dict(schema=1,ok=True,violations=[])) is None
    assert geo.assembly_count(dict(schema=1,ok=True,violations=[]),3)==3


def test_physical_key_and_certificate_do_not_promote_aabb_false_positives():
    evidence=dict(ok=True,native_geometry=projection())
    assert synth.placement_craft_repair_key(evidence,overlap_count=1)[0]==0
    certificate=synth.placement_craft_blocker_certificate(evidence,dict(baseline_overlap=1))
    assert certificate['overlap_count']==0
    assert 'courtyard_separation' not in certificate['required_stages']
    evidence=dict(ok=False,native_geometry=projection([('body','nearby')]))
    certificate=synth.placement_craft_blocker_certificate(evidence)
    assert certificate['overlap_count']==1
    assert 'courtyard_separation' in certificate['required_stages']
    assert 'native_pad_clearance' not in certificate['required_stages']


@pytest.mark.parametrize('old,new,accepted',[
    ([],[('A','B')],False),
    ([('A','B')],[('B','C')],False),  # same count is not same fault
    ([('A','B')],[],True),
    ([('A','B')],[('A','B')],True),
])
def test_worker_vetoes_new_assembly_fault_even_if_electrical_score_improves(old,new,accepted):
    candidate=SimpleNamespace()
    with mock.patch.object(synth,'materialize'), \
         mock.patch.object(synth,'placement_craft_evidence',return_value=dict(
             ok=not new,native_geometry=projection(new))):
        result=synth._placement_craft_trial_worker(dict(candidate=candidate,
            cfg=None,path='synthetic',baseline_geometry=projection(old)))
    assert result['ok'] is accepted
    if not accepted:
        assert result['error_kind']=='native_geometry_regression'
        assert result['introduced_native_conflicts']


def fixture_board(path, *, shifted=False, back=False):
    import cec_swig_guard; cec_swig_guard.pin()
    import pcbnew
    board=pcbnew.CreateEmptyBoard()
    edge=[(0,0),(20,0),(20,20),(0,20),(0,0)]
    for a,b in zip(edge,edge[1:]):
        item=pcbnew.PCB_SHAPE()
        item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b))
        item.SetWidth(pcbnew.FromMM(.05));board.Add(item)
    square=[(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5),(-.5,-.5)]
    for ref,origin,shape in (
        ('BLOCK',(5,5),[(0,0),(5,0),(5,1),(1,1),(1,5),(0,5),(0,0)]),
        ('MOVING',(8,10.8 if shifted else 8),square),
        ('NEIGHBOR',(8,11),square)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*origin))
        for a,b in zip(shape,shape[1:]):
            item=pcbnew.PCB_SHAPE(fp)
            item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(pcbnew.F_CrtYd)
            item.SetStart(pcbnew.VECTOR2I_MM(a[0]+origin[0],a[1]+origin[1]))
            item.SetEnd(pcbnew.VECTOR2I_MM(b[0]+origin[0],b[1]+origin[1]))
            item.SetWidth(pcbnew.FromMM(.05));fp.Add(item)
        board.Add(fp)
        if ref=='NEIGHBOR' and back:fp.Flip(fp.GetPosition(),False)
    pcbnew.SaveBoard(str(path),board)


def test_native_concave_fixture_catches_real_collision_but_not_empty_notch(tmp_path):
    before=tmp_path/'before.kicad_pcb';after=tmp_path/'after.kicad_pcb'
    fixture_board(before);fixture_board(after,shifted=True)
    first=geo.craft_projection(geo.evaluate(before))
    second=geo.craft_projection(geo.evaluate(after))
    assert first['ok'] and geo.assembly_pairs(first)==set()
    assert not second['ok']
    assert geo.assembly_pairs(second)=={('MOVING','NEIGHBOR')}
    assert geo.craft_conflict_keys(second)-geo.craft_conflict_keys(first)
    assert synth.placement_craft_repair_key(dict(native_geometry=first),1)[0]==0
    assert synth.placement_craft_repair_key(dict(native_geometry=second),1)[0]==1


def test_native_assembly_coverage_respects_opposite_board_faces(tmp_path):
    path=tmp_path/'opposite.kicad_pcb'
    fixture_board(path,shifted=True,back=True)
    native=geo.craft_projection(geo.evaluate(path))
    assert native['ok'] and geo.assembly_pairs(native)==set()
