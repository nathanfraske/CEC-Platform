"""Native compact launch pockets omitted by the old half-mm seat floor."""
import json
import math
import subprocess

import pcbnew
import pytest
import cec_fr as fr
from cec_native_items import discard_items
from test_bridge_exact_hole_spacing import fixture


def narrow_pocket(tmp_path, *, quarter=0, layer='F.Cu', wall_x=1.03):
    data = fixture(tmp_path, quarter=quarter, layer=layer)
    path, start, _, end, front, bridge = data
    board = pcbnew.LoadBoard(str(path))
    # Keep only the far same-net bridge barrel; the auxiliary drill-spacing
    # control in the shared fixture is unrelated to this escape pocket.
    discard_items(board, [item for item in board.GetTracks() if item.GetPosition() != end])
    def point(x, y):
        for _ in range(quarter):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(x + 20, y + 20)
    net = board.FindNet('unrelated_signal')
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('FOREIGN_PORT'); board.Add(fp)
    for index, y in enumerate((-2., 2.)):
        pad = pcbnew.PAD(fp); pad.SetNumber(str(index + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4)); pad.SetPosition(point(wall_x, y))
        layers = pcbnew.LSET(); layers.AddLayer(front); pad.SetLayerSet(layers)
        pad.SetNet(net); fp.Add(pad)
    wall = pcbnew.PCB_TRACK(board); wall.SetNet(net); wall.SetLayer(front)
    wall.SetStart(point(wall_x, -2.)); wall.SetEnd(point(wall_x, 2.))
    wall.SetWidth(pcbnew.FromMM(.2)); board.Add(wall)
    pcbnew.SaveBoard(str(path), board, True)
    return data


def plan(data, quarter=0):
    path, start, _, end, front, bridge = data
    board = pcbnew.LoadBoard(str(path))
    ops = fr._lastmile_bridge(board, tuple(start), {front}, tuple(end),
        set(board.GetEnabledLayers().CuStack()), pcbnew.FromMM(.2),
        board.GetNetcodeFromNetname('renamed_signal'), [bridge], pcbnew.FromMM(.2),
        allow_maze=False, allow_lattice=False, seat_angles_deg=(quarter * 90,),
        leg_ok=lambda a, b, half: fr._edge_leg_clear(board, a, b, half))
    return board, ops


@pytest.mark.parametrize('quarter,layer', [(0, 'F.Cu'), (1, 'B.Cu'), (2, 'F.Cu'), (3, 'B.Cu')])
def test_compact_native_pocket_has_real_bridge_legacy_domain_misses(tmp_path, monkeypatch, quarter, layer):
    data = narrow_pocket(tmp_path, quarter=quarter, layer=layer)
    original = data[0].read_bytes()
    offsets = fr._dogbone_offset_ladder_mm()
    with monkeypatch.context() as old:
        old.setattr(fr, '_dogbone_offset_ladder_mm', lambda: tuple(x for x in offsets if x >= .5))
        assert plan(data, quarter)[1] is None
    board, ops = plan(data, quarter)
    assert ops is not None
    vias = [op for op in ops if op[0] == 'via']
    assert len(vias) == 1
    assert 0. < math.hypot(*(vias[0][1] - data[1])) / 1e6 < .5
    assert vias[0][2:] == (.3, .6)  # ordinary process dimensions, unchanged
    assert data[0].read_bytes() == original
    assert len(list(board.GetTracks())) == 2


@pytest.mark.parametrize('quarter', range(4))
def test_compact_domain_does_not_waive_foreign_clearance(tmp_path, quarter):
    data = narrow_pocket(tmp_path, quarter=quarter, wall_x=.85)
    board, ops = plan(data, quarter)
    assert ops is None
    assert len(list(board.GetTracks())) == 2


def test_legacy_successful_seat_keeps_priority(tmp_path):
    data = fixture(tmp_path)
    board, ops = plan(data)
    via = next(op for op in ops if op[0] == 'via')
    assert via[1] == data[2]
    assert fr._dogbone_offset_ladder_mm()[0] == .5


def test_compact_plan_passes_native_drc_without_rule_changes(tmp_path):
    data = narrow_pocket(tmp_path)
    board, ops = plan(data)
    assert ops
    for op in ops:
        if op[0] == 'via':
            item = pcbnew.PCB_VIA(board); item.SetPosition(op[1])
            item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            item.SetDrill(pcbnew.FromMM(op[2])); item.SetWidth(pcbnew.FromMM(op[3]))
        else:
            item = pcbnew.PCB_TRACK(board); item.SetStart(op[1]); item.SetEnd(op[2])
            item.SetWidth(op[3]); item.SetLayer(op[4])
        item.SetNet(board.FindNet('renamed_signal')); board.Add(item)
    path = tmp_path / 'closed.kicad_pcb'; pcbnew.SaveBoard(str(path), board, True)
    path.with_suffix('.kicad_pro').write_bytes(data[0].with_suffix('.kicad_pro').read_bytes())
    output = tmp_path / 'drc.json'
    result = subprocess.run(['kicad-cli', 'pcb', 'drc', '--format', 'json',
        '--output', str(output), str(path)], capture_output=True, text=True, timeout=10.)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert not report['unconnected_items'], report['unconnected_items']
    assert not [row for row in report['violations'] if row.get('severity') == 'error'], report['violations']
