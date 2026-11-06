"""Distinct Source-stage Ground cut identity plus independent native frame."""
import copy
from pathlib import Path
import time

import pcbnew
import pytest
import cec_field_coupling as field
import cec_linear_stage_ground_boundary as op
import cec_cell_macro_requests as compiler
from cec_native_items import discard_items
from test_linear_stage_ground_boundary import fixture as boundary_fixture


def fixture(tmp_path,monkeypatch,locked=False):
    parent,proposal,ids,root,tree=boundary_fixture(tmp_path,monkeypatch)
    # The native transport mode must not pretend an independently stretched
    # retained branch has a known port projection. This positive fixture is
    # the complete original land-to-barrel pickup, with no such extra branch.
    discard_items(parent,[op.native._items(parent)[ids['branch']]])
    props=parent.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';parent.SetProperties(props)
    edge=op.native._items(parent)[ids['edge']];edge.SetLocked(locked)
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    proposal.update(source_native_binding=op.row._source_binding(parent),
        source_linear_power_stages=op.entries.stage.collect(parent,proposal['poses'],
            board_hint=str(root),enabled=True),row_plan={},max_shift_mm=6.,allow_owned_locked_escapes=True)
    return parent,proposal,ids,root


def derive(parent,proposal,ids,**kw):
    return op.ownership(parent,proposal,[ids['edge']],deadline=time.monotonic()+9.,**kw)


def test_default_stays_unchanged_and_unlocked(tmp_path,monkeypatch):
    parent,q,ids,root=fixture(tmp_path,monkeypatch)
    authority=derive(parent,q,ids)['extras'][0]['authority']
    assert op.authority_label(authority)
    assert authority['existing_barrels_must_survive_unchanged']is True
    assert 'independent_native_transport'not in authority['source_linear_stage_ground_boundary']
    assert not op.transport_matches(authority,{})


def test_exact_locked_Source_consent_is_distinct_from_transport(tmp_path,monkeypatch):
    parent,q,ids,root=fixture(tmp_path,monkeypatch,True)
    with pytest.raises(ValueError,match='every_and_only_locked'):derive(parent,q,ids)
    authority=derive(parent,q,ids,allow_locked_track_uuids=[ids['edge']])['extras'][0]['authority']
    assert op.authority_label(authority)and authority['kind']==op.KIND
    proof=authority['source_linear_stage_ground_boundary']
    assert proof['exact_locked_Source_edge_consent']==[ids['edge']]
    assert proof['exact_Source_edge']['locked']is True
    assert authority['existing_barrels_must_survive_unchanged']is True
    assert not op.transport_matches(authority,{})


@pytest.mark.parametrize('fault',['unrelated','duplicate','wrong_type','unnecessary'])
def test_exact_locked_scope_refuses_wrong_consent(tmp_path,monkeypatch,fault):
    parent,q,ids,root=fixture(tmp_path,monkeypatch,fault!='unnecessary')
    consent={'unrelated':[ids['branch']],'duplicate':[ids['edge']]*2,
        'wrong_type':True,'unnecessary':[ids['edge']]}[fault]
    with pytest.raises(ValueError,match='locked'):
        derive(parent,q,ids,allow_locked_track_uuids=consent)


def test_native_transport_is_rederived_not_caller_authority(tmp_path,monkeypatch):
    parent,q,ids,root=fixture(tmp_path,monkeypatch,True)
    before=Path(parent.GetFileName()).read_bytes();binding=op.row._source_binding(parent)
    calls=[];actual=compiler._frame
    def observe(*a,**kw):
        result=actual(*a,**kw);calls.append(result[1]);return result
    monkeypatch.setattr(compiler,'_frame',observe)
    result=derive(parent,q,ids,allow_locked_track_uuids=[ids['edge']],native_transport_options={})
    authority=result['extras'][0]['authority']
    assert len(calls)==1 and op.authority_label(authority)
    assert op.transport_matches(authority,calls[0])
    assert authority['existing_barrels_must_survive_unchanged']is False
    assert authority['existing_barrel_dispositions_require_independent_frame']is True
    assert authority['source_owned_barrel_roots']==[]
    control=next(r for r in authority['source_pad_roots']if r['pad_uuid']==ids['root'])
    assert control['role']=='control'and control['functional_ground_return']is False
    assert authority['current_authority']is False and authority['new_barrel_authority']is False
    assert all(p['every_original_contact_mandatory']and 'independent_frame_contact_ports'in p
        for p in authority['source_linear_stage_ground_boundary']['source_contacts'])
    assert before==Path(parent.GetFileName()).read_bytes()and binding==op.row._source_binding(parent)
    corrupt=copy.deepcopy(calls[0]);corrupt['new_barrels_created']=1
    assert not op.transport_matches(authority,corrupt)


@pytest.mark.parametrize('options',[True,[],{'transport':{}},{'unknown':[]},{'reuse_ground_barrels':True},
    {'ordinary_via_poses':{'uuid':'caller proof'}}])
def test_only_literal_whitelisted_frame_intent_is_accepted(tmp_path,monkeypatch,options):
    parent,q,ids,root=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='literal_frame_options'):
        derive(parent,q,ids,native_transport_options=options)


@pytest.mark.parametrize('field_name',['mode','options','hash','barrel_authority','contact','consent'])
def test_mutated_structural_transport_proof_refused(tmp_path,monkeypatch,field_name):
    parent,q,ids,root=fixture(tmp_path,monkeypatch,True)
    authority=derive(parent,q,ids,allow_locked_track_uuids=[ids['edge']],native_transport_options={})['extras'][0]['authority']
    bad=copy.deepcopy(authority);proof=bad['source_linear_stage_ground_boundary']
    if field_name=='mode':proof['independent_native_transport']['mode']='caller accepted'
    elif field_name=='options':proof['independent_native_transport']['options']['caller_proof']=[]
    elif field_name=='hash':proof['independent_native_transport']['independently_rederived_transport_sha256']='bad'
    elif field_name=='barrel_authority':proof['independent_native_transport']['barrel_motion_authority']=True
    elif field_name=='contact':proof['source_contacts'][0].pop('independent_frame_contact_ports')
    else:proof['exact_locked_Source_edge_consent']=[]
    # Recompute the outer diagnostic checksum: structural checks must still
    # reject this malformed mode rather than trusting a producer hash.
    bad['Source_binding_sha256']=op._digest(proof)
    assert not op.authority_label(bad)


def test_exact_width_rule_not_weakened_in_transport_mode(tmp_path,monkeypatch):
    parent,q,ids,root=fixture(tmp_path,monkeypatch)
    edge=op.native._items(parent)[ids['edge']];edge.SetWidth(200000)
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    q['source_native_binding']=op.row._source_binding(parent)
    q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=str(root),enabled=True)
    with pytest.raises(ValueError,match='exact_Source_class_width'):
        derive(parent,q,ids,native_transport_options={})
