"""Native Source corridors remain mandatory geometry, never cut/current authority.

Only the synthetic Source current-domain catalog is injected. Manufacturer,
input role, shunt topology, native lands, ordering and saved path checks run
through their real implementations.
"""
import copy
import math

import pcbnew
import pytest

import cec_cell_row_rebuild as row
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_measurement_corridor as corridor
import cec_source_literal_additions as literal
from test_measurement_terminal_route import fixture as native_fixture


def _pads(board):
    return {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}


def case(tmp_path, monkeypatch, quarter=0, source_fault=None):
    board, _demand, root, target = native_fixture(quarter)
    owner = root.GetParentFootprint()
    owner.SetReference('RENAMED_MONITOR')
    target.GetParentFootprint().SetReference('RENAMED_SHUNT')
    if source_fault == 'manufacturer': owner.SetValue('UNKNOWN_INPUT_DEVICE')
    elif source_fault == 'package': owner.SetFPID(pcbnew.LIB_ID('fixture', 'wrong_package'))
    elif source_fault == 'power_pin': root.SetNumber('6')
    elif source_fault == 'filtered': root.SetNet(board.FindNet('INPUT_A'))
    elif source_fault == 'dnp': owner.SetDNP(True)
    elif source_fault == 'partial':
        stub=pcbnew.PCB_TRACK(board);stub.SetStart(root.GetPosition())
        stub.SetEnd(root.GetPosition()+pcbnew.VECTOR2I_MM(1,0));stub.SetWidth(200000)
        stub.SetLayer(pcbnew.F_Cu);stub.SetNet(root.GetNet());board.Add(stub)
    domains = {n.GetNetname(): dict(complete=True, authority_refs=['RENAMED_SHUNT'])
               for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **kw: copy.deepcopy(domains))
    source = tmp_path/'source'/'board.kicad_pcb'
    source.parent.mkdir()
    field._save_field_snapshot(board, source)
    uid, target_uid = force._uid(root), force._uid(target)
    parent = pcbnew.LoadBoard(str(source))
    private = pcbnew.LoadBoard(str(source))
    fp = _pads(private)[uid].GetParentFootprint()
    fp.Move(pcbnew.VECTOR2I_MM(0, -2))
    pose = [fp.GetPosition().x/1e6, fp.GetPosition().y/1e6, fp.GetOrientationDegrees()]
    proposal = dict(source_native_binding=row._source_binding(parent), board_hint='RENAMED_SOURCE',
                    poses={fp.GetReference(): pose})
    a, z = [tuple(_pads(private)[u].GetPosition()) for u in (uid, target_uid)]
    pickup=_pads(private)[target_uid]
    peer=next(p for p in pickup.GetParentFootprint().Pads() if force._uid(p)!=target_uid)
    direction=[z[i]-peer.GetPosition()[i] for i in (0,1)]
    inner=[z[i]-(int(math.copysign(1000000,direction[i])) if direction[i] else 0) for i in (0,1)]
    # Rotate the two-step lead with the whole native fixture. The moved
    # owner's displacement is two mm upwards in board coordinates.
    if a[0] == inner[0] or a[1] == inner[1]: points = [list(a), inner]
    else:
        distance = min(abs(inner[0]-a[0]), abs(inner[1]-a[1]))
        if abs(inner[0]-a[0]) >= abs(inner[1]-a[1]):
            knee = [inner[0] - int(math.copysign(distance, inner[0]-a[0])), a[1]]
        else: knee = [a[0], inner[1] - int(math.copysign(distance, inner[1]-a[1]))]
        points = [list(a), knee, inner]
    points.append(list(z))
    points=[p for i,p in enumerate(points) if i==0 or p!=points[i-1]]
    request = [dict(pad_uuid=uid, points_nm=points)]
    return source, parent, private, proposal, request, uid, target_uid


def compile_case(args):
    _source, parent, private, proposal, request, _uid, _target = args
    return corridor.plan(parent, private, proposal, request, timeout_s=10.)


def add_path(board, proof, fault=None):
    points = copy.deepcopy(proof['points_nm'])
    if fault == 'omitted': return set()
    if fault == 'unused': points = [[40000000, 20000000], [41000000, 20000000]]
    if fault == 'diverted':
        a, z = points[0], points[-1]
        points = [a, [a[0], 6000000], [z[0], 6000000], z]
    if fault == 'subdivided':
        a, z = points[:2]
        points.insert(1, [(a[0]+z[0])//2, (a[1]+z[1])//2])
    incoming = set()
    for a, z in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        if fault == 'reverse': a, z = z, a
        track.SetStart(pcbnew.VECTOR2I(*a)); track.SetEnd(pcbnew.VECTOR2I(*z))
        track.SetWidth(proof['width_nm'] if fault != 'wrong_width' else proof['width_nm']+50000)
        track.SetLayer(pcbnew.F_Cu if fault != 'back' else pcbnew.B_Cu)
        track.SetNetCode(board.GetNetcodeFromNetname(proof['net'] if fault != 'wrong_net' else 'FORCE_B'))
        board.Add(track); incoming.add(force._uid(track))
    if fault == 'extraneous':
        track = pcbnew.PCB_TRACK(board); track.SetStart(pcbnew.VECTOR2I_MM(40,20))
        track.SetEnd(pcbnew.VECTOR2I_MM(41,20)); track.SetWidth(proof['width_nm'])
        track.SetLayer(pcbnew.F_Cu); track.SetNetCode(board.GetNetcodeFromNetname(proof['net']))
        board.Add(track); incoming.add(force._uid(track))
    if fault == 'via':
        via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I(*points[0]))
        via.SetWidth(600000); via.SetDrill(300000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(board.GetNetcodeFromNetname(proof['net'])); board.Add(via)
        incoming.add(force._uid(via))
    return incoming


@pytest.mark.parametrize('value', [None, True, 1, {}, 'corridor'])
def test_requests_requires_explicit_bounded_sequence(value):
    with pytest.raises(ValueError): corridor.requests(value)


@pytest.mark.parametrize('fault', ['extra_key','missing_key','empty_uid','boolean_uid','duplicate_uid',
    'boolean_coordinate','float_coordinate','huge_coordinate','short_point','one_point','too_many_points',
    'zero_leg','noncanonical','overlong','crossing','closed_loop','closed_loop_mixed','too_many_requests'])
def test_geometry_requests_cannot_smuggle_ambiguity_or_unbounded_paths(fault):
    value = dict(pad_uuid='source-pad', points_nm=[[0,0],[1000000,0]])
    values = [value]
    if fault == 'extra_key': value['width_nm'] = 100000
    elif fault == 'missing_key': del value['pad_uuid']
    elif fault == 'empty_uid': value['pad_uuid'] = ''
    elif fault == 'boolean_uid': value['pad_uuid'] = True
    elif fault == 'duplicate_uid': values.append(copy.deepcopy(value))
    elif fault == 'boolean_coordinate': value['points_nm'][0][0] = False
    elif fault == 'float_coordinate': value['points_nm'][0][0] = 0.0
    elif fault == 'huge_coordinate': value['points_nm'][0][0] = 1000000001
    elif fault == 'short_point': value['points_nm'][0] = [0]
    elif fault == 'one_point': value['points_nm'] = [[0,0]]
    elif fault == 'too_many_points': value['points_nm'] = [[i*1000,0] for i in range(18)]
    elif fault == 'zero_leg': value['points_nm'] = [[0,0],[0,0]]
    elif fault == 'noncanonical': value['points_nm'] = [[0,0],[1000000,200000]]
    elif fault == 'overlong': value['points_nm'] = [[0,0],[24000001,0]]
    elif fault == 'crossing': value['points_nm'] = [[0,0],[2000000,2000000],[0,2000000],[2000000,0]]
    elif fault == 'closed_loop': value['points_nm'] = [[0,0],[1000000,0],[1000000,1000000],[0,1000000],[0,0]]
    elif fault == 'closed_loop_mixed': value['points_nm'] = [(0,0),[1000000,0],[1000000,1000000],[0,1000000],[0,0]]
    else: values = [dict(pad_uuid=str(i),points_nm=[[0,0],[1000,0]]) for i in range(5)]
    with pytest.raises(ValueError): corridor.requests(values)


def test_requests_normalizes_without_mutation_and_accepts_exact_length_bound():
    original = (dict(pad_uuid='geometry-only', points_nm=((0,0),(24000000,0))),)
    before = copy.deepcopy(original)
    assert corridor.requests(original) == [dict(pad_uuid='geometry-only', points_nm=[[0,0],[24000000,0]])]
    assert original == before and corridor.requests([]) == []


def test_empty_opt_in_is_noop_and_maximum_native_stroke_count_is_explicit():
    assert corridor.plan(None,None,{},[]) == ([],[])
    assert corridor.receive(None,[],set()) == []
    points=[[i*1000000,0] for i in range(17)]
    assert corridor.requests([dict(pad_uuid='geometry-only',points_nm=points)])[0]['points_nm']==points


@pytest.mark.parametrize('timeout', [True,False,0,-1,10.01,float('inf'),float('nan')])
def test_all_public_leases_are_strict_and_bounded(timeout):
    with pytest.raises(ValueError): corridor.plan(None,None,{},[],timeout_s=timeout)
    with pytest.raises(ValueError): corridor.receive(None,[],set(),timeout_s=timeout)
    with pytest.raises(ValueError): corridor.entry_ops(None,{},timeout_s=timeout)
    with pytest.raises(ValueError): corridor.rederive(None,{},timeout_s=timeout)


@pytest.mark.parametrize('quarter', range(4))
def test_native_renamed_source_plan_owns_actual_moved_input_and_stationary_shunt(tmp_path,monkeypatch,quarter):
    args = case(tmp_path,monkeypatch,quarter); source,parent,private,proposal,request,uid,target = args
    before = source.read_bytes(), row._source_binding(parent), row._source_binding(private)
    proofs, columns = compile_case(args)
    assert len(proofs) == 1 and len(columns) == len(request[0]['points_nm'])-1
    proof = proofs[0]
    assert proof['pad_uuid'] == uid and proof['target_pad_uuid'] == target
    assert proof['mandatory_exact_saved_path'] and proof['width_nm'] == 200000
    assert not proof['cuts_current_or_layer_or_Kelvin_or_release_authorized']
    assert all(t.GetLayer() == pcbnew.F_Cu and t.GetWidth() == 200000 for t in columns)
    assert before == (source.read_bytes(), row._source_binding(parent), row._source_binding(private))


@pytest.mark.parametrize('fault',['manufacturer','package','power_pin','filtered','dnp','partial'])
def test_source_role_manufacturer_and_direct_shunt_policy_must_be_positive(tmp_path,monkeypatch,fault):
    args = case(tmp_path,monkeypatch,source_fault=fault)
    with pytest.raises(ValueError): compile_case(args)


@pytest.mark.parametrize('fault',['unknown_pad','unmoved','missing_pose','wrong_declared_pose','pad_only_move',
    'shunt_move','input_net','input_number','input_size','input_shape','input_side','private_dnp',
    'private_manufacturer','private_package','stale_binding',
    'wrong_start','wrong_target','reversed_request'])
def test_source_land_and_exact_posed_input_cannot_be_forged(tmp_path,monkeypatch,fault):
    args = case(tmp_path,monkeypatch); source,parent,private,proposal,request,uid,target = args
    root, anchor = [_pads(private)[u] for u in (uid,target)]
    if fault == 'unknown_pad': request[0]['pad_uuid'] = 'not-a-source-pad'
    elif fault == 'unmoved':
        root.GetParentFootprint().Move(pcbnew.VECTOR2I_MM(0,2)); request[0]['points_nm'][0]=list(root.GetPosition())
    elif fault == 'missing_pose': proposal['poses'] = {}
    elif fault == 'wrong_declared_pose': proposal['poses'][root.GetParentFootprint().GetReference()][0] += 1
    elif fault == 'pad_only_move':
        root.Move(pcbnew.VECTOR2I_MM(1,0)); request[0]['points_nm'] = [list(root.GetPosition()),[18000000,8000000],[20000000,10000000]]
    elif fault == 'shunt_move': anchor.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault == 'input_net': root.SetNet(private.FindNet('FORCE_B'))
    elif fault == 'input_number': root.SetNumber('forged')
    elif fault == 'input_size': root.SetSize(pcbnew.VECTOR2I_MM(.9,.8))
    elif fault == 'input_shape': root.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault == 'input_side':
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);root.SetLayerSet(mask)
    elif fault == 'private_dnp': root.GetParentFootprint().SetDNP(True)
    elif fault == 'private_manufacturer': root.GetParentFootprint().SetValue('UNKNOWN_INPUT_DEVICE')
    elif fault == 'private_package': root.GetParentFootprint().SetFPID(pcbnew.LIB_ID('fixture','wrong_package'))
    elif fault == 'stale_binding': proposal['source_native_binding'] = 'forged'
    elif fault == 'wrong_start': request[0]['points_nm'][0][0] -= 1000000
    elif fault == 'wrong_target': request[0]['points_nm'] = [list(root.GetPosition()),[21000000,8000000],[23000000,10000000]]
    else: request[0]['points_nm'].reverse()
    with pytest.raises(ValueError): compile_case(args)


@pytest.mark.parametrize('fault',[None,'reverse','subdivided'])
def test_saved_native_corridor_accepts_only_same_geometry_and_collinear_subdivision(tmp_path,monkeypatch,fault):
    args = case(tmp_path,monkeypatch); proofs,_ = compile_case(args)
    private=args[2]; incoming=add_path(private,proofs[0],fault)
    saved=tmp_path/'saved.kicad_pcb'; field._save_field_snapshot(private,saved)
    reloaded=pcbnew.LoadBoard(str(saved))
    result=corridor.receive(reloaded,proofs,incoming,timeout_s=10.)
    assert len(result)==1 and result[0]['exact_required_corridor_constructed']
    assert result[0]['new_track_uuids']==sorted(incoming)
    assert not result[0]['current_or_Kelvin_qualified'] and not result[0]['release_authority']


@pytest.mark.parametrize('fault',['omitted','unused','diverted','wrong_width','via','extraneous','back','wrong_net'])
def test_required_corridor_cannot_be_unused_diverted_or_gain_unowned_material(tmp_path,monkeypatch,fault):
    args=case(tmp_path,monkeypatch); proofs,_=compile_case(args)
    private=args[2]; incoming=add_path(private,proofs[0],fault)
    if fault=='wrong_net':
        # KiCad normalizes a physically pad-connected wrong-net chain to
        # that pad's net on file reload. Test this board-only contract on
        # its actual malformed native input; the enclosing saved macro
        # must additionally check authored/literal net annotations.
        assert {t.GetNetname() for t in private.GetTracks() if force._uid(t) in incoming}=={'FORCE_B'}
        with pytest.raises(ValueError): corridor.receive(private,proofs,incoming,timeout_s=10.)
        return
    # Preserve malformed authored material for independent saved inspection;
    # the safer inventory-normalizing helper can reject wrong-net shorts
    # before this mandatory-path receiver gets to examine its own contract.
    saved=tmp_path/'saved-negative.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(saved),private)
    reloaded=pcbnew.LoadBoard(str(saved))
    with pytest.raises(ValueError): corridor.receive(reloaded,proofs,incoming,timeout_s=10.)


@pytest.mark.parametrize('field_name',['width_nm','net','target_pose','source_sha256','actual_land_sha256','code_identity'])
def test_saved_proof_is_rederived_not_worker_declared(tmp_path,monkeypatch,field_name):
    args=case(tmp_path,monkeypatch); proofs,_=compile_case(args); private=args[2]
    incoming=add_path(private,proofs[0]); proofs=copy.deepcopy(proofs)
    proofs[0][field_name] = 250000 if field_name=='width_nm' else [1,2,0] if field_name=='target_pose' else 'forged'
    with pytest.raises((ValueError,KeyError)): corridor.receive(private,proofs,incoming,timeout_s=10.)


def test_foreign_full_power_wall_does_not_become_retirement_permission(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch); proofs,_=compile_case(args); private=args[2]
    wall=pcbnew.PCB_TRACK(private);wall.SetNetCode(private.GetNetcodeFromNetname('POWER'))
    wall.SetWidth(1000000);wall.SetLayer(pcbnew.F_Cu)
    wall.SetStart(pcbnew.VECTOR2I_MM(15,6));wall.SetEnd(pcbnew.VECTOR2I_MM(15,10));private.Add(wall)
    before=row._source_binding(private)
    ops,detail=corridor.entry_ops(private,proofs[0],timeout_s=10.)
    assert not ops and not detail['found'] and not all(detail['actual_native_clearance_and_edge'])
    assert before==row._source_binding(private) and force._uid(wall) in {force._uid(t) for t in private.GetTracks()}


def test_native_entry_menu_rederives_land_and_checks_actual_contact_field_and_craft(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch); proofs,_=compile_case(args); private=args[2]
    before=row._source_binding(private)
    ops,detail=corridor.entry_ops(private,proofs[0],timeout_s=10.)
    assert ops and detail['found'],detail
    assert all(detail['actual_native_clearance_and_edge'])
    assert detail['actual_source_pickup_and_force_contacts'] is True
    assert detail['field']['ok'] and detail['field']['complete']
    assert detail['craft']['ok'] and detail['craft']['complete']
    assert before==row._source_binding(private)


def test_unknown_current_source_domain_cannot_create_corridor_authority(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch)
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{})
    with pytest.raises(ValueError): compile_case(args)


def test_source_board_is_compared_to_actual_saved_native_source(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch)
    _pads(args[1])[args[5]].Move(pcbnew.VECTOR2I_MM(.1,0))
    args[3]['source_native_binding']=row._source_binding(args[1])
    with pytest.raises(ValueError): compile_case(args)


def saved_case(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch);proofs,_=compile_case(args)
    private=args[2];incoming=add_path(private,proofs[0])
    saved=tmp_path/'actual-candidate.kicad_pcb'
    field._save_field_snapshot(private,saved)
    return saved,pcbnew.LoadBoard(str(saved)),proofs,incoming


def change_incoming_net_literal(saved,incoming,net):
    text=saved.read_text();inventory=literal._inventory(text)[0]
    uid=sorted(incoming)[0];start,end,node=inventory[uid]
    a,z=literal._child(node,'net')
    # This is deliberately malformed test evidence, not a manufacturing
    # writer. Preserve all other Source/native node bytes exactly.
    import json
    changed=node[:a]+'(net '+json.dumps(net)+')'+node[z:]
    saved.write_text(text[:start]+changed+text[end:])


def test_explicit_saved_path_accepts_correct_authored_native_chain(tmp_path,monkeypatch):
    saved,board,proofs,incoming=saved_case(tmp_path,monkeypatch)
    before=saved.read_bytes()
    assert literal.incoming_copper_nets(saved.read_text(),incoming)=={
        uid:proofs[0]['net'] for uid in incoming}
    report=corridor.receive(board,proofs,incoming,saved_path=saved,timeout_s=10.)
    assert len(report)==1 and report[0]['exact_required_corridor_constructed']
    assert saved.read_bytes()==before


def test_explicit_saved_path_refuses_authored_wrong_net_despite_correct_native_chain(tmp_path,monkeypatch):
    saved,board,proofs,incoming=saved_case(tmp_path,monkeypatch)
    change_incoming_net_literal(saved,incoming,'FORCE_B')
    assert 'FORCE_B' in literal.incoming_copper_nets(saved.read_text(),incoming).values()
    # Exercise the real loader normalization, not a forged native result.
    # Its positive chain must not launder contradictory file annotations.
    board=pcbnew.LoadBoard(str(saved))
    assert {t.GetNetname() for t in board.GetTracks() if force._uid(t) in incoming}=={proofs[0]['net']}
    with pytest.raises(ValueError,match='literal_net_mismatch'):
        corridor.receive(board,proofs,incoming,saved_path=saved,timeout_s=10.)


def test_explicit_saved_path_refuses_raw_missing_required_uuid(tmp_path,monkeypatch):
    saved,board,proofs,incoming=saved_case(tmp_path,monkeypatch)
    text=saved.read_text();inventory=literal._inventory(text)[0]
    a,z,_=inventory[sorted(incoming)[0]];saved.write_text(text[:a]+text[z:])
    assert incoming-{force._uid(t) for t in board.GetTracks()}==set()
    with pytest.raises(ValueError):
        corridor.receive(board,proofs,incoming,saved_path=saved,timeout_s=10.)


@pytest.mark.parametrize('fault',['copied_other_path','missing_path'])
def test_explicit_saved_path_is_actual_candidate_not_a_worker_selected_alternate(tmp_path,monkeypatch,fault):
    saved,board,proofs,incoming=saved_case(tmp_path,monkeypatch)
    other=tmp_path/'other-family'/'board.kicad_pcb'
    if fault=='copied_other_path':
        other.parent.mkdir();other.write_bytes(saved.read_bytes())
    with pytest.raises((ValueError,OSError)):
        corridor.receive(board,proofs,incoming,saved_path=other,timeout_s=10.)


def test_explicit_no_proof_default_does_not_acquire_saved_file_obligations(tmp_path):
    assert corridor.receive(None,[],set())==[]
    assert corridor.receive(None,[],set(),saved_path=None)==[]
    assert corridor.receive(None,[],set(),saved_path=tmp_path/'not-present.kicad_pcb')==[]
