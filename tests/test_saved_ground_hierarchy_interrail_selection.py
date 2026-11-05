"""Ground-only receiving must not reclassify a second interrail bypass.

Manufacturer/Source assignment boundaries are mocked as in the existing
hierarchy fixture; all Ground paths and land contacts are native KiCad.
"""
import copy
import time

import pcbnew
import pytest
import cec_complete_cell_receiving as complete
import cec_device_power_roles as roles
import cec_force_current as force
import cec_saved_ground_hierarchy as subject
from test_saved_ground_hierarchy import fixture


def mixed_fixture(tmp_path, monkeypatch, rotation=0):
    parent, child, requests, assignment = fixture(tmp_path,monkeypatch,rotation)
    original_model = roles.footprint_contract(parent.FindFootprintByReference('renamed_owner'))
    model = dict(original_model,pins=dict(original_model['pins'],**{'4':'power_input'}))
    monkeypatch.setattr(roles,'footprint_contract',lambda f:
        copy.deepcopy(model) if f.GetReference()=='renamed_owner' else None)
    for board in (parent,child):
        board.Add(pcbnew.NETINFO_ITEM(board,'VIO'))
        owner = board.FindFootprintByReference('renamed_owner')
        p = pcbnew.PAD(owner);p.SetNumber('4');p.SetNet(board.FindNet('VIO'))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(12,13));owner.Add(p)
        cap = pcbnew.FOOTPRINT(board);cap.SetReference('unrelated_interrail');cap.SetValue('100n')
        board.Add(cap)
        for number,net,at in [('1','VIO',(12,14)),('2','RAIL',(13,14))]:
            pad=pcbnew.PAD(cap);pad.SetNumber(number);pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(pcbnew.VECTOR2I_MM(*at));cap.Add(pad)
    assignment['assigned']['source']['requirement'].update(return_rail='GND',return_pin='1')
    assignment['assigned']['interrail'] = dict(cap_ref='unrelated_interrail',requirement=dict(
        ref='renamed_owner',pin='4',rail='VIO',return_rail='RAIL',return_pin='3',
        source='explicit manufacturer VIO-to-VCC bypass fixture'))
    return parent,child,requests,assignment


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_ground_hierarchy_keeps_interrail_bypass_separate(tmp_path,monkeypatch,rotation):
    parent,child,requests,assignment = mixed_fixture(tmp_path,monkeypatch,rotation)
    before = copy.deepcopy(assignment)
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2')
    r=requests['ground:'+force._uid(ref)]
    proof=subject.receive(parent,child,r,requests,board_hint='fixture',deadline=time.monotonic()+9)
    assert proof['ok'] and len(proof['links'])==2 and proof['root_return_max_mm']==.8
    assert proof['root_return_mm']<=.8
    assert assignment==before
    # The common saved terminal caller must also retain the separate role.
    proofs=complete._receive_paths(parent,child,requests,set(),'fixture',time.monotonic()+9,
        allow_retained_no_additions=True)
    assert sum('source_ground_hierarchy' in p for p in proofs)==2
    assert assignment==before


def test_interrail_requirement_cannot_supply_missing_ground_root(tmp_path,monkeypatch):
    parent,child,requests,assignment=mixed_fixture(tmp_path,monkeypatch)
    del assignment['assigned']['source']
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2')
    with pytest.raises(ValueError,match='source_selected_bypass_required'):
        subject.receive(parent,child,requests['ground:'+force._uid(ref)],requests,
            board_hint='fixture',deadline=time.monotonic()+9)


def test_false_ground_metadata_still_requires_native_ground_land(tmp_path,monkeypatch):
    parent,child,requests,assignment=mixed_fixture(tmp_path,monkeypatch)
    assignment['assigned']['interrail']['requirement']['return_rail']='GND'
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2')
    with pytest.raises(ValueError):
        subject.receive(parent,child,requests['ground:'+force._uid(ref)],requests,
            board_hint='fixture',deadline=time.monotonic()+9)


def test_saved_ground_cap_cannot_change_into_interrail_cap(tmp_path,monkeypatch):
    parent,child,requests,_=mixed_fixture(tmp_path,monkeypatch)
    child.FindFootprintByReference('renamed_cap').FindPadByNumber('2').SetNet(child.FindNet('VIO'))
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2')
    with pytest.raises(ValueError):
        subject.receive(parent,child,requests['ground:'+force._uid(ref)],requests,
            board_hint='fixture',deadline=time.monotonic()+9)


def test_ground_cap_duplicate_owner_assignment_still_refuses(tmp_path,monkeypatch):
    parent,child,requests,assignment=mixed_fixture(tmp_path,monkeypatch)
    assignment['assigned']['duplicate']=copy.deepcopy(assignment['assigned']['source'])
    ref=child.FindFootprintByReference('renamed_owner').FindPadByNumber('2')
    with pytest.raises(ValueError,match='unique_source_bypass_assignment_required'):
        subject.receive(parent,child,requests['ground:'+force._uid(ref)],requests,
            board_hint='fixture',deadline=time.monotonic()+9)
