"""Longer construction work does not change measurement authority or defaults."""
import math
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_isolated_measurement_completion as op
from test_isolated_measurement_completion import case, child, refused


def long_case(tmp_path, monkeypatch, quarter=0):
    source, uid, target = case(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(source))
    pad = next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==target)
    pad.Move(pcbnew.VECTOR2I_MM(16,0))
    for track in board.GetTracks():
        track.Move(pcbnew.VECTOR2I_MM(16,0))
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pivot,angle)
    field._save_field_snapshot(board,source)
    return source,uid,target


@pytest.mark.parametrize('quarter',range(4))
def test_long_real_saved_chain_needs_explicit_matching_work_tier(tmp_path,monkeypatch,quarter):
    source,uid,target=long_case(tmp_path,monkeypatch,quarter)
    candidate=child(source,tmp_path,uid,target)
    original=[p.read_bytes() for p in (source,candidate)]
    default=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid)
    assert not default['complete'] and not default['ok'],default
    received=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,
        path_length_budget_nm=32000000)
    assert received['complete'] and received['ok'],received
    assert received['construction_work_limits']==dict(maximum_tracks=16,
        maximum_path_length_nm=32000000,electrical_length_qualified=False)
    assert received['source_components']>received['candidate_components']
    assert not received['current_authority'] and not received['kelvin_qualified']
    assert original==[p.read_bytes() for p in (source,candidate)]


def test_explicit_constructor_searches_and_receives_same_finite_long_tier(tmp_path,monkeypatch):
    source,uid,target=long_case(tmp_path,monkeypatch)
    proposal=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='RENAMED_SOURCE',
        pad_uuid=uid,path_length_budget_nm=32000000)
    candidate=force._copy_family(source,tmp_path/'constructed')
    result=op.construct_private(source,candidate,proposal,board_hint='RENAMED_SOURCE',
        path_length_budget_nm=32000000)
    assert result['complete'],result
    assert 24000000<sum(math.dist(o[1],o[2]) for o in result['ops'])<=32000000
    received=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,
        path_length_budget_nm=32000000)
    assert received['complete'] and received['ok'],received


def test_forged_proposal_cannot_select_larger_constructor_tier(tmp_path,monkeypatch):
    import cec_measurement_terminal_route as terminal
    source,uid,target=long_case(tmp_path,monkeypatch)
    proposal=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='RENAMED_SOURCE',
        pad_uuid=uid,path_length_budget_nm=32000000)
    proposal['construction_work_limits']['maximum_path_length_nm']=10**12
    candidate=force._copy_family(source,tmp_path/'not_saved');before=candidate.read_bytes()
    seen=[]
    def menu(*args,**kwargs):
        seen.append(kwargs['max_length_nm']);return {'ops':[]}
    monkeypatch.setattr(terminal,'menus',menu)
    result=op.construct_private(source,candidate,proposal,board_hint='RENAMED_SOURCE')
    assert not result['complete'] and seen==[24000000]
    assert candidate.read_bytes()==before


@pytest.mark.parametrize('bad',[True,False,None,0,-1,24000000.,32000000.,
    '32000000',32000001,64000000,float('inf'),float('nan')])
def test_only_enumerated_integer_work_limits_are_accepted(bad):
    with pytest.raises(ValueError,match='explicit_finite_measurement'):
        op.path_length_work_limit(bad)


@pytest.mark.parametrize('fault',['thin','wrong_width','wide','wrong_target','force_contact',
    'noncanonical','missing_join','source_cut','source_pin','moved_owner','wrong_net',
    'via','orphan','back_track','new_group','no_new_route'])
def test_longer_work_tier_retains_every_saved_scope_refusal(tmp_path,monkeypatch,fault):
    source,uid,target=long_case(tmp_path,monkeypatch)
    candidate=child(source,tmp_path,uid,target,fault)
    refused(lambda:op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid,
        path_length_budget_nm=32000000))


@pytest.mark.parametrize('tier',[24000000,32000000])
def test_transaction_work_limit_is_explicit_finite_not_geometry_authority(tier):
    import root_receive_local_transaction_20261022 as transaction
    row=dict(kind='isolated_measurement_join',candidate='/private/child.kicad_pcb',
        candidate_sha256='a'*64,pad_uuid='Source-input',path_length_budget_nm=tier)
    assert transaction.validate_phases([row])==['isolated_measurement_join']
    for key,value in [('width_nm',100000),('current',.01),('permitted_layers',[2]),
                      ('timeout_s',30),('ops',[]),('path_length_budget_nm',64000000)]:
        with pytest.raises(ValueError):transaction.validate_phases([dict(row,**{key:value})])


def test_transaction_rederives_the_same_explicit_tier_on_actual_saved_files(tmp_path,monkeypatch):
    import root_receive_local_transaction_20261022 as transaction
    source,uid,target=long_case(tmp_path,monkeypatch)
    candidate=child(source,tmp_path,uid,target)
    row=dict(kind='isolated_measurement_join',candidate=str(candidate),
        candidate_sha256=force._hash(candidate),pad_uuid=uid,path_length_budget_nm=32000000)
    assert transaction.validate_phases([row])==['isolated_measurement_join']
    actual,proof=transaction.receive_phase(source,source,row,'RENAMED_SOURCE')
    assert actual==candidate and proof['ok'] and proof['complete'],proof
    assert proof['construction_work_limits']['maximum_path_length_nm']==32000000
    del row['path_length_budget_nm']
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,row,'RENAMED_SOURCE')
