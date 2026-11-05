"""No redundant route can be omitted on hints or hypothetical conductivity."""
from unittest import mock

import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_native_rated_continuation as continuation
from test_native_bus_column import fixture


def native(tmp_path, angle=0, back=False):
    board, owner, cap, bus, current = fixture(tmp_path, angle, back)
    layer = int(next(iter(owner.GetLayerSet().CuStack())))
    bus.SetLayer(layer); bus.SetEnd(owner.GetPosition())
    via = pcbnew.PCB_VIA(board); via.SetPosition(bus.GetStart())
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetWidth(1000000); via.SetDrill(300000); via.SetNet(owner.GetNet()); board.Add(via)
    return board, via, owner, bus, current, layer


def call(board, start, end, face, **kwargs):
    options = dict(source=board.GetFileName(), board_hint='arbitrary-native-source', layer=face,
        run_guard=lambda *args: True, endpoint_guard=lambda *args: True)
    options.update(kwargs)
    return continuation.plan(board, start.m_Uuid.AsString(), end.m_Uuid.AsString(), **options)


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_native_same_face_full_width_reuse_is_rotation_and_name_independent(tmp_path, angle, back):
    board, via, owner, bus, current, layer = native(tmp_path, angle, back)
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        proof = call(board, via, owner, layer)
    assert proof and proof['complete'] and proof['connected']
    assert proof['native_path_uuids'] == [q.m_Uuid.AsString() for q in (via, bus, owner)]
    assert proof['reused_track_rows'][0]['width_nm'] == bus.GetWidth()
    assert not proof['zones_or_intermediate_pads_or_layer_jumps_used']
    assert not proof['current_sharing_inferred'] and not proof['release_authority']
    assert not proof['plated_barrel_ampacity_qualified']
    assert before == field._field_snapshot_inventory(board)


@pytest.mark.parametrize('fault', ['thin', 'wrong_net', 'wrong_face', 'missing_track',
    'missing_anchor', 'unknown_current', 'small_barrel_web', 'non_plated', 'plane',
    'denied_track', 'unknown_track', 'truthy_track', 'denied_anchor', 'unknown_anchor',
    'truthy_anchor', 'class_floor', 'native_floor'])
def test_continuation_requires_actual_full_width_same_face_source_material(tmp_path, fault):
    board, via, owner, bus, current, layer = native(tmp_path)
    options = {}
    if fault == 'thin': bus.SetWidth(current['required_by_layer_nm'][layer]-1)
    if fault == 'wrong_net': owner.SetNetCode(board.GetNetcodeFromNetname('GND'))
    if fault == 'wrong_face': bus.SetLayer(pcbnew.B_Cu)
    if fault == 'missing_track': board.Remove(bus)
    if fault == 'missing_anchor': board.Remove(via)
    if fault == 'small_barrel_web': via.SetWidth(via.GetDrillValue()+1)
    if fault == 'non_plated': owner.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    if fault == 'plane': options['layer'] = pcbnew.In1_Cu
    if fault in ('denied_track', 'unknown_track', 'truthy_track'):
        options['run_guard'] = lambda *args: {'denied_track':False,
            'unknown_track':None,'truthy_track':1}[fault]
    if fault in ('denied_anchor', 'unknown_anchor', 'truthy_anchor'):
        options['endpoint_guard'] = lambda *args: {'denied_anchor':False,
            'unknown_anchor':None,'truthy_anchor':1}[fault]
    if fault == 'native_floor': board.GetDesignSettings().m_TrackMinWidth = bus.GetWidth()+1
    if fault == 'class_floor':
        actual = cells._netclass(board, str(owner.GetNetname()))
        actual['width'] = bus.GetWidth()+1
    else: actual = cells._netclass(board, str(via.GetNetname()))
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths',
            return_value=None if fault == 'unknown_current' else current), \
            mock.patch.object(cells, '_netclass', return_value=actual):
        assert call(board, via, owner, layer, **options) is None
    assert before == field._field_snapshot_inventory(board)


def test_direct_actual_native_anchor_contact_needs_no_extra_tail(tmp_path):
    board, via, owner, bus, current, layer = native(tmp_path)
    via.SetPosition(owner.GetPosition()); board.Remove(bus)
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        proof = call(board, via, owner, layer,
            run_guard=lambda *args: (_ for _ in ()).throw(AssertionError('no borrowed track')))
    assert proof and proof['reused_track_rows'] == []
    assert len(proof['native_path_uuids']) == 2 and before == field._field_snapshot_inventory(board)


def branch_fixture(tmp_path, angle=0, back=False):
    board, via, owner, bus, current, layer = native(tmp_path, angle, back)
    start, end = pcbnew.VECTOR2I(*bus.GetStart()), pcbnew.VECTOR2I(*bus.GetEnd())
    mid = pcbnew.VECTOR2I((start.x+end.x)//2, (start.y+end.y)//2)
    bus.SetStart(mid)
    parent_path = tmp_path/'retained-parent.kicad_pcb'
    board.Remove(via)
    pcbnew.SaveBoard(str(parent_path), board)
    parent = pcbnew.LoadBoard(str(parent_path))
    board.Add(via)
    added = pcbnew.PCB_TRACK(board)
    added.SetStart(start); added.SetEnd(mid); added.SetWidth(bus.GetWidth())
    added.SetLayer(layer); added.SetNet(owner.GetNet()); board.Add(added)
    return board, parent, via, owner, bus, added, current, layer


def entry_call(board, parent, owner, layer, **options):
    values = dict(source=parent.GetFileName(), board_hint='renamed-native-branch',
        layer=layer, run_guard=lambda *args: True, endpoint_guard=lambda *args: True)
    values.update(options)
    return continuation.retained_entry(board, parent, owner.m_Uuid.AsString(), **values)


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_added_source_stub_can_be_absent_only_with_actual_rated_retained_entry(tmp_path, angle, back):
    board, parent, via, owner, bus, added, current, layer = branch_fixture(tmp_path, angle, back)
    before = field._field_snapshot_inventory(board)
    original = field._field_snapshot_inventory(parent)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        proof = entry_call(board, parent, owner, layer)
    assert proof and proof['complete'] and proof['connected']
    assert proof['retained_track_uuids'] == [bus.m_Uuid.AsString()]
    assert proof['added_track_uuids'] == [added.m_Uuid.AsString()]
    assert proof['added_barrel_uuid'] == via.m_Uuid.AsString()
    assert not proof['incident_added_pad_segment_inferred']
    assert not proof['current_sharing_inferred'] and not proof['release_authority']
    assert before == field._field_snapshot_inventory(board)
    assert original == field._field_snapshot_inventory(parent)


@pytest.mark.parametrize('fault', ['thin_added', 'old_moved', 'old_thinned',
    'missing_added', 'missing_barrel', 'wrong_added_net', 'small_barrel_web',
    'unknown_current', 'denied_track', 'denied_anchor', 'foreign_face', 'too_many_portals'])
def test_retained_entry_does_not_replace_native_current_or_ownership_receiving(tmp_path, fault):
    board, parent, via, owner, bus, added, current, layer = branch_fixture(tmp_path)
    options = {}
    if fault == 'thin_added': added.SetWidth(current['required_by_layer_nm'][layer]-1)
    if fault == 'old_moved': bus.SetStart(pcbnew.VECTOR2I_MM(14,11))
    if fault == 'old_thinned': bus.SetWidth(bus.GetWidth()-1)
    if fault == 'missing_added': board.Remove(added)
    if fault == 'missing_barrel': board.Remove(via)
    if fault == 'wrong_added_net': added.SetNetCode(board.GetNetcodeFromNetname('GND'))
    if fault == 'small_barrel_web': via.SetWidth(via.GetDrillValue()+1)
    if fault == 'denied_track': options['run_guard'] = lambda *args: False
    if fault == 'denied_anchor': options['endpoint_guard'] = lambda *args: False
    if fault == 'foreign_face': added.SetLayer(pcbnew.B_Cu)
    if fault == 'too_many_portals':
        for i in range(6):
            extra = pcbnew.PCB_VIA(board); extra.SetPosition(pcbnew.VECTOR2I_MM(1+i,1))
            extra.SetViaType(pcbnew.VIATYPE_THROUGH); extra.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            extra.SetWidth(1000000); extra.SetDrill(300000); extra.SetNet(owner.GetNet()); board.Add(extra)
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths',
            return_value=None if fault == 'unknown_current' else current):
        assert entry_call(board, parent, owner, layer, **options) is None
    assert before == field._field_snapshot_inventory(board)


def test_phantom_zone_or_intermediate_pad_cannot_bridge_a_real_copper_gap(tmp_path):
    board, via, owner, bus, current, layer = native(tmp_path)
    bus.SetEnd(pcbnew.VECTOR2I_MM(12,10))
    other = pcbnew.PCB_TRACK(board); other.SetStart(pcbnew.VECTOR2I_MM(13,10))
    other.SetEnd(owner.GetPosition()); other.SetWidth(bus.GetWidth()); other.SetLayer(layer)
    other.SetNet(owner.GetNet()); board.Add(other)
    bridge = pcbnew.PAD(owner.GetParentFootprint()); bridge.SetNumber('99'); bridge.SetNet(owner.GetNet())
    bridge.SetAttribute(pcbnew.PAD_ATTRIB_SMD); bridge.SetLayerSet(pcbnew.PAD.SMDMask())
    bridge.SetShape(pcbnew.PAD_SHAPE_RECT); bridge.SetSize(pcbnew.VECTOR2I_MM(2,1))
    bridge.SetPosition(pcbnew.VECTOR2I_MM(12.5,10)); owner.GetParentFootprint().Add(bridge)
    zone = pcbnew.ZONE(board); zone.SetLayer(layer); zone.SetNet(owner.GetNet())
    zone.Outline().NewOutline()
    for x,y in ((10,9),(16,9),(16,11),(10,11)): zone.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    board.Add(zone)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        assert call(board, via, owner, layer) is None


def test_native_track_budget_and_timeout_do_not_grant_continuity(tmp_path):
    board, via, owner, bus, current, layer = native(tmp_path)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        assert call(board, via, owner, layer, max_items=2) is None
        with mock.patch.object(continuation.time, 'monotonic', side_effect=[0.,3.]):
            assert call(board, via, owner, layer) is None


@pytest.mark.parametrize('options', [dict(timeout_s=0),dict(timeout_s=float('inf')),
    dict(timeout_s=True),dict(max_items=True),dict(max_items=1025),dict(run_guard=None),
    dict(endpoint_guard=None),dict(source=''),dict(board_hint=''),dict(layer=True)])
def test_bounded_explicit_native_permissions_required(tmp_path, options):
    board, via, owner, bus, current, layer = native(tmp_path)
    with pytest.raises(ValueError): call(board, via, owner, layer, **options)


def retained(tmp_path, angle=0, back=False):
    board, via, owner, bus, current, layer = native(tmp_path, angle, back)
    other = pcbnew.PCB_TRACK(board); other.SetStart(bus.GetStart()); other.SetEnd(bus.GetEnd())
    other.SetWidth(bus.GetWidth()); other.SetLayer(pcbnew.B_Cu if layer == pcbnew.F_Cu else pcbnew.F_Cu)
    other.SetNet(owner.GetNet()); board.Add(other)
    return board, via, owner, bus, other, current, layer


def portal_call(board, via, layer, **kwargs):
    options = dict(net=str(via.GetNetname()), source=board.GetFileName(),
        board_hint='arbitrary-native-source', from_layer=layer,
        to_layer=pcbnew.B_Cu if layer == pcbnew.F_Cu else pcbnew.F_Cu,
        run_guard=lambda *args: True, endpoint_guard=lambda *args: True)
    options.update(kwargs)
    return continuation.portal(board, tuple(via.GetPosition()), **options)


@pytest.mark.parametrize('angle,back', [(0,False),(90,False),(180,True),(270,True)])
def test_existing_actual_two_face_source_portal_needs_no_new_barrel(tmp_path, angle, back):
    board, via, owner, bus, other, current, layer = retained(tmp_path, angle, back)
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current):
        proof = portal_call(board, via, layer)
    assert proof and proof['via_uuid'] == via.m_Uuid.AsString()
    assert proof['actual_native_contacts']['actual_contact_layers'] == ['B.Cu','F.Cu']
    assert before == field._field_snapshot_inventory(board) and not proof['release_authority']


@pytest.mark.parametrize('fault', ['single_face', 'thin_web', 'small_factory_land',
    'small_factory_drill', 'small_factory_annulus', 'inner_contact', 'class_floor',
    'duplicate', 'plane', 'denied_capture', 'unknown_capture', 'truthy_capture',
    'denied_anchor', 'unknown_current'])
def test_retained_does_not_mean_current_or_process_qualified(tmp_path, fault):
    board, via, owner, bus, other, current, layer = retained(tmp_path)
    options = {}; spec = cells._netclass(board, str(via.GetNetname()))
    if fault == 'single_face': board.Remove(other)
    if fault == 'thin_web': via.SetWidth(via.GetDrillValue()+1)
    if fault == 'small_factory_land': board.GetDesignSettings().m_ViasMinSize = via.GetWidth(layer)+1
    if fault == 'small_factory_drill': board.GetDesignSettings().m_MinThroughDrill = via.GetDrillValue()+1
    if fault == 'small_factory_annulus': board.GetDesignSettings().m_ViasMinAnnularWidth = via.GetWidth(layer)
    if fault == 'inner_contact': other.SetLayer(pcbnew.In2_Cu)
    if fault == 'class_floor': spec['width'] = via.GetWidth(layer)-via.GetDrillValue()+1
    if fault == 'duplicate':
        copy = pcbnew.PCB_VIA(board); copy.SetPosition(via.GetPosition()); copy.SetNet(via.GetNet()); board.Add(copy)
    if fault == 'plane': options['to_layer'] = pcbnew.In1_Cu
    if fault in ('denied_capture','unknown_capture','truthy_capture'):
        options['run_guard'] = lambda *args: {'denied_capture':False,
            'unknown_capture':None,'truthy_capture':1}[fault]
    if fault == 'denied_anchor': options['endpoint_guard'] = lambda *args: False
    before = field._field_snapshot_inventory(board)
    with mock.patch.object(cells, '_supply_current_widths',
            return_value=None if fault == 'unknown_current' else current), \
            mock.patch.object(cells, '_netclass', return_value=spec):
        assert portal_call(board, via, layer, **options) is None
    assert before == field._field_snapshot_inventory(board)
