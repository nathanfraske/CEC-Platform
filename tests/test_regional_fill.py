"""Native region-preserving fill provenance, rotations and adversarial gates."""
import copy
import time

import pcbnew
import pytest

import cec_rectilinear_copper as owner
import cec_regional_fill as regions
from cec_local_copper_cell import copper_inventory
from test_native_landing_union import high_priority_setup, keeper_setup


def regional_plan(b,t,z,high=None):
    return owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=1000000,
        clearance_nm=200000,min_thickness_nm=100000,contour_style='chamfer45',
        contour_grid_nm=1000,fill_envelope_margin_nm=4,retire_source_tracks=False,
        enclosing_native_zone_uuids=[z.m_Uuid.AsString(),
            *([high.m_Uuid.AsString()] if high else [])],
        landing_enclosure_mode='canonical_outline',replace_native_zone_uuid=z.m_Uuid.AsString(),
        fill_policy=regions.POLICY)


def snapshot(tmp_path,b):
    path=tmp_path/'immutable-source.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    return pcbnew.LoadBoard(str(path))


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_native_regional_fill_keeps_stronger_clearance_and_source_exact(
        tmp_path,angle,mirror,layer):
    b,t,z,high=high_priority_setup(angle,mirror,layer);source=snapshot(tmp_path,b)
    before=copper_inventory(source);p=regional_plan(b,t,z,high)
    e=owner.materialize(b,p);r=owner.fill(b,p,e['zone_uuid'],regional_source=source)
    assert r['invented_copper'] is False
    path=tmp_path/'native-constrained.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));saved_before=copper_inventory(saved)
    proof=owner.receive(saved,p,e['zone_uuid'],regional_source=source,timeout_s=10)
    assert proof['ok'] and proof['complete'],proof
    assert proof['regional_fill_receiving']['protected_region_count']==1
    assert proof['regional_fill_receiving']['independently_replayed_native_additions']
    assert copper_inventory(saved)==saved_before and copper_inventory(source)==before
    void=high.Outline().CloneDropTriangulation();void.BooleanSubtract(high.GetFilledPolysList(layer))
    zone=next(z for z in saved.Zones() if z.m_Uuid.AsString()==e['zone_uuid'])
    intrusion=zone.GetFilledPolysList(layer).CloneDropTriangulation();intrusion.BooleanIntersection(void)
    assert not intrusion.OutlineCount()
    assert not proof['new_capacity_credited'] and not proof['release_authority']


def test_region_policy_also_receives_no_higher_priority_native_owner(tmp_path):
    b,t,z,_=keeper_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z)
    e=owner.materialize(b,p);owner.fill(b,p,e['zone_uuid'],regional_source=source)
    r=owner.receive(b,p,e['zone_uuid'],regional_source=source,timeout_s=10)
    assert r['ok'] and r['regional_fill_receiving']['protected_region_count']==0,r


@pytest.mark.parametrize('fault',['source_clearance','source_fill','source_priority',
    'candidate_clearance','candidate_high_clearance','candidate_high_fill',
    'rehash_source','rehash_regions','missing_source'])
def test_source_or_protected_process_changes_refuse_without_private_mutation(tmp_path,fault):
    b,t,z,high=high_priority_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z,high)
    e=owner.materialize(b,p)
    oldzones={z.m_Uuid.AsString():z for z in source.Zones()}
    if fault=='source_clearance':oldzones[z.m_Uuid.AsString()].SetLocalClearance(199999)
    elif fault=='source_fill':oldzones[z.m_Uuid.AsString()].SetFilledPolysList(pcbnew.F_Cu,
        owner._poly([(0,0),(1,0),(1,1),(0,1)]))
    elif fault=='source_priority':oldzones[high.m_Uuid.AsString()].SetAssignedPriority(2)
    elif fault=='candidate_clearance':z.SetLocalClearance(199999)
    elif fault=='candidate_high_clearance':high.SetLocalClearance(499999)
    elif fault=='candidate_high_fill':high.SetFilledPolysList(pcbnew.F_Cu,
        owner._poly([(0,0),(1,0),(1,1),(0,1)]))
    elif fault=='rehash_source':p['replacement_source_zone']['fill_nm'][0][0]+=1
    elif fault=='rehash_regions':p['regional_fill_binding']['protected_regions']=[]
    else:source=None
    if fault.startswith('rehash'):
        p.pop('plan_sha256');p['plan_sha256']=owner._digest(p)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.fill(b,p,e['zone_uuid'],regional_source=source)
    assert copper_inventory(b)==before


def test_raw_native_refill_cannot_bypass_stronger_region_policy(tmp_path):
    b,t,z,high=high_priority_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z,high)
    e=owner.materialize(b,p);owner.fill(b,p,e['zone_uuid'],regional_source=source)
    batch=pcbnew.ZONES();batch.append(z);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    r=owner.receive(b,p,e['zone_uuid'],regional_source=source,timeout_s=10)
    assert not r['ok'] and r['reason']=='higher_priority_native_landing_void_changed',r


def test_saved_receiving_requires_immutable_source_not_only_a_cached_proof(tmp_path):
    b,t,z,_=keeper_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z)
    e=owner.materialize(b,p);owner.fill(b,p,e['zone_uuid'],regional_source=source)
    r=owner.receive(b,p,e['zone_uuid'],timeout_s=10)
    assert not r['ok'] and not r['complete'] and r['reason']=='immutable_regional_source_required',r


@pytest.mark.parametrize('change',[1,-1])
def test_one_nanometre_fabricated_saved_fill_is_refused_by_native_replay(tmp_path,change):
    b,t,z,_=keeper_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z)
    e=owner.materialize(b,p);owner.fill(b,p,e['zone_uuid'],regional_source=source)
    original=z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    ring=original.Outline(0);v=ring.CPoint(0)
    ring.SetPoint(0,pcbnew.VECTOR2I(v.x+change,v.y))
    z.SetFilledPolysList(pcbnew.F_Cu,original)
    r=owner.receive(b,p,e['zone_uuid'],regional_source=source,timeout_s=10)
    assert not r['ok'] and not r['complete'],r


@pytest.mark.parametrize('policy',['caller_fake',True,0,[]])
def test_unsupported_regional_policy_cannot_declare_fabricated_fill(policy):
    b,t,z,_=keeper_setup();before=copper_inventory(b)
    with pytest.raises(owner.Refused):
        owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=1000000,
            clearance_nm=200000,min_thickness_nm=100000,fill_policy=policy)
    assert copper_inventory(b)==before
