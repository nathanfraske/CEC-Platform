"""New real Ground drills cannot hide missing native pair reference metal."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_added_ground_bore_reference as owner
import cec_field_coupling as field
import cec_force_current as force
import cec_native_reference_sheet_inclusion as no_bore_owner
from test_ground_access_completion import fixture
from test_field_proposals import track


def case(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,hazard=None):
    b,source,pad,point=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=face,mode='vip',observed=True)
    for name in ('/USB_DP','/USB_DM'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    for net,y in (('/USB_DP',4),('/USB_DM',4.45)):
        aa,zz=point(2,y),point(14,y)
        track(b,net,[v/1e6 for v in aa],[v/1e6 for v in zz],layer=face,width=.25)
    if hazard:
        at=pad.GetPosition()
        if hazard in ('track','near_clearance'):
            dy=0 if hazard=='track' else 450000
            # A real paired conductor on an interior face, not a plotted line.
            track(b,'/USB_DP',[(at.x-1000000)/1e6,(at.y+dy)/1e6],
                [(at.x+1000000)/1e6,(at.y+dy)/1e6],layer=pcbnew.In2_Cu,width=.25)
        elif hazard=='land':
            fp=pcbnew.FOOTPRINT(b);fp.SetReference('arbitrary_pair_land');b.Add(fp)
            p=pcbnew.PAD(fp);p.SetNumber('z');p.SetNet(b.FindNet('/USB_DP'))
            p.SetPosition(at);p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers);fp.Add(p)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'child');after=pcbnew.LoadBoard(str(child))
    v=pcbnew.PCB_VIA(after);v.SetPosition(pad.GetPosition());v.SetNet(after.FindNet('GND'))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True);after.Add(v)
    additive._ground_refill(after);field._save_field_snapshot(after,child)
    return source,child,force._uid(v)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_added_ground_hole_passes_only_native_projection_and_source_clearance(tmp_path,quarter,mirror,face):
    source,child,uid=case(tmp_path,quarter,mirror,face);raw=source.read_bytes()
    old=no_bore_owner.receive(source,child,board_hint='synthetic')
    assert not old['ok'] and any('no_new_or_moved_bores' in e for e in old['errors'])
    r=owner.receive(source,child,board_hint='synthetic')
    assert r['ok'] and r['complete'],r['errors']
    assert r['added_ground_via_uuids']==[uid]
    assert r['new_ground_bores_source_clearance_separated_from_all_pair_copper']
    assert r['missing_saved_ground_fill_source_clearance_separated_from_all_pair_copper']
    assert r['independent_native_additive_replay']['ok'] and not r['global_physical_ground_metal_unchanged_claimed']
    assert not r['numeric_area_or_sampling_waiver_used'] and not r['pair_or_reference_qualified']
    assert not r['release_authority'] and source.read_bytes()==raw


@pytest.mark.parametrize('hazard',['track','near_clearance','land'])
def test_bore_beneath_any_real_pair_face_or_source_clearance_is_rejected(tmp_path,hazard):
    if hazard=='track':
        # A direct foreign-copper short is already rejected by the native
        # authored-net guard while making this deliberately invalid child.
        with pytest.raises(RuntimeError,match='selected_native_fill_changed_authored_net_identity'):
            case(tmp_path,hazard=hazard)
        return
    source,child,uid=case(tmp_path,hazard=hazard)
    r=owner.receive(source,child,board_hint='synthetic')
    assert not r['ok'] and r['errors']
    assert not r['release_authority']


@pytest.mark.parametrize('fault',['source_track','source_pad','source_drill','source_via_position',
    'not_ground','blind','removed_via','extra_track','pair_zone','profile','sidecar','lost_fill','zone_intent'])
def test_exact_native_source_delta_and_missing_ground_are_not_area_waivers(tmp_path,fault):
    source,child,uid=case(tmp_path);b=pcbnew.LoadBoard(str(child))
    old_via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t)!=uid)
    new_via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    z=next(iter(b.Zones()))
    if fault=='source_track':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(999999)
    elif fault=='source_pad':next(iter(next(iter(b.GetFootprints())).Pads())).SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault=='source_drill':old_via.SetDrill(old_via.GetDrillValue()+1)
    elif fault=='source_via_position':old_via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='not_ground':
        new_via.SetPosition(pcbnew.VECTOR2I_MM(20,20));new_via.SetNet(b.FindNet('/USB_DP'))
        additive._ground_refill(b)
    elif fault=='blind':new_via.SetViaType(pcbnew.VIATYPE_BLIND);new_via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=='removed_via':b.Remove(old_via)
    elif fault=='extra_track':track(b,'GND',(20,20),(21,20),width=.25)
    elif fault=='pair_zone':z.SetNet(b.FindNet('/USB_DP'))
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='lost_fill':
        poly=z.GetFilledPolysList(z.GetLayer()).CloneDropTriangulation();poly.Move(pcbnew.VECTOR2I(1,0))
        z.SetFilledPolysList(z.GetLayer(),poly);z.SetIsFilled(True)
    else:z.SetLocalClearance(z.GetLocalClearance()+1)
    field._save_field_snapshot(b,child);r=owner.receive(source,child,board_hint='synthetic')
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('options',[dict(timeout_s=True),dict(timeout_s=0),dict(timeout_s=11),
    dict(timeout_s=float('nan')),dict(board_hint='')])
def test_independent_phase_bounds_do_not_turn_into_new_manufacturing_authority(tmp_path,options):
    source,child,uid=case(tmp_path);args=dict(board_hint='synthetic');args.update(options)
    r=owner.receive(source,child,**args)
    assert not r['ok'] and r['errors'] and not r['release_authority']
