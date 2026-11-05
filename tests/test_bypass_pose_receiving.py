"""Native selected-bypass motion is neither a refdes exception nor release."""
from pathlib import Path
import math

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_bypass_pose_receiving as receiving
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_local_copper_cell as copper
import cec_pi_cleanup as cleanup
from test_lastmile import _board


def fixture(tmp_path,rotation=0,prefix=''):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    nets={}
    for name in ('GND','+3V3'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    for ref,value,x in (('U'+prefix+'71','INA240A3DR',10),('C'+prefix+'92','100nF',12)):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,10.5))
        for pin,net,y in (('6' if value.startswith('INA240') else '1','+3V3',10),
                           ('2','GND',11)):
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(nets[net]);p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);fp.Add(p)
        b.Add(fp)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(10,10));t.SetEnd(pcbnew.VECTOR2I_MM(12,10))
    t.SetWidth(pcbnew.FromMM(.25));t.SetLayer(pcbnew.F_Cu);t.SetNet(nets['+3V3']);b.Add(t)
    vias=[]
    for x in (10,12):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(x,11));v.SetNet(nets['GND'])
        v.SetWidth(pcbnew.FromMM(.35));v.SetDrill(pcbnew.FromMM(.25))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);vias.append(v)
    if rotation:
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for fp in b.GetFootprints():fp.Rotate(pivot,angle)
        for item in b.GetTracks():item.Rotate(pivot,angle)
    assert fr.group_local_pofv_signal_vias(b,vias)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);additive.bind_local_via_rule(b,source)
    target=force._copy_family(source,tmp_path/'trial');child=pcbnew.LoadBoard(str(target))
    cap=child.FindFootprintByReference('C'+prefix+'92')
    cap.Move(pcbnew.VECTOR2I(round(-.1e6*math.cos(math.radians(rotation))),
                            round(.1e6*math.sin(math.radians(rotation)))))
    field._save_field_snapshot(child,target)
    return source,target,'C'+prefix+'92'


@pytest.mark.parametrize('rotation,prefix',[(0,''),(90,'A'),(180,'NEXT_'),(270,'Z')])
def test_renamed_rotated_source_selected_cell_preserves_old_land_contacts(tmp_path,rotation,prefix):
    source,target,_=fixture(tmp_path,rotation,prefix);before=source.read_bytes()
    assert not additive.receive(source,target)['ok']
    proof=receiving.receive(source,target,board_hint='fixture')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['moved_bypasses'][0]['shift_mm']==pytest.approx(.1)
    assert proof['all_prior_native_terminal_and_copper_partitions_preserved']
    assert proof['original_owner_power_pair_and_sense_copper_exact']
    assert proof['independently_measured_local_PI_progress']
    assert proof['moved_bypasses'][0]['native_PI_metrics']['original_qualified_via_still_fully_in_pad']
    assert not proof['release_authority'] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['owner_move','value','pad_net','pad_shape','bulk','flip','nonquarter',
    'too_far','broken_old_contact','no_ground','bad_ground','protected_track','outline','project'])
def test_motion_cannot_conceal_unrelated_or_electrically_invalid_edits(tmp_path,fault):
    source,target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(target));cap=b.FindFootprintByReference(ref)
    if fault=='owner_move':b.FindFootprintByReference('U71').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='value':cap.SetValue('10nF')
    elif fault=='pad_net':cap.FindPadByNumber('1').SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='pad_shape':cap.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    elif fault=='bulk':cap.SetValue('1000uF')
    elif fault=='flip':cap.Flip(cap.GetPosition(),False)
    elif fault=='nonquarter':cap.SetOrientationDegrees(13)
    elif fault=='too_far':cap.Move(pcbnew.VECTOR2I_MM(7,0))
    elif fault=='broken_old_contact':cap.Move(pcbnew.VECTOR2I_MM(-1,0))
    elif fault=='no_ground':
        for t in list(b.GetTracks()):
            if t.GetClass()=='PCB_VIA':b.Remove(t)
    elif fault=='bad_ground':
        for t in b.GetTracks():
            if t.GetClass()=='PCB_VIA':t.SetWidth(pcbnew.FromMM(.25))
    elif fault=='protected_track':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(100000)
    elif fault=='outline':next(d for d in b.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts).Move(pcbnew.VECTOR2I_MM(.1,0))
    else:target.with_suffix('.kicad_pro').write_text('{}')
    field._save_field_snapshot(b,target)
    proof=receiving.receive(source,target,board_hint='fixture')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def test_native_constructor_reuses_qualified_short_returns_and_preserves_all_source_copper(tmp_path):
    source,_target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    old=copper.copper_inventory(b)
    cap=b.FindFootprintByReference(ref);at=cap.GetPosition()
    proposal=cleanup.construct_bypass_board(b,cap_ref=ref,position_mm=[at.x/1e6-.1,at.y/1e6],
        orientation_deg=cap.GetOrientationDegrees(),board_hint='fixture',board_path=str(source))
    assert proposal['ok'] and proposal['constructed'],proposal
    assert proposal['after']['supply_mm']<proposal['before']['supply_mm']
    assert proposal['after']['ground_path_mm']<=.8
    new=copper.copper_inventory(b)
    assert all(new.get(uid)==geometry for uid,geometry in old.items()) and not proposal['release_authority']
    target=force._copy_family(source,tmp_path/'constructed');field._save_field_snapshot(b,target)
    proof=receiving.receive(source,target,board_hint='fixture');assert proof['ok'],proof


def test_failed_native_constructor_restores_pose_copper_and_groups(tmp_path):
    source,_target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));cap=b.FindFootprintByReference(ref)
    at=tuple(cap.GetPosition());before=field._field_snapshot_inventory(b)
    result=cleanup.construct_bypass_board(b,cap_ref=ref,position_mm=[20,20],orientation_deg=13,board_hint='fixture')
    assert not result['ok'] and not result['constructed']
    assert tuple(cap.GetPosition())==at and field._field_snapshot_inventory(b)==before


def test_moved_return_on_foreign_supply_is_rejected_before_local_cell_construction(tmp_path):
    source,_target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(11.2,11));t.SetEnd(pcbnew.VECTOR2I_MM(11.3,11))
    t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(b.GetNetcodeFromNetname('+3V3'));b.Add(t)
    before=field._field_snapshot_inventory(b)
    proof=cleanup.construct_bypass_board(b,cap_ref=ref,position_mm=[11.5,10.5],
        orientation_deg=0,board_hint='fixture')
    assert not proof['constructed'] and 'PI_pose_foreign_copper_clearance' in proof['reason'],proof
    assert 'cell' not in proof and field._field_snapshot_inventory(b)==before


def test_rejected_pose_does_not_relabel_copper_through_an_inherited_short(tmp_path):
    source,_target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(11.8,11));t.SetEnd(pcbnew.VECTOR2I_MM(11.9,11))
    t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(b.GetNetcodeFromNetname('+3V3'));b.Add(t)
    before=field._field_snapshot_inventory(b)
    proof=cleanup.construct_bypass_board(b,cap_ref=ref,position_mm=[11.9,10.5],orientation_deg=0,board_hint='fixture')
    assert not proof['constructed'] and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('rotation,prefix',[(0,''),(90,'R'),(180,'OTHER'),(270,'LAST')])
def test_finite_native_pose_menu_keeps_parent_untouched(tmp_path,rotation,prefix):
    source,_target,ref=fixture(tmp_path,rotation,prefix);b=pcbnew.LoadBoard(str(source))
    cap=b.FindFootprintByReference(ref);origin=(tuple(cap.GetPosition()),cap.GetOrientationDegrees())
    rows=cleanup.pose_menu(b,ref,max_poses=8)
    assert 1<=len(rows)<=8 and len({(*r['position_mm'],r['orientation_deg']) for r in rows})==len(rows)
    assert (tuple(cap.GetPosition()),cap.GetOrientationDegrees())==origin


@pytest.mark.parametrize('rotation,prefix',[(0,''),(90,'R'),(180,'OTHER'),(270,'LAST')])
def test_small_menu_does_not_starve_fixed_supply_or_native_return_portal(tmp_path,rotation,prefix):
    source,_target,ref=fixture(tmp_path,rotation,prefix);b=pcbnew.LoadBoard(str(source))
    cap=b.FindFootprintByReference(ref);ground=cap.FindPadByNumber('2')
    old=ground.GetPosition();via=next(v for v in b.GetTracks() if v.GetClass()=='PCB_VIA'
        and tuple(v.GetPosition())==tuple(old))
    angle=math.radians(rotation)
    owner_ground=b.FindFootprintByReference('U'+prefix+'71').FindPadByNumber('2')
    owner_ground.Move(pcbnew.VECTOR2I(round(.9e6*math.cos(angle)),round(-.9e6*math.sin(angle))))
    via.Move(pcbnew.VECTOR2I(round(-1.2e6*math.cos(angle)),round(1.2e6*math.sin(angle))))
    t=pcbnew.PCB_TRACK(b);t.SetStart(old);t.SetEnd(via.GetPosition());t.SetWidth(250000)
    t.SetLayer(pcbnew.F_Cu);t.SetNetCode(ground.GetNetCode());b.Add(t)
    before=field._field_snapshot_inventory(b)
    rows=cleanup.pose_menu(b,ref,max_poses=4)
    assert len(rows)<=4 and {'native_connected_return_portal','native_fixed_supply_return_pivot'}<=set(r['basis'] for r in rows)
    assert field._field_snapshot_inventory(b)==before


def test_actual_parent_field_delta_requires_typed_pose_replay(tmp_path):
    source,target,_=fixture(tmp_path)
    report=field.assess_native_bypass_poses(source,target,board_hint='fixture')
    assert report['ok'] and report['complete'],report
    assert report['moved_bypasses'] and not report['release_authority']
    report=field.assess_native_bypass_poses(source,target,board_hint='fixture',timeout_s=0)
    assert report['ok'] is None and not report['complete']


def test_new_qualified_ground_entry_cannot_hide_loss_of_the_old_native_barrel(tmp_path):
    source,target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(target))
    cap=b.FindFootprintByReference(ref);cap.Move(pcbnew.VECTOR2I_MM(-.5,0))
    ground=cap.FindPadByNumber('2');via=pcbnew.PCB_VIA(b);via.SetPosition(ground.GetPosition())
    via.SetWidth(pcbnew.FromMM(.35));via.SetDrill(pcbnew.FromMM(.25))
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNetCode(ground.GetNetCode());b.Add(via);assert fr.group_local_pofv_signal_vias(b,[via])
    field._save_field_snapshot(b,target);additive.bind_local_via_rule(b,target)
    proof=receiving.receive(source,target,board_hint='fixture')
    assert not proof['ok'] and any('lost_original_native_component' in e for e in proof['errors']),proof


@pytest.mark.parametrize('fault',[{'position_mm':None},{'position_mm':[float('nan'),1]},
    {'orientation_deg':float('inf')},{'board_hint':''},{'return_reach_mm':2},{'search_work_limit':0}])
def test_invalid_constructor_domain_refuses_without_board_mutation(tmp_path,fault):
    source,_target,ref=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));before=field._field_snapshot_inventory(b)
    args=dict(cap_ref=ref,position_mm=[11.9,10.5],orientation_deg=0,board_hint='fixture');args.update(fault)
    proof=cleanup.construct_bypass_board(b,**args)
    assert not proof['ok'] and field._field_snapshot_inventory(b)==before


def test_route_evidence_derives_pure_pose_nets_from_native_source_not_worker_claims(tmp_path,monkeypatch):
    import cec_received_route_evidence as evidence
    source,target,ref=fixture(tmp_path)
    def bound(path):
        family=force._family(path,'fixture');code=force._code_identity()
        import cec_pair_semantics as semantics
        assert not semantics.analog_input_pairs(pcbnew.LoadBoard(str(path)))
        return dict(board_hint='fixture',source_family_before=family,source_family_after=family,
            code_before=code,code_after=code,identity_stable=True,
            same_net_connectivity=dict(details=[]))
    observed={}
    def physical(before,after,**kwargs):
        observed.update(kwargs);return dict(comparison_complete=True,same_evidence=True)
    # This isolates inventory/authority dispatch; it is not Kelvin qualification.
    monkeypatch.setattr(evidence.sense,'compare_contour_preservation',physical)
    prior,final=bound(source),bound(target)
    assert not evidence.compare(source,target,prior,final)['ok']
    proof=evidence.compare(source,target,prior,final,allow_selected_bypass_poses=True)
    assert proof['ok'] and proof['complete'],proof
    assert {row['net'] for row in proof['native_transforms']}=={'+3V3','GND'}
    assert all(not row['added_track_uuids'] and not row['retired_track_uuids'] for row in proof['native_transforms'])
    assert proof['moved_bypasses'][0]['ref']==ref and not proof['full_kelvin_qualification']
    assert set(observed['modified_nets'])=={'+3V3','GND'}
    assert observed['native_copper_transforms']==[]
    assert not evidence.compare(source,target,prior,final,allow_selected_bypass_poses=1)['ok']
    assert not evidence.compare(source,target,prior,final,allow_selected_bypass_poses=True,
        retired_ordinary_track_uuids=['untrusted'])['ok']


def test_pure_native_pose_uses_actual_contact_receivers_with_no_count_delta(tmp_path):
    import cec_force_sense_evidence as sense
    import cec_received_route_evidence as evidence
    source,target,_=fixture(tmp_path)
    prior=sense.replay(source,board_hint='fixture',timeout_s=5)
    final=sense.replay(target,board_hint='fixture',timeout_s=5)
    proof=evidence.compare(source,target,prior,final,allow_selected_bypass_poses=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['contact_count_transforms']==[]
    assert proof['preservation']['same_evidence']
    assert not proof['full_kelvin_qualification'] and not proof['release_authority']
