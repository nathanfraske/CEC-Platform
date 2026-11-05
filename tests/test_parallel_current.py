import copy
import itertools
import math
import pytest
import cec_parallel_current as parallel


def branch(uid, layer='F.Cu', width=3.5, copper=.07, length=50.):
    return dict(id=uid,terminals=['source-contact','sink-contact'],
        series_ohm=[0.,.0005],temperature_c=[20.,70.],segments=[dict(
        layer=layer,length_mm=[length,length],width_mm=[width-.05,width+.05],
        copper_mm=[copper*.9,copper*1.1])])


def screen(rows, **changes):
    args=dict(terminals=['source-contact','sink-contact'],permitted_layers=['F.Cu','B.Cu','In3.Cu'])
    args.update(changes)
    return parallel.screen_bundle(dict(amps=20.,geometry_margin=1.25,margin_included=False),rows,**args)


def test_thick_outer_parallel_paths_are_narrower_without_assumed_equal_sharing():
    result=screen([branch('front'),branch('back','B.Cu')])
    assert result['ipc_width_screen_ok']
    assert all(r['current_interval_a'][1]>10. for r in result['branches'])
    assert sum(r['nominal_current_a'] for r in result['branches'])==pytest.approx(20.)
    assert not result['routing_admitted'] and not result['transitions_current_qualified']
    assert not result['native_common_nodes_verified'] and not result['coupled_thermal_qualified']


def test_thin_inner_layer_does_not_receive_equal_share_or_free_capacity():
    result=screen([branch('outer'),branch('inner','In3.Cu',copper=.0152)])
    front,inner=result['branches']
    assert front['nominal_current_a']>inner['nominal_current_a']*4
    assert not result['ipc_width_screen_ok']
    assert not inner['ipc_width_screen_ok']


def test_short_low_resistance_path_cannot_be_sized_as_half_current():
    result=screen([branch('short',length=10.),branch('long','B.Cu',length=100.)])
    assert result['branches'][0]['current_interval_a'][1]>18.
    assert not result['ipc_width_screen_ok']


def test_series_transition_resistance_changes_sharing_and_is_not_qualified():
    rows=[branch('a'),branch('b','B.Cu')];rows[1]['series_ohm']=[.005,.01]
    result=screen(rows)
    assert result['branches'][0]['nominal_current_a']>14.
    assert not result['ipc_width_screen_ok']
    assert not result['transitions_current_qualified']


def test_interval_current_bounds_enclose_every_resistance_corner():
    result=screen([branch('a'),branch('b','B.Cu',width=4.1),branch('c','In3.Cu',width=1.,copper=.0152)])
    rows=result['branches']
    for corner in itertools.product(*[r['resistance_ohm'] for r in rows]):
        conductance=sum(1/r for r in corner)
        for row,r in zip(rows,corner):
            value=20./r/conductance
            lo,hi=row['current_interval_a']
            assert lo-1e-12 <= value <= hi+1e-12


def test_area_current_correlation_is_retained_and_encloses_intermediate_areas():
    rows=[branch('a'),branch('b','B.Cu')];result=screen(rows)
    segment=result['branches'][0]['segments'][0]
    area_lo=segment['width_mm'][0]*segment['copper_mm'][0]
    area_hi=segment['width_mm'][1]*segment['copper_mm'][1]
    other_max=result['branches'][1]['resistance_ohm'][1]
    import cec_fab_profile as fab
    coefficient=fab.ipc2221_required_width_mm(1.,'F.Cu',copper_mm=1.,rise_c=30.,margin=1.25)
    for n in range(101):
        area=area_lo+(area_hi-area_lo)*n/100
        resistance=parallel.RHO_20_OHM_MM*50./area
        amps=20./(1+resistance/other_max)
        ratio=coefficient*amps**(1/.725)/area
        assert ratio<=segment['ipc_worst_capacity_ratio']+1e-12
    assert result['ipc_width_screen_ok']


def test_interior_area_extremum_is_not_missed_by_checking_endpoints_only():
    rows=[branch('a'),branch('b','B.Cu')]
    rows[0]['segments'][0]['width_mm']=[.01,100.]
    result=screen(rows);segment=result['branches'][0]['segments'][0]
    assert .01*.063 < segment['critical_area_mm2'] < 100*.077


def test_input_order_and_endpoint_direction_do_not_change_result():
    rows=[branch('z'),branch('a','B.Cu')];first=screen(rows)
    rows.reverse();rows[0]['terminals'].reverse();second=screen(rows)
    assert {r['id']:r for r in first['branches']}=={r['id']:r for r in second['branches']}


@pytest.mark.parametrize('field,value',[('id',''),('series_ohm',None),('series_ohm',[-1,1]),
    ('temperature_c',[100,20]),('temperature_c',[20,float('inf')]),
    ('terminals',['source-contact','different-sink'])])
def test_bad_or_missing_branch_authority_fails_closed(field,value):
    rows=[branch('a'),branch('b','B.Cu')];rows[1][field]=value
    with pytest.raises(ValueError):screen(rows)


@pytest.mark.parametrize('field,value',[('length_mm',[0.,1.]),('width_mm',[1.,float('nan')]),
    ('copper_mm',[.07,.01]),('layer','In1.Cu'),('layer','renamed-no-layer')])
def test_invalid_dimensions_or_reference_plane_are_refused(field,value):
    rows=[branch('a'),branch('b','B.Cu')];rows[1]['segments'][0][field]=value
    with pytest.raises(ValueError):screen(rows)


def test_same_uuid_double_counts_no_branch():
    with pytest.raises(ValueError):screen([branch('same'),branch('same','B.Cu')])


def test_no_single_branch_silent_division_and_no_unbounded_topology():
    for count in (1,9):
        with pytest.raises(ValueError):screen([branch(str(n)) for n in range(count)])
    rows=[branch('a'),branch('b')];rows[0]['segments']*=257
    with pytest.raises(ValueError):screen(rows)


def test_no_second_margin_when_current_already_includes_it():
    with pytest.raises(ValueError):parallel.screen_bundle(
        dict(amps=25.,geometry_margin=1.25,margin_included=True),[branch('a'),branch('b')],
        terminals=['source-contact','sink-contact'],permitted_layers=['F.Cu'])


def test_inputs_are_never_mutated():
    rows=[branch('a'),branch('b','B.Cu')];before=copy.deepcopy(rows)
    screen(rows);assert rows==before


def test_barrel_model_requires_actual_plating_and_does_not_credit_pin_fill():
    r=parallel.plated_barrel_resistance_ohm(length_mm=1.6,drill_mm=1.8,plating_mm=.02,temperature_c=20.)
    assert r==pytest.approx(1.72e-5*1.6/(math.pi*1.8*.02))
    with pytest.raises(ValueError):parallel.plated_barrel_resistance_ohm(
        length_mm=1.6,drill_mm=1.8,plating_mm=0,temperature_c=20.)


def test_local_neck_length_matters_but_does_not_qualify_unknown_boundaries():
    args=dict(amps=12.,width_mm=1.3,copper_mm=.063,endpoint_temperature_c=70.,conductivity_w_mk=350.)
    a=parallel.short_neck_temperature_rise_bound_c(length_mm=1.,**args)
    b=parallel.short_neck_temperature_rise_bound_c(length_mm=2.,**args)
    assert b['rise_bound_c']==pytest.approx(4*a['rise_bound_c'])
    assert a['boundary_receiving_required'] and not a['routing_admitted']
    assert not a['current_crowding_qualified'] and not a['release_authority']


def test_neck_model_cannot_exceed_its_resistivity_temperature_bound():
    with pytest.raises(ValueError):parallel.short_neck_temperature_rise_bound_c(
        amps=20.,length_mm=100.,width_mm=.1,copper_mm=.0152,
        endpoint_temperature_c=70.,conductivity_w_mk=350.)
