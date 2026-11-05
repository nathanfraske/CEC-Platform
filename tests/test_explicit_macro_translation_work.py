"""Explicit far construction reach propagates to every native transport.

This is provisional exact Source geometry transport, not routing, current,
clearance, placement or saved-board admission.
"""
import pcbnew
import pytest
import cec_force_current as force
import cec_inpad_ground_barrel_seats as seats
import cec_smd_macro_transport as macro
from test_smd_macro_transport import pair,inventory


@pytest.mark.parametrize('distance',[64.000001,71.,100.,128.])
@pytest.mark.parametrize('back',[False,True])
def test_only_explicit_work_reach_transports_exact_owned_native_barrels(tmp_path,distance,back):
    source,child,owner,via=pair(tmp_path,back=back)
    fp=next(f for f in child.GetFootprints()if force._uid(f)==owner)
    fp.Move(pcbnew.VECTOR2I_MM(distance,0))
    source_before=inventory(source);before=inventory(child)
    with pytest.raises(ValueError,match='bounded_explicit_native_smd_macro_scope'):
        macro.apply(source,child,maximum_shift_mm=distance)
    assert inventory(child)==before
    proof=macro.apply(source,child,maximum_shift_mm=distance,maximum_translation_mm=distance)
    expected=tuple(a+round(b*1e6)for a,b in zip(source_before[via][0],(distance,0)))
    assert inventory(child)[via][0]==expected and inventory(source)==source_before
    assert proof['explicit_maximum_translation_work_mm']==distance
    assert proof['new_barrels_created']==0 and not proof['routing_admitted']
    assert not proof['current_qualified']and not proof['saved_candidate_authorized']


@pytest.mark.parametrize('value',[True,0,-1,128.000001,float('nan'),float('inf'),'128'])
def test_nonfinite_or_unbounded_work_extent_never_writes_conductors(tmp_path,value):
    source,child,_,_=pair(tmp_path);next(iter(child.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    before=inventory(child)
    with pytest.raises(ValueError):macro.apply(source,child,maximum_translation_mm=value)
    assert before==inventory(child)
    with pytest.raises(ValueError):seats.resolve(source,child,[],[],maximum_shift_nm=1000000,maximum_translation_mm=value)
    assert before==inventory(child)


def test_ground_seat_noop_retains_default_bound_but_accepts_only_explicit_far_tier(tmp_path):
    source,child,_,_=pair(tmp_path)
    with pytest.raises(ValueError):seats.resolve(source,child,[],[],maximum_shift_nm=80000000)
    assert seats.resolve(source,child,[],[],maximum_shift_nm=80000000,maximum_translation_mm=80.)==[]
    with pytest.raises(ValueError):
        seats.resolve(source,child,[],[],maximum_shift_nm=80000001,maximum_translation_mm=80.)


def test_legacy_transport_has_no_implicit_work_extent_packet_change(tmp_path):
    source,child,_,_=pair(tmp_path);next(iter(child.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    result=macro.apply(source,child)
    assert 'explicit_maximum_translation_work_mm'not in result


def test_truly_selected_isolated_supply_retains_its_original_64mm_bound(tmp_path):
    from test_isolated_selected_bypass_supply_transport_20261026 import fixture,options
    import cec_source_supply_endpoint_cut as selected
    source,child,_,_,_,_=fixture(tmp_path)
    for fp in child.GetFootprints():fp.Move(pcbnew.VECTOR2I_MM(70,0))
    before=inventory(child)
    with pytest.raises(ValueError,match='bounded_isolated_supply_literal_translation'):
        selected.isolated_components(source,child,**options())
    assert before==inventory(child)
