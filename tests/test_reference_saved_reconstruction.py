"""Independent fresh expected native material is not a saved success cache."""
import copy
from pathlib import Path

import pcbnew
import pytest

import cec_dense_reference_mapping as dense
import cec_force_current as force
import cec_mask_search_reference_mapping as maps
import cec_reference_map_material_identity as material
from test_reference_map_material_identity import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_material_receiver_consumes_three_real_phases(tmp_path,quarter,back,monkeypatch):
    source,child,path,q,uid,manifest=fixture(tmp_path,quarter=quarter,back=back)
    def combined_forbidden(*args,**kwargs):raise AssertionError('combined receive under one material lease')
    monkeypatch.setattr(maps,'receive',combined_forbidden)
    proof=material.receive(source,child,path,staged_map_replay=True)
    assert proof['ok']and proof['complete']and proof['same_material'],proof
    assert set(proof['timings_s'])=={'map_reconstruct','map_scope','material_live'}
    assert all(0<=v<10. for v in proof['timings_s'].values())
    assert proof['bounded_composition']==dict(map_reconstruct_limit_s=10.,map_scope_limit_s=10.,
        material_live_limit_s=10.,aggregate_limit_s=30.)
    assert proof['map_scope']['source_bound_projection_exact']
    assert proof['map_scope']['manifest']==manifest
    assert not proof['mutation_authority']and not proof['admitted']and not proof['full_kelvin_qualification']


def test_reconstruction_is_private_and_comparison_uses_two_fresh_native_candidate_loads(tmp_path,monkeypatch):
    source,child,path,q,*_=fixture(tmp_path)
    replay=maps._private.saved_replay(source,child,q)
    with pytest.raises(ValueError,match='stage_order'):replay.receive()
    diagnostic=replay.reconstruct()
    assert diagnostic['reconstruction_only']and diagnostic['saved_candidate_received']is False
    assert 'ok'not in diagnostic and 'manifest'not in diagnostic
    actual_load=pcbnew.LoadBoard;loads=[]
    def load(filename,*args,**kwargs):
        loads.append(Path(filename));return actual_load(filename,*args,**kwargs)
    monkeypatch.setattr(pcbnew,'LoadBoard',load)
    def construct_forbidden(*args,**kwargs):raise AssertionError('saved comparison reran construction')
    monkeypatch.setattr(maps._private,'construct',construct_forbidden)
    assert replay.receive()['ok']
    # _nodes additionally native-validates its normalized snapshots. The
    # ACTUAL saved child must still have two independent native loads.
    assert loads.count(child)==2 and source not in loads
    with pytest.raises(ValueError,match='stage_order'):replay.reconstruct()
    with pytest.raises(ValueError,match='stage_order'):replay.receive()


@pytest.mark.parametrize('field',['_expected_tree','_expected_literal','_manifest','_seal'])
def test_retained_expected_material_cannot_be_replaced_by_caller_success(tmp_path,field):
    source,child,path,q,*_=fixture(tmp_path)
    replay=maps._private.saved_replay(source,child,q);replay.reconstruct()
    setattr(replay,field,dict(ok=True,complete=True))
    with pytest.raises(ValueError,match='expected_material_changed'):replay.receive()
    assert replay.observation()['state']=='failed'
    with pytest.raises(TypeError):replay.receive(dict(ok=True,complete=True))


@pytest.mark.parametrize('fault',['source','candidate','grade','report','sidecar','rules','code','native','environment'])
def test_changed_inputs_after_expected_reconstruction_cannot_borrow_it(tmp_path,monkeypatch,fault):
    source,child,path,q,*_=fixture(tmp_path)
    replay=maps._private.saved_replay(source,child,q);replay.reconstruct()
    if fault in('source','candidate'):
        p=source if fault=='source'else child;p.write_bytes(p.read_bytes()+b'\n')
    elif fault in('grade','report'):
        p=Path(q['grade']if fault=='grade'else q['binding']['native_report']);p.write_bytes(p.read_bytes()+b'\n')
    elif fault=='sidecar':(child.parent/'unowned-new-metadata.json').write_text('{}')
    elif fault=='rules':child.with_suffix('.kicad_dru').write_text('forged rules')
    elif fault=='code':monkeypatch.setattr(force,'_code_identity',lambda:{'forged':'0'*64})
    elif fault=='native':monkeypatch.setattr(pcbnew,'__file__',str(path))
    else:monkeypatch.setenv('CEC_TEST_EXPECTED_NATIVE_DRIFT','changed')
    with pytest.raises(ValueError,match='inputs_changed_before_comparison'):replay.receive()


@pytest.mark.parametrize('phase',['reconstruct','compare'])
@pytest.mark.parametrize('seconds',[10.,10.1,float('nan')])
def test_real_native_constituents_keep_their_own_deadlines(tmp_path,monkeypatch,phase,seconds):
    source,child,path,q,*_=fixture(tmp_path);now=[0.]
    owner=maps._private
    monkeypatch.setattr(owner,'_saved_replay_clock',lambda:now[0])
    replay=owner.saved_replay(source,child,q)
    if phase=='compare':replay.reconstruct()
    actual=owner.construct if phase=='reconstruct'else owner.field._save_field_snapshot
    def late(*args,**kwargs):
        result=actual(*args,**kwargs);now[0]+=seconds;return result
    if phase=='reconstruct':monkeypatch.setattr(owner,'construct',late)
    else:monkeypatch.setattr(owner.field,'_save_field_snapshot',late)
    with pytest.raises(ValueError,match='saved_reference_'+phase+'_deadline'):
        (replay.reconstruct if phase=='reconstruct'else replay.receive)()
    assert replay.observation()['state']=='failed'


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_material_staged_policy_is_strict_boolean(tmp_path,value):
    source,child,path,*_=fixture(tmp_path)
    result=material.receive(source,child,path,staged_map_replay=value)
    assert not result['ok']and result['error']=='explicit_staged_map_replay_boolean_required'


@pytest.mark.parametrize('timeout',[True,0,-1,10.01,float('nan')])
def test_saved_replay_cannot_expand_native_leases(tmp_path,timeout):
    source,child,path,q,*_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_saved_reference_stage'):
        maps.saved_replay(source,child,q,timeout_s=timeout)


def test_second_candidate_save_is_mandatory_not_a_cached_first_tree(tmp_path,monkeypatch):
    source,child,path,q,*_=fixture(tmp_path);replay=maps.saved_replay(source,child,q)
    replay.reconstruct();actual=maps._private.field._save_field_snapshot
    def corrupt_second(board,target):
        actual(board,target)
        if Path(target).name=='second-save.kicad_pcb':
            text=Path(target).read_text();Path(target).write_text(text[:-2]+'(opaque_extra_native 1)\n)')
    monkeypatch.setattr(maps._private.field,'_save_field_snapshot',corrupt_second)
    with pytest.raises(ValueError,match='not_stable_under_a_second_native_save'):replay.receive()


def test_saved_stage_still_requires_fresh_mask_preflight(tmp_path,monkeypatch):
    source,child,path,q,*_=fixture(tmp_path);replay=maps.saved_replay(source,child,q)
    replay.reconstruct()
    monkeypatch.setattr(maps.masks,'observe',lambda *args:dict(ok=False,complete=False,errors=['actual mask refused']))
    with pytest.raises(ValueError,match='saved_mask_artwork_preflight_refused'):replay.receive()
