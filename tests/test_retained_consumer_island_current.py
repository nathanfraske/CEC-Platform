"""Existing copper receives only the same physically exclusive local budget."""
import math
import pcbnew
import pytest
import cec_constraints as constraints
import cec_supply_consumer_branch as branch
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
from test_supply_consumer_branch import fixture


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_retained_leaf_receives_existing_allowance_but_shared_trunk_does_not(monkeypatch,tmp_path,angle,mirror):
    b,root,a,new,old,trunk,g,row,rail,*_=fixture(monkeypatch,tmp_path,angle=angle,mirror=mirror)
    before=field._field_snapshot_inventory(b)
    r=branch.inventory(b,board_hint='unrelated',timeout_s=10.)
    assert r['complete'],r
    assert set(r['track_requirements'])=={force._uid(new)}
    assert set(r['retained_island_track_requirements'])=={force._uid(old)}
    assert set(r['all_owned_track_requirements'])=={force._uid(new),force._uid(old)}
    assert force._uid(trunk) not in r['all_owned_track_requirements']
    assert all(v['current_authority']['amps']==.5 for v in r['all_owned_track_requirements'].values())
    assert r['proofs'][0]['budget']['aggregate_current_authority']['amps']==3.
    assert field._field_snapshot_inventory(b)==before
    loaded=pcbnew.LoadBoard(b.GetFileName())
    assert branch.inventory(loaded,board_hint='unrelated',timeout_s=10.)==r


def test_inherited_narrow_leaf_is_still_a_fault_at_local_floor_and_shared_trunk_stays_full(monkeypatch,tmp_path):
    b,root,a,new,old,trunk,g,row,rail,*_=fixture(monkeypatch,tmp_path)
    old.SetWidth(100000);trunk.SetWidth(200000)
    monkeypatch.setattr(topology,'current_contract_for_net',lambda *a,**k:dict(rail))
    monkeypatch.setattr(constraints,'_legal_neckdown_uuids',lambda *a,**k:set())
    monkeypatch.setattr(constraints,'_validated_current_supply_escape_uuids',lambda *a,**k:set())
    field._save_field_snapshot(b,b.GetFileName())
    result=constraints.CHECKERS['trace-width-high-current'](b,b.GetFileName(),{})
    assert result[0] is False,result
    rows={r['uuid']:r for r in result[2] if r.get('type')=='keepout'}
    assert rows[force._uid(old)]['current_authority']['amps']==.5
    assert rows[force._uid(old)]['actual_mm']==.1
    assert rows[force._uid(old)]['required_mm']>=.2
    assert rows[force._uid(trunk)]['current_authority']['amps']==3.
    assert force._uid(new) not in rows


@pytest.mark.parametrize('fault',['unknown_load','second_tap','reused_root','unknown_cap','no_policy'])
def test_retained_allocation_is_withheld_when_full_native_leaf_proof_fails(monkeypatch,tmp_path,fault):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path)
    if fault=='unknown_load':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetValue('unknown')
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(root.GetNet());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(root.GetPosition())
    elif fault=='second_tap':trunk.SetStart(pcbnew.VECTOR2I_MM(6,5))
    elif fault=='reused_root':
        duplicate=pcbnew.PCB_GROUP(b);b.Add(duplicate);duplicate.SetName(g.GetName())
    elif fault=='unknown_cap':cap.SetValue('100uF')
    elif fault=='no_policy':declaration['params']['supply_consumer_allocations']=[]
    r=branch.inventory(b,board_hint='unrelated',timeout_s=10.)
    assert not r['complete'] and r['refusals']
    assert not r['track_requirements'] and not r['retained_island_track_requirements']
    assert not r['all_owned_track_requirements']
