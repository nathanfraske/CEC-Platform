"""Saved ordinary process minima are not interactive netclass preferences.

Fixture current/terminal authority is explicit. No mock whole-suite gate or
lowered Source clearance/current/web requirement admits a real board here.
"""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_distributed_supply_layer_join as join
import cec_force_current as force
import cec_route_dimensions as dimensions
import cec_field_coupling as field
from test_distributed_native_frontier_join import geometry
from test_distributed_supply_layer_join import source_boundary, companions


def saved_chain(tmp_path, turn=0, face=pcbnew.F_Cu, mutate=None, project_rules=None):
    board, net, pads, source, point, items = geometry(tmp_path, turn, face)
    for item in items[3:]:
        board.Remove(item)
    pcbnew.SaveBoard(str(source), board)
    if project_rules is not None:
        source.with_suffix('.kicad_pro').write_text(json.dumps(dict(board=dict(
            design_settings=dict(rules=project_rules)))))
    parent = pcbnew.LoadBoard(str(source))
    with source_boundary(net):
        proposal = join.plan_native_frontier(parent, source, board_hint='arbitrary-current-owner',
            net=net, pad_uuids=[force._uid(p) for p in pads[:2]])
        assert proposal['complete'], proposal
        minimum = join._via_geometry(parent, proposal['contract'], source_minimum=True)
        preferred = join._via_geometry(parent, proposal['contract'])
    child = pcbnew.LoadBoard(str(source))
    code = child.GetNetcodeFromNetname(net)
    for a,b,layer in [((12,22),(16,22),pcbnew.In2_Cu), ((16,22),(16,20),face)]:
        item = pcbnew.PCB_TRACK(child)
        item.SetStart(point(*a)); item.SetEnd(point(*b))
        item.SetLayer(layer); item.SetWidth(500000); item.SetNetCode(code)
        child.Add(item)
    via = pcbnew.PCB_VIA(child)
    via.SetPosition(point(16,22)); via.SetWidth(round(minimum[0]*1e6))
    via.SetDrill(round(minimum[1]*1e6)); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); via.SetNetCode(code)
    child.Add(via)
    if mutate is not None:
        mutate(via, child)
    candidate = tmp_path/'minimum-child.kicad_pcb'
    field._save_field_snapshot(child, candidate)
    companions(source, candidate)
    return net, pads, source, candidate, minimum, preferred


@pytest.mark.parametrize('turn,face', [(r,f) for r in range(4) for f in (pcbnew.F_Cu,pcbnew.B_Cu)])
def test_saved_minimum_full_web_is_positive_only_in_distinct_tier(tmp_path,turn,face):
    net,pads,source,child,minimum,preferred = saved_chain(tmp_path,turn,face)
    before = source.read_bytes()
    assert minimum[1] < preferred[1] and minimum[0] < preferred[0]
    assert round((minimum[0]-minimum[1])*1e6) >= 500000
    ids = [force._uid(p) for p in pads[:2]]
    with source_boundary(net):
        received = join.receive_native_frontier(source,child,board_hint='arbitrary-current-owner',
            net=net,pad_uuids=ids)
        legacy = join.receive(source,child,board_hint='arbitrary-current-owner',net=net,pad_uuids=ids)
    assert received['ok'] and received['complete'], received
    assert not legacy['ok']
    assert received['exactly_two_source_islands_joined'] and received['all_source_partitions_preserved']
    assert not received['current_qualified'] and not received['plated_barrel_current_qualified']
    assert source.read_bytes() == before


@pytest.mark.parametrize('rules', [
    {'min_through_hole_diameter':.35},
    {'min_via_diameter':1.},
    {'min_via_annular_width':.35},
    {'min_through_hole_diameter':.3,'min_via_annular_width':.3,'min_via_diameter':.95},
])
def test_higher_exact_saved_project_floor_is_preserved_in_saved_positive(tmp_path,rules):
    net,pads,source,child,minimum,preferred = saved_chain(tmp_path,project_rules=rules)
    assert minimum[0] >= rules.get('min_via_diameter',0)
    assert minimum[1] >= rules.get('min_through_hole_diameter',0)
    assert round((minimum[0]-minimum[1])*1e6) >= round(2e6*rules.get('min_via_annular_width',0))
    with source_boundary(net):
        received = join.receive_native_frontier(source,child,board_hint='arbitrary-current-owner',
            net=net,pad_uuids=[force._uid(p) for p in pads[:2]])
    assert received['ok'] and received['complete'], received


@pytest.mark.parametrize('fault', ['below_drill','below_land','weak_web','nonuniform_faces','not_through'])
def test_smaller_tier_never_waives_actual_process_or_whole_web(tmp_path,fault):
    def mutate(via, child):
        if fault == 'below_drill':
            via.SetDrill(199999)
        elif fault == 'below_land':
            via.SetWidth(499999)
        elif fault == 'weak_web':
            via.SetWidth(via.GetDrillValue()+499999)
        elif fault == 'nonuniform_faces':
            via.SetWidth(via.GetWidth()-1,pcbnew.In2_Cu)
        else:
            via.SetViaType(pcbnew.VIATYPE_BLIND)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
    net,pads,source,child,_,_ = saved_chain(tmp_path,mutate=mutate)
    with source_boundary(net):
        received = join.receive_native_frontier(source,child,board_hint='arbitrary-current-owner',
            net=net,pad_uuids=[force._uid(p) for p in pads[:2]])
    assert not received['ok'] and received['errors'], received


@pytest.mark.parametrize('key,value', [
    ('min_via_diameter',True), ('min_through_hole_diameter',False),
    ('min_via_annular_width',float('nan')), ('min_through_hole_diameter',float('inf')),
    ('min_via_diameter',-.1), ('min_via_annular_width','0.1'),
    ('min_through_hole_diameter',11.),
])
def test_malformed_exact_saved_floor_cannot_fund_geometry(tmp_path,key,value):
    board,_,_,source,_,_ = geometry(tmp_path)
    board.SetFileName(str(source))
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(board=dict(
        design_settings=dict(rules={key:value})))))
    with pytest.raises(ValueError,match='finite_distributed_source_via_floor_required'):
        join._source_via_limits(board)


def test_saved_lower_floor_never_reduces_native_limit(tmp_path):
    board,_,_,source,_,_ = geometry(tmp_path)
    board.SetFileName(str(source))
    board.GetDesignSettings().m_ViasMinSize = 800000
    board.GetDesignSettings().m_MinThroughDrill = 350000
    board.GetDesignSettings().m_ViasMinAnnularWidth = 200000
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(board=dict(
        design_settings=dict(rules=dict(min_via_diameter=.5,
            min_through_hole_diameter=.2,min_via_annular_width=.1))))))
    limits = join._source_via_limits(board)
    assert limits['via_diameter'] == .8 and limits['via_drill'] == .35 and limits['annular'] == .2


@pytest.mark.parametrize('rules,diameter,drill', [
    ({'min_through_hole_diameter':.4},800000,300000),
    ({'min_via_diameter':1.},900000,400000),
    ({'min_via_annular_width':.3},900000,400000),
])
def test_whole_web_does_not_override_higher_saved_project_floor(tmp_path,rules,diameter,drill):
    def mutate(via, child):
        via.SetWidth(diameter)
        via.SetDrill(drill)
    net,pads,source,child,_,_ = saved_chain(tmp_path,project_rules=rules,mutate=mutate)
    assert diameter-drill >= 500000
    with source_boundary(net):
        received = join.receive_native_frontier(source,child,board_hint='arbitrary-current-owner',
            net=net,pad_uuids=[force._uid(p) for p in pads[:2]])
    assert not received['ok'] and received['errors'], received


@pytest.mark.parametrize('mode',[None,0,1,{},[],'true'])
def test_source_minimum_mode_is_not_truthy_caller_permission(tmp_path,mode):
    board,net,pads,source,_,_ = geometry(tmp_path)
    with source_boundary(net):
        proposal = join.plan_native_frontier(board,source,board_hint='arbitrary-current-owner',
            net=net,pad_uuids=[force._uid(p) for p in pads[:2]])
        with pytest.raises(ValueError,match='explicit_distributed_via_geometry_mode_required'):
            join._via_geometry(board,proposal['contract'],source_minimum=mode)
