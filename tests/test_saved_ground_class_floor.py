"""Literal Source connectivity is not new-route width or inherited debt qualification."""
import copy
import json
import time
import pytest
import pcbnew
import cec_cell_macro_requests as compiler
import cec_cell_escape_replan as escape
import cec_retained_ground_component as ground
import cec_force_current as force
from test_macro_retained_ground_reference import case


@pytest.mark.parametrize('ambient',[100000,900000])
def test_ground_boundary_class_comes_from_saved_project_not_ambient_native_class(tmp_path,monkeypatch,ambient):
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch,ground_class_width_mm=.5)
    native=compiler.cells._netclass
    def unrelated_native_class(board,net):
        q=native(board,net)
        return dict(q,width=ambient)if net=='GND'else q
    monkeypatch.setattr(compiler.cells,'_netclass',unrelated_native_class)
    authority=request['exact_additional_macro_component_source_ownership'][0]
    edge=next(t for t in parent.GetTracks()if force._uid(t)==authority['native_source_uuid'])
    actual=compiler._ground_boundary_authority(parent,edge,packet['transport'],packet['source_plan'],time.monotonic()+2.)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    authored=next(q for q in project['net_settings']['classes']if q['name']=='EXPLICIT_SYNTHETIC_GROUND')
    assert authored['track_width']==.5
    assert actual['source_full_class_width_nm']==500000
    assert actual['source_width_nm']==200000
    assert actual['source_class_geometry_origin']=='fresh_saved_source_project'
    assert actual['source_class_project_sha256']==force._hash(source.with_suffix('.kicad_pro'))
    assert actual['current_authority']is False


@pytest.mark.parametrize('demand',[200000,500000])
def test_zero_emission_scope_keeps_exact_subfloor_source_debt_visible(tmp_path,monkeypatch,demand):
    source,parent,private,packet,key,request=case(tmp_path,monkeypatch,ground_class_width_mm=.5)
    request=copy.deepcopy(request);request['width_nm']=demand
    assert ground._scope(request)
    before=escape.row._source_binding(private)
    proof=ground.observe(private,request)
    assert proof and proof['inherited_source_width_debt_present']
    assert proof['inherited_source_width_not_qualified']and not proof['current_qualified']
    assert proof['new_copper']==proof['new_holes']==0
    assert escape.row._source_binding(private)==before
    for width in (200001,499999,500001):
        forged=copy.deepcopy(request);forged['width_nm']=width
        assert ground.observe(private,forged)is None


def test_new_construction_cannot_borrow_retained_subfloor_width(tmp_path,monkeypatch):
    from test_macro_ground_branch_current_scope import fixture,forbid_aggregate_lookup
    source,private,packet,key,request=fixture(tmp_path,monkeypatch,ground_class_width_mm=.5)
    monkeypatch.setattr(ground,'observe',lambda *a,**k:None)
    forbid_aggregate_lookup(monkeypatch)
    details={};choices=[];before=escape.row._source_binding(private)
    escape._connection_menu(private,request,board_hint='opaque',deadline=time.monotonic()+1.,
        layers=[pcbnew.F_Cu,pcbnew.B_Cu],append=choices.append,detail=details)
    assert details['source_owned_low_power_ground_component']['source_full_class_width_nm']==500000
    assert choices and any(q for q in choices)
    assert all(op[3]>=500000 for q in choices for op in q if op[0]=='trk')
    assert escape.row._source_binding(private)==before
