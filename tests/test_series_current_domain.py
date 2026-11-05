"""No board names, current guesses or fuse-rating substitutions in ingress."""
from unittest import mock

import pcbnew
import pytest
import cec_series_current_domain as series
import cec_current_topology as topology
import cec_native_bus_column as column
import cec_force_current as force
import cec_field_coupling as field


def fixture(tmp_path, *, amps=.73, margin=1.25, included=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    b.SetFileName(str(tmp_path/'renamed-native-board.kicad_pcb'))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    raw=pcbnew.NETINFO_ITEM(b,'/arbitrary/EXTERNAL');post=pcbnew.NETINFO_ITEM(b,'/other/PROTECTED')
    b.Add(raw);b.Add(post)
    def fp(ref, lib, item, nets, drilled=False):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetFPID(pcbnew.LIB_ID(lib,item));b.Add(f)
        for i,n in enumerate(nets,1):
            p=pcbnew.PAD(f);p.SetNumber(str(i));p.SetNet(n)
            p.SetPosition(pcbnew.VECTOR2I_MM(i*5,10+len(list(b.GetFootprints()))*4))
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(2,2))
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if drilled else pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.PTHMask() if drilled else pcbnew.PAD.SMDMask())
            if drilled:p.SetDrillSize(pcbnew.VECTOR2I_MM(.7,.7))
            f.Add(p)
        return f
    fuse=fp('PROTECTION_X','Resistor_SMD','R_1206_3216Metric',[raw,post])
    fuse.SetValue('1.1A/16V PTC');fuse.SetField('MPN','FSMD110-16-1206R');fuse.SetField('Manufacturer','FUZETEC')
    connector=fp('EXTERNAL_X','Connector_JST','JST_PH_1x02',[raw],True)
    load=fp('LOAD_X','Package_SO','SOIC-8',[post])
    domain={post.GetNetname():dict(net=post.GetNetname(),configured_net=post.GetNetname(),
        amps=amps,complete=True,source_refs=('PROTECTION_X',),sink_refs=('LOAD_X',),
        authority_refs=('PROTECTION_X','LOAD_X'),source='thermal_source_sink_override')}
    authority=dict(amps=amps,geometry_margin=margin,margin_included=included,source='current_domain_authority')
    return b,raw,post,fuse,connector,load,domain,authority


@pytest.mark.parametrize('amps,margin,included',[(.73,1.25,False),(2.4,1.,True)])
def test_exact_whole_contract_not_selected_ptc_current(tmp_path,amps,margin,included):
    b,raw,post,fuse,conn,load,domains,authority=fixture(tmp_path,amps=amps,margin=margin,included=included)
    before=field._field_snapshot_inventory(b)
    result=series.derive(b,domains,lambda net: authority)
    row=result[raw.GetNetname()]
    assert row['current_contract']['amps']==amps and row['amps']==amps
    assert row['current_contract']['geometry_margin']==margin
    assert row['current_contract']['margin_included']==included
    witness=row['series_transfer']
    assert witness['whole_current_carried'] and not witness['inferred_load_or_fault_limit']
    assert not witness['selected_part']['fuse_hold_or_trip_rating_used_as_current_limit']
    assert set(row['authority_refs'])=={'EXTERNAL_X','PROTECTION_X'}
    assert before==field._field_snapshot_inventory(b)
    assert topology.current_contract_for_net(raw.GetNetname(),'arbitrary',result)==row['current_contract']


@pytest.mark.parametrize('fault',['unknown_mpn','wrong_manufacturer','wrong_package','dnp','missing_pin',
    'same_net','source_incomplete','source_not_series','bidirectional_domain','unknown_connector',
    'unplated_connector','branch','duplicate_ref','no_authority','zero_current','double_margin'])
def test_unsealed_or_untyped_network_cannot_inherit(tmp_path,fault):
    b,raw,post,fuse,conn,load,domains,authority=fixture(tmp_path)
    if fault=='unknown_mpn':fuse.SetField('MPN','UNSPECIFIED')
    if fault=='wrong_manufacturer':fuse.SetField('Manufacturer','UNSPECIFIED')
    if fault=='wrong_package':fuse.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0402_1005Metric'))
    if fault=='dnp':fuse.SetDNP(True)
    if fault=='missing_pin':fuse.FindPadByNumber('2').SetNumber('3')
    if fault=='same_net':fuse.FindPadByNumber('2').SetNet(raw)
    if fault=='source_incomplete':domains[post.GetNetname()]['complete']=False
    if fault=='source_not_series':domains[post.GetNetname()]['authority_refs']=('LOAD_X',)
    if fault=='bidirectional_domain':domains[post.GetNetname()]['sink_refs']=('PROTECTION_X',)
    if fault=='unknown_connector':conn.SetFPID(pcbnew.LIB_ID('Unknown','Unqualified'))
    if fault=='unplated_connector':conn.FindPadByNumber('1').SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    if fault=='branch':load.FindPadByNumber('1').SetNet(raw)
    if fault=='duplicate_ref':load.SetReference(conn.GetReference())
    if fault=='no_authority':authority=None
    if fault=='zero_current':authority['amps']=0
    if fault=='double_margin':authority['margin_included']=True
    before=field._field_snapshot_inventory(b)
    assert not series.derive(b,domains,lambda net: authority)
    assert before==field._field_snapshot_inventory(b)


def test_real_topology_rederives_whole_transfer_and_widths(tmp_path):
    b,raw,post,fuse,conn,load,domains,authority=fixture(tmp_path)
    config=({post.GetNetname():authority['amps']},None,
        {post.GetNetname():{'refs_src':['PROTECTION_X'],'refs_sink':['LOAD_X']}},None)
    with force._thermal_hint('synthetic-input'), \
            mock.patch('cec_thermal_overlay.board_thermal_config',return_value=config), \
            mock.patch('cec_synth_pipeline.spec_net_current_contract',return_value=None):
        actual=topology.board_current_domains(b,'synthetic-input')
        inherited=topology.current_contract_for_net(raw.GetNetname(),'synthetic-input',actual)
        assert series.validate_existing_domain_authority(b,raw.GetNetname(),inherited)
        widths=topology.route_width_contracts(b,'synthetic-input')
        assert widths[raw.GetNetname()]['required_by_layer_mm']==widths[post.GetNetname()]['required_by_layer_mm']
        assert column._authority(b,raw.GetNetname())['current_authority']==inherited
        fake=dict(inherited,amps=inherited['amps']/2)
        assert not series.validate_existing_domain_authority(b,raw.GetNetname(),fake)


def test_preexisting_domain_is_never_replaced_or_reduced(tmp_path):
    b,raw,post,fuse,conn,load,domains,authority=fixture(tmp_path)
    domains[raw.GetNetname()]=dict(domains[post.GetNetname()],amps=8.)
    assert not series.derive(b,domains,lambda net: authority)
    assert domains[raw.GetNetname()]['amps']==8.


def test_canonical_vendored_library_alias_preserves_electrical_identity(tmp_path):
    b,raw,post,fuse,conn,load,domains,authority=fixture(tmp_path)
    fuse.SetFPID(pcbnew.LIB_ID('cec-Resistor_SMD','R_1206_3216Metric'))
    conn.SetFPID(pcbnew.LIB_ID('cec-Connector_JST','JST_PH_1x02'))
    assert raw.GetNetname() in series.derive(b,domains,lambda net: authority)
