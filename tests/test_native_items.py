"""Permanent-discard semantics and native lifetime regressions."""
import ast
import gc
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cec_native_items import discard_items


def test_aliases_are_deduplicated_and_other_group_members_survive():
    import pcbnew
    import cec_fr
    board = pcbnew.CreateEmptyBoard()
    group = pcbnew.PCB_GROUP(board)
    group.SetName("arbitrary-owner")
    board.Add(group)
    items = [pcbnew.PCB_TRACK(board) for _ in range(2)]
    for item in items:
        board.Add(item)
        group.AddItem(item)
    doomed_id = items[0].m_Uuid.AsString()
    keep_id = items[1].m_Uuid.AsString()
    alias = next(t for t in board.GetTracks() if t.m_Uuid.AsString() == doomed_id)
    assert discard_items(board, [items[0], alias, items[0]]) == 1
    assert items[0].this is None
    assert [t.m_Uuid.AsString() for t in board.GetTracks()] == [keep_id]
    assert group.ContainsItem(items[1])
    assert len(list(group.GetItems())) == 1


def test_loaded_borrowed_items_delete_without_consuming_the_registry(tmp_path):
    """This subprocess also checks native cleanup at normal interpreter exit."""
    import subprocess
    script = r'''
import gc, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import pcbnew
import cec_fr
from cec_native_items import discard_items
path = Path(sys.argv[2]) / 'synthetic.kicad_pcb'
board = pcbnew.CreateEmptyBoard()
group = pcbnew.PCB_GROUP(board)
group.SetName('generic-owner')
board.Add(group)
for cls in (pcbnew.PCB_TRACK, pcbnew.PCB_VIA, pcbnew.ZONE):
    item = cls(board)
    if cls is pcbnew.PCB_TRACK:
        item.SetStart(pcbnew.VECTOR2I_MM(1, 1))
        item.SetEnd(pcbnew.VECTOR2I_MM(2, 1))
        item.SetWidth(pcbnew.FromMM(.3))
    elif cls is pcbnew.PCB_VIA:
        item.SetPosition(pcbnew.VECTOR2I_MM(3, 3))
        item.SetWidth(pcbnew.FromMM(.6))
        item.SetDrill(pcbnew.FromMM(.3))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    else:
        item.SetLayer(pcbnew.F_Cu)
        outline = item.Outline()
        outline.NewOutline()
        for x, y in ((0, 0), (5, 0), (5, 5), (0, 5)):
            outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    board.Add(item)
    group.AddItem(item)
pcbnew.SaveBoard(str(path), board)
capsule = sys.modules['swig_runtime_data4'].type_pointer_capsule
def discard_loaded():
    loaded = pcbnew.LoadBoard(str(path))
    items = list(loaded.GetTracks()) + list(loaded.Zones())
    assert discard_items(loaded, items) == 3
    assert not list(loaded.GetTracks()) and not list(loaded.Zones())
for _ in range(8):
    before = sys.getrefcount(capsule)
    discard_loaded()
    gc.collect()
    assert sys.getrefcount(capsule) == before, 'unbalanced borrowed registry reference'
assert isinstance(pcbnew.LoadBoard(str(path)), pcbnew.BOARD)
'''
    result = subprocess.run([sys.executable, "-c", script,
        str(Path(__file__).resolve().parents[1] / "scripts"), str(tmp_path)],
        text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr[-4000:]


@pytest.mark.parametrize("module", ["cec_dimension_repair.py", "cec_decoupler_cell.py", "cec_fr.py",
                                   "cec_constraints.py", "cec_current_topology.py",
                                   "cec_sync_pcb_from_schematic.py", "cec_precision_route.py",
                                   "cec_native_copper_snapshot.py", "cec_certificate_repair.py"])
def test_audited_cleanup_modules_do_not_reintroduce_detach_for_discard(module):
    path = Path(__file__).resolve().parents[1] / "scripts" / module
    tree = ast.parse(path.read_text())
    calls = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "Remove"
             and ((isinstance(node.func.value, ast.Name) and node.func.value.id in {"board", "b", "probe"})
                  or (isinstance(node.func.value, ast.Attribute) and node.func.value.attr=='board'))]
    assert not calls, "Use the native permanent-discard helper at these audited sites: %s" % calls
