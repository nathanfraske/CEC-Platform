"""A supply-centred capacitor turn owns neither another load nor a bus."""
import json,math
import pcbnew,pytest
import cec_capacitor_return_repack as worker
import cec_ground_tee_tail as tails
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_ground_tee_tail import fixture as tee_fixture


def fixture(tmp_path,angle=0,back=False):
    source,b,body,tip,root,branch,_=tee_fixture(tmp_path)
    cap=pcbnew.FOOTPRINT(b);cap.SetReference('C_RENAMED_RETURN');cap.SetValue('100nF')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));cap.SetPosition(pcbnew.VECTOR2I_MM(16.5,15));b.Add(cap)
    supply=pcbnew.NETINFO_ITEM(b,'/RENAMED_RAIL');b.Add(supply)
    lands=[]
    for pin,net,point in [('1',supply,(17,15)),('2',b.FindNet('GND'),(16,15))]:
        pad=pcbnew.PAD(cap);cap.Add(pad);pad.SetNumber(pin);pad.SetNet(net)
        pad.SetPosition(pcbnew.VECTOR2I_MM(*point));pad.SetSize(pcbnew.VECTOR2I_MM(.55,.65))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());lands.append(pad)
    if back:
        cap.Flip(cap.GetPosition(),False)
        ground=cap.FindPadByNumber('2');delta=pcbnew.VECTOR2I_MM(16,15)-ground.GetPosition()
        cap.Move(delta)
        for t in (body,tip,branch):t.SetLayer(pcbnew.B_Cu)
        load=b.FindFootprintByReference('RETAINED_TEST_LOAD');load.Flip(load.GetPosition(),False)
    for f in (cap.Reference(),cap.Value()):
        f.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
        f.SetPosition(cap.GetPosition());f.SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    if angle:
        turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T);origin=pcbnew.VECTOR2I_MM(12,14)
        for item in (cap,root,body,tip,branch,b.FindFootprintByReference('RETAINED_TEST_LOAD')):item.Rotate(origin,turn)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));additive._ground_refill(b);field._save_field_snapshot(b,source)
    old=pcbnew.LoadBoard(str(source));fp=old.FindFootprintByReference('C_RENAMED_RETURN');pad=fp.FindPadByNumber('2');anchor=fp.FindPadByNumber('1')
    uid=force._uid(pad);fields=[(f,pcbnew.VECTOR2I(f.GetPosition()),f.GetTextAngle()) for f in (fp.Reference(),fp.Value())]
    fp.Rotate(anchor.GetPosition(),pcbnew.EDA_ANGLE(270 if back else 90,pcbnew.DEGREES_T))
    target_pose=(pcbnew.VECTOR2I(fp.GetPosition()),fp.GetOrientationDegrees())
    # Construct with the exact same native source setters as pose receiving;
    # Rotate and SetOrientation do not serialize hidden field angles equally
    # for every pre-existing cardinal orientation. No receiver is weakened.
    old=pcbnew.LoadBoard(str(source));fp=old.FindFootprintByReference('C_RENAMED_RETURN')
    fp.SetPosition(target_pose[0]);fp.SetOrientationDegrees(target_pose[1]);pad=fp.FindPadByNumber('2');anchor=fp.FindPadByNumber('1')
    fields=[(f,at,turn) for f,(_,at,turn) in zip((fp.Reference(),fp.Value()),fields)]
    for f,at,turn in fields:f.SetPosition(at);f.SetTextAngle(turn)
    direction=pad.GetPosition()-anchor.GetPosition();target=pad.GetPosition()+direction
    via=pcbnew.PCB_VIA(old);via.SetPosition(target);via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(pad.GetNetCode());old.Add(via)
    t=pcbnew.PCB_TRACK(old);t.SetStart(pad.GetPosition());t.SetEnd(target);t.SetWidth(200000)
    t.SetLayer(worker.cells._ground_terminal_layer(pad));t.SetNetCode(pad.GetNetCode());old.Add(t)
    mid=force._copy_family(source,tmp_path/'posed');additive._ground_refill(old);field._save_field_snapshot(old,mid)
    changed=pcbnew.LoadBoard(str(mid));q=tails.plan(changed,force._uid(tip));tails.subtract(changed,q)
    child=force._copy_family(source,tmp_path/'final');additive._ground_refill(changed);field._save_field_snapshot(changed,child)
    return source,mid,child,dict(pad_uuid=uid,posed_candidate=str(mid),seed_uuid=force._uid(tip)),q


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_source_native_quarter_turn_return_repack_is_not_a_refdes_or_coordinate_recipe(tmp_path,angle,back):
    source,mid,child,args,tail=fixture(tmp_path,angle,back);frozen=[p.read_bytes() for p in (source,mid,child)]
    r=worker.receive(source,child,board_hint='synthetic',per_phase_leases=True,**args)
    assert r['ok'] and r['complete'],r
    assert r['source_ground_return_mm']>4. and r['saved_ground_return_mm']==1.
    assert r['return_gain_mm']>3. and r['source_bypass_assignments_unchanged']
    assert r['real_native_supply_land_reoriented_with_package'] and not r['entire_source_supply_land_unchanged']
    assert r['source_supply_land_centre_and_all_original_supply_tracks_unchanged']
    assert len(r['modified_footprint_uuids'])==len(r['retired_track_uuids'])==1
    assert len(r['added_native_uuids'])==2 and r['new_ordinary_ground_barrels']==1
    assert not r['current_qualified'] and not r['release_authority']
    assert [p.read_bytes() for p in (source,mid,child)]==frozen


@pytest.mark.parametrize('fault',['value','other_pad','via_drill','via_size','other_part','sidecar','missing_leaf',
    'wrong_seed','fake_pad','identical_phase','lock_scope'])
def test_changed_population_geometry_or_untyped_delta_cannot_borrow_pose_authority(tmp_path,fault):
    source,mid,child,args,tail=fixture(tmp_path);b=pcbnew.LoadBoard(str(child));fp=b.FindFootprintByReference('C_RENAMED_RETURN')
    if fault=='value':fp.SetValue('47uF')
    elif fault=='other_pad':fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.7,.7))
    elif fault=='via_drill':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetPosition().x>16000000).SetDrill(200000)
    elif fault=='via_size':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetPosition().x>16000000).SetWidth(500000)
    elif fault=='other_part':b.FindFootprintByReference('RETAINED_TEST_LOAD').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    elif fault=='missing_leaf':child=mid
    elif fault=='wrong_seed':args['seed_uuid']='absent'
    elif fault=='fake_pad':args['pad_uuid']='absent'
    elif fault=='identical_phase':args['posed_candidate']=str(source)
    elif fault=='lock_scope':args['allow_locked_track_uuids']=[tail['retained_tee_track_uuids'][0]]
    if fault in ('value','other_pad','via_drill','via_size','other_part'):field._save_field_snapshot(b,child)
    frozen=source.read_bytes();r=worker.receive(source,child,board_hint='synthetic',**args)
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('mode',[1,None,'yes'])
def test_independent_phase_leases_must_be_explicit_boolean(tmp_path,mode):
    source,mid,child,args,_=fixture(tmp_path)
    r=worker.receive(source,child,board_hint='synthetic',per_phase_leases=mode,**args)
    assert not r['ok'] and not r['complete'] and r['errors']


@pytest.mark.parametrize('lease',[True,0,10.0001,float('nan')])
def test_repack_never_widens_an_individual_owner_lease(tmp_path,lease):
    source,mid,child,args,_=fixture(tmp_path)
    r=worker.receive(source,child,board_hint='synthetic',per_phase_leases=True,timeout_s=lease,**args)
    assert not r['ok'] and not r['complete'] and r['errors']
