"""No duplicate native refill; no receipt beyond its exact private context."""
import pcbnew
import pytest

import cec_field_coupling as field
import cec_fr as fr
import cec_proposal_receipt_memo as memo
from test_lastmile import _board


def fixture():
    board=_board([(8,8,'/OPAQUE'),(12,8,'/OPAQUE')],edge=(3,3,18,18))
    op=('trk',pcbnew.VECTOR2I_MM(8,8),pcbnew.VECTOR2I_MM(12,8),200000,pcbnew.F_Cu)
    return board,op,memo.proposal_key('/OPAQUE',[op])


def test_exact_completed_receipt_is_private_bounded_and_read_only():
    board,operation,key=fixture()
    before=field._field_snapshot_inventory(board)
    store=memo.NativePlanReceiptMemo(board)
    assert store.lookup(key) is None
    assert store.remember(key) is True and store.lookup(key) is True
    assert before==field._field_snapshot_inventory(board)
    changed=list(operation);changed[3]=250000
    assert store.lookup(memo.proposal_key('/OPAQUE',[tuple(changed)])) is None
    report=store.report()
    assert report['hits']==1 and not report['persisted'] and not report['release_authority']
    assert report['saved_board_receiving_still_required']


@pytest.mark.parametrize('mutation',['track','pad_pose','pad_angle','pad_shape','pad_drill',
    'local_clearance','board_rules','profile','classification'])
def test_every_native_material_or_contract_change_invalidates_positive_receipt(mutation):
    board,operation,key=fixture()
    classes={'name':'Default','track_width':.2,'clearance':.2}
    store=memo.NativePlanReceiptMemo(board,netclass_resolver=lambda _name:dict(classes))
    assert store.remember(key)
    pad=next(p for fp in board.GetFootprints() for p in fp.Pads())
    if mutation=='track':
        t=pcbnew.PCB_TRACK(board);t.SetNet(pad.GetNet());t.SetStart(pcbnew.VECTOR2I_MM(8,8))
        t.SetEnd(pcbnew.VECTOR2I_MM(9,8));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);board.Add(t)
    elif mutation=='pad_pose':pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(.1,0))
    elif mutation=='pad_angle':pad.SetOrientationDegrees(90)
    elif mutation=='pad_shape':pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif mutation=='pad_drill':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif mutation=='local_clearance':pad.SetLocalClearance(300000)
    elif mutation=='board_rules':board.GetDesignSettings().m_MinClearance=300000
    elif mutation=='profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    else:classes['name']='Analog'
    assert store.lookup(key) is False
    assert store.lookup(key) is False and store.remember(key) is False
    assert store.report()['changed_context_refusals']>=1


def test_original_rule_companions_are_not_hidden_by_live_board_identity(tmp_path):
    board,operation,key=fixture()
    source=tmp_path/'board.kicad_pcb';field._save_field_snapshot(board,source)
    board.SetFileName(str(source))
    saved=source.read_bytes()
    store=memo.NativePlanReceiptMemo(board)
    assert store.remember(key)
    (tmp_path/'board.kicad_dru').write_text('(version 1)\n')
    assert store.lookup(key) is False and source.read_bytes()==saved


def test_production_does_not_repeat_a_complete_unchanged_proposal_until_timeout(monkeypatch):
    board,operation,key=fixture();assessed=[]
    native=field.assess_proposed_route
    def once(*args,**kwargs):
        assert not assessed,'duplicate complete native proposal review'
        result=native(*args,**kwargs);assessed.append(result)
        return result
    monkeypatch.setattr(field,'assess_proposed_route',once)
    result=fr.synthesize_lastmile(board,include_nets=['/OPAQUE'],max_mm=5,
        min_w=.2,clearance=.2,cap=1,maze_max_mm=0,field_guard=True,wall_timeout_s=2.)
    assert result['closed']==1 and assessed[0]['complete'] and assessed[0]['ok']
    assert fr.net_connectivity_component_count(board,board.GetNetcodeFromNetname('/OPAQUE'))==1
    assert result['field_guard']['assessed']==1
    assert sum(r['hits'] for r in result['exact_private_proposal_receipt_reuse'])>=1


def test_unknown_proposal_review_is_never_memoized_as_positive(monkeypatch):
    board,operation,key=fixture()
    monkeypatch.setattr(field,'assess_proposed_route',lambda *a,**k:
        dict(ok=None,complete=False,reason='bounded_native_refill_unknown'))
    result=fr.synthesize_lastmile(board,include_nets=['/OPAQUE'],max_mm=5,
        min_w=.2,clearance=.2,cap=1,maze_max_mm=0,field_guard=True,wall_timeout_s=.2)
    assert result['closed']==0 and fr.net_connectivity_component_count(board,
        board.GetNetcodeFromNetname('/OPAQUE'))==2
    assert not any(r['stored'] or r['hits'] for r in result['exact_private_proposal_receipt_reuse'])


@pytest.mark.parametrize('size',[0,True,65])
def test_receipt_storage_is_explicitly_bounded(size):
    board,operation,key=fixture()
    with pytest.raises(ValueError,match='bounded_private_receipt_memo'):
        memo.NativePlanReceiptMemo(board,max_entries=size)
