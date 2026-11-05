"""One necessary ordinary GND mesh entry, never a power/current/locality grant."""
import time
import json
import pcbnew
import pytest
import cec_ground_mesh_entry as op
import cec_ground_component_join as tracks_only
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_fab_profile as fab
import cec_decoupler_cell as cells
from cec_native_items import discard_items
from test_ground_component_join import fixture as base_fixture
from test_field_proposals import track


@pytest.mark.parametrize('now,deadline,remaining,expected',[
    (10.,20.,1,20.),(10.,20.,2,15.),(15.,20.,5,16.),(21.,20.,2,20.)])
def test_actual_ground_island_lease_shares_remaining_wall_without_extension(monkeypatch,now,deadline,remaining,expected):
    monkeypatch.setattr(op.time,'monotonic',lambda:now)
    assert op._island_deadline(deadline,remaining)==expected


@pytest.mark.parametrize('remaining',[0,-1,True,1.5])
def test_ground_lease_requires_actual_positive_remaining_island_count(remaining):
    with pytest.raises(ValueError):op._island_deadline(time.monotonic()+10.,remaining)


def fixture(tmp_path,*,quarter=0,layer=pcbnew.F_Cu,barrier=True):
    b,source,owner,cap,via=base_fixture(tmp_path,quarter=quarter,layer=layer)
    b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND':t.SetWidth(500000)
    if barrier:
        at=cap.FindPadByNumber('2').GetPosition();root=via.GetPosition()
        bar=pcbnew.ZONE(b);bar.SetLayer(layer);bar.SetNet(b.FindNet('+3V3'));bar.SetLocalClearance(200000);bar.SetMinThickness(100000)
        if quarter%2==0:
            axis=(at.x+root.x)//2;coords=[(axis-250000,500000),(axis+250000,500000),(axis+250000,29500000),(axis-250000,29500000)]
        else:
            axis=(at.y+root.y)//2;coords=[(500000,axis-250000),(29500000,axis-250000),(29500000,axis+250000),(500000,axis+250000)]
        p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
        for x,y in coords:p.Append(x,y)
        bar.Outline().Append(p);bar.SetFilledPolysList(layer,p);bar.SetIsFilled(True);b.Add(bar)
    settings={'net_settings':{'classes':[{'name':'Default','track_width':.5,'clearance':.2,'via_diameter':.9,'via_drill':.5}]}}
    source.with_suffix('.kicad_pro').write_text(json.dumps(settings))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    # The producer must read the SAME saved ordinary geometry as receiving,
    # not the detached native board's unrelated process-wide Default.
    b.SetFileName(str(source))
    return b,source,owner,cap,via


def construct(tmp_path,**options):
    b,source,*_=fixture(tmp_path,**options);before=source.read_bytes()
    q=op.plan(b,board_hint='synthetic',timeout_s=10.,radius_mm=8.,max_sites=12)
    assert q['complete'],q
    old={force._uid(t)for t in b.GetTracks()};op.construct_private(b,q,board_hint='synthetic')
    added=[t for t in b.GetTracks()if force._uid(t)not in old]
    assert sum(t.GetClass()=='PCB_VIA'for t in added)==1
    assert all(t.GetNetname()=='GND'for t in added)
    child=force._copy_family(source,tmp_path/'mesh-child')
    import cec_additive_pair_repair as producer
    producer.save_native_additions(child,b,{},old,board_hint='synthetic')
    assert source.read_bytes()==before
    return source,child,q,{force._uid(t)for t in added}


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_native_new_entry_really_crosses_reference_not_surface_power_bar(tmp_path,quarter,layer):
    source,child,q,added=construct(tmp_path,quarter=quarter,layer=layer);before=source.read_bytes()
    result=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert result['ok']and result['complete'],result
    assert not result.get('current_qualified',False)and not result.get('release_authority',False)
    assert source.read_bytes()==before
    # This public pre-existing receiver must stay tracks-only.
    assert not tracks_only.receive(source,child,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',['extra_via','small_via','foreign_via','partial_pad','one_plane','source_overwrite','no_via','extra_foreign'])
def test_saved_mesh_cannot_expand_scope_or_skip_native_process_and_source(tmp_path,fault):
    source,child,q,ids=construct(tmp_path);b=pcbnew.LoadBoard(str(child))
    new=[t for t in b.GetTracks()if force._uid(t)in ids];via=next(t for t in new if t.GetClass()=='PCB_VIA')
    if fault=='extra_via':
        other=via.Duplicate();other.m_Uuid.Clone(pcbnew.KIID());other.Move(pcbnew.VECTOR2I_MM(1,0));b.Add(other)
    elif fault=='small_via':via.SetWidth(350000);via.SetDrill(250000)
    elif fault=='foreign_via':via.SetNet(b.FindNet('+3V3'))
    elif fault=='partial_pad':
        p=b.FindFootprintByReference('TOTALLY_RENAMED_SENSOR').FindPadByNumber('7');via.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(.2,0))
    elif fault=='one_plane':
        zone=next(z for z in b.Zones()if z.GetNetname()=='GND');zone.UnFill()
    elif fault=='source_overwrite':
        next(t for t in b.GetTracks()if force._uid(t)not in ids and t.GetClass()=='PCB_TRACK').SetWidth(123456)
    elif fault=='no_via':discard_items(b,[via])
    else:
        track(b,'+3V3',(2,2),(3,2),width=.5)
    if fault=='foreign_via':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),b)
    else:field._save_field_snapshot(b,child)
    result=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert not result['ok']and not result['complete'],result


@pytest.mark.parametrize('fault',['unknown_owner','converter','no_planes','one_plane'])
def test_mesh_source_kernel_must_be_positive_and_all_reference_planes_present(tmp_path,fault):
    b,source,owner,cap,via=fixture(tmp_path)
    if fault=='unknown_owner':owner.SetValue('UNMODELED')
    elif fault=='converter':owner.SetValue('TPS2121RUXR')
    else:
        zones=[z for z in b.Zones()if z.GetNetname()=='GND']
        for z in zones if fault=='no_planes'else zones[:1]:discard_items(b,[z])
    before=field._field_snapshot_inventory(b)
    try:result=op.plan(b,board_hint='synthetic',timeout_s=2.,radius_mm=8.,max_sites=12)
    except ValueError:result={'complete':False}
    assert not result['complete'],result
    assert before==field._field_snapshot_inventory(b)


def test_new_via_must_be_necessary_not_an_extra_rooted_stitch(tmp_path):
    b,source,owner,cap,oldvia=fixture(tmp_path,barrier=False)
    q=tracks_only.plan(b,board_hint='synthetic',timeout_s=10.);assert q['complete'],q
    old={force._uid(t)for t in b.GetTracks()};tracks_only.construct_private(b,q,board_hint='synthetic')
    spec=cells._netclass(b,'GND');dia,drill,_=fab.board_legal_through_via_geometry(b,max(.6,spec['via_dia']),max(.3,spec['via_drill']))
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(oldvia.GetPosition()+pcbnew.VECTOR2I_MM(2,0));via.SetWidth(round(dia*1e6));via.SetDrill(round(drill*1e6));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    child=force._copy_family(source,tmp_path/'redundant-child')
    import cec_additive_pair_repair as producer
    producer.save_native_additions(child,b,{},old,board_hint='synthetic')
    result=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert not result['ok']and not result['complete'],result


@pytest.mark.parametrize('kwargs',[{'timeout_s':True},{'timeout_s':0},{'radius_mm':9},{'radius_mm':float('nan')},{'max_sites':True},{'max_sites':13},{'obstacle_aware':1}])
def test_proposal_work_and_geometry_are_explicitly_bounded(tmp_path,kwargs):
    b,source,*_=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(b,board_hint='synthetic',**kwargs)


@pytest.mark.parametrize('quarter,layer',[(0,pcbnew.F_Cu),(1,pcbnew.B_Cu)])
def test_real_obstacle_snake_reaches_same_ordinary_mesh_seat_without_relaxing_receiving(tmp_path,monkeypatch,quarter,layer):
    b,source,owner,cap,via=fixture(tmp_path,quarter=quarter,layer=layer,barrier=False)
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=20-y,x
        return x,y
    # The reused fixture adds its root trunk after rotating its terminals;
    # rotate that authored trunk too, so this is one rigid test geometry.
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND' and t.GetStart()==via.GetPosition():
            t.SetEnd(pcbnew.VECTOR2I_MM(*xy((14,12))))
    # Alternating literal foreign walls require a multi-turn escape. The
    # frontier fixture only fixes a proposed seat, never a geometry verdict.
    track(b,'+3V3',xy((1,9.5)),xy((10,9.5)),layer=layer,width=.5)
    track(b,'+3V3',xy((9,11)),xy((29,11)),layer=layer,width=.5)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    seat=tuple(pcbnew.VECTOR2I_MM(*xy((8,12))))
    monkeypatch.setattr(op.frontier,'sites',lambda *args,**kwargs:{'sites_nm':[seat]})
    original=field._field_snapshot_inventory(b);literal=source.read_bytes()
    flat=op.plan(b,board_hint='synthetic',timeout_s=10.)
    assert not flat['complete'] and not flat.get('error'),flat
    q=op.plan(b,board_hint='synthetic',timeout_s=10.,obstacle_aware=True)
    assert q['complete'] and any(t.get('obstacle_path_attempts',0)>0 for t in q['trials']),q
    assert field._field_snapshot_inventory(b)==original and source.read_bytes()==literal
    old={force._uid(t)for t in b.GetTracks()};op.construct_private(b,q,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'obstacle-child')
    import cec_additive_pair_repair as producer
    producer.save_native_additions(child,b,{},old,board_hint='synthetic')
    received=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert received['ok'] and received['complete'],received
    assert not received.get('current_qualified',False) and not received['release_authority']


def test_one_exhausted_island_does_not_hide_later_real_native_join(tmp_path,monkeypatch):
    b,source,owner,cap,via=fixture(tmp_path,barrier=False)
    def part(ref,value,entries):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);b.Add(fp)
        for pin,net,x,y in entries:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(b.FindNet(net))
            p.SetPosition(pcbnew.VECTOR2I_MM(x,y));p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetShape(pcbnew.PAD_SHAPE_RECT);fp.Add(p)
        return fp
    part('U_NEXT','INA238',[('6','+3V3',18,7.2),('7','GND',18,8)])
    part('C_NEXT','100nF',[('1','+3V3',19.5,7.2),('2','GND',19.5,8)])
    track(b,'+3V3',(18,7.2),(19.5,7.2),width=.5)
    track(b,'GND',(18,8),(19.5,8),width=.5)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    context=tracks_only._context(b,'synthetic',time.monotonic()+10.)
    assert len(context['islands'])==2
    # Model one slow finite frontier without mocking any accepting geometry
    # or receiving predicate. The short lease makes this deterministic and
    # fast; the pure share tests above check the real allocation formula.
    native_frontier=op.frontier.sites;native_lease=op._island_deadline
    def lease(deadline,remaining):
        return min(deadline,time.monotonic()+.01) if remaining==2 else native_lease(deadline,remaining)
    called=[]
    def frontier(*args,**kw):
        called.append(tuple(args[2]))
        if len(called)==1:
            time.sleep(max(0.,kw['deadline']-time.monotonic())+.002)
            return {'sites_nm':[]}
        return native_frontier(*args,**kw)
    monkeypatch.setattr(op,'_island_deadline',lease);monkeypatch.setattr(op.frontier,'sites',frontier)
    literal=source.read_bytes();q=op.plan(b,board_hint='synthetic',timeout_s=10.,obstacle_aware=True)
    assert q['complete'] and len(q['island_leases'])==2,q
    assert q['island_leases'][0]['lease_exhausted'] and not q['island_leases'][0]['complete']
    assert q['island_leases'][1]['complete'] and len(called)>=2
    assert source.read_bytes()==literal
    old={force._uid(t)for t in b.GetTracks()};op.construct_private(b,q,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'fair-child')
    import cec_additive_pair_repair as producer
    producer.save_native_additions(child,b,{},old,board_hint='synthetic')
    received=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert received['ok'] and received['complete'],received
