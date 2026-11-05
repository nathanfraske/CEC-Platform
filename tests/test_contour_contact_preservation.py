"""Fresh absolute cut requalification, without laundering unknown legs."""
import copy
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_sense_evidence as evidence
import cec_rectilinear_copper as owner
from test_force_sense_evidence import fixture,run,contact_comparison_fixture


def native_reports(tmp_path):
    source=tmp_path/"source.kicad_pcb";candidate=tmp_path/"child.kicad_pcb"
    domains=fixture(source,filtered=True,angle=90)
    b=pcbnew.LoadBoard(str(source))
    # Real native fill needs an actual board boundary, unlike contact-only
    # observations. No reference/name coordinate is used by the engine.
    for a,z in [((0,0),(200,0)),((200,0),(200,200)),((200,200),(0,200)),((0,200),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));edge.SetLayer(pcbnew.Edge_Cuts);b.Add(edge)
    pcbnew.SaveBoard(str(source),b)
    before=run(source,domains);before["identity_stable"]=True
    assert before["clipped_isolation"]["passed"]==2
    t=max((t for t in b.GetTracks() if t.GetNetname()=="RENAMED_FEED"),key=lambda t:t.GetLength())
    uid=t.m_Uuid.AsString()
    plan=owner.plan(b,[uid],clearance_nm=200000,min_thickness_nm=100000,
        required_width_nm=500000,allow_locked_track_uuids=[uid],contour_style="chamfer45")
    emitted=owner.materialize(b,plan,allow_locked_track_uuids=[uid])
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(candidate),b)
    assert owner.receive(pcbnew.LoadBoard(str(candidate)),plan,emitted["zone_uuid"])["ok"]
    after=run(candidate,domains);after["identity_stable"]=True
    assert after["clipped_isolation"]["passed"]==2
    manifest=[dict(net="RENAMED_FEED",retired_track_uuids=[uid],added_zone_uuids=[emitted["zone_uuid"]])]
    return before,after,manifest


def test_real_native_positive_legs_are_requalified_not_blindly_hash_relabelled(tmp_path):
    before,after,manifest=native_reports(tmp_path)
    assert not evidence.compare_contact_preservation(before,after,native_copper_transforms=manifest)["same_evidence"]
    initial=copy.deepcopy((before,after))
    result=evidence.compare_contour_preservation(before,after,modified_nets=["RENAMED_FEED"],native_copper_transforms=manifest)
    assert result["comparison_complete"] and result["same_evidence"],result
    assert result["rebound_nets"][0]["after"]["checked"]==1
    assert result["coverage_after"]["passed"]==2
    assert not result["release_authority"] and result["kelvin_isolation_qualified"] is None
    assert (before,after)==initial


@pytest.mark.parametrize("fault",["unlisted_net","guard","source_uuid","lineage","bypass","cut_incomplete","missing_refinement","unknown_to_pass","new_model_property","failure_on_other_net","count","current_authority"])
def test_scoped_rebinding_cannot_hide_any_safety_or_unaffected_evidence_change(tmp_path,fault):
    before,after,manifest=native_reports(tmp_path);modified=["RENAMED_FEED"]
    row=next(r for r in after["clipped_isolation"]["details"] if r["net"]=="RENAMED_FEED")
    if fault=="unlisted_net":modified=["RENAMED_LOAD"]
    elif fault=="guard":row["native"]["numerical_guard_nm"]+=1
    elif fault=="source_uuid":row["native"]["source"]["uuid"]="stale-physical-source"
    elif fault=="lineage":after["lineage"]["details"][0]["ref"]="changed-physical-input"
    elif fault=="bypass":row["native"].update(ok=False,physical_bypass_proved=True)
    elif fault=="cut_incomplete":row["native"]["complete"]=False
    elif fault=="missing_refinement":row["native"]["exact_linear_identity_verified"]=False
    elif fault=="unknown_to_pass":
        old=next(r for r in before["clipped_isolation"]["details"] if r["net"]=="RENAMED_FEED")
        old.update(ok=None,status="unknown");old["native"].update(ok=None,complete=False)
    elif fault=="new_model_property":row["native"]["unrecorded_process_waiver"]=True
    elif fault=="failure_on_other_net":
        other=next(r for r in after["clipped_isolation"]["details"] if r["net"]=="RENAMED_LOAD")
        other["native"]["complete"]=False
    elif fault=="count":after["clipped_isolation"]["unknown"]=1
    else:after["authority"]["RENAMED_FEED"]["source_refs"]=["WRONG_CURRENT_SOURCE"]
    result=evidence.compare_contour_preservation(before,after,modified_nets=modified,native_copper_transforms=manifest)
    assert not result["same_evidence"],result
    assert not result["release_authority"]


def test_unmodified_unknown_geometry_remains_strict_and_unknown():
    before=contact_comparison_fixture();before["clipped_isolation"].update(ok=None,status="unknown",passed=0,unknown=1)
    row=before["clipped_isolation"]["details"][0]
    row.update(ok=None,status="unknown");row["native"].update(ok=None,complete=False)
    for item in before["shunt_pad_omitted"]["details"]:
        item.update(input_ref=row["input_ref"],leg=row["leg"],net=row["net"],reached_authority=[])
    before["shunt_pad_omitted"]["reached_authority_legs"]=0
    after=copy.deepcopy(before)
    result=evidence.compare_contour_preservation(before,after,modified_nets=["RENAMED_FORCE"])
    assert result["same_evidence"] and result["coverage_after"]["unknown"]==1 and not result["rebound_nets"]
    after["clipped_isolation"]["details"][0]["native"]["contacts_examined"]+=1
    assert not evidence.compare_contour_preservation(before,after,modified_nets=["RENAMED_FORCE"])["same_evidence"]


@pytest.mark.parametrize('fault',[None,'new_exit','wrong_delta','lost_internal','guard','unknown'])
def test_received_internal_contact_needs_exact_departures_and_absolute_cuts(tmp_path,fault):
    before,after,manifest=native_reports(tmp_path)
    row=next(r for r in after['inner_departure']['details'] if r['net']=='RENAMED_FEED')
    row['native']['contact_count']+=1;row['native']['internal_count']+=1
    if fault=='new_exit':row['native']['departure_count']+=1
    elif fault=='wrong_delta':row['native']['contact_count']+=1
    elif fault=='lost_internal':row['native']['internal_count']-=2;row['native']['contact_count']-=2
    elif fault=='guard':row['native']['new_unrecorded_permission']=True
    elif fault=='unknown':
        cut=next(r for r in before['clipped_isolation']['details'] if r['net']=='RENAMED_FEED')
        cut.update(ok=None,status='unknown');cut['native'].update(ok=None,complete=False)
    result=evidence.compare_contour_preservation(before,after,modified_nets=['RENAMED_FEED'],
        native_copper_transforms=manifest,rebind_covered_internal_contacts=True)
    assert result['same_evidence']==(fault is None),result
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize("fault",[None,"unknown_cut","wrong_terminal","invalid_counter","not_observation","duplicate_terminal"])
def test_vertex_deletion_observation_needs_fresh_geometric_cut_not_a_graph_excuse(tmp_path,fault):
    before,after,manifest=native_reports(tmp_path)
    row=next(r for r in after["shunt_pad_omitted"]["details"] if r["net"]=="RENAMED_FEED")
    row["reached_authority"]=copy.deepcopy(row["authority_excluding_cut"])
    after["shunt_pad_omitted"]["reached_authority_legs"]=1
    if fault=="unknown_cut":
        cut=next(r for r in after["clipped_isolation"]["details"] if r["net"]=="RENAMED_FEED")
        cut["native"].update(ok=None,complete=False)
    elif fault=="wrong_terminal":row["reached_authority"][0]["uuid"]="foreign-physical-terminal"
    elif fault=="invalid_counter":after["shunt_pad_omitted"]["reached_authority_legs"]=0
    elif fault=="not_observation":row["ok"]=True
    elif fault=="duplicate_terminal":row["reached_authority"]*=2
    result=evidence.compare_contour_preservation(before,after,modified_nets=["RENAMED_FEED"],native_copper_transforms=manifest)
    assert result["same_evidence"]==(fault is None),result
    if fault is None:
        assert result["vertex_omission_observations_rebound"][0]["basis"]=="fresh_absolute_geometric_cut_not_PAD_vertex_deletion"
        assert result["coverage_after"]["passed"]==2
    assert result["kelvin_isolation_qualified"] is None and not result["release_authority"]
