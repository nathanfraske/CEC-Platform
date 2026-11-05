"""Exercise real certificate-repair destruction on loaded, borrowed copper."""
from pathlib import Path
import ast
import subprocess
import sys

import pytest


@pytest.mark.parametrize('operation', ['reroute', 'negotiate', 'retreat', 'via', 'prune'])
def test_loaded_certificate_workers_preserve_native_registry(tmp_path, operation):
    script = r'''
import gc, hashlib, shutil, sys
from pathlib import Path
root, out, operation = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(root / 'scripts'))
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_certificate_repair as repair
source, target = out/'source.kicad_pcb', out/'candidate.kicad_pcb'
board = pcbnew.CreateEmptyBoard()
net = pcbnew.NETINFO_ITEM(board, '/ANONYMOUS_SIGNAL')
board.Add(net)
for a, b in (((0,0),(15,0)), ((15,0),(15,15)), ((15,15),(0,15)), ((0,15),(0,0))):
    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
    edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
    edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
track = pcbnew.PCB_TRACK(board)
track.SetStart(pcbnew.VECTOR2I_MM(4,5)); track.SetEnd(pcbnew.VECTOR2I_MM(5,5))
track.SetWidth(pcbnew.FromMM(.25)); track.SetLayer(pcbnew.F_Cu); track.SetNet(net)
board.Add(track)
uid = track.m_Uuid.AsString()
via = pcbnew.PCB_VIA(board)
via.SetPosition(pcbnew.VECTOR2I_MM(5,5)); via.SetWidth(pcbnew.FromMM(.6))
via.SetDrill(pcbnew.FromMM(.3)); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
via.SetNet(net); board.Add(via)
vid = via.m_Uuid.AsString()
if operation in ('retreat', 'prune', 'via'):
    group = pcbnew.PCB_GROUP(board); group.SetName(repair.cec_fr.ENDPOINT_NECKDOWN_GROUP)
    board.Add(group); group.AddItem(via if operation == 'prune' else track)
pcbnew.SaveBoard(str(source),board,True)
original = hashlib.sha256(source.read_bytes()).hexdigest()

def probe():
    shutil.copy2(source,target)
    if operation == 'reroute':
        loaded = pcbnew.LoadBoard(str(target))
        selected = repair.RepairTarget(uid,'/ANONYMOUS_SIGNAL','F.Cu',1,(),(),(),False,())
        ops, report = repair._candidate_ops(loaded,selected,board_path=str(target),
            mode='same_layer',maze_margin_mm=1)
        assert ops and report['removed_tracks'] == [uid], report
        pcbnew.SaveBoard(str(target),loaded,True)
    elif operation == 'negotiate':
        loaded = pcbnew.LoadBoard(str(target))
        window = repair.NegotiationWindow('/OTHER',1,.25,.2,(uid,),('/ANONYMOUS_SIGNAL',),
            1,0,0,0,(),())
        changed, report, snapshots = repair._remove_negotiation_blockers(loaded,window)
        assert changed and report['removed_tracks'] == 1, report
        assert tuple(snapshots[0]['removed_uuids']) == (uid,), snapshots
        pcbnew.SaveBoard(str(target),loaded,True)
    elif operation == 'retreat':
        changed, report = repair._apply_target_endpoint_retreat_worker(str(target),
            '/ANONYMOUS_SIGNAL',dict(removed_uuids=[uid],endpoint={}))
        assert changed and report['removed_tracks'] == 1, report
    elif operation == 'via':
        selected = repair.ViaRepairTarget(vid,'/ANONYMOUS_SIGNAL',5000000,5000000,
            600000,300000,(),(),0,1,())
        changed, report = repair._relocate_via_worker(str(target),repair.asdict(selected),0,300000)
        assert changed and report['incident_stubs'] == 1, report
    else:
        drc = dict(violations=[dict(type='via_dangling',items=[dict(uuid=vid)])])
        changed, report = repair._prune_relocated_dangling_vias_worker(str(target),[vid],drc)
        assert changed and report['removed'] == [vid], report
    saved = pcbnew.LoadBoard(str(target))
    live = {item.m_Uuid.AsString() for item in saved.GetTracks()}
    assert (vid if operation == 'prune' else uid) not in live
    assert all(member.m_Uuid.AsString() in live for group in saved.Groups() for member in group.GetItems())
    return len(live - {uid, vid})

# Warm lazy imports once, then verify both repeated worker cleanup and normal
# interpreter exit. A pin prevents catastrophic exit, but not a refcount leak.
probe()
capsule = sys.modules['swig_runtime_data4'].type_pointer_capsule
# This KiCad build retains a capsule reference per Python-created Add().
# Calibrate that unrelated behavior using a plain loaded-board add/save; a
# removed borrowed object must not consume it (or any other registry ref).
def plain_add():
    loaded = pcbnew.LoadBoard(str(source))
    item = pcbnew.PCB_TRACK(loaded)
    item.SetStart(pcbnew.VECTOR2I_MM(8,8)); item.SetEnd(pcbnew.VECTOR2I_MM(9,8))
    item.SetWidth(250000); item.SetLayer(pcbnew.F_Cu); loaded.Add(item)
    pcbnew.SaveBoard(str(target),loaded,True)
gc.collect(); count = sys.getrefcount(capsule)
plain_add(); gc.collect(); per_add = sys.getrefcount(capsule) - count
assert per_add >= 0
for _ in range(8):
    gc.collect(); before = sys.getrefcount(capsule)
    added = probe(); gc.collect()
    assert sys.getrefcount(capsule) == before + added * per_add, 'borrowed registry imbalance'
assert hashlib.sha256(source.read_bytes()).hexdigest() == original
'''
    result = subprocess.run([sys.executable, '-c', script,
        str(Path(__file__).resolve().parents[1]), str(tmp_path), operation],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr[-5000:]


def test_lifetime_harness_detects_the_legacy_detach_path(tmp_path):
    """Negative control: no source-engine patch, isolated native process only."""
    tree = ast.parse(Path(__file__).read_text())
    fixture = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == 'test_loaded_certificate_workers_preserve_native_registry')
    script = next(ast.literal_eval(node.value) for node in fixture.body
                  if isinstance(node, ast.Assign) and any(
                      isinstance(target, ast.Name) and target.id == 'script' for target in node.targets))
    script = script.replace('import cec_certificate_repair as repair',
        'import cec_certificate_repair as repair\n'
        'repair.discard_items = lambda board, items: [board.Remove(item) for item in items]')
    result = subprocess.run([sys.executable, '-c', script,
        str(Path(__file__).resolve().parents[1]), str(tmp_path), 'negotiate'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'borrowed registry imbalance' in result.stderr
