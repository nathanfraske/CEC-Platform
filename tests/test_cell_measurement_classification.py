"""Cell construction reuses positive native nonload evidence, never a label."""
import copy
import time
import pytest
import cec_cell_endpoint_groups as subject
import cec_current_topology as topology
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_measurement_current_branch as branch
from test_measurement_current_branch import fixture


def example(tmp_path,monkeypatch):
    source,b,net,domains,trunk=fixture(tmp_path)
    raw=dict(current_authority=dict(amps=39.,source='FIXED',sink='POWER_SINK',margin=1.25),
        profile='jlcpcb_6l_pofv_signal',required_by_layer_nm={0:16000000,2:190000000})
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:copy.deepcopy(domains))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a,**kw:copy.deepcopy(raw))
    monkeypatch.setattr(cells,'_netclass',lambda *a,**kw:{'width':2500000,'clearance':200000})
    ids=branch.inventory(b,source,domains)['uuids'];assert ids
    items=[t for t in b.GetTracks() if force._uid(t) in ids]
    return source,b,net,domains,trunk,raw,items


def test_group_and_saved_receive_distinguish_nonload_from_same_net_power(tmp_path,monkeypatch):
    source,b,net,domains,trunk,raw,items=example(tmp_path,monkeypatch)
    proof=subject.group(b,items,board_hint='arbitrary',source_path=source)
    assert proof and all(i.GetParentGroup() is None for i in items)
    result=subject.receive(b,b,{},items,board_hint='arbitrary',deadline=time.monotonic()+10.)
    assert set(result['track_uuids'])=={force._uid(i) for i in items}
    assert trunk not in result['track_uuids']
    assert not result['current_budget_lowered']
    assert not result['proofs'][0]['aggregate_current_budget_changed']


@pytest.mark.parametrize('fault',['unknown','load_terminal','timeout','changed_current','power_trunk'])
def test_no_untyped_or_stale_or_load_bearing_exemption(tmp_path,monkeypatch,fault):
    source,b,net,domains,trunk,raw,items=example(tmp_path,monkeypatch)
    if fault=='unknown':b.FindFootprintByReference('U_RENAMED').SetValue('UNKNOWN')
    elif fault=='load_terminal':domains[net]['authority_refs'].append('U_RENAMED')
    elif fault=='timeout':monkeypatch.setattr(branch,'inventory',lambda *a,**kw:dict(
        complete=False,uuids=[force._uid(i) for i in items],proofs=[]))
    elif fault=='changed_current':
        changed=copy.deepcopy(raw);changed['current_authority']['amps']+=1
        variants=iter([raw,changed]);monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:next(variants))
    else:items.append(next(t for t in b.GetTracks() if force._uid(t)==trunk))
    with pytest.raises(ValueError):
        subject.receive(b,b,{},items,board_hint='arbitrary',deadline=time.monotonic()+10.)
