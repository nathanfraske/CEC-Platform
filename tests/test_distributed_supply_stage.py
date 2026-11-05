"""Scope rejection, real native geometry, and mandatory whole-stage admission.

Synthetic current/Source compilation is an explicit fixture boundary only;
no mocked native/field/intake success can publish a board.
"""
from unittest import mock
import copy
import json
import shutil
import pcbnew
import pytest
import cec_distributed_supply as supply
import cec_distributed_supply_prefix as prefixes
import cec_distributed_supply_stage as operator
import cec_received_private_stage as stage
from test_distributed_supply import authority
from test_distributed_supply_prefix import native_fixture,compile_boundary


@pytest.mark.parametrize('value',[True,False,0,-1,11,float('nan'),float('inf'),'10'])
def test_only_real_bounded_scope_lease(value):
    with pytest.raises(ValueError):operator._budget(value)


@pytest.mark.parametrize('net',[None,'',False,3])
def test_supply_stage_requires_explicit_net_before_namespace(tmp_path,net):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator'):
        stage.run(tmp_path/'absent',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator='distributed_supply',net=net)
    assert not(tmp_path/'out').exists()


def test_supply_scope_does_not_accept_caller_pad_whitelist(tmp_path):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator'):
        stage.run(tmp_path/'absent',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator='distributed_supply',net='/rail',pad_uuid='caller')


@pytest.mark.parametrize('compiled',[False,True])
def test_supply_worker_refusals_never_reach_receiving_or_publication(tmp_path,monkeypatch,compiled):
    from test_lastmile import _board
    source=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source),_board([],edge=(0,0,20,20)))
    monkeypatch.setattr(stage,'identity',lambda *a:{'epoch':'exact'})
    seen=[]
    def plan(*a,**kw):seen.append(('plan',kw));return {'complete':compiled}
    def construct(*a,**kw):seen.append(('construct',kw));return {'complete':False}
    monkeypatch.setattr(operator,'plan',plan);monkeypatch.setattr(operator,'construct_private',construct)
    monkeypatch.setattr(operator,'receive',lambda *a,**kw:pytest.fail('no saved complete candidate'))
    result=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'epoch':'exact'},operator='distributed_supply',net='/source-rail'))
    assert result['gates']=={} and result['reason']=='finite_proposal_incomplete'
    assert [r[0]for r in seen]==(['plan','construct']if compiled else ['plan'])
    assert all(r[1]['timeout_s']==10. for r in seen)
    assert not(tmp_path/'publication.json').exists()


def test_missing_current_contract_never_becomes_ordinary_or_default_geometry(tmp_path):
    board,net=native_fixture(tmp_path)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    with mock.patch.object(supply,'audit',return_value={'contracts':{},'refusals':{net:'missing'}}),\
            mock.patch.object(prefixes,'prepare',side_effect=AssertionError('no current authority')):
        result=operator.plan(board,source,board_hint='synthetic',net=net)
    assert not result['complete'] and not result['current_authority_changed']


@pytest.mark.parametrize('before,after,expected',[
    ([['a','b'],['c']],[['a','b','c']],True),
    ([['a','b'],['c']],[['a','c'],['b']],False),
    ([['a'],['b']],[['a']],False),
])
def test_every_old_native_partition_survives(before,after,expected):
    assert operator._partitions_survive(before,after)is expected


def test_only_known_generated_export_hash_may_change_in_fresh_plan_identity():
    import copy
    import cec_source_netlist_semantics as semantic
    p=dict(source_authority=dict(hierarchy={'source':'b'*64},export=dict(
        netlist_sha256='a'*64,exporter='/actual/cli',exporter_sha256='b'*64,
        netlist_semantic_policy=semantic.POLICY,netlist_semantic_sha256='c'*64)))
    q=copy.deepcopy(p);q['source_authority']['export']['netlist_sha256']='d'*64
    assert operator._replay_identity(p)==operator._replay_identity(q)
    assert p['source_authority']['export']['netlist_sha256']=='a'*64
    q['source_authority']['export']['netlist_semantic_sha256']='e'*64
    assert operator._replay_identity(p)!=operator._replay_identity(q)
    q['source_authority']['export'].pop('netlist_semantic_policy')
    with pytest.raises(ValueError):operator._replay_identity(q)


def test_exact_json_transport_is_replay_equivalent_without_mutating_the_proposal():
    p=dict(contract=dict(routing_layers=('F.Cu','B.Cu'),amps=.25),
        source_binding={'native': ('one', 'two')}, complete=True)
    before=copy.deepcopy(p)
    q=json.loads(json.dumps(p))
    assert operator._replay_identity(p)==operator._replay_identity(q)
    assert p==before and type(p['contract']['routing_layers'])is tuple
    assert type(q['contract']['routing_layers'])is list


@pytest.mark.parametrize('old,new',[
    (True,1),(True,1.0),(1,1.0),(False,0),(False,0.0),
    (['F.Cu','B.Cu'],['B.Cu','F.Cu']),
    (['F.Cu'],['F.Cu','B.Cu']),(.25,.2),('Source','source'),
])
def test_replay_keeps_actual_values_types_and_array_order_exact(old,new):
    assert operator._replay_identity({'bound':old})!=operator._replay_identity({'bound':new})


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_json_scope_is_never_a_replay_identity(value):
    with pytest.raises(ValueError):operator._replay_identity({'amps':value})


@pytest.mark.parametrize('turn,layer',[(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),(2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
def test_public_plan_json_construct_and_saved_receive_round_trip(tmp_path,turn,layer):
    board,net=native_fixture(tmp_path,turn,layer)
    source=tmp_path/'source.kicad_pcb';candidate=tmp_path/'child.kicad_pcb'
    pcbnew.SaveBoard(str(source),board)
    shutil.copy2(source,candidate)
    real_audit=supply.audit
    def audit(b,**kwargs):
        kwargs['netclass_resolver']=lambda n:dict(name='Power',track_width=.5,clearance=.2)
        return real_audit(b,**kwargs)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary),\
            mock.patch.object(supply,'audit',side_effect=audit):
        # Only canonical Source compilation is a fixture boundary. The
        # public constructor, saved literal copper and independent native
        # partitions/prefix receiving all execute after real JSON transport.
        proposal=operator.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',net=net)
        assert proposal['complete']
        wire=json.loads(json.dumps(proposal))
        built=operator.construct_private(source,candidate,wire,board_hint='synthetic',timeout_s=5.)
        assert built['complete'],built
        received=operator.receive(source,candidate,board_hint='synthetic',net=net,timeout_s=5.)
    assert received['ok']and received['complete'],received
    assert received['source_components']==2 and received['candidate_components']==1
    assert not received['current_qualified']and not received['release_authority']
    assert received['whole_shared_stage_still_required']


@pytest.mark.parametrize('mutation',[
    'source_sha','binding','current','width','layer','complete_type','authority_type',
])
def test_changed_serialized_scope_is_rejected_before_geometry(tmp_path,mutation):
    board,net=native_fixture(tmp_path)
    source=tmp_path/'source.kicad_pcb';candidate=tmp_path/'child.kicad_pcb'
    pcbnew.SaveBoard(str(source),board);shutil.copy2(source,candidate)
    original=source.read_bytes()
    real_audit=supply.audit
    def audit(b,**kwargs):
        kwargs['netclass_resolver']=lambda n:dict(name='Power',track_width=.5,clearance=.2)
        return real_audit(b,**kwargs)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary),\
            mock.patch.object(supply,'audit',side_effect=audit):
        proposal=operator.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',net=net)
        assert proposal['complete']
        wire=json.loads(json.dumps(proposal))
        if mutation=='source_sha':wire['source_sha256']='0'*64
        elif mutation=='binding':wire['source_binding']='forged:'+wire['source_binding']
        elif mutation=='current':wire['contract']['current_authority']['amps']/=2
        elif mutation=='width':wire['contract']['required_by_layer_mm']['F.Cu']/=2
        elif mutation=='layer':wire['contract']['routing_layers'].append('unbound-face')
        elif mutation=='complete_type':wire['complete']=1
        elif mutation=='authority_type':wire['source_authority']['fresh_test_source_export']=1
        else:raise AssertionError(mutation)
        with mock.patch.object(supply,'construct',side_effect=AssertionError('forged scope reached geometry')):
            with pytest.raises(ValueError,match='fresh_exact_supply_scope_required'):
                operator.construct_private(source,candidate,wire,board_hint='synthetic',timeout_s=5.)
    assert source.read_bytes()==candidate.read_bytes()==original


@pytest.mark.parametrize('turn,layer',[(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),(2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
def test_saved_source_qualified_prefix_scope_replays_real_geometry(tmp_path,turn,layer):
    board,net=native_fixture(tmp_path,turn,layer)
    source=tmp_path/'source.kicad_pcb';candidate=tmp_path/'child.kicad_pcb'
    pcbnew.SaveBoard(str(source),board)
    real_audit=supply.audit
    def audit(b,**kwargs):
        kwargs['netclass_resolver']=lambda n:dict(name='Power',track_width=.5,clearance=.2)
        return real_audit(b,**kwargs)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary),\
            mock.patch.object(supply,'audit',side_effect=audit):
        # The Source fixture only replaces canonical compilation. Native
        # routing, native saved partitions and full-current prefix receiver
        # execute, without faking the whole-stage gates.
        proposal=operator.plan(board,source,board_hint='synthetic',net=net)
        assert proposal['complete']
        report=supply.construct(board,board_hint='synthetic',include_nets=[net],
            timeout_s=5.,allow_supply_prefixes=True)
        assert report['created_uuids']
        pcbnew.SaveBoard(str(candidate),board)
        received=operator.receive(source,candidate,board_hint='synthetic',net=net)
    assert received['ok'],received
    assert received['source_components']==2 and received['candidate_components']==1
    assert received['saved_prefix_receiving']['track_uuids']
    assert not received['current_qualified'] and not received['release_authority']
    assert received['whole_shared_stage_still_required']
    assert not stage.admitted({'operator':True})
