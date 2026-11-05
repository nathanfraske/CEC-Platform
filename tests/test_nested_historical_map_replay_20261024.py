"""A new actual-ancestor observation replaces evidence, never stale epochs."""
import copy,json,types
from pathlib import Path
import pytest
import cec_force_current as force
import cec_chained_annotation_transition as chain
from test_chained_annotation_transition import env,bound


@pytest.fixture
def nested(env,monkeypatch):
    import cec_mask_search_reference_mapping as maps
    import cec_native_drc_runner as native
    import cec_nonpolar_print_context as print_op
    origin,selected,child,h,*unused=env
    ancestor=origin.parent.parent/'ancestor/board.kicad_pcb';ancestor.parent.mkdir();ancestor.write_text('original-native')
    report=ancestor.parent.parent/'old-native.json';report.write_text('{}')
    grade=ancestor.parent.parent/'old-grade.json'
    old_producer=dict(report=str(report),report_sha256=force._hash(report),reporting_build={'root':'/verified-build'})
    grade.write_text(json.dumps(dict(code_identity={'STALE':True},boards={'source':dict(
        sha256=force._hash(ancestor),native_producer=old_producer)})))
    q=dict(board_hint='renamed',maximum_components=2,seed_index=3,
        reverse_ownership='rigid_root_group_per_component',mode='opposite_face_projected_courtyard',
        positive_leaders_only=False,owner_uuid_scope=['owner'],records=[{'geometry':'exact-original'}],
        grade=str(grade),binding=dict(source=str(ancestor),source_sha256=force._hash(ancestor),
            source_family=force._family(ancestor,'renamed'),grade=str(grade),grade_sha256=force._hash(grade),
            native_report=str(report),native_report_sha256=force._hash(report),code_identity={'STALE':True},
            authority_sha256='old-authority',factory_legend={'height':1.}))
    qpath=ancestor.parent.parent/'old-map.json';qpath.write_text(json.dumps(q))
    historical=json.loads(h.read_text());historical['reference_mapping_transition']=dict(
        source=bound(ancestor),proposal=bound(qpath))
    h.write_text(json.dumps(historical));env[5]['steps'][0]['proposal']=bound(h)
    for path in(selected,child):(path.parent/'print-proposal.json').write_bytes(h.read_bytes())
    seen=[];state=dict(native_ok=True,replay_ok=True,reconstruct_ok=True,receive_ok=True)
    def native_run(source,output,**kwargs):
        assert source==ancestor and kwargs['reporting_build']==Path('/verified-build')
        seen.append('new_native');output.write_text('{}')
        return dict(ok=state['native_ok'],complete=True,source_and_producer_unchanged=True,
            native_inventory={'potentially_truncated':False},report=str(output),report_sha256=force._hash(output),
            command=['native',str(source)],source_files={str(source):force._hash(source)})
    def replay(source,mapped,**kwargs):
        assert source==ancestor and mapped==origin
        g=json.loads(kwargs['grade'].read_text())
        assert g['code_identity']==force._code_identity() and kwargs['grade']!=grade
        if kwargs['maximum_components']!=2 or kwargs['seed_index']!=3:
            raise ValueError('changed_recipe_cannot_reproduce_saved_map')
        assert kwargs['positive_leaders_only']is q['positive_leaders_only']
        seen.append('new_plan')
        if not state['replay_ok']:raise ValueError('exact_saved_map_geometry_refused')
        fresh=copy.deepcopy(q);fresh['grade']=str(kwargs['grade'])
        fresh['binding'].update(grade=fresh['grade'],grade_sha256=force._hash(kwargs['grade']),
            native_report=g['boards']['source']['native_producer']['report'],code_identity=force._code_identity())
        return fresh
    def receive(source,mapped,proposal):
        if proposal['binding']['code_identity']!=force._code_identity():
            return dict(ok=False,complete=False,errors=['source_native_legend_grade_epoch_changed'])
        seen.append('new_receive')
        return dict(ok=state['receive_ok'],complete=True,source_bound_projection_exact=True)
    class Saved:
        def __init__(self,source,mapped,proposal):
            self.source,self.mapped,self.proposal=source,mapped,proposal
        def reconstruct(self):
            seen.append('new_reconstruct')
            if not state['reconstruct_ok']:raise ValueError('independent_reconstruction_refused')
            return dict(reconstruction_only=True)
        def receive(self):return receive(self.source,self.mapped,self.proposal)
    class Existing:
        def __init__(self,source,mapped,options):self.source,self.mapped,self.options=source,mapped,options
        def plan(self):
            self.proposal=replay(self.source,self.mapped,**self.options);return self.proposal
        def reconstruct(self):
            self.saved=maps.saved_replay(self.source,self.mapped,self.proposal)
            return self.saved.reconstruct()
        def receive(self):return self.saved.receive()
    def print_plan(source,**kwargs):
        declaration=kwargs['reference_mapping_transition']
        proposal=json.loads(Path(declaration['proposal']['path']).read_text())
        mapped=Path(declaration['mapped_source']['path'])if 'mapped_source'in declaration else source
        active=print_op._STAGED_PRINT.get()
        assert active is not None
        assert active._map_proof(ancestor,mapped,proposal)['ok']
        seen.append('print_plan');return dict(fresh=True)
    class PrintReplay(print_op._PrintReplay):
        """Synthetic native I/O only; real enclosing stage/order/lease owner.

        These text-only fixtures are not KiCad boards. Actual native replay is
        exercised in test_staged_existing_reference_replay and staged print
        fixtures. Never mock the staged map methods or their verdict guards.
        """
        def _snapshot(self):
            declaration=self._options['reference_mapping_transition']
            paths=[self._source,Path(declaration['source']['path']),Path(declaration['proposal']['path'])]
            if self._candidate is not None:paths.append(self._candidate)
            if 'mapped_source'in declaration:paths.append(Path(declaration['mapped_source']['path']))
            current=json.loads(paths[2].read_text())
            paths.extend(Path(current['binding'][key])for key in('grade','native_report'))
            return (force._code_identity(),tuple((str(p),force._hash(p))for p in paths),
                tuple(force._family(p,'renamed')for p in paths if p.suffix=='.kicad_pcb'),
                json.dumps(self._options,sort_keys=True))
        def reconstruct(self,out):
            def run():
                artifact=print_op.construct_private(self._source,json.loads(self._q),out)
                self._fixture_expected=self._files(Path(artifact['candidate']).parent)
                return artifact
            return self._run('reconstruct','planned','reconstructed',run)
        def compare_origin(self,candidate,historical):
            def run():
                assert Path(candidate)==self._candidate
                expected=dict(self._fixture_expected);actual=self._files(Path(candidate).parent)
                for name in('print-proposal.json','print-context.json'):
                    assert name in expected and name in actual
                    del expected[name];del actual[name]
                if expected!=actual:raise ValueError('fresh_origin_literal_print_family_replay_failed')
                return dict(ok=True,complete=True)
            return self._run('saved_compare','reconstructed','received',run)
    monkeypatch.setattr(native,'run',native_run);monkeypatch.setattr(maps,'replay_existing_plan',replay)
    monkeypatch.setattr(maps,'existing_replay',lambda source,mapped,**options:Existing(source,mapped,options))
    monkeypatch.setattr(maps,'saved_replay',lambda source,mapped,proposal,**kwargs:Saved(source,mapped,proposal))
    monkeypatch.setattr(maps,'receive',receive);monkeypatch.setattr(print_op,'plan',print_plan)
    monkeypatch.setattr(print_op,'staged_replay',lambda source,*,options,timeout_s=10.,candidate=None,proposal=None:
        PrintReplay(source,options,timeout_s,candidate,proposal))
    return env,ancestor,qpath,q,state,seen


def run(nested):
    env=nested[0]
    return chain.receive_print_row(env[1],dict(source=bound(env[0]),proposal=bound(env[3])),board_hint='renamed')


def test_old_grade_is_rejected_but_actual_fresh_replay_succeeds(nested):
    import cec_mask_search_reference_mapping as maps
    env,ancestor,qpath,q,state,seen=nested
    assert not maps.receive(ancestor,env[0],q)['ok']
    original=[(p,p.read_bytes())for p in(ancestor,env[0],env[1],env[3],qpath)]
    result=run(nested);assert result['ok'],result
    assert seen==['new_native','new_plan','new_reconstruct','new_receive','print_plan']
    assert result['bounded_composition']['constituents']==chain._phase_names(True)
    assert chain.same_print_replay(result,copy.deepcopy(result))
    assert all(p.read_bytes()==data for p,data in original)


@pytest.mark.parametrize('fault',['native_ok','replay_ok','reconstruct_ok','receive_ok'])
def test_no_old_success_or_epoch_relabelling_can_replace_a_fresh_phase(nested,fault):
    nested[4][fault]=False
    assert not run(nested)['ok']
    assert 'print_plan'not in nested[5]


@pytest.mark.parametrize('fault',['geometry','recipe','ancestor_path','ancestor_hash','factory_floor',
    'grade_path','map_hash','flag_type','print_metadata','print_geometry'])
def test_forged_historical_inputs_are_not_ignored(nested,fault):
    env,ancestor,qpath,q,state,seen=nested
    forged=copy.deepcopy(q)
    if fault in('geometry','map_hash'):forged['records'][0]['geometry']='forged'
    elif fault=='recipe':forged['seed_index']=100
    elif fault=='ancestor_path':forged['binding']['source']=str(env[0])
    elif fault=='ancestor_hash':forged['binding']['source_sha256']='0'*64
    elif fault=='factory_floor':forged['binding']['factory_legend']['height']=.1
    elif fault=='grade_path':forged['binding']['grade']=str(qpath)
    elif fault=='flag_type':forged['positive_leaders_only']=1
    elif fault=='print_metadata':(env[1].parent/'print-context.json').write_text('{}')
    elif fault=='print_geometry':env[6]['physical']=False
    qpath.write_text(json.dumps(forged))
    historical=json.loads(env[3].read_text())
    if fault!='map_hash':historical['reference_mapping_transition']['proposal']=bound(qpath)
    env[3].write_text(json.dumps(historical))
    (env[1].parent/'print-proposal.json').write_bytes(env[3].read_bytes())
    assert not run(nested)['ok']


def test_nested_map_each_constituent_still_has_ten_second_limit(nested,monkeypatch):
    import cec_mask_search_reference_mapping as maps
    now=[0.];monkeypatch.setattr(chain.time,'monotonic',lambda:now[0])
    old=maps.existing_replay
    def slow(*a,**kwargs):
        observer=old(*a,**kwargs);plan=observer.plan
        def delayed():now[0]+=10.;return plan()
        observer.plan=delayed;return observer
    monkeypatch.setattr(maps,'existing_replay',slow)
    result=run(nested)
    assert not result['ok']and result['error']=='annotation_map_plan_deadline'


def positive_recipe(nested,monkeypatch):
    import cec_mask_search_reference_mapping as maps
    env,ancestor,qpath,q,state,seen=nested
    q['positive_leaders_only']=True;qpath.write_text(json.dumps(q))
    historical=json.loads(env[3].read_text())
    historical['reference_mapping_transition']['proposal']=bound(qpath)
    env[3].write_text(json.dumps(historical))
    for path in(env[1],env[2]):(path.parent/'print-proposal.json').write_bytes(env[3].read_bytes())
    original=maps.replay_existing_plan
    def plan(source,**kwargs):
        assert kwargs['positive_leaders_only']is True
        return original(source,env[0],**kwargs)
    def no_duplicate_saved_replay(*args,**kwargs):
        raise AssertionError('positive_plan_must_not_compose_saved_receiving')
    monkeypatch.setattr(maps,'plan',plan)
    monkeypatch.setattr(maps,'replay_existing_plan',no_duplicate_saved_replay)
    return plan


def test_positive_map_plan_and_saved_receive_have_distinct_mandatory_phases(nested,monkeypatch):
    positive_recipe(nested,monkeypatch)
    result=run(nested);assert result['ok'],result
    assert nested[5]==['new_native','new_plan','new_reconstruct','new_receive','print_plan']
    assert result['bounded_composition']['constituents']==chain._phase_names(True)


@pytest.mark.parametrize('fault',['native_ok','replay_ok','reconstruct_ok','receive_ok'])
def test_positive_split_does_not_skip_any_fresh_failure(nested,monkeypatch,fault):
    positive_recipe(nested,monkeypatch);nested[4][fault]=False
    result=run(nested)
    assert not result['ok']and 'print_plan'not in nested[5]


@pytest.mark.parametrize('phase',['plan','reconstruct','receive'])
def test_positive_split_keeps_each_original_ten_second_bound(nested,monkeypatch,phase):
    import cec_mask_search_reference_mapping as maps
    positive_recipe(nested,monkeypatch)
    now=[0.];monkeypatch.setattr(chain.time,'monotonic',lambda:now[0])
    if phase=='plan':
        original=maps.plan
        def slow(*args,**kwargs):
            result=original(*args,**kwargs);now[0]+=10.;return result
        monkeypatch.setattr(maps,'plan',slow)
    else:
        original=maps.saved_replay
        def slow(*args,**kwargs):
            observer=original(*args,**kwargs);method=getattr(observer,phase)
            def delayed():
                result=method();now[0]+=10.;return result
            setattr(observer,phase,delayed);return observer
        monkeypatch.setattr(maps,'saved_replay',slow)
    result=run(nested)
    owner='annotation_'if phase=='plan'else'staged_print_'
    assert not result['ok']and result['error']==owner+'map_'+phase+'_deadline'


def test_actual_ancestor_sidecar_mutation_cannot_be_quarantined_as_runtime(nested,monkeypatch):
    import cec_native_drc_runner as native
    old=native.run
    def mutate(source,*a,**kwargs):
        source.with_suffix('.kicad_prl').write_text('unexpected mutation')
        return old(source,*a,**kwargs)
    monkeypatch.setattr(native,'run',mutate)
    result=run(nested)
    assert not result['ok']and result['error']=='native_map_ancestor_family_mutated'


def test_only_new_successfully_bound_runtime_lock_moves_across_filesystems(nested,monkeypatch,tmp_path):
    import errno,getpass,os,socket
    import cec_native_drc_runner as native
    ancestor=nested[1];old=native.run;lock=ancestor.parent/('~'+ancestor.with_suffix('.kicad_pro').name+'.lck')
    payload=json.dumps(dict(hostname=socket.gethostname(),username=getpass.getuser())).encode()
    def generated(source,*a,**kwargs):
        result=old(source,*a,**kwargs);lock.write_bytes(payload);return result
    rename=os.rename
    def cross_device(source,target,*args,**kwargs):
        # Reports may cross filesystems, but the ownership rename must not.
        if Path(source).parent.stat().st_dev!=Path(target).parent.stat().st_dev:
            raise OSError(errno.EXDEV,'synthetic cross-device boundary')
        return rename(source,target,*args,**kwargs)
    monkeypatch.setattr(native,'run',generated);monkeypatch.setattr(os,'rename',cross_device)
    output=tmp_path/'runtime';output.mkdir()
    proof=chain._native_map_ancestor(ancestor,output/'report.json',Path('/verified-build'),Path('/table'),10.)
    assert proof['ok']and not lock.exists()and(output/'runtime-lock').read_bytes()==payload
    assert ancestor.read_text()=='original-native'


def test_preexisting_runtime_lock_is_never_owned_or_moved(nested,tmp_path):
    ancestor=nested[1];lock=ancestor.parent/('~'+ancestor.with_suffix('.kicad_pro').name+'.lck')
    lock.write_text('another job')
    with pytest.raises(ValueError,match='preexisting_map_ancestor_runtime_lock_refused'):
        chain._native_map_ancestor(ancestor,tmp_path/'report.json',Path('/verified-build'),Path('/table'),10.)
    assert lock.read_text()=='another job'


def test_additive_map_ancestor_is_replayed_at_its_actual_saved_target(nested,tmp_path):
    env,ancestor,qpath,q,state,seen=nested
    declaration=dict(source=bound(ancestor),proposal=bound(qpath),mapped_source=bound(env[0]))
    work=tmp_path/'fresh-map';work.mkdir()
    # Map geometry and original generated IDs belong to env[0], NOT the
    # later copper child. The print owner separately owes strict additive
    # saved receiving before it may use that retained reference association.
    result=chain._fresh_nested_map(env[2],declaration,'renamed',Path('/canonical'),work,
        lambda name,fn:fn(),10.)
    assert set(result)=={'source','proposal','mapped_source'}
    assert result['mapped_source']==bound(env[0])
    assert result['proposal']!=bound(qpath)
    assert seen==['new_native','new_plan']
    # Discovery alone grants no saved success. Consume the real enclosing
    # print owner's two mandatory map stages at the actual mapped boundary.
    receive_discovered_map(env[2],result)
    assert seen==['new_native','new_plan','new_reconstruct','new_receive']


def receive_discovered_map(origin,declaration):
    import cec_nonpolar_print_context as print_op
    replay=print_op.staged_replay(origin,options=dict(library_table='/canonical',
        board_hint='renamed',reference_mapping_transition=declaration),timeout_s=10.)
    assert replay.observation()['state']=='new'
    replay.map_reconstruct()
    assert replay.observation()['state']=='map_reconstructed'
    proof=replay.map_receive()
    assert proof['ok']and proof['complete']and proof['source_bound_projection_exact']
    assert replay.observation()['state']=='map_received'
    return replay


@pytest.mark.parametrize('fault',['hash','same_origin','same_ancestor','extra_field'])
def test_additive_map_ancestry_does_not_relax_historical_boundaries(nested,tmp_path,fault):
    env,ancestor,qpath,q,state,seen=nested
    declaration=dict(source=bound(ancestor),proposal=bound(qpath),mapped_source=bound(env[0]))
    if fault=='hash':declaration['mapped_source']['sha256']='0'*64
    elif fault=='same_origin':declaration['mapped_source']=bound(env[2])
    elif fault=='same_ancestor':declaration['mapped_source']=bound(ancestor)
    else:declaration['accepted']=True
    work=tmp_path/'refused';work.mkdir()
    with pytest.raises(ValueError):chain._fresh_nested_map(env[2],declaration,'renamed',
        Path('/canonical'),work,lambda name,fn:fn(),10.)
