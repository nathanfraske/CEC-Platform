"""Eligible native refusal never skips same-call immutable-input fences."""
import time
from pathlib import Path
import pcbnew,pytest
import cec_cell_macro_requests as macro
import cec_selected_cap_ground_boundary as fallback
from test_ground_boundary_single_call import source_case


@pytest.mark.parametrize('fault',['proposal','transport','native','family','canonical'])
def test_changed_input_and_eligible_refusal_never_reaches_fallback(tmp_path,monkeypatch,fault):
    b,p,t,edges=source_case(tmp_path,monkeypatch);original=macro._ground_boundary_at_edge;fallback_calls=[]
    def refused(*a,**kw):
        original(*a,**kw)
        if fault=='proposal':p['selected_programming_resistors']['R_program']['current_authority']=True
        elif fault=='transport':t['source_process_barrel_motion'][0]['source_owner_pad_uuids']=[]
        elif fault=='native':b.FindFootprintByReference('R_program').Move(pcbnew.VECTOR2I(1,0))
        elif fault=='family':Path(b.GetFileName()).with_suffix('.kicad_pro').write_text('{}')
        else:
            root=Path(p['board_hint']);root.write_text(root.read_text()+'\n; changed canonical Source\n')
        raise ValueError('changed_macro_ground_boundary_has_unowned_land:synthetic_refusal')
    def forbidden(*a,**kw):fallback_calls.append(True);raise AssertionError('must not fall through')
    monkeypatch.setattr(macro,'_ground_boundary_at_edge',refused)
    monkeypatch.setattr(fallback,'single_edge_ownerships',forbidden)
    with pytest.raises(ValueError,match='macro_ground_boundary_same_call_(inputs|canonical_bindings)_changed'):
        macro._extra_ownership(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    assert fallback_calls==[]


def test_unchanged_eligible_refusal_preserves_fallback_error_and_cause(tmp_path,monkeypatch):
    b,p,t,edges=source_case(tmp_path,monkeypatch);original=macro._ground_boundary_at_edge;calls=[]
    def refused(*a,**kw):
        original(*a,**kw)
        raise ValueError('changed_macro_ground_boundary_has_unowned_land:literal_scope')
    def failing(*a,**kw):calls.append(list(a[2]));raise ValueError('independent_fallback_refused')
    monkeypatch.setattr(macro,'_ground_boundary_at_edge',refused)
    monkeypatch.setattr(fallback,'single_edge_ownerships',failing)
    with pytest.raises(ValueError,match='changed_macro_ground_boundary_has_unowned_land:literal_scope')as e:
        macro._extra_ownership(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    assert len(calls)==1 and calls[0]==[macro.force._uid(edge)for edge in edges]
    assert str(e.value.__cause__)=='independent_fallback_refused'
