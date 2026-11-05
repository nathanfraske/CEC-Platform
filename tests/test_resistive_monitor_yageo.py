"""Exact selected Yageo resistance bounds, never a new rail/load budget."""
import json
import math

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_resistive_monitor_branch as branch
from test_resistive_monitor_branch import fixture


def resistor(*,mpn='RT0402BRD0747KL',value='47kΩ',manufacturer='Yageo'):
    board=pcbnew.BOARD()
    fp=pcbnew.FOOTPRINT(board);board.Add(fp)
    fp.SetReference('ARBITRARY_709');fp.SetValue(value)
    fp.SetFPID(pcbnew.LIB_ID('arbitrary_library','R_0402_1005Metric'))
    fp.SetField('MPN',mpn);fp.SetField('Manufacturer',manufacturer)
    fp.SetField('Tolerance','0.1%')
    for number,x in [('1',10.),('2',11.)]:
        pad=pcbnew.PAD(fp);pad.SetNumber(number)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,12.));fp.Add(pad)
    return board,fp


@pytest.mark.parametrize('code,value,ohms',[
    ('47K','47kΩ',47000.),('10K','10kΩ',10000.),
    ('4R7','4.7Ω',4.7),('9R76','9.76',9.76),('100R','100 ohms',100.),
    ('4K7','4.7k',4700.),('47K5','47.5K',47500.),('240K','240kΩ',240000.)])
def test_exact_decimal_code_and_manufacturer_bounds(code,value,ohms):
    board,fp=resistor(mpn='RT0402BRD07'+code+'L',value=value)
    result=branch.resistor_contract(fp)
    assert result is not None
    assert result['nominal_ohms']==ohms
    assert result['tolerance_fraction']==.001
    assert result['tcr_bound_ppm_per_c']==25.
    assert result['temperature_bounds_c']==[-55.,155.]
    assert result['reference_temperature_c']==25.
    assert result['minimum_ohms']==ohms*.999*(1-25.*130.*1e-6)
    assert result['source']==branch.YAGEO_RT_SOURCE
    assert result['manufacturer_revision']=='17'
    assert result['manufacturer_pdf_sha256']=='00a9148c2958122200e8a93292e389392a795adcfe40562d6ca4f690d1e5d7d1'
    assert not any(result[k] for k in ('aging_and_fault_conditions_qualified',
        'resistance_or_power_qualification','power_qualified','voltage_qualified',
        'thermal_qualified','release_authority'))


@pytest.mark.parametrize('code,value',[
    ('4R64','4.64'),('243K','243k'),('1M','1M'),('0R','0'),
    ('047K','47k'),('47K00','47k'),('4702','47k'),('47K1K','47.1k'),
    ('R47','0.47'),('4.7K','4.7k'),('47','47'),('','47k')])
def test_unavailable_range_or_malformed_encoding_refuses(code,value):
    board,fp=resistor(mpn='RT0402BRD07'+code+'L',value=value)
    assert branch.resistor_contract(fp) is None


@pytest.mark.parametrize('fault',[
    'value','nonfinite_value','missing_mpn','family','package_mpn','tolerance_mpn',
    'tcr_mpn','packing_mpn','reel_mpn','suffix_mpn','manufacturer','missing_manufacturer',
    'footprint','dnp','through_hole','npth','drill','duplicate_pad','extra_pad','tolerance_field'])
def test_contradictory_or_unselected_device_refuses(fault):
    board,fp=resistor();pad=fp.FindPadByNumber('1')
    if fault=='value':fp.SetValue('10kΩ')
    elif fault=='nonfinite_value':fp.SetValue('NaN')
    elif fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='family':fp.SetField('MPN','RC0402BRD0747KL')
    elif fault=='package_mpn':fp.SetField('MPN','RT0603BRD0747KL')
    elif fault=='tolerance_mpn':fp.SetField('MPN','RT0402FRD0747KL')
    elif fault=='tcr_mpn':fp.SetField('MPN','RT0402BRE0747KL')
    elif fault=='packing_mpn':fp.SetField('MPN','RT0402BKD0747KL')
    elif fault=='reel_mpn':fp.SetField('MPN','RT0402BRD1047KL')
    elif fault=='suffix_mpn':fp.SetField('MPN','RT0402BRD0747K')
    elif fault=='manufacturer':fp.SetField('Manufacturer','UNI-ROYAL')
    elif fault=='missing_manufacturer':fp.SetField('Manufacturer','')
    elif fault=='footprint':fp.SetFPID(pcbnew.LIB_ID('arbitrary_library','R_0603_1608Metric'))
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='through_hole':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='npth':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='drill':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='duplicate_pad':fp.FindPadByNumber('2').SetNumber('1')
    elif fault=='extra_pad':
        extra=pcbnew.PAD(fp);extra.SetNumber('3');fp.Add(extra)
    elif fault=='tolerance_field':fp.SetField('Tolerance','1%')
    assert branch.resistor_contract(fp) is None


@pytest.mark.parametrize('angle,flip',[(0,False),(90,False),(180,True),(270,True)])
def test_ref_placement_orientation_and_copper_face_are_not_current_authority(angle,flip):
    board,fp=resistor();expected=branch.resistor_contract(fp)
    fp.SetReference('UNRELATED_NAME');fp.SetPosition(pcbnew.VECTOR2I_MM(37.,29.))
    fp.Rotate(pcbnew.VECTOR2I_MM(37.,29.),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if flip:fp.Flip(pcbnew.VECTOR2I_MM(37.,29.),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    assert branch.resistor_contract(fp)==expected


@pytest.mark.parametrize('value,code',[(10.,'10R'),(10000.,'10K'),(47000.,'47K')])
def test_power_and_continuous_voltage_are_conditional_and_not_fifty_volts_for_every_value(value,code):
    board,fp=resistor(mpn='RT0402BRD07'+code+'L',value=str(value))
    result=branch.resistor_contract(fp)
    assert result['rated_power_w']==1/16
    assert result['power_rating_ambient_c']==70.
    assert result['power_derating']==dict(full_power_through_c=70.,zero_power_at_c=155.,
        interpolation='linear_above_70c',operating_temperature_bounds_c=[-55.,155.])
    assert result['maximum_working_voltage_v']==50.
    expected=min(50.,math.sqrt(result['minimum_ohms']/16))
    assert result['continuous_voltage_ceiling_at_70c_using_minimum_r_v']==expected
    assert result['continuous_voltage_ceiling_at_155c_v']==0.
    if value<40000.:assert expected<50.
    assert not result['power_qualified'] and not result['voltage_qualified']


@pytest.mark.parametrize('code,value,ohms',[
    ('0010','1',1),('0100','10',10),('4702','47k',47000),('1003','100k',100000)])
def test_uni_royal_result_remains_byte_semantically_exact(code,value,ohms):
    board,fp=resistor(mpn='0402WGF'+code+'TCE',value=value,manufacturer='')
    # The original model did not consume Manufacturer or Tolerance fields.
    fp.SetField('Tolerance','unconsumed legacy field')
    tcr=200. if ohms<=10 else 100.
    expected=dict(mpn='0402WGF'+code+'TCE',nominal_ohms=ohms,tolerance_fraction=.01,
        tcr_bound_ppm_per_c=tcr,temperature_bounds_c=[-55.,155.],reference_temperature_c=25.,
        minimum_ohms=ohms*.99*(1-tcr*130.*1e-6),source=branch.RESISTOR_SOURCE,
        aging_and_fault_conditions_qualified=False,resistance_or_power_qualification=False)
    assert json.dumps(branch.resistor_contract(fp),sort_keys=True)==json.dumps(expected,sort_keys=True)


@pytest.mark.parametrize('angle,flip',[(0,False),(90,True)])
def test_yageo_divider_uses_existing_source_and_exclusive_native_plan(tmp_path,angle,flip):
    source,board,top,bottom,_,domains,owned,trunk,_=fixture(tmp_path)
    for fp,code,value in [(top,'47K','47kΩ'),(bottom,'10K','10kΩ')]:
        fp.SetField('MPN','RT0402BRD07'+code+'L');fp.SetField('Manufacturer','Yageo')
        fp.SetField('Tolerance','0.1%');fp.SetValue(value)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if flip:item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(board,source);original=source.read_bytes()
    root=force._uid(top.FindPadByNumber('1'))
    contract=branch.source_contract(board,root)
    assert contract['current_upper_bound_a']==pytest.approx(24.3/(47000*.999*(1-.00325)))
    plan=branch.plan(board,root)
    assert set(plan['track_uuids'])==set(owned)
    assert trunk not in plan['native_removed_material_uuids']
    result=branch.inventory(board,source,domains)
    assert result['complete'] and set(result['uuids'])==set(owned),result
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert not result['current_path_qualified'] and not result['release_authority']
    assert source.read_bytes()==original
