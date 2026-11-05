"""Saved complete-cell replay cannot borrow a worker's cut or a green graph."""
import copy
import json
import time
import pcbnew
import pytest
import cec_complete_cell_receiving as receiving
import cec_cell_escape_replan as escape
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_complete_cell_connections import native_source


def saved_pair(tmp_path,monkeypatch,quarter=0):
    path,parent,_,initial=native_source(tmp_path,monkeypatch,turn=quarter)
    poses=copy.deepcopy(initial['poses'])
    for ref in initial['device_contracts']:
        fp=parent.FindFootprintByReference(ref)
        poses[ref]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    cap_ref=next(iter(initial['selected_bypasses']))
    cap=parent.FindFootprintByReference(cap_ref)
    gp=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    via=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA')
    # This receiver deliberately owns no new-barrel process. Exercise an
    # orientation-invariant motion toward the literal retained source via.
    delta=[(via.GetPosition()[i]-gp.GetPosition()[i])*.3 for i in (0,1)]
    poses[cap_ref]=[(cap.GetPosition()[i]+delta[i])/1e6 for i in (0,1)]+[cap.GetOrientationDegrees()]
    plan=escape.prepare(parent,poses,board_hint='opaque')
    board=pcbnew.LoadBoard(str(path));escape.apply_private(board,plan)
    proof=escape.complete_connection_screen(path,board,plan,board_hint='opaque',per_obligation_leases=True)
    assert proof['complete'],proof
    packet=dict(proof['packet'],domains={key:[q for q in choices if all(op[0]=='trk' for op in q['ops'])]
        for key,choices in proof['packet']['domains'].items()})
    selection=escape.choose(board,packet)
    assert selection['complete'],packet
    escape.construct_private(board,packet,selection)
    target=force._copy_family(path,tmp_path/'child');additive._ground_refill(board)
    field._save_field_snapshot(board,target)
    monkeypatch.setattr(receiving.force,'_family',lambda p,h:force._hash(p))
    return path,target,plan


@pytest.mark.parametrize('quarter',range(4))
def test_actual_saved_cell_rederives_cuts_poses_paths_and_every_surviving_partition(tmp_path,monkeypatch,quarter):
    source,child,plan=saved_pair(tmp_path,monkeypatch,quarter)
    before=[p.read_bytes() for p in (source,child)]
    result=receiving.receive(source,child,board_hint='opaque')
    assert result['ok'] and result['complete'],result
    assert set(result['retired_track_uuids'])==set(plan['retired_track_uuids'])
    assert result['all_original_surviving_native_partitions_preserved']
    assert result['all_source_ground_returns']['ok'] and result['actual_native_terminal_paths']
    assert result['independent_exact_cut_pose_and_additions']['ok']
    assert not any(result[k] for k in ('routing_admitted','fab_ready','release_authority','current_qualified'))
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('fault',['part_value','land_size','land_net','flip','dnp','unrelated_pose',
    'unowned_cut','changed_retained_track','missing_restoration','extra_foreign_track','extra_ground_barrel'])
def test_hostile_saved_delta_cannot_substitute_for_source_owned_reconstruction(tmp_path,monkeypatch,fault):
    source,child,plan=saved_pair(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child));cap=board.FindFootprintByReference(next(iter(plan['selected_bypasses'])))
    source_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    retained=[t for t in board.GetTracks() if force._uid(t) in source_ids]
    incoming=[t for t in board.GetTracks() if force._uid(t) not in source_ids]
    if fault=='part_value':cap.SetValue('not-the-original-capacitance')
    elif fault=='land_size':next(iter(cap.Pads())).SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='land_net':next(iter(cap.Pads())).SetNet(board.FindNet('OUT'))
    elif fault=='flip':cap.Flip(cap.GetPosition(),False)
    elif fault=='dnp':cap.SetDNP(True)
    elif fault=='unrelated_pose':board.FindFootprintByReference('external_OUT').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='unowned_cut':discard_items(board,[retained[0]])
    elif fault=='changed_retained_track':
        item=next(t for t in retained if t.GetClass()=='PCB_TRACK');item.SetWidth(item.GetWidth()+10000)
    elif fault=='missing_restoration':discard_items(board,incoming)
    elif fault=='extra_ground_barrel':
        v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(25,25))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(600000);v.SetDrill(300000);board.Add(v)
    else:
        t=pcbnew.PCB_TRACK(board);t.SetNet(board.FindNet('OUT'));t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(25,25));t.SetEnd(pcbnew.VECTOR2I_MM(26,25));t.SetWidth(200000);board.Add(t)
    pcbnew.SaveBoard(str(child),board)
    before=source.read_bytes();result=receiving.receive(source,child,board_hint='opaque')
    assert not result['ok'] and not result['complete'] and result['errors'],result
    assert source.read_bytes()==before and not result['routing_admitted']


@pytest.mark.parametrize('changed',[False,True])
def test_json_layer_key_normalization_preserves_the_entire_current_contract(tmp_path,monkeypatch,changed):
    source,child,plan=saved_pair(tmp_path,monkeypatch)
    parent=pcbnew.LoadBoard(str(source));board=pcbnew.LoadBoard(str(child))
    projected=pcbnew.LoadBoard(str(source));escape.apply_private(projected,plan)
    requests=escape.obligations(parent,projected,plan)
    contract=dict(required_by_layer_nm={int(pcbnew.F_Cu):200000},synthetic_contract_identity='immutable')
    for request in requests.values():
        if request['net']=='RAIL':request['unchanged_full_rail_current_contract']=json.loads(json.dumps(contract))
    def current(b,net):
        assert net=='RAIL'
        return dict(contract,synthetic_contract_identity='changed') if b is board and changed else contract
    monkeypatch.setattr(receiving.cells,'_supply_current_widths',current)
    old={force._uid(t) for t in parent.GetTracks()}
    incoming={force._uid(t) for t in board.GetTracks()}-old
    if changed:
        with pytest.raises(ValueError,match='original_current_contract_changed'):
            receiving._receive_paths(parent,board,requests,incoming,'opaque',time.monotonic()+10.,
                source_proposal=plan)
    else:
        # Ground cuts now require independent Source expectations even when
        # this fixture's focus is the separate full-rail JSON contract.
        # A caller-authored request dictionary is not Ground authority.
        proofs=receiving._receive_paths(parent,board,requests,incoming,'opaque',time.monotonic()+10.,
            source_proposal=plan)
        assert proofs and any(p['kind']=='local_supply' for p in proofs)


@pytest.mark.parametrize('options',[{'timeout_s':True},{'timeout_s':11},{'timeout_s':0},
    {'max_shift_mm':True},{'max_shift_mm':33},{'max_shift_mm':float('nan')},
    {'allow_owned_locked_escapes':1},{'board_hint':''}])
def test_unbounded_or_truthy_receiving_scope_is_refused_before_source_reads(options):
    kwargs=dict(board_hint='opaque');kwargs.update(options)
    with pytest.raises(ValueError,match='bounded_complete_saved_cell'):
        receiving.receive('no-source','no-candidate',**kwargs)
