"""Solver boundaries must preserve current reserve without compounding it."""
import sys
from pathlib import Path
from unittest import mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cec_pour_plan as planner
import cec_slab_pour as compiler


@pytest.mark.parametrize('raw,margin',[(3.,1.25),(12.,1.25),(20.,1.25),(7.,1.4)])
def test_fallback_resolver_applies_declared_margin_once(raw,margin):
    import cec_synth_pipeline as synth
    original=dict(net='/ARBITRARY_RAIL',layers=('F.Cu','B.Cu'))
    ask=planner.fallback_current_ask(original,raw*margin)
    contract=dict(amps=raw,geometry_margin=margin,margin_included=False,source='fixture_basis')
    with mock.patch.object(compiler,'_board_thermal_config',return_value=({},None,{},None)), \
         mock.patch('cec_current_topology.board_current_domains',return_value={}), \
         mock.patch.object(synth,'spec_net_current_contract',return_value=contract):
        _,_,_,rows=compiler.resolve_pour_current_contracts('synthetic.kicad_pcb',[ask])
    assert rows[original['net']]['effective_A']==pytest.approx(raw*margin)
    assert 'design_current_A' not in original
    assert planner.fallback_current_ask(ask,raw*margin)==ask


def test_larger_explicit_contract_is_never_reduced():
    ask=planner.fallback_current_ask(dict(net='/RAIL',design_current_A=40.,geometry_margin=1.5),25.)
    assert ask['design_current_A']==60.
    assert ask['margin_included'] is True and ask['geometry_margin']==1.


@pytest.mark.parametrize('basis,ask',[(-1.,{}),(float('nan'),{}),
    (2.,{'design_current_A':float('inf')}),(2.,{'geometry_margin':.5})])
def test_invalid_contracts_fail_closed(basis,ask):
    with pytest.raises(ValueError,match='basis'):
        planner.fallback_current_ask(ask,basis)
