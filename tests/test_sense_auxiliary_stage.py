"""A stranded typed package strap is not a generic force-net routing waiver."""
import ast
import json
from pathlib import Path
import time
from unittest import mock

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_native_items as native
import cec_sense_auxiliary_stage as stage
from test_field_proposals import track
from test_measurement_auxiliary_cut import fixture as base_fixture


def fixture(tmp_path,quarter=0,back=False,fault=None):
    board,source,fp,strap,departure=base_fixture(tmp_path,quarter,back)
    native.discard_items(board,[strap,departure])
    root,peer=fp.FindPadByNumber('9'),fp.FindPadByNumber('8')
    if fault=='unknown_model':fp.SetValue('UNKNOWN_PACKAGE')
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='locked_owner':fp.SetLocked(True)
    elif fault=='wrong_source_net':peer.SetNet(board.FindNet('OTHER'))
    elif fault=='source_force_pickup':
        fixed=board.FindFootprintByReference('unrelated_external_boundary').FindPadByNumber('1')
        t=pcbnew.PCB_TRACK(board);t.SetStart(peer.GetPosition());t.SetEnd(fixed.GetPosition())
        t.SetNet(peer.GetNet());t.SetLayer(next(iter(peer.GetLayerSet().CuStack())))
        t.SetWidth(200000);board.Add(t)
    elif fault=='interior_tap':
        assert quarter==0 and not back
        track(board,root.GetNetname(),(10.25,8),(10.25,12),width=.1)
    field._save_field_snapshot(board,source)
    candidate=tmp_path/'candidate.kicad_pcb'
    child=pcbnew.LoadBoard(str(source));owner=child.FindFootprintByReference(fp.GetReference())
    a,b=owner.FindPadByNumber('8'),owner.FindPadByNumber('9')
    edge=pcbnew.PCB_TRACK(child);edge.SetStart(a.GetPosition());edge.SetEnd(b.GetPosition())
    edge.SetNet(b.GetNet());edge.SetLayer(next(iter(b.GetLayerSet().CuStack())))
    edge.SetWidth(250000);child.Add(edge)
    if fault=='wide':edge.SetWidth(400000)
    elif fault=='wrong_new_net':edge.SetNet(child.FindNet('OTHER'))
    elif fault=='extra_copper':track(child,'OTHER',(2,2),(3,2),width=.2)
    elif fault=='via':
        v=pcbnew.PCB_VIA(child);v.SetPosition(pcbnew.VECTOR2I_MM(2,2))
        v.SetWidth(600000);v.SetDrill(300000);v.SetNet(b.GetNet());child.Add(v)
    elif fault=='split_literal':
        start,end=pcbnew.VECTOR2I(edge.GetStart()),pcbnew.VECTOR2I(edge.GetEnd())
        middle=pcbnew.VECTOR2I((start.x+end.x)//2,(start.y+end.y)//2)
        edge.SetEnd(middle)
        other=pcbnew.PCB_TRACK(child);other.SetStart(middle);other.SetEnd(end)
        other.SetNet(edge.GetNet());other.SetLayer(edge.GetLayer());other.SetWidth(edge.GetWidth());child.Add(other)
    field._save_field_snapshot(child,candidate)
    return source,candidate


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_typed_literal_straps_rename_rotate_and_reflect(tmp_path,quarter,back):
    source,candidate=fixture(tmp_path,quarter,back)
    old={p:p.read_bytes()for p in (source,candidate)}
    result=stage.receive_straps(source,candidate)
    assert result['ok']and result['complete']and len(result['proofs'])==1
    assert result['source_ends_stranded_manufacturer_input_copper']
    assert result['no_unowned_same_net_interior_contacts']
    assert not result['current_authority']and not result['kelvin_qualified']and not result['release_authority']
    assert old=={p:p.read_bytes()for p in old}


@pytest.mark.parametrize('fault',['unknown_model','DNP','locked_owner','wrong_source_net',
    'source_force_pickup','interior_tap','wide','extra_copper','via','split_literal'])
def test_unknown_external_wide_multileg_or_extra_scope_refuses(tmp_path,fault):
    source,candidate=fixture(tmp_path,fault=fault)
    with pytest.raises(ValueError):stage.receive_straps(source,candidate)


def test_native_snapshot_refuses_foreign_assigned_short_before_any_receiving(tmp_path):
    # Even the producer's raw save/reload boundary must refuse authored net
    # evidence that native loading would normalize through a foreign short.
    with pytest.raises(field._ProposalUnknown,match='changed_saved_identity'):
        fixture(tmp_path,fault='wrong_new_net')


@pytest.mark.parametrize('timeout',[True,0,-1,11,float('nan')])
def test_receiving_has_finite_explicit_ten_second_bound(timeout):
    with pytest.raises(ValueError):stage.receive_straps('absent','absent',timeout_s=timeout)


def test_noop_worker_never_grandfathers_whole_nets_or_copies_source(tmp_path):
    source,_=fixture(tmp_path)
    import cec_sense_auxiliary as aux
    with mock.patch.object(aux,'construct',return_value={'generated_item_count':0}),\
            mock.patch.object(force,'_copy_family',side_effect=AssertionError('no-op must not save child')):
        result=stage._worker(str(source),'synthetic',str(tmp_path),1.)
    assert result['ok']and not result['prefix_accepted']and result['selected']==str(source)
    assert result['completed_nets']==[]and not result['release_authority']


def test_actual_pipeline_executes_received_prefix_before_ordinary_tier():
    source=(Path(stage.__file__).parent/'cec_synth_pipeline.py').read_text()
    a=source.index('"automatic_auxiliary_sense_strap_tier", True')
    b=source.index('"automatic_power_distribution_tier", True',a)
    block=source[a:b]
    assert 'cec_sense_auxiliary_stage.run('in block
    assert '_auxiliary_result.get("prefix_accepted")'in block
    assert 'route_input = _auxiliary_result["selected"]'in block
    assert 'completed_nets'not in block
    tree=ast.parse(Path(stage.__file__).read_text())
    worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_worker_impl')
    text=ast.unparse(worker)
    assert text.index('_receive_full(')<text.index('prefix_accepted=True')


def test_worker_refusal_retains_traceback_and_never_selects_child(tmp_path):
    with mock.patch.object(stage,'_worker_impl',side_effect=ValueError('exact native refusal')):
        report=stage._worker('immutable-parent','synthetic',str(tmp_path),1.)
    assert not report['ok']and not report['prefix_accepted']and report['selected']=='immutable-parent'
    assert 'exact native refusal'in report['traceback']
    assert json.loads((tmp_path/'worker-receiving.json').read_text())==report


def test_partial_receiving_evidence_survives_later_native_failure(tmp_path):
    def fail(source,candidate,hint,directory,report):
        report['source_typed_auxiliary_isolation']={'ok':True}
        raise ValueError('later native tool failed')
    with mock.patch.object(stage,'_receive_full_checks',side_effect=fail):
        with pytest.raises(ValueError,match='later native tool failed'):
            stage._receive_full('source','candidate','synthetic',tmp_path/'checks')
    saved=json.loads((tmp_path/'checks'/'receiving.json').read_text())
    assert not saved['ok'] and saved['source_typed_auxiliary_isolation']['ok']
    assert 'later native tool failed' in saved['traceback']


def test_refused_empty_constructor_is_not_reported_as_success(tmp_path):
    source,_=fixture(tmp_path)
    import cec_sense_auxiliary as aux
    with mock.patch.object(aux,'construct',return_value={'generated_item_count':0,'refused':[{'reason':'blocked'}]}):
        report=stage._worker(str(source),'synthetic',str(tmp_path),1.)
    assert not report['ok'] and report['status']=='construction_refused'
    assert not report['prefix_accepted'] and report['selected']==str(source)
