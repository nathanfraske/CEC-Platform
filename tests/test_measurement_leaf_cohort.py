"""Batched native miters have disjoint original scopes, never a net waiver."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_measurement_leaf_cohort as cohort
import cec_measurement_leaf_finish as finish
import cec_measurement_leaf as leaf
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_measurement_leaf_finish import prepare_source


def two_steps(tmp_path,quarter=0,back=False):
    source,root=prepare_source(tmp_path,quarter,back);b=pcbnew.LoadBoard(str(source))
    q=leaf.plan(b,root);points=finish.paths(q)[0]['points_nm']
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in q['track_uuids']]);leaf.add_path(b,q,points)
    middle=force._copy_family(source,tmp_path/'one-root');field._save_field_snapshot(b,middle)
    first=finish.receive(source,middle,board_hint='fixture',pad_uuids=[root]);assert first['ok'],first
    second=finish.run(middle,tmp_path/'remaining',board_hint='fixture');assert second['changed'],second
    ids=second['records'][0]['plan']['pad_uuids'];assert root not in ids
    steps=[dict(source=str(source),candidate=str(middle),pad_uuids=[root]),
        dict(source=str(middle),candidate=second['candidate'],pad_uuids=ids)]
    return source,Path(second['candidate']),steps


def test_native_automatic_cohort_runs_in_a_fresh_bounded_namespace_and_stops(tmp_path):
    source,_=prepare_source(tmp_path);raw=source.read_bytes()
    r=cohort.run(source,tmp_path/'automatic-cohort',board_hint='fixture',max_steps=4)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert len(r['steps'])==1 and len(r['step_receipts'])==2
    assert r['finite_stop_reason']=='no_remaining_inventory'
    assert source.read_bytes()==raw and not r['release_authority']
    assert Path(r['step_receipts'][0]).is_file()
    with pytest.raises(ValueError,match='fresh_measurement_cohort_directory_required'):
        cohort.run(source,tmp_path/'automatic-cohort',board_hint='fixture')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_disjoint_composition_uses_original_boundaries_on_either_surface(tmp_path,quarter,back):
    source,candidate,steps=two_steps(tmp_path,quarter,back);raw=source.read_bytes()
    result=cohort.receive(source,candidate,board_hint='fixture',steps=copy.deepcopy(steps))
    assert result['ok'] and result['complete'],result
    assert len(result['source_leaves'])==2 and len(result['steps'])==2
    assert sum(q['source_right_angles']-q['candidate_right_angles'] for q in result['source_owned_measurement_progress'])>2
    assert result['original_leaf_boundaries_fixed_and_all_unowned_native_objects_exact']
    assert not result['retired_via_uuids'] and not result['current_authority'] and not result['kelvin_qualified']
    assert source.read_bytes()==raw and not result['release_authority']


@pytest.mark.parametrize('fault',['reversed','gap','wrong_final','foreign_force','width','pose','sidecar'])
def test_saved_cohort_refuses_chain_gaps_or_any_unowned_final_mutation(tmp_path,fault):
    source,candidate,steps=two_steps(tmp_path)
    if fault=='reversed':steps.reverse()
    elif fault=='gap':steps[1]['source']=str(source)
    elif fault=='wrong_final':candidate=Path(steps[0]['candidate'])
    elif fault=='sidecar':candidate.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:
        b=pcbnew.LoadBoard(str(candidate))
        if fault=='pose':b.FindFootprintByReference('SENSOR_WITH_UNRELATED_NAME').Move(pcbnew.VECTOR2I(1,0))
        elif fault=='width':next(t for t in b.GetTracks() if t.GetNetname()=='MEASURE_PLUS').SetWidth(199999)
        else:
            t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('+3V3'));t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
            t.SetStart(pcbnew.VECTOR2I_MM(3,3));t.SetEnd(pcbnew.VECTOR2I_MM(4,3));b.Add(t)
        field._save_field_snapshot(b,candidate)
    result=cohort.receive(source,candidate,board_hint='fixture',steps=steps)
    assert not result['ok'] and not result['complete'] and result['errors'] and not result['release_authority']


@pytest.mark.parametrize('steps',[None,[],[{}],True,[dict(source='a',candidate='b',pad_uuids=['root'])]*9,
    [dict(source='a',candidate='b',pad_uuids=['root','root'])],
    [dict(source='a',candidate='b',pad_uuids=['root']),dict(source='b',candidate='c',pad_uuids=['root'])],
    [dict(source='a',candidate='b',pad_uuids=[True])],
    [dict(source='a',candidate='b',pad_uuids=['root'],caller_current_waiver=True)]])
def test_invalid_or_repeated_cohort_roots_refuse_before_reading_files(steps):
    result=cohort.receive('missing','also-missing',board_hint='fixture',steps=steps)
    assert not result['ok'] and not result['complete'] and result['errors']


@pytest.mark.parametrize('lease',[True,False,0,11,float('nan'),float('inf')])
def test_work_lease_is_not_an_unbounded_composition(lease):
    result=cohort.receive('missing','missing2',board_hint='fixture',
        steps=[dict(source='missing',candidate='missing2',pad_uuids=['root'])],timeout_s=lease)
    assert not result['ok'] and result['errors']


def witness(index):
    root='root-'+str(index);boundary='junction-'+str(index)
    old=dict(pad_uuid=root,owner='arbitrary-input-'+str(index),pin='4',net='rail-'+str(index),layer=0,
        width_nm=250000,boundary_uuids=[boundary],track_uuids=['old-'+root+'-a','old-'+root+'-b'])
    new=dict(old,track_uuids=['new-'+root+'-a','new-'+root+'-b','new-'+root+'-c'])
    def row(plan):return dict(input_ref=plan['owner'],leg='n',net=plan['net'],ok=True,
        native=dict(departures=[dict(input_contact_paths={root:['shunt-'+str(index),boundary,*reversed(plan['track_uuids']),root]})]))
    return old,new,row(old),row(new)


@pytest.mark.parametrize('count',[1,2,4])
def test_direct_shunt_cut_seed_requires_the_whole_received_run_and_both_absolute_cut_passes(monkeypatch,count):
    rows=[witness(i) for i in range(count)];old=[q[0] for q in rows];new=[q[1] for q in rows]
    for original,replacement,first,last in rows:
        first['native']['departures'][0]['input_contact_paths'][original['pad_uuid']]=[*reversed(original['track_uuids']),original['pad_uuid']]
        last['native']['departures'][0]['input_contact_paths'][original['pad_uuid']]=[*reversed(replacement['track_uuids']),original['pad_uuid']]
    before=dict(inner_departure=dict(details=[q[2] for q in rows]));after=dict(inner_departure=dict(details=[q[3] for q in rows]))
    calls=[]
    def absolute(a,b,net):calls.append((a is b,net));return dict(ok=True,applicable=True,expected_legs=2,checked=2)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',absolute)
    adjusted,paths,qualified,strokes=cohort._rebind_reports(before,after,old,new)
    assert adjusted==before and len(paths)==count and len(calls)==2*count and not strokes
    assert all(q['directly_seeded_complete_owned_run'] for q in paths)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',lambda a,b,net:dict(ok=False,applicable=True,expected_legs=2,checked=2))
    with pytest.raises(ValueError,match='two_absolute'):
        cohort._rebind_reports(before,after,old,new)


@pytest.mark.parametrize('fault',['partial_old','partial_new','reorder','extra_prefix','foreign_tail','foreign_inside','wrong_root','width','face'])
def test_direct_cut_seed_is_not_permission_for_a_partial_or_foreign_path(fault):
    old,new,_,_=witness(0);first=[*reversed(old['track_uuids']),old['pad_uuid']];last=[*reversed(new['track_uuids']),old['pad_uuid']]
    if fault=='partial_old':first.pop(0)
    elif fault=='partial_new':last.pop(0)
    elif fault=='reorder':last[0],last[1]=last[1],last[0]
    elif fault=='extra_prefix':last.insert(0,'unowned-junction')
    elif fault=='foreign_tail':last.append('unowned-land')
    elif fault=='foreign_inside':last.insert(1,'unowned-copper')
    elif fault=='wrong_root':last[-1]='different-input'
    elif fault=='width':new['width_nm']+=1
    else:new['layer']=2
    with pytest.raises(ValueError):cohort._rebind_path(first,last,old,new)


@pytest.mark.parametrize('change',['setup','unknown_node','generator'])
def test_root_settings_comparison_excludes_only_objects_checked_by_exact_delta(change):
    track=['segment',['uuid','"track"'],['width','0.2']]
    first=['kicad_pcb',['generator','"pcbnew"'],['setup',['pad_to_mask_clearance','0']],track]
    later=copy.deepcopy(first);last_track=later[-1]
    assert cohort._settings(first,{'track':track})==cohort._settings(later,{'track':last_track})
    if change=='setup':later[2][1][1]='0.1'
    elif change=='generator':later[1][1]='"foreign-generator"'
    else:later.append(['unrecorded_rule',['waive','true']])
    assert cohort._settings(first,{'track':track})!=cohort._settings(later,{'track':last_track})


@pytest.mark.parametrize('count',[1,2,4,8,16])
def test_pure_multiowner_witness_transform_keeps_literal_after_and_does_not_mutate_reports(monkeypatch,count):
    rows=[witness(i) for i in range(count)];old=[q[0] for q in rows];new=[q[1] for q in rows]
    before=dict(inner_departure=dict(details=[q[2] for q in rows]));after=dict(inner_departure=dict(details=[q[3] for q in rows]))
    frozen=copy.deepcopy((before,after));calls=[]
    def absolute(a,b,net):calls.append((a is b,net));return dict(ok=True,applicable=True,expected_legs=2,checked=2)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',absolute)
    adjusted,paths,qualified,strokes=cohort._rebind_reports(before,after,old,new)
    assert adjusted==before and (before,after)==frozen and len(paths)==count
    assert len(calls)==2*count and len(qualified)==count
    assert all(p['before_path']!=p['after_path'] for p in paths)
    assert all(p['after_path']==rows[i][3]['native']['departures'][0]['input_contact_paths'][p['pad_uuid']] for i,p in enumerate(paths))
    assert not strokes


def departure_example(category,shorter):
    old,new,left,right=witness(0)
    old['points_nm']=[[0,0],[0,2000000],[2000000,2000000]]
    new['points_nm']=[[0,0],[0,1800000],[200000,2000000] if shorter else [0,2000000],[2000000,2000000]]
    def row(plan):return dict(uuid=plan['track_uuids'][-1],departure_end_mm=[v/1e6 for v in plan['points_nm'][-2]],
        width_mm=.25,source_pin='fixed-physical-shunt-pad',layer='F.Cu')
    left['native'][category]=[row(old)];right['native'][category]=[row(new)]
    return old,new,dict(inner_departure=dict(details=[left])),dict(inner_departure=dict(details=[right]))


@pytest.mark.parametrize('category',['departures','non_sense_departures'])
@pytest.mark.parametrize('shorter',[False,True])
def test_departure_metadata_rebind_is_exact_native_segment_not_whole_row_waiver(monkeypatch,category,shorter):
    old,new,before,after=departure_example(category,shorter);frozen=copy.deepcopy((before,after));calls=[]
    def absolute(a,b,net):calls.append((a is b,net));return dict(ok=True,applicable=True,expected_legs=2,checked=2)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',absolute)
    adjusted,_,_,strokes=cohort._rebind_reports(before,after,[old],[new])
    assert adjusted==before and len(strokes)==1 and len(calls)==2
    assert strokes[0]['source_uuid']==old['track_uuids'][-1] and strokes[0]['candidate_uuid']==new['track_uuids'][-1]
    assert (before,after)==frozen
    # An extra field is not normalized away; the outer strict comparator
    # must still see any new guard, exit, width, role or model property.
    after['inner_departure']['details'][0]['native'][category][0]['unknown_authority_waiver']=True
    adjusted,_,_,_=cohort._rebind_reports(before,after,[old],[new])
    assert adjusted!=before and adjusted['inner_departure']['details'][0]['native'][category][0]['unknown_authority_waiver'] is True


@pytest.mark.parametrize('fault',['wrong_uuid','old_coordinate','new_coordinate','net','unknown_before','unknown_after','fixed_entry','before_cut','after_cut'])
def test_departure_segment_rebind_cannot_fabricate_cut_exit_or_native_coordinates(monkeypatch,fault):
    old,new,before,after=departure_example('departures',True)
    if fault=='wrong_uuid':after['inner_departure']['details'][0]['native']['departures'][0]['uuid']='foreign-track'
    elif fault=='old_coordinate':before['inner_departure']['details'][0]['native']['departures'][0]['departure_end_mm'][0]+=.001
    elif fault=='new_coordinate':after['inner_departure']['details'][0]['native']['departures'][0]['departure_end_mm'][0]+=.001
    elif fault=='net':before['inner_departure']['details'][0]['net']='another-net';after['inner_departure']['details'][0]['net']='another-net'
    elif fault=='unknown_before':before['inner_departure']['details'][0]['ok']=None
    elif fault=='unknown_after':after['inner_departure']['details'][0]['ok']=None
    elif fault=='fixed_entry':new['points_nm'][-1][0]+=1
    def absolute(a,b,net):
        bad=fault=='before_cut' and a is b or fault=='after_cut' and a is not b
        return dict(ok=not bad,applicable=True,expected_legs=2,checked=2)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',absolute)
    with pytest.raises(ValueError):cohort._rebind_reports(before,after,[old],[new])


@pytest.mark.parametrize('fault',['shared_old','shared_new','retired_boundary','new_original_id','changed_owner','changed_width','changed_face','changed_fixed_contact'])
def test_cohort_scope_cannot_steal_a_boundary_or_another_input(fault):
    rows=[witness(i) for i in range(2)];old=[q[0] for q in rows];new=[q[1] for q in rows]
    if fault=='shared_old':old[1]['track_uuids'][0]=old[0]['track_uuids'][0]
    elif fault=='shared_new':new[1]['track_uuids'][0]=new[0]['track_uuids'][0]
    elif fault=='retired_boundary':old[1]['boundary_uuids']=[old[0]['track_uuids'][0]];new[1]['boundary_uuids']=list(old[1]['boundary_uuids'])
    elif fault=='new_original_id':new[1]['track_uuids'][0]=old[0]['track_uuids'][0]
    else:
        key={'changed_owner':'owner','changed_width':'width_nm','changed_face':'layer','changed_fixed_contact':'boundary_uuids'}[fault]
        new[1][key]=['different'] if key=='boundary_uuids' else 250001 if key=='width_nm' else 2 if key=='layer' else 'wrong'
    with pytest.raises(ValueError):cohort._disjoint_scope(old,new)


@pytest.mark.parametrize('fault',['before_cut','after_cut','inventory','unknown_departure','foreign_path','changed_context'])
def test_pure_cohort_witness_rebinding_requires_positive_absolute_cuts_and_exact_context(monkeypatch,fault):
    old,new,before_row,after_row=witness(0)
    before=dict(inner_departure=dict(details=[before_row]));after=dict(inner_departure=dict(details=[after_row]));calls=[]
    def absolute(a,b,net):
        calls.append(net);bad=(fault=='before_cut' and a is b or fault=='after_cut' and a is not b)
        return dict(ok=not bad,applicable=True,expected_legs=2,checked=2)
    monkeypatch.setattr(cohort.sense,'admit_changed_net',absolute)
    if fault=='inventory':after['inner_departure']['details']=[]
    elif fault=='unknown_departure':after_row['ok']=None
    elif fault=='foreign_path':after_row['native']['departures'][0]['input_contact_paths'][old['pad_uuid']].insert(3,'foreign')
    elif fault=='changed_context':after_row['native']['departures'][0]['input_contact_paths'][old['pad_uuid']][0]='another-shunt'
    with pytest.raises(ValueError):cohort._rebind_reports(before,after,[old],[new])
