"""Const native caches must never be writable through Python mask factories."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock

import pcbnew
import pytest
import cec_native_layer_masks as masks
import cec_field_coupling as field
from test_field_proposals import track
from test_lastmile import _board


@pytest.mark.parametrize('name',sorted(masks._profile(pcbnew)))
def test_every_native_const_factory_returns_independent_owned_mask(name):
    result=masks.install(pcbnew)
    assert result['native_caches_pristine']
    expected=masks._profile(pcbnew)[name]
    first=getattr(pcbnew.LSET,name)();second=getattr(pcbnew.LSET,name)()
    assert first.thisown and second.thisown and first is not second
    if expected:first.RemoveLayer(min(expected))
    if set(range(pcbnew.PCB_LAYER_ID_COUNT))-expected:
        first.AddLayer(min(set(range(pcbnew.PCB_LAYER_ID_COUNT))-expected))
    assert frozenset(map(int,second.Seq()))==expected
    assert frozenset(map(int,getattr(pcbnew.LSET,name)().Seq()))==expected
    assert masks.install(pcbnew)==result


@pytest.mark.parametrize('count',[2,4,6,8,16,32])
def test_all_copper_count_overload_preserves_native_semantics_and_ownership(count):
    masks.install(pcbnew)
    raw=getattr(pcbnew.LSET,masks._STATE)['originals']['AllCuMask']
    result=pcbnew.LSET.AllCuMask(count)
    assert result.thisown and set(result.Seq())==set(raw(count).Seq())
    result.AddLayer(pcbnew.F_Mask)
    assert not pcbnew.LSET.AllCuMask().Contains(pcbnew.F_Mask)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_mutating_local_pad_mask_does_not_break_native_masked_track_roundtrip(tmp_path,layer):
    b=_board([(5,5,'/renamed/ordinary'),(8,5,'/renamed/ordinary')],edge=(0,0,15,15))
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        mask=pcbnew.LSET.AllCuMask();mask.AddLayer(pcbnew.F_Mask);mask.AddLayer(pcbnew.B_Mask)
        pad.SetLayerSet(mask);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    t=track(b,'/renamed/ordinary',(5,5),(8,5),layer=layer);t.SetHasSolderMask(True)
    prior=field._field_snapshot_inventory(b)
    child=field._save_field_snapshot(b,tmp_path/'board.kicad_pcb')
    assert field._field_snapshot_inventory(child)==prior
    saved=next(iter(child.GetTracks()))
    assert saved.HasSolderMask() and saved.GetLayer()==layer
    assert not pcbnew.LSET.AllCuMask().Contains(pcbnew.F_Mask)
    assert not pcbnew.LSET.AllCuMask().Contains(pcbnew.B_Mask)


def _fresh(code):
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'scripts'))
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env=env,timeout=10)
    assert result.returncode==0,(result.stdout,result.stderr)
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('name,layer',[('AllCuMask','F_Mask'),('InternalCuMask','B_Cu'),
    ('ExternalCuMask','In1_Cu'),('FrontTechMask','F_Cu')])
def test_prior_native_cache_poisoning_is_refused_not_reset(name,layer):
    result=_fresh(f'''
import pcbnew,json
import cec_swig_guard;cec_swig_guard.pin()
import cec_native_layer_masks as masks
raw=pcbnew.LSET.{name};value=raw();assert not value.thisown
value.AddLayer(pcbnew.{layer})
try:masks.install(pcbnew)
except masks.NativeLayerMaskError as exc:reason=str(exc)
else:raise AssertionError('poisoned cache accepted')
assert raw().Contains(pcbnew.{layer})
print(json.dumps(dict(reason=reason,cache_not_reset=True)))
''')
    assert 'cache_corrupted:'+name in result['reason'] and result['cache_not_reset']


def test_raw_factory_alias_after_install_cannot_hide_native_corruption():
    result=_fresh('''
import pcbnew,json
import cec_swig_guard;cec_swig_guard.pin()
import cec_native_layer_masks as masks
raw=pcbnew.LSET.AllCuMask;masks.install(pcbnew);raw().AddLayer(pcbnew.F_Mask)
reasons=[]
for action in (masks.install,pcbnew.LSET.AllCuMask):
    try:action()
    except masks.NativeLayerMaskError as exc:reasons.append(str(exc))
assert len(reasons)==2
print(json.dumps(dict(reasons=reasons)))
''')
    assert all('cache_corrupted:AllCuMask' in reason for reason in result['reasons'])


def test_replaced_factory_is_refused():
    masks.install(pcbnew)
    with mock.patch.object(pcbnew.LSET,'AllCuMask',return_value=pcbnew.LSET()):
        with pytest.raises(masks.NativeLayerMaskError,match='factory_replaced:AllCuMask'):
            masks.install(pcbnew)


def test_unavailable_native_reload_has_explicit_failure_not_attribute_error(tmp_path):
    b=_board([(5,5,'/renamed/ordinary')],edge=(0,0,15,15))
    with mock.patch.object(pcbnew,'LoadBoard',return_value=None):
        with pytest.raises(field._ProposalUnknown,match='native_field_snapshot_reload_failed'):
            field._save_field_snapshot(b,tmp_path/'board.kicad_pcb')
