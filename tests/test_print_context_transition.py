"""Adapter contracts; actual native OPS replay is tested by its own suite."""
import copy
import json
import sys
import types
from pathlib import Path
import pytest
import cec_print_context_transition as transition

@pytest.fixture
def env(tmp_path,monkeypatch):
    source=tmp_path/'old'/'board.kicad_pcb';child=tmp_path/'new'/'board.kicad_pcb'
    for p in(source,child):p.parent.mkdir();p.write_text('source')
    old={'authority':'canonical'};new={'authority':'print'};calls=[]
    state=dict(old=old,new=new,scope_old=old,scope_new=new,scope_ok=True,canonical_identity=old,drift=False)
    fakeop=tmp_path/'op.py';fakeop.write_text('original')
    fakeink=tmp_path/'ink.py';fakeink.write_text('ink');fakeframe=tmp_path/'frame.py';fakeframe.write_text('frame')
    def scope(*a,**kw):calls.append('scope');return dict(ok=state['scope_ok'],complete=True,old_library_context=state['scope_old'],new_library_context=state['scope_new'])
    def authority(board,table):calls.append('authority');return state['new']if Path(table).parent==child.parent else state['old']
    def identity(p,h,i):return dict(source=str(p),other='immutable',native_library_authority=state['canonical_identity'])
    mods={
      'cec_nonpolar_print_context':dict(__file__=str(fakeop),receive=scope,ink=types.SimpleNamespace(__file__=str(fakeink),frame=types.SimpleNamespace(__file__=str(fakeframe)))),
      'cec_force_current':dict(_code_identity=lambda:'epoch',_family=lambda p,h:str(p),_hash=lambda p:Path(p).read_text()),
      'cec_received_private_stage':dict(stable=lambda x:copy.deepcopy(x),identity=identity,matched_instance=lambda i,p:i),
      'cec_native_library_context':dict(authority=authority),
      'cec_synth_pipeline':dict(Config=types.SimpleNamespace(load=lambda h:types.SimpleNamespace(dir=source.parent)))}
    for name,attrs in mods.items():monkeypatch.setitem(sys.modules,name,types.SimpleNamespace(**attrs))
    return source,child,state,calls

def run(env,**kw):
    s,c,_,_=env;return transition.receive(s,c,{'board_hint':'renamed'},board_hint='renamed',**kw)

def test_context_is_received_first_and_only_identity_field_changes(env):
    result=run(env);assert result['ok'];assert env[3][0]=='scope'
    assert result['source_identity']['native_library_authority']==env[2]['old']
    assert result['candidate_identity']['native_library_authority']==env[2]['new']
    assert result['candidate_identity']['other']=='immutable'
    assert result['candidate_native_arguments']['board_hint']is None
    assert result['admitted']is False and result['all_shared_receiving_still_required']
    assert result['bounded_composition']['aggregate_limit_s']==20


@pytest.mark.parametrize('scope_s,identity_s,ok,error',[(6,5,True,None),(10,0,False,'scope_deadline'),(1,10,False,'identity_live_deadline')])
def test_two_phase_leases_not_blanket_ten_seconds(env,monkeypatch,scope_s,identity_s,ok,error):
    clock={'now':100.};monkeypatch.setattr(transition.time,'monotonic',lambda:clock['now'])
    m=sys.modules['cec_nonpolar_print_context'];original=m.receive
    def scope(*a,**kw):clock['now']+=scope_s;return original(*a,**kw)
    monkeypatch.setattr(m,'receive',scope)
    stage=sys.modules['cec_received_private_stage'];identity=stage.identity;count=0
    def identified(*a):
        nonlocal count
        count+=1
        if count==1:clock['now']+=identity_s
        return identity(*a)
    monkeypatch.setattr(stage,'identity',identified)
    r=run(env);assert r['ok']is ok
    if error:assert error in r['error']
    else:assert r['timings_s']==dict(scope=6,identity_live=5,aggregate=11)


def test_replay_excludes_only_checked_timing_observations(env):
    r=run(env);other=copy.deepcopy(r)
    other['timings_s']=dict(scope=6.,identity_live=5.,aggregate=11.)
    assert transition.same_replay(r,other)
    for fault in('context','unbounded','false_scope'):
        bad=copy.deepcopy(other)
        if fault=='context':bad['new_library_context']={'forged':1}
        if fault=='unbounded':bad['timings_s']['scope']=10.
        if fault=='false_scope':bad['operator_scope']['ok']=False
        assert not transition.same_replay(r,bad)


@pytest.mark.parametrize('module',['ink','frame'])
def test_nested_ops_dependency_cannot_change_between_composed_phases(env,monkeypatch,module):
    m=sys.modules['cec_nonpolar_print_context'];original=m.receive
    target=Path(m.ink.__file__ if module=='ink'else m.ink.frame.__file__)
    def mutate(*a,**kw):
        value=original(*a,**kw);target.write_text('changed');return value
    monkeypatch.setattr(m,'receive',mutate)
    assert 'source_code_or_context_changed'in run(env)['error']

@pytest.mark.parametrize('key,value,error',[
 ('scope_ok',False,'independent_print_scope'),('scope_old',{'forged':1},'not_canonical'),
 ('scope_new',{'forged':1},'not_independently'),('canonical_identity',{'forged':1},'identity_context_conflict')])
def test_forged_or_conflicting_contexts_refuse(env,key,value,error):
    env[2][key]=value;r=run(env);assert not r['ok'];assert error in r['error']

@pytest.mark.parametrize('value',[True,0,-1,11,float('nan'),float('inf')])
def test_timeout_bounds(env,value):assert not run(env,timeout_s=value)['ok']

def test_context_drift_during_replay_refuses(env,monkeypatch):
    m=sys.modules['cec_native_library_context'];original=m.authority;count=0
    def changing(*a):
        nonlocal count
        count+=1
        return {'drift':1}if count>2 else original(*a)
    monkeypatch.setattr(m,'authority',changing)
    assert 'changed' in run(env)['error']

def test_native_context_requires_bound_actual_producer(env):
    received=run(env);proof=dict(ok=True,complete=True,source_and_producer_unchanged=True,
      command=['native',str(env[1])],source_files={str(env[1]):'source'},
      native_library_context=dict(bound=True,source_and_context_unchanged=True,authority=env[2]['new']))
    s,c,_,_=env
    assert transition.require_native_context(proof,s,c,{'board_hint':'renamed'},board_hint='renamed',candidate=True)
    for key in('bound','source_and_context_unchanged','authority'):
        bad=copy.deepcopy(proof);bad['native_library_context'][key]=False
        with pytest.raises(ValueError):transition.require_native_context(bad,s,c,{'board_hint':'renamed'},board_hint='renamed',candidate=True)
    wrong=copy.deepcopy(proof);wrong['command'][-1]=str(s)
    with pytest.raises(ValueError):transition.require_native_context(wrong,s,c,{'board_hint':'renamed'},board_hint='renamed',candidate=True)

def test_no_public_context_override(env):
    with pytest.raises(TypeError):run(env,new_library_context={'arbitrary':1})

@pytest.mark.parametrize('name',['_code_identity','_family'])
def test_code_or_source_family_drift_refuses(env,monkeypatch,name):
    m=sys.modules['cec_force_current'];original=getattr(m,name);count=0
    def changing(*args):
        nonlocal count
        count+=1
        return 'drift'if count>(1 if name=='_code_identity'else 2)else original(*args)
    monkeypatch.setattr(m,name,changing)
    assert 'changed' in run(env)['error']

def test_wrong_named_source_context_refuses_before_scope(env):
    s,c,_,calls=env
    r=transition.receive(s,c,{'board_hint':'wrong'},board_hint='renamed')
    assert not r['ok']and not calls

def test_no_later_copper_descendant_can_bypass_scope(env,monkeypatch):
    m=sys.modules['cec_nonpolar_print_context']
    monkeypatch.setattr(m,'receive',lambda *a,**k:dict(ok=False,complete=False,error='not_exact_literal_print_child'))
    assert 'not_exact_literal_print_child' in run(env)['error']

def declaration(env):
    s,c,_,_=env;p=s.parent/'proposal.json';p.write_text(json.dumps({'board_hint':'renamed'}))
    return c,{'source':{'path':str(s),'sha256':'a'*64},'proposal':{'path':str(p),'sha256':'b'*64}}

def test_exact_row_dispatches_fresh_receiver(env,monkeypatch):
    c,row=declaration(env);m=sys.modules['cec_force_current']
    monkeypatch.setattr(m,'_hash',lambda p:'b'*64 if Path(p).name=='proposal.json'else'a'*64)
    assert transition.receive_row(c,row,board_hint='renamed')['ok']

@pytest.mark.parametrize('mutation',['extra_context','extra_file_key','missing_source','bad_sha','changed_file'])
def test_row_cannot_self_authorize_or_drift(env,mutation):
    c,row=declaration(env)
    if mutation=='extra_context':row['new_context']={}
    if mutation=='extra_file_key':row['source']['authority']={}
    if mutation=='missing_source':del row['source']
    if mutation=='bad_sha':row['source']['sha256']='x'
    with pytest.raises(ValueError):transition.receive_row(c,row,board_hint='renamed')


def staged_env(env,monkeypatch):
    """Dispatch-only synthetic operator; native replay has separate tests."""
    clock=[100.];monkeypatch.setattr(transition.time,'monotonic',lambda:clock[0])
    module=sys.modules['cec_nonpolar_print_context'];calls=[]
    def staged(*a,**kw):
        calls.append(a);clock[0]+=5.
        times={k:1. for k in transition._STAGED_NAMES};limit=kw['timeout_s']
        return dict(ok=True,complete=True,old_library_context=env[2]['old'],new_library_context=env[2]['new'],
            elapsed_s=5.,timings_s=times,
            bounded_composition=dict(kind='fresh_source_plan_reconstruct_saved_native',per_constituent_limit_s=limit,
                constituents=list(transition._STAGED_NAMES),aggregate_limit_s=5*limit),
            staged_replay=dict(state='received',timings_s=times,per_constituent_limit_s=limit,
                constituents=list(transition._STAGED_NAMES),aggregate_limit_s=5*limit,no_saved_verdict_or_release_authority=True))
    def legacy(*a,**kw):raise AssertionError('declared map must use fresh independent staged receiver')
    monkeypatch.setattr(module,'receive_staged',staged,raising=False);monkeypatch.setattr(module,'receive',legacy)
    return module,staged,calls,clock


def staged_run(env):
    return transition.receive(env[0],env[1],dict(board_hint='renamed',reference_mapping_transition={}),board_hint='renamed')


def test_declared_map_uses_five_fresh_operator_stages_then_identity(env,monkeypatch):
    module,real,calls,clock=staged_env(env,monkeypatch)
    a=staged_run(env);b=staged_run(env)
    assert a['ok']and b['ok']and len(calls)==2,(a,b)
    assert a['bounded_composition']['aggregate_limit_s']==60.
    assert set(a['timings_s'])==set(transition._STAGED_NAMES)|{'identity_live','aggregate'}
    assert transition.same_replay(a,b)


@pytest.mark.parametrize('fault',['missing','extra','late','bool','nan','scopefalse','incomplete','failedstate','observation','aggregate','context'])
def test_staged_scope_cannot_forge_composition_or_authority(env,monkeypatch,fault):
    module,real,calls,clock=staged_env(env,monkeypatch)
    def corrupt(*a,**kw):
        proof=real(*a,**kw)
        if fault=='missing':proof['timings_s'].pop('source_plan')
        elif fault=='extra':proof['timings_s']['unowned']=0.
        elif fault in('late','bool','nan'):proof['timings_s']['source_plan']={'late':10.,'bool':True,'nan':float('nan')}[fault]
        elif fault=='scopefalse':proof['ok']=False
        elif fault=='incomplete':proof['complete']=False
        elif fault=='failedstate':proof['staged_replay']['state']='failed'
        elif fault=='observation':proof['staged_replay']['no_saved_verdict_or_release_authority']=False
        elif fault=='aggregate':proof['elapsed_s']=50.
        else:proof['new_library_context']={'forged':True}
        return proof
    monkeypatch.setattr(module,'receive_staged',corrupt)
    assert not staged_run(env)['ok']


def test_staged_same_replay_normalizes_only_checked_actual_times(env,monkeypatch):
    staged_env(env,monkeypatch);proof=staged_run(env);other=copy.deepcopy(proof)
    times={k:.5 for k in transition._STAGED_NAMES}
    other['operator_scope']['timings_s']=times
    other['operator_scope']['staged_replay']['timings_s']=times
    other['operator_scope']['elapsed_s']=2.5
    other['timings_s']=dict(times,identity_live=.5,aggregate=3.)
    assert transition.same_replay(proof,other)
    for fault in('state','identity','context','time'):
        bad=copy.deepcopy(other)
        if fault=='state':bad['operator_scope']['staged_replay']['state']='failed'
        elif fault=='identity':bad['candidate_identity']['other']='forged'
        elif fault=='context':bad['new_library_context']={'forged':True}
        else:bad['timings_s']['identity_live']=10.
        assert not transition.same_replay(proof,bad)


def test_staged_identity_keeps_its_own_ten_second_limit(env,monkeypatch):
    module,real,calls,clock=staged_env(env,monkeypatch)
    stage=sys.modules['cec_received_private_stage'];identity=stage.identity
    def late(*a):clock[0]+=10.;return identity(*a)
    monkeypatch.setattr(stage,'identity',late)
    proof=staged_run(env)
    assert not proof['ok']and 'identity_live_deadline'in proof['error']
