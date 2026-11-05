from types import SimpleNamespace

import pytest
import cec_synth_pipeline as synth
from cec_blueprint_placement import restore_candidate


def fixture(monkeypatch, rotation=0):
    template = {'anchor': {'ref':'A'}, 'parts': {
        'A': {'offset_mm': [0, 0], 'rot_delta': 0, 'flipped': False},
        'B': {'offset_mm': [2, 0], 'rot_delta': 180, 'flipped': False}},
        'internal_tracks': [], 'vias': []}
    monkeypatch.setattr(synth, '_declared_blueprint_stamps', lambda cfg, P: [dict(
        template=template, at_mm=[10, 12], rot=rotation,
        ref_map={'A':'SHUNT', 'B':'MONITOR'}, net_map={})])
    cfg = SimpleNamespace(params={}, pins={'SHUNT': (10, 12, rotation)})
    candidate = SimpleNamespace(P={'SHUNT': (10,12,rotation), 'MONITOR': (18,8,0),
                                   'UNRELATED': (31,32,90)}, back_refs=(), strat='incumbent')
    return cfg, candidate


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_restore_is_anchor_relative_atomic_and_nonmutating(monkeypatch, rotation):
    cfg, source = fixture(monkeypatch, rotation)
    before = dict(source.P)
    result, report = restore_candidate(cfg, source)
    assert report['changed'] and not report['admitted']
    assert report['changed_refs'] == ['MONITOR']
    assert source.P == before
    assert result.P['SHUNT'] == source.P['SHUNT']
    assert result.P['UNRELATED'] == source.P['UNRELATED']
    assert result.P['MONITOR'] != source.P['MONITOR']
    again, receipt = restore_candidate(cfg, result)
    assert again is None and not receipt['changed']


@pytest.mark.parametrize('defect', ['fixed','missing','face','frozen'])
def test_restore_cannot_relax_other_contracts(monkeypatch, defect):
    cfg, source = fixture(monkeypatch)
    if defect == 'fixed': cfg.pins['MONITOR'] = source.P['MONITOR']
    if defect == 'missing': del source.P['MONITOR']
    if defect == 'face': source.back_refs = ('MONITOR',)
    if defect == 'frozen': source.frozen_placement_contract = {'state_sha256':'opaque'}
    before = dict(source.P)
    result, report = restore_candidate(cfg, source)
    assert result is None and report['refusals'] and not report['changed']
    assert source.P == before


def test_no_declared_cells_adds_no_candidate(monkeypatch):
    cfg, source = fixture(monkeypatch)
    monkeypatch.setattr(synth, '_declared_blueprint_stamps', lambda *a: [])
    result, report = restore_candidate(cfg, source)
    assert result is None and not report['applicable']


def test_source_owned_supply_follower_rotates_with_owner(monkeypatch):
    from cec_placement_search_domain import rigid_cell_transform
    cfg, source = fixture(monkeypatch, 90)
    cfg.sch = 'current-hierarchy'
    source.P['BYPASS'] = (19,8,90)
    monkeypatch.setattr(synth, 'View', lambda cfg: SimpleNamespace(nl=SimpleNamespace(comps={})))
    monkeypatch.setattr(synth, '_device_bypass_specs', lambda *a: {'BYPASS': {'owner':'MONITOR'}})
    result, report = restore_candidate(cfg, source)
    old,new = source.P['MONITOR'],result.P['MONITOR']
    expected=rigid_cell_transform({r:source.P[r] for r in ('MONITOR','BYPASS')},
        'MONITOR',new[2]-old[2],(new[0]-old[0],new[1]-old[1]))
    assert result.P['BYPASS'] == expected['BYPASS']
    assert report['supply_followers'] == [{'ref':'BYPASS','owner':'MONITOR'}]
    cfg.pins['BYPASS'] = source.P['BYPASS']
    result,report = restore_candidate(cfg, source)
    assert result is None and report['refusals'][0]['reason'] == 'explicit_pose_constraint'


def test_whole_cell_contact_reseating_avoids_native_exclusion(monkeypatch):
    import pcbnew
    import cec_pcb
    from cec_blueprint_placement import restoration_candidates
    cfg,source=fixture(monkeypatch)
    cfg.pins={}
    cfg.params['blueprint_cells']=[{'anchor_ref':'SHUNT'}]
    source.source_board='native-source';source.W=40.;source.H=40.
    board=pcbnew.BOARD()
    zone=pcbnew.ZONE(board);zone.SetIsRuleArea(True);zone.SetLayer(pcbnew.F_Cu)
    zone.SetDoNotAllowFootprints(True)
    poly=zone.Outline();poly.NewOutline()
    for x,y in [(11,11),(13,11),(13,13),(11,13)]: poly.Append(int(x*1e6),int(y*1e6))
    board.Add(zone)
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda _:board)
    monkeypatch.setattr(synth,'View',lambda _:SimpleNamespace(nl=SimpleNamespace(comps={})))
    monkeypatch.setattr(synth,'_fp_of',lambda _: {})
    monkeypatch.setattr(synth,'_extend_footprint_map_from_board',lambda *a,**k:{r:r for r in source.P})
    monkeypatch.setattr(synth,'_device_bypass_specs',lambda *a: {})
    monkeypatch.setattr(cec_pcb,'courtyard_bbox',lambda c,x,y,r:(x-.4,x+.4,y-.4,y+.4))
    candidates,report=restoration_candidates(cfg,source,max_candidates=3)
    assert len(candidates)==3 and len(report['reseating'])==2
    for result in candidates[1:]:
        a,b=result.P['SHUNT'],result.P['MONITOR']
        assert abs(b[0]-a[0]-2)<1e-6 and abs(b[1]-a[1])<1e-6
        assert result.P['UNRELATED']==source.P['UNRELATED']
        assert b[0]+.4<=10.9 or b[0]-.4>=13.1 or b[1]+.4<=10.9 or b[1]-.4>=13.1
        assert not result.blueprint_restore['admitted']
    cfg.pins={'SHUNT':source.P['SHUNT']}
    candidates,report=restoration_candidates(cfg,source)
    assert len(candidates)==1 and not report['reseating']
    cfg.pins={}
    source.noncontact_placement_contract={'immutable_refs':['SHUNT']}
    candidates,report=restoration_candidates(cfg,source)
    assert len(candidates)==1 and not report['reseating']
