"""Strict Source Ground requests, not role/budget or worker-receipt permits."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_source_divider_ground_span as divider
import root_receive_local_transaction_20261022 as transaction
from test_source_divider_ground_span import received_fixture


def phase(kind='source_divider_ground_span',**updates):
    request=(dict(pad_uuid='actual-Source-ground-pad')if kind=='existing_local_ground_entry'else
        dict(ground_pad_uuid='actual-Source-divider-ground-pad',retired_track_uuids=['actual-Source-track'],
            points_nm=[[0,0],[1000000,1000000]]))
    row=dict(kind=kind,candidate='/saved/actual-child.kicad_pcb',candidate_sha256='a'*64,**request)
    row.update(updates);return row


@pytest.mark.parametrize('kind',['existing_local_ground_entry','source_divider_ground_span'])
def test_only_actual_Source_request_fields_are_in_strict_Ground_schema(kind):
    row=phase(kind);assert transaction.validate_phases([row])==[kind]


@pytest.mark.parametrize('kind',['existing_local_ground_entry','source_divider_ground_span'])
@pytest.mark.parametrize('key,value',[('role','ordinary'),('net','GND'),('current_a',.001),
    ('current_budget',{'amps':.001}),('width_nm',100000),('clearance_mm',0),
    ('timeout_s',30),('reach_mm',10),('proposal','/saved/worker-plan.json'),
    ('use_existing_local_pad_rule',True),('prefer_source_track_root',True),
    ('dogbone_position_nm',[0,0]),('receipt',{'ok':True,'complete':True}),
    ('options',{}),('external_success',True)])
def test_Source_role_net_width_budget_timeout_proposal_and_mode_flags_are_forbidden(kind,key,value):
    row=phase(kind);row[key]=value
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema'):
        transaction.validate_phases([row])


@pytest.mark.parametrize('kind',['existing_local_ground_entry','source_divider_ground_span'])
@pytest.mark.parametrize('identity',['',None,True,[],{}])
def test_Source_pad_identity_is_explicit_nonempty_and_scalar(kind,identity):
    row=phase(kind);row['pad_uuid'if kind=='existing_local_ground_entry'else'ground_pad_uuid']=identity
    with pytest.raises(ValueError):transaction.validate_phases([row])


@pytest.mark.parametrize('changes',[
    dict(retired_track_uuids=[]),dict(retired_track_uuids=['same','same']),
    dict(retired_track_uuids=list(map(str,range(9)))),dict(retired_track_uuids=['track',True]),
    dict(points_nm=[]),dict(points_nm=[[0,0]]),dict(points_nm=[[0,0]]*17),
    dict(points_nm=((0,0),(1,1))),dict(points_nm=[[0,0,0],[1,1]]),
    dict(points_nm=[[0,0],[1.0,1]]),dict(points_nm=[[0,0],[True,1]]),
    dict(points_nm=[[0,0],[2000000001,1]]),dict(points_nm=[[0,0],[float('nan'),1]])])
def test_divider_request_is_bounded_unique_Source_cut_and_integer_geometry(changes):
    with pytest.raises(ValueError):transaction.validate_phases([phase(**changes)])


@pytest.mark.parametrize('kind',['existing_local_ground_entry','source_divider_ground_span'])
def test_repeated_Ground_operator_print_order_and_explicit_phase_cap_are_checked(kind):
    row=phase(kind)
    with pytest.raises(ValueError,match='repeated_local_operator'):
        transaction.validate_phases([row,dict(row)])
    printed=dict(kind='print_context',candidate='/saved/print.kicad_pcb',candidate_sha256='b'*64,proposal='/saved/print.json')
    with pytest.raises(ValueError,match='typed_print_context_must_be_last'):
        transaction.validate_phases([printed,row])
    joins=[dict(kind='ordinary_join',net='/unrelated_'+str(i),candidate='/saved/'+str(i),candidate_sha256='c'*64)for i in range(transaction.MAX_LOCAL_PHASES)]
    assert transaction.validate_phases([row,*joins[:3]])==[kind]+['ordinary_join']*3
    with pytest.raises(ValueError,match='finite_one_to_six'):
        transaction.validate_phases([row,*joins])


def test_distinct_typed_Source_Ground_operations_and_literal_join_fit_one_finite_transaction():
    rows=[phase('existing_local_ground_entry'),phase(),
        dict(kind='ordinary_join',net='/literal_control',candidate='/saved/control',candidate_sha256='c'*64),
        dict(kind='print_context',candidate='/saved/print',candidate_sha256='d'*64,proposal='/saved/print.json')]
    assert transaction.validate_phases(rows)==[r['kind']for r in rows]


@pytest.mark.parametrize('accepted',[True,False])
def test_existing_local_Ground_dispatch_fixes_literal_Source_rule_mode_and_ten_second_lease(tmp_path,monkeypatch,accepted):
    # Dispatcher wiring only. A fabricated text file never establishes an
    # actual local rule or native success; the public native module owns it.
    original=tmp_path/'original';parent=tmp_path/'immediate-parent';child=tmp_path/'saved-child'
    for path in(original,parent,child):path.write_text(path.name)
    row=phase('existing_local_ground_entry',candidate=str(child),candidate_sha256=force._hash(child));calls=[]
    def receive(source,candidate,**options):
        calls.append((source,candidate,options));return dict(ok=accepted,complete=True)
    monkeypatch.setattr(transaction.ground_entry,'receive',receive)
    if accepted:assert transaction.receive_phase(original,parent,row,'bound-Source-design')[0]==child
    else:
        with pytest.raises(AssertionError):transaction.receive_phase(original,parent,row,'bound-Source-design')
    assert calls==[(parent,child,dict(board_hint='bound-Source-design',pad_uuid=row['pad_uuid'],
        use_existing_local_pad_rule=True,timeout_s=10.))]


def saved_divider_phase(f):
    return phase(candidate=str(f['candidate']),candidate_sha256=force._hash(f['candidate']),
        ground_pad_uuid=force._uid(f['ground']),retired_track_uuids=[force._uid(t)for t in f['retired']],
        points_nm=copy.deepcopy(f['points']))


def test_saved_divider_transaction_recompiles_Source_owner_and_actual_geometry_not_worker_receipt(tmp_path,monkeypatch):
    # The upstream fixture explicitly stubs physical guard dependencies, not
    # this public receiver. Actual Source symbols/export, selected resistors,
    # owner, full-class path, opaque saved replay and contact kernels run.
    # This compositional test is not manufacturing or whole-suite evidence.
    f=received_fixture(tmp_path,monkeypatch);row=saved_divider_phase(f)
    assert transaction.validate_phases([row])==['source_divider_ground_span']
    before=[p.read_bytes()for p in(f['source'],f['candidate'],f['root'])]
    original=divider.receive;calls=[]
    def fresh(source,candidate,**options):
        calls.append((source,candidate,options));return original(source,candidate,**options)
    monkeypatch.setattr(divider,'receive',fresh)
    child,result=transaction.receive_phase(tmp_path/'not-the-parent',f['source'],row,str(f['root']))
    assert child==f['candidate'].resolve()and result['ok']and result['complete']and result['errors']==[]
    assert calls==[(f['source'],f['candidate'].resolve(),dict(board_hint=str(f['root']),
        ground_pad_uuid=row['ground_pad_uuid'],retired_track_uuids=row['retired_track_uuids'],points_nm=row['points_nm'],timeout_s=10.))]
    assert len(f['exports'])==1 and f['calls']==['partition','additive','partition','returns','field','field']
    assert result['source_owner']['ground_pad_uuid']==row['ground_pad_uuid']
    assert result['source_owner']['lower_resistor_uuid']==force._uid(f['lower'])
    assert result['source_owner']['manufacturer_monitor']['function']=='OV1'
    assert result['literal_source_cut_projection']['independent_full_native_inventory_equal']
    assert result['opaque_source_preservation']['all_retained_source_nodes_and_root_records_opaque_exact']
    assert not result['current_qualified']and not result['routing_admitted']and not result['release_authority']
    assert before==[p.read_bytes()for p in(f['source'],f['candidate'],f['root'])]


@pytest.mark.parametrize('fault',['Source_MPN','Source_monitor_pin','saved_width','candidate_rule','partition','incomplete_additive'])
def test_prior_true_divider_receipt_cannot_authorize_mutated_Source_or_saved_child(tmp_path,monkeypatch,fault):
    actual_additive=divider.additive.receive
    f=received_fixture(tmp_path,monkeypatch);row=saved_divider_phase(f)
    _,prior=transaction.receive_phase(f['source'],f['source'],row,str(f['root']))
    assert prior['ok']and prior['complete']
    if fault=='Source_MPN':f['root'].write_text(f['root'].read_text().replace('0402WGF1002TCE','0402WGF9999TCE'))
    elif fault=='Source_monitor_pin':f['root'].write_text(f['root'].read_text().replace('(name "OV1")','(name "ILIM")'))
    elif fault=='saved_width':
        text=f['candidate'].read_text();f['candidate'].write_text(text.replace('(width 0.5)','(width 0.499999)',1))
    elif fault=='candidate_rule':
        f['candidate'].with_suffix('.kicad_dru').write_text('(version 1)\n(rule "unsafe" (constraint clearance (min 0mm)))\n')
        # Sidecars belong to the actual additive guard, not the explicitly
        # stubbed positive composition fixture. Exercise that real guard.
        monkeypatch.setattr(divider.additive,'receive',actual_additive)
    elif fault=='partition':monkeypatch.setattr(divider.partitions,'compare',lambda *a,**kw:dict(available=True,preserved=False))
    else:monkeypatch.setattr(divider.additive,'receive',lambda *a,**kw:dict(ok=True,complete=False))
    # Updating the saved hash is necessary but never sufficient authority.
    row=saved_divider_phase(f)
    with pytest.raises(AssertionError):transaction.receive_phase(f['source'],f['source'],row,str(f['root']))


@pytest.mark.parametrize('kind',['existing_local_ground_entry','source_divider_ground_span'])
def test_stale_saved_hash_refuses_before_any_public_Ground_receiver(tmp_path,monkeypatch,kind):
    child=tmp_path/'saved-child';child.write_text('actual saved boundary');row=phase(kind,candidate=str(child),candidate_sha256='0'*64)
    target=transaction.ground_entry if kind=='existing_local_ground_entry'else transaction.divider_ground
    monkeypatch.setattr(target,'receive',lambda *a,**kw:pytest.fail('stale hash reached public Source receiver'))
    with pytest.raises(AssertionError):transaction.receive_phase(tmp_path/'source',tmp_path/'parent',row,'bound')
