"""Necessary GND branches have positive ownership, exact ports and no mesh waiver."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_ground_span_reflow as redundant
import cec_native_ground_terminal_branch as op
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,locked=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for name in ('GND','+3V3'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    # Synthetic .20 mm Source class is explicit, not the mutable default
    # NETCLASS proxy left by an unrelated .50/.90 mm mesh fixture.
    b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(200000)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return (round(x*1e6),round(y*1e6))
    def part(ref,value,entries):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);fp.SetLayer(layer);b.Add(fp)
        for pin,net,x,y in entries:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNetCode(b.GetNetcodeFromNetname(net))
            p.SetPosition(pcbnew.VECTOR2I(*point(x,y)));p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers);fp.Add(p)
        return fp
    root=part('TOTALLY_RENAMED_SENSOR','INA238',[('6','+3V3',8,7.2),('7','GND',8,8)])
    cap=part('C_UNRELATED_REFERENCE','100nF',[('1','+3V3',9.5,7.2),('2','GND',9.5,8)])
    def edge(net,a,z,width=.2):
        return track(b,net,[v/1e6 for v in point(*a)],[v/1e6 for v in point(*z)],layer=layer,width=width)
    edge('+3V3',(8,7.2),(9.5,7.2));edge('GND',(8,8),(9.5,8))
    source_points=[(8,8),(8,10),(10,12),(12,12)]
    edges=[edge('GND',a,z) for a,z in zip(source_points,source_points[1:])]
    for t in edges:t.SetLocked(locked)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I(*point(12,12)))
    via.SetNet(b.FindNet('GND'));via.SetWidth(600000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face);z.SetLocalClearance(200000)
        z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    additive._ground_refill(b)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    points=sorted((list(point(8,8)),list(point(12,12))))
    return b,source,[force._uid(t) for t in edges],points,root,cap,via


def proposal(b,ids,points):
    live={force._uid(t):t for t in b.GetTracks()}
    return op.plan(b,ids,points,allow_locked_track_uuids=[u for u in ids if live[u].IsLocked()])


def construct(tmp_path,**options):
    b,source,ids,points,*_=fixture(tmp_path,**options)
    q=proposal(b,ids,points);added=op.materialize(b,q)
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child')
    field._save_field_snapshot(b,child)
    return source,child,q,added


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('locked',[False,True])
def test_necessary_selected_ground_branch_reconnects_every_real_terminal_and_keeps_process(tmp_path,quarter,mirror,layer,locked):
    source,child,q,added=construct(tmp_path,quarter=quarter,mirror=mirror,layer=layer,locked=locked)
    before=source.read_bytes();r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert not r['source_span_already_redundant_to_retained_native_copper']
    assert r['every_surviving_native_conductor_partition_identical']
    assert r['every_source_retained_contact_and_proved_ground_return_preserved']
    assert r['source_length_nm']>r['replacement_length_nm']
    assert len(added)==1 and len(q['retired_track_uuids'])==3
    assert source.read_bytes()==before and not r['current_qualified'] and not r['release_authority']
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if force._uid(t) in added)
    assert t.GetWidth()==200000 and t.GetLayer()==layer and bool(t.IsLocked())==locked
    old=redundant.receive(source,child,op._base(q),board_hint='synthetic')
    assert not old['ok'] and any('not_already_native_plane_redundant' in e for e in old['errors'])


@pytest.mark.parametrize('fault',['unknown_owner','converter','power_return','no_bypass','bulk',
    'other_pad','plated_pad','retained_barrel','no_planes','one_plane','grouped_branch','mixed_lock',
    'wide','port','hard90','diagonal','mask','no_lock_authority','deadline','extra_length'])
def test_source_selection_is_positive_bounded_and_never_permission_to_cut_a_ground_mesh(tmp_path,fault):
    b,source,ids,points,owner,cap,via=fixture(tmp_path,locked=True)
    root=owner.FindPadByNumber('7');extra={}
    if fault=='unknown_owner':owner.SetValue('UNKNOWN_IC')
    elif fault=='converter':owner.SetValue('TPS2121RUXR')
    elif fault=='power_return':owner.SetValue('TLV7011DBVR');root.SetNumber('2')
    elif fault=='no_bypass':b.Remove(cap)
    elif fault=='bulk':cap.SetValue('2200uF')
    elif fault=='other_pad':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('OTHER_GROUND_LOAD');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet('GND'));p.SetPosition(root.GetPosition())
        p.SetSize(pcbnew.VECTOR2I_MM(.2,.2));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    elif fault=='plated_pad':root.SetAttribute(pcbnew.PAD_ATTRIB_PTH);root.SetDrillSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='retained_barrel':
        item=via.Duplicate();item.m_Uuid.Clone(pcbnew.KIID());item.SetPosition(root.GetPosition());b.Add(item)
    elif fault=='no_planes':
        for z in list(b.Zones()):b.Remove(z)
    elif fault=='one_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='grouped_branch':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED_RETURN');b.Add(g)
        g.AddItem(next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND' and force._uid(t) not in ids))
    elif fault=='mixed_lock':next(t for t in b.GetTracks() if force._uid(t)==ids[0]).SetLocked(False)
    elif fault=='wide':next(t for t in b.GetTracks() if force._uid(t)==ids[0]).SetWidth(500000)
    elif fault=='port':points[0][0]+=1
    elif fault=='hard90':points=[[8000000,8000000],[8000000,12000000],[12000000,12000000]]
    elif fault=='diagonal':points=[[8000000,8000000],[12000000,11999999],[12000000,12000000]]
    elif fault=='mask':next(t for t in b.GetTracks() if force._uid(t)==ids[0]).SetHasSolderMask(True)
    elif fault=='deadline':extra['timeout_s']=0
    elif fault=='extra_length':extra['maximum_extra_nm']=1
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        op.plan(b,ids,points,allow_locked_track_uuids=[] if fault=='no_lock_authority' else ids,**extra)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['forged_kernel','missing_contract','changed_lock','width','face','pad','via',
    'source_zone','extra_cut','extra_track','new_contact','changed_endpoint'])
def test_independent_saved_receiver_rejects_a_forged_scope_or_unowned_saved_delta(tmp_path,fault):
    source,child,q,added=construct(tmp_path,locked=True)
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if force._uid(t) in added)
    if fault=='forged_kernel':q=copy.deepcopy(q);q['necessary_branch']['owner_pad_uuid']='arbitrary'
    elif fault=='missing_contract':q=op._base(q)
    elif fault=='changed_lock':t.SetLocked(False)
    elif fault=='width':t.SetWidth(210000)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='pad':next(p for fp in b.GetFootprints() for p in fp.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='via':next(i for i in b.GetTracks() if i.GetClass()=='PCB_VIA').SetDrill(250000)
    elif fault=='source_zone':b.Remove(next(iter(b.Zones())))
    elif fault=='extra_cut':discard_items(b,[next(i for i in b.GetTracks() if i.GetNetname()=='+3V3')])
    elif fault in ('extra_track','new_contact'):track(b,'GND',(8,8),(8.4,8.4),width=.2)
    else:t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,child);r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert not r['release_authority']


@pytest.mark.parametrize('value',[None,0,1,'yes'])
def test_necessary_stage_contract_requires_a_literal_boolean(tmp_path,value):
    import cec_native_ground_chain_shortening as stage
    b,source,*_=fixture(tmp_path)
    with pytest.raises(ValueError):stage.run(source,tmp_path/'out',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=tmp_path/'unused',necessary_branch=value)
    assert not (tmp_path/'out').exists()
def test_ground_parts_never_use_whole_zone_seed_for_two_fill_polygons():
    from test_native_zone_islands import fixture as zone_fixture
    import time
    import cec_force_current as force
    b,z=zone_fixture()
    z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-000000000001'))
    live,parts=op._ground_parts(b,set(),time.monotonic()+5.)
    assert len(parts)==2
    assert sum(i.GetClass()=='ZONE'for i in live.values())==2
