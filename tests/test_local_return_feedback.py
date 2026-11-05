import copy
from types import SimpleNamespace

import pytest
import cec_local_return_feedback as feedback
import cec_synth_pipeline as synth
import cec_full_pipeline as pipeline


def fixture():
    positions = {'U_TEST': (10., 10., 0.), 'C_TEST': (11., 10., 180.),
                 'C_OTHER': (10., 12., 90.)}
    proof = dict(search_exhausted=True, conclusion='no_legal_immediate_ground_return',
        terminal=dict(ref='U_TEST', pad='G'), pad_center=dict(copper_admission=dict(
            at_mm=[10., 10.], diameter_mm=.35, clearance_mm=.2,
            blockers=[dict(kind='pour_first_reservation', layer='In3.Cu', net='POWER',
                           rect_mm=[8., 8., 12., 12.])])))
    row = dict(cap_ref='C_TEST', owner_ref='U_TEST', status='assigned',
        owner_position_mm=[10., 10.], cap_position_mm=[11., 10.],
        supply_access_ok=False, actionable=True,
        supply_access_certificate=dict(ground_return=dict(attempts=[
            dict(error='native search refused', evidence=proof)])))
    other = dict(cap_ref='C_OTHER', owner_ref='U_TEST', status='assigned')
    evidence = dict(ok=False, errors=[], decoupler=dict(ok=False, details=[row, other],
        violations=[['C_TEST', 'U_TEST.VDD local-cell-access', 1.]]))
    return positions, evidence, row, proof


def test_exhausted_constructor_is_not_deferred_to_the_same_constructor():
    _, evidence, _, _ = fixture()
    gate = synth.placement_craft_admission(evidence, allow_route_access_repair=True)
    assert not gate['ok'] and not gate['deferred_to_route']
    assert 'ground-return search exhausted' in gate['blockers'][0]
    policy = pipeline._initial_resume_craft_policy(evidence, {}, resumed=True)
    assert policy['needs_repair']
    certificate = synth.placement_craft_blocker_certificate(evidence)
    assert 'return_path_placement' in certificate['required_stages']


def test_unconstructed_local_copper_can_still_reach_the_mandatory_route_stage():
    _, evidence, row, _ = fixture()
    row['supply_access_certificate'] = None
    assert synth.placement_craft_admission(evidence, allow_route_access_repair=True)['ok']


@pytest.mark.parametrize('field,value', [('search_exhausted',False),
    ('conclusion','in_progress')])
def test_non_final_search_is_not_invented_as_exhausted(field, value):
    _, _, row, proof = fixture(); proof[field] = value
    assert not feedback.failed_searches(row)


def test_successful_cell_does_not_replay_an_old_failed_attempt():
    _, _, row, _ = fixture(); row['supply_access_ok'] = True
    assert not feedback.failed_searches(row)


def test_owner_moves_rigid_cell_and_preserves_angles_and_power():
    positions, evidence, _, _ = fixture()
    original = copy.deepcopy((positions, evidence))
    moves = feedback.move_specs(positions, evidence['decoupler']['details'])
    assert len(moves) == 4
    for move in moves:
        assert set(move['placements']) == set(positions)
        assert move['requires_native_requalification']
        dx, dy = move['dx_mm'], move['dy_mm']
        assert (dx == 0) != (dy == 0)
        assert abs(dx) + abs(dy) == pytest.approx(2.425)
        for ref, (x,y,r) in move['placements'].items():
            assert (x-dx,y-dy,r) == pytest.approx(positions[ref])
    assert (positions, evidence) == original


def test_compact_seat_feeds_smaller_measured_envelope_to_rigid_proposals():
    positions,evidence,_,proof=fixture()
    admission=copy.deepcopy(proof['pad_center']['copper_admission'])
    admission.update(at_mm=[10.,11.],diameter_mm=.30,ok=False)
    proof['compact_dogbone_attempts']=[dict(error='bounded search refused',evidence=dict(
        search_exhausted=True,conclusion='no_legal_immediate_ground_return',
        dogbone_candidates=[dict(failed_checks=['via_spot_clearance'],
                                copper_admission=admission)]))]
    original=copy.deepcopy(evidence)
    moves=feedback.move_specs(positions,evidence['decoupler']['details'],max_specs=1)
    assert len(moves)==1
    assert moves[0]['dy_mm']==pytest.approx(1.40)
    assert moves[0]['requires_native_requalification']
    assert set(moves[0]['placements'])==set(positions)
    assert evidence==original
    # A clear via seat with a blocked lead is NOT a usable compact launch.
    proof['compact_dogbone_attempts'][0]['evidence']['dogbone_candidates'][0][
        'failed_checks'].append('stub_foreign_clearance')
    moves=feedback.move_specs(positions,evidence['decoupler']['details'],max_specs=1)
    assert abs(moves[0]['dx_mm'])+abs(moves[0]['dy_mm'])==pytest.approx(2.425)


def test_incomplete_compact_search_does_not_create_feedback_geometry():
    positions,evidence,_,proof=fixture()
    proof['compact_dogbone_attempts']=[dict(error='pending',evidence=dict(
        search_exhausted=False,dogbone_candidates=[{}]))]
    assert len(list(feedback._seat_proofs([proof])))==1


def test_cap_blocker_offers_cap_only_and_complete_cell_options():
    positions, evidence, _, proof = fixture()
    proof['terminal']['ref'] = 'C_TEST'
    proof['pad_center']['copper_admission']['at_mm'] = [11., 10.]
    moves = feedback.move_specs(positions, evidence['decoupler']['details'])
    assert any(set(m['placements']) == {'C_TEST'} for m in moves)
    assert any(set(m['placements']) == set(positions) for m in moves)


def test_complete_return_macro_has_its_own_bounded_probe_group():
    positions, evidence, _, proof = fixture()
    proof['terminal']['ref'] = 'C_TEST'
    proof['pad_center']['copper_admission']['at_mm'] = [11., 10.]
    moves = feedback.move_specs(positions, evidence['decoupler']['details'])
    selected = synth._bounded_diverse_move_specs(moves, 2)
    assert {set(m['placements']) == set(positions) for m in selected} == {True, False}
    assert len({m['budget_group'] for m in selected}) == 2


@pytest.mark.parametrize('fixed', [('U_TEST',),('C_TEST',),('C_OTHER',)])
def test_cannot_partially_translate_a_fixed_cell(fixed):
    p,e,_,_ = fixture()
    assert not feedback.move_specs(p,e['decoupler']['details'],immovable=fixed)


@pytest.mark.parametrize('fixed,reason', [('U_TEST','terminal_is_fixed'),
    ('C_OTHER','complete_cell_has_fixed_member')])
def test_empty_proposal_family_reports_fixed_dependency_not_missing_solver(fixed, reason):
    p,e,_,_ = fixture(); original=copy.deepcopy((p,e)); diagnostic={}
    assert not feedback.move_specs(p,e['decoupler']['details'],immovable=[fixed],
                                   diagnostics=diagnostic)
    assert diagnostic['rejection_counts'][reason] > 0
    assert diagnostic['samples'][0]['fixed_refs'] == [fixed]
    assert diagnostic['measured_seat_proofs'] == diagnostic['failed_cells'] == 1
    assert diagnostic['proposed'] == diagnostic['selected'] == 0
    assert not diagnostic['geometric_infeasibility_proven']
    assert not diagnostic['allows_power_replan']
    assert (p,e) == original


def test_feedback_diagnostics_distinguish_stale_evidence_and_bounded_motion():
    p,e,row,_=fixture(); diagnostic={}
    row['owner_position_mm'][0] += .001
    assert not feedback.move_specs(p,e['decoupler']['details'],diagnostics=diagnostic)
    assert diagnostic['rejection_counts']=={'stale_terminal_position':1}
    row['owner_position_mm'][0] -= .001
    diagnostic={}
    assert not feedback.move_specs(p,e['decoupler']['details'],max_shift_mm=2.,
                                   diagnostics=diagnostic)
    assert diagnostic['rejection_counts']=={'exit_outside_bounded_motion':4}
    assert not diagnostic['geometric_infeasibility_proven']


def test_feedback_diagnostics_do_not_change_selection_and_survive_certificate():
    p,e,row,proof=fixture(); diagnostic={}
    expected=feedback.move_specs(p,e['decoupler']['details'],max_specs=2)
    assert feedback.move_specs(p,e['decoupler']['details'],max_specs=2,
                               diagnostics=diagnostic)==expected
    assert diagnostic['proposed']==4 and diagnostic['selected']==2
    candidate=SimpleNamespace(P=p,W=30,H=30,back_refs=())
    collected={}
    synth._placement_craft_move_specs(candidate,e,immovable=['U_TEST'],
                                     proposal_diagnostics=collected)
    assert collected['local_ground_return']['rejection_counts']['terminal_is_fixed']
    cert=synth.placement_craft_blocker_certificate(e,dict(proposal_diagnostics=collected))
    assert cert['proposal_diagnostics']==collected
    collected.clear()
    assert cert['proposal_diagnostics']['local_ground_return']['selected']==0


def test_feedback_diagnostic_samples_are_bounded_and_duplicate_proofs_are_counted():
    p,e,row,proof=fixture(); diagnostic={}
    row['supply_access_certificate']['ground_return']['attempts'] *= 100
    feedback.move_specs(p,e['decoupler']['details'],immovable=['U_TEST'],diagnostics=diagnostic)
    assert diagnostic['rejection_counts']['terminal_is_fixed']==100
    assert len(diagnostic['samples'])==1


def test_proposal_and_displacement_budgets_and_duplicate_attempts():
    p,e,row,proof = fixture()
    row['supply_access_certificate']['ground_return']['attempts'] *= 4
    assert len(feedback.move_specs(p,e['decoupler']['details'])) == 4
    assert len(feedback.move_specs(p,e['decoupler']['details'],max_specs=2)) == 2
    assert not feedback.move_specs(p,e['decoupler']['details'],max_shift_mm=2.)


@pytest.mark.parametrize('mutation', ['stale','nan','unknown','reversed','missing_layer'])
def test_no_guessed_geometry_or_stale_coordinates(mutation):
    p,e,row,proof = fixture()
    admission = proof['pad_center']['copper_admission']
    if mutation == 'stale': row['owner_position_mm'][0] += .01
    if mutation == 'nan': admission['at_mm'][0] = float('nan')
    if mutation == 'unknown': admission['blockers'][0]['kind'] = 'pad'
    if mutation == 'reversed': admission['blockers'][0]['rect_mm'] = [12,8,8,12]
    if mutation == 'missing_layer': admission['blockers'][0].pop('layer')
    assert not feedback.move_specs(p,e['decoupler']['details'])


def test_production_move_generator_dispatches_new_family():
    p,e,_,_ = fixture()
    moves = synth._placement_craft_move_specs(SimpleNamespace(P=p), e,
        required_stages=['return_path_placement'])
    assert any(m['kind'] == 'decoupler_ground_territory_reseat' for m in moves)


@pytest.mark.parametrize('status', ['accepted','refused','exception'])
def test_frozen_craft_commit_is_atomic_over_board_and_power_family(tmp_path, monkeypatch, status):
    board = tmp_path/'candidate.kicad_pcb'
    state = board.with_suffix('.pourfirst-state.json')
    rules = board.with_suffix('.kicad_dru')
    board.write_bytes(b'original board'); state.write_bytes(b'original authority')
    def materialize(*args):
        board.write_bytes(b'proposed board')
        rules.write_bytes(b'new rules')
    def sync(*args):
        if status == 'exception': raise RuntimeError('state failure')
        return dict(ok=status=='accepted')
    monkeypatch.setattr(synth,'materialize',materialize)
    monkeypatch.setattr(pipeline,'_sync_safe_postfreeze_placement_delta',sync)
    if status == 'exception':
        with pytest.raises(RuntimeError,match='state failure'):
            pipeline._commit_frozen_craft_repair(None,None,board,dict(changed=True,accepted_count=2))
    else:
        result=pipeline._commit_frozen_craft_repair(None,None,board,dict(changed=True,accepted_count=2))
        assert result['changed'] == (status=='accepted')
        if status=='refused':
            assert result['rolled_back'] and result['accepted_count']==0
            assert result['proposed_accepted_count']==2 and result['proposal_only']
    if status=='accepted':
        assert board.read_bytes()==b'proposed board' and rules.exists()
    else:
        assert board.read_bytes()==b'original board'
        assert state.read_bytes()==b'original authority'
        assert not rules.exists()


def test_unchanged_craft_commit_never_materializes(tmp_path, monkeypatch):
    monkeypatch.setattr(synth,'materialize',lambda *a:pytest.fail('no-op must not rewrite'))
    assert pipeline._commit_frozen_craft_repair(None,None,tmp_path/'absent',dict(changed=False)) == dict(changed=False)


def test_sampled_clear_escape_reveals_power_hidden_by_pad_center_exclusion():
    p,e,row,proof=fixture()
    sample=copy.deepcopy(proof['pad_center']['copper_admission'])
    sample.update(ok=False,at_mm=[11.4,10.],diameter_mm=.9)
    proof['pad_center']['copper_admission']['blockers']=[dict(kind='pad',ref='U_TEST')]
    proof['dogbone_candidates']=[dict(failed_checks=['via_spot_clearance'],copper_admission=sample)]
    moves=feedback.move_specs(p,e['decoupler']['details'])
    assert moves and any(m['dx_mm']==pytest.approx(1.3) for m in moves)
    proof['dogbone_candidates'][0]['failed_checks'].append('stub_foreign_clearance')
    assert not feedback.move_specs(p,e['decoupler']['details'])


def test_global_budget_cannot_starve_a_second_owner():
    p,e,row,proof=fixture()
    other=copy.deepcopy(row);other.update(owner_ref='U_NEXT',cap_ref='C_NEXT')
    other['supply_access_certificate']['ground_return']['attempts'][0]['evidence']['terminal']['ref']='U_NEXT'
    p.update(U_NEXT=p['U_TEST'],C_NEXT=p['C_TEST'])
    moves=feedback.move_specs(p,e['decoupler']['details']+[other],max_specs=2)
    assert {m['owner_ref'] for m in moves}=={'U_TEST','U_NEXT'}


def test_rotated_return_portal_can_clear_reservation_without_translation():
    p,e,_,proof=fixture()
    admission=proof['pad_center']['copper_admission']
    admission['at_mm']=[12.,10.]
    admission['blockers'][0]['rect_mm']=[11.,9.,13.,11.]
    original=copy.deepcopy((p,e))
    moves=feedback.move_specs(p,e['decoupler']['details'],rotation_degrees=(0,90,180,270))
    rotated=[m for m in moves if m['rotation_deg']==180]
    assert any(m['dx_mm']==m['dy_mm']==0 for m in rotated)
    move=next(m for m in rotated if m['dx_mm']==m['dy_mm']==0)
    assert move['placements']['C_TEST']==pytest.approx((9.,10.,0.))
    assert move['placements']['C_OTHER']==pytest.approx((10.,8.,270.))
    assert set(move['placements'])==set(p)
    assert move['budget_group'].endswith(':rotate-180')
    assert move['requires_native_requalification']
    assert (p,e)==original


def test_rotation_fairness_and_explicit_disabled_or_invalid_angles():
    p,e,_,_=fixture()
    moves=feedback.move_specs(p,e['decoupler']['details'],rotation_degrees=(0,90,180,270),max_specs=4)
    assert {m['rotation_deg'] for m in moves}=={0,90,180,270}
    assert not feedback.move_specs(p,e['decoupler']['details'],max_specs=0)
    moves=feedback.move_specs(p,e['decoupler']['details'],rotation_degrees=(13,float('nan'),float('inf'),360,90,90))
    assert {m['rotation_deg'] for m in moves}=={0,90}
    assert not feedback.move_specs(p,e['decoupler']['details'],rotation_degrees=(90,180),immovable={'C_OTHER'})


def test_production_offers_complete_return_orientations_without_rotating_caps_alone():
    p,e,_,proof=fixture()
    proof['terminal']['ref']='C_TEST'
    proof['pad_center']['copper_admission']['at_mm']=[11.,10.]
    moves=synth._placement_craft_move_specs(SimpleNamespace(P=p),e,
        required_stages=['return_path_placement'])
    returns=[m for m in moves if m['kind']=='decoupler_ground_territory_reseat']
    assert any(m['rotation_deg'] for m in returns)
    assert all(set(m['placements'])==set(p) for m in returns if m['rotation_deg'])


@pytest.mark.parametrize('flipped',[False,True])
def test_loaded_native_return_exits_preserve_every_bypass_pad_distance(tmp_path,flipped):
    import math
    import pcbnew
    from test_placement_search_domain import native_cell,native_poses,native_pad_points,apply_poses
    source=native_cell(tmp_path,flipped);original=source.read_bytes()
    board=pcbnew.LoadBoard(str(source));p=native_poses(board);before=native_pad_points(board)
    point=before['P_DEST'];box=[point[0]-1,point[1]-.8,point[0]+1,point[1]+.8]
    proof=dict(search_exhausted=True,conclusion='no_legal_immediate_ground_return',
        terminal=dict(ref='P_DEST',pad='1'),pad_center=dict(copper_admission=dict(
            at_mm=point,diameter_mm=.35,clearance_mm=.2,blockers=[dict(
                kind='pour_first_reservation',layer='In3.Cu',net='/RESERVED',rect_mm=box)])))
    detail=dict(owner_ref='P_DEST',cap_ref='P_FOLLOWER',status='assigned',
        owner_position_mm=list(p['P_DEST'][:2]),cap_position_mm=list(p['P_FOLLOWER'][:2]),
        supply_access_ok=False,supply_access_certificate=dict(ground_return=dict(attempts=[
            dict(error='refused',evidence=proof)])))
    moves=feedback.move_specs(p,[detail],rotation_degrees=(0,90,180,270))
    assert {m['rotation_deg'] for m in moves}=={0,90,180,270}
    for move in moves:
        trial=pcbnew.LoadBoard(str(source));apply_poses(trial,move['placements'])
        after=native_pad_points(trial)
        assert math.dist(after['P_DEST'],after['P_FOLLOWER'])==pytest.approx(
            math.dist(before['P_DEST'],before['P_FOLLOWER']),abs=5e-6)
        x,y=after['P_DEST'];margin=.35/2+.2+.05
        assert not (box[0]-margin+5e-6 < x < box[2]+margin-5e-6
                    and box[1]-margin+5e-6 < y < box[3]+margin-5e-6)
        assert after['P_SOURCE']==before['P_SOURCE']
    assert source.read_bytes()==original
