"""Spec for immutable grouped full-floor supply contact, not thin credit.

Implementation contract: cec_retained_fullwidth_supply_contact.plan(parent,
projected,track_uuid=...,board_hint=...,source_floor=...,timeout_s=10.)
returns a JSON-only proof or None/ValueError refusal. Source catalogue/export
is injected only at existing fixture boundaries; all copper is actual native.
"""
import importlib
import json
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_decoupler_cell as cells
from test_source_supply_endpoint_cut import fixture as source_fixture


def native_case(tmp_path,monkeypatch,angle=0,back=False):
    b,cap,owner,root,tree=source_fixture(tmp_path,monkeypatch)
    b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    cap.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.56,.62))
    cap.FindPadByNumber('1').SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    cap.FindPadByNumber('1').SetRoundRectRadiusRatio(.25)
    group=pcbnew.PCB_GROUP(b);group.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');b.Add(group)
    track=pcbnew.PCB_TRACK(b);track.SetStart(pcbnew.VECTOR2I_MM(5,4.68));track.SetEnd(pcbnew.VECTOR2I_MM(5,5.205));track.SetWidth(500000);track.SetLayer(pcbnew.F_Cu);track.SetNet(cap.FindPadByNumber('1').GetNet());track.SetLocked(True);b.Add(track);group.AddItem(track)
    other=pcbnew.PCB_TRACK(b);other.SetStart(pcbnew.VECTOR2I_MM(10,10));other.SetEnd(pcbnew.VECTOR2I_MM(12,10));other.SetWidth(200000);other.SetLayer(pcbnew.F_Cu);other.SetNet(track.GetNet());other.SetLocked(True);b.Add(other);group.AddItem(other)
    origin=pcbnew.VECTOR2I(0,0)
    if angle:
        turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for fp in b.GetFootprints():fp.Rotate(origin,turn)
        for t in b.GetTracks():t.Rotate(origin,turn)
    if back:
        for fp in b.GetFootprints():fp.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for t in b.GetTracks():t.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    saved=tmp_path/'parent.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(saved),b)
    child=pcbnew.LoadBoard(str(saved))
    # Derive the same rigid vector as the source board transformations.
    theta=math.radians(angle);dx=-.115*math.sin(theta);dy=-.115*math.cos(theta)
    if back:dx=-dx
    child.FindFootprintByReference(cap.GetReference()).Move(pcbnew.VECTOR2I(round(dx*1e6),round(dy*1e6)))
    authority=dict(current_authority=dict(amps=.25,geometry_margin=1.25,margin_included=False,source='board_design_basis'),profile='jlcpcb_6l_pofv_high_current',required_by_layer_nm={int(track.GetLayer()):100000},barrel_capacity_qualified=False,release_authority=False)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:authority)
    return b,child,track,other,group,root,authority


def invoke(b,child,track,root):
    module=importlib.import_module('cec_retained_fullwidth_supply_contact')
    return module.plan(b,child,track_uuid=force._uid(track),board_hint=str(root),
        source_floor=lambda t:(500000,200000),timeout_s=10.)


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_common_native_core_retains_world_copper_and_all_group_members(tmp_path,monkeypatch,angle,back):
    b,child,t,other,group,root,authority=native_case(tmp_path,monkeypatch,angle,back)
    original=[(force._uid(x),tuple(x.GetStart()),tuple(x.GetEnd()),x.GetWidth(),x.IsLocked())for x in b.GetTracks()]
    proof=invoke(b,child,t,root)
    assert proof and proof['full_width_floor_nm']>=500000
    assert proof['common_source_and_projected_same_pad_native_core']is True
    assert proof['source_group_uuid']==force._uid(group)
    assert force._uid(other)in proof['source_group_member_uuids']
    assert proof['original_track_lock_retained']is True
    assert proof['old_narrow_component_not_qualified']is True
    assert not proof['current_qualified']and not proof['release_authority']
    json.dumps(proof,allow_nan=False)
    assert original==[(force._uid(x),tuple(x.GetStart()),tuple(x.GetEnd()),x.GetWidth(),x.IsLocked())for x in b.GetTracks()]


@pytest.mark.parametrize('fault',['arbitrary_group','locked_group','nested_group','overlap_group',
    'thin_track','current_floor','no_current','wrong_net','other_member_changed','other_member_unlocked',
    'track_moved','track_unlocked','new_only_contact','one_nm_common_deficit','sliver','wrong_source'])
def test_no_group_name_collision_sliver_or_new_only_contact_authority(tmp_path,monkeypatch,fault):
    b,child,t,other,group,root,authority=native_case(tmp_path,monkeypatch)
    live={force._uid(x):x for x in child.GetTracks()}
    if fault=='arbitrary_group':group.SetName('arbitrary')
    elif fault=='locked_group':group.SetLocked(True)
    elif fault=='nested_group':
        parent=pcbnew.PCB_GROUP(b);parent.SetName('outer');b.Add(parent);parent.AddItem(group)
    elif fault=='overlap_group':
        extra=pcbnew.PCB_GROUP(b);extra.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');b.Add(extra);extra.AddItem(t)
    elif fault=='thin_track':t.SetWidth(499999);live[force._uid(t)].SetWidth(499999)
    elif fault=='current_floor':authority['required_by_layer_nm'][0]=500001
    elif fault=='no_current':monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:None)
    elif fault=='wrong_net':live[force._uid(t)].SetNetCode(0)
    elif fault=='other_member_changed':live[force._uid(other)].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='other_member_unlocked':live[force._uid(other)].SetLocked(False)
    elif fault=='track_moved':live[force._uid(t)].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='track_unlocked':live[force._uid(t)].SetLocked(False)
    elif fault in('new_only_contact','sliver','one_nm_common_deficit'):
        pad=child.FindFootprintByReference('FILTER').FindPadByNumber('1')
        # Exact source/projected common rectangle height: .62 - shift.
        shift=.3 if fault=='new_only_contact'else(.619 if fault=='sliver'else .120001)
        pad.GetParentFootprint().Move(pcbnew.VECTOR2I(0,round((-shift+.115)*1e6)))
    else:root.write_text(root.read_text().replace('CL05B104KO5NNNC','UNQUALIFIED'))
    try:proof=invoke(b,child,t,root)
    except ValueError:return
    assert not proof
