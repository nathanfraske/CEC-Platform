"""Consumer composition controls, not mocked physical qualification.

The production Source/ordinary/quiet/Ground receivers have separate native
tests. Here their call boundaries are mocked, while the unchanged measurement
leg derivation and new strict sequencing/identity composition run for real.
"""
import copy
import os
from pathlib import Path

import pcbnew
import pytest
import root_ordinary_preclear_measurement_phase_20261028 as adapter


def uid(n):
    return f'{n:08x}-1111-4111-8111-111111111111'


def scenario(tmp_path, monkeypatch, *, ground=False, unlocked=False, quiet_count=1, prefix_count=2):
    base = adapter.base
    prefix_names = ['first', 'second', 'third'][:prefix_count]
    quiet_names = ['quiet' if i == 0 else 'quiet'+str(i+1) for i in range(quiet_count)]
    names = ['source', *prefix_names] + (['ground'] if ground else []) + [*quiet_names, 'final']
    paths = {name:tmp_path/(name+'.kicad_pcb') for name in names}
    board = pcbnew.BOARD(); pcbnew.SaveBoard(str(paths['source']), board)
    for path in list(paths.values())[1:]:
        path.write_bytes(paths['source'].read_bytes())
    def row(kind, name, **extra):
        return dict(kind=kind,candidate=str(paths[name]),candidate_sha256=adapter.force._hash(paths[name]),**extra)
    phases = [row(adapter.barrel.KIND,'first',net='/arbitrary-A',retired_track_uuids=[uid(1)],retired_via_uuids=[uid(2)])]
    if prefix_count >= 2:
        phases.append(row('ordinary_reflow' if unlocked else 'ordinary_source_reflow','second',net='/arbitrary-B',
            retired_track_uuids=[uid(3)],**({} if unlocked else dict(allow_locked_track_uuids=[uid(3)]))))
    if prefix_count == 3:
        phases.append(row('ordinary_reflow','third',net='/arbitrary-C',retired_track_uuids=[uid(8)]))
    if ground:
        phases.append(row(adapter.GROUND_KIND,'ground',owner_pad_uuid=uid(4),via_uuid=uid(5)))
    quiet_rows = [row(adapter.MEASUREMENT_KIND,name,pad_uuid=uid(6+20*i),peer_pad_uuid=uid(7+20*i))
        for i,name in enumerate(quiet_names)]
    phases += [*quiet_rows,row('print_context','final',proposal=str(tmp_path/'print.json'))]
    actual_quiet_rows = copy.deepcopy(quiet_rows)
    actual_legs = [('RENAMED_INPUT'+('_'+str(i+1) if i else ''),'p',
        '/actual-quiet'+('-'+str(i+1) if i else '')) for i in range(quiet_count)]
    state = dict(calls=[],fault=None,fault_quiet_index=0)
    epoch = {'synthetic-source.py':'a'*64}
    monkeypatch.setattr(adapter.force,'_code_identity',lambda:copy.deepcopy(epoch))
    monkeypatch.setattr(adapter.force,'_family',lambda p,h:{str(Path(p).resolve()):adapter.force._hash(p)})
    monkeypatch.setattr(base,'annotation_dependencies',lambda:{})
    monkeypatch.setattr(base.stage,'matched_instance',lambda instance,path:instance)
    def raw(path):
        family=adapter.force._family(path,'renamed-context')
        return dict(complete=True,identity_stable=True,board_hint='renamed-context',source=str(path),
            source_family_before=family,source_family_after=copy.deepcopy(family),
            code_before=copy.deepcopy(epoch),code_after=copy.deepcopy(epoch))
    evidence=[raw(paths['source']),raw(paths['final'])]
    def proof(parent, phase):
        state['calls'].append(('phase',phase['kind'],str(parent),phase['candidate']))
        q=dict(ok=True,complete=True)
        if state['fault']=='prefix_refused' and phase['kind'] in adapter.PREFIX_KINDS:
            q['complete']=False
        if phase['kind']==adapter.MEASUREMENT_KIND:
            index = next(i for i,r in enumerate(actual_quiet_rows) if r['candidate']==phase['candidate'])
            previous = paths[quiet_names[index-1]] if index else paths['ground' if ground else prefix_names[-1]]
            if Path(parent)!=previous:
                raise ValueError('public_quiet_actual_saved_parent_refused')
            bad_phase = index == state['fault_quiet_index']
            pad = uid(99) if state['fault']=='wrong_pad' and bad_phase else actual_quiet_rows[index]['pad_uuid']
            peer = uid(98) if state['fault']=='wrong_peer' and bad_phase else actual_quiet_rows[index]['peer_pad_uuid']
            ref,leg,net = actual_legs[0 if state['fault']=='duplicate_actual_leg' else index]
            q.update(exact_source_shunt_and_original_quiet_tree_retained=True,
                independently_compiled_source_scope=dict(complete=True,pad_uuid=pad,
                    peer_pad_uuid=peer,
                    source_request=dict(complete=True,pad_uuid=pad,request=dict(demand=dict(
                        pad_uuid=pad,net=net,source_segment=dict(
                            start=dict(ref=ref),leg=leg,net=net))))))
            if state['fault']=='quiet_refused' and bad_phase:
                raise ValueError('real_quiet_owner_refused')
        return q
    def receive(original,parent,phase,hint,**kwargs):
        return Path(phase['candidate']),proof(parent,phase)
    monkeypatch.setattr(base,'receive_phase',receive)
    monkeypatch.setattr(adapter.barrel,'receive_phase',lambda original,parent,phase,hint,**kw:proof(parent,phase))
    def chain(source,candidate,**kwargs):
        state['calls'].append(('cut_chain',str(source),str(candidate),copy.deepcopy(kwargs)))
        assert kwargs['timeout_s']==10. and kwargs['per_phase_leases'] is True
        return dict(ok=state['fault']!='chain_refused',complete=True)
    monkeypatch.setattr(adapter.cut_chain,'receive',chain)
    def current(source,candidate,**kwargs):
        state['calls'].append(('current',str(source),str(candidate),kwargs))
        bad=(state['fault']=='current_refused' or
            state['fault']=='ground_current_refused' and Path(candidate)==paths.get('ground'))
        return dict(ok=not bad,complete=True,source_candidate_and_code_unchanged=True)
    monkeypatch.setattr(adapter.current,'receive',current)
    def replay(path,**kwargs):
        state['calls'].append(('raw',str(path),kwargs));assert kwargs['timeout_s']==10.
        q=raw(path)
        if state['fault']=='raw_incomplete':q['complete']=False
        if state['fault']=='raw_wrong_source':q['source']='/unreceived/source'
        return q
    monkeypatch.setattr(adapter.sense,'replay',replay)
    def ground_receive(source,candidate,**kwargs):
        state['calls'].append(('Ground',str(source),str(candidate),kwargs))
        assert kwargs==dict(owner_pad_uuid=uid(4),via_uuid=uid(5),board_hint='renamed-context',timeout_s=10.)
        return dict(ok=state['fault']!='ground_refused',complete=True)
    monkeypatch.setattr(adapter.functional_ground,'receive',ground_receive)
    def strict(before,after,nets,transforms):
        state['calls'].append(('strict',before['source'],after['source']))
        bad=(state['fault']=='strict_refused' or
            state['fault']=='ground_strict_refused' and after['source']==str(paths.get('ground')))
        return dict(same_evidence=not bad,comparison_complete=True)
    monkeypatch.setattr(base,'strict_contact_transition',strict)
    def compare(before,after,legs,nets,transforms):
        state['calls'].append(('absolute',before['source'],after['source'],copy.deepcopy(legs)))
        assert legs==actual_legs
        if state['fault']=='raw_mutated':after['forged']=True
        return dict(same_evidence=state['fault']!='absolute_refused',comparison_complete=True,
            release_authority=False,full_kelvin_qualification=False)
    monkeypatch.setattr(base.received_contact,'_compare_input_repairs',compare)
    def run():
        with adapter.installed():
            return base.isolated_measurement_contact_transition(paths['source'],paths['final'],phases,evidence,
                board_hint='renamed-context')
    return paths,phases,evidence,state,run


@pytest.mark.parametrize('ground',[False,True])
@pytest.mark.parametrize('unlocked',[False,True])
def test_fresh_prefix_chain_then_actual_independent_suffix(tmp_path,monkeypatch,ground,unlocked):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=ground,unlocked=unlocked)
    saved=copy.deepcopy(evidence);result=run()
    assert result['same_evidence'] is True and result['comparison_complete'] is True
    assert evidence==saved and result['measurement_repair_authority_not_applied_to_prefix'] is True
    assert not result['current_qualified'] and not result['full_kelvin_qualification']
    assert not result['release_authority'] and not result['inherited_debt_qualified']
    chain=next(c for c in state['calls'] if c[0]=='cut_chain')
    assert chain[1:3]==(str(paths['source']),str(paths['second']))
    cuts=chain[3]['phases'];assert len(cuts)==2
    assert cuts[0]['kind']=='ordinary_exclusive_via_path' and cuts[0]['allow_locked_via_uuids']==[]
    assert cuts[1]['allow_locked_track_uuids']==([] if unlocked else [uid(3)])
    absolute=next(c for c in state['calls']if c[0]=='absolute')
    assert absolute[1:3]==(str(paths['ground' if ground else 'second']),str(paths['final']))
    strict=[c for c in state['calls']if c[0]=='strict']
    assert strict[0][1:]==(str(paths['source']),str(paths['second']))
    if ground:assert strict[1][1:]==(str(paths['second']),str(paths['ground']))


@pytest.mark.parametrize('fault',['prefix_refused','chain_refused','current_refused','raw_incomplete',
    'raw_wrong_source','strict_refused','quiet_refused','wrong_pad','absolute_refused','raw_mutated'])
def test_refused_or_unknown_boundary_never_becomes_physical_pass(tmp_path,monkeypatch,fault):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch)
    state['fault']=fault;result=run()
    assert result['same_evidence'] is False and result['comparison_complete'] is False
    assert result['errors']
    if fault in {'prefix_refused','chain_refused','current_refused','raw_incomplete','raw_wrong_source','strict_refused'}:
        assert not any(c[0]=='absolute'for c in state['calls'])


@pytest.mark.parametrize('fault',['ground_refused','ground_current_refused','ground_strict_refused'])
def test_functional_ground_has_its_own_strict_boundary_before_quiet(tmp_path,monkeypatch,fault):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=True)
    state['fault']=fault;result=run()
    assert not result['same_evidence'] and result['errors']
    assert not any(c[0]=='absolute'for c in state['calls'])


@pytest.mark.parametrize('fault',['typo','extra_override','missing_quiet','missing_print','quiet_then_ordinary',
    'bad_sha','changed_sha','same_path','hardlink','extra_pad','extra_current','raw_Source_unknown'])
def test_schema_or_saved_identity_mismatch_refuses_before_physical_claim(tmp_path,monkeypatch,fault):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch)
    if fault=='typo':phases[0]['kind']='ordinary_source_barrell_chain_reflow'
    elif fault=='extra_override':phases[0]['timeout_s']=20
    elif fault=='missing_quiet':phases.pop(-2)
    elif fault=='missing_print':phases.pop()
    elif fault=='quiet_then_ordinary':phases[1],phases[2]=phases[2],phases[1]
    elif fault=='bad_sha':phases[1]['candidate_sha256']='bad'
    elif fault=='changed_sha':phases[1]['candidate_sha256']='f'*64
    elif fault=='same_path':phases[1]['candidate']=phases[0]['candidate']
    elif fault=='hardlink':
        paths['second'].unlink();os.link(paths['first'],paths['second'])
    elif fault=='extra_pad':phases[-2]['pad_uuids']=[uid(99)]
    elif fault=='extra_current':phases[-2]['current_amps']=.01
    elif fault=='raw_Source_unknown':evidence[0]['complete']=False
    if fault=='missing_quiet':
        # Existing no-measurement dispatch returns no contact-repair grant.
        # It is not reclassified as this new composite or a successful proof.
        assert run() is None
    else:
        with pytest.raises((ValueError,KeyError)):
            run()
    assert not any(c[0]=='absolute'for c in state['calls'])


def test_missing_saved_preclear_cannot_use_later_quiet_repair_to_launder_it(tmp_path,monkeypatch):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch)
    phases.pop(1)
    result=run()
    assert result['same_evidence'] is False and any('public_quiet_actual_saved_parent_refused'in e for e in result['errors'])


@pytest.mark.parametrize('field,value',[('owner_pad_uuid','unknown'),('via_uuid','unknown'),
    ('via_uuid',uid(4)),('pad_uuids',[uid(4)]),('diameter_nm',900000),
    ('allow_ground_fill',True),('current_amps',1.),('callback','anything'),('timeout_s',10.)])
def test_ground_schema_is_exact_two_identities_not_geometry_or_authority(tmp_path,monkeypatch,field,value):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=True)
    phases[2][field]=value
    with pytest.raises(ValueError):run()
    assert not state['calls']


@pytest.mark.parametrize('fault',['missing_ground','ground_after_quiet','four_preclears','duplicate_ground'])
def test_finite_ground_composition_order_and_count(tmp_path,monkeypatch,fault):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=True)
    if fault=='missing_ground':phases.pop(2)
    elif fault=='ground_after_quiet':phases[2],phases[3]=phases[3],phases[2]
    elif fault=='duplicate_ground':phases.insert(2,copy.deepcopy(phases[2]))
    else:
        phases[1:1]=[copy.deepcopy(phases[1]),copy.deepcopy(phases[1])]
    if fault=='missing_ground':
        assert run()['same_evidence'] is False
    else:
        with pytest.raises(ValueError):run()


def test_context_restores_all_dispatch_and_dependency_functions_on_exception():
    base=adapter.base
    prior=(base.validate_phases,base.receive_phase,base.annotation_dependencies,
        base.isolated_measurement_contact_transition,copy.deepcopy(base.KINDS))
    with pytest.raises(RuntimeError):
        with adapter.installed():
            dependencies=base.annotation_dependencies()
            for module in (adapter,adapter.barrel,adapter.functional_ground,adapter.cut_chain):
                path=str(Path(module.__file__).resolve())
                assert dependencies[path]==adapter.force._hash(path)
            raise RuntimeError('scope exits')
    assert prior==(base.validate_phases,base.receive_phase,base.annotation_dependencies,
        base.isolated_measurement_contact_transition,base.KINDS)


def test_existing_nonmatching_measurement_path_remains_the_original_delegate(monkeypatch):
    marker=object();seen=[]
    def prior(*args,**kwargs):seen.append((args,kwargs));return marker
    monkeypatch.setattr(adapter.base,'isolated_measurement_contact_transition',prior)
    phases=[dict(kind='ordinary_join',net='/test',candidate='/not-read',candidate_sha256='a'*64)]
    raw=[{},{}]
    with adapter.installed():
        assert adapter.base.isolated_measurement_contact_transition('source','child',phases,raw,board_hint='opaque')is marker
    assert seen[0][0][2]is phases and seen[0][0][3]is raw


def test_three_distinct_preclears_are_bounded_only_with_exact_ground_suffix(tmp_path,monkeypatch):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=True)
    third=tmp_path/'third.kicad_pcb';third.write_bytes(paths['source'].read_bytes())
    phases.insert(2,dict(kind='ordinary_reflow',candidate=str(third),
        candidate_sha256=adapter.force._hash(third),net='/arbitrary-C',retired_track_uuids=[uid(8)]))
    with adapter.installed():
        prefix,ground,suffix=adapter._sequence(phases)
        assert len(prefix)==3 and ground['kind']==adapter.GROUND_KIND and len(suffix)==2
        del phases[3]
        with pytest.raises(ValueError):adapter._sequence(phases)


@pytest.mark.parametrize('changed',['family','epoch','dependencies'])
def test_live_end_binding_refuses_drift_even_after_positive_delegates(tmp_path,monkeypatch,changed):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch)
    original=adapter.base.received_contact._compare_input_repairs
    def drift(*args,**kwargs):
        value=original(*args,**kwargs)
        if changed=='family':paths['first'].write_bytes(paths['first'].read_bytes()+b'\n')
        elif changed=='epoch':monkeypatch.setattr(adapter.force,'_code_identity',lambda:{'changed.py':'b'*64})
        else:monkeypatch.setattr(adapter.base,'annotation_dependencies',lambda:{'changed.py':'b'*64})
        return value
    monkeypatch.setattr(adapter.base.received_contact,'_compare_input_repairs',drift)
    result=run()
    assert not result['same_evidence'] and not result['comparison_complete']
    assert 'preclear_measurement_raw_Source_family_or_dependency_changed'in result['errors']


@pytest.mark.parametrize('accepted',[False,True])
def test_ground_dispatch_calls_only_unchanged_public_owner_at_ten_seconds(tmp_path,monkeypatch,accepted):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=True)
    row=phases[2]
    if not accepted:state['fault']='ground_refused'
    with adapter.installed():
        if accepted:
            path,proof=adapter.base.receive_phase(paths['source'],paths['second'],row,'renamed-context')
            assert path==paths['ground']and proof['ok'] is True
        else:
            with pytest.raises(ValueError):
                adapter.base.receive_phase(paths['source'],paths['second'],row,'renamed-context')
    assert len([c for c in state['calls']if c[0]=='Ground'])==1


@pytest.mark.parametrize('prefix_count,ground,quiet_count',[
    (1,False,1),(1,False,2),(1,False,3),
    (2,False,1),(2,False,2),(2,False,3),
    (2,True,1),(2,True,2),(3,True,1)])
def test_finite_distinct_quiet_suffix_uses_each_actual_saved_parent_and_absolute_cohort(
        tmp_path,monkeypatch,prefix_count,ground,quiet_count):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,ground=ground,
        quiet_count=quiet_count,prefix_count=prefix_count)
    saved=copy.deepcopy(evidence);original_phase=adapter.base.receive_phase
    result=run()
    assert result['same_evidence'] is True and result['comparison_complete'] is True
    assert adapter.base.receive_phase is original_phase
    assert evidence==saved
    assert len(phases)<=adapter.base.MAX_LOCAL_PHASES==6
    assert result['actual_measurement_suffix_count']==quiet_count
    assert result['independent_constituent_limit_s']==10.
    suffix_limit=10.*(quiet_count+3)
    assert result['independent_suffix_limit_s']==suffix_limit
    assert result['aggregate_limit_s']==10.*(2*prefix_count+4+4*ground)+suffix_limit
    if quiet_count==1:
        assert suffix_limit==40.  # Exact former single-input composition budget.
        assert result['aggregate_limit_s']==10.*(2*prefix_count+8+4*ground)
    suffix=phases[-quiet_count-1:]
    phase_calls=[c for c in state['calls'] if c[0]=='phase'
        and c[1] in (adapter.MEASUREMENT_KIND,adapter.PRINT_KIND)]
    assert len(phase_calls)==len(suffix)
    parent=result['actual_measurement_parent']
    for i,(call,row) in enumerate(zip(phase_calls,suffix)):
        assert call[2:]==(parent,row['candidate'])
        parent=row['candidate']
        assert 'typed_suffix_'+str(i)+'_'+row['kind'] in result['timings_s']
    remainder=result['independently_received_measurement_suffix']
    legs=remainder['actual_Source_derived_repair_legs']
    assert len(legs)==quiet_count and len({tuple(leg) for leg in legs})==quiet_count
    absolute=[c for c in state['calls'] if c[0]=='absolute']
    assert len(absolute)==1 and [list(leg) for leg in absolute[0][3]]==legs
    assert absolute[0][1:3]==(result['actual_measurement_parent'],str(paths['final']))
    assert not result['current_qualified'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('fault',[
    'four_quiet','seven_total','duplicate_input','isolated_kind','late_ordinary',
    'late_ground','middle_print','three_prefix_without_ground','single_prefix_with_ground'])
def test_multiquiet_scope_caps_and_order_do_not_widen_other_owners(tmp_path,monkeypatch,fault):
    options=dict(quiet_count=2)
    if fault=='four_quiet':options.update(quiet_count=4,prefix_count=1)
    elif fault=='seven_total':options.update(quiet_count=3,ground=True)
    elif fault=='three_prefix_without_ground':options.update(quiet_count=1,prefix_count=3)
    elif fault=='single_prefix_with_ground':options.update(quiet_count=1,prefix_count=1,ground=True)
    elif fault=='late_ground':options['ground']=True
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,**options)
    quiet=[i for i,row in enumerate(phases) if row['kind']==adapter.MEASUREMENT_KIND]
    if fault=='duplicate_input':phases[quiet[1]]['pad_uuid']=phases[quiet[0]]['pad_uuid']
    elif fault=='isolated_kind':
        phases[quiet[1]]['kind']='isolated_measurement_join'
        del phases[quiet[1]]['peer_pad_uuid']
    elif fault=='late_ordinary':phases[1],phases[quiet[0]]=phases[quiet[0]],phases[1]
    elif fault=='late_ground':phases[2],phases[quiet[0]]=phases[quiet[0]],phases[2]
    elif fault=='middle_print':phases[-1],phases[quiet[1]]=phases[quiet[1]],phases[-1]
    with pytest.raises(ValueError):run()
    assert not state['calls']


@pytest.mark.parametrize('fault',['wrong_pad','wrong_peer','quiet_refused','duplicate_actual_leg'])
@pytest.mark.parametrize('fault_quiet_index',[1,2])
def test_each_later_quiet_input_needs_its_own_fresh_source_identity(
        tmp_path,monkeypatch,fault,fault_quiet_index):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    state.update(fault=fault,fault_quiet_index=fault_quiet_index)
    original_phase=adapter.base.receive_phase
    result=run()
    assert not result['same_evidence'] and not result['comparison_complete']
    assert result['errors'] and not any(c[0]=='absolute' for c in state['calls'])
    assert adapter.base.receive_phase is original_phase
    if fault=='duplicate_actual_leg':
        assert any('duplicate_actual_measurement_contact_leg' in error for error in result['errors'])


@pytest.mark.parametrize('fault',['prefix_refused','chain_refused','current_refused',
    'raw_incomplete','raw_wrong_source','strict_refused','raw_mutated','absolute_refused'])
def test_multiple_quiet_inputs_do_not_mask_prefix_unknown_or_mutate_raw_packets(tmp_path,monkeypatch,fault):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    state['fault']=fault;result=run()
    assert not result['same_evidence'] and not result['comparison_complete']
    assert result['errors']
    if fault not in {'raw_mutated','absolute_refused'}:
        assert not any(c[0]=='absolute' for c in state['calls'])


@pytest.mark.parametrize('endpoint,field,value',[
    (0,'complete',False),(1,'complete',False),(0,'identity_stable',False),
    (1,'source','/different/saved-board'),(1,'code_after',{'changed.py':'f'*64}),
    (0,'source_family_before',{}),(1,'source_family_after',{})])
def test_multiquiet_raw_endpoint_identity_is_required_before_any_receiver(
        tmp_path,monkeypatch,endpoint,field,value):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    evidence[endpoint][field]=value
    with pytest.raises(ValueError,match='fresh_exact_saved_raw_sense_boundary_required'):run()
    assert not state['calls']


@pytest.mark.parametrize('kind,index',[(adapter.MEASUREMENT_KIND,1),(adapter.PRINT_KIND,3)])
@pytest.mark.parametrize('elapsed,accepted',[(9.999,True),(10.,True),(10.001,False)])
def test_each_actual_suffix_receiver_keeps_the_ten_second_lease(
        tmp_path,monkeypatch,kind,index,elapsed,accepted):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    original_phase=adapter.base.receive_phase;clock=[100.]
    monkeypatch.setattr(adapter.time,'monotonic',lambda:clock[0])
    target=phases[-4+index]
    assert target['kind']==kind
    def timed(*args,**kwargs):
        result=original_phase(*args,**kwargs)
        if args[2] is target:clock[0]+=elapsed
        return result
    monkeypatch.setattr(adapter.base,'receive_phase',timed)
    result=run()
    assert result['same_evidence'] is accepted and result['comparison_complete'] is accepted
    assert adapter.base.receive_phase is timed
    if not accepted:
        assert any('bounded_preclear_measurement_constituent_deadline:typed_suffix_'+str(index)+'_'+kind
            in error for error in result['errors'])
        assert not any(c[0]=='absolute' for c in state['calls'])


@pytest.mark.parametrize('quiet_count',[1,2,3])
@pytest.mark.parametrize('overrun',[False,True])
def test_suffix_aggregate_is_finite_and_derived_only_from_actual_count(
        tmp_path,monkeypatch,quiet_count,overrun):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=quiet_count)
    original_compare=adapter.base.received_contact._compare_input_repairs;clock=[100.]
    monkeypatch.setattr(adapter.time,'monotonic',lambda:clock[0])
    actual_limit=10.*(quiet_count+3)
    def timed_compare(*args,**kwargs):
        result=original_compare(*args,**kwargs)
        clock[0]+=actual_limit+(.001 if overrun else 0.)
        return result
    monkeypatch.setattr(adapter.base.received_contact,'_compare_input_repairs',timed_compare)
    result=run()
    assert result['independent_suffix_limit_s']==actual_limit
    assert result['same_evidence'] is (not overrun)
    if overrun:
        assert any('bounded_preclear_measurement_constituent_deadline:independent_measurement_suffix'
            in error for error in result['errors'])


def test_suffix_dispatch_cannot_skip_actual_saved_receivers_with_a_positive_summary(tmp_path,monkeypatch):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    monkeypatch.setattr(adapter.base,'isolated_measurement_contact_transition',
        lambda *a,**kw:dict(same_evidence=True,comparison_complete=True))
    result=run()
    assert not result['same_evidence'] and not result['comparison_complete']
    assert any('complete_actual_quiet_suffix_saved_receiving_required' in error for error in result['errors'])


def test_multiquiet_keeps_exact_current_source_family_and_dependency_end_binding(tmp_path,monkeypatch):
    paths,phases,evidence,state,run=scenario(tmp_path,monkeypatch,quiet_count=3)
    original_compare=adapter.base.received_contact._compare_input_repairs
    def drift(*args,**kwargs):
        result=original_compare(*args,**kwargs)
        paths['quiet2'].write_bytes(paths['quiet2'].read_bytes()+b'\n')
        return result
    monkeypatch.setattr(adapter.base.received_contact,'_compare_input_repairs',drift)
    result=run()
    assert not result['same_evidence'] and not result['comparison_complete']
    assert 'preclear_measurement_raw_Source_family_or_dependency_changed' in result['errors']
