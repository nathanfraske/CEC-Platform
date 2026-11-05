import time

import pcbnew
import pytest

import cec_constraints as constraints
import cec_power_connectivity as power
import cec_device_power_roles as device_roles


def fixture():
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, '+3V3')
    board.Add(net)
    ground = pcbnew.NETINFO_ITEM(board, 'GND')
    board.Add(ground)
    grounds = []
    pads = []
    for ref, x in [('U_A', 10), ('C_A', 11), ('U_B', 20), ('C_B', 21)]:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        if ref.startswith('U'):
            fp.SetValue('INA181A2IDBVR')
        board.Add(fp)
        pad = pcbnew.PAD(fp)
        pad.SetNumber('6' if ref.startswith('U') else '1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x, 10))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layers)
        pad.SetNet(net)
        fp.Add(pad)
        pads.append(pad)
        if ref.startswith('U'):
            # A manufacturer-complete power fixture includes the actual GND
            # pin; a missing required ground is independently a real defect.
            g = pcbnew.PAD(fp); g.SetNumber('2'); g.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            g.SetShape(pcbnew.PAD_SHAPE_RECT); g.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
            g.SetPosition(pcbnew.VECTOR2I_MM(x, 14)); g.SetLayerSet(layers)
            g.SetNet(ground); fp.Add(g); grounds.append(g)
    for a, b in [(pads[0], pads[1]), (pads[2], pads[3])]:
        trace = pcbnew.PCB_TRACK(board)
        trace.SetStart(a.GetPosition())
        trace.SetEnd(b.GetPosition())
        trace.SetLayer(pcbnew.F_Cu)
        trace.SetWidth(pcbnew.FromMM(.2))
        trace.SetNet(net)
        board.Add(trace)
    trace = pcbnew.PCB_TRACK(board); trace.SetStart(grounds[0].GetPosition())
    trace.SetEnd(grounds[1].GetPosition()); trace.SetLayer(pcbnew.F_Cu)
    trace.SetWidth(200000); trace.SetNet(ground); board.Add(trace)
    return board, pads


def test_native_inventory_sees_both_ic_islands_without_airwire_names(monkeypatch):
    board, pads = fixture()
    before = [(str(p.m_Uuid.AsString()), p.GetNetCode(), list(p.GetPosition())) for p in pads]
    monkeypatch.setattr(constraints, '_unconnected',
        lambda *_: [('+3V3', ['Track [+3V3]', 'Pad 1 [+3V3] of C_B'])])
    verdict = constraints._chk_ic_power(board, '', {})
    assert verdict[0] is False
    assert [r['type'] for r in verdict[2]] == ['power_net_partition']
    assert {r['ic'] for r in verdict[2][0]['native_terminals']} == {'U_A', 'U_B'}
    assert all(r['energization_inferred'] is False for r in verdict[2])
    assert before == [(str(p.m_Uuid.AsString()), p.GetNetCode(), list(p.GetPosition())) for p in pads]


def test_all_ic_terminal_partitions_are_stable_if_witness_changes():
    board, _ = fixture()
    first = power.inventory(board)
    # Added copper inside an already-connected island is not a new terminal
    # partition and must not change any IC classification.
    trace = pcbnew.PCB_TRACK(board)
    trace.SetStart(pcbnew.VECTOR2I_MM(10, 10))
    trace.SetEnd(pcbnew.VECTOR2I_MM(10, 10.5))
    trace.SetLayer(pcbnew.F_Cu)
    trace.SetWidth(pcbnew.FromMM(.2))
    trace.SetNetCode(board.GetNetcodeFromNetname('+3V3'))
    board.Add(trace)
    second = power.inventory(board)
    assert first == second
    assert len(power.fragmented_ics(second)) == 2


def test_joining_actual_islands_clears_checker():
    board, pads = fixture()
    trace = pcbnew.PCB_TRACK(board)
    trace.SetStart(pads[1].GetPosition())
    trace.SetEnd(pads[2].GetPosition())
    trace.SetLayer(pcbnew.F_Cu)
    trace.SetWidth(pcbnew.FromMM(.2))
    trace.SetNetCode(pads[0].GetNetCode())
    board.Add(trace)
    assert constraints._chk_ic_power(board, '', {})[0] is True


def test_isolated_terminal_is_not_confused_with_connected_island():
    board, pads = fixture()
    pads[3].SetNetCode(0)
    rows = power.fragmented_ics(power.inventory(board))
    assert next(r for r in rows if r['ic'] == 'U_A')['isolated_terminal'] is False
    assert next(r for r in rows if r['ic'] == 'U_B')['isolated_terminal'] is True


@pytest.mark.parametrize('seconds', [0, 11, float('nan'), True])
def test_invalid_bounds_refuse(seconds):
    with pytest.raises(ValueError):
        power.inventory(pcbnew.BOARD(), timeout_s=seconds)


def test_budget_refuses_partial_inventory(monkeypatch):
    board, _ = fixture()
    ticks = iter([0., 20.])
    monkeypatch.setattr(time, 'monotonic', lambda: next(ticks))
    with pytest.raises(ValueError, match='deadline'):
        power.inventory(board)


def test_inventory_bound_refuses():
    board, _ = fixture()
    with pytest.raises(ValueError, match='inventory_bound'):
        power.inventory(board, max_items=1)


@pytest.mark.parametrize('value,pin', [('INA181A2IDBVR', '3'), ('INA181A2IDBVR', '4'),
    ('INA238', '10'), ('INA238', '9'), ('INA238', '8')])
def test_measurement_pin_on_supply_named_net_is_not_power_escape(value, pin):
    board, pads = fixture()
    fp = pads[0].GetParentFootprint()
    fp.SetValue(value)
    sense = pcbnew.PAD(fp)
    sense.SetNumber(pin)
    sense.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    sense.SetShape(pcbnew.PAD_SHAPE_RECT)
    sense.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
    sense.SetPosition(pcbnew.VECTOR2I_MM(25, 25))
    sense.SetLayerSet(pcbnew.PAD.SMDMask())
    sense.SetNet(board.FindNet('+3V3'))
    fp.Add(sense)
    report = power.inventory(board)
    rows = power.fragmented_ics(report)
    assert not any(r['uuid'] == str(sense.m_Uuid.AsString()) for r in rows)
    assert {r['pin'] for r in rows} == {'6'}
    assert not report['unresolved_ic_pin_roles']


def test_catalog_supply_role_follows_renamed_rail_and_ref():
    board, _ = fixture()
    for fp in board.GetFootprints():
        if fp.GetReference().startswith('U'):
            fp.SetReference('RENAMED_' + fp.GetReference())
    net = board.FindNet('+3V3')
    # All native consumers use the fitted role, not voltage-name matching.
    net.SetNetname('/arbitrary_rail')
    rows = power.fragmented_ics(power.inventory(board))
    assert len(rows) == 2 and all(r['net'] == '/arbitrary_rail' for r in rows)
    assert all(not r['isolated_terminal'] and len(r['component_pad_uuids']) == 2 for r in rows)


def test_native_power_type_qualifies_unknown_device_but_input_does_not():
    board, pads = fixture()
    for pad in (pads[0], pads[2]):
        pad.GetParentFootprint().SetValue('UNLISTED_DEVICE')
    pads[0].SetPinType('power_in')
    pads[2].SetPinType('input')
    rows = power.fragmented_ics(power.inventory(board))
    assert len(rows) == 1 and rows[0]['ic'] == 'U_A'


def test_bypass_catalog_is_not_assumed_to_cover_every_device_power_role():
    board, pads = fixture()
    pads[0].SetNumber('99')
    report = power.inventory(board)
    # Known supply pin 6 is now missing, and an untyped pin 99 on this rail
    # stays unresolved; absence from the bypass list is NOT a signal role.
    assert report['supply_pin_contract_errors']
    assert any(r['ref'] == 'U_A' and r['pin'] == '99' for r in report['unresolved_ic_pin_roles'])


@pytest.mark.parametrize('value,pin,expected', [
    ('TPS2121RUXR', '8', 'supply'), ('TPS2121RUXR', '6', 'not_power'),
    ('INA238', '1', 'not_power'), ('INA238AIDGSR', '2', 'not_power'),
    ('LP5907MFX-3.3', '3', 'not_power'), ('TLV62569DBVR', '1', 'not_power'),
    ('TLV75533PDRVR', '4', 'not_power'), ('TLV75533PDBVR', '3', 'not_power')])
def test_manufacturer_pin_roles_are_not_bypass_or_net_name_inferences(value, pin, expected):
    catalog = device_roles.contract(value)
    assert catalog and catalog['source'].startswith('https://www.ti.com/')
    assert power.terminal_role('/renamed_supply', pin, '', set(), manufacturer=catalog)[0] == expected


def test_package_role_catalog_does_not_transfer_to_unreviewed_packages():
    assert device_roles.contract('TLV62569DRLR') is None
    assert device_roles.contract('LP5907SNX-3.3') is None
    assert device_roles.contract('TLV75533PDQNR') is None


def test_second_mux_output_is_required_without_extra_bypass_requirement():
    import cec_device_bypass as bypass
    pins = device_roles.contract('TPS2121RUXR')['pins']
    assert {p for p, r in pins.items() if r in ('power_input', 'power_output')} == {'1', '2', '7', '8'}
    assert len(list(bypass.requirements_for_value('TPS2121RUXR'))) == 3


def mux_fixture():
    board = pcbnew.BOARD()
    for name in ('/custom/out', '/custom/in1', '/custom/in2', 'GND', '/wrong/out'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('U_RENAMED_MUX')
    fp.SetValue('TPS2121RUXR')
    board.Add(fp)
    for pin, net in [('1', '/custom/out'), ('8', '/custom/out'),
                     ('7', '/custom/in1'), ('2', '/custom/in2'), ('12', 'GND')]:
        pad = pcbnew.PAD(fp)
        pad.SetNumber(pin)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.4, .8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(10 + int(pin), 10))
        pad.SetNet(board.FindNet(net))
        fp.Add(pad)
    return board, fp


def test_actual_native_second_output_is_not_skipped_or_treated_as_control():
    board, _ = mux_fixture()
    report = power.inventory(board)
    assert not report['supply_pin_contract_errors'] and not report['unresolved_ic_pin_roles']
    rows = [r for r in power.fragmented_ics(report) if r['net'] == '/custom/out']
    assert {r['pin'] for r in rows} == {'1', '8'}
    assert all(r['role'] == 'supply' and r['isolated_terminal'] for r in rows)


@pytest.mark.parametrize('fault', ['missing_output', 'split_output', 'unnetted_ground'])
def test_manufacturer_power_pin_and_common_domain_contracts_cannot_be_omitted(fault):
    board, fp = mux_fixture()
    if fault == 'missing_output':
        fp.Remove(fp.FindPadByNumber('8'))
    elif fault == 'split_output':
        fp.FindPadByNumber('8').SetNet(board.FindNet('/wrong/out'))
    else:
        fp.FindPadByNumber('12').SetNetCode(0)
    errors = power.inventory(board)['supply_pin_contract_errors']
    assert len(errors) == 1
    assert errors[0]['reason'] == {
        'missing_output': 'selected_device_supply_pad_missing',
        'split_output': 'manufacturer_common_domain_net_mismatch',
        'unnetted_ground': 'device_ground_pad_unnetted'}[fault]


def test_unknown_power_named_terminal_cannot_receive_pass_or_escape_role():
    board, pads = fixture()
    for pad in (pads[0], pads[2]):
        pad.GetParentFootprint().SetValue('UNLISTED_DEVICE')
    report = power.inventory(board)
    assert not power.fragmented_ics(report)
    assert len(report['unresolved_ic_pin_roles']) == 2
    verdict = constraints._chk_ic_power(board, '', {})
    assert verdict[0] is False and all(r['type'] == 'power_pin_role_unresolved' for r in verdict[2])


def test_only_actual_one_terminal_island_is_local_escape_target():
    board, pads = fixture()
    pads[3].SetNetCode(0)
    verdict = constraints._chk_ic_power(board, '', {})
    escapes = [r for r in verdict[2] if r['type'] == 'power_escape']
    assert len(escapes) == 1 and escapes[0]['ic'] == 'U_B'
    assert len(escapes[0]['native_terminals']) == 1
    assert any(r['type'] == 'power_net_partition' for r in verdict[2])


def test_generic_directive_consumer_does_not_expand_domain_or_unknown_into_all_ics():
    board, _ = fixture()
    verdict = constraints._chk_ic_power(board, '', {})
    rule = next(c for c in constraints.REGISTRY if c.id == 'ic-power-ground-connected')
    directives = constraints.directives([(rule, 'FAIL', verdict[1], verdict[2])])
    assert power.local_escape_ic_refs(directives) == []
    assert power.local_escape_ic_refs([
        dict(type='power_net_partition', directive='power_escape', ic='NOT_A_LOCAL_TARGET'),
        dict(type='power_pin_role_unresolved', ic='UNKNOWN'),
        dict(type='power_escape', ic=False),
        dict(directive='power_escape', ic='LEGACY_TARGET'),
        dict(type='power_escape', ic='ACTUAL_ISOLATED'),
    ]) == ['ACTUAL_ISOLATED', 'LEGACY_TARGET']


@pytest.mark.parametrize('fault', ['missing', 'unnetted', 'grounded'])
def test_missing_or_unnetted_catalog_supply_pin_cannot_pass(fault):
    board, pads = fixture()
    if fault == 'missing':
        pads[0].SetNumber('3')
    elif fault == 'unnetted':
        pads[0].SetNetCode(0)
    else:
        ground = board.GetNetInfo().GetNetItem('GND')
        pads[0].SetNet(ground)
    report = power.inventory(board)
    assert len(report['supply_pin_contract_errors']) == 1
    assert constraints._chk_ic_power(board, '', {})[0] is False


def test_ground_tied_reference_is_explicit_but_not_a_device_ground_escape():
    board, _ = fixture()
    owner = board.FindFootprintByReference('U_A')
    ref = pcbnew.PAD(owner); ref.SetNumber('5'); ref.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    ref.SetShape(pcbnew.PAD_SHAPE_RECT); ref.SetLayerSet(pcbnew.PAD.SMDMask())
    ref.SetSize(pcbnew.VECTOR2I_MM(.5, .5)); ref.SetPosition(pcbnew.VECTOR2I_MM(10, 16))
    ref.SetNet(board.GetNetInfo().GetNetItem('GND')); owner.Add(ref)
    report = power.inventory(board)
    target = next(r for r in power.fragmented_ics(report) if r['pin'] == '5')
    assert target['role'] == 'ground_reference' and target['no_other_native_contacts']
    assert device_roles.contract(owner.GetValue())['pins']['2'] == 'ground'
    verdict = constraints._chk_ic_power(board, '', {})
    reference = [r for r in verdict[2] if r['type'] == 'reference_escape']
    assert len(reference) == 1 and reference[0]['ic'] == 'U_A'
    assert not any(r['type'] == 'power_escape' and any(t['pin'] == '5'
        for t in r['native_terminals']) for r in verdict[2])
    assert device_roles.contract('INA181A2IDCKR')['pins']['3'] == 'power_input'


def test_offset_reference_is_not_rewritten_as_ground_or_supply():
    contract = device_roles.contract('INA181A2IDBVR')
    assert power.terminal_role('MIDRAIL', '5', '', set(), manufacturer=contract)[0] == 'not_power'
