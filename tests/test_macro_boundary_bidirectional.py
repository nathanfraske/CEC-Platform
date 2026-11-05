"""Native bidirectional Source-boundary composition, no fabricated eligibility."""
import copy
import json
import time

import pcbnew
import pytest
import cec_cell_row_rebuild as binding
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_boundary_composition as composition
import cec_ordinary_route_receiving as ordinary


def fixture(tmp_path, quarter=0, back=False):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    name = '/opaque_bidirectional_data'
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('arbitrary_native_owner')
    fp.SetValue('INA238AIDGSR')
    fp.SetField('MPN', 'INA238AIDGSR')
    fp.SetFPID(pcbnew.LIB_ID('Package_SO', 'VSSOP-10_3x3mm_P0.5mm'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    board.Add(fp)
    for pin in range(1, 11):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(pin))
        pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(8 + pin, 8))
        fp.Add(pad)
    pad = fp.FindPadByNumber('4')
    pad.SetNet(net)
    pad.SetPinType('bidirectional')
    pad.SetPinFunction('SDA')
    pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    edges = []
    for a, z in [((10, 10), (10, 10.5)), ((10, 10.5), (11, 11.5))]:
        edge = pcbnew.PCB_TRACK(board)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetWidth(200000)
        edge.SetLayer(pcbnew.F_Cu)
        edge.SetNet(net)
        board.Add(edge)
        edges.append(edge)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(11, 11.5))
    via.SetWidth(600000)
    via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)
    if back:
        fp.SetLayer(pcbnew.B_Cu)
        for p in fp.Pads():
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.B_Cu)
            p.SetLayerSet(layers)
        for edge in edges:
            edge.SetLayer(pcbnew.B_Cu)
    if quarter:
        for item in [fp, *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15, 15),
                pcbnew.EDA_ANGLE(quarter * 90, pcbnew.DEGREES_T))
    source = tmp_path/'source.kicad_pcb'
    field._save_field_snapshot(board, source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(
        net_settings=dict(classes=[dict(name='Default', track_width=.2,
            clearance=.2)], netclass_assignments={}))))
    stub, peer = edges
    uid, other = force._uid(stub), force._uid(peer)
    face = int(stub.GetLayer())
    plan = dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=binding._source_binding(board), board_hint='synthetic',
        retired_track_uuids=[uid], poses={fp.GetReference():[11, 10, 0]},
        device_contracts={fp.GetReference():roles.footprint_contract(fp)})
    request = dict(kind='source_boundary', net=name, width_nm=200000,
        a=dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()), layers=[face]),
        b=dict(native_uuids=[other], at_nm=list(stub.GetEnd()), layers=[face]))
    extras = [dict(change=dict(uuid=other, net=name,
        source_nm=[list(peer.GetStart()), list(peer.GetEnd())]),
        authority=dict(kind='positive_source_ordinary', native_source_uuid=other))]
    return board, source, plan, {'boundary:'+uid:request}, extras, uid, other, pad


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_actual_bidirectional_manufacturer_pin_keeps_both_original_cut_owners(tmp_path, quarter, back):
    board, source, plan, requests, extras, uid, other, pad = fixture(tmp_path, quarter, back)
    assert roles.footprint_contract(pad.GetParentFootprint())['pins']['4'] == 'signal_io'
    assert pad.GetNetname() in ordinary.eligible_nets(board, source, 'synthetic')
    before, raw, inputs = binding._source_binding(board), source.read_bytes(), copy.deepcopy(extras)
    pending, extended, proof = composition.compose(board, source, plan, requests,
        extras, deadline=time.monotonic()+10.)
    assert not pending and len(proof) == 1
    assert {row['change']['uuid'] for row in extended} == {uid, other}
    assert proof[0]['source_composition_proof']['no_additional_source_edge_retired']
    assert extras == inputs and binding._source_binding(board) == before and source.read_bytes() == raw


@pytest.mark.parametrize('fault', ['sensitive_class', 'power_class', 'source_pour',
    'wrong_native_pin', 'wrong_declared_role', 'unknown_package'])
def test_bidirectional_role_never_overrides_original_electrical_or_manufacturer_exclusions(tmp_path, fault):
    board, source, plan, requests, extras, uid, other, pad = fixture(tmp_path)
    if fault.endswith('_class'):
        name = 'Sense' if fault == 'sensitive_class' else 'Power'
        source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
            classes=[dict(name='Default', track_width=.2, clearance=.2),
                dict(name=name, track_width=.2, clearance=.2)],
            netclass_assignments={pad.GetNetname():[name]}))))
    elif fault == 'source_pour':
        zone = pcbnew.ZONE(board)
        zone.SetNet(pad.GetNet())
        zone.SetLayer(pcbnew.F_Cu)
        outline = zone.Outline()
        n = outline.NewOutline()
        for x, y in [(20, 20), (21, 20), (21, 21), (20, 21)]:
            outline.Append(x*1000000, y*1000000, n)
        board.Add(zone)
    elif fault == 'wrong_native_pin':
        # A power input in the same exact manufacturer package is not SDA.
        next(iter(requests.values()))['a']['pad_uuid'] = force._uid(
            pad.GetParentFootprint().FindPadByNumber('6'))
    elif fault == 'wrong_declared_role':
        plan['device_contracts'][pad.GetParentFootprint().GetReference()]['pins']['4'] = 'signal_input'
    else:
        pad.GetParentFootprint().SetFPID(pcbnew.LIB_ID('Package', 'unknown'))
    plan['source_native_binding'] = binding._source_binding(board)
    with pytest.raises(ValueError):
        composition.compose(board, source, plan, requests, extras, deadline=time.monotonic()+10.)
