"""Fresh enable pull-up scope survives complete-cell production/receiving."""
from pathlib import Path
import pcbnew,pytest
import cec_cell_escape_replan as escape
import cec_complete_cell_receiving as saved
import cec_control_pullup_placement as pullup
import cec_decoupler_cell as cells
from test_control_pullup_placement import fixture


def test_pullup_does_not_gain_generic_device_or_bypass_authority(tmp_path,monkeypatch):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    q=escape.prepare(b,poses,board_hint=str(root))
    assert set(q['selected_control_pullups'])==set(poses)
    assert not q['selected_bypasses']and not q['device_contracts']
    assert q['selected_control_pullups'][r.GetReference()]['source_trace_retirement_authority']is False
    assert 'selected_control_shunts'not in q


def test_saved_actual_motion_requires_fresh_canonical_pullup_both_requests(tmp_path,monkeypatch):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(saved,'_assignments',lambda *a:{})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},current_authority={'amps':1.}))
    child=pcbnew.LoadBoard(b.GetFileName());fp=child.FindFootprintByReference(r.GetReference());target=poses[r.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])));fp.SetOrientationDegrees(target[2])
    actual,moved=saved._poses(b,child,str(root))
    assert actual==poses and moved==set(poses)
    fp.SetField('MPN','changed')
    with pytest.raises(ValueError):saved._poses(b,child,str(root))


def test_control_pullup_mandatory_requests_and_original_current_receiver_remain():
    text=Path(escape.__file__).read_text();native=Path(saved.__file__).read_text()
    assert "result['selected_control_pullups']=control_pullups"in text
    assert 'requests.update(control_pullup.requests(source,board,proposal))'in text
    assert "if reqs:raise ValueError('control_pullup_cannot_alias_power_bypass')"in text
    assert 'cells._supply_current_widths(parent,net)'in native
    assert 'cell_current_layer_not_authorized'in native
    assert 'new_cell_barrels_or_untyped_conductors_need_separate_receiving'in native
