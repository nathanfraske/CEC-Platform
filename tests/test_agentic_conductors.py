import copy
import math

import pytest

from cec_pipeline import conductors as c


def branch(name, a, b, r=.001, alpha=0, hot='bar'):
    return dict(id=name, a=a, b=b, r_ref_ohm=r, ref_C=25,
                alpha_per_K=alpha, valid_C=[-40, 150], thermal_node=hot, kind='bar')


def model():
    return dict(schema=1, electrical_nodes=['source','return'],
                thermal_nodes=['bar','ambient'], reference='return',
                injections_a={'source':25,'return':-25},
                electrical=[branch('actual-metal','source','return')],
                thermal=[dict(id='explicit-cooling',a='bar',b='ambient',K_per_W=10)],
                bath_C={'ambient':25}, evidence=dict(
                    basis='Analytic synthetic regression, NOT measured board/material data.',
                    limitations='This synthetic heat path cannot qualify a real assembly.'))


def test_single_resistor_energy_and_heat_are_conserved():
    m=model();before=copy.deepcopy(m);r=c.solve(m)
    assert m==before
    assert r['voltage_V']['source']==pytest.approx(.025)
    assert r['total_joule_W']==pytest.approx(.625)
    assert r['temperature_C']['bar']==pytest.approx(31.25,abs=1e-7)
    assert r['supplied_W']==pytest.approx(r['total_joule_W'])
    assert r['rejected_W']==pytest.approx(r['total_joule_W'])
    assert not r['release_authority'] and not r['parameter_qualification']
    assert not r['native_connectivity_inferred'] and not r['assembled_Kelvin_checked']


def test_temperature_feedback_matches_closed_form_not_cold_copper():
    m=model();m['electrical'][0]['alpha_per_K']=.004
    r=c.solve(m);expected=.001/(1-.001*.004*10*25**2)
    assert r['branches'][0]['resistance_ohm']==pytest.approx(expected,rel=1e-8)
    assert r['temperature_C']['bar']==pytest.approx(25+10*25**2*expected,abs=1e-6)


def test_parallel_sharing_is_calculated_not_equal():
    m=model();m['electrical'].append(branch('pcb-path','source','return',.003))
    r=c.solve(m)
    assert [v['current_a'] for v in r['branches']]==pytest.approx([18.75,6.25])
    assert not r['current_sharing_assumed']


def test_two_joints_add_voltage_loss_and_heat():
    m=model();m['electrical_nodes']=['source','left','right','return']
    m['electrical']=[branch('entry','source','left',.0002),
                     branch('metal','left','right',.001),
                     branch('exit','right','return',.0003)]
    m['electrical'][0]['kind']=m['electrical'][2]['kind']='joint'
    r=c.solve(m)
    assert all(row['current_a']==pytest.approx(25) for row in r['branches'])
    assert r['total_joule_W']==pytest.approx(25**2*.0015)


def test_distributed_joint_ladder_does_not_union_boards_and_bar():
    m=model();m['electrical_nodes']=['source','p1','return','b0','b1','b2']
    m['electrical']=[branch('pcb1','source','p1',.003),branch('pcb2','p1','return',.003),
                     branch('bar1','b0','b1',.0001),branch('bar2','b1','b2',.0001),
                     branch('joint0','source','b0',.0002),branch('joint1','p1','b1',.0002),
                     branch('joint2','return','b2',.0002)]
    r=c.solve(m)
    by={v['id']:v for v in r['branches']}
    assert abs(by['joint1']['current_a'])<1e-8
    assert by['bar1']['current_a']==pytest.approx(25*.006/(.006+.0006))
    assert not r['native_copper_changed']


def test_heat_can_flow_to_multiple_distinct_temperature_boundaries():
    m=model();m['thermal_nodes'].append('board')
    m['bath_C']['board']=35
    m['thermal'].append(dict(id='to-pcb',a='bar',b='board',K_per_W=10))
    r=c.solve(m)
    assert r['temperature_C']['bar']==pytest.approx(30+5*.625,abs=1e-7)
    assert r['rejected_W']==pytest.approx(.625)


@pytest.mark.parametrize('fault',[
    'floating_electrical','floating_thermal','unbalanced','zero_resistance',
    'nan','bool','missing_heat','unknown_branch','duplicate','missing_evidence',
    'range','thermal_zero','temperature_unknown','extra'])
def test_incomplete_or_unphysical_network_is_rejected(fault):
    m=model()
    if fault=='floating_electrical':m['electrical_nodes'].append('island')
    elif fault=='floating_thermal':m['thermal_nodes'].append('uncooled')
    elif fault=='unbalanced':m['injections_a']['return']=-24
    elif fault=='zero_resistance':m['electrical'][0]['r_ref_ohm']=0
    elif fault=='nan':m['electrical'][0]['r_ref_ohm']=math.nan
    elif fault=='bool':m['electrical'][0]['r_ref_ohm']=True
    elif fault=='missing_heat':m['electrical'][0]['thermal_node']='unknown'
    elif fault=='unknown_branch':m['electrical'][0]['kind']='imaginary_copper'
    elif fault=='duplicate':m['electrical'].append(copy.deepcopy(m['electrical'][0]))
    elif fault=='missing_evidence':m['evidence']['basis']=''
    elif fault=='range':m['electrical'][0]['valid_C']=[50,10]
    elif fault=='thermal_zero':m['thermal'][0]['K_per_W']=0
    elif fault=='temperature_unknown':m['bath_C']={}
    else:m['qualified']=True
    with pytest.raises(ValueError):c.solve(m)


def test_runaway_or_out_of_characterized_temperature_range_is_not_pass():
    m=model();m['electrical'][0]['alpha_per_K']=.004
    m['thermal'][0]['K_per_W']=1000
    with pytest.raises(ValueError,match='extrapolation|iteration_limit'):c.solve(m)


def test_dimensions_use_minimum_section_and_maximum_length_for_max_R():
    bounds=c.bulk_resistance_bounds(dict(length=[29.7,30.3],width=[2.8,3.2],height=[1.9,2.1]),
                                   [1.7e-8,2e-8])
    assert bounds==pytest.approx([1.7e-8*.0297/(.0032*.0021),2e-8*.0303/(.0028*.0019)])
    # This function returns ohms, never an ampacity or rating.
    assert type(bounds) is list and len(bounds)==2


@pytest.mark.parametrize('bad',[[0,1],[-1,2],[2,1],[1,math.inf],[True,2]])
def test_no_missing_or_reversed_geometric_bound(bad):
    with pytest.raises(ValueError):
        c.bulk_resistance_bounds(dict(length=bad,width=[2,3],height=[1,2]),[1e-8,2e-8])


def test_readonly_repack_capacity_does_not_expand_connected_actuator():
    from cec_pipeline.cells import normalize_poses
    poses=[dict(reference='Q'+str(i),at_nm=[i*1000000,0],rotation_deg=0) for i in range(18)]
    assert len(normalize_poses(poses,limit=32))==18
    with pytest.raises(ValueError):normalize_poses(poses)
    with pytest.raises(ValueError):normalize_poses(poses,limit=33)
