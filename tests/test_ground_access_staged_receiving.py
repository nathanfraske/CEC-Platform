"""Explicit four-constituent Ground receiving never weakens native ownership."""
import copy
import time
from pathlib import Path
from types import SimpleNamespace

import pcbnew
import pytest

import cec_ground_access_completion as operation
from test_ground_access_completion import saved
from test_ground_access_existing_pad_rule import saved as local_saved


NAMES=('Source_identity_and_proposal','independent_saved_delta',
       'actual_saved_partitions_and_local_return','all_Source_returns_craft_and_identity')
LIMITS=(10.,10.,10.,10.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_staged_receiving_keeps_all_four_actual_proofs(tmp_path,quarter,layer):
    source,child,args,proposal=saved(tmp_path,quarter=quarter,layer=layer,mode='vip')
    before=(source.read_bytes(),child.read_bytes())
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert result['ok']and result['complete'],result
    assert tuple(result['stage_timings_s'])==NAMES
    composition=result['bounded_composition']
    assert composition==dict(constituents=list(NAMES),stage_limits_s=list(LIMITS),
        per_constituent_limit_s=10.,aggregate_limit_s=40.)
    assert all(0<=result['stage_timings_s'][name]<10 for name in NAMES)
    assert result['all_source_known_returns']['ok']and result['all_source_known_returns']['complete']
    assert result['every_source_native_partition_identical']
    assert result['saved_return_witness_mm']<=1.5
    assert result['source_unobserved_return_not_an_open_or_infinite_length']
    assert not result['fab_ready']and not result['current_qualified']and not result['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('limits',[list(LIMITS),LIMITS])
def test_existing_pad_rule_is_rederived_in_staged_receiving(tmp_path,limits):
    source,child,args,proposal=local_saved(tmp_path)
    result=operation.receive(source,child,receiving_phase_timeouts_s=limits,**args)
    assert result['ok']and result['complete'],result
    assert result['saved_return_witness_mm']==0 and result['new_holes']==1
    assert result['proposal']==proposal
    assert tuple(result['stage_timings_s'])==NAMES


def test_none_preserves_legacy_default_fields_and_proof(tmp_path):
    source,child,args,proposal=saved(tmp_path,mode='reuse')
    implicit=operation.receive(source,child,**args)
    explicit=operation.receive(source,child,receiving_phase_timeouts_s=None,**args)
    assert implicit['ok']and explicit['ok'],(implicit,explicit)
    assert implicit.keys()==explicit.keys()
    assert 'stage_timings_s'not in implicit and 'bounded_composition'not in implicit
    for field in ('proposal','source_sha256','candidate_sha256','added_native_uuids',
        'saved_return_witness_mm','source_return_witness_mm','every_source_native_partition_identical'):
        assert implicit[field]==explicit[field]


@pytest.mark.parametrize('limits',[False,True,0,10.,{},'',(),(10.,),
    (10.,10.,10.),(10.,10.,10.,10.,10.),(True,10.,10.,10.),(False,10.,10.,10.),
    (0.,10.,10.,10.),(-1.,10.,10.,10.),(float('nan'),10.,10.,10.),
    (float('inf'),10.,10.,10.),('10',10.,10.,10.),(10.001,10.,10.,10.)])
def test_explicit_stage_limits_are_strict_bounded_shape(tmp_path,limits):
    result=operation.receive(tmp_path/'missing',tmp_path/'other',board_hint='synthetic',
        pad_uuid='not-caller-authority',receiving_phase_timeouts_s=limits)
    assert not result['ok']and not result['complete']and result['errors'],result
    assert not any('FileNotFoundError'in e for e in result['errors']),result


def test_stage_limit_cannot_exceed_the_unchanged_caller_limit(tmp_path):
    result=operation.receive(tmp_path/'missing',tmp_path/'other',board_hint='synthetic',
        pad_uuid='x',timeout_s=2.,receiving_phase_timeouts_s=(2.,2.,2.,2.001))
    assert not result['ok']and not result['complete']and result['errors'],result
    assert not any('FileNotFoundError'in e for e in result['errors']),result


@pytest.mark.parametrize('failure',['unknown','failed'])
def test_source_return_failure_or_unknown_cannot_be_promoted(tmp_path,monkeypatch,failure):
    source,child,args,proposal=saved(tmp_path)
    real=operation.returns.receive
    def refusal(*args,**kwargs):
        value=real(*args,**kwargs)
        value.update(ok=False,complete=failure=='failed',errors=['test_actual_return_'+failure])
        if failure=='failed':value['regressed_terminals']=[dict(reason='test_return_regression')]
        return value
    monkeypatch.setattr(operation.returns,'receive',refusal)
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert not result['ok']and not result['complete'],result
    assert result['all_source_known_returns']['ok']is False
    assert result['all_source_known_returns']['errors']==['test_actual_return_'+failure]
    assert any('known_returns'in e for e in result['errors']),result


def test_saved_delta_refusal_stops_before_partition_stage(tmp_path,monkeypatch):
    source,child,args,proposal=saved(tmp_path)
    real=operation.additive.receive;calls=[]
    def refusal(*args,**kwargs):
        calls.append(kwargs.get('timeout_s'))
        value=real(*args,**kwargs);value.update(ok=False,complete=False)
        return value
    monkeypatch.setattr(operation.additive,'receive',refusal)
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert not result['ok']and not result['complete'],result
    assert calls and 0<calls[0]<=10.
    assert any('independent_ground_completion_additive_receiving_refused'in e for e in result['errors'])
    assert NAMES[2]not in result['stage_timings_s']and NAMES[3]not in result['stage_timings_s']


def test_partition_loss_stops_before_return_and_craft_stage(tmp_path,monkeypatch):
    source,child,args,proposal=saved(tmp_path)
    real=operation.ordinary._partition;calls=[]
    def broken(*args,**kwargs):
        value=real(*args,**kwargs);calls.append(1)
        if len(calls)==2:return [*value,{'test-lost-native-partition'}]
        return value
    monkeypatch.setattr(operation.ordinary,'_partition',broken)
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert not result['ok']and not result['complete'],result
    assert any('changed_existing_native_partitions'in e for e in result['errors'])
    assert NAMES[3]not in result['stage_timings_s']


def test_native_craft_regression_remains_a_failure(tmp_path,monkeypatch):
    source,child,args,proposal=saved(tmp_path)
    real=operation.quality.analyze_board;calls=[]
    def worse(*args,**kwargs):
        value=real(*args,**kwargs)
        # Private construction may itself analyze boards; only change the
        # final whole-parent/child craft comparison after the returns proof.
        import inspect
        if any(frame.filename==operation.__file__ and frame.function=='receive'
               and 'preserved'in frame.frame.f_locals for frame in inspect.stack()):
            calls.append(1)
            if len(calls)==2:value=dict(value,issue_count=value['issue_count']+1)
        return value
    monkeypatch.setattr(operation.quality,'analyze_board',worse)
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert not result['ok']and not result['complete'],result
    assert any('worsened_whole_native_route_craft'in e for e in result['errors'])


def test_first_stage_deadline_never_starts_saved_delta(tmp_path,monkeypatch):
    source,child,args,proposal=saved(tmp_path)
    now=time.monotonic;offset=[0.];real=operation.plan;called=[]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:now()+offset[0]))
    def late(*args,**kwargs):
        value=real(*args,**kwargs);offset[0]=11.;return value
    monkeypatch.setattr(operation,'plan',late)
    monkeypatch.setattr(operation.additive,'receive',lambda *a,**k:called.append(1))
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert not result['ok']and not result['complete']and result['errors'],result
    assert not called
    assert NAMES[1]not in result['stage_timings_s']


def test_final_identity_scan_cannot_return_a_late_success(tmp_path,monkeypatch):
    source,child,args,proposal=saved(tmp_path)
    now=time.monotonic;offset=[0.];done=[False]
    real_returns=operation.returns.receive;real_family=operation.force._family
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:now()+offset[0]))
    def returns(*args,**kwargs):
        value=real_returns(*args,**kwargs);done[0]=True;return value
    def late_family(*args,**kwargs):
        value=real_family(*args,**kwargs)
        if done[0]:offset[0]=11.
        return value
    monkeypatch.setattr(operation.returns,'receive',returns)
    monkeypatch.setattr(operation.force,'_family',late_family)
    result=operation.receive(source,child,receiving_phase_timeouts_s=LIMITS,**args)
    assert done[0]and offset[0]==11.
    assert not result['ok']and not result['complete']and result['errors'],result
    assert tuple(result['stage_timings_s'])==NAMES[:3]


@pytest.mark.parametrize('bad_next',[NAMES[0],NAMES[2],NAMES[3],'caller_stage',''])
def test_lease_never_resets_to_an_out_of_order_stage(bad_next):
    lease=operation._GroundReceivingLease(10.,LIMITS)
    with pytest.raises(ValueError):lease.advance(bad_next)


def test_all_four_lease_stages_mandatory():
    lease=operation._GroundReceivingLease(10.,LIMITS)
    with pytest.raises(ValueError):lease.finish()


def test_a_finished_stage_cannot_be_restarted_to_reset_time():
    lease=operation._GroundReceivingLease(10.,LIMITS)
    lease.advance(NAMES[1])
    with pytest.raises(ValueError):lease.advance(NAMES[0])


def test_four_fresh_leases_allow_real_declared_composition_not_one_outer_lease(monkeypatch):
    clock=[0.]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    lease=operation._GroundReceivingLease(10.,LIMITS)
    for index,name in enumerate(NAMES[1:],1):
        clock[0]=8.*index
        assert lease.advance(name)==8.*index+10.
    clock[0]=32.
    lease.finish()
    assert lease.timings==dict.fromkeys(NAMES,8.)


@pytest.mark.parametrize('index',range(4))
def test_each_stage_strict_boundary_cannot_borrow_next_lease(monkeypatch,index):
    clock=[0.]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    lease=operation._GroundReceivingLease(10.,LIMITS)
    for name in NAMES[1:index+1]:lease.advance(name)
    clock[0]=10.
    with pytest.raises(ValueError,match='deadline'):
        if index==3:lease.finish()
        else:lease.advance(NAMES[index+1])
    assert lease.index==index


def test_stage_transition_uses_the_actual_closing_clock_without_unmeasured_gap(monkeypatch):
    values=iter((0.,8.,19.));calls=[]
    def clock():
        value=next(values);calls.append(value);return value
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=clock))
    lease=operation._GroundReceivingLease(10.,LIMITS)
    assert lease.advance(NAMES[1])==18.
    assert calls==[0.,8.]
    with pytest.raises(ValueError,match='deadline'):lease.advance(NAMES[2])


@pytest.mark.parametrize('kind,geometry,options',[
    ('existing_local_ground_entry',{},dict(use_existing_local_pad_rule=True)),
    ('source_local_ground_dogbone',dict(position_nm=[1000000,1000000]),
        dict(dogbone_position_nm=[1000000,1000000],use_existing_local_pad_rule=False)),
    ('source_local_ground_polyline',dict(points_nm=[[0,0],[100000,100000],[200000,100000]]),
        dict(dogbone_points_nm=[[0,0],[100000,100000],[200000,100000]],use_existing_local_pad_rule=True))])
@pytest.mark.parametrize('proof',[dict(ok=True,complete=True),dict(ok=False,complete=False),
    dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_root_dispatch_uses_immediate_parent_and_only_fixed_four_leases(tmp_path,monkeypatch,kind,geometry,options,proof):
    # Call-routing contract only, not synthetic success as hardware admission.
    import root_receive_local_transaction_20261022 as transaction
    original,parent,child=[tmp_path/(name+'.kicad_pcb')for name in ('original','parent','child')]
    for path in (original,parent,child):path.write_text(path.stem)
    row=dict(kind=kind,candidate=str(child),candidate_sha256=transaction.force._hash(child),
        pad_uuid='literal-Source-land',**geometry)
    assert transaction.validate_phases([row])==[kind]
    calls=[]
    def receive(*args,**kwargs):calls.append((args,kwargs));return proof
    monkeypatch.setattr(transaction.ground_entry,'receive',receive)
    if proof.get('ok')is True and proof.get('complete')is True:
        target,result=transaction.receive_phase(original,parent,row,'literal-Source-hint')
        assert target==child and result is proof
    else:
        with pytest.raises(AssertionError):transaction.receive_phase(original,parent,row,'literal-Source-hint')
    assert calls==[((parent,child),dict(board_hint='literal-Source-hint',pad_uuid=row['pad_uuid'],
        timeout_s=10.,receiving_phase_timeouts_s=LIMITS,**options))]


@pytest.mark.parametrize('kind,geometry',[
    ('existing_local_ground_entry',{}),
    ('source_local_ground_dogbone',dict(position_nm=[1000000,1000000])),
    ('source_local_ground_polyline',dict(points_nm=[[0,0],[100000,100000],[200000,100000]]))])
@pytest.mark.parametrize('extra',['receiving_phase_timeouts_s','timeout_s','current_a','allow_unknown_returns','success'])
def test_root_phase_schema_has_no_caller_stage_or_process_authority(kind,geometry,extra):
    import root_receive_local_transaction_20261022 as transaction
    row=dict(kind=kind,candidate='/literal/private/board.kicad_pcb',candidate_sha256='a'*64,
        pad_uuid='literal-Source-land',**geometry)
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([dict(row,**{extra:True})])
