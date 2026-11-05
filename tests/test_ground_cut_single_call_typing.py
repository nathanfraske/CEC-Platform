"""Independent Ground cut observer shares no axis/proof/current authority."""
import copy,json,time
from pathlib import Path
import pcbnew,pytest
import cec_cell_ground_cut_boundaries as ground
import cec_cell_macro_requests as compiler
import cec_programming_resistor_placement as programming
import cec_selected_cap_ground_boundary as fallback
import cec_field_coupling as field
from cec_native_items import discard_items
from test_ground_boundary_single_call import source_case


@pytest.mark.parametrize('monitor',[False,True])
def test_actual_saved_two_wide_source_cuts_have_one_fresh_role_replay(tmp_path,monkeypatch,monitor):
    source,p,_,edges=source_case(tmp_path,monkeypatch,monitor)
    project=Path(source.GetFileName()).with_suffix('.kicad_pro');data=json.loads(project.read_text())
    data['net_settings']['classes'][0]['track_width']=.5;project.write_text(json.dumps(data))
    for edge in edges:edge.SetWidth(500000)
    field._save_field_snapshot(source,source.GetFileName());source=pcbnew.LoadBoard(source.GetFileName())
    p['source_native_binding']=ground.row._source_binding(source)
    p['selected_programming_resistors']=programming.plan(source,p['poses'],board_hint=p['board_hint'])
    p['retired_track_uuids']=[compiler.force._uid(t)for t in edges]
    posed=pcbnew.LoadBoard(source.GetFileName());fp=posed.FindFootprintByReference('R_program');pose=p['poses']['R_program']
    fp.SetPosition(pcbnew.VECTOR2I(*(round(n*1e6)for n in pose[:2])));fp.SetOrientationDegrees(pose[2])
    discard_items(posed,[t for t in posed.GetTracks()if compiler.force._uid(t)in p['retired_track_uuids']])
    target=tmp_path/'posed.kicad_pcb';field._save_field_snapshot(posed,target);posed=pcbnew.LoadBoard(str(target))
    original=programming.plan;calls=[]
    def replay(*a,**kw):calls.append(True);return original(*a,**kw)
    monkeypatch.setattr(programming,'plan',replay)
    before=[ground.row._source_binding(b)for b in(source,posed)];inputs=copy.deepcopy(p)
    rows=ground.requests(source,posed,p,timeout_s=9.1)
    assert len(calls)==1 and len(rows)==1 and p==inputs
    row=next(iter(rows.values()));proof=row['retained_source_ground_fragment']
    assert row['kind']=='ground_boundary'and row['width_nm']==500000
    assert proof['retired_ground_track_uuids']==sorted(p['retired_track_uuids'])
    assert proof['low_power_source_cut_restoration_not_aggregate_ground_rating']
    assert proof['actual_fixed_source_contacts_not_same_net_proximity']
    assert before==[ground.row._source_binding(b)for b in(source,posed)]


def test_complete_typer_retains_original_singleton_fallback_wiring(tmp_path,monkeypatch):
    # This test substitutes ONLY the fallback verdict to inspect dispatch.
    # Positive native ownership/partition behavior is exercised above and
    # in the unchanged selected-cap Ground boundary test suites.
    source,p,t,edges=source_case(tmp_path,monkeypatch);observed=[];old=compiler._ground_boundary_at_edge
    def unknown(*a,**kw):
        old(*a,**kw)
        raise ValueError('changed_macro_ground_boundary_has_unowned_land:literal_fixed_port')
    def single(parent,proposal,ids,*,deadline):
        observed.append((parent is source,proposal is p,list(ids),deadline))
        return dict(extras=[dict(authority={'literal_singleton':ids[0]})])
    monkeypatch.setattr(compiler,'_ground_boundary_at_edge',unknown);monkeypatch.setattr(fallback,'ownership',single)
    deadline=time.monotonic()+8.;typer=compiler._complete_ground_boundary_typer(source,t,p,deadline)
    for edge in edges:assert typer(edge)=={'literal_singleton':compiler.force._uid(edge)}
    assert [q[:3]for q in observed]==[(True,True,[compiler.force._uid(edge)])for edge in edges]
    assert all(q[3]==deadline for q in observed)


@pytest.mark.parametrize('fault',['proposal','transport','family','canonical'])
def test_fallback_cannot_return_a_certificate_after_context_input_mutation(tmp_path,monkeypatch,fault):
    source,p,t,edges=source_case(tmp_path,monkeypatch);old=compiler._ground_boundary_at_edge
    def unknown(*a,**kw):
        old(*a,**kw)
        raise ValueError('changed_macro_ground_trunk_not_owned_by_cell_cut:literal_edge')
    def changed(*a,**kw):
        if fault=='proposal':p['selected_programming_resistors']['R_program']['current_authority']=True
        elif fault=='transport':t['source_process_barrel_motion']=[]
        elif fault=='family':Path(source.GetFileName()).with_suffix('.kicad_pro').write_text('{}')
        else:Path(p['board_hint']).write_text('; changed actual canonical Source')
        return dict(extras=[dict(authority={'not':'valid'})])
    monkeypatch.setattr(compiler,'_ground_boundary_at_edge',unknown);monkeypatch.setattr(fallback,'ownership',changed)
    typer=compiler._complete_ground_boundary_typer(source,t,p,time.monotonic()+8.)
    with pytest.raises(ValueError,match='same_call_(inputs|canonical_bindings)_changed'):typer(edges[0])
