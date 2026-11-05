"""Explicit Source reach must survive the independently rated-power tier.

The synthetic current catalog is test-only.  Native conductors, unchanged
width/layer gates, obstruction geometry and saved Source bytes are real.
"""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_macro_obstacle_cuts as cuts
from test_macro_obstacle_cuts import fixture


def current_case(tmp_path,monkeypatch,quarter=0,back=False):
    source,parent,private,proposal,ids=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    edge=next(t for t in parent.GetTracks() if force._uid(t)==ids[0])
    a,z=edge.GetStart(),edge.GetEnd()
    edge.SetEnd(pcbnew.VECTOR2I(a.x+(z.x-a.x)*49//10,a.y+(z.y-a.y)*49//10))
    field._save_field_snapshot(parent,source)
    net=str(edge.GetNetname());face=parent.GetLayerName(edge.GetLayer())
    contract=dict(net=net,routing_layers=[face],required_by_layer_mm={face:.2},
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    domain=dict(complete=True,source_refs=['source'],sink_refs=['receiver'])
    monkeypatch.setattr(cuts.ordinary,'eligible_nets',lambda *args:set())
    monkeypatch.setattr(cuts.full.topology,'board_current_domains',lambda *args:{net:domain})
    monkeypatch.setattr(cuts.full.topology,'route_width_contracts',lambda *args,**kw:{net:contract})
    return source,parent,private,proposal,edge,contract,domain


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_long_current_owned_obstacle_uses_explicit_source_work_without_narrowing(tmp_path,monkeypatch,quarter,back):
    source,parent,private,proposal,edge,contract,domain=current_case(tmp_path,monkeypatch,quarter,back)
    raw=source.read_bytes();uid=force._uid(edge)
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,[uid],deadline=time.monotonic()+10.)
    proof=cuts.ownership(parent,private,source,proposal,[uid],deadline=time.monotonic()+10.,max_source_track_mm=24.)
    rated=proof[0]['authority']['source_plan']
    assert rated['max_source_track_mm']==24. and rated['width_nm']==200000
    assert rated['contract']==contract and rated['retired_track_uuids']==[uid]
    assert proof[0]['source_native_obstacle_ownership']['literal_foreign_native_conflicts']
    assert source.read_bytes()==raw and not rated['source_current_reduced'] and not rated['release_authority']


@pytest.mark.parametrize('fault',['current_floor','unknown_authority','incomplete','wrong_face','locked','grouped','unrelated'])
def test_source_reach_never_waives_current_ownership_face_or_real_obstruction(tmp_path,monkeypatch,fault):
    source,parent,private,proposal,edge,contract,domain=current_case(tmp_path,monkeypatch)
    if fault=='current_floor':contract['required_by_layer_mm']['F.Cu']=.3
    elif fault=='unknown_authority':contract['current_authority']['source']='unverified_guess'
    elif fault=='incomplete':domain['complete']=False
    elif fault=='wrong_face':contract['routing_layers']=['B.Cu']
    elif fault=='locked':edge.SetLocked(True)
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(parent);parent.Add(group);group.AddItem(edge)
    else:edge.Move(pcbnew.VECTOR2I_MM(0,5))
    with pytest.raises(ValueError):
        cuts.ownership(parent,private,source,proposal,[force._uid(edge)],
            deadline=time.monotonic()+10.,max_source_track_mm=24.)
