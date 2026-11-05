import ast
import copy
import hashlib
from pathlib import Path
import pcbnew
import pytest
import cec_complete_cell_receiving as receiving
import cec_control_shunt_placement as shunt
from test_control_shunt_placement import fixture


def pair(tmp_path,monkeypatch,turn=0,back=False):
    parent,owner,ground,root,poses=fixture(tmp_path,monkeypatch,turn,back)
    monkeypatch.setattr(receiving,'_assignments',lambda *a:{})
    child=pcbnew.LoadBoard(parent.GetFileName());ref=ground.GetParentFootprint().GetReference()
    target=child.FindFootprintByReference(ref);target.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in poses[ref][:2])));target.SetOrientationDegrees(poses[ref][2])
    return parent,child,owner,ground,root,poses


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_saved_actual_source_shunt_motion_not_fake_bypass(tmp_path,monkeypatch,turn,back):
    parent,child,owner,g,root,actual=pair(tmp_path,monkeypatch,turn,back)
    poses,moved=receiving._poses(parent,child,str(root))
    assert moved==set(actual)and owner.GetReference()not in poses
    assert {r:[*p[:2],p[2]%360]for r,p in poses.items()}==actual


@pytest.mark.parametrize('fault',['unknown_passive','owner_move','ground_net','signal_net','face','unknown_source','orphan_source','population'])
def test_unknown_or_changed_source_child_cannot_acquire_rc_motion(tmp_path,monkeypatch,fault):
    parent,child,owner,g,root,actual=pair(tmp_path,monkeypatch);ref=g.GetParentFootprint().GetReference()
    if fault=='unknown_passive':
        target=child.FindFootprintByReference(ref);target.SetPosition(parent.FindFootprintByReference(ref).GetPosition());target.SetOrientationDegrees(0)
        # Move unrelated native physical object, not its source-typed cap.
        child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.5,0))
    elif fault=='owner_move':child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='ground_net':child.FindFootprintByReference(ref).FindPadByNumber('2').SetNetCode(0)
    elif fault=='signal_net':child.FindFootprintByReference(ref).FindPadByNumber('1').SetNetCode(0)
    elif fault=='face':child.FindFootprintByReference(ref).Flip(pcbnew.VECTOR2I(0,0),False)
    elif fault=='unknown_source':parent.FindFootprintByReference(ref).SetValue('unknown')
    elif fault=='orphan_source':parent.FindFootprintByReference(ref).FindPadByNumber('1').SetNetCode(0)
    else:
        extra=pcbnew.FOOTPRINT(child);extra.SetReference('unrelated');child.Add(extra)
    with pytest.raises(ValueError):receiving._poses(parent,child,str(root))


def test_source_semantic_export_clock_changes_do_not_change_inferred_poses(tmp_path,monkeypatch):
    parent,child,owner,g,root,actual=pair(tmp_path,monkeypatch);export=shunt.leaf._export;count=[0]
    def dated(*a,**kw):
        tree,meta=export(*a,**kw);count[0]+=1;tree=copy.deepcopy(tree)
        tree.append(['design',['source',str(root)],['date','2026-10-22T21:00:'+format(count[0],'02d')+'-0500']])
        meta.update(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),**shunt.semantic.metadata(tree));return tree,meta
    monkeypatch.setattr(shunt.leaf,'_export',dated)
    with shunt.capture_exports()as raw:
        first=receiving._poses(parent,child,str(root));second=receiving._poses(parent,child,str(root))
    assert first==second and len(raw)>=4
    assert raw[0]['raw_source_proof']['exporter']['netlist_sha256']!=raw[-1]['raw_source_proof']['exporter']['netlist_sha256']


def test_saved_receiver_still_recompiles_and_checks_all_routing_gates():
    text=Path(receiving.__file__).read_text()
    function=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)and n.name=='receive')
    def calls(name):
        return [n for n in ast.walk(function)if isinstance(n,ast.Call)and ast.unparse(n.func)==name]
    poses,=calls('_poses')
    assert [ast.unparse(a)for a in poses.args]==[
        'parent','child','board_hint','reference_group_uuids']
    prepare,=calls('escape.prepare');obligations,=calls('escape.obligations')
    receive,=calls('additive.receive')
    assert [ast.unparse(a)for a in prepare.args]==['parent','poses']
    assert [ast.unparse(a)for a in obligations.args]==['parent','projected','plan']
    assert [ast.unparse(a)for a in receive.args][:2]==['expected','paths[1]']
    assert poses.lineno<prepare.lineno<obligations.lineno<receive.lineno
