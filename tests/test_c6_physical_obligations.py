"""Complete C6 ownership keeps physical Ground contacts through reconstruction.

Synthetic schematic assignment is isolated here; native lands, obligation
generation, partitions and saved-board return receiving are the real tools.
These tests grant no hardware placement, current or release qualification.
"""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_ground_return_preservation as returns
import cec_native_partition_pair as partitions
from cec_native_items import discard_items
from test_c6_device_physical_pinmap import fixture
from test_ground_return_preservation import native_pair, item
from test_native_partition_pair import clone


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_all_physical_ground_obligations_survive_complete_owner_pose(monkeypatch,quarter,back):
    source,owner=fixture(quarter,back);ref=owner.GetReference()
    source.SetCopperLayerCount(6)
    power=owner.FindPadByNumber('3')
    cap=pcbnew.FOOTPRINT(source);cap.SetReference('independent_bypass');cap.SetValue('100n')
    cap.SetPosition(power.GetPosition()+pcbnew.VECTOR2I_MM(1.,0));source.Add(cap)
    for n,net,delta in [('1',power.GetNet(),(0,0)),('2',source.FindNet('GND'),(.8,0))]:
        p=pcbnew.PAD(cap);p.SetNumber(n);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(cap.GetPosition()+pcbnew.VECTOR2I_MM(*delta))
        p.SetNet(net);cap.Add(p)
    if back:cap.Flip(cap.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    selected=dict(owner=ref,pin='3',rail=power.GetNetname())
    # Only the synthetic schematic assignment is substituted. Production
    # assignment remains Source-compiled, not inferred from this test's names.
    assignment={'assigned':{'synthetic_requirement':dict(cap_ref=cap.GetReference(),
        requirement=dict(ref=ref,pin='3',rail=power.GetNetname(),return_rail='GND'))}}
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:copy.deepcopy(assignment))
    posed=clone(source);poses={}
    for fp in posed.GetFootprints():
        fp.Move(pcbnew.VECTOR2I_MM(.5,-.5))
        poses[fp.GetReference()]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    model=escape.roles.footprint_contract(owner)
    assert sum(map(len,escape.roles.physical_pinmap(owner,model).values()))==61
    proposal=dict(poses=poses,retired_track_uuids=[],measurement_leaves=[],rated_supply_leaves=[],
        scalar_links=[],inherited_unrouted_measurement_lands=[],
        selected_bypasses={cap.GetReference():selected},stationary_device_owners=[],
        device_contracts={ref:model},board_hint='__synthetic_c6_obligations__',
        source_native_binding=row._source_binding(source),
        row_plan=dict(source_incident_boundaries=[],source_native_barrel_boundaries=[]))
    bindings=[row._source_binding(b)for b in(source,posed)]
    requests=escape.obligations(source,posed,proposal)
    actual={force._uid(p)for fp in posed.GetFootprints()for p in fp.Pads()if p.GetNetname()=='GND'}
    ground={key.removeprefix('ground:'):q for key,q in requests.items()if key.startswith('ground:')}
    assert len(actual)==len(ground)==31 and ground.keys()==actual
    split=[p for fp in posed.GetFootprints()if fp.GetReference()==ref
        for p in fp.Pads()if p.GetNumber()=='49']
    assert len(split)==len({force._uid(p)for p in split})==9
    assert all(ground[force._uid(p)]['a']['pad_uuid']==force._uid(p)for p in split)
    assert len([q for q in requests.values()if q['kind']=='local_supply'])==1
    assert all(q['reach_mm']<=.8 for q in ground.values())
    assert bindings==[row._source_binding(b)for b in(source,posed)]


@pytest.mark.parametrize('back',[False,True])
def test_same_logical_ground_number_never_grants_native_pcb_connection(back):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('unrelated_module');board.Add(fp)
    for x in(1,5):
        p=pcbnew.PAD(fp);p.SetNumber('49');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(x,1))
        p.SetNet(net);fp.Add(p)
    fp.SetDuplicatePadNumbersAreJumpers(False)
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    child=clone(board);result=partitions.compare(board,child)
    assert result['preserved'] and result['source_component_count']==result['child_component_count']==2
    assert not result['routing_admitted'] and not result['current_capacity_qualified']


@pytest.mark.parametrize('fault',['missing','identity','return'])
def test_one_split_ground_contact_cannot_be_lost_behind_another(tmp_path,fault):
    source,child,via,track,pad=native_pair(tmp_path)
    peer_id=None
    for board in(source,child):
        first=item(board,pad);first.SetNumber('49')
        # The source fixture has a real five-millimetre horizontal track;
        # place the independent same-number land perpendicular to that metal.
        second=first.Duplicate();second.SetPosition(first.GetPosition()+pcbnew.VECTOR2I_MM(0,5))
        if peer_id is None:
            second.m_Uuid.Clone(pcbnew.KIID());peer_id=force._uid(second)
        else:second.m_Uuid.Clone(pcbnew.KIID(peer_id))
        first.GetParentFootprint().Add(second)
    if fault=='missing':child.FindFootprintByReference('arbitrary_terminal').Remove(item(child,pad))
    elif fault=='identity':item(child,pad).m_Uuid.Clone(pcbnew.KIID())
    else:discard_items(child,[item(child,track)])
    proof=returns.receive(source,child)
    assert not proof['ok'] and proof['observed_source_terminals']==2
    if fault=='return':
        assert proof['complete'] and len(proof['regressed_terminals'])==1
        assert proof['regressed_terminals'][0]['pad_uuid']==pad
    else:assert not proof['complete'] and 'ground_return_preservation_terminal_inventory_changed'in proof['errors']
