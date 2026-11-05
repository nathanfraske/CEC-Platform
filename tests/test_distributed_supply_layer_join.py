"""Real saved native joins; only Source/current compilation is a fixture.

No mocked whole-board gate publishes a candidate.  Full-load trace/web
geometry remains distinct from unknown barrel ampacity/thermal qualification.
"""
from contextlib import contextmanager
import copy
import json
import shutil
import time
from unittest import mock

import pcbnew
import pytest
import cec_distributed_supply_layer_join as join
import cec_distributed_supply as supply
import cec_distributed_supply_prefix as prefixes
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_distributed_supply import fixture, authority
from test_distributed_supply_prefix import compile_boundary


@contextmanager
def source_boundary(net):
    current = dict(amps=.2, geometry_margin=1., margin_included=True,
                   source='component_power_budget')
    real_audit = supply.audit
    def audit(board, **kwargs):
        kwargs['netclass_resolver'] = lambda n: dict(name='Power', track_width=.5, clearance=.2)
        return real_audit(board, **kwargs)
    with authority(net, current), mock.patch.object(prefixes, 'prepare', side_effect=compile_boundary), \
            mock.patch.object(supply, 'audit', side_effect=audit), \
            mock.patch.object(fr, '_project_netclass_resolver', return_value=lambda n: dict(
                name='Power', track_width=.5, clearance=.2, via_diameter=.8, via_drill=.4)):
        yield


def native(tmp_path, turn=0, face=pcbnew.F_Cu):
    board, net = fixture(tmp_path, name='/renamed/aggregate', turn=turn, layer=face)
    pads = sorted((p for fp in board.GetFootprints() for p in fp.Pads()),
                  key=lambda p: p.GetNumber())
    source = tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    return board, net, pads, source


def companions(source, candidate):
    for ext in force._sidecars(source):
        p = source.with_suffix(ext)
        if p.is_file():
            shutil.copy2(p, candidate.with_suffix(ext))


def add_chain(board, pads, *, turn=0, face=pcbnew.F_Cu, width=.5, diameter=.9):
    def point(x, y):
        for _ in range(turn):
            x, y = 40-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    other = pcbnew.B_Cu if face == pcbnew.F_Cu else pcbnew.F_Cu
    made = []
    for start, end, layer in [((8,20),(8,22),face),((8,22),(16,22),other),
                               ((16,22),(16,20),face)]:
        t = pcbnew.PCB_TRACK(board); t.SetStart(point(*start)); t.SetEnd(point(*end))
        t.SetLayer(layer); t.SetWidth(pcbnew.FromMM(width)); t.SetNetCode(pads[0].GetNetCode())
        board.Add(t); made.append(t)
    for at in [(8,22),(16,22)]:
        v = pcbnew.PCB_VIA(board); v.SetPosition(point(*at)); v.SetWidth(pcbnew.FromMM(diameter))
        v.SetDrill(pcbnew.FromMM(.4)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNetCode(pads[0].GetNetCode())
        board.Add(v); made.append(v)
    return made


@pytest.mark.parametrize('seconds', [True, False, 0, -1, 11, float('nan'), float('inf'), '10'])
def test_real_short_lease_required(seconds):
    with pytest.raises(ValueError):
        join._deadline(seconds)


@pytest.mark.parametrize('ids', [[], ['x'], ['x','x'], ['x',True], ['x',''], 'xy', ['x','y','z']])
def test_only_two_existing_identity_requests(ids):
    with pytest.raises(ValueError):
        join._ids(ids)


@pytest.mark.parametrize('turn,face', [(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),
                                      (2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
def test_real_saved_two_island_join_preserves_unknown_vertical_capacity(tmp_path, turn, face):
    board, net, pads, source = native(tmp_path, turn, face)
    original = source.read_bytes(); ids = [force._uid(p) for p in pads[:2]]
    with source_boundary(net):
        proposal = join.plan(pcbnew.LoadBoard(str(source)), source,
            board_hint='arbitrary-source-family', net=net, pad_uuids=ids)
        assert proposal['complete'], proposal
        child = pcbnew.LoadBoard(str(source)); live = join._source_pads(child, proposal)
        by_pin = sorted(live, key=lambda p:p.GetNumber())
        add_chain(child, by_pin, turn=turn, face=face)
        candidate = tmp_path/'child.kicad_pcb'; field._save_field_snapshot(child, candidate)
        companions(source, candidate)
        received = join.receive(source, candidate, board_hint='arbitrary-source-family',
                                net=net, pad_uuids=ids)
    assert received['ok'] and received['complete'], received
    assert received['source_components'] == 3 and received['candidate_components'] == 2
    assert len(received['actual_native_barrel_contacts']) == 2
    assert received['existing_rating_graphs_unchanged']
    assert received['unresolved_barrel_ampacity_and_thermal_debt']
    assert not received['plated_barrel_current_qualified']
    assert not received['current_qualified'] and not received['thermal_qualified']
    assert received['whole_shared_stage_still_required'] and not received['release_authority']
    assert source.read_bytes() == original


@pytest.mark.parametrize('fault', ['width','web','branch','cycle','foreign_net','wrong_face',
                                  'third_island','middle_pickup','source_change','pad_moved',
                                  'source_drill','source_diameter'])
def test_saved_mutations_are_not_received(tmp_path, fault):
    board, net, pads, source = native(tmp_path)
    ids = [force._uid(p) for p in pads[:2]]
    child = pcbnew.LoadBoard(str(source))
    live = sorted((p for f in child.GetFootprints() for p in f.Pads()), key=lambda p:p.GetNumber())
    incoming = add_chain(child, live, width=.2 if fault=='width' else .5,
                         diameter=.8 if fault=='web' else .9)
    def extra(start, end, layer=pcbnew.F_Cu):
        t = pcbnew.PCB_TRACK(child); t.SetStart(pcbnew.VECTOR2I_MM(*start))
        t.SetEnd(pcbnew.VECTOR2I_MM(*end)); t.SetWidth(500000); t.SetLayer(layer)
        t.SetNetCode(live[0].GetNetCode()); child.Add(t)
    if fault=='branch': extra((8,22),(6,22), pcbnew.B_Cu)
    elif fault=='source_drill':
        for v in incoming:
            if v.GetClass()=='PCB_VIA':v.SetDrill(300000)
    elif fault=='source_diameter':
        # Keep full .5 web, but violate the larger authored source land.
        for v in incoming:
            if v.GetClass()=='PCB_VIA':v.SetWidth(800000);v.SetDrill(300000)
    elif fault=='cycle':
        extra((8,20),(10,20)); extra((10,20),(10,22)); extra((10,22),(8,22))
    elif fault=='foreign_net':
        pass  # Forge the actual literal after the identity-preserving writer.
    elif fault=='wrong_face': incoming[1].SetLayer(pcbnew.In1_Cu)
    elif fault=='third_island':
        # A continuous path can pick up a third old island without a drawn T.
        back = pcbnew.LSET(); back.AddLayer(pcbnew.B_Cu)
        live[2].SetPosition(pcbnew.VECTOR2I_MM(12,22)); live[2].SetLayerSet(back)
        # This is Source geometry too, not an authorized candidate-only move.
        parent=pcbnew.LoadBoard(str(source)); old=next(p for f in parent.GetFootprints()
            for p in f.Pads() if p.GetNumber()=='3')
        old.SetPosition(pcbnew.VECTOR2I_MM(12,22)); old.SetLayerSet(back)
        pcbnew.SaveBoard(str(source),parent)
    elif fault=='middle_pickup':
        parent=pcbnew.LoadBoard(str(source))
        t=pcbnew.PCB_TRACK(parent);t.SetStart(pcbnew.VECTOR2I_MM(8,20));t.SetEnd(pcbnew.VECTOR2I_MM(8,22))
        t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(live[0].GetNetCode());parent.Add(t)
        pcbnew.SaveBoard(str(source),parent)
        child.Add(t.Duplicate())
    elif fault=='source_change': incoming[0].SetLocked(True); live[2].SetSize(pcbnew.VECTOR2I_MM(1.6,1.6))
    elif fault=='pad_moved': live[0].SetPosition(pcbnew.VECTOR2I_MM(7,20))
    candidate=tmp_path/'child.kicad_pcb';field._save_field_snapshot(child,candidate)
    if fault=='foreign_net':
        root,nodes=additive._nodes(candidate)
        node=nodes[force._uid(incoming[0])]
        field_net=next(v for v in node if isinstance(v,list)and v and v[0]=='net')
        field_net[1]=json.dumps('foreign')
        candidate.write_text(additive._render(root)+'\n')
    companions(source, candidate)
    with source_boundary(net):
        received=join.receive(source,candidate,board_hint='arbitrary-source-family',net=net,pad_uuids=ids)
    assert not received['ok'] and not received['complete'] and received['errors'], received


@pytest.mark.parametrize('fault', ['amps','width','pad','layer','complete_type','source','canonical'])
def test_forged_proposals_never_reach_geometry(tmp_path, fault):
    board,net,pads,source=native(tmp_path)
    candidate=tmp_path/'child.kicad_pcb';shutil.copy2(source,candidate)
    with source_boundary(net):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete']
        q=json.loads(json.dumps(proposal))
        companions(source, candidate)
        if fault=='amps':q['contract']['current_authority']['amps']/=2
        elif fault=='width':q['contract']['required_by_layer_mm']['F.Cu']/=2
        elif fault=='pad':q['pad_uuids'][0]='missing'
        elif fault=='layer':q['contract']['routing_layers'].append('In1.Cu')
        elif fault=='complete_type':q['complete']=1
        elif fault=='source':q['source_sha256']='0'*64
        elif fault=='canonical':q['source_terminal_records']={}
        with mock.patch.object(fr,'_multilayer_maze_lastmile_ops',side_effect=AssertionError('forged geometry')):
            with pytest.raises(ValueError):
                join.construct_private(source,candidate,q,board_hint='arbitrary-source-family')
    assert source.read_bytes()==candidate.read_bytes()


def test_actual_public_constructor_searches_three_dimensions_under_one_lease(tmp_path):
    board,net,pads,source=native(tmp_path)
    # A foreign F-only divider forces the actual search to change faces.
    foreign=pcbnew.NETINFO_ITEM(board,'foreign');board.Add(foreign)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('unrelated')
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1,40))
    p.SetPosition(pcbnew.VECTOR2I_MM(12,20));p.SetNet(foreign)
    mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);p.SetLayerSet(mask);fp.Add(p);board.Add(fp)
    pcbnew.SaveBoard(str(source),board)
    candidate=tmp_path/'child.kicad_pcb';shutil.copy2(source,candidate)
    with source_boundary(net):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete']
        companions(source, candidate)
        made=join.construct_private(source,candidate,json.loads(json.dumps(proposal)),
                                    board_hint='arbitrary-source-family',timeout_s=10.)
        assert made['complete'],made
        companions(source, candidate)
        saved=join.receive(source,candidate,board_hint='arbitrary-source-family',net=net,
                            pad_uuids=proposal['pad_uuids'])
    assert saved['ok']and saved['complete'],saved


def test_new_vias_must_respect_each_other_not_only_parent_holes(tmp_path):
    board,net,pads,source=native(tmp_path)
    board.GetDesignSettings().m_HoleToHoleMin=800000
    pcbnew.SaveBoard(str(source),board)
    # Board.Save does not guarantee an immediate project-file flush. Bind
    # the actual saved rule before either receiving board is loaded.
    project=source.with_suffix('.kicad_pro')
    data=json.loads(project.read_text())if project.is_file()else{}
    data.setdefault('board',{}).setdefault('design_settings',{}).setdefault('rules',{})[
        'min_hole_to_hole']=.8
    project.write_text(json.dumps(data))
    child=pcbnew.LoadBoard(str(source));made=[]
    for start,end,face in [((8,20),(10,22),pcbnew.F_Cu),
        ((10,22),(11.5,22),pcbnew.B_Cu),((11.5,22),(13.5,20),pcbnew.F_Cu),
        ((13.5,20),(16,20),pcbnew.F_Cu)]:
        t=pcbnew.PCB_TRACK(child);t.SetStart(pcbnew.VECTOR2I_MM(*start));t.SetEnd(pcbnew.VECTOR2I_MM(*end))
        t.SetLayer(face);t.SetWidth(500000);t.SetNetCode(pads[0].GetNetCode());child.Add(t)
    for point in [(10,22),(11.5,22)]:
        v=pcbnew.PCB_VIA(child);v.SetPosition(pcbnew.VECTOR2I_MM(*point));v.SetWidth(1300000)
        v.SetDrill(800000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNetCode(pads[0].GetNetCode());child.Add(v)
    candidate=tmp_path/'child.kicad_pcb';field._save_field_snapshot(child,candidate)
    companions(source,candidate)
    with source_boundary(net):
        proof=join.receive(source,candidate,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
    assert not proof['ok']and 'hole_spacing_required' in str(proof['errors']),proof


@pytest.mark.parametrize('width,expected',[(200000,False),(500000,True)])
def test_native_ports_do_not_credit_thin_source_tracks(tmp_path,width,expected):
    board,net,pads,source=native(tmp_path)
    t=pcbnew.PCB_TRACK(board);t.SetStart(pads[0].GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(8,23))
    t.SetLayer(pcbnew.F_Cu);t.SetWidth(width);t.SetNetCode(pads[0].GetNetCode());board.Add(t)
    pcbnew.SaveBoard(str(source),board)
    with source_boundary(net):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
        menus=join._ports(board,proposal,time.monotonic()+2.)
    actual=[port for menu in menus for port in menu if port['point_nm']==[8000000,23000000]]
    assert bool(actual)is expected


def test_explicit_force_domain_and_untyped_endpoints_are_not_reclassified(tmp_path):
    board,net,pads,source=native(tmp_path)
    with source_boundary(net),mock.patch.object(supply,'audit',return_value={
            'contracts':{},'refusals':{net:dict(reason='aggregate_current_domain_owned')}}):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
    assert not proposal['complete']and not proposal['current_authority_changed']
    with source_boundary(net),mock.patch.object(prefixes,'prepare',return_value={
            'contracts':{net:{}},'pads':{},'source_bindings':{}}):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
                           pad_uuids=[force._uid(p)for p in pads[:2]])
    assert not proposal['complete']and proposal['reason']=='canonical_supply_or_shunt_terminal_required'
