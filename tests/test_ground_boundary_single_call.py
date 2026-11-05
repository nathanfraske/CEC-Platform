"""One fresh same-call Source replay, unchanged native checks per edge."""
import copy,time
from pathlib import Path
import pcbnew,pytest
import cec_cell_macro_requests as macro
import cec_programming_resistor_placement as programming
import cec_field_coupling as field
from test_programming_resistor_placement import fixture


def source_case(tmp_path,monkeypatch,monitor=False):
    b,owner,r,root,tree,poses=fixture(tmp_path,monkeypatch,monitor_pin='6'if monitor else None)
    g=next(p for p in r.Pads()if p.GetNetname()=='GND')
    first=next(t for t in b.GetTracks()if t.GetNetname()=='GND')
    v=pcbnew.PCB_VIA(b);v.SetPosition(first.GetEnd());v.SetWidth(800000);v.SetDrill(400000)
    v.SetNetCode(g.GetNetCode());v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    second=pcbnew.PCB_TRACK(b);second.SetNetCode(g.GetNetCode());second.SetLayer(g.GetLayer())
    second.SetWidth(250000);second.SetStart(g.GetPosition());second.SetEnd(g.GetPosition()+pcbnew.VECTOR2I(0,1200000));b.Add(second)
    field._save_field_snapshot(b,b.GetFileName())
    selected=programming.plan(b,poses,board_hint=str(root))
    p=dict(scope='source_typed_complete_cell_escape_proposal',poses=poses,board_hint=str(root),
        selected_programming_resistors=selected,selected_bypasses={},device_contracts={},
        retired_track_uuids=[],max_shift_mm=6.,source_native_binding=macro.row._source_binding(b))
    t=dict(source_process_barrel_motion=[dict(uuid=macro.force._uid(v),source_owner_pad_uuids=[macro.force._uid(g)])],
        changes=[dict(uuid=macro.force._uid(edge),net='GND',
            source_nm=[list(edge.GetStart()),list(edge.GetEnd())])for edge in(first,second)])
    return b,p,t,(first,second)


@pytest.mark.parametrize('monitor',[False,True])
def test_multiple_native_edges_and_duplicate_barrel_owner_replay_once_not_per_contact(tmp_path,monkeypatch,monitor):
    b,p,t,edges=source_case(tmp_path,monkeypatch,monitor)
    original=programming.plan;calls=[]
    def observed(*a,**kw):calls.append((a,kw));return original(*a,**kw)
    monkeypatch.setattr(programming,'plan',observed)
    before=macro.row._source_binding(b);saved=Path(b.GetFileName()).read_bytes();inputs=copy.deepcopy((p,t))
    rows=macro._extra_ownership(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    assert len(calls)==1 and len(rows)==2
    for q,edge in zip(rows,edges):
        a=q['authority'];assert q['change']==t['changes'][edges.index(edge)]
        assert a['native_source_uuid']==macro.force._uid(edge)and a['source_width_nm']==250000
        assert a['source_full_class_width_nm']==250000 and a['current_authority']is False
        assert len(a['source_pad_roots'])==1 and programming.ground_root_label(a['source_pad_roots'][0])
    assert len(rows[0]['authority']['source_owned_barrel_roots'])==1
    # A later invocation MUST perform a new complete canonical Source replay.
    assert macro._extra_ownership(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)==rows
    assert len(calls)==2 and (p,t)==inputs
    assert before==macro.row._source_binding(b)and saved==Path(b.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault',['proposal','transport','native','family','code','expired'])
def test_private_replay_context_cannot_outlive_its_exact_call_inputs(tmp_path,monkeypatch,fault):
    b,p,t,edges=source_case(tmp_path,monkeypatch)
    original=macro._ground_boundary_at_edge;count=[]
    def changed(*a,**kw):
        result=original(*a,**kw);count.append(True)
        if len(count)==1:
            if fault=='proposal':p['selected_programming_resistors']['R_program']['current_authority']=True
            elif fault=='transport':t['source_process_barrel_motion'][0]['source_owner_pad_uuids']=[]
            elif fault=='native':b.FindFootprintByReference('R_program').Move(pcbnew.VECTOR2I(1,0))
            elif fault=='family':Path(b.GetFileName()).with_suffix('.kicad_pro').write_text('{}')
            elif fault=='code':monkeypatch.setattr(macro.force,'_code_identity',lambda:{'not_the_frozen_code':'changed'})
        return result
    monkeypatch.setattr(macro,'_ground_boundary_at_edge',changed)
    deadline=time.monotonic()+8. if fault!='expired'else time.monotonic()-1
    expected=('macro_boundary_ownership_deadline'if fault=='expired'else
        'macro_ground_boundary_(same_call_inputs_changed|typing_deadline)')
    with pytest.raises(ValueError,match=expected):
        macro._extra_ownership(b,Path(b.GetFileName()),t,p,deadline)


@pytest.mark.parametrize('fault',['rating','ground','missing_role','node','part'])
def test_single_replay_is_still_fresh_canonical_not_a_caller_role_certificate(tmp_path,monkeypatch,fault):
    b,p,t,edges=source_case(tmp_path,monkeypatch)
    if fault=='rating':p['selected_programming_resistors']['R_program']['current_authority']=True
    elif fault=='ground':p['selected_programming_resistors']['R_program']['ground_pad_uuid']='forged'
    elif fault=='missing_role':p['selected_programming_resistors']={}
    elif fault=='node':p['selected_programming_resistors']['R_program']['net']='GND'
    else:b.FindFootprintByReference('U_program').SetField('MPN','unknown')
    with pytest.raises(ValueError):macro._extra_ownership(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)


def test_standalone_boundary_calls_cannot_reuse_an_earlier_complete_role(tmp_path,monkeypatch):
    b,p,t,edges=source_case(tmp_path,monkeypatch);original=programming.plan;calls=[]
    def observed(*a,**kw):calls.append(True);return original(*a,**kw)
    monkeypatch.setattr(programming,'plan',observed)
    for edge in edges:
        result=macro._legacy_ground_boundary_authority(b,edge,t,p,time.monotonic()+8.)
        assert programming.ground_root_label(result['source_pad_roots'][0])
    assert len(calls)==2
