"""Explicit targets narrow proposals, not saved-source receiving authority."""
import time
import ast
import inspect
import pcbnew
import pytest
import cec_ground_component_join as join
import cec_ground_mesh_entry as mesh
import cec_ground_local_mesh_entry as local
import cec_force_current as force
from test_ground_component_join import fixture,construct


def ground_pad(owner):
    return next(p for p in owner.Pads() if p.GetNetname()=='GND')


def test_none_preserves_exact_context_and_all_partitions(tmp_path):
    b,source,owner,*_=fixture(tmp_path)
    ctx=join._context(b,'synthetic',time.monotonic()+10)
    assert join._target_context(ctx,None) is ctx
    scoped=join._target_context(ctx,force._uid(ground_pad(owner)))
    assert len(scoped['islands'])==1
    for key in ('parts','ground','root','live','requests'):
        assert scoped[key] is ctx[key]
    assert source.read_bytes()


@pytest.mark.parametrize('fault',['missing','foreign','rooted','dnp','untyped','empty','wrong_type'])
def test_target_requires_fresh_original_typed_detached_ground(tmp_path,fault):
    b,source,owner,cap,via=fixture(tmp_path)
    pad=ground_pad(owner);uid=force._uid(pad)
    if fault=='dnp':owner.SetDNP(True)
    ctx=join._context(b,'synthetic',time.monotonic()+10)
    if fault=='missing':uid='not-a-source-uuid'
    elif fault=='foreign':uid=force._uid(next(p for p in owner.Pads() if p.GetNetname()!='GND'))
    elif fault=='rooted':
        ctx=dict(ctx,islands=[])
    elif fault=='untyped':ctx=dict(ctx,requests={})
    elif fault=='empty':uid=''
    elif fault=='wrong_type':uid=True
    with pytest.raises(ValueError):join._target_context(ctx,uid)


@pytest.mark.parametrize('module',[join,mesh,local])
def test_all_planners_fail_closed_for_stale_target(tmp_path,module):
    b,source,*_=fixture(tmp_path);before=source.read_bytes()
    q=module.plan(b,board_hint='synthetic',pad_uuid='missing',timeout_s=1.)
    assert not q['complete'] and q.get('error'),q
    assert source.read_bytes()==before


@pytest.mark.parametrize('quarter',[0,1])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_target_merge_is_additional_whole_source_proof(tmp_path,quarter,layer):
    source,child,q,_=construct(tmp_path,quarter=quarter,layer=layer)
    parent=pcbnew.LoadBoard(str(source))
    ctx=join._context(parent,'synthetic',time.monotonic()+10)
    uid=next(force._uid(ctx['live'][k]) for k in ctx['islands'][0]
        if ctx['live'][k].GetClass()=='PAD')
    r=join.receive_target(source,child,board_hint='synthetic',pad_uuid=uid)
    assert r['ok'] and r['whole_saved_receiver_still_required'],r
    r=join.receive_target(source,source,board_hint='synthetic',pad_uuid=uid)
    assert not r['ok'] and 'not_rooted' in r['error'],r


def test_scope_selects_later_island_without_dropping_source_authority(tmp_path):
    b,source,owner,*_=fixture(tmp_path)
    ctx=join._context(b,'synthetic',time.monotonic()+10)
    target=force._uid(ground_pad(owner));island=ctx['islands'][0]
    # A blocked earlier portfolio member must not consume this target's lease.
    other=ctx['root']
    ctx=dict(ctx,islands=[other,island])
    scoped=join._target_context(ctx,target)
    assert scoped['islands']==[island]
    assert scoped['parts'] is ctx['parts'] and scoped['requests'] is ctx['requests']


def test_target_planner_constructs_only_eligible_original_component(tmp_path):
    b,source,owner,*_=fixture(tmp_path)
    uid=force._uid(ground_pad(owner));before=source.read_bytes()
    q=join.plan(b,board_hint='synthetic',pad_uuid=uid)
    assert q['complete'] and q['target_pad_uuid']==uid,q
    join.construct_private(b,q,board_hint='synthetic')
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['power_model','unknown_model'])
def test_real_manufacturer_typing_not_caller_target_authority(tmp_path,fault):
    b,source,owner,*_=fixture(tmp_path)
    uid=force._uid(ground_pad(owner))
    owner.SetValue('TPS54302' if fault=='power_model' else 'UNKNOWN_COMPONENT')
    # Contradictory/unknown native metadata cannot grant target privileges.
    q=join.plan(b,board_hint='synthetic',pad_uuid=uid)
    assert not q['complete'] and q.get('error'),q


def test_stage_target_refusal_precedes_shared_admission_and_publication():
    import cec_received_private_stage as stage
    source=inspect.getsource(stage.worker)
    tree=ast.parse(source)
    target=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='receive_target')
    invariant=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='_invariant_worker')
    assert target.lineno<invariant.lineno
    refusal=next(n for n in ast.walk(tree) if isinstance(n,ast.Return)
        and 'targeted_saved_merge_refused' in ast.unparse(n))
    assert target.lineno<refusal.lineno<invariant.lineno
    assert 'gates={}' in ast.unparse(refusal)


def test_ground_target_never_bypasses_source_epoch_preflight(tmp_path):
    import cec_received_private_stage as stage
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.write_bytes(b'original source');output=tmp_path/'output'
    with pytest.raises(ValueError,match='expected_source_epoch'):
        stage.run(source,output,board_hint='synthetic',expected_source_sha256='0'*64,
            operator='ground',pad_uuid='caller-cannot-authorize-this')
    assert source.read_bytes()==b'original source' and not output.exists()
