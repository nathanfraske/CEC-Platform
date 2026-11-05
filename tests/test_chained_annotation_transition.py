import copy,json,shutil,types
from pathlib import Path
import pytest
import cec_force_current as force
import cec_chained_annotation_transition as op


def bound(path):return dict(path=str(path),sha256=force._hash(path))


@pytest.fixture
def env(tmp_path,monkeypatch):
    import cec_nonpolar_print_context as print_op
    import cec_reference_field_seating as fields
    import cec_reference_material_identity as material
    import cec_native_library_context as libraries
    import cec_received_private_stage as stage
    import cec_synth_pipeline as synth
    origin=tmp_path/'origin/board.kicad_pcb';selected=tmp_path/'selected/board.kicad_pcb';child=tmp_path/'child/board.kicad_pcb'
    for path in(origin,selected,child):path.parent.mkdir();path.write_text('native')
    old=dict(references=['a'],rows={'kind':'canonical'});new=dict(references=['a'],rows={'kind':'received-print'})
    historical=dict(board_hint='renamed',old_library_context=old,footprint_ids=['a:b'],expected_instance_uuids=['owner'])
    h=tmp_path/'historical.json';h.write_text(json.dumps(historical))
    q=tmp_path/'reference.json';q.write_text(json.dumps(dict(board_hint='renamed')))
    metadata=dict(candidate=str(selected),library_table=str(selected.parent/'fp-lib-table'),old_library_context=old,new_library_context=new,
        physical_original_template_authority_retained=True,whole_stage_source_current_native_receiving_still_required=True,admitted=False,release_authority=False)
    for path in(selected,child):
        (path.parent/'print-proposal.json').write_bytes(h.read_bytes())
        (path.parent/'print-context.json').write_text(json.dumps(metadata))
        (path.parent/'fp-lib-table').write_text('exact table')
    calls=[];state=dict(scope=True,material=True,physical=True,identity=old)
    def construct(source,proposal,out):
        calls.append('fresh_construct');shutil.copytree(selected.parent,out)
        (out/'print-proposal.json').write_text('fresh independent epoch')
        (out/'print-context.json').write_text('fresh independent location')
        if not state['physical']:(out/'board.kicad_pcb').write_text('different')
        return dict(candidate=str(out/'board.kicad_pcb'))
    monkeypatch.setattr(print_op,'plan',lambda *a,**kw:dict(fresh=True))
    monkeypatch.setattr(print_op,'construct_private',construct)
    # Dispatch-only fixture: native staged replay is covered separately with
    # actual footprints/maps. Keep these original mocked plan/constructor
    # semantics visible through the new explicit stage boundary.
    class Replay:
        def __init__(self,source,options):self.source=source;self.options=options
        def plan(self):
            self.q=print_op.plan(self.source,**self.options);return self.q
        def reconstruct(self,out):return print_op.construct_private(self.source,self.q,out)
        def compare_origin(self,candidate,historical):
            # This fixture tests orchestration only; real native comparison
            # runs in test_staged_nonpolar_print_replay and origin fixtures.
            return dict(ok=state['physical'],complete=state['physical'])
    monkeypatch.setattr(print_op,'staged_replay',lambda source,*,options,timeout_s,candidate:Replay(source,options))
    monkeypatch.setattr(fields,'receive',lambda *a:dict(ok=state['scope'],complete=True))
    monkeypatch.setattr(material,'receive',lambda *a,**kw:dict(ok=state['material'],same_material=True,complete=True,elapsed_s=.1))
    monkeypatch.setattr(libraries,'authority',lambda p,t:old if Path(p)==origin else new)
    monkeypatch.setattr(stage,'identity',lambda *a:dict(native_library_authority=state['identity']))
    monkeypatch.setattr(stage,'matched_instance',lambda i,p:i)
    monkeypatch.setattr(synth.Config,'load',lambda h:types.SimpleNamespace(dir=origin.parent))
    chain=dict(schema=1,origin=bound(origin),steps=[dict(kind='print_context',candidate=bound(selected),proposal=bound(h)),dict(kind='reference_fields',candidate=bound(child),proposal=bound(q))])
    return origin,selected,child,h,q,chain,state,calls


def run(env):return op.receive(env[1],env[2],env[5],board_hint='renamed')


def test_fresh_origin_then_reference_then_context(env):
    r=run(env);assert r['ok'],r
    assert env[7]==['fresh_construct']and r['independent_origin_recompiled']
    assert r['source_native_arguments']['board_hint']is None
    assert r['source_identity']['native_library_authority']==r['old_library_context']
    assert not r['admitted']and not r['full_kelvin_qualification']
    assert op.same_replay(r,copy.deepcopy(r))


def test_fresh_reverse_map_chain_uses_its_own_scope_and_material_receiver(env,monkeypatch):
    import cec_mask_search_reference_mapping as maps
    import cec_reference_map_material_identity as material
    import cec_reference_field_seating as fields
    env[5]['steps'][1]['kind']='reference_map';seen=[]
    def receive_scope(source,candidate,q):
        seen.append(('map',source,candidate));return dict(ok=True,complete=True)
    def receive_material(source,candidate,qpath,*,timeout_s,staged_map_replay):
        assert staged_map_replay is True
        scope=maps.receive(source,candidate,{})
        seen.append(('material',source,candidate,qpath))
        return dict(ok=True,complete=True,same_material=True,elapsed_s=.2,
            map_scope=scope,
            timings_s=dict(map_reconstruct=.1,map_scope=.1,material_live=.1),
            bounded_composition=dict(map_reconstruct_limit_s=10.,map_scope_limit_s=10.,material_live_limit_s=10.,aggregate_limit_s=30.))
    def wrong_receiver(*args,**kw):raise AssertionError('forward-field scope cannot authorize a reverse map')
    monkeypatch.setattr(maps,'receive',receive_scope)
    monkeypatch.setattr(material,'receive',receive_material)
    monkeypatch.setattr(fields,'receive',wrong_receiver)
    r=run(env);assert r['ok'],r
    assert r['annotation_kind']=='reference_map'
    assert seen==[('map',env[1],env[2]),('material',env[1],env[2],env[4])]
    other=copy.deepcopy(r);other['material_identity']['timings_s']=dict(map_reconstruct=.2,map_scope=.2,material_live=.2)
    assert op.same_replay(r,other)
    other['material_identity']['timings_s']['map_scope']=10.
    assert not op.same_replay(r,other)


@pytest.mark.parametrize('receiver',['scope','material'])
def test_reverse_map_chain_refuses_failed_map_receiver(env,monkeypatch,receiver):
    import cec_mask_search_reference_mapping as maps
    import cec_reference_map_material_identity as material
    env[5]['steps'][1]['kind']='reference_map'
    monkeypatch.setattr(maps,'receive',lambda *a,**kw:dict(ok=receiver!='scope',complete=True))
    monkeypatch.setattr(material,'receive',lambda *a,**kw:dict(ok=receiver!='material',complete=True,same_material=True,
        map_scope=maps.receive(*a[:2],{}),elapsed_s=.2,timings_s=dict(map_reconstruct=.1,map_scope=.1,material_live=.1),
        bounded_composition=dict(map_reconstruct_limit_s=10.,map_scope_limit_s=10.,material_live_limit_s=10.,aggregate_limit_s=30.)))
    assert not run(env)['ok']


@pytest.mark.parametrize('fault',['missing_phase','slow_phase','wide_limit','aggregate','bad_timing'])
def test_reverse_map_phase_bounds_are_not_relaxed(env,monkeypatch,fault):
    import cec_reference_map_material_identity as material
    env[5]['steps'][1]['kind']='reference_map'
    result=dict(ok=True,complete=True,same_material=True,map_scope=dict(ok=True,complete=True),elapsed_s=.2,
        timings_s=dict(map_reconstruct=.1,map_scope=.1,material_live=.1),
        bounded_composition=dict(map_reconstruct_limit_s=10.,map_scope_limit_s=10.,material_live_limit_s=10.,aggregate_limit_s=30.))
    if fault=='missing_phase':result['timings_s'].pop('material_live')
    elif fault=='slow_phase':result['timings_s']['material_live']=10.
    elif fault=='wide_limit':result['bounded_composition']['material_live_limit_s']=20.
    elif fault=='aggregate':result['elapsed_s']=30.
    else:result['timings_s']['map_scope']=float('nan')
    monkeypatch.setattr(material,'receive',lambda *a,**kw:result)
    assert not run(env)['ok']


@pytest.mark.parametrize('fault',['extra','schema_bool','third','wrongkind','hash','current','context','scope','material','physical','metadata','proposal','companion','identity'])
def test_fail_closed_chain(env,fault):
    origin,selected,child,h,q,chain,state,_=env
    if fault=='extra':chain['context']={}
    elif fault=='schema_bool':chain['schema']=True
    elif fault=='third':chain['steps'].append(copy.deepcopy(chain['steps'][1]))
    elif fault=='wrongkind':chain['steps'][1]['kind']='complete_macro'
    elif fault=='hash':chain['steps'][0]['candidate']['sha256']='0'*64
    elif fault=='current':chain['steps'][0]['candidate']=bound(origin)
    elif fault=='context':chain['steps'][1]['context']={}
    elif fault in('scope','material','physical'):state[fault]=False
    elif fault=='metadata':(selected.parent/'print-context.json').write_text('{}')
    elif fault=='proposal':(selected.parent/'print-proposal.json').write_text('{}')
    elif fault=='companion':(child.parent/'fp-lib-table').write_text('forged')
    elif fault=='identity':state['identity']={'forged':1}
    assert not run(env)['ok']


def test_native_replay_timing_not_authority(env):
    r=run(env);assert r['ok']
    other=copy.deepcopy(r);other['timings_s']={k:.5 for k in other['timings_s']};other['elapsed_s']=3
    assert op.same_replay(r,other)
    other['timings_s']['reference_scope']=10
    assert not op.same_replay(r,other)


def test_source_mutation_during_scope_refuses(env,monkeypatch):
    import cec_reference_field_seating as fields
    def mutate(*a):env[0].write_text('changed');return dict(ok=True,complete=True)
    monkeypatch.setattr(fields,'receive',mutate)
    assert 'source_code_or_dependencies_changed'in run(env)['error']


def test_selected_historical_print_requires_fresh_whole_origin_reconstruction(env):
    declaration=dict(source=bound(env[0]),proposal=bound(env[3]))
    result=op.receive_print_row(env[1],declaration,board_hint='renamed')
    assert result['ok']and result['independent_origin_recompiled'],result
    assert env[7]==['fresh_construct']
    assert result['candidate_native_arguments']['footprint_table']==str(env[1].parent/'fp-lib-table')
    assert not result['admitted']and not result['full_kelvin_qualification']
    assert op.same_print_replay(result,copy.deepcopy(result))


@pytest.mark.parametrize('fault',['physical','metadata','proposal','hash','identity','extra_context','slow'])
def test_historical_print_replay_never_uses_old_success_or_serialized_context(env,monkeypatch,fault):
    declaration=dict(source=bound(env[0]),proposal=bound(env[3]))
    if fault=='physical':env[6]['physical']=False
    elif fault=='metadata':(env[1].parent/'print-context.json').write_text('{}')
    elif fault=='proposal':(env[1].parent/'print-proposal.json').write_text('{}')
    elif fault=='hash':declaration['source']['sha256']='0'*64
    elif fault=='identity':env[6]['identity']={'forged':True}
    elif fault=='extra_context':declaration['context']={}
    else:
        import cec_nonpolar_print_context as print_op
        now=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:now[0])
        def slow(*a,**kw):now[0]+=10;return{}
        monkeypatch.setattr(print_op,'plan',slow)
    assert not op.receive_print_row(env[1],declaration,board_hint='renamed')['ok']


def test_per_phase_deadline(env,monkeypatch):
    import cec_reference_field_seating as fields
    now=[0.];monkeypatch.setattr(op.time,'monotonic',lambda:now[0])
    def slow(*a):now[0]+=10;return dict(ok=True,complete=True)
    monkeypatch.setattr(fields,'receive',slow)
    assert 'reference_scope_deadline'in run(env)['error']


@pytest.mark.parametrize('chart_recipe', ['exact', 'missing', 'forged'])
def test_historical_chart_scope_is_forwarded_but_still_recompiled(env,monkeypatch,chart_recipe):
    import cec_nonpolar_print_context as printing
    origin,selected,child,h,q,chain,state,calls=env
    actual=['actual_Source_closed_chart']
    historical=json.loads(h.read_text())
    historical['script_code_identity']={'historical_only':'not_current_authority'}
    if chart_recipe!='missing':
        historical['source_chart_group_uuids']=actual if chart_recipe=='exact'else['forged_chart']
    h.write_text(json.dumps(historical))
    (selected.parent/'print-proposal.json').write_bytes(h.read_bytes())
    seen=[]
    def fresh_plan(source,**options):
        assert source==origin
        seen.append(copy.deepcopy(options.get('source_chart_group_uuids')))
        if options.get('source_chart_group_uuids')!=actual:
            raise ValueError('actual_Source_closed_chart_required')
        return dict(fresh=True,source_chart_group_uuids=actual)
    monkeypatch.setattr(printing,'plan',fresh_plan)
    declaration=dict(source=bound(origin),proposal=bound(h))
    result=op.receive_print_row(selected,declaration,board_hint='renamed')
    assert result['ok']is(chart_recipe=='exact'),result
    assert seen==[historical.get('source_chart_group_uuids',())]
    assert calls==(['fresh_construct']if chart_recipe=='exact'else[])
    assert (selected.parent/'print-proposal.json').read_bytes()==h.read_bytes()
    assert not result['admitted']and not result['release_authority']
