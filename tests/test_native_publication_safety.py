"""Reject pretty/count-improved candidates that change unknown cut evidence."""
import copy
import pytest
from root_native_publication_safety_20261012 import require_saved_grade


def fixture():
    native=dict(ok=True,complete=True,native_inventory={'potentially_truncated':False})
    checks=[dict(id='check-'+str(i),status='PASS') for i in range(50)]
    return dict(code_identity={'digest':'same'},source_candidate_and_code_unchanged=True,
        new_native_fault_ids=[],clipped_kelvin_comparison={'comparison_complete':True,'same_evidence':True},
        boards={side:dict(sha256=side,native_producer=copy.deepcopy(native),
            opens=3 if side=='source' else 0,scored_drc=23,board_bbox_mm=[0.,0.,78.,89.5],
            full50_checks=copy.deepcopy(checks)) for side in ('source','candidate')})


def check(grade):
    return require_saved_grade(grade,epoch={'digest':'same'},source_sha256='source',candidate_sha256='candidate')


def test_complete_nonregression_never_claims_release():
    assert check(fixture())['release_authority'] is False


@pytest.mark.parametrize('fault',['epoch','unstable','fault_ids','clip_changed','clip_incomplete',
    'source_hash','candidate_hash','capped','native_incomplete','native_failed',
    'negative_count','bool_count','opens_regressed','score_regressed','check_failed',
    'check_disappeared','duplicate_check','check_unavailable','missing_bbox','growth'])
def test_no_counter_or_render_can_borrow_missing_source_evidence(fault):
    grade=fixture();row=grade['boards']['candidate']
    if fault=='epoch':grade['code_identity']={'digest':'different'}
    if fault=='unstable':grade['source_candidate_and_code_unchanged']=False
    if fault=='fault_ids':grade['new_native_fault_ids']=['new']
    if fault=='clip_changed':grade['clipped_kelvin_comparison']['same_evidence']=False
    if fault=='clip_incomplete':grade['clipped_kelvin_comparison']['comparison_complete']=False
    if fault=='source_hash':grade['boards']['source']['sha256']='wrong'
    if fault=='candidate_hash':row['sha256']='wrong'
    if fault=='capped':row['native_producer']['native_inventory']['potentially_truncated']=True
    if fault=='native_incomplete':row['native_producer']['complete']=False
    if fault=='native_failed':row['native_producer']['ok']=False
    if fault=='negative_count':row['opens']=-1
    if fault=='bool_count':row['opens']=False
    if fault=='opens_regressed':row['opens']=4
    if fault=='score_regressed':row['scored_drc']=24
    if fault=='check_failed':row['full50_checks'][0]['status']='FAIL'
    if fault=='check_disappeared':row['full50_checks'].pop()
    if fault=='duplicate_check':row['full50_checks'][0]=row['full50_checks'][1]
    if fault=='check_unavailable':row['full50_checks'][0]['status']='N/A'
    if fault=='missing_bbox':row['board_bbox_mm']=None
    if fault=='growth':row['board_bbox_mm'][3]+=.1
    with pytest.raises(ValueError):check(grade)


def test_real_compaction_and_fail_to_pass_are_allowed_without_downgrading_other_checks():
    grade=fixture();grade['boards']['candidate']['board_bbox_mm'][3]-=1.
    grade['boards']['source']['full50_checks'][0]['status']='FAIL'
    assert check(grade)['same_clipped_evidence_preserved']


def joint_fixture(monkeypatch):
    import root_native_pth_bank_preclear_receiving_20261013 as bank
    calls=[]
    c=dict(scope='private_joint_pth_bank_and_full_load_branch_prototype',
        source='old-native',candidate='new-native',source_sha256='source',candidate_sha256='candidate',
        reflowed_zone_uuid='actual-zone',target_layer='B.Cu',source_bank_enclosure_margin_nm=50000,
        retired_track_uuids=['actual-owned-cut'],claimed_success=True)
    proof=dict(ok=True,complete=True,source_sha256='source',candidate_sha256='candidate',
        code_identity={'digest':'same'},exact_native_reconstruction=True,
        physical_kelvin_preservation={'comparison_complete':True,'same_evidence':True},
        release_authority=False)
    def replay(*a,**k):
        calls.append((a,k));return copy.deepcopy(proof)
    monkeypatch.setattr(bank,'receive',replay)
    grade=fixture();grade['clipped_kelvin_comparison']['same_evidence']=False
    def check_joint():
        return require_saved_grade(grade,epoch={'digest':'same'},source_sha256='source',
            candidate_sha256='candidate',contour_construction=c,board_hint='renamed-board')
    return grade,c,proof,calls,check_joint


def test_joint_native_transform_requires_fresh_whole_source_replay_even_when_producer_says_success(monkeypatch):
    grade,c,proof,calls,run=joint_fixture(monkeypatch)
    result=run()
    assert calls==[(('old-native','new-native',dict(source_zone_uuid='actual-zone',target_layer='B.Cu',
        enclosure_margin_nm=50000,retired_track_uuids=['actual-owned-cut'])),{'board_hint':'renamed-board'})]
    assert not result['same_clipped_evidence_preserved']  # Raw changed evidence is NOT rewritten.
    assert result['independent_fresh_joint_bank_force_preclear_requalification']['ok']
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['ok','complete','source_sha256','candidate_sha256','code_identity',
    'exact_native_reconstruction','cut_complete','cut_preserved','construction_source','new_fault','missing_check'])
def test_joint_transform_cannot_borrow_a_flag_or_skip_complete_native_grade(monkeypatch,fault):
    grade,c,proof,calls,run=joint_fixture(monkeypatch)
    if fault in ('ok','complete','exact_native_reconstruction'):proof[fault]=False
    if fault in ('source_sha256','candidate_sha256'):proof[fault]='wrong'
    if fault=='code_identity':proof[fault]={'digest':'old'}
    if fault=='cut_complete':proof['physical_kelvin_preservation']['comparison_complete']=False
    if fault=='cut_preserved':proof['physical_kelvin_preservation']['same_evidence']=False
    if fault=='construction_source':c['source_sha256']='unrelated'
    if fault=='new_fault':grade['new_native_fault_ids']=['fault']
    if fault=='missing_check':grade['boards']['candidate']['full50_checks'].pop()
    with pytest.raises(ValueError):run()


def bundle_fixture(monkeypatch):
    import cec_redundant_force_bundle as bundle
    calls=[]
    scope=dict(native_uuids=['native-zone','native-track'],
        allow_locked_native_uuids=['native-zone','native-track'])
    construction=dict(source='old-native',candidate='new-native',source_sha256='source',
        candidate_sha256='candidate',native_force_bundle_scope=scope,worker_success=True)
    proof=dict(ok=True,complete=True,source_sha256='source',candidate_sha256='candidate',
        code_identity={'digest':'same'},source_sense={},candidate_sense={},release_authority=False)
    def replay(*a,**k):
        calls.append((a,k));return copy.deepcopy(proof)
    monkeypatch.setattr(bundle,'receive',replay)
    grade=fixture()
    def run():
        return require_saved_grade(grade,epoch={'digest':'same'},source_sha256='source',
            candidate_sha256='candidate',contour_construction=construction,board_hint='renamed-board')
    return grade,construction,proof,calls,run


def test_bundle_publication_replays_actual_cut_even_with_unchanged_counts(monkeypatch):
    grade,c,proof,calls,run=bundle_fixture(monkeypatch)
    result=run()
    assert calls==[(('old-native','new-native'),dict(board_hint='renamed-board',timeout_s=20.,
        **c['native_force_bundle_scope']))]
    assert result['independent_fresh_native_force_bundle_requalification']['ok']
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['ok','complete','source_sha256','candidate_sha256','code_identity',
    'construction_source','construction_candidate','new_fault'])
def test_bundle_publication_does_not_trust_old_success_or_hashes(monkeypatch,fault):
    grade,c,proof,calls,run=bundle_fixture(monkeypatch)
    if fault in ('ok','complete'):proof[fault]=False
    if fault in ('source_sha256','candidate_sha256'):proof[fault]='wrong'
    if fault=='code_identity':proof[fault]={'digest':'old'}
    if fault=='construction_source':c['source_sha256']='unrelated'
    if fault=='construction_candidate':c['candidate_sha256']='unrelated'
    if fault=='new_fault':grade['new_native_fault_ids']=['fault']
    with pytest.raises(ValueError):run()


def planar_fixture(monkeypatch):
    import cec_full_current_planar_reflow as planar
    calls=[]
    phases=[dict(kind='full_current_planar_reflow',candidate='new-native',retired_track_uuids=['native-cut'])]
    construction=dict(source='old-native',candidate='new-native',source_sha256='source',
        candidate_sha256='candidate',native_planar_current_chain=phases,worker_success=True)
    proof=dict(ok=True,complete=True,source_sha256='source',candidate_sha256='candidate',
        code_identity={'digest':'same'},source_sense={},candidate_sense={},
        physical_preservation={'comparison_complete':True,'same_evidence':True},release_authority=False)
    def replay(*a,**k):calls.append((a,k));return copy.deepcopy(proof)
    monkeypatch.setattr(planar,'receive_force_sense_chain',replay)
    grade=fixture();grade['clipped_kelvin_comparison']['same_evidence']=False
    def run():
        return require_saved_grade(grade,epoch={'digest':'same'},source_sha256='source',
            candidate_sha256='candidate',contour_construction=construction,board_hint='renamed-board')
    return grade,construction,proof,calls,run


def test_planar_changed_witnesses_require_fresh_exact_native_and_two_absolute_cut_proofs(monkeypatch):
    grade,c,proof,calls,run=planar_fixture(monkeypatch)
    result=run()
    assert calls==[(('old-native','new-native'),dict(board_hint='renamed-board',
        phases=c['native_planar_current_chain']))]
    assert result['independent_fresh_native_planar_current_requalification']['ok']
    assert not result['same_clipped_evidence_preserved'] and not result['release_authority']


@pytest.mark.parametrize('fault',['ok','complete','source_sha256','candidate_sha256','code_identity',
    'physical_complete','physical_preserved','construction_source','new_fault','missing_check'])
def test_planar_publication_cannot_borrow_success_or_changed_unknown_evidence(monkeypatch,fault):
    grade,c,proof,calls,run=planar_fixture(monkeypatch)
    if fault in ('ok','complete'):proof[fault]=False
    if fault in ('source_sha256','candidate_sha256'):proof[fault]='wrong'
    if fault=='code_identity':proof[fault]={'digest':'old'}
    if fault=='physical_complete':proof['physical_preservation']['comparison_complete']=False
    if fault=='physical_preserved':proof['physical_preservation']['same_evidence']=False
    if fault=='construction_source':c['source_sha256']='unrelated'
    if fault=='new_fault':grade['new_native_fault_ids']=['fault']
    if fault=='missing_check':grade['boards']['candidate']['full50_checks'].pop()
    with pytest.raises(ValueError):run()
