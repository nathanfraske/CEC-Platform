"""Only fresh binding hashes survive suspension, including no-fallback work.

The synthetic netlist exporter is retained. Actual reviewed PDF/executable
bytes are copied to this test's temporary directory solely to mutate file
identity safely; no workspace datasheet or installed binary is modified.
"""
import shutil,time
from pathlib import Path
import pytest
import cec_cell_macro_requests as macro
import cec_programming_resistor_placement as programming
import cec_selected_cap_ground_boundary as multiport
from test_ground_boundary_single_call import source_case


@pytest.mark.parametrize('kind',['evidence','exporter'])
@pytest.mark.parametrize('mutation',['append','missing','same_bytes'])
def test_fresh_nonfamily_input_bindings_survive_without_pending_cap_fallback(tmp_path,monkeypatch,kind,mutation):
    b,p,t,_=source_case(tmp_path,monkeypatch)
    if kind=='evidence':
        original=Path(programming.__file__).resolve().parents[1]/programming.PDF
        target=tmp_path/'copied-manufacturer-evidence.pdf';shutil.copyfile(original,target)
        assert programming.force._hash(target)==programming.PDF_SHA256
        monkeypatch.setattr(programming,'PDF',str(target))
    else:
        import sys
        original=Path(sys.executable);target=tmp_path/'copied-netlist-exporter';shutil.copyfile(original,target)
        first=programming.canonical._export
        def export(*a,**kw):
            tree,metadata=first(*a,**kw)
            return tree,dict(metadata,exporter=str(target),exporter_sha256=programming.force._hash(target))
        monkeypatch.setattr(programming.canonical,'_export',export)
    p['selected_programming_resistors']=programming.plan(b,p['poses'],board_hint=p['board_hint'])
    forbidden=[]
    def fallback(*a,**kw):forbidden.append(True);raise AssertionError('no pending fallback is permitted here')
    monkeypatch.setattr(multiport,'single_edge_ownerships',fallback)
    steps=macro._extra_ownership_steps(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    assert next(steps)=='canonical_ground_multiport_boundary'
    if mutation=='append':target.write_bytes(target.read_bytes()+b'changed evidence or executable')
    elif mutation=='missing':target.unlink()
    else:target.write_bytes(target.read_bytes())
    before=macro.row._source_binding(b)
    if mutation=='same_bytes':assert len(macro._finish_extra_ownership(steps,time.monotonic()+8.))==2
    else:
        with pytest.raises(ValueError,match='macro_boundary_ownership_live_inputs_changed'):
            macro._finish_extra_ownership(steps,time.monotonic()+8.)
    assert forbidden==[]and before==macro.row._source_binding(b)
