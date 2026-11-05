"""Native source-complete bank refresh is not placement/current authority."""
import copy
import math
import pcbnew
import pytest
import cec_owned_pad_bank_refresh as refresh
import cec_pad_bank_collector as bank
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_pad_bank_collector import fixture, proposal


def make_case(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu):
    source,pads,tracks=fixture(angle,mirror,layer)
    p=proposal(source,pads,tracks,layer);emitted=bank.materialize(source,p)
    source.BuildConnectivity();assert pcbnew.ZONE_FILLER(source).Fill(source.Zones())
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),source)
    candidate=pcbnew.LoadBoard(str(path))
    motion=pcbnew.VECTOR2I(0,-1000000)
    for fp in candidate.GetFootprints():fp.Move(motion)
    for track in candidate.GetTracks():track.Move(motion)
    request=dict(zone_uuid=emitted['zone_uuid'],pad_uuids=[p.m_Uuid.AsString() for p in pads],
        support_track_uuids=[t.m_Uuid.AsString() for t in tracks],allow_locked_zone=True,
        allow_locked_track_uuids=[t.m_Uuid.AsString() for t in tracks])
    return source,candidate,request


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('extent',['pad_row','pad_row_and_retained_leads'])
def test_actual_saved_moved_row_refresh_is_source_complete(tmp_path,angle,mirror,layer,extent):
    source,candidate,request=make_case(tmp_path,angle,mirror,layer)
    before=copper_inventory(candidate)
    p=refresh.plan(source,candidate,**request,cover_extent=extent)
    assert copper_inventory(candidate)==before
    assert len(p['candidate_track_rows'])==2 and len(p['candidate_pad_rows'])==3
    assert not p['new_capacity_credited'] and not p['release_authority']
    refresh.materialize(candidate,p)
    assert len(list(candidate.GetTracks()))==2
    assert all(t.GetWidth()==3400000 for t in candidate.GetTracks())
    candidate.BuildConnectivity();assert pcbnew.ZONE_FILLER(candidate).Fill(candidate.Zones())
    path=tmp_path/'saved.kicad_pcb';pcbnew.SaveBoard(str(path),candidate)
    received=refresh.receive(source,pcbnew.LoadBoard(str(path)),p)
    assert received['ok'] and received['complete'],received
    assert not received['release_authority'] and not received['new_capacity_credited']
    if extent=='pad_row':
        # Leads remain actual copper outside a purposefully small landing.
        zone=refresh._zone(candidate,request['zone_uuid'])
        missing=owner._native_capsule(next(iter(candidate.GetTracks())))
        missing.BooleanSubtract(zone.Outline());assert missing.OutlineCount()


@pytest.mark.parametrize('fault',['omitted_pad','omitted_track','duplicate','missing',
    'source_unfilled','source_fill_loss','candidate_width','candidate_drill',
    'candidate_net','source_permission','extra_permission','foreign','not_row',
    'group','extent','nan','infinite'])
def test_refuses_bad_source_or_motion_without_mutation(tmp_path,fault):
    source,candidate,q=make_case(tmp_path)
    if fault=='omitted_pad':q['pad_uuids'].pop()
    elif fault=='omitted_track':q['support_track_uuids'].pop()
    elif fault=='duplicate':q['pad_uuids'][0]=q['pad_uuids'][1]
    elif fault=='missing':q['zone_uuid']='missing'
    elif fault=='source_unfilled':refresh._zone(source,q['zone_uuid']).UnFill()
    elif fault=='source_fill_loss':
        z=refresh._zone(source,q['zone_uuid']);fill=z.GetFilledPolysList(z.GetLayer()).CloneDropTriangulation()
        p=next(p for f in source.GetFootprints() for p in f.Pads())
        x,y=p.GetPosition();fill.BooleanSubtract(owner._poly([[x-100,y-100],[x+100,y-100],[x+100,y+100],[x-100,y+100]]))
        z.SetFilledPolysList(z.GetLayer(),fill)
    elif fault=='candidate_width':next(iter(candidate.GetTracks())).SetWidth(3399999)
    elif fault=='candidate_drill':next(p for f in candidate.GetFootprints() for p in f.Pads()).SetDrillSize(pcbnew.VECTOR2I(1700000,1700000))
    elif fault=='candidate_net':next(iter(candidate.GetTracks())).SetNetCode(0)
    elif fault=='source_permission':q['allow_locked_zone']=False
    elif fault=='extra_permission':q['allow_locked_track_uuids'].append('missing')
    elif fault=='foreign':
        n=pcbnew.NETINFO_ITEM(candidate,'/OTHER_RENAMED_NET');candidate.Add(n)
        t=pcbnew.PCB_TRACK(candidate);t.SetNet(n);t.SetLayer(pcbnew.F_Cu);t.SetWidth(100000)
        t.SetStart(pcbnew.VECTOR2I_MM(44.2,38.8));t.SetEnd(pcbnew.VECTOR2I_MM(44.2,39.2));candidate.Add(t)
    elif fault=='not_row':next(p for f in candidate.GetFootprints() for p in f.Pads()).Move(pcbnew.VECTOR2I(0,1))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(source);g.SetName('UNRELATED_TYPED_OWNER');source.Add(g);g.AddItem(next(iter(source.GetTracks())))
    elif fault=='extent':q['cover_extent']='anything'
    else:q['timeout_s']=math.nan if fault=='nan' else math.inf
    before=copper_inventory(candidate)
    with pytest.raises(refresh.owner.Refused):refresh.plan(source,candidate,**q)
    assert copper_inventory(candidate)==before


@pytest.mark.parametrize('fault',['rehash_polygon','rehash_fill','rehash_authority','rehash_extent',
    'rehash_rows','extra_field','saved_unfilled','saved_thermal','source_unfilled','source_changed'])
def test_independent_saved_receiving_refuses_forged_or_stale_bank(tmp_path,fault):
    source,candidate,q=make_case(tmp_path)
    p=refresh.plan(source,candidate,**q,cover_extent='pad_row')
    refresh.materialize(candidate,p);candidate.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(candidate).Fill(candidate.Zones())
    z=refresh._zone(candidate,q['zone_uuid'])
    if fault.startswith('rehash_'):
        p=copy.deepcopy(p)
        if fault=='rehash_polygon':p['polygon_nm'][0][0]+=1
        elif fault=='rehash_fill':p['fill_envelope_nm'][0][0]+=1
        elif fault=='rehash_authority':p['new_capacity_credited']=True
        elif fault=='rehash_extent':p['cover_extent']='pad_row_and_retained_leads'
        else:p['source_track_rows'][0]['width_nm']+=1
        p.pop('plan_sha256');p['plan_sha256']=owner._digest(p)
        before=copper_inventory(candidate)
        with pytest.raises(refresh.owner.Refused):refresh.materialize(candidate,p)
        assert copper_inventory(candidate)==before
    elif fault=='extra_field':p['current_capacity_authority']=True
    elif fault=='saved_unfilled':z.UnFill()
    elif fault=='saved_thermal':z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault=='source_unfilled':refresh._zone(source,q['zone_uuid']).UnFill()
    else:next(iter(source.GetTracks())).SetWidth(3400001)
    result=refresh.receive(source,candidate,p)
    assert not result['ok'] and not result['complete'] and result['errors']
