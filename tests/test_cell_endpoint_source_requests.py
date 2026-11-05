"""Trial construction consumes the receiver's complete Source width demands."""
import ast
import inspect
import time

import pcbnew
import pytest
import cec_cell_endpoint_groups as groups
import cec_cell_escape_replan as escape
import cec_fr as fr
import cec_force_current as force
from test_cell_endpoint_groups import supply


def low_class(monkeypatch,back=False,angle=0):
    b,launch,via,trunk,prefix,contract,requests=supply(monkeypatch,back=back,angle=angle)
    prefix.GetParentGroup().RemoveItem(prefix)
    # Deliberate discovery fixture: shared Source demand remains 1 mm while
    # the local catalog/class alone sees the smaller current-qualified lead.
    monkeypatch.setattr(groups.cells,'_netclass',lambda*b:{'width':prefix.GetWidth(),'clearance':200000})
    return b,prefix,requests


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_request_aware_group_matches_independent_saved_receiver(monkeypatch,back,angle):
    b,prefix,requests=low_class(monkeypatch,back,angle)
    assert groups.group(b,[prefix],board_hint='renamed')==[]
    assert prefix.GetParentGroup()is None
    with pytest.raises(ValueError,match='ungrouped_narrow_endpoint'):
        groups.receive(b,b,requests,[prefix],board_hint='renamed',deadline=time.monotonic()+10)
    proofs=groups.group(b,[prefix],board_hint='renamed',requests=requests)
    assert proofs and prefix.GetParentGroup().GetName()==fr.ENDPOINT_NECKDOWN_GROUP
    received=groups.receive(b,b,requests,[prefix],board_hint='renamed',deadline=time.monotonic()+10)
    assert received['track_uuids']==[force._uid(prefix)]and not received['current_budget_lowered']


def test_constructor_rejects_long_component_receiver_also_refuses(monkeypatch):
    b,prefix,requests=low_class(monkeypatch)
    prefix.SetStart(prefix.GetStart()+pcbnew.VECTOR2I_MM(-3,0))
    with pytest.raises(groups.EndpointMaterializationRefused):
        groups.group(b,[prefix],board_hint='renamed',requests=requests)
    assert prefix.GetParentGroup()is None
    with pytest.raises(ValueError):
        groups.receive(b,b,requests,[prefix],board_hint='renamed',deadline=time.monotonic()+10)


def test_requests_do_not_grant_missing_current_authority(monkeypatch):
    b,prefix,requests=low_class(monkeypatch)
    monkeypatch.setattr(groups.cells,'_supply_current_widths',lambda*b:None)
    with pytest.raises(ValueError,match='positive_source_current'):
        groups.group(b,[prefix],board_hint='renamed',requests=requests)


def test_materialization_passes_original_requests_and_preserves_rejection_provenance(monkeypatch):
    b,prefix,requests=low_class(monkeypatch)
    selected={'local':dict(id='0',net=prefix.GetNetname(),ops=[('trk',
        tuple(prefix.GetStart()),tuple(prefix.GetEnd()),prefix.GetWidth(),int(prefix.GetLayer()))])}
    # Isolate native item creation only; actual cohort/neckdown qualification
    # below remains real, with the same exact native fixture as the receiver.
    monkeypatch.setattr(escape,'_native_ops',lambda board,ops,net:[prefix])
    made,owners=escape._stage_selected_connections(b,selected,board_hint='renamed',source_path=None,requests=requests)
    assert made==[prefix]and owners[force._uid(prefix)]==dict(obligation='local',choice_id='0')
    assert groups.receive(b,b,requests,made,board_hint='renamed',deadline=time.monotonic()+10)['track_uuids']


def test_both_trial_and_save_call_sites_explicitly_forward_original_source_requests():
    tree=ast.parse(inspect.getsource(escape));calls=[n for n in ast.walk(tree)
        if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='_stage_selected_connections']
    assert len(calls)==2
    for call in calls:
        keyword=next(k for k in call.keywords if k.arg=='requests')
        assert isinstance(keyword.value,ast.Call)
        assert keyword.value.args[0].value=='original_source_requests'


@pytest.mark.parametrize('long',[False,True])
def test_private_constructor_uses_complete_original_request_width_and_rolls_back(monkeypatch,long):
    import cec_exact_connection_aliases as aliases
    b,prefix,requests=low_class(monkeypatch)
    if long:prefix.SetStart(prefix.GetStart()+pcbnew.VECTOR2I_MM(-3,0))
    choice=dict(id='0',net=prefix.GetNetname(),ops=[('trk',tuple(prefix.GetStart()),
        tuple(prefix.GetEnd()),prefix.GetWidth(),int(prefix.GetLayer()))])
    domains={'arbitrary':[choice]};coverage=aliases.derive(requests)
    packet=dict(domains=domains,original_source_requests=requests,exact_source_request_aliases=coverage,
        source_native_binding=escape.row._source_binding(b),ground_dependency_board_hint='renamed')
    selection=dict(complete=True,all_obligations_present=True,routing_admitted=False,
        domain_binding=escape.joint._binding(domains),selected={'arbitrary':choice},
        original_obligation_coverage=coverage)
    monkeypatch.setattr(escape,'_native_ops',lambda board,ops,net:[prefix])
    if long:
        with pytest.raises(groups.EndpointMaterializationRefused)as caught:
            escape.construct_private(b,packet,selection)
        assert caught.value.constructed_by[force._uid(prefix)]==dict(obligation='arbitrary',choice_id='0')
        assert prefix.GetParentGroup()is None
    else:
        made=escape.construct_private(b,packet,selection)
        assert made==[prefix]and prefix.GetParentGroup().GetName()==fr.ENDPOINT_NECKDOWN_GROUP
        assert groups.receive(b,b,requests,made,board_hint='renamed',deadline=time.monotonic()+10)['track_uuids']
