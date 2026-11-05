import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import cec_sense_topology as topology


def network():
    pads={'SHUNT':{'a':'FORCE_A','b':'FORCE_B'},
          'SERIES_A':{'left':'FORCE_A','right':'INPUT_A'},
          'SERIES_B':{'left':'FORCE_B','right':'INPUT_B'},
          'DIFF_CAP':{'1':'INPUT_A','2':'INPUT_B'},
          'MONITOR':{'8':'INPUT_A','1':'INPUT_B','6':'POWER'}}
    inputs=[dict(ref='MONITOR',device='INA240',pins=['8','1'],p='INPUT_A',n='INPUT_B')]
    return pads,inputs


def trace(pads,inputs,**kwargs):
    return topology.trace_inputs(pads,inputs,resistor_refs=kwargs.pop('resistor_refs',{'SERIES_A','SERIES_B'}),
        anchors=kwargs.pop('anchors',{'SHUNT':pads['SHUNT']}),**kwargs)


def test_filtered_chain_preserves_actual_pad_order_not_distance_or_spelling():
    pads,inputs=network()
    before=copy.deepcopy((pads,inputs))
    result=trace(pads,inputs)
    assert result['ok'] and result['resolved']==1
    cell=result['details'][0]['selected']
    assert cell['anchor_ref']=='SHUNT' and cell['kind']=='filtered'
    assert cell['p']['series']==[dict(ref='SERIES_A',input_pad='right',anchor_pad='left',
                                     input_net='INPUT_A',anchor_net='FORCE_A')]
    assert cell['n']['anchor_pad']=='b'
    assert (pads,inputs)==before
    assert 'DIFF_CAP' not in json.dumps(cell)


def test_direct_input_has_no_invented_filter():
    pads,inputs=network()
    pads['MONITOR'].update({'8':'FORCE_A','1':'FORCE_B'})
    inputs[0].update(p='FORCE_A',n='FORCE_B')
    cell=trace(pads,inputs)['details'][0]['selected']
    assert cell['kind']=='direct' and not cell['p']['series'] and not cell['n']['series']


@pytest.mark.parametrize('fault',['missing_edge','unknown_type','wrong_input','same_input','no_anchor'])
def test_unknown_or_incomplete_network_is_not_a_nearest_anchor_pass(fault):
    pads,inputs=network();kwargs={}
    if fault=='missing_edge':del pads['SERIES_A']
    if fault=='unknown_type':kwargs['resistor_refs']={'SERIES_B'}
    if fault=='wrong_input':inputs[0]['p']='UNRELATED'
    if fault=='same_input':inputs[0]['n']='INPUT_A'
    if fault=='no_anchor':kwargs['anchors']={}
    result=trace(pads,inputs,**kwargs)
    assert not result['ok'] and 'selected' not in result['details'][0]


def test_two_real_anchors_are_ambiguous_even_if_one_is_geometrically_nearer():
    pads,inputs=network();pads['OTHER']=dict(pads['SHUNT'])
    result=trace(pads,inputs,anchors={r:pads[r] for r in ('SHUNT','OTHER')})
    assert result['details'][0]['reason']=='ambiguous'
    assert len(result['details'][0]['candidates'])==2


def test_parallel_filter_paths_are_ambiguous():
    pads,inputs=network();pads['OTHER']=dict(pads['SERIES_A'])
    result=trace(pads,inputs,resistor_refs={'SERIES_A','SERIES_B','OTHER'})
    assert result['details'][0]['reason']=='ambiguous'


def test_multiple_series_sections_remain_ordered():
    pads,inputs=network();pads['SERIES_A']['right']='MIDDLE'
    pads['EXTRA']={'x':'INPUT_A','y':'MIDDLE'}
    result=trace(pads,inputs,resistor_refs={'SERIES_A','SERIES_B','EXTRA'})
    assert result['ok']
    assert [s['ref'] for s in result['details'][0]['selected']['p']['series']]==['EXTRA','SERIES_A']


@pytest.mark.parametrize('kwargs',[{'max_hops':0},{'max_expansions':1}])
def test_exhaustion_never_becomes_no_path_proof(kwargs):
    pads,inputs=network();result=trace(pads,inputs,**kwargs)
    assert not result['ok']
    assert result['details'][0]['reason']=='search_budget_exhausted'
    assert result['details'][0]['exhaustion_is_no_path_proof'] is False


def test_shared_path_cannot_be_two_independent_input_legs():
    pads,inputs=network();pads['SERIES_B']['left']='FORCE_A'
    assert not trace(pads,inputs)['ok']


def test_declared_anchor_must_match_live_graph():
    pads,inputs=network()
    with pytest.raises(ValueError,match='live pad nets'):
        trace(pads,inputs,anchors={'SHUNT':{'a':'WRONG','b':'FORCE_B'}})


@pytest.mark.parametrize('kwargs',[{'max_hops':True},{'max_hops':9},{'max_expansions':0}])
def test_invalid_work_policy_refused(kwargs):
    pads,inputs=network()
    with pytest.raises(ValueError):trace(pads,inputs,**kwargs)


def native_network():
    import pcbnew
    import cec_fr  # pins native lifetime through the project's guard
    pads,_=network();board=pcbnew.CreateEmptyBoard();nets={}
    for name in {n for pinmap in pads.values() for n in pinmap.values()}:
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    for ref,pinmap in pads.items():
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref)
        fp.SetValue('INA240A3DR' if ref=='MONITOR' else '470nF' if ref=='DIFF_CAP' else '10')
        fid='Resistor_SMD:R_0603' if ref not in ('MONITOR','DIFF_CAP') else 'Capacitor_SMD:C_0603'
        if ref == 'MONITOR':fid='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
        fp.SetFPID(pcbnew.LIB_ID(*fid.split(':')))
        board.Add(fp)
        for pin,net in pinmap.items():
            pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetNet(nets[net])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));fp.Add(pad)
    return board


def test_loaded_native_adapter_uses_declared_pair_not_refdes_and_excludes_capacitor(tmp_path):
    import pcbnew
    board=native_network();path=str(tmp_path/'input.kicad_pcb')
    pcbnew.SaveBoard(path,board,True);before=Path(path).read_bytes()
    loaded=pcbnew.LoadBoard(path)
    result=topology.board_evidence(loaded,anchor_pairs=[('FORCE_A','FORCE_B')])
    assert result['ok'] and result['anchor_refs']==['SHUNT']
    assert 'DIFF_CAP' not in result['typed_resistor_refs']
    assert not result['copper_connectivity_proved']
    assert Path(path).read_bytes()==before


def test_known_native_input_with_wrong_pin_cannot_disappear():
    board=native_network()
    board.FindFootprintByReference('MONITOR').FindPadByNumber('8').SetNumber('OTHER')
    result=topology.board_evidence(board,anchor_pairs=[('FORCE_A','FORCE_B')])
    assert result['inputs']==1 and not result['ok']
    assert result['details'][0]['reason']=='input_contract_mismatch'


def posed_network(offset=.3):
    import pcbnew
    board=native_network()
    shunt=board.FindFootprintByReference('SHUNT')
    shunt.FindPadByNumber('a').SetPosition(pcbnew.VECTOR2I_MM(0,-1))
    shunt.FindPadByNumber('b').SetPosition(pcbnew.VECTOR2I_MM(0,1))
    board.FindFootprintByReference('MONITOR').SetPosition(pcbnew.VECTOR2I_MM(offset,5))
    return board


@pytest.mark.parametrize('angle',[0,90,180,270,37])
@pytest.mark.parametrize('flipped',[False,True])
def test_native_shunt_axis_alignment_is_rigid_transform_invariant(tmp_path,angle,flipped):
    import pcbnew
    board=posed_network()
    for fp in board.GetFootprints():
        if flipped:fp.Flip(pcbnew.VECTOR2I(0,0),True)
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        pos=fp.GetPosition();x,y=pos.x,pos.y
        fp.SetPosition(pcbnew.VECTOR2I(x+123000000,y+456000000))
    path=str(tmp_path/'transformed.kicad_pcb');pcbnew.SaveBoard(path,board,True)
    loaded=pcbnew.LoadBoard(path)
    evidence=topology.board_evidence(loaded,anchor_refs=['SHUNT'])
    result=topology.filtered_alignment(loaded,evidence,tolerance_mm=1.0)
    assert result['ok'] and result['checked']==1
    # Native integer-nm rotation and six-decimal PCB serialization can add a
    # few nm at arbitrary angles. This is not a clearance/tolerance relaxation.
    assert result['details'][0]['lateral_offset_mm']==pytest.approx(.3,abs=5e-6)


def test_current_flow_anchor_resolves_arbitrary_renamed_force_nets():
    board=posed_network()
    assert not topology.board_evidence(board)['ok']
    evidence=topology.board_evidence(board,anchor_refs=['SHUNT'])
    assert evidence['ok'] and evidence['details'][0]['selected']['anchor_ref']=='SHUNT'


def test_unrelated_nearby_shunt_cannot_hide_wrong_lane_and_checker_consumes_topology():
    import pcbnew
    import cec_constraints as constraints
    board=posed_network(offset=4)
    other=pcbnew.FOOTPRINT(board);other.SetReference('RS_DISTRACTOR')
    other.SetPosition(pcbnew.VECTOR2I_MM(4,0));board.Add(other)
    # Reproduce the former nearest-X criterion independently.
    owner=board.FindFootprintByReference('MONITOR')
    nearest=min([board.FindFootprintByReference('SHUNT'),other],
                key=lambda fp:abs(fp.GetPosition().x-owner.GetPosition().x))
    assert abs(nearest.GetPosition().x-owner.GetPosition().x)/1e6==0
    context={}
    with patch('cec_current_topology.board_current_domains',return_value={
            'FORCE_A':dict(complete=True,authority_refs=['SHUNT'])}):
        result=constraints._chk_kelvin_adj(board,'',context)
    assert result[0] is False
    assert result[2][0]['b']=='SHUNT'
    assert result[2][0]['lateral_offset_mm']==4
    assert context['sense_input_topology']['resolved']==1


def test_partial_current_authority_cannot_invent_an_anchor():
    import cec_constraints as constraints
    board=posed_network()
    with patch('cec_current_topology.board_current_domains',return_value={
            'FORCE_A':dict(complete=False,authority_refs=['SHUNT'])}):
        result=constraints._chk_kelvin_adj(board,'',{})
    assert result[0] is False and 'unproved' in result[1]


@pytest.mark.parametrize('ref,pin',[('MONITOR','8'),('SERIES_A','left')])
def test_alignment_rejects_stale_electrical_evidence(ref,pin):
    board=posed_network()
    evidence=topology.board_evidence(board,anchor_refs=['SHUNT'])
    board.FindFootprintByReference(ref).FindPadByNumber(pin).SetNetCode(0)
    with pytest.raises(ValueError,match='net changed'):
        topology.filtered_alignment(board,evidence,tolerance_mm=1.0)


def test_ambiguous_native_anchor_geometry_is_not_a_distance_pass():
    import pcbnew
    board=posed_network()
    evidence=topology.board_evidence(board,anchor_refs=['SHUNT'])
    shunt=board.FindFootprintByReference('SHUNT')
    pad=pcbnew.PAD(shunt);pad.SetNumber('a')
    pad.SetNetCode(shunt.FindPadByNumber('a').GetNetCode())
    pad.SetPosition(pcbnew.VECTOR2I_MM(2,3));shunt.Add(pad)
    with pytest.raises(ValueError,match='geometry is ambiguous'):
        topology.filtered_alignment(board,evidence,tolerance_mm=1.0)
