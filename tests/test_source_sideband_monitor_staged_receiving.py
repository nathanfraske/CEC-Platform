"""Independent normal-tap composition, never local-via/process authority."""
import time

import pcbnew
import pytest
import cec_source_sideband_monitor_tap as op
import cec_additive_route_receiving as additive
import cec_native_partition_pair as partitions
import cec_route_proposal_guard as guard
import cec_field_coupling as field
import cec_fr as fr
import cec_source_literal_additions as literal
from test_source_sideband_monitor_tap import fixture, child, receive


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mode',['barrel','two_vias'])
def test_real_normal_tap_stages_without_local_authority(tmp_path,monkeypatch,quarter,mode):
    data=fixture(tmp_path,monkeypatch,quarter=quarter,mode=mode,planes=True)
    candidate=child(data,tmp_path);before=[p.read_bytes()for p in(data[0],candidate)]
    original=op._live_bindings;barriers=[]
    def live(*args,**kwargs):
        original(*args,**kwargs);barriers.append(time.monotonic())
    monkeypatch.setattr(op,'_live_bindings',live)
    r=receive(data,candidate,staged_receiving=True)
    assert r['ok']and r['complete'],r
    assert r['staged_receiving']is True and r['allow_source_local_pofv']is False
    assert r['bounded_receiving_stages']==2 and r['composed_budget_s']==20
    assert r['completed_receiving_stages']==['Source_geometry_field','independent_saved_replay_partitions']
    assert r['failed_stage']is None and len(barriers)==2
    assert all(0<t<10 for t in r['stage_timings_s'].values())
    assert 2<r['native_route_proposal_guard']['per_proposal_preflight_cap_s']<=10
    assert r['new_normal_vias']==(1 if mode=='barrel'else 2)and r['new_local_vias']==0
    assert not r['factory_group_delta_uuids']and not r.get('Source_local_POFV_vias')
    assert r['exact_saved_additive_receiving']['existing_ground_fill_matches_independent_native_replay']
    assert r['whole_native_Source_partitions']['preserved']
    assert not any(r[k]for k in('ordinary_reclassification','quiet_reclassification','new_current_budget',
        'current_qualified','barrel_qualified','voltage_qualified','release_authority','routing_admitted'))
    assert before==[p.read_bytes()for p in(data[0],candidate)]


@pytest.mark.parametrize('explicit',[False,True])
def test_legacy_default_and_explicit_false_keep_single_shared_lease_and_two_second_preflight(tmp_path,monkeypatch,explicit):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    r=receive(data,candidate,**({'staged_receiving':False}if explicit else{}))
    assert r['ok']and r['complete'],r
    assert r['bounded_receiving_stages']==1 and r['composed_budget_s']==10
    assert not r['staged_receiving']and not r['allow_source_local_pofv']
    assert r['native_route_proposal_guard']['per_proposal_preflight_cap_s']==2.
    assert r['completed_receiving_stages']==['Source_geometry_field']and r['failed_stage']is None
    assert set(r['stage_timings_s'])=={'Source_geometry_field'}


@pytest.mark.parametrize('staged',[False,True])
def test_legacy_local_mode_remains_two_stages_independent_of_new_option(tmp_path,monkeypatch,staged):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    r=receive(data,candidate,allow_source_local_pofv=True,staged_receiving=staged)
    assert r['ok']and r['complete'],r
    assert r['bounded_receiving_stages']==2 and r['allow_source_local_pofv']is True
    assert r['staged_receiving']is staged
    assert r['completed_receiving_stages']==['Source_geometry_field','independent_saved_replay_partitions']


@pytest.mark.parametrize('value',[None,0,1,0.,1.,'true',[],{},object()])
def test_strict_staging_boolean_checked_before_paths(value):
    with pytest.raises(ValueError,match='explicit_sideband_staged_receiving_mode_required'):
        op.receive('not-source','not-child',board_hint='none',connector_pad_uuids=['a','b'],
                   target_pad_uuid='c',staged_receiving=value)


@pytest.mark.parametrize('result',[False,None])
def test_failed_or_unknown_first_stage_never_calls_saved_receiver(tmp_path,monkeypatch,result):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path);calls=[]
    monkeypatch.setattr(guard.RouteProposalGuard,'__call__',lambda *a:result)
    def forbidden(*a,**kw):calls.append(True);raise AssertionError('failed first stage cannot start second')
    monkeypatch.setattr(additive,'receive',forbidden)
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and not r['complete']and not calls,r
    assert r['failed_stage']=='Source_geometry_field'and not r['completed_receiving_stages']
    assert set(r['stage_timings_s'])=={'Source_geometry_field'}
    assert any('proposal_guard_refused'in e for e in r['errors'])


@pytest.mark.parametrize('fault',['hierarchy','exporter','Source','candidate','profile','code','deadline'])
def test_first_live_barrier_rejects_binding_drift_or_exhausted_lease_before_stage_two(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path);calls=[]
    original=guard.RouteProposalGuard.__call__;clock=time.monotonic;offset=[0.]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock()+offset[0])
    def changed(self,*a,**kw):
        accepted=original(self,*a,**kw)
        assert accepted is True,self.report()
        if fault=='deadline':offset[0]=20.
        elif fault=='code':monkeypatch.setattr(op.force,'_code_identity',lambda:{'changed':'untrusted epoch'})
        else:
            path={'hierarchy':data[1],'exporter':tmp_path/'real-export-boundary',
                  'Source':data[0],'candidate':candidate,
                  'profile':data[0].with_suffix('.kicad_pro')}[fault]
            path.write_bytes(path.read_bytes()+b'\n; live binding changed\n')
        return accepted
    def forbidden(*a,**kw):calls.append(True);raise AssertionError('changed first-stage binding')
    monkeypatch.setattr(guard.RouteProposalGuard,'__call__',changed)
    monkeypatch.setattr(additive,'receive',forbidden)
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and not r['complete']and not calls,r
    assert r['failed_stage']=='Source_geometry_field'and not r['completed_receiving_stages']
    assert set(r['stage_timings_s'])=={'Source_geometry_field'}
    assert any(('deadline'if fault=='deadline'else'changed')in e for e in r['errors']),r


@pytest.mark.parametrize('fault',['failed','incomplete','Ground_replay','deadline'])
def test_independent_saved_stage_remains_mandatory_and_has_own_failure_attribution(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path)
    original=additive.receive;clock=time.monotonic;offset=[0.];calls=[]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock()+offset[0])
    def changed(*a,**kw):
        assert 0<kw['timeout_s']<=10
        r=original(*a,**kw);assert r['ok']and r['complete'],r
        calls.append(True)
        if fault=='failed':r['ok']=False
        elif fault=='incomplete':r['complete']=False
        elif fault=='Ground_replay':r['existing_ground_fill_matches_independent_native_replay']=False
        else:offset[0]=20.
        return r
    monkeypatch.setattr(additive,'receive',changed)
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and not r['complete']and calls==[True],r
    assert r['failed_stage']=='independent_saved_replay_partitions'
    assert r['completed_receiving_stages']==['Source_geometry_field']
    assert set(r['stage_timings_s'])=={'Source_geometry_field','independent_saved_replay_partitions'}
    assert any(('deadline'if fault=='deadline'else'not_independently_recomputed'if fault=='Ground_replay'else'not_received')in e for e in r['errors']),r


def test_final_source_live_barrier_not_replaced_by_first_stage_success(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path);original=partitions.compare
    def changed(*a,**kw):
        r=original(*a,**kw);assert r['available']and r['preserved'],r
        data[1].write_text(data[1].read_text()+'\n; changed after native partition comparison\n')
        return r
    monkeypatch.setattr(partitions,'compare',changed)
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and r['failed_stage']=='independent_saved_replay_partitions',r
    assert r['completed_receiving_stages']==['Source_geometry_field']
    assert any('changed'in e for e in r['errors'])


@pytest.mark.parametrize('fault',['small_via','factory_group','unrelated_group'])
def test_normal_staging_never_acquires_local_process_or_group_permission(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch,mode='barrel')
    candidate=child(data,tmp_path)
    b=pcbnew.LoadBoard(str(candidate));old=pcbnew.LoadBoard(str(data[0]))
    old_ids={t.m_Uuid.AsString()for t in old.GetTracks()}
    via=next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA'and t.m_Uuid.AsString()not in old_ids)
    text=candidate.read_text();nodes=literal._inventory(text)[0];uid=via.m_Uuid.AsString()
    node=nodes[uid][2]
    if fault=='small_via':
        assert '(size 0.6)'in node and '(drill 0.3)'in node
        candidate.write_text(text.replace(node,node.replace('(size 0.6)','(size 0.4)').replace('(drill 0.3)','(drill 0.2)')))
    else:
        group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP if fault=='factory_group'else'unrelated')
        b.Add(group);group.AddItem(via);via.SetLocked(True)
        # Extract ONLY incoming nodes from the native edit. All retained Source
        # fields stay literal, so these tests reach process/group authorization
        # rather than being stopped by incidental native serialization drift.
        native=tmp_path/'incoming-only-native.kicad_pcb';field._save_field_snapshot(b,native)
        changed=literal._inventory(native.read_text())[0]
        altered=text.replace(node,changed[uid][2]);end=altered.rfind(')')
        candidate.write_text(altered[:end]+'\n'+changed[group.m_Uuid.AsString()][2]+'\n'+altered[end:])
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and r['failed_stage']=='Source_geometry_field',r
    expected='below_Source_absolute_or_class_floor'if fault=='small_via'else'only_bounded_new_sideband_tap_copper_required'
    assert any(expected in e for e in r['errors']),r['errors']
    assert not r['allow_source_local_pofv']and not r.get('Source_local_POFV_vias')


@pytest.mark.parametrize('fault',['wrong_net','source_cut','pose','width','orphan'])
def test_explicit_staging_does_not_skip_saved_geometry_or_source_scope(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);candidate=child(data,tmp_path,fault=fault)
    r=receive(data,candidate,staged_receiving=True)
    assert not r['ok']and r['errors'],r
    assert not r['completed_receiving_stages']and r['failed_stage']=='Source_geometry_field'


def test_unchanged_board_is_not_a_tap_even_in_staged_mode(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch)
    r=receive(data,data[0],staged_receiving=True)
    assert not r['ok']and r['failed_stage']=='Source_geometry_field',r
    assert any('distinct_saved_sideband_tap_paths'in e for e in r['errors'])
