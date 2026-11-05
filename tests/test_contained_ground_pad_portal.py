"""A future contour cannot own a ground mesh, pad, rule or missing plane."""
import copy,json,time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_contained_ground_pad_portal as op
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track


def case(tmp_path,angle=0,name='arbitrary'):
    b=_board([(10,8,'GND')],edge=(0,0,25,25));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    fp=next(iter(b.GetFootprints()));fp.SetReference(name);pad=next(iter(fp.Pads()))
    pad.SetNumber('2');pad.SetSize(pcbnew.VECTOR2I_MM(1.0,1.0))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pad.GetPosition());via.SetNet(pad.GetNet())
    via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);b.Add(via)
    rail=pcbnew.NETINFO_ITEM(b,'/rail_'+name);b.Add(rail)
    track(b,rail.GetNetname(),(8,9),(12,9),width=1.0,layer=pcbnew.B_Cu)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(b.FindNet('GND'));z.Outline().NewOutline()
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        for at in ((1,1),(24,1),(24,24),(1,24)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        b.Add(z)
    if angle:
        center=pcbnew.VECTOR2I_MM(12,12);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for i in [*b.GetFootprints(),*b.GetTracks()]:i.Rotate(center,rotation)
    additive._ground_refill(b);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,force._uid(via)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('name',['one','completely_renamed'])
def test_native_rotated_renamed_finite_inpad_portals_preserve_swept_plane_sheets(tmp_path,angle,name):
    source,uid=case(tmp_path,angle,name);before=source.read_bytes()
    discovery=op.discover(source,board_hint='synthetic',allow_owned_locked=True)
    assert discovery['ok'] and discovery['complete'] and len(discovery['plans'])==1
    q=discovery['plans'][0];assert q['via_uuid']==uid
    q=json.loads(json.dumps(q));built=op.construct(source,tmp_path/'auto',q)
    r=op.receive(source,built['candidate'],q)
    assert r['ok'] and r['complete'],r
    assert r['source_and_candidate_external_dogbones_mm']==[0.,0.]
    assert len({w[1] for w in r['swept_ground_plane_witnesses']})==2
    assert r['candidate_pad_center_distance_mm']>r['source_pad_center_distance_mm']
    assert r['other_proved_ground_returns_and_signal_barrel_support_preserved']
    assert r['exact_saved_ground_barrel_and_all_other_objects_replayed']
    assert not r['current_authority'] and not r['routing_admitted'] and not r['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['net','small','land_size','lead','second_land','one_plane','unknown_fill',
    'structural_group','locked_group','locked_via','dnp','source_land_not_containing','surface_zone'])
def test_source_contact_plane_process_and_ownership_cannot_be_inferred(tmp_path,fault):
    source,uid=case(tmp_path);b=pcbnew.LoadBoard(str(source));via=next(v for v in b.GetTracks() if force._uid(v)==uid)
    pad=next(p for f in b.GetFootprints() for p in f.Pads())
    if fault=='net':
        via.SetNetCode(b.GetNetcodeFromNetname('/rail_arbitrary'))
        # A foreign short is also refused by the non-normalizing serializer;
        # exercise source typing directly without asking it to normalize one.
        with pytest.raises(ValueError):op._source(b,uid,True,time.monotonic()+10.)
        return
    elif fault=='small':via.SetWidth(350000);via.SetDrill(250000)
    elif fault=='land_size':pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    elif fault=='lead':track(b,'GND',(10,8),(10.8,8),width=.2)
    elif fault=='second_land':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('other');b.Add(fp);p=pcbnew.PAD(fp)
        p.SetNumber('1');p.SetNet(pad.GetNet());p.SetPosition(pad.GetPosition());p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    elif fault=='one_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='unknown_fill':next(iter(b.Zones())).UnFill()
    elif fault in ('structural_group','locked_group'):
        import cec_fr as fr
        group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP if fault=='locked_group' else 'protected')
        b.Add(group);group.AddItem(via);group.SetLocked(fault=='locked_group')
    elif fault=='dnp':pad.GetParentFootprint().SetDNP(True)
    elif fault=='source_land_not_containing':via.Move(pcbnew.VECTOR2I_MM(.4,0))
    elif fault=='surface_zone':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(pad.GetNet());z.Outline().NewOutline()
        for at in ((9,7),(11,7),(11,8.5),(9,8.5)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        b.Add(z)
        z.SetFilledPolysList(pcbnew.F_Cu,pcbnew.SHAPE_POLY_SET(z.Outline()));z.SetIsFilled(True)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=fault!='locked_via')


@pytest.mark.parametrize('fault',['diameter','drill','pose','extra','priority','no_op','offpad','rules'])
def test_saved_replay_does_not_accept_extra_changes_or_stale_barrel_geometry(tmp_path,fault):
    source,uid=case(tmp_path);q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    built=op.construct(source,tmp_path/'valid',q);child=built['candidate'];b=pcbnew.LoadBoard(child)
    via=next(v for v in b.GetTracks() if force._uid(v)==uid)
    if fault=='diameter':via.SetWidth(610000)
    elif fault=='drill':via.SetDrill(290000)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra':track(b,'/rail_arbitrary',(20,20),(21,20),width=.2)
    elif fault=='priority':next(iter(b.Zones())).SetAssignedPriority(1)
    elif fault=='no_op':via.SetPosition(pcbnew.VECTOR2I(*q['source_position_nm']))
    elif fault=='offpad':via.Move(pcbnew.VECTOR2I_MM(.6,0))
    elif fault=='rules':
        from pathlib import Path
        Path(child).with_suffix('.kicad_dru').write_text('(version 1)\n')
    field._save_field_snapshot(b,child);r=op.receive(source,child,q)
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('fault',['portal','source','code','dimension','authority'])
def test_worker_plan_is_never_the_source_oracle(tmp_path,fault):
    source,uid=case(tmp_path);q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    built=op.construct(source,tmp_path/'valid',q);bad=copy.deepcopy(q)
    if fault=='portal':bad['portal_menu'][0]['at_nm'][0]+=1
    elif fault=='source':bad['source_sha256']='0'*64
    elif fault=='code':bad['code_identity']={}
    elif fault=='dimension':bad['drill_nm']-=1
    else:bad['current_authority']=True
    assert not op.receive(source,built['candidate'],bad)['ok']


@pytest.mark.parametrize('radius,grid',[(True,.025),(.3,True),(0,.025),(.6,.025),(.3,.01),(.025,.1),
    (float('nan'),.025),(.3,float('inf'))])
def test_even_empty_proposals_keep_literal_finite_work_bounds(tmp_path,radius,grid):
    source,uid=case(tmp_path)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',via_uuid=uid,
        allow_owned_locked=True,radius_mm=radius,grid_mm=grid)
