"""Explicit terminal data must bind real selected parts without inventing amps."""
from copy import deepcopy
import json
import pcbnew
import pytest

import cec_declared_current_endpoints as endpoints
import cec_current_topology as topology


def fixture(*, variant=0, source_pins=('A', 'B')):
    board=pcbnew.BOARD(); board.SetCopperLayerCount(6)
    net='/partition'+str(variant)+'/POWER'; ground='GND'
    nets={}
    for name in (net,ground):
        item=pcbnew.NETINFO_ITEM(board,name);board.Add(item);nets[name]=item
    refs=('EXT_'+str(variant+71),'DEVICE_'+str(variant+92))
    items={}
    for ref,pins,mpn,fpid in ((refs[0],source_pins,'INPUT-SELECTED','Synthetic:source'),
                               (refs[1],('7',),'LOAD-SELECTED','Synthetic:load')):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue('display is not authority')
        fp.SetFPID(pcbnew.LIB_ID(*fpid.split(':',1)));fp.SetField('MPN',mpn)
        for index,pin in enumerate(pins):
            pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetNet(nets[net])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers);pad.SetPosition(pcbnew.VECTOR2I_MM(10+variant*2,index+10))
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));fp.Add(pad)
        board.Add(fp);items[ref]=fp
    declaration=dict(net='/POWER',sources=[dict(ref=refs[0],pins=list(source_pins),
        mpn='INPUT-SELECTED',footprint='Synthetic:source')],
        sinks=[dict(ref=refs[1],pins=['7'],mpn='LOAD-SELECTED',footprint='Synthetic:load')],
        basis='Explicit native/netlist terminal map; only the existing conductor contract is bound.')
    current=dict(amps=.75,geometry_margin=1.25,margin_included=False,source='board_design_basis')
    return board,net,refs,items,declaration,current


@pytest.mark.parametrize('variant',range(4))
@pytest.mark.parametrize('side',('F','B','PTH'))
def test_smd_through_and_renamed_maps_bind_the_same_existing_authority(tmp_path,variant,side):
    b,net,refs,items,d,current=fixture(variant=variant)
    for fp in items.values():
        if side=='B':fp.Flip(pcbnew.VECTOR2I_MM(0,0),False)
        elif side=='PTH':
            for pad in fp.Pads():
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
                layers=pcbnew.LSET.AllCuMask();pad.SetLayerSet(layers)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),b);saved=path.read_bytes()
    b=pcbnew.LoadBoard(str(path));old_d=deepcopy(d);old_current=deepcopy(current)
    domain=endpoints.bind(b,[d],lambda _net:current)[net]
    assert domain['complete'] and domain['source_refs']==(refs[0],) and domain['sink_refs']==(refs[1],)
    assert domain['amps']==.75 and domain['current_contract']==old_current
    witness=domain['declared_endpoint_witness']
    assert len(witness['native_endpoints']['sources'][0]['pad_uuids'])==2
    assert not witness['new_budget_or_pin_sharing_inferred']
    assert d==old_d and current==old_current and path.read_bytes()==saved
    assert not any(key in d for key in ('amps','capacity','geometry_margin'))


@pytest.mark.parametrize('fault',('no_current','zero','negative','bool','nan','inf','no_margin',
    'zero_margin','small_margin','included_twice','missing_included','missing_source'))
def test_endpoint_map_cannot_create_or_relax_the_current_or_margin(fault):
    b,net,refs,items,d,current=fixture()
    if fault=='no_current':current=None
    elif fault in ('zero','negative','bool','nan','inf'):
        current['amps']={'zero':0.,'negative':-1.,'bool':True,'nan':float('nan'),'inf':float('inf')}[fault]
    elif fault=='no_margin':current.pop('geometry_margin')
    elif fault=='zero_margin':current['geometry_margin']=0.
    elif fault=='small_margin':current['geometry_margin']=.99
    elif fault=='included_twice':current['margin_included']=True
    elif fault=='missing_included':current.pop('margin_included')
    else:current.pop('source')
    with pytest.raises(ValueError,match='existing_positive_current'):
        endpoints.bind(b,[d],lambda _net:current)


@pytest.mark.parametrize('fault',('source_missing','sink_missing','duplicate_ref','wrong_mpn',
    'missing_mpn','wrong_footprint','dnp','off_net','omitted_pin','extra_pin','split_pin',
    'noncopper','mechanical_pad','duplicate_uuid'))
def test_native_terminal_mismatch_never_falls_back_to_a_partial_or_guessed_map(fault):
    b,net,refs,items,d,current=fixture();fp=items[refs[0]];pad=list(fp.Pads())[0]
    if fault=='source_missing':d['sources'][0]['ref']='absent'
    elif fault=='sink_missing':d['sinks'][0]['ref']='absent'
    elif fault=='duplicate_ref':
        copy=pcbnew.FOOTPRINT(b);copy.SetReference(refs[0]);b.Add(copy)
    elif fault=='wrong_mpn':fp.SetField('MPN','OTHER')
    elif fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='wrong_footprint':fp.SetFPID(pcbnew.LIB_ID('Other','source'))
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='off_net':pad.SetNet(b.FindNet('GND'))
    elif fault=='omitted_pin':d['sources'][0]['pins'].pop()
    elif fault=='extra_pin':d['sources'][0]['pins'].append('absent')
    elif fault=='split_pin':
        copy=pad.Duplicate();copy.SetNet(b.FindNet('GND'));fp.Add(copy)
    elif fault=='noncopper':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_SilkS);pad.SetLayerSet(layers)
    elif fault=='mechanical_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    else:list(fp.Pads())[1].m_Uuid.Clone(pad.m_Uuid)
    with pytest.raises(ValueError):endpoints.bind(b,[d],lambda _net:current)


@pytest.mark.parametrize('fault',('budget','empty_sources','empty_sinks','unknown_field','bad_pins',
    'duplicate_pin','duplicate_endpoint','source_equals_sink','duplicate_net','ambiguous_net',
    'missing_net','bad_row','bad_list','too_many'))
def test_declaration_schema_resolution_and_bounds_refuse(fault):
    b,net,refs,items,d,current=fixture();rows=[d]
    if fault=='budget':d['amps']=.001
    elif fault=='empty_sources':d['sources']=[]
    elif fault=='empty_sinks':d['sinks']=[]
    elif fault=='unknown_field':d['sources'][0]['capacity']=99.
    elif fault=='bad_pins':d['sources'][0]['pins']='A'
    elif fault=='duplicate_pin':d['sources'][0]['pins'].append('A')
    elif fault=='duplicate_endpoint':d['sources'].append(deepcopy(d['sources'][0]))
    elif fault=='source_equals_sink':d['sinks']=[deepcopy(d['sources'][0])]
    elif fault=='duplicate_net':rows.append(deepcopy(d))
    elif fault=='ambiguous_net':b.Add(pcbnew.NETINFO_ITEM(b,'/another/POWER'))
    elif fault=='missing_net':d['net']='/absent'
    elif fault=='bad_row':rows=[None]
    elif fault=='bad_list':rows={}
    else:rows=[d]*65
    with pytest.raises(ValueError):endpoints.bind(b,rows,lambda _net:current)


def test_empty_declarations_leave_legacy_without_board_or_authority_access():
    assert endpoints.bind(None,[],lambda _net:pytest.fail('authority accessed'))=={}


def test_existing_identical_domain_is_preserved_not_replaced():
    b,net,refs,items,d,current=fixture()
    old=dict(net=net,amps=.75,complete=True,missing_refs=(),source_refs=(refs[0],),
             sink_refs=(refs[1],),authority_refs=refs,source='legacy_authority')
    before=deepcopy(old);bound=endpoints.bind(b,[d],lambda _net:current,existing={net:old})[net]
    assert old==before and all(bound[key]==value for key,value in old.items())
    bound['declared_endpoint_witness']['existing_current_contract']['amps']=999
    assert current['amps']==.75


@pytest.mark.parametrize('fault',('incomplete','missing_ref','different_amps','different_source','different_sink'))
def test_conflicting_existing_authority_cannot_be_silently_overridden(fault):
    b,net,refs,items,d,current=fixture()
    old=dict(amps=.75,complete=True,missing_refs=(),source_refs=(refs[0],),sink_refs=(refs[1],))
    if fault=='incomplete':old['complete']=False
    elif fault=='missing_ref':old['missing_refs']=('absent',)
    elif fault=='different_amps':old['amps']=3.
    elif fault=='different_source':old['source_refs']=('another',)
    else:old['sink_refs']=('another',)
    before=deepcopy(old)
    with pytest.raises(ValueError,match='conflict_with_existing_authority'):
        endpoints.bind(b,[d],lambda _net:current,existing={net:old})
    assert old==before


def test_shared_topology_path_consumes_declarations_without_inferring_from_holes(monkeypatch):
    b,net,refs,items,d,current=fixture()
    import cec_board_policy as policy
    import cec_synth_pipeline as synth
    import cec_thermal_overlay as overlay
    monkeypatch.setattr(policy,'params',lambda *a,**k:dict(current_endpoint_contracts=[d]))
    monkeypatch.setattr(overlay,'board_thermal_config',lambda *a,**k:({},None,{},None))
    monkeypatch.setattr(synth,'spec_net_current_contract',lambda hint,n:deepcopy(current) if n==net else None)
    domain=topology.board_current_domains(b,board_hint='arbitrary-synthetic')[net]
    assert domain['complete'] and domain['source']=='board_policy_existing_current_endpoints'
    assert domain['source_refs']==(refs[0],) and domain['sink_refs']==(refs[1],)
    assert all(not pad.HasHole() for fp in b.GetFootprints() for pad in fp.Pads())


def test_record_serializes_without_native_proxies_or_mutating_declaration():
    b,net,refs,items,d,current=fixture();before=deepcopy(d)
    proof=endpoints.bind(b,[d],lambda _net:current)
    assert json.loads(json.dumps(proof))[net]['declared_endpoint_witness']['declaration']==before
