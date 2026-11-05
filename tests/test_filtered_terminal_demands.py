"""Filtered placement metrics must follow real nets on both sides of parts."""
import copy
from pathlib import Path

import pytest
import cec_sense_topology as topology
import cec_synth_pipeline as synth
from test_sense_topology import network, trace, native_network


def test_segments_end_at_resistor_pads_instead_of_shorting_across_filter():
    pads, inputs = network()
    row = trace(pads, inputs)['details'][0]
    segments = topology.placement_segments(row)
    assert len(segments) == 4
    assert [(s['net'], s['start']['ref'], s['end']['ref']) for s in segments] == [
        ('INPUT_A','MONITOR','SERIES_A'), ('FORCE_A','SERIES_A','SHUNT'),
        ('INPUT_B','MONITOR','SERIES_B'), ('FORCE_B','SERIES_B','SHUNT')]
    for s in segments:
        for end in (s['start'], s['end']):
            assert pads[end['ref']][end['pad']] == s['net']
        assert s['start']['ref'] != s['end']['ref']


def test_multiple_series_sections_never_become_one_fictitious_chord():
    pads, inputs = network()
    pads['SERIES_A']['right'] = 'MID'
    pads['EXTRA'] = {'x':'INPUT_A','y':'MID'}
    row = trace(pads, inputs, resistor_refs={'SERIES_A','SERIES_B','EXTRA'})['details'][0]
    segments = topology.placement_segments(row)
    assert [s['net'] for s in segments if s['leg']=='p'] == ['INPUT_A','MID','FORCE_A']
    assert len(segments) == 5


@pytest.mark.parametrize('fault', ['unresolved','series_net','anchor_net'])
def test_unqualified_or_discontinuous_evidence_fails_closed(fault):
    pads,inputs = network(); row=trace(pads,inputs)['details'][0]
    if fault=='unresolved':row['ok']=False
    if fault=='series_net':row['selected']['p']['series'][0]['input_net']='UNKNOWN'
    if fault=='anchor_net':row['selected']['n']['anchor_net']='UNKNOWN'
    with pytest.raises(ValueError):topology.placement_segments(row)


def native_placed_network():
    import pcbnew
    board = native_network()
    positions = {'SHUNT':(10,0), 'SERIES_A':(5,-2), 'SERIES_B':(5,2),
                 'MONITOR':(0,0), 'DIFF_CAP':(2,4)}
    local = {'SHUNT':{'a':(0,-2),'b':(0,2)},
             'SERIES_A':{'left':(.5,0),'right':(-.5,0)},
             'SERIES_B':{'left':(.5,0),'right':(-.5,0)},
             'MONITOR':{'8':(1,-1),'1':(1,1),'6':(-1,0)},
             'DIFF_CAP':{'1':(-.5,0),'2':(.5,0)}}
    for fp in board.GetFootprints():
        ref=fp.GetReference();x,y=positions[ref]
        fp.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        for pad in fp.Pads():
            dx,dy=local[ref][pad.GetNumber()]
            pad.SetPosition(pcbnew.VECTOR2I_MM(x+dx,y+dy))
    return board


def full_and_cheap(board, evidence=None):
    import cec_interface_eco
    evidence = evidence or topology.board_evidence(board,anchor_refs=['SHUNT'])
    poses = cec_interface_eco.poses(board)
    templates = synth._parallel_pour_pad_templates(board)
    details = synth._filtered_terminal_order_evidence(evidence,poses,templates,clearance=.25)
    specs = synth._parallel_pour_critical_terminal_specs({'critical_terminal_order':{'details':details}})
    cheap = synth._parallel_pour_critical_terminal_geometry(poses,templates,specs)
    return details, cheap, poses, templates, specs


@pytest.mark.parametrize('angle',[0,90,180,270,37])
@pytest.mark.parametrize('flipped',[False,True])
def test_loaded_native_full_and_cheap_agree_in_every_frame(tmp_path,angle,flipped):
    import pcbnew
    board=native_placed_network()
    for fp in board.GetFootprints():
        if flipped:fp.Flip(pcbnew.VECTOR2I(0,0),True)
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        pos=fp.GetPosition();x,y=pos.x,pos.y
        fp.SetPosition(pcbnew.VECTOR2I(x+129000000,y-71000000))
    path=str(tmp_path/'current.kicad_pcb');pcbnew.SaveBoard(path,board,True)
    before=Path(path).read_bytes()
    details,cheap,*_=full_and_cheap(pcbnew.LoadBoard(path))
    row=details[0]
    assert len(details)==cheap['qualified_relations']==1
    assert row['crossings']==cheap['key'][0]==0
    assert row['direct_length_mm']==cheap['key'][1]
    assert row['segment_count']==cheap['details'][0]['segment_count']==4
    assert row['series_refs']==['SERIES_A','SERIES_B']
    assert not cheap['details'][0]['copper_connectivity_proved']
    assert Path(path).read_bytes()==before


def test_crossed_input_rotation_is_found_without_moving_filters_or_shunt():
    import pcbnew
    board=native_placed_network();owner=board.FindFootprintByReference('MONITOR')
    owner.SetOrientationDegrees(180)
    details,cheap,*_=full_and_cheap(board)
    assert details[0]['crossings']>0 and cheap['key'][0]==details[0]['crossings']
    assert details[0]['recommended_rotation_deg']==0


@pytest.mark.parametrize('fault',['missing_pad','wrong_net','duplicate_position','missing_component','empty_segments'])
def test_cheap_path_cannot_disappear_on_stale_or_incomplete_templates(fault):
    board=native_placed_network()
    _,_,poses,templates,specs=full_and_cheap(board)
    templates=copy.deepcopy(templates)
    if fault=='missing_pad':templates['SERIES_A']=tuple(p for p in templates['SERIES_A'] if p['pad']!='left')
    if fault=='wrong_net':templates['SERIES_A'][0]['net']='UNRELATED'
    if fault=='duplicate_position':
        templates['SERIES_A']+=({**templates['SERIES_A'][0],'local':(200,300)},)
    if fault=='missing_component':del poses['SERIES_A']
    if fault=='empty_segments':specs[0]['demand_segments']=[]
    with pytest.raises(ValueError,match='current-input'):
        synth._parallel_pour_critical_terminal_geometry(poses,templates,specs)


def test_every_segment_affects_full_and_cheap_metric_not_just_the_ic_endpoint():
    import pcbnew
    board=native_placed_network()
    original=full_and_cheap(board)
    fp=board.FindFootprintByReference('SERIES_A');fp.SetPosition(pcbnew.VECTOR2I_MM(5,-5))
    moved=full_and_cheap(board)
    assert moved[0][0]['direct_length_mm']>original[0][0]['direct_length_mm']
    assert moved[0][0]['direct_length_mm']==moved[1]['key'][1]
    assert moved[0][0]['selected_pads']==original[0][0]['selected_pads']
