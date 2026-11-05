from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_rc_return_pivot as pivot
import cec_rc_return_pivot_receiving as receiving
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, *, rotation=0, back=False, ref='FILTER_CAP'):
    board = _board([], edge=(0, 0, 30, 30))
    board.SetCopperLayerCount(6)
    properties = board.GetProperties()
    properties['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    board.SetProperties(properties)
    for name in ('GND', '/CONTROL'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for name, value, pads in [(ref, '100nF', [('1', '/CONTROL', 12, 15), ('2', 'GND', 11, 15)]),
            ('SOURCE_NODE', '', [('1', 'GND', 15, 15)])]:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(name)
        fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I_MM(11.5 if name == ref else 15, 15))
        for number, net, x, y in pads:
            p = pcbnew.PAD(fp)
            p.SetNumber(number)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.F_Cu if name == ref else pcbnew.In1_Cu)
            p.SetLayerSet(ls)
            p.SetNet(board.FindNet(net))
            p.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            fp.Add(p)
        board.Add(fp)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
    track(board, '/CONTROL', (12, 15), (12, 12))
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetNet(board.FindNet('GND'))
    zone.SetLocalClearance(pcbnew.FromMM(.2))
    zone.Outline().NewOutline()
    for at in [(1, 1), (29, 1), (29, 29), (1, 29)]:
        zone.Outline().Append(pcbnew.VECTOR2I_MM(*at))
    board.Add(zone)
    if back:
        fp = board.FindFootprintByReference(ref)
        fp.Flip(pcbnew.VECTOR2I_MM(15, 15), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for t in board.GetTracks():
            t.Flip(pcbnew.VECTOR2I_MM(15, 15), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if rotation:
        for item in [*board.GetFootprints(), *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15, 15), pcbnew.EDA_ANGLE(rotation, pcbnew.DEGREES_T))
    additive._ground_refill(board)
    source = tmp_path/'source'/'board.kicad_pcb'
    source.parent.mkdir()
    field._save_field_snapshot(board, source)
    target = force._copy_family(source, tmp_path/'child')
    child = pcbnew.LoadBoard(str(target))
    cap = child.FindFootprintByReference(ref)
    cap.Rotate(cap.FindPadByNumber('1').GetPosition(), pcbnew.EDA_ANGLE(180, pcbnew.DEGREES_T))
    pad = cap.FindPadByNumber('2')
    via = pcbnew.PCB_VIA(child)
    via.SetPosition(pad.GetPosition())
    via.SetNet(pad.GetNet())
    via.SetWidth(pcbnew.FromMM(.35))
    via.SetDrill(pcbnew.FromMM(.25))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    child.Add(via)
    assert fr.group_local_pofv_signal_vias(child, [via])
    additive._ground_refill(child)
    field._save_field_snapshot(child, target)
    additive.bind_local_via_rule(child, target)
    return source, target, ref


@pytest.mark.parametrize('rotation,back,ref', [(0, False, 'FILTER_CAP'),
    (90, False, 'RC_OTHER'), (180, True, 'RENAMED_X'), (270, True, 'LAST_PART')])
def test_actual_native_rc_ground_pivot_is_received(tmp_path, rotation, back, ref):
    source, target, ref = fixture(tmp_path, rotation=rotation, back=back, ref=ref)
    before = [p.read_bytes() for p in (source, target)]
    receipt = receiving.receive(source, target, board_hint='synthetic')
    assert receipt['ok'] and receipt['complete'], {k: receipt.get(k) for k in ('errors', 'new_native_faults', 'physical_placement')}
    assert receipt['source_opens'] == 1 and receipt['opens'] == 0
    assert receipt['original_native_conductor_and_terminal_partitions_preserved']
    assert receipt['independent_pose_and_additive_replay']['ok']
    assert not receipt['power_authority'] and not receipt['release_authority']
    assert before == [p.read_bytes() for p in (source, target)]


@pytest.mark.parametrize('fault', ['anchor', 'value', 'return_net', 'power_addition',
    'old_trace', 'outline', 'new_zone', 'flip', 'nonquarter', 'bad_barrel', 'rule'])
def test_rc_return_scope_cannot_hide_unrelated_or_protected_changes(tmp_path, fault):
    source, target, ref = fixture(tmp_path)
    board = pcbnew.LoadBoard(str(target))
    fp = board.FindFootprintByReference(ref)
    if fault == 'anchor':
        fp.Move(pcbnew.VECTOR2I_MM(.01, 0))
    elif fault == 'value':
        fp.SetValue('10nF')
    elif fault == 'return_net':
        fp.FindPadByNumber('2').SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
    elif fault == 'power_addition':
        track(board, '/CONTROL', (24, 24), (25, 24))
    elif fault == 'old_trace':
        next(t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK').SetWidth(250000)
    elif fault == 'outline':
        next(d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts).Move(pcbnew.VECTOR2I_MM(.1, 0))
    elif fault == 'new_zone':
        z = pcbnew.ZONE(board)
        z.SetLayer(pcbnew.F_Cu)
        z.SetNetCode(board.GetNetcodeFromNetname('GND'))
        z.Outline().NewOutline()
        for at in [(22, 22), (23, 22), (23, 23), (22, 23)]:
            z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        board.Add(z)
    elif fault == 'flip':
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault == 'nonquarter':
        fp.Rotate(fp.FindPadByNumber('1').GetPosition(), pcbnew.EDA_ANGLE(15, pcbnew.DEGREES_T))
    elif fault == 'bad_barrel':
        next(t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA').SetWidth(250000)
    else:
        rule = target.with_suffix('.kicad_dru')
        rule.write_text(rule.read_text()+'\n(rule "unsafe" (constraint clearance (min 0mm)))\n')
    if fault != 'rule':
        try:
            field._save_field_snapshot(board, target)
        except field._ProposalUnknown:
            # These malformed native pads can be rejected even earlier by
            # the strict writer's saved-identity check. That is a refusal,
            # not permission to switch to net-normalizing SaveBoard.
            assert fault in ('return_net', 'flip')
            return
    receipt = receiving.receive(source, target, board_hint='synthetic')
    assert not receipt['ok'] and not receipt['complete'] and receipt['errors'], receipt


def test_automatic_source_menu_and_receiving_end_to_end(tmp_path):
    source, _, _ = fixture(tmp_path)
    before = source.read_bytes()
    result = pivot.run(source, tmp_path/'automatic', source_sha256=force._hash(source),
        board_hint='synthetic', max_trials=3)
    assert result['ok'] and result['source_opens'] == 1 and result['opens'] == 0, result
    assert result['source_family_and_code_unchanged'] and source.read_bytes() == before


def test_connected_return_is_not_a_movable_orphan(tmp_path):
    source, target, ref = fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source))
    pad = board.FindFootprintByReference(ref).FindPadByNumber('2')
    track(board, 'GND', (pad.GetPosition().x/1e6, pad.GetPosition().y/1e6), (10, 15))
    field._save_field_snapshot(board, source)
    assert pivot.source_menu(board, source, 'synthetic') == []
    assert not receiving.receive(source, target, board_hint='synthetic')['ok']
