"""Real native staged print tests; no proof/verdict mocks."""
import copy,json
from pathlib import Path
import pytest
import cec_nonpolar_print_context as op
from test_nonpolar_print_context import fixture,planned


def options(q):
    return {k:q[k]for k in('library_table','footprint_ids','expected_instance_uuids','board_hint')}


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_fresh_staged_saved_native_matches_legacy(tmp_path,monkeypatch,turn,back):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn,back)
    q=planned(source,table,ids);artifact=op.construct_private(source,q,tmp_path/'legacy')
    before={p:p.read_bytes()for p in(source,table,*library.glob('*'))}
    proof=op.receive_staged(source,artifact['candidate'],q)
    assert proof['ok']and proof['complete'],proof
    assert proof['staged_replay']['state']=='received'
    assert set(proof['staged_replay']['timings_s'])=={'source_plan','reconstruct','saved_compare'}
    assert all(0<=t<10 for t in proof['staged_replay']['timings_s'].values())
    assert all(p.read_bytes()==value for p,value in before.items())
    assert not proof['admitted']and not proof['release_authority']
    assert op._STAGED_PRINT.get()is None


@pytest.mark.parametrize('fault',['source','template','table','sidecar','extra','metadata','pad','proposal'])
def test_actual_saved_or_source_damage_refuses(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    artifact=op.construct_private(source,q,tmp_path/'candidate');child=Path(artifact['candidate'])
    if fault in('source','template','table','sidecar','extra'):
        p={'source':source,'template':library/'R_1206_3216Metric.kicad_mod','table':table,
           'sidecar':child.with_suffix('.kicad_dru'),'extra':child.parent/'unowned'}[fault]
        p.write_bytes((p.read_bytes()if p.exists()else b'')+b'\n# changed\n')
    elif fault=='metadata':
        p=child.parent/'print-context.json';m=json.loads(p.read_text());m['admitted']=True;p.write_text(json.dumps(m))
    elif fault=='pad':
        b=op.pcbnew.LoadBoard(str(child));f=next(f for f in b.GetFootprints()if op.force._uid(f)==ids[0])
        next(iter(f.Pads())).Move(op.pcbnew.VECTOR2I(1,0));op.ink.field._save_field_snapshot(b,child)
    else:q=copy.deepcopy(q);q['records']=q['records'][:1]
    proof=op.receive_staged(source,child,q)
    assert not proof['ok'],proof


@pytest.mark.parametrize('fault',['source','template','table','rules'])
def test_between_stage_mutations_are_terminal(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    replay=op.staged_replay(source,options=options(q));replay.plan()
    p={'source':source,'template':library/'R_1206_3216Metric.kicad_mod','table':table,'rules':source.with_suffix('.kicad_dru')}[fault]
    p.write_bytes(p.read_bytes()+b'\n \n')
    with pytest.raises(ValueError,match='inputs_changed'):replay.reconstruct(tmp_path/'bad')
    assert replay.observation()['state']=='failed'
    with pytest.raises(ValueError,match='order_required'):replay.reconstruct(tmp_path/'rescue')


def test_stage_order_copy_seal_and_context_cleanup(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    replay=op.staged_replay(source,options=options(q))
    with pytest.raises(ValueError,match='order_required'):replay.reconstruct(tmp_path/'early')
    assert replay.observation()['state']=='failed'
    replay=op.staged_replay(source,options=options(q))
    fresh=replay.plan();fresh['records'].clear()
    artifact=replay.reconstruct(tmp_path/'exact')
    assert Path(artifact['candidate']).is_file()
    with pytest.raises(ValueError,match='order_required'):replay.plan()
    assert op._STAGED_PRINT.get()is None


def test_late_real_plan_cannot_advance_or_reset(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    real=op.plan;clock=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    def late(*a,**kw):
        value=real(*a,**kw);clock[0]=10.;return value
    monkeypatch.setattr(op,'plan',late)
    replay=op.staged_replay(source,options=options(q))
    with pytest.raises(ValueError,match='deadline'):replay.plan()
    assert replay.observation()['state']=='failed'and op._STAGED_PRINT.get()is None
    clock[0]=0.
    with pytest.raises(ValueError,match='order_required'):replay.plan()


@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_map_replayed_once_per_fresh_receiver(tmp_path,monkeypatch,back):
    from test_received_guide_print_context import case
    import cec_mask_search_reference_mapping as annotation
    ancestor,mapped,declaration,opts=case(tmp_path,monkeypatch,back=back)
    q=op.plan(mapped,**opts,reference_mapping_transition=declaration)
    artifact=op.construct_private(mapped,q,tmp_path/'printed')
    real=annotation.saved_replay;calls=[]
    def observed(*a,**kw):
        calls.append((a[0],a[1]));return real(*a,**kw)
    monkeypatch.setattr(annotation,'saved_replay',observed)
    proof=op.receive_staged(mapped,artifact['candidate'],q)
    assert proof['ok']and proof['complete'],(proof.get('error'),proof.get('staged_replay'))
    assert len(calls)==1 and set(proof['staged_replay']['timings_s'])=={
        'map_reconstruct','map_receive','source_plan','reconstruct','saved_compare'}
    assert op._STAGED_PRINT.get()is None
    again=op.receive_staged(mapped,artifact['candidate'],q)
    assert again['ok']and len(calls)==2,again


@pytest.mark.parametrize('fault',['plan_material','expected_material','candidate_between','candidate_after_plan','final_hash_clock'])
def test_sealed_material_and_final_boundary_fail_closed(tmp_path,monkeypatch,fault):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    artifact=op.construct_private(source,q,tmp_path/'candidate')
    replay=op.staged_replay(source,options=options(q),candidate=artifact['candidate'],proposal=q)
    replay.plan()
    if fault=='candidate_after_plan':
        p=Path(artifact['candidate']);p.write_bytes(p.read_bytes()+b'\n')
        with pytest.raises(ValueError,match='inputs_changed'):replay.reconstruct(tmp_path/'expected')
        assert replay.observation()['state']=='failed'
        return
    if fault=='plan_material':
        replay._q=replay._q+' '
        with pytest.raises(ValueError,match='material_changed'):replay.reconstruct(tmp_path/'expected')
    else:
        replay.reconstruct(tmp_path/'expected')
        if fault=='expected_material':replay._expected['board.kicad_pcb']+=b' '
        elif fault=='candidate_between':
            p=Path(artifact['candidate']);p.write_bytes(p.read_bytes()+b'\n')
        else:
            real=replay._snapshot;clock=[0.];calls=[0]
            monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
            def observed():
                value=real();calls[0]+=1
                if calls[0]==2:clock[0]=10.
                return value
            monkeypatch.setattr(replay,'_snapshot',observed)
        with pytest.raises(ValueError):replay.receive()
    assert replay.observation()['state']=='failed'
    with pytest.raises(ValueError,match='order_required'):replay.receive()


def test_unchanged_but_aged_invocation_cannot_start_a_new_stage(tmp_path,monkeypatch):
    source,table,ids,library=fixture(tmp_path,monkeypatch);q=planned(source,table,ids)
    clock=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    replay=op.staged_replay(source,options=options(q));clock[0]=30.
    with pytest.raises(ValueError,match='aggregate_deadline'):replay.plan()
    assert replay.observation()['state']=='failed'


@pytest.mark.parametrize('back',[False,True])
def test_typed_consumer_uses_actual_native_staged_operator(tmp_path,monkeypatch,back):
    # Only the outer board-catalog identity is synthetic; the entire saved
    # map/Source plan/family/native/second-save operator is real.
    from test_received_guide_print_context import case
    import cec_print_context_transition as transition
    import cec_received_private_stage as stage
    import cec_synth_pipeline as synth
    import types
    ancestor,mapped,declaration,opts=case(tmp_path,monkeypatch,back=back)
    q=op.plan(mapped,**opts,reference_mapping_transition=declaration)
    artifact=op.construct_private(mapped,q,tmp_path/'printed')
    old=stage.stable(op.libraries.authority(mapped,opts['library_table']))
    monkeypatch.setattr(synth.Config,'load',lambda hint:types.SimpleNamespace(dir=Path(opts['library_table']).parent))
    monkeypatch.setattr(stage,'identity',lambda path,*a:dict(source=str(path),native_library_authority=old))
    monkeypatch.setattr(stage,'matched_instance',lambda instance,path:instance)
    proof=transition.receive(mapped,artifact['candidate'],q,board_hint='renamed')
    assert proof['ok']and proof['complete'],(proof.get('error'),proof.get('operator_scope'))
    assert proof['operator_scope']['staged_replay']['state']=='received'
    assert len(proof['bounded_composition']['constituents'])==6
    assert transition.same_replay(proof,copy.deepcopy(proof))
