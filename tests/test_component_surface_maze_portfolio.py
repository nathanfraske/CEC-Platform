"""Actual connected contacts get surface detail without new authority."""
import math,time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_native_component_ports as ports
from test_field_proposals import track
from test_local_supply_native_detours import source,menu


def alternate_fixture(monkeypatch,quarter=0,back=False):
    b,request,obstacle,contract=source(monkeypatch,quarter,back);request['kind']='source_boundary'
    a=tuple(request['a']['at_nm']);z=tuple(request['b']['at_nm']);dx,dy=z[0]-a[0],z[1]-a[1]
    at=(a[0]-dy,a[1]+dx);face=request['a']['layers'][0]
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('INDEPENDENT_CONNECTED_CONTACT');fp.SetLayer(face);b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetPosition(pcbnew.VECTOR2I(*at))
    pad.SetSize(pcbnew.VECTOR2I(600000,600000));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetNet(b.FindNet(request['net']))
    ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls);fp.Add(pad)
    vias=[]
    for point in (a,at):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I(*point));v.SetNet(pad.GetNet())
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);vias.append(v)
    other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    track(b,request['net'],[v/1e6 for v in a],[v/1e6 for v in at],width=.25,layer=other)
    return b,request,pad,vias,contract


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('kind',['source_boundary','ground_boundary'])
def test_an_existing_surface_offer_does_not_starve_real_contact_detail(monkeypatch,quarter,back,kind):
    b,request,pad,vias,contract=alternate_fixture(monkeypatch,quarter,back)
    if kind=='ground_boundary':
        old=b.GetNetcodeFromNetname(request['net']);net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
        for item in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:
            if item.GetNetCode()==old:item.SetNet(net)
        request.update(kind=kind,net='GND',width_nm=250000,retained_source_ground_fragment=dict(
            actual_fixed_source_contacts_not_same_net_proximity=True,
            whole_original_current_plane_and_saved_partition_receiving_required=True))
        request.pop('unchanged_full_rail_current_contract')
    original=escape.fr._guarded_profiled_lastmile_legs;calls=[]
    def native(*args,**kwargs):
        calls.append((tuple(args[1]),tuple(args[2]),kwargs['deadline_monotonic']))
        if tuple(args[1])==tuple(request['a']['at_nm']):return []
        return original(*args,**kwargs)
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',native)
    monkeypatch.setattr(escape.fr,'_lastmile_bridge',lambda *args,**kwargs:None)
    before=row._source_binding(b);start=time.monotonic();choices,detail=menu(b,request,seconds=3.)
    assert calls and any(a==tuple(pad.GetPosition()) for a,z,d in calls)
    trials=detail['source_boundary_surface_trials']
    assert any(q['found'] and not q['original_named_pair'] for q in trials),detail
    wanted=[q for q in choices if q and tuple(q[0][1])==tuple(pad.GetPosition())]
    assert wanted and all(op[0]=='trk' and op[3]==250000 and op[4]==request['a']['layers'][0]
        for ops in wanted for op in ops)
    assert all(tuple(ops[-1][2])==tuple(request['b']['at_nm']) for ops in wanted)
    assert all(d<=start+3.+.01 for a,z,d in calls)
    assert detail['original_component_and_bridge_pairs_retained']
    assert row._source_binding(b)==before


@pytest.mark.parametrize('fault',['thin','start','end','non45','too_long','disconnected'])
@pytest.mark.parametrize('kind',['source_boundary','ground_boundary'])
def test_alternate_contact_cannot_weaken_exact_width_path_or_named_obligation(monkeypatch,fault,kind):
    b,request,pad,vias,contract=alternate_fixture(monkeypatch);calls=[]
    if kind=='ground_boundary':
        old=b.GetNetcodeFromNetname(request['net']);net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
        for item in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:
            if item.GetNetCode()==old:item.SetNet(net)
        request.update(kind=kind,net='GND',width_nm=250000,retained_source_ground_fragment=dict(
            actual_fixed_source_contacts_not_same_net_proximity=True,
            whole_original_current_plane_and_saved_partition_receiving_required=True))
        request.pop('unchanged_full_rail_current_contract')
    def malicious(*args,**kwargs):
        a,z=args[1],args[2];calls.append(tuple(a));width=args[3]
        if tuple(a)==tuple(request['a']['at_nm']):return []
        legs=[(a,z,width)]
        if fault=='thin':legs=[(a,z,width-1)]
        elif fault=='start':legs=[(pcbnew.VECTOR2I(a.x+1,a.y),z,width)]
        elif fault=='end':legs=[(a,pcbnew.VECTOR2I(z.x+1,z.y),width)]
        elif fault=='non45':
            p=pcbnew.VECTOR2I(a.x+1000000,a.y+100000);legs=[(a,p,width),(p,z,width)]
        elif fault=='too_long':
            p=pcbnew.VECTOR2I(a.x,a.y+20000000);q=pcbnew.VECTOR2I(z.x,p.y)
            legs=[(a,p,width),(p,q,width),(q,z,width)]
        else:legs=[(a,pcbnew.VECTOR2I(a.x,a.y+100000),width),(pcbnew.VECTOR2I(a.x,a.y+200000),z,width)]
        return legs
    monkeypatch.setattr(escape.fr,'_guarded_profiled_lastmile_legs',malicious)
    monkeypatch.setattr(escape.fr,'_lastmile_bridge',lambda *args,**kwargs:None)
    _,detail=menu(b,request)
    assert calls and all(not q['found'] for q in detail['source_boundary_surface_trials'])


def test_land_and_plated_priority_describes_the_changed_contact_not_the_fixed_target(monkeypatch):
    b,request,pad,vias,contract=alternate_fixture(monkeypatch)
    original=(request['a'],request['b']);z=request['b'];face=z['layers'][0]
    aliases=[]
    # A borrowed fixed target being a PAD must not label every track alias
    # on the other side as an actual alternative native land.
    for i in range(12):
        t=track(b,request['net'],(11.8+i*.001,12),(11.801+i*.001,12),width=.25,layer=face)
        aliases.append((dict(at_nm=list(t.GetStart()),layers=[face],native_uuids=[force._uid(t)]),z))
    land=(dict(at_nm=list(pad.GetPosition()),layers=[face],pad_uuid=force._uid(pad),native_uuids=[force._uid(pad)]),z)
    via=vias[1];barrel=(dict(at_nm=list(via.GetPosition()),layers=list(map(int,via.GetLayerSet().CuStack())),native_uuids=[force._uid(via)]),z)
    before=row._source_binding(b);rows=[original,*aliases,land,barrel]
    chosen=ports.surface_maze_pairs(b,rows,limit=3)
    assert chosen==[original,land,barrel] and rows==[original,*aliases,land,barrel]
    assert row._source_binding(b)==before


@pytest.mark.parametrize('limit',[0,9,True,None])
def test_unbounded_contact_scheduling_is_not_source_authority(monkeypatch,limit):
    b,request,*_=alternate_fixture(monkeypatch)
    with pytest.raises(ValueError):ports.surface_maze_pairs(b,[(request['a'],request['b'])],limit=limit)


@pytest.mark.parametrize('fault',['missing_contact','fractional_point','no_layers','not_pair'])
def test_contact_scheduler_does_not_rank_forged_or_nonexact_native_geometry(monkeypatch,fault):
    b,request,*_=alternate_fixture(monkeypatch);end=dict(request['a']);pair=(end,request['b'])
    if fault=='missing_contact':end['native_uuids']=['not_a_native_contact']
    elif fault=='fractional_point':end['at_nm']=[.1,10000000]
    elif fault=='no_layers':end['layers']=[]
    else:pair=(end,)
    with pytest.raises(ValueError):ports.surface_maze_pairs(b,[pair])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_common_face_access_is_not_starved_by_expanded_fixed_barrel_aliases(monkeypatch,quarter,back):
    b,request,pad,vias,contract=alternate_fixture(monkeypatch,quarter,back)
    face=pcbnew.In2_Cu;other=pcbnew.In3_Cu
    z=pcbnew.PCB_VIA(b);z.SetPosition(pcbnew.VECTOR2I(*request['b']['at_nm']))
    z.SetNet(b.FindNet(request['net']));z.SetWidth(600000);z.SetDrill(300000)
    z.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(z)
    a0=dict(at_nm=list(vias[0].GetPosition()),layers=[int(face)],native_uuids=[force._uid(vias[0])])
    b0=dict(at_nm=list(z.GetPosition()),layers=[int(face)],native_uuids=[force._uid(z)])
    expanded=dict(b0,layers=list(map(int,z.GetLayerSet().CuStack())))
    aliases=[]
    for i in range(12):
        at=tuple(vias[0].GetPosition());end=(at[0]+10000+i,at[1])
        t=track(b,request['net'],[v/1e6 for v in at],[v/1e6 for v in end],width=.25,layer=face)
        aliases.append((dict(at_nm=list(t.GetEnd()),layers=[int(face)],native_uuids=[force._uid(t)]),expanded))
    actual=(dict(a0,layers=list(map(int,vias[0].GetLayerSet().CuStack()))),expanded)
    pairs=[(a0,b0),*aliases,actual];before=row._source_binding(b)
    selected=ports.surface_maze_pairs(b,pairs,limit=3,route_layers=[int(face),int(other)])
    assert selected[0]==pairs[0] and actual in selected
    assert any(other in x['layers'] and other in y['layers'] for x,y in selected)
    assert row._source_binding(b)==before and pairs[-1]==actual


@pytest.mark.parametrize('layers',[True,[],[999],[0,0],[False],[0.,2]])
def test_surface_layer_scheduling_requires_explicit_actual_bounded_faces(monkeypatch,layers):
    b,request,*_=alternate_fixture(monkeypatch)
    with pytest.raises(ValueError,match='surface_search_layers'):
        ports.surface_maze_pairs(b,[(request['a'],request['b'])],route_layers=layers)
