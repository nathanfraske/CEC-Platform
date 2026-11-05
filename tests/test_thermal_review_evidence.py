"""Rendered/reported thermal screens may not hide dropped current or layers."""
from types import SimpleNamespace
from unittest import mock
import pytest
import cec_thermal_overlay as overlay


@pytest.mark.parametrize('layers',[(0,31),(0,1,2,31),(0,1,2,3,4,31)])
def test_all_native_enabled_copper_layers_are_renderable(layers):
    board=mock.Mock()
    board.GetEnabledLayers.return_value.CuStack.return_value=layers
    assert overlay._thermal_copper_layers(board)==layers


@pytest.mark.parametrize('entry',['render_detail_blend','render_thermal_detail'])
@pytest.mark.parametrize('dropped',[{}, {'RAIL_Z':'not injected'}])
def test_render_summary_cannot_claim_thermal_pass_after_dropped_current(entry,dropped):
    result=SimpleNamespace(max_T=55.,ambient=50.,grid_mm=.3,meta={
        'operation_complete':True,'budget_exhausted':False,
        'thermal_iterations_completed':1},
        per_net_maxT={},nets_requested={'RAIL_Z':.5},nets_dropped=dropped,nets_absent={})
    with mock.patch.object(overlay,'_solve_thermal',return_value=(result,'filled','test')):
        with mock.patch.object(overlay,'_draw_detail_blend'):
            report=getattr(overlay,entry)('input.kicad_pcb','output.png')
    assert report['verdict']==('FAIL' if dropped else 'PASS')
    assert report['current_injection_complete'] is (not bool(dropped))
    assert report['component_temperature_qualified'] is False


@pytest.mark.parametrize('entry',['render_detail_blend','render_thermal_detail'])
@pytest.mark.parametrize('metadata',[
    {},
    {'operation_complete':False,'budget_exhausted':True,'thermal_iterations_completed':1},
    {'operation_complete':True,'budget_exhausted':True,'thermal_iterations_completed':1},
    {'operation_complete':1,'budget_exhausted':False,'thermal_iterations_completed':1},
    {'operation_complete':True,'budget_exhausted':False,'thermal_iterations_completed':True},
    {'operation_complete':True,'budget_exhausted':False,'thermal_iterations_completed':0},
])
def test_retained_or_unproven_cool_field_cannot_render_as_pass(entry,metadata):
    result=SimpleNamespace(max_T=55.,ambient=50.,grid_mm=.3,meta=metadata,
        per_net_maxT={},nets_requested={'POWER':1.},nets_dropped={},nets_absent={})
    with mock.patch.object(overlay,'_solve_thermal',return_value=(result,'filled','test')):
        with mock.patch.object(overlay,'_draw_detail_blend'):
            report=getattr(overlay,entry)('input.kicad_pcb','output.png')
    assert report['verdict']=='FAIL'
    assert report['operation_complete'] is False
    assert report['current_injection_complete'] is True


@pytest.mark.parametrize('rise',[0.,0.01,float('nan'),float('inf')])
def test_completed_impossible_temperature_field_cannot_be_green(rise):
    result=SimpleNamespace(max_T=50.+rise,ambient=50.,meta={
        'operation_complete':True,'budget_exhausted':False,
        'thermal_iterations_completed':1},nets_dropped={},nets_absent={})
    assert overlay._blend_thermal_verdict(result,30.)[0]=='FAIL'
