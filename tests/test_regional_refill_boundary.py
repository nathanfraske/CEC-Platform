"""Unowned global refill cannot erase a source-preserving native construction."""
import time

import pcbnew
import pytest

import cec_rectilinear_copper as owner
import cec_zone_fill as full_fill
from cec_native_fill_geometry import identity
from cec_local_copper_cell import copper_inventory
from test_native_landing_union import keeper_setup
from test_regional_fill import regional_plan, snapshot
from test_zone_fill_stability import fixture


def test_global_refill_refuses_overlapping_owned_native_fill_before_any_mutation(tmp_path):
    b,t,z,_=keeper_setup();source=snapshot(tmp_path,b);p=regional_plan(b,t,z)
    e=owner.materialize(b,p);owner.fill(b,p,e['zone_uuid'],regional_source=source)
    source_before=copper_inventory(source);before=copper_inventory(b)
    filled=identity(z.GetFilledPolysList(pcbnew.F_Cu),time.monotonic()+2)[0]
    with pytest.raises(RuntimeError,match='requires_declared_source_preserving_owner'):
        full_fill.fill_with_report(b)
    assert copper_inventory(b)==before and copper_inventory(source)==source_before
    assert z.IsFilled() and identity(z.GetFilledPolysList(pcbnew.F_Cu),time.monotonic()+2)[0]==filled
    assert owner.receive(b,p,e['zone_uuid'],regional_source=source,timeout_s=10)['ok']


def test_disjoint_native_islands_are_not_an_owned_overlap():
    b,t,z,_=keeper_setup();shape=owner._poly([[30000000,30000000],[31000000,30000000],
        [31000000,31000000],[30000000,31000000]])
    shape.Append(owner._poly([[32000000,30000000],[33000000,30000000],
        [33000000,31000000],[32000000,31000000]]))
    z.SetFilledPolysList(pcbnew.F_Cu,shape);z.SetIsFilled(True)
    before=copper_inventory(b);full_fill._assert_unowned_refill_safe(b)
    assert copper_inventory(b)==before


def test_refill_ownership_deadline_cannot_be_reported_clean():
    b,_,_,_=keeper_setup();before=copper_inventory(b)
    with pytest.raises(owner.Refused):full_fill._assert_unowned_refill_safe(b,timeout_s=0)
    assert copper_inventory(b)==before


def test_selected_native_compile_settles_without_rewriting_other_fills(tmp_path):
    b=fixture(tmp_path/'native.kicad_pcb');full_fill.fill(b)
    zones=list(b.Zones());before=full_fill._fingerprint([zones[1]])
    report=full_fill.compile_selected(b,[zones[0]])
    assert report['stable'] and report['ordered_passes']==2
    assert full_fill._fingerprint([zones[1]])==before
    assert not report['native_copper_received'] and not report['release_authority']


@pytest.mark.parametrize('fault',['duplicate','not_actual','zero_deadline','rule_area'])
def test_selected_native_compile_invalid_scope_fails_before_mutation(tmp_path,fault):
    b=fixture(tmp_path/'native.kicad_pcb');z=list(b.Zones())[0]
    selected=[z];seconds=10
    if fault=='duplicate':selected.append(z)
    elif fault=='not_actual':selected=[pcbnew.ZONE(b)]
    elif fault=='zero_deadline':seconds=0
    else:z.SetIsRuleArea(True)
    before=copper_inventory(b)
    with pytest.raises(RuntimeError):full_fill.compile_selected(b,selected,timeout_s=seconds)
    assert copper_inventory(b)==before
