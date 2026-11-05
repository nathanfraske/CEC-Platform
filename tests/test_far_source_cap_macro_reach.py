"""Real canonical Source cap survives all nested frame/replay reach limits.

Only the pre-existing aggregate current contract is synthetic, as in the
shared fixture. This is unfinished placement construction, not admission.
"""
import copy
import pcbnew
import pytest
import cec_additional_aggregate_macro as aggregate
import cec_cell_escape_replan as escape
from test_additional_aggregate_macro import fixture


def test_source_only_far_cap_reach_cannot_move_ordinary_owner_or_replace_minimum(tmp_path,monkeypatch):
    source,root,_,_,_=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source))
    for fp in board.GetFootprints():
        if fp.GetReference()!='RENAMED_C':fp.Move(pcbnew.VECTOR2I_MM(80,0))
    # Expand this SYNTHETIC input board's blank placement field, not a real
    # project board. The selected owner and original minimum are still local.
    for drawing in board.GetDrawings():
        if drawing.GetLayer()!=pcbnew.Edge_Cuts:continue
        for get,setter in ((drawing.GetStart,drawing.SetStart),(drawing.GetEnd,drawing.SetEnd)):
            p=get()
            if p.x>=29000000:setter(pcbnew.VECTOR2I(149000000,p.y))
    import cec_force_current as force
    import cec_field_coupling as field
    field._save_field_snapshot(board,source)
    parent=pcbnew.LoadBoard(str(source));owner=parent.FindFootprintByReference('AMP73')
    poses={'RENAMED_C':[94.,14.,0.], 'AMP73':[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}
    before=escape.row._source_binding(parent)
    with pytest.raises(ValueError):escape.prepare(parent,poses,board_hint=str(root),max_shift_mm=6.)
    q=escape.prepare(parent,poses,board_hint=str(root),max_shift_mm=6.,aggregate_capacitor_max_shift_mm=100.)
    assert q['row_plan']['maximum_translation_mm']==100.
    assert q['additional_aggregate_capacitors']['RENAMED_C']['unchanged_selected_bypass_assignments']['AMP73:6:100n']=='EXISTING_FEED'
    child=pcbnew.LoadBoard(str(source));escape.apply_private(child,q)
    assert list(child.FindFootprintByReference('RENAMED_C').GetPosition())==[94000000,14000000]
    demands=escape.obligations(parent,child,q)
    assert demands['ground:'+force._uid(parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('2'))]['reach_mm']==.8
    # Go beyond row.prepare/apply: the actual complete macro's native
    # endpoint transport and its nested Ground-seat resolver must receive
    # the same explicitly Source-typed construction reach, not a hard64.
    import cec_cell_macro_requests as compiler
    frame,transport=compiler._frame(parent,source,q,timeout_s=9.)
    assert list(frame.FindFootprintByReference('RENAMED_C').GetPosition())==[94000000,14000000]
    assert transport['explicit_maximum_translation_work_mm']==100.
    assert transport['all_source_dimensions_and_identities_retained']
    assert not transport['routing_admitted']and not transport['current_qualified']
    import cec_source_supply_endpoint_cut as selected
    assert selected.isolated_components(parent,frame,board_hint=str(root),
        source_floor=lambda t:(500000,200000),timeout_s=3.)==[]
    assert before==escape.row._source_binding(parent)
    bad=copy.deepcopy(poses);bad['AMP73'][0]+=.1
    with pytest.raises(ValueError):escape.prepare(parent,bad,board_hint=str(root),max_shift_mm=6.,aggregate_capacitor_max_shift_mm=100.)
