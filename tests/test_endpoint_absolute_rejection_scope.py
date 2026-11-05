"""Native rejection learning must keep every possible constructive rescuer."""
import copy

import pcbnew
import pytest
import cec_cell_endpoint_groups as groups
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_joint_connection_search as joint
from cec_native_items import discard_items
from test_cell_endpoint_groups import ground


def choice(name,ops,net='GND',cost=0):
    return dict(id=name,ops=ops,net=net,cost=cost)


def op(a=(10000000,10000000),b=(12000000,10000000),width=280000,face=0):
    return ['trk',list(a),list(b),width,face]


def native_error(monkeypatch):
    board,pad,narrow,trunk,requests=ground(monkeypatch)
    discard_items(board,[narrow,trunk])
    selected={'producer':choice('long',[op()])}
    with pytest.raises(groups.EndpointMaterializationRefused)as failed:
        escape._stage_selected_connections(board,selected,board_hint='synthetic',source_path=None)
    error=failed.value
    assert error.native_components[0]['reason']=='escape_budget_exceeded'
    assert sum(t['length_nm']for t in error.native_components[0]['tracks'])==2000000
    assert error.constructed_by and error.fixed_ordinary_nets==('GND',)
    # Native owners must outlive SWIG views throughout the test.
    return board,pad,narrow,trunk,error,selected


def clause(error,selected,domains):
    return groups.rejection_clause(error,selected,domain_binding=joint._binding(domains),domains=domains)


def test_native_absolute_failure_omits_thousands_of_unrelated_same_net_variants(monkeypatch):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    domains={'producer':[selected['producer'],choice('short',[op(b=(10400000,10000000))],cost=1)]}
    for key,y in [('later_a',20000000),('later_b',22000000)]:
        domains[key]=[choice(str(i),[op(a=(10000000+i,y),b=(12000000+i,y))],cost=i)for i in range(48)]
    before=copy.deepcopy(domains);calls=[]
    def validate(chosen):
        calls.append({k:q['id']for k,q in chosen.items()})
        if chosen['producer']['id']=='long':return clause(error,chosen,domains)
        return True
    result=joint.solve(domains,conflicts=lambda *_:False,validate_selection=validate,
        timeout_s=2.,max_states=64)
    assert result['complete']and len(calls)==2
    assert result['learned_rejections'][0]['choices']==[('producer','long')]
    assert result['learned_prefix_cuts']and domains==before
    assert not result['routing_admitted']and not result['release_authority']


@pytest.mark.parametrize('rescue',[
    op(width=500000),
    op(a=(10000000,10000000),b=(11000000,10000000),width=500000),
    op(a=(11000000,10000000),b=(12000000,10000000)),
    op(a=(12000000,10000000),b=(13000000,10000000)),
    op(a=(9000000,10000000),b=(10000000,10000000)),
    op(a=(12000000,10000000),b=(10000000,10000000)),
])
def test_every_future_whole_partial_equal_width_or_endpoint_cover_is_retained(monkeypatch,rescue):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    selected['possible_rescuer']=choice('currently_distant',[op(a=(10000000,20000000),b=(12000000,20000000))])
    domains={k:[q]for k,q in selected.items()}
    domains['possible_rescuer'].append(choice('future_cover',[rescue],cost=1))
    result=clause(error,selected,domains)
    assert set(result.choices)=={('producer','long'),('possible_rescuer','currently_distant')}
    assert result.reason=='native_absolute_overlength_with_all_potential_collinear_rescuers'


@pytest.mark.parametrize('not_cover',[
    op(face=2),op(width=279999),
    op(a=(10000000,10000001),b=(12000000,10000001)),
    op(a=(12000001,10000000),b=(13000000,10000000)),
    op(a=(11000000,9000000),b=(11000000,11000000)),
])
def test_other_faces_insufficient_width_one_nm_offsets_and_crossings_cannot_suppress(monkeypatch,not_cover):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    selected['independent']=choice('elsewhere',[not_cover])
    domains={k:[q]for k,q in selected.items()}
    assert clause(error,selected,domains).choices==(('producer','long'),)


@pytest.mark.parametrize('fault',['native_context','owner','choice_id','stroke','length','unknown_operation','too_many_choices'])
def test_missing_or_ambiguous_proof_falls_back_to_whole_same_net_selection(monkeypatch,fault):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    selected['independent']=choice('unrelated',[op(a=(10000000,20000000),b=(12000000,20000000))])
    domains={k:[q]for k,q in selected.items()}
    if fault=='native_context':error.native_components=()
    elif fault=='owner':error.constructed_by={}
    elif fault=='choice_id':next(iter(error.constructed_by.values()))['choice_id']='wrong'
    elif fault=='stroke':error.native_components[0]['tracks'][0]['a_nm']=(10000001,10000000)
    elif fault=='length':error.native_components[0]['tracks'][0]['length_nm']=1500002
    elif fault=='unknown_operation':domains['independent'].append(choice('unknown',[['polygon',1]]))
    else:domains['independent']*=129
    result=clause(error,selected,domains)
    assert set(result.choices)=={('producer','long'),('independent','unrelated')}
    assert result.reason=='native_complete_same_net_endpoint_materialization_refused'


def test_missing_or_measurement_dependent_classification_keeps_other_net_partitions(monkeypatch,tmp_path):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    source=tmp_path/'source.kicad_pcb';source.write_text('not loaded by role-only check')
    import cec_device_power_roles as roles
    monkeypatch.setattr(roles,'footprint_contract',lambda fp:dict(pins={pad.GetNumber():'measurement'}))
    assert groups._fixed_ordinary_nets(board,{'GND'},source)==()
    error.fixed_ordinary_nets=()
    selected['other_current_partition']=choice('fixed',[],net='other')
    domains={k:[q]for k,q in selected.items()}
    result=clause(error,selected,domains)
    assert set(result.choices)=={('producer','long'),('other_current_partition','fixed')}
    assert groups.rejection_clause(error,selected,domain_binding='stale',domains=domains)is False


def test_actual_union_suppression_is_the_only_constructive_escape_from_bad_track(monkeypatch):
    board,pad,narrow,trunk,error,selected=native_error(monkeypatch)
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)in error.constructed_by])
    # Sufficient-width exact collinear parts are materialized first, so the
    # offending whole narrow stroke is not made at all. This remains only a
    # constructor test, not a saved connectivity/current/DRC admission.
    selected['cover']=choice('two_parts',[
        op(a=(10000000,10000000),b=(11000000,10000000),width=1000000),
        op(a=(11000000,10000000),b=(12000000,10000000),width=1000000)])
    made,owners=escape._stage_selected_connections(board,selected,board_hint='synthetic',source_path=None)
    assert made and all(t.GetWidth()==1000000 for t in made)
    assert all(owner['obligation']=='cover'for owner in owners.values())
