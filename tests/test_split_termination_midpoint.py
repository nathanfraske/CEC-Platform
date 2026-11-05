"""Only a closed passive split midpoint, never CAN lanes, is scalar-owned."""
from unittest import mock
import pcbnew
import pytest
import cec_pair_semantics as semantics
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary


def fixture(*, angle=0, back=False, prefix='/context/', midpoint='CAN_MID', refs=('X','Y','Z')):
    b = pcbnew.BOARD(); b.SetCopperLayerCount(6)
    names = [prefix+'CAN_H', prefix+'CAN_L', prefix+midpoint, 'GND', 'OTHER']
    for name in names:
        b.Add(pcbnew.NETINFO_ITEM(b, name))
    parts = []
    for idx, (kind, value, mpn, nets) in enumerate([
        ('R_0402_1005Metric', '60.4', 'GR0402F60R4TAG00', (names[2], names[0])),
        ('R_0402_1005Metric', '60.4', 'GR0402F60R4TAG00', (names[2], names[1])),
        ('C_0402_1005Metric', '4n7', '0402B472K500NT', (names[2], 'GND'))]):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference(refs[idx]); fp.SetValue(value)
        fp.SetField('MPN', mpn); fp.SetFPID(pcbnew.LIB_ID('Passive', kind))
        b.Add(fp); parts.append(fp)
        for pin, name in enumerate(nets, 1):
            pad = pcbnew.PAD(fp); pad.SetNumber(str(pin)); pad.SetNet(b.FindNet(name))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.82, .64)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(pcbnew.VECTOR2I_MM(10+idx*3, 10+pin)); fp.Add(pad)
        if back: fp.Flip(pcbnew.VECTOR2I_MM(10,10), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle: fp.Rotate(pcbnew.VECTOR2I_MM(10,10), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    return b, parts, names


@pytest.mark.parametrize('angle,back,prefix,midpoint,refs', [
    (0, False, '/a/', 'CAN_MID', ('R1','R2','C1')),
    (90, False, '/elsewhere/', 'PASSIVE_CENTER', ('A','B','C')),
    (180, True, '/another/', 'CAN_MID_NODE', ('Q','X','Y')),
    (270, True, '/deep/context/', 'OTHER_CENTER', ('F','G','H'))])
def test_exact_passive_junction_is_detected_without_ref_or_pose_heuristic(
        angle, back, prefix, midpoint, refs):
    b, _parts, names = fixture(angle=angle, back=back, prefix=prefix, midpoint=midpoint, refs=refs)
    proof = semantics.split_termination_midpoints(b)
    assert set(proof) == {names[2]}
    assert set(proof[names[2]]['pair_members']) == set(names[:2])
    assert not proof[names[2]]['pair_member_scalar_permission']
    assert not proof[names[2]]['electrical_or_release_qualified']
    resolver = lambda net: dict(name='CAN', track_width=.2, clearance=.2)
    assert names[2] in fr._ordinary_final_completion_nets(b, resolver)
    assert not set(names[:2]) & set(fr._ordinary_final_completion_nets(b, resolver))
    with mock.patch.object(fr, '_project_netclass_resolver', return_value=resolver), \
            mock.patch.object(ordinary.topology, 'board_current_domains', return_value={}), \
            mock.patch.object(ordinary.synth, 'spec_net_current_contract', return_value=None):
        selected = ordinary.eligible_nets(b, 'synthetic', 'synthetic')
    assert names[2] in selected and not set(names[:2]) & selected


@pytest.mark.parametrize('fault', ['unknown_cap','unknown_resistor','no_mpn','wrong_value',
    'asymmetric','too_low','too_high','cap_power_return','cap_dnp','res_dnp','same_member',
    'missing_mate','extra_terminal','same_net_passive','no_cap','drilled','unconnected'])
def test_missing_unknown_or_loaded_midpoint_does_not_acquire_pair_bypass(fault):
    b, parts, names = fixture()
    first, second, cap = parts
    if fault == 'unknown_cap': cap.SetFPID(pcbnew.LIB_ID('Unknown','Unknown'))
    if fault == 'unknown_resistor': first.SetFPID(pcbnew.LIB_ID('Unknown','Unknown'))
    if fault == 'no_mpn': cap.SetField('MPN','')
    if fault == 'wrong_value': first.SetValue('SIGNAL')
    if fault == 'asymmetric': first.SetValue('50')
    if fault == 'too_low': cap.SetValue('1p')
    if fault == 'too_high': cap.SetValue('100u')
    if fault == 'cap_power_return': cap.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    if fault == 'cap_dnp': cap.SetDNP(True)
    if fault == 'res_dnp': first.SetDNP(True)
    if fault == 'same_member': second.FindPadByNumber('2').SetNet(b.FindNet(names[0]))
    if fault == 'missing_mate': b.FindNet(names[1]).SetNetname('UNPAIRED_SIGNAL')
    if fault == 'extra_terminal':
        pad=pcbnew.PAD(first); pad.SetNumber('3'); pad.SetNet(b.FindNet(names[2])); first.Add(pad)
    if fault == 'same_net_passive': first.FindPadByNumber('2').SetNet(b.FindNet(names[2]))
    if fault == 'no_cap': cap.SetFPID(pcbnew.LIB_ID('Passive','R_0402_1005Metric'))
    if fault == 'drilled': cap.FindPadByNumber('1').SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    if fault == 'unconnected': first.FindPadByNumber('2').SetNetCode(0)
    assert not semantics.split_termination_midpoints(b)
    assert names[2] not in fr._ordinary_final_completion_nets(b,
        lambda _net:dict(name='CAN',track_width=.2))


def test_source_current_or_non_can_specialized_class_still_owns_midpoint():
    b, _parts, names = fixture()
    resolver = lambda _net:dict(name='CAN',track_width=.2)
    with mock.patch.object(fr,'_project_netclass_resolver',return_value=resolver), \
            mock.patch.object(ordinary.topology,'board_current_domains',return_value={names[2]:{}}), \
            mock.patch.object(ordinary.synth,'spec_net_current_contract',return_value=None):
        assert names[2] not in ordinary.eligible_nets(b,'synthetic','synthetic')
    for role in ('power','clock','usb','differential','sense'):
        with mock.patch.object(fr,'_project_netclass_resolver',return_value=lambda _net:dict(name=role,track_width=.2)), \
                mock.patch.object(ordinary.topology,'board_current_domains',return_value={}), \
                mock.patch.object(ordinary.synth,'spec_net_current_contract',return_value=None):
            assert names[2] not in ordinary.eligible_nets(b,'synthetic','synthetic')
