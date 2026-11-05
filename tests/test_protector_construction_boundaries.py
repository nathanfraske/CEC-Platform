"""A private protector result never borrows a stale Ground or timeout proof."""
import subprocess
import time

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_ground_return_shortcut as reference
import cec_protector_cell as op
from test_ground_return_shortcut import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_final_witness_is_the_actual_post_refill_ground_in_each_native_frame(tmp_path,quarter,mirror,face):
    b,_,_,pad,via,_=fixture(tmp_path,quarter,mirror,face)
    via.SetPosition(pad.GetPosition());additive._ground_refill(b)
    q=op._final_ground_reference(b,pad,3.1,time.monotonic()+10.)
    assert q['return_mm']==0 and q['via_uuid']==op.force._uid(via)
    assert q['references']==reference._reference_contacts(b,via)
    assert q['freshly_observed_after_all_routes_and_final_refill']


@pytest.mark.parametrize('fault',['all_planes_lost','one_plane_lost','wrong_ground','moved_far'])
def test_pre_pair_reference_contacts_cannot_substitute_for_the_final_native_reference(tmp_path,monkeypatch,fault):
    b,_,_,pad,via,_=fixture(tmp_path)
    via.SetPosition(pad.GetPosition());additive._ground_refill(b)
    assert reference._reference_contacts(b,via)
    # Even a retained path witness cannot make its old reference-plane
    # certificate survive an actual post-route material change.
    monkeypatch.setattr(op.cells,'_existing_return',lambda *a,**k:(0.,via))
    if fault=='all_planes_lost':
        for z in b.Zones():z.UnFill()
    elif fault=='one_plane_lost':next(iter(b.Zones())).UnFill()
    elif fault=='wrong_ground':
        for z in b.Zones():z.SetNet(b.FindNet('+3V3'))
    else:via.SetPosition(pcbnew.VECTOR2I_MM(200.,200.))
    with pytest.raises(ValueError,match='actual_saved_contact_to_each_declared_ground_reference_required'):
        op._final_ground_reference(b,pad,3.1,time.monotonic()+10.)


@pytest.mark.parametrize('witness,source_return',[(None,3.1),((1.500002,None),3.1),((1.1,None),1.),((.2,None),.1)])
def test_final_ground_must_be_known_immediate_and_nonregressing(monkeypatch,witness,source_return):
    monkeypatch.setattr(op.cells,'_existing_return',lambda *a,**k:witness)
    with pytest.raises(ValueError,match='protector_final_ground_not_immediate_or_source_nonregressing'):
        op._final_ground_reference(None,None,source_return,time.monotonic()+10.)


def test_reference_proof_and_final_hashing_cannot_escape_the_constituent_lease(monkeypatch):
    clock=[1.]
    monkeypatch.setattr(op.cells,'_existing_return',lambda *a,**k:(0.,object()))
    def observe(*args):clock[0]=11.;return [['final-native-zone',4]]
    monkeypatch.setattr(reference,'_reference_contacts',observe)
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    with pytest.raises(ValueError,match='protector_constituent_deadline'):
        op._final_ground_reference(None,None,3.1,10.)


@pytest.mark.parametrize('error',[subprocess.TimeoutExpired(['kicad-cli','sch','export'],.1),
    ValueError('source-contract-refused'),RuntimeError('native-refused'),OSError('source-missing')])
def test_failed_fresh_source_compilation_returns_no_partial_board_or_no_path_claim(monkeypatch,error):
    def refuse(*args,**kwargs):raise error
    monkeypatch.setattr(op,'compile',refuse)
    board,q=op.construct(dict(source='/not-used/source.kicad_pcb',owner_uuid='fixture-owner',
        board_hint='fixture',pair_plan={'pair':{'name':'fixture-pair'}},target_pose=[1.,2.,90.],max_shift_mm=6.))
    assert board is None and not q['complete'] and not q['partial_candidate_emitted']
    assert q['failed_stage']=='source_compilation' and q['errors']
    assert q['phases']['source_compilation']['elapsed_s']>=0
    assert not q['no_path_proof'] and not q['routing_admitted'] and not q['release_authority']


@pytest.mark.parametrize('proposal',[None,[],{},dict(source=None),dict(source='/not-used/source.kicad_pcb')])
def test_malformed_source_proposals_also_have_an_honest_atomic_failure_shape(proposal):
    board,q=op.construct(proposal)
    assert board is None and not q['complete'] and q['failed_stage']=='source_compilation'
    assert q['errors'] and not q['partial_candidate_emitted'] and not q['no_path_proof']


@pytest.mark.parametrize('seconds',[True,0.,-1.,10.01,float('nan'),float('inf')])
def test_constructor_never_accepts_a_longer_or_nonfinite_constituent(seconds):
    with pytest.raises(ValueError,match='bounded_protector_constituent_required'):
        op.construct({},timeout_s=seconds)


def test_protector_compilation_and_proposal_comparison_share_one_original_lease(monkeypatch):
    clock=[0.];stable=op._stable
    q=dict(source='/unused/source.kicad_pcb',owner_uuid='fixture',board_hint='fixture',
        pair_plan={'pair':{'name':'fixture'}},target_pose=[1.,2.,0.],max_shift_mm=6.,pose_screen={'ok':True})
    def compile(*a,**k):clock[0]=9.99;return object(),q
    def compare(value):clock[0]+=.02;return stable(value)
    monkeypatch.setattr(op,'compile',compile);monkeypatch.setattr(op,'_stable',compare)
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    b,r=op.construct(q)
    assert b is None and not r['complete']and r['failed_stage']=='source_compilation'
    assert 'protector_constituent_deadline'in r['errors'][0]
