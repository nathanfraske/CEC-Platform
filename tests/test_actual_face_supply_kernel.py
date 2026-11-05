"""Inner pickup removal uses its actual floor and keeps current/pour roots."""
import copy,json
from pathlib import Path
import pcbnew,pytest
import cec_actual_face_supply_kernel as repair
import cec_force_current as force
import cec_field_coupling as field
from test_supply_kernel_reembedding import case as outer_case
from test_field_proposals import track


def case(tmp_path,monkeypatch,quarter=0,back=False):
    source,args,contract,domain=outer_case(tmp_path,monkeypatch,quarter,back)
    b=pcbnew.LoadBoard(str(source));face=pcbnew.In3_Cu if back else pcbnew.In2_Cu
    contract['routing_layers']+=['In2.Cu','In3.Cu']
    contract['required_by_layer_mm'].update({'In2.Cu':3.5,'In3.Cu':3.5})
    for t in b.GetTracks():
        if force._uid(t) in args['retired_track_uuids']:t.SetLayer(face)
    field._save_field_snapshot(b,source)
    return source,args,contract,domain


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_inner_floor_discovery_and_exact_saved_outer_reembedding(tmp_path,monkeypatch,quarter,back):
    source,args,contract,domain=case(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes();budget=copy.deepcopy(contract)
    found=repair.discover(source,board_hint='opaque',seed_track_uuids=args['retired_track_uuids'],allow_locked_source=True)
    assert len(found['kernels'])==1 and not found['refusals']
    assert found['kernels'][0]['retired_track_uuids']==sorted(args['retired_track_uuids'])
    proposal=repair.plan(source,**args)
    assert set(proposal['actual_source_face_floor_by_track_nm'].values())=={3500000}
    assert proposal['actual_current_factory_floor_nm']==500000
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    proof=repair.receive(source,child,proposal,board_hint='opaque')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['actual_source_face_floors_rederived'] and proof['all_old_current_sized_joins_preserved']
    assert proof['reference_face_tracks_and_retained_current_barrel_roots_unchanged']
    assert all(q['all_actual_terminals_definitely_connected'] for q in proof['actual_drilled_terminal_graphs'])
    assert not proof['current_or_barrel_qualified'] and not proof['new_capacity_credited']
    assert not proof['source_current_reduced'] and contract==budget and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['unbudgeted_face','reference_face','missing_face_floor','already_sized',
    'outer_destination_underfloor','inner_destination','implicit_lock','changed_budget'])
def test_inner_origin_never_grants_a_source_floor_or_current_waiver(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    old=[t for t in b.GetTracks() if force._uid(t) in args['retired_track_uuids']]
    if fault=='unbudgeted_face':contract['routing_layers'].remove('In2.Cu')
    elif fault=='reference_face':
        for t in old:t.SetLayer(pcbnew.In1_Cu)
        contract['required_by_layer_mm']['In1.Cu']=3.5
    elif fault=='missing_face_floor':del contract['required_by_layer_mm']['In2.Cu']
    elif fault=='already_sized':old[0].SetWidth(3500000)
    elif fault=='outer_destination_underfloor':args['width_nm']=499999
    elif fault=='inner_destination':args['layer']=int(pcbnew.In3_Cu)
    elif fault=='implicit_lock':args['allow_locked_source']=False
    elif fault=='changed_budget':contract['current_authority']['source']='guessed'
    field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,TypeError)):repair.plan(source,**args)


@pytest.mark.parametrize('kind',['rated_track','saved_pour'])
def test_ungrouped_barrels_on_existing_full_current_or_pour_material_are_immutable_roots(tmp_path,monkeypatch,kind):
    source,args,contract,domain=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    v=next(t for t in b.GetTracks() if force._uid(t)==args['retired_via_uuids'][0]);at=v.GetPosition()
    if kind=='rated_track':
        t=track(b,contract['net'],(at.x/1e6,at.y/1e6),(at.x/1e6+1.,at.y/1e6),width=1.)
        t.SetLayer(pcbnew.B_Cu)
    else:
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet(contract['net']));z.SetLayer(pcbnew.B_Cu);z.Outline().NewOutline()
        for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]:z.Outline().Append(at.x+x*1000000,at.y+y*1000000)
        z.SetFilledPolysList(pcbnew.B_Cu,z.Outline());z.SetIsFilled(True);b.Add(z)
    assert repair.retained_supply_barrel_root(b,v,source,contract)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='immutable_root'):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['new_width','source_reference','root_drill','new_zone','plan_source_floor','rules'])
def test_saved_receiving_rederives_actual_source_and_refuses_collateral_changes(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);proposal=json.loads(json.dumps(repair.plan(source,**args)))
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='new_width':t.SetWidth(t.GetWidth()-1)
    elif fault=='source_reference':
        parent=pcbnew.LoadBoard(str(source));next(t for t in parent.GetTracks() if force._uid(t) in args['retired_track_uuids']).SetLayer(pcbnew.In1_Cu)
        field._save_field_snapshot(parent,source)
    elif fault=='root_drill':next(v for v in b.GetTracks() if force._uid(v)==args['end_uuid']).SetDrill(450000)
    elif fault=='new_zone':
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet(contract['net']));z.SetLayer(pcbnew.B_Cu);z.Outline().NewOutline()
        for p in [(-1000000,-1000000),(0,-1000000),(0,0),(-1000000,0)]:z.Outline().Append(*p)
        b.Add(z)
    elif fault=='plan_source_floor':proposal['actual_source_face_floor_by_track_nm'][args['retired_track_uuids'][0]]=1
    elif fault=='rules':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    field._save_field_snapshot(b,child)
    proof=repair.receive(source,child,proposal,board_hint='opaque')
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']
