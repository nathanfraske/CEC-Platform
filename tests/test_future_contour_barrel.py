"""Native ordinary-barrel restoration must also respect future bus geometry."""
import copy,json,math
from pathlib import Path
import pcbnew
import pytest
import cec_future_contour_barrel as op
import cec_ordinary_barrel_reseat as core
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_ordinary_barrel_reseat import fixture as ordinary_case


def case(tmp_path,angle=0,name='one'):
    source,unused,uid=ordinary_case(tmp_path,rotation=0,rename=name)
    b=pcbnew.LoadBoard(str(source));n=pcbnew.NETINFO_ITEM(b,'/rail_'+name);b.Add(n)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(8,9));t.SetEnd(pcbnew.VECTOR2I_MM(12,9))
    t.SetWidth(1000000);t.SetLayer(pcbnew.F_Cu);t.SetNet(n);b.Add(t)
    if angle:
        for item in b.GetTracks():item.Rotate(pcbnew.VECTOR2I_MM(12,12),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    return source,uid


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('name',['independent_A','completely_renamed'])
def test_native_discovery_constructs_rotated_renamed_source_without_coordinates(tmp_path,angle,name):
    source,uid=case(tmp_path,angle,name);before=source.read_bytes()
    proposed=op.discover(source,board_hint='synthetic',allow_owned_locked=True)
    assert proposed['ok'] and proposed['complete'] and len(proposed['plans'])==1
    q=json.loads(json.dumps(proposed['plans'][0]))
    assert q['via_uuid']==uid and q['blocked_profiles'] and q['portal_positions_nm']
    assert math.dist(q['source_barrel']['root_nm'],q['portal_positions_nm'][0])==100000
    built=op.construct(source,tmp_path/'auto',q)
    proof=op.receive(source,built['candidate'],q)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_future_source_power_profiles_clear'] and not proof['routing_admitted']
    assert proof['source_power_and_other_native_material_exact'] and not proof['current_authority']
    child=pcbnew.LoadBoard(built['candidate'])
    assert not any(z.GetIsRuleArea() for z in child.Zones())
    assert source.read_bytes()==before and built['temporary_reservations_removed']
    original=pcbnew.LoadBoard(str(source));old={force._uid(t):t for t in original.GetTracks()}
    assert all(force._uid(t) in old and list(t.GetStart())==list(old[force._uid(t)].GetStart())
        and list(t.GetEnd())==list(old[force._uid(t)].GetEnd()) and t.GetWidth()==old[force._uid(t)].GetWidth()
        for t in child.GetTracks() if t.GetNetname()=='/rail_'+name)


@pytest.mark.parametrize('fault',['ground','sense','group','small','pad','interior_tee','locked'])
def test_future_profiles_never_grant_protected_barrel_or_contact_ownership(tmp_path,fault):
    source,uid=case(tmp_path);b=pcbnew.LoadBoard(str(source))
    via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault in ('ground','sense'):
        n=pcbnew.NETINFO_ITEM(b,'GND' if fault=='ground' else '/SENSE_HI');b.Add(n)
        for t in b.GetTracks():
            if t.GetNetname()=='/ordinary_one':t.SetNet(n)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('not-a-construction-lease');b.Add(g);g.AddItem(via)
    elif fault=='small':via.SetWidth(350000);via.SetDrill(250000)
    elif fault=='pad':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('fixed');b.Add(fp);p=pcbnew.PAD(fp)
        p.SetPosition(via.GetPosition());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetNet(via.GetNet())
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);fp.Add(p)
    elif fault=='interior_tee':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(9,7));t.SetEnd(pcbnew.VECTOR2I_MM(9,8))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(via.GetNet());b.Add(t)
    field._save_field_snapshot(b,source);before=source.read_bytes()
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=fault!='locked')
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['portal','profile','clearance','source_width','source_binding','authority','code'])
def test_persisted_plan_is_not_authority_and_is_rederived(tmp_path,fault):
    source,uid=case(tmp_path);q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    built=op.construct(source,tmp_path/'valid',q);bad=copy.deepcopy(q)
    if fault=='portal':bad['portal_positions_nm'][0][1]+=1000
    elif fault=='profile':bad['future_profiles'][0]['polygons_nm'][0][0][0][0]+=1
    elif fault=='clearance':bad['clearance_nm']-=1
    elif fault=='source_width':bad['source_barrel']['root_width_by_layer_nm']['0']-=1
    elif fault=='source_binding':bad['source_binding_sha256']='0'*64
    elif fault=='authority':bad['current_authority']=True
    else:bad['code_identity']={}
    proof=op.receive(source,built['candidate'],bad)
    assert not proof['ok'] and proof['errors'] and not proof['routing_admitted']
    with pytest.raises(ValueError):op.construct(source,tmp_path/'forged',bad)


def test_current_native_legal_pose_is_refused_when_it_blocks_future_profile(tmp_path):
    source,uid=case(tmp_path);b=pcbnew.LoadBoard(str(source))
    q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    original=core.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    old=next(t for t in b.GetTracks() if force._uid(t)==uid)
    v=old.Duplicate();v.m_Uuid.Clone(pcbnew.KIID());core.subtract(b,source,original)
    at=pcbnew.VECTOR2I_MM(10.1,7.9995);v.SetPosition(at);b.Add(v)
    for row in original['source_points_nm']:
        start=pcbnew.VECTOR2I(*row['far_nm']);bend=pcbnew.VECTOR2I(at.x, start.y)
        for a,z in ((start,bend),(bend,at)):
            if a==z:continue
            t=pcbnew.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(row['width_nm'])
            t.SetLayer(row['layer']);t.SetNet(v.GetNet());b.Add(t)
    child=force._copy_family(source,tmp_path/'native-only');field._save_field_snapshot(b,child)
    ordinary=core.receive(source,child,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    assert ordinary['ok'] and ordinary['complete'],ordinary
    future=op.receive(source,child,q)
    assert not future['ok'] and 'replacement_not_in_source_derived_future_portal_menu' in str(future['errors'])


@pytest.mark.parametrize('radius,grid',[(True,.1),(float('nan'),.1),(0,.1),(2.1,.1),(.5,True),
    (.5,float('inf')),(.5,.04),(.5,1),(2.,.05)])
def test_even_empty_discovery_has_literal_bounded_work(tmp_path,radius,grid):
    source,uid=case(tmp_path)
    with pytest.raises(ValueError):op.discover(source,board_hint='synthetic',radius_mm=radius,grid_mm=grid)


@pytest.mark.parametrize('value',[True,0,-1,9,1.5,'4'])
def test_discovery_cannot_broaden_barrel_budget(tmp_path,value):
    source,uid=case(tmp_path)
    with pytest.raises(ValueError):op.discover(source,board_hint='synthetic',max_barrels=value)


@pytest.mark.parametrize('index',[True,-1,10000,.5,'0'])
def test_private_constructor_never_accepts_unbounded_or_nonliteral_index(tmp_path,index):
    source,uid=case(tmp_path);q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    with pytest.raises(ValueError):op.construct(source,tmp_path/'bad',q,portal_index=index)


def test_source_change_and_existing_output_are_never_overwritten(tmp_path):
    source,uid=case(tmp_path);q=op.plan(source,board_hint='synthetic',via_uuid=uid,allow_owned_locked=True)
    with pytest.raises(ValueError):op.construct(source,source.parent,q)
    b=pcbnew.LoadBoard(str(source));track=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    track.SetLocked(not track.IsLocked());field._save_field_snapshot(b,source)
    before=source.read_bytes()
    with pytest.raises(ValueError):op.construct(source,tmp_path/'stale',q)
    assert source.read_bytes()==before
