"""Native compact dogbone seats must use drill rules, not a fixed halo."""
import inspect
import json
import math
import subprocess

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr


def legacy_bridge():
    """Negative control restoring only the superseded offset-seat halo."""
    source = inspect.getsource(cec_fr._lastmile_bridge)
    marker = '            S = pcbnew.VECTOR2I(int(ex), int(ey))'
    assert source.count(marker) == 1
    source = source.replace(marker, '''            if any((vx-qx)**2+(vy-qy)**2 < _nm(0.85)**2
                   for qx, qy in ex_vias):
                return False
''' + marker)
    namespace = {}
    exec(compile(source, '<legacy-fixed-hole-halo>', 'exec'), cec_fr.__dict__, namespace)
    return namespace['_lastmile_bridge']


def fixture(tmp_path, *, quarter=0, layer='F.Cu', foreign=False,
            spacing=.65, existing_drill=.3, hole_gap=.2):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    def point(x, y):
        for _ in range(quarter):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(x + 20, y + 20)
    front = board.GetLayerID(layer)
    bridge = pcbnew.B_Cu if front == pcbnew.F_Cu else pcbnew.F_Cu
    for name in ('renamed_signal', 'unrelated_signal'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    net = board.FindNet('renamed_signal')
    corners = ((-3,-3),(12,-3),(12,8),(-3,8),(-3,-3))
    for a, b in zip(corners, corners[1:]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(point(*a)); edge.SetEnd(point(*b)); board.Add(edge)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('PORT_RENAMED'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('1')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2)); pad.SetPosition(point(0,0))
    layers = pcbnew.LSET(); layers.AddLayer(front); pad.SetLayerSet(layers)
    pad.SetNet(net); fp.Add(pad)
    for x, y, drill, name in ((5,0,.3,'renamed_signal'),
            (.5,spacing,existing_drill,'unrelated_signal' if foreign else 'renamed_signal')):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point(x,y)); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetDrill(pcbnew.FromMM(drill)); via.SetWidth(pcbnew.FromMM(max(.6,drill+.3)))
        via.SetNet(board.FindNet(name)); board.Add(via)
    path = tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(path),board,True)
    # Persist native rules, not an in-memory-only setting lost on load/DRC.
    path.with_suffix('.kicad_pro').write_text(json.dumps({'board': {'design_settings': {
        'rules': {'min_hole_to_hole':hole_gap,'min_hole_clearance':.2,'min_via_diameter':.6,
                  'min_through_hole_diameter':.3,'min_via_annular_width':.15,
                  'min_clearance':.2}}}}))
    return path, point(0,0), point(.5,0), point(5,0), front, bridge


def solve(data, solver=cec_fr._lastmile_bridge):
    path, a, seat, b, front, bridge = data
    board = pcbnew.LoadBoard(str(path))
    ops = solver(board,(a.x,a.y),{front},(b.x,b.y),set(board.GetEnabledLayers().CuStack()),
        pcbnew.FromMM(.2),board.GetNetcodeFromNetname('renamed_signal'),
        [bridge],pcbnew.FromMM(.2),allow_maze=False,allow_lattice=False,
        seat_offsets_mm=(.5,),seat_angles_deg=(
            round(math.degrees(math.atan2(seat.y-a.y,seat.x-a.x))),))
    return board, ops


@pytest.mark.parametrize('quarter,layer',[(0,'F.Cu'),(1,'B.Cu'),(2,'F.Cu'),(3,'B.Cu')])
def test_loaded_compact_seat_passes_actual_rules_and_old_halo_refuses(tmp_path,quarter,layer):
    data = fixture(tmp_path,quarter=quarter,layer=layer)
    original = data[0].read_bytes()
    assert solve(data,legacy_bridge())[1] is None
    board, ops = solve(data)
    assert ops is not None
    vias = [op for op in ops if op[0]=='via']
    assert len(vias)==1 and vias[0][1]==data[2]
    assert board.GetDesignSettings().m_HoleToHoleMin==pcbnew.FromMM(.2)
    assert data[0].read_bytes()==original


@pytest.mark.parametrize('kwargs,contact',[
    ({'spacing':.499},'hole_clearance'),
    ({'hole_gap':.36},'hole_clearance'),
    ({'existing_drill':.7},'hole_clearance'),
    ({'spacing':0},'co_located_hole'),
    ({'foreign':True},None),
])
def test_exact_hole_and_foreign_annulus_failures_still_refuse(tmp_path,kwargs,contact):
    data=fixture(tmp_path,**kwargs)
    board, ops=solve(data)
    assert ops is None
    report={}
    assert not cec_fr._via_spot_clear(board,data[2],pcbnew.FromMM(.6),pcbnew.FromMM(.2),
        {board.GetNetcodeFromNetname('renamed_signal')},drill_nm=pcbnew.FromMM(.3),
        net_code=board.GetNetcodeFromNetname('renamed_signal'),report=report)
    if contact:
        assert any(row.get('contact')==contact for row in report['blockers']),report


def test_completed_native_fixture_has_no_drill_or_copper_drc_errors(tmp_path):
    data=fixture(tmp_path)
    board, ops=solve(data)
    assert ops
    for op in ops:
        if op[0]=='via':
            item=pcbnew.PCB_VIA(board); item.SetPosition(op[1])
            item.SetViaType(pcbnew.VIATYPE_THROUGH); item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            item.SetDrill(pcbnew.FromMM(op[2])); item.SetWidth(pcbnew.FromMM(op[3]))
        else:
            item=pcbnew.PCB_TRACK(board); item.SetStart(op[1]); item.SetEnd(op[2])
            item.SetWidth(op[3]); item.SetLayer(op[4])
        item.SetNet(board.FindNet('renamed_signal')); board.Add(item)
    # Connect the neighboring same-net test barrel too. The fixture then has
    # one net/component, not a hidden dangling-net exemption in its DRC check.
    item=pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I_MM(20.5,20.65)); item.SetEnd(pcbnew.VECTOR2I_MM(20.5,20))
    item.SetWidth(pcbnew.FromMM(.2)); item.SetLayer(pcbnew.B_Cu)
    item.SetNet(board.FindNet('renamed_signal')); board.Add(item)
    path=tmp_path/'closed.kicad_pcb'; pcbnew.SaveBoard(str(path),board,True)
    path.with_suffix('.kicad_pro').write_bytes(data[0].with_suffix('.kicad_pro').read_bytes())
    report=tmp_path/'drc.json'
    result=subprocess.run(['kicad-cli','pcb','drc','--format','json','--output',str(report),str(path)],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    rows=json.loads(report.read_text())
    assert not rows['unconnected_items'],rows['unconnected_items']
    assert not [row for row in rows['violations'] if row.get('severity')=='error'],rows['violations']
