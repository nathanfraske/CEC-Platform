"""Composition/schema tests; individual native annotation physics stay separate.

Dispatch spies below are explicitly NOT hardware grades. The corresponding
public receivers have their own native synthetic and whole-board tests.
"""
import copy,json
from types import SimpleNamespace
from pathlib import Path
import pytest
import cec_saved_reference_cleanup_chain as op


def fixture(tmp_path,kinds=('root_reference_seat','reference_map','reference_fields')):
    paths=[tmp_path/(str(i)+'.kicad_pcb')for i in range(len(kinds)+1)]
    for i,p in enumerate(paths):p.write_text('dispatch-only-native-placeholder-'+str(i))
    def ref(p):return dict(path=str(p.resolve()),sha256=op.force._hash(p))
    steps=[]
    for i,kind in enumerate(kinds):
        q=dict(board_hint='synthetic')
        if kind=='root_reference_seat':q.update(source=str(paths[i]),source_sha256=op.force._hash(paths[i]),owner_uuid='owner-'+str(i))
        else:q.update(binding=dict(source=str(paths[i]),source_sha256=op.force._hash(paths[i])),
            records=[dict(footprint_uuid='owner-'+str(i))])
        file=tmp_path/('proposal-'+str(i)+'.json');file.write_text(json.dumps(q))
        steps.append(dict(kind=kind,source=ref(paths[i]),candidate=ref(paths[i+1]),proposal=ref(file)))
    q=dict(schema=1,board_hint='synthetic',source=ref(paths[0]),candidate=ref(paths[-1]),steps=steps)
    return paths,q


@pytest.mark.parametrize('kinds',[('root_reference_seat','reference_map'),
    ('reference_fields','reference_map'),('root_reference_seat','reference_fields','reference_map'),
    ('root_reference_seat','reference_map','reference_fields')])
def test_only_distinct_typed_annotation_owners_and_actual_boundaries(tmp_path,kinds):
    paths,q=fixture(tmp_path,kinds)
    result=op.validate(paths[0],paths[-1],json.loads(json.dumps(q)))
    assert [r[0]for r in result]==list(kinds)
    assert [(r[1],r[2])for r in result]==list(zip(paths,paths[1:]))


@pytest.mark.parametrize('fault',['schema_bool','schema_extra','board_bool','one','four','repeat',
    'physical','root_late','discontinuous','wrong_source','wrong_candidate','hash','relative',
    'same_owner','owner_bool','empty_records','wrong_operation_board','stale_operation_source'])
def test_schema_or_receipts_cannot_expand_work_or_mutation_authority(tmp_path,fault):
    paths,q=fixture(tmp_path);bad=copy.deepcopy(q)
    def rewrite(index,fn):
        row=bad['steps'][index];p=Path(row['proposal']['path']);value=json.loads(p.read_text());fn(value)
        p.write_text(json.dumps(value));row['proposal']['sha256']=op.force._hash(p)
    if fault=='schema_bool':bad['schema']=True
    elif fault=='schema_extra':bad['external_success']=True
    elif fault=='board_bool':bad['board_hint']=True
    elif fault=='one':bad['steps']=bad['steps'][:1]
    elif fault=='four':bad['steps'].append(copy.deepcopy(bad['steps'][-1]))
    elif fault=='repeat':bad['steps'][1]['kind']=bad['steps'][0]['kind']
    elif fault=='physical':bad['steps'][1]['kind']='complete_macro'
    elif fault=='root_late':bad['steps'][0]['kind']='reference_fields';bad['steps'][1]['kind']='root_reference_seat'
    elif fault=='discontinuous':bad['steps'][1]['source']=bad['source']
    elif fault=='wrong_source':bad['source']=bad['steps'][1]['source']
    elif fault=='wrong_candidate':bad['candidate']=bad['steps'][0]['candidate']
    elif fault=='hash':bad['steps'][0]['candidate']['sha256']='0'*64
    elif fault=='relative':bad['steps'][0]['candidate']['path']='relative.kicad_pcb'
    elif fault=='same_owner':rewrite(1,lambda x:x['records'][0].update(footprint_uuid='owner-0'))
    elif fault=='owner_bool':rewrite(1,lambda x:x['records'][0].update(footprint_uuid=True))
    elif fault=='empty_records':rewrite(1,lambda x:x.update(records=[]))
    elif fault=='wrong_operation_board':rewrite(1,lambda x:x.update(board_hint='another'))
    else:rewrite(1,lambda x:x['binding'].update(source_sha256='0'*64))
    with pytest.raises((ValueError,OSError,KeyError)):op.validate(paths[0],paths[-1],bad)


@pytest.mark.parametrize('fault',[None,'false','incomplete','legacy_observation','late_source_write','sidecar'])
def test_every_public_saved_receiver_is_required_not_a_serialized_success(tmp_path,monkeypatch,fault):
    paths,q=fixture(tmp_path);calls=[]
    # These are unit dispatch probes only, never physical receiving evidence.
    monkeypatch.setattr(op.force,'_family',lambda p,h:dict(path=str(p),hash=op.force._hash(p)))
    def receiver(kind):
        def call(parent,child,proposal):
            calls.append((kind,parent,child))
            if fault=='late_source_write'and len(calls)==3:paths[0].write_text('late mutation')
            return dict(ok=not(fault=='false'and len(calls)==2),
                complete=not(fault=='incomplete'and len(calls)==2),
                read_only_legacy_replay=fault=='legacy_observation'and kind=='reference_map')
        return SimpleNamespace(receive=call)
    monkeypatch.setattr(op,'OPERATIONS',{k:receiver(k)for k in op.OPERATIONS})
    if fault=='sidecar':paths[-1].with_suffix('.kicad_pro').write_text('changed')
    r=op.receive(paths[0],paths[-1],q,board_hint='synthetic')
    assert r['ok']is(fault is None),r
    if fault is None:
        assert r['complete']and len(calls)==3
        assert r['only_distinct_source_owned_references_and_associations_changed']
        assert r['no_parts_copper_masks_courtyards_rules_or_dimensions_changed']
        assert not r['release_authority']and not r['current_qualified']
    else:assert r['errors']


def test_outer_transaction_keeps_four_phases_and_one_cleanup_strategy():
    from test_detached_passive_transaction import wrapper
    m=wrapper();row=dict(kind='saved_reference_cleanup',candidate='/exact/child.kicad_pcb',
        candidate_sha256='a'*64,proposal='/exact/proposal.json')
    assert m.validate_phases([row])==['saved_reference_cleanup']
    field=dict(row,kind='reference_fields')
    for bad in([row]*5,[field,row],[row,field],[dict(row,external_success=True)]):
        with pytest.raises(ValueError):m.validate_phases(bad)


def test_outer_dispatch_calls_fresh_chain_with_actual_parent(tmp_path,monkeypatch):
    from test_detached_passive_transaction import wrapper
    m=wrapper();paths,q=fixture(tmp_path);file=tmp_path/'chain.json';file.write_text(json.dumps(q));calls=[]
    def receive(parent,child,request,**kwargs):
        calls.append((parent,child,request,kwargs));return dict(ok=True,complete=True)
    monkeypatch.setattr(m.reference_cleanup,'receive',receive)
    row=dict(kind='saved_reference_cleanup',candidate=str(paths[-1]),candidate_sha256=op.force._hash(paths[-1]),proposal=str(file))
    child,r=m.receive_phase(paths[0],paths[0],row,'synthetic')
    assert child==paths[-1]and r['ok']
    assert calls==[(paths[0],paths[-1],q,dict(board_hint='synthetic'))]
