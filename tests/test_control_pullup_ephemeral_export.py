"""One actual canonical export per plan, never a cross-call Source cache."""
import copy
import pytest
import cec_control_pullup_placement as op
from test_control_pullup_placement import fixture


def test_each_source_and_independent_request_plan_exports_fresh_once(tmp_path,monkeypatch):
    import pcbnew,cec_decoupler_cell as cells
    board,owner,cap,resistor,button,root,tree,poses=fixture(tmp_path,monkeypatch)
    original=op.leaf._export;calls=[]
    def export(*args):calls.append(args[0]);return original(*args)
    monkeypatch.setattr(op.leaf,'_export',export)
    selected=op.complete_plan(board,poses,board_hint=str(root));assert calls==[root]
    assert op.complete_plan(board,poses,board_hint=str(root))==selected and calls==[root,root]
    monkeypatch.setattr(cells,'_supply_current_widths',lambda b,n:dict(
        required_by_layer_nm={int(l):800000 for l in b.GetEnabledLayers().CuStack()},current_authority={'fixture_only':True}))
    op.requests(board,pcbnew.LoadBoard(board.GetFileName()),dict(poses=poses,selected_control_pullups=selected,board_hint=str(root)))
    assert calls==[root,root,root]


@pytest.mark.parametrize('fault',['wrong_root','missing','tree','metadata','source_after_export','native_after_export'])
def test_ephemeral_output_is_not_trusted_or_stale_authority(tmp_path,monkeypatch,fault):
    import pcbnew
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    original=op.leaf.plan_with_export
    def changed(*args,**kwargs):
        proof,snapshot=original(*args,**kwargs)
        if fault=='wrong_root':snapshot=('wrong-root',snapshot[1],snapshot[2])
        elif fault=='missing':snapshot=None
        elif fault=='tree':
            snapshot=copy.deepcopy(snapshot);snapshot[1].append(['unexpected_semantic_node','not_generated_date'])
        elif fault=='metadata':snapshot=copy.deepcopy(snapshot);snapshot[2]['netlist_semantic_sha256']='0'*64
        elif fault=='source_after_export':root.write_text(root.read_text()+'\n; actual post-export Source mutation\n')
        elif fault=='native_after_export':r.Move(pcbnew.VECTOR2I(1,0))
        return proof,snapshot
    monkeypatch.setattr(op.leaf,'plan_with_export',changed)
    with pytest.raises(ValueError):op.complete_plan(b,poses,board_hint=str(root))


def test_legacy_leaf_plan_does_not_publish_ephemeral_tree(tmp_path,monkeypatch):
    board,owner,cap,resistor,button,root,tree,poses=fixture(tmp_path,monkeypatch)
    legacy=op.leaf.plan(board,board_hint=str(root))
    assert legacy['complete']and 'fresh_export'not in legacy
    proof,snapshot=op.leaf.plan_with_export(board,board_hint=str(root))
    assert proof['complete']and snapshot[0]==str(root)
    assert op.shunt._canonical_source_proof(next(iter(legacy['proofs'].values())))==op.shunt._canonical_source_proof(next(iter(proof['proofs'].values())))
