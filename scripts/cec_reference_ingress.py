"""Positively type a closed scalar external-reference ingress, not a supply.

One connector land, one selected bidirectional ESD clamp and one selected
series resistor must feed a bounded divider/filter/manufacturer input node.
This only corrects lexical rail/sense guesses. Pair/Kelvin/current, exact
foreign-copper, field, factory and native receiving remain independent gates.
No nominal voltage, current budget, high-Z GPIO mode or ESD rating is inferred.
"""
import math
import re
import time

import pcbnew
import cec_device_power_roles as roles
import cec_resistive_monitor_branch as monitor
import cec_series_current_domain as series
from cec_footprint_fields import footprint_properties


ESD_SOURCE='https://datasheet.lcsc.com/datasheet/pdf/93f78f16c9b422f661a175328267027f.pdf'


def esd_return(member):
    fp=member.GetParentFootprint();props=footprint_properties(fp);pads=list(fp.Pads())
    if (fp.IsDNP() or props.get('MPN')!='PESD5V0S1BA'
            or props.get('Manufacturer','').upper()!='HXY MOSFET'
            or str(fp.GetValue()).strip().upper()!='PESD5V0S1BA'
            or not re.fullmatch(r'(?:cec-)?Diode_SMD:D_SOD-323',fp.GetFPIDAsString())
            or len(pads)!=2 or {p.GetNumber() for p in pads}!={'1','2'}
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)):
        return None
    other=next(p for p in pads if p.m_Uuid!=member.m_Uuid)
    if str(other.GetNetname())!='GND':return None
    return dict(mpn=props['MPN'],source=ESD_SOURCE,role='selected_bidirectional_shunt_ESD',
        ground_pad_uuid=other.m_Uuid.AsString(),operating_or_transient_qualification=False)


def source_contract(board,net,*,timeout_s=2.):
    if (type(net) is not str or not net or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10):
        raise ValueError('bounded_native_reference_ingress_required')
    deadline=time.monotonic()+timeout_s
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode()>0]
    if len(pads)>16384:raise ValueError('reference_ingress_inventory_bound')
    terminals=[p for p in pads if str(p.GetNetname())==net]
    if len(terminals)!=3 or net=='GND':return None
    resistor=[];connector=[];clamp=[]
    for p in terminals:
        if time.monotonic()>=deadline:raise ValueError('reference_ingress_deadline')
        if p.GetParentFootprint().IsDNP():return None
        selected=monitor.resistor_contract(p.GetParentFootprint())
        if selected:resistor.append((p,selected));continue
        if series.connector_land(p):connector.append(p);continue
        esd=esd_return(p)
        if esd:clamp.append((p,esd));continue
        return None
    if len(resistor)!=1 or len(connector)!=1 or len(clamp)!=1:return None
    source,resistance=resistor[0]
    other=next(p for p in source.GetParentFootprint().Pads() if p.m_Uuid!=source.m_Uuid)
    if other.GetNetCode()<=0 or other.GetNetname() in (net,'GND'):return None
    node=[p for p in pads if p.GetNetCode()==other.GetNetCode()]
    if not 3<=len(node)<=6:return None
    inputs=[];bottom=[];filters=[]
    for p in node:
        if time.monotonic()>=deadline:raise ValueError('reference_ingress_deadline')
        if p.m_Uuid==other.m_Uuid:continue
        fp=p.GetParentFootprint()
        if fp.IsDNP():return None
        endpoint=roles.resistive_sensing_endpoint_contract(fp,p.GetNumber())
        if endpoint and endpoint.get('endpoint_role') in (
                'analog_comparator_input','adc_capable_gpio_voltage_envelope_not_application_mode'):
            inputs.append(dict(pad_uuid=p.m_Uuid.AsString(),contract=endpoint));continue
        selected=monitor.resistor_contract(fp)
        peers=[q for q in fp.Pads() if q.m_Uuid!=p.m_Uuid]
        if selected and len(peers)==1 and peers[0].GetNetname()=='GND':
            bottom.append(dict(pad_uuid=p.m_Uuid.AsString(),resistor=selected));continue
        selected=monitor._shunt_filter_contract(fp,p)
        if selected:filters.append(dict(pad_uuid=p.m_Uuid.AsString(),contract=selected));continue
        return None
    if not 1<=len(inputs)<=2 or len(bottom)!=1 or len(filters)>2:return None
    return dict(schema=1,net=net,role='native_closed_scalar_reference_ingress',
        connector_pad_uuid=connector[0].m_Uuid.AsString(),
        series_pad_uuid=source.m_Uuid.AsString(),series_resistor=resistance,
        clamp_pad_uuid=clamp[0][0].m_Uuid.AsString(),clamp=clamp[0][1],
        downstream_net=str(other.GetNetname()),manufacturer_inputs=inputs,
        ground_resistors=bottom,shunt_filters=filters,
        whole_current_or_precision_net_ownership_overridden=False,
        numeric_load_or_rail_budget_modified=False,gpio_high_impedance_assumed=False,
        ESD_or_fault_or_operating_qualification=False,release_authority=False)
