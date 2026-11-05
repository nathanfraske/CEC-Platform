"""Literal source-ground slides, never refdes/board-specific placement rules."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_retained_ground_land_slide as op
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,via_distance=2.):
    b=_board([],edge=(0,0,24,24));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for net in ('GND','+3V3'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('C_OTHER_DESIGN');fp.SetValue('100nF');fp.SetLayer(layer)
    fp.SetPosition(pcbnew.VECTOR2I_MM(8,8));b.Add(fp)
    for pin,net,x in [('1','+3V3',7),('2','GND',9)]:
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(b.FindNet(net));p.SetPosition(pcbnew.VECTOR2I_MM(x,8))
        p.SetSize(pcbnew.VECTOR2I_MM(1.,1.45));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        mask=pcbnew.LSET();mask.AddLayer(layer);p.SetLayerSet(mask);fp.Add(p)
    court=pcbnew.PCB_SHAPE(fp);court.SetShape(pcbnew.SHAPE_T_RECT)
    court.SetStart(pcbnew.VECTOR2I_MM(6.4,7.1));court.SetEnd(pcbnew.VECTOR2I_MM(9.6,8.9))
    court.SetLayer(pcbnew.F_CrtYd if layer==pcbnew.F_Cu else pcbnew.B_CrtYd);court.SetWidth(50000);fp.Add(court)
    supply=track(b,'+3V3',(5,8),(7,8),width=.2,layer=layer)
    lead=track(b,'GND',(9,8),(9+via_distance,8),width=.2,layer=layer)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(9+via_distance,8));via.SetNet(b.FindNet('GND'))
    via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(0,2);b.Add(via)
    def point(x,y):
        if mirror:x=24-x
        for _ in range(quarter):x,y=24-y,x
        return pcbnew.VECTOR2I(*(round(v*1e6) for v in (x,y)))
    # Rigid transforms exercise the actual native layer/shape path. A mirror
    # here is a 180-degree board-frame reflection of the horizontal source;
    # no caller/source coordinate is used as runtime ownership authority.
    if mirror:
        for item in [fp,supply,lead,via]:
            item.Rotate(pcbnew.VECTOR2I_MM(12,8),pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
    if quarter:
        for item in [fp,supply,lead,via]:
            item.Rotate(pcbnew.VECTOR2I_MM(12,12),pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T))
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face);z.SetMinThickness(100000)
        z.SetLocalClearance(200000);z.Outline().NewOutline()
        for x,y in ((1,1),(23,1),(23,23),(1,23)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    additive._ground_refill(b);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    direction=tuple(lead.GetEnd()[i]-lead.GetStart()[i] for i in (0,1))
    delta=[0 if v==0 else 300000*(1 if v>0 else -1) for v in direction]
    args=dict(board_hint='synthetic',footprint_uuid=force._uid(fp),delta_nm=delta)
    return b,source,args,fp,lead,via,supply


def saved(tmp_path,**options):
    b,source,args,*_=fixture(tmp_path,**options);q=op.plan(source,**args);child=op.construct(q)
    additive._ground_refill(child);target=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child,target)
    return source,target,args,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_source_bound_slide_shortens_ground_without_moving_a_barrel_or_power_copper(tmp_path,quarter,mirror,layer):
    source,target,args,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer);before=source.read_bytes()
    r=op.receive(source,target,**args)
    assert r['ok'] and r['complete'],r
    assert r['every_original_native_partition_identical'] and r['every_barrel_power_track_and_non_ground_fill_exact']
    assert r['shortened_ground_return_mm']==pytest.approx(.3)
    assert q['source_root_copper_covered_by_new_actual_ground_land'] and q['new_holes']==0
    assert source.read_bytes()==before and not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('fault',['locked_part','locked_lead','grouped_part','grouped_lead','DNP','no_via',
    'new_contact','wide','mask','not_capacitor','not_ground','wrong_identity','off_axis','backwards','beyond_barrel'])
def test_ownership_is_native_positive_and_bounded_before_any_construction(tmp_path,fault):
    b,source,args,fp,lead,via,supply=fixture(tmp_path)
    if fault=='locked_part':fp.SetLocked(True)
    elif fault=='locked_lead':lead.SetLocked(True)
    elif fault in ('grouped_part','grouped_lead'):
        g=pcbnew.PCB_GROUP(b);g.SetName('unrelated_protected_owner');b.Add(g);g.AddItem(fp if fault=='grouped_part' else lead)
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='no_via':discard_items(b,[via])
    elif fault=='new_contact':track(b,'GND',(10,8),(10,9),width=.2)
    elif fault=='wide':lead.SetWidth(400000)
    elif fault=='mask':lead.SetHasSolderMask(True)
    elif fault=='not_capacitor':fp.SetReference('R_NOT_A_CAP');fp.SetValue('10k')
    elif fault=='not_ground':
        discard_items(b,[lead,via]);fp.FindPadByNumber('2').SetNet(b.FindNet('+3V3'))
    elif fault=='wrong_identity':args['footprint_uuid']='not-a-source-UUID'
    elif fault=='off_axis':args['delta_nm']=[300000,1]
    elif fault=='backwards':args['delta_nm']=[-300000,0]
    else:
        via.Move(pcbnew.VECTOR2I(-1800000,0));lead.SetEnd(via.GetPosition())
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,**args)


def test_positive_lock_scope_does_not_unlock_or_generalize_to_another_source_track(tmp_path):
    b,source,args,fp,lead,via,supply=fixture(tmp_path);lead.SetLocked(True);field._save_field_snapshot(b,source)
    q=op.plan(source,**args,allow_owned_locked=True);child=op.construct(q)
    assert next(t for t in child.GetTracks() if force._uid(t)==force._uid(lead)).IsLocked()
    assert next(t for t in child.GetTracks() if force._uid(t)==force._uid(supply)).GetEnd()==supply.GetEnd()


def test_moved_land_cannot_partly_overlap_its_unchanged_barrel(tmp_path):
    b,source,args,*_=fixture(tmp_path,via_distance=.9)
    with pytest.raises(ValueError,match='barrel_process_owner'):op.plan(source,**args)


@pytest.mark.parametrize('fault',['width','power_endpoint','barrel','new_track','part_value','delta','field'])
def test_saved_receiver_replays_the_original_source_and_rejects_every_unowned_edit(tmp_path,fault):
    source,target,args,q=saved(tmp_path);b=pcbnew.LoadBoard(str(target));fp=next(iter(b.GetFootprints()))
    lead=next(t for t in b.GetTracks() if force._uid(t)==q['lead_uuid'])
    if fault=='width':lead.SetWidth(199999)
    elif fault=='power_endpoint':next(t for t in b.GetTracks() if t.GetNetname()=='+3V3').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='barrel':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='new_track':track(b,'GND',(15,15),(16,15),width=.2)
    elif fault=='part_value':fp.SetValue('another_component')
    elif fault=='delta':args['delta_nm']=[200000,0]
    else:fp.Reference().SetText('not_the_source_field')
    field._save_field_snapshot(b,target);r=op.receive(source,target,**args)
    assert not r['ok'] and not r['complete'] and r['errors']


def test_constructor_does_not_trust_a_mutated_proposal(tmp_path):
    b,source,args,*_=fixture(tmp_path);q=op.plan(source,**args);q=copy.deepcopy(q);q['lead_uuid']='unowned'
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct(q)


@pytest.mark.parametrize('options',[dict(delta_nm=[1,0]),dict(delta_nm=[500001,0]),dict(delta_nm=[True,0]),
    dict(delta_nm=[300000.,0]),dict(delta_nm=[0,0]),dict(timeout_s=11),dict(timeout_s=0),dict(timeout_s=True),
    dict(allow_owned_locked=1),dict(board_hint='')])
def test_untyped_or_unbounded_requests_are_not_placement_permission(tmp_path,options):
    b,source,args,*_=fixture(tmp_path);args.update(options)
    with pytest.raises(ValueError):op.plan(source,**args)
