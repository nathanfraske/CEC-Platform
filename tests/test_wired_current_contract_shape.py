"""Wire representation parity is not permission to alter current contracts."""
import copy
import pytest
import cec_additional_aggregate_macro as op
from cec_native_items import discard_items
from test_wired_additional_macro_integration import context,leaves


def prepared(tmp_path,monkeypatch):
    parent,child,proposal,pad,ids=context(tmp_path,monkeypatch,with_supply_boundary=True)
    positive=parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
    edge=next(t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'
        and t.GetNetCode()==positive.GetNetCode()
        and positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(),0))
    uid=leaves.native.force._uid(edge)
    proposal['row_plan']['retired_track_uuids']=[uid]
    discard_items(child,[t for t in child.GetTracks()if leaves.native.force._uid(t)==uid])
    return parent,child,proposal,uid


def test_actual_planner_tuple_inventory_equals_wire_roles_without_dropping_fields(tmp_path,monkeypatch):
    parent,child,proposal,uid=prepared(tmp_path,monkeypatch)
    planner=leaves.wired.cap.full;original=planner._model;seen=[]
    def native_model(*a,**kw):
        kind,domain,contract=original(*a,**kw);contract=copy.deepcopy(contract)
        for key in ('routing_layers','authority_refs'):
            if key in contract:contract[key]=tuple(contract[key])
        seen.append(contract)
        return kind,domain,contract
    monkeypatch.setattr(planner,'_model',native_model)
    demands=op.requests(parent,child,proposal)
    request,=[r for k,r in demands.items()if k.startswith('aggregate_incident_cut:')]
    assert request['source_full_current_incident_cut_plan']['retired_track_uuids']==[uid]
    assert request['width_nm']==500000 and request['every_surviving_source_component_port_mandatory']
    assert any(type(c.get('routing_layers'))is tuple for c in seen)


@pytest.mark.parametrize('fault',['current','margin','layers','missing_field','source_hash'])
def test_real_rating_or_identity_difference_is_not_normalized_away(tmp_path,monkeypatch,fault):
    parent,child,proposal,uid=prepared(tmp_path,monkeypatch)
    planner=leaves.wired.cap.full;original=planner.plan
    def changed(*a,**kw):
        result=copy.deepcopy(original(*a,**kw));contract=result['contract']
        if fault=='current':contract['current_authority']['amps']+=1
        elif fault=='margin':contract['current_authority']['geometry_margin']=99
        elif fault=='layers':contract['routing_layers']=['fabricated layer']
        elif fault=='missing_field':contract.pop('routing_layers')
        else:result['source_sha256']='0'*64
        return result
    monkeypatch.setattr(planner,'plan',changed)
    with pytest.raises(ValueError,match='same_full_current_cut_authority'):
        op.requests(parent,child,proposal)
