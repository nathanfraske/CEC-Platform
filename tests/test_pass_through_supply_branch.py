"""Saved native one-tap pass-through branches, no board or refdes policies."""
from copy import deepcopy
import math
import pcbnew
import pytest
import cec_supply_consumer_branch as branch
import cec_current_topology as topology
import cec_synth_pipeline as synth
import cec_route_dimensions as dimensions
import cec_field_coupling as field
import cec_force_current as force


def fixture(monkeypatch, tmp_path, angle=0, mirrored=False):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_high_current'; board.SetProperties(props)
    supply, output = '/arbitrary/FEED', '/arbitrary/DELIVERY'
    nets = {}
    for name in (supply, output, 'GND', 'OTHER'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    def fp(ref, value, fpid, mpn, pins):
        item = pcbnew.FOOTPRINT(board); item.SetReference(ref); item.SetValue(value)
        item.SetFPID(pcbnew.LIB_ID(*fpid.split(':'))); board.Add(item)
        if mpn: item.SetField('MPN', mpn)
        for pin, net, xy, size in pins:
            pad = pcbnew.PAD(item); pad.SetNumber(pin); pad.SetNet(nets[net])
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(*size)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetPosition(pcbnew.VECTOR2I_MM(*xy)); item.Add(pad)
        return item
    owner = fp('NO_PREFIX_OWNER', 'TPS2121', 'Manufacturer:RUX0012A', 'TPS2121RUXR', [
        ('7', supply, (5,8), (1,1)), ('2','OTHER',(5,4),(1,1)),
        ('1',output,(5,6),(1,1)), ('8',output,(7,6),(1,1))])
    cap = fp('NO_PREFIX_BYPASS', '100nF', 'Generic:C_0402_1005Metric', 'CL05B104KO5NNNC', [
        ('1', supply, (8,8), (1,1)), ('2','GND',(8,11),(1,1))])
    anchor = fp('UNCHANGED_ORIGIN', 'port', 'Generic:Port', None,
        [('1',supply,(25,8),(8,8))]).FindPadByNumber('1')
    sink = fp('UNCHANGED_DESTINATION', 'port', 'Generic:Port', None,
        [('1',supply,(40,8),(8,8))]).FindPadByNumber('1')
    row = dict(net=supply, device_package='TPS2121 RUX', pin='7', amps=3.0004,
        maximum_consumers=1, basis='existing explicit output envelope plus manufacturer quiescent maximum')
    declaration = dict(params=dict(supply_consumer_allocations=[row]))
    rail = dict(amps=20., geometry_margin=1.25, margin_included=False, source='board_design_basis')
    downstream = dict(rail, amps=3.)
    domain = dict(complete=True, authority_refs=[anchor.GetParentFootprint().GetReference(),
        sink.GetParentFootprint().GetReference()])
    monkeypatch.setattr(branch.policy, 'load', lambda *a, **k: deepcopy(declaration))
    monkeypatch.setattr(synth, 'spec_net_current_contract', lambda hint, net:
        deepcopy(rail if net == supply else downstream if net == output else None))
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **k: {supply: deepcopy(domain)})
    monkeypatch.setattr(dimensions, 'project_resolver', lambda *a, **k: lambda net:
        dict(track_width=.2, clearance=.2, via_diameter=.6, via_drill=.3))
    root = owner.FindPadByNumber('7')
    budget = branch.contract(board, force._uid(root), board_hint='unrelated_identity')
    width = math.ceil(budget['required_by_layer_mm']['F.Cu']*1e6)
    def track(start, end, width):
        t = pcbnew.PCB_TRACK(board); t.SetNet(nets[supply]); t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(*start)); t.SetEnd(pcbnew.VECTOR2I_MM(*end))
        t.SetWidth(width); t.SetLocked(True); board.Add(t); return t
    trunk = track((25,8),(40,8),math.ceil(budget['aggregate_required_by_layer_mm']['F.Cu']*1e6))
    incoming = [track((5,8),(8,8),width), track((8,8),(25,8),width)]
    group = branch.record(board,incoming,[],root_pad_uuid=force._uid(root),anchor_uuid=force._uid(anchor))
    for item in [*board.GetFootprints(), *board.GetTracks()]:
        if angle: item.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirrored: item.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    path = tmp_path/'board.kicad_pcb'; field._save_field_snapshot(board,path); board.SetFileName(str(path))
    return board,root,anchor,owner,cap,incoming,trunk,group,row,domain,downstream


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
def test_actual_saved_native_one_tap_and_new_bypass_island(monkeypatch,tmp_path,angle,mirrored):
    board,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream = fixture(monkeypatch,tmp_path,angle,mirrored)
    before = field._field_snapshot_inventory(board)
    proof = branch.inventory(board, board_hint='unrelated_identity', timeout_s=10.)
    assert proof['complete'] and len(proof['proofs']) == 1, proof
    assert set(proof['track_requirements']) == set(map(force._uid, tracks))
    detail = proof['proofs'][0]
    assert detail['budget']['current_authority']['amps'] == 3.0004
    assert detail['budget']['aggregate_current_authority']['amps'] == 20.
    assert detail['budget']['pass_through_input_bound']['output_current_authority'] == downstream
    assert detail['physical_trunk_tap_count'] == 1 and detail['shared_terminal_partitions_preserved']
    assert not detail['release_authority'] and not detail['inrush_fault_barrel_and_release_qualified']
    assert field._field_snapshot_inventory(board) == before
    loaded = pcbnew.LoadBoard(board.GetFileName())
    assert branch.inventory(loaded, board_hint='unrelated_identity', timeout_s=10.) == proof


@pytest.mark.parametrize('fault',['output_mismatch','output_unrated','missing_output','wrong_package',
    'allocation_below_output','authority_owner','incomplete_force_domain','extra_power_load','unselected_cap',
    'cap_cross_rail','second_tap','undersized_track','inner_outer_width_mismatch'])
def test_unknown_scope_or_current_bus_bridge_never_acquires_a_local_budget(monkeypatch,tmp_path,fault):
    board,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream = fixture(monkeypatch,tmp_path)
    if fault == 'output_mismatch': owner.FindPadByNumber('8').SetNet(root.GetNet())
    elif fault == 'output_unrated': downstream['source'] = 'guessed'
    elif fault == 'missing_output': owner.Remove(owner.FindPadByNumber('8'))
    elif fault == 'wrong_package': owner.SetFPID(pcbnew.LIB_ID('Manufacturer','WrongPackage'))
    elif fault == 'allocation_below_output': row['amps'] = 3.
    elif fault == 'authority_owner': domain['authority_refs'].append(owner.GetReference())
    elif fault == 'incomplete_force_domain': domain['complete'] = False
    elif fault == 'extra_power_load':
        other = pcbnew.FOOTPRINT(board); other.SetReference('ADDITIONAL_LOAD'); board.Add(other)
        pad = pcbnew.PAD(other); pad.SetNumber('1'); pad.SetNet(root.GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(1,1)); pad.SetPosition(pcbnew.VECTOR2I_MM(15,8)); other.Add(pad)
    elif fault == 'unselected_cap': cap.SetField('MPN','unknown')
    elif fault == 'cap_cross_rail': cap.FindPadByNumber('2').SetNet(owner.FindPadByNumber('1').GetNet())
    elif fault == 'second_tap':
        new = pcbnew.PCB_TRACK(board); new.SetNet(root.GetNet()); new.SetLayer(pcbnew.F_Cu)
        new.SetWidth(tracks[0].GetWidth()); new.SetStart(pcbnew.VECTOR2I_MM(8,8)); new.SetEnd(pcbnew.VECTOR2I_MM(40,8))
        board.Add(new); group.AddItem(new)
    elif fault == 'undersized_track': tracks[0].SetWidth(200000)
    elif fault == 'inner_outer_width_mismatch': tracks[0].SetLayer(pcbnew.In2_Cu)
    result = branch.inventory(board, board_hint='unrelated_identity', timeout_s=10.)
    assert not result['complete'] and not result['track_requirements'] and result['refusals'],result


def retained_portal(board, tracks):
    start, end = tracks[1].GetStart(), tracks[1].GetEnd()
    centre = pcbnew.VECTOR2I((start.x+end.x)//2,(start.y+end.y)//2)
    via = pcbnew.PCB_VIA(board); via.SetNet(tracks[1].GetNet()); via.SetPosition(centre)
    via.SetWidth(600000); via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); board.Add(via)
    tail = pcbnew.PCB_TRACK(board); tail.SetNet(via.GetNet()); tail.SetLayer(pcbnew.B_Cu)
    tail.SetWidth(500000); tail.SetStart(centre)
    # Perpendicular to the incoming line; rotations and flips use the actual
    # saved native endpoints, not a reference-specific coordinate convention.
    dx,dy=end.x-start.x,end.y-start.y; scale=max(abs(dx),abs(dy))
    tail.SetEnd(pcbnew.VECTOR2I(centre.x-dy*2000000//scale,centre.y+dx*2000000//scale))
    board.Add(tail); return via,tail


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
def test_contacted_old_pad_free_portal_is_not_a_second_bus_tap(monkeypatch,tmp_path,angle,mirrored):
    board,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream = fixture(monkeypatch,tmp_path,angle,mirrored)
    portal,tail=retained_portal(board,tracks)
    field._save_field_snapshot(board,board.GetFileName())
    loaded=pcbnew.LoadBoard(board.GetFileName())
    proof=branch.inventory(loaded,board_hint='unrelated_identity',timeout_s=10.)
    assert proof['complete'],proof
    detail=proof['proofs'][0]
    assert {force._uid(portal),force._uid(tail)} <= set(detail['retained_consumer_island_uuids'])
    assert set(detail['exact_branch_material_uuids']) == set(map(force._uid,tracks))
    assert detail['physical_trunk_tap_count']==1 and detail['aggregate_rail_budget_unchanged']


@pytest.mark.parametrize('fault',['other_ic','third_cap','oversized_source_island','off_anchor_tap'])
def test_retained_portal_does_not_hide_other_loads_or_two_source_taps(monkeypatch,tmp_path,fault):
    board,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream=fixture(monkeypatch,tmp_path)
    portal,tail=retained_portal(board,tracks)
    if fault=='other_ic':
        fp=pcbnew.FOOTPRINT(board); fp.SetReference('UNMODELED_LOAD'); board.Add(fp)
        pad=pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(root.GetNet())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(1,1)); pad.SetPosition(portal.GetPosition()); fp.Add(pad)
    elif fault=='third_cap':
        for n in range(2):
            fp=pcbnew.FOOTPRINT(board); fp.SetReference('EXTRA_CAP_'+str(n)); fp.SetValue('100nF')
            fp.SetField('MPN','CL05B104KO5NNNC'); fp.SetFPID(pcbnew.LIB_ID('Generic','C_0402_1005Metric')); board.Add(fp)
            for pin,net,offset in [('1',root.GetNet(),0),('2',cap.FindPadByNumber('2').GetNet(),2000000)]:
                pad=pcbnew.PAD(fp); pad.SetNumber(pin); pad.SetNet(net)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetLayerSet(pcbnew.PAD.SMDMask())
                pad.SetSize(pcbnew.VECTOR2I_MM(1,1)); pad.SetPosition(pcbnew.VECTOR2I(portal.GetPosition().x,portal.GetPosition().y+offset)); fp.Add(pad)
    elif fault=='oversized_source_island':
        for n in range(34):
            t=pcbnew.PCB_TRACK(board); t.SetNet(root.GetNet()); t.SetLayer(pcbnew.B_Cu)
            t.SetWidth(500000); t.SetStart(tail.GetStart()); t.SetEnd(tail.GetEnd()); board.Add(t)
    else:
        # This old portal touches the anchor component away from the one
        # allowed capture. Excluding its source component in discovery must
        # not exclude that physical second contact from the receiving proof.
        tail.SetLayer(pcbnew.F_Cu); tail.SetEnd(pcbnew.VECTOR2I_MM(35,8))
    proof=branch.inventory(board,board_hint='unrelated_identity',timeout_s=10.)
    assert not proof['complete'] and not proof['track_requirements'] and proof['refusals'],proof
