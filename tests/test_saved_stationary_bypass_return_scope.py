"""Recover Source-selected fixed peers from new real local returns, not IDs."""
import time
import uuid

import pcbnew
import pytest
import cec_complete_cell_receiving as saved
import cec_cell_escape_replan as escape
import cec_field_coupling as field
import cec_force_current as force
from test_complete_cell_connections import native_source


def fixture(tmp_path,monkeypatch,*,back=False,angle=0):
    source,parent,unused,old=native_source(tmp_path,monkeypatch)
    rows=[]
    for suffix in('owner','cap'):
        original=next(f for f in parent.GetFootprints()if f.GetReference().endswith('_'+suffix))
        duplicate=pcbnew.Cast_to_FOOTPRINT(original.Duplicate(False));duplicate.SetReference('STATIONARY_OPAQUE_'+suffix)
        duplicate.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid4())))
        for p in duplicate.Pads():p.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid4())))
        parent.Add(duplicate);duplicate.Move(pcbnew.VECTOR2I_MM(8,8))
        if back:
            duplicate.Flip(duplicate.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle:duplicate.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        rows.append(duplicate)
    assignment=escape.constraints._device_bypass_assignment(parent)
    assignment['assigned']['fixed_extra']=dict(cap_ref=rows[1].GetReference(),requirement=dict(
        ref=rows[0].GetReference(),pin='5',rail='RAIL',return_rail='GND'))
    field._save_field_snapshot(parent,source);parent=pcbnew.LoadBoard(str(source))
    proposal=escape.prepare(parent,old['poses'],board_hint='opaque')
    child=pcbnew.LoadBoard(str(source));escape.apply_private(child,proposal)
    cap=child.FindFootprintByReference(rows[1].GetReference());pad=cap.FindPadByNumber('2')
    via=pcbnew.PCB_VIA(child);via.SetNet(child.FindNet('GND'));via.SetWidth(500000);via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pad.GetPosition());child.Add(via)
    return parent,child,pad,via,proposal,{r.GetReference()for r in rows}


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_saved_scope_adds_only_exact_stationary_source_owner_and_selected_cap(tmp_path,monkeypatch,back,angle):
    parent,child,pad,via,proposal,peers=fixture(tmp_path,monkeypatch,back=back,angle=angle)
    before=[escape.row._source_binding(b)for b in(parent,child)]
    poses,moved=saved._poses(parent,child,'opaque')
    assert peers<=poses.keys()and not peers&moved
    assert set(poses)==set(proposal['poses'])|peers
    fresh=escape.prepare(parent,poses,board_hint='opaque')
    assert fresh['stationary_device_owners']==['STATIONARY_OPAQUE_owner']
    assert fresh['retired_track_uuids']==proposal['retired_track_uuids']
    assert before==[escape.row._source_binding(b)for b in(parent,child)]


@pytest.mark.parametrize('fault',['no_new_barrel','foreign','remote','changed_part','changed_pad','ambiguous_assignment'])
def test_plane_labels_nearness_unknown_assignment_and_changed_parts_do_not_expand_scope(tmp_path,monkeypatch,fault):
    parent,child,pad,via,proposal,peers=fixture(tmp_path,monkeypatch)
    assigned=saved._assignments(parent,'opaque')
    if fault=='no_new_barrel':
        existing=via.Duplicate();existing.m_Uuid.Clone(pcbnew.KIID(force._uid(via)));parent.Add(existing)
    elif fault=='foreign':via.SetNet(child.FindNet('OUT'))
    elif fault=='remote':via.Move(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='changed_part':pad.GetParentFootprint().SetValue('not_source_selected')
    elif fault=='changed_pad':pad.SetSize(pcbnew.VECTOR2I(500001,500000))
    else:assigned['duplicate']=next(r for r in assigned.values()if r[0]in peers)
    assert not saved._stationary_bypass_return_peers(parent,child,assigned,set(proposal['poses']))


def test_nearby_via_without_explicit_copper_does_not_gain_stationary_owner(tmp_path,monkeypatch):
    parent,child,pad,via,proposal,peers=fixture(tmp_path,monkeypatch)
    via.Move(pcbnew.VECTOR2I_MM(0,.6))
    assert not saved._stationary_bypass_return_peers(parent,child,saved._assignments(parent,'opaque'),set(proposal['poses']))
