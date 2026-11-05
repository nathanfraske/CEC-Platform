"""A bounded relocation prefix is not an exhausted placement neighborhood."""
import json

import pytest
import cec_certificate_repair as repair
import cec_fixed_pofv_mobility as mobility
import cec_support_craft_gate as craft
import cec_support_pose_rank as craft_rank
import cec_route_pose_history as history


@pytest.mark.parametrize('mode,budget,attempts,unvisited,stop',[
    ('route',8,6,4,'nonproductive_prefix_budget'),
    ('placement',3,3,7,'candidate_trial_budget'),
    ('placement',0,0,10,'candidate_trial_budget'),
    ('placement',10,10,0,'candidate_exhausted'),
    ('effort',8,2,8,'global_attempt_budget'),
])
@pytest.mark.parametrize('ref,offset',[('SUPPORT',0),('RENAMED',31.7)])
def test_real_transaction_reports_remaining_primary_proposals(
        tmp_path,monkeypatch,mode,budget,attempts,unvisited,stop,ref,offset):
    source=tmp_path/'original.kicad_pcb';source.write_text('unchanged')
    target=repair.asdict(repair.FootprintRepairTarget(ref=ref,target_net='/SIGNAL',
        endpoint_ref='SOURCE',endpoint_pad='3',endpoint_x_mm=offset+2,
        endpoint_y_mm=7,hit_count=1,distance_mm=2,priority=(0,)))
    poses=[dict(dx_mm=offset+i,dy_mm=0,rotation_delta_deg=0) for i in range(10)]
    monkeypatch.setattr(repair,'_copy_board_family',lambda *args:None)
    def drc(_board,destination):
        with open(destination,'w') as stream:json.dump({'violations':[]},stream)
        return {'violations':[]}
    monkeypatch.setattr(repair,'_run_drc',drc)
    def spawn(worker,args,**kwargs):
        if worker is craft.measure:
            return dict(ok=True,gates={},faults={})
        if worker is mobility.filter_candidates:
            return dict(eligible=args[2],rejected=[])
        if worker is craft_rank.rank_candidates:
            return dict(candidates=args[2],release_authority=False,admission_authority=False)
        if worker is repair._relocate_footprint_worker:
            return True,{'affected_nets':[]}
        if worker is repair._refill_worker:return True
        if worker is repair._score_worker:return {}
        if worker is repair._classify_placement_conflicts_worker:
            return dict(fixed_conflict_count=1,movable_track_uuids=[],movable_via_targets=[])
        if worker is repair._exact_relocated_connections_worker:
            return dict(target_closed=False,refused=[])
        pytest.fail('unexpected worker '+worker.__name__)
    monkeypatch.setattr(repair,'_spawn_apply',spawn)
    monkeypatch.setattr(repair,'_placement_preflight_accepts',
        lambda *args:(mode=='route','measured_preflight',[]))
    effort=repair.RepairEffortBudget(max_attempts=2,wall_budget_s=60) if mode=='effort' else None
    result=repair._attempt_footprint_relocation(str(source),{},target,work_dir=str(tmp_path),
        token='prefix',candidate_override=poses,max_candidates=budget,effort=effort,
        allow_route_expansion=False)
    assert result['stop']==stop
    assert len(result['attempts'])==attempts
    assert result['candidate_frontier']==dict(generated=10,prior_skipped=0,physical_prior_skipped=0,
        craft_geometry_prior_skipped=0,
        electrical_pose_ranking=dict(release_authority=False,admission_authority=False),
        native_pin_aperture_proposals=dict(count=0,release_authority=False),
        fixed_via_domain=dict(eligible=poses,rejected=[]),
        scheduled=attempts,unvisited=unvisited,exhaustion_is_no_path_proof=False)
    assert source.read_text()=='unchanged' and not result['adopted']


def test_skipped_poses_are_not_reported_as_new_work(tmp_path,monkeypatch):
    target=repair.asdict(repair.FootprintRepairTarget(ref='CELL',target_net='N',
        endpoint_ref='OWNER',endpoint_pad='1',endpoint_x_mm=2,endpoint_y_mm=3,
        hit_count=1,distance_mm=1,priority=(0,)))
    poses=[dict(dx_mm=i,dy_mm=0,rotation_delta_deg=0) for i in range(7)]
    context=dict(stage='footprint_relocation',max_copper_pads=2,max_branch_tracks=12)
    skipped={history.candidate_key(target,p,context) for p in poses[:4]}
    def spawn(worker,args,**kwargs):
        if worker is craft_rank.rank_candidates:
            return dict(candidates=args[2],release_authority=False,admission_authority=False)
        assert worker is mobility.filter_candidates
        return dict(eligible=args[2],rejected=[])
    monkeypatch.setattr(repair,'_spawn_apply',spawn)
    result=repair._attempt_footprint_relocation('never-opened.kicad_pcb',{},target,
        work_dir=str(tmp_path),token='skips',candidate_override=poses,max_candidates=0,
        skip_candidate_keys=skipped)
    assert result['candidate_frontier']==dict(generated=7,prior_skipped=4,physical_prior_skipped=0,
        craft_geometry_prior_skipped=0,
        electrical_pose_ranking=dict(release_authority=False,admission_authority=False),
        native_pin_aperture_proposals=dict(count=0,release_authority=False),
        fixed_via_domain=dict(eligible=poses,rejected=[]),
        scheduled=0,unvisited=3,exhaustion_is_no_path_proof=False)
    assert result['stop']=='candidate_trial_budget'
