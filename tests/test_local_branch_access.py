"""A typed source leaf is reconstructed, not a force-net name permission."""
import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_local_branch_access as access
import cec_measurement_leaf as leaf
from cec_native_items import discard_items


def test_single_causal_ports_are_funded_before_joint_reservations():
    def task(owner, role, uid, ground=False):
        row = dict(owner=owner, role=role, pad_uuid=uid, cap='owned_bypass',
            cap_pad='2', destination_uuid=uid+'-cap', b_nm=[1, 2])
        row['verified_ground_alternatives'] = [dict(uuid=uid+'-ground',
            ref=owner, pin='2', at_nm=[3, 4])] if ground else []
        return row
    tasks = [task('arbitrary_a', 'supply', 's'),
        task('arbitrary_a', 'ground_reference', 'g', True),
        task('arbitrary_b', 'supply', 'other')]
    leases = access._task_leases(tasks)
    sizes = [len(cohort) for _, cohort, _ in leases]
    assert sizes == sorted(sizes)
    assert leases[0][1][0]['role'] == 'ground_reference'
    assert leases[0][2]['g']['uuid'] == 'g-ground'
    assert leases[1][2]['g']['uuid'] == 'g-cap'
    assert any(len(cohort) == 2 for _, cohort, _ in leases)
    keys = [tuple(sorted((u, d['uuid']) for u, d in destinations.items()))
        for _, _, destinations in leases]
    assert len(keys) == len(set(keys))
    assert access._task_leases(list(reversed(tasks))) == leases


def fixture(tmp_path):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    for a, b in [((0, 0), (30, 0)), ((30, 0), (30, 30)),
                 ((30, 30), (0, 30)), ((0, 30), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b)); board.Add(edge)
    nets = {}
    for name in ('GND', '+3V3', 'MEASURE_PLUS', 'MEASURE_MINUS'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    def part(ref, value, pins, footprint=''):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        if footprint:fp.SetFPID(pcbnew.LIB_ID(*footprint.split(':')))
        board.Add(fp)
        for pin, net, x, y in pins:
            p = pcbnew.PAD(fp); p.SetNumber(pin); p.SetNet(nets[net])
            p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I_MM(.45, .45))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetPosition(pcbnew.VECTOR2I_MM(x, y)); fp.Add(p)
        bounds = [min(p[2] for p in pins)-.4, min(p[3] for p in pins)-.4,
                  max(p[2] for p in pins)+.4, max(p[3] for p in pins)+.4]
        x0, y0, x1, y1 = bounds
        for a, b in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
            line = pcbnew.PCB_SHAPE(fp); line.SetLayer(pcbnew.F_CrtYd)
            line.SetShape(pcbnew.SHAPE_T_SEGMENT); line.SetWidth(50000)
            line.SetStart(pcbnew.VECTOR2I_MM(*a)); line.SetEnd(pcbnew.VECTOR2I_MM(*b)); fp.Add(line)
        return fp
    owner = part('U_RENAMED', 'INA181A2IDBVR', [
        ('6','+3V3',14,13), ('5','GND',15,13), ('4','MEASURE_MINUS',16,13),
        ('2','GND',15,15), ('3','MEASURE_PLUS',16,15)], 'Package_TO_SOT_SMD:SOT-23-6')
    part('C_RENAMED', '100nF', [('1','+3V3',14,10),('2','GND',15,10)])
    part('FIXED', 'test', [('1','MEASURE_MINUS',10,13)])
    part('OTHER', 'test', [('1','MEASURE_PLUS',24,17)])
    def tracks(net, points):
        for a, b in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board); track.SetNet(nets[net]); track.SetLayer(pcbnew.F_Cu)
            track.SetWidth(200000); track.SetStart(pcbnew.VECTOR2I_MM(*a)); track.SetEnd(pcbnew.VECTOR2I_MM(*b))
            board.Add(track)
    tracks('MEASURE_MINUS', [(16,13),(16,12),(10,12),(10,13)])
    tracks('MEASURE_PLUS', [(16,15),(16,17),(24,17)])
    tracks('GND', [(15,10),(20,10),(20,16),(15,16),(15,15)])
    source = tmp_path/'source.kicad_pcb'; field._save_field_snapshot(board, source)
    candidate = force._copy_family(source, tmp_path/'candidate')
    child = pcbnew.LoadBoard(str(candidate))
    pad = child.FindFootprintByReference(owner.GetReference()).FindPadByNumber('4')
    proposal = leaf.plan(child, force._uid(pad))
    discard_items(child, [t for t in child.GetTracks() if force._uid(t) in proposal['track_uuids']])
    points = [[round(v*1e6) for v in p] for p in [(16,13),(16,14),(13,14),(13,9),(10,9),(10,13)]]
    diagnostic = {}
    assert leaf.path_clear(child, proposal, points, diagnostics=diagnostic), diagnostic
    leaf.add_path(child, proposal, points)
    owner = child.FindFootprintByReference('U_RENAMED')
    cap = child.FindFootprintByReference('C_RENAMED')
    for a, b in [(owner.FindPadByNumber('6'),cap.FindPadByNumber('1')),
                 (owner.FindPadByNumber('5'),cap.FindPadByNumber('2'))]:
        track = pcbnew.PCB_TRACK(child); track.SetNetCode(a.GetNetCode()); track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(200000); track.SetStart(a.GetPosition()); track.SetEnd(b.GetPosition()); child.Add(track)
    field._save_field_snapshot(child, candidate)
    return source, candidate, proposal['pad_uuid']


def test_independent_receiver_replays_exact_retirement_and_local_saved_gain(tmp_path):
    source, candidate, pad_uuid = fixture(tmp_path)
    proof = access.receive(source, candidate, board_hint='fixture', pad_uuid=pad_uuid)
    assert proof['ok'] and proof['complete'], proof['errors']
    assert proof['opens'] < proof['source_opens']
    assert proof['independent_exact_retirement_additive_replay']['ok']
    assert proof['exact_force_copper_barrels_and_component_poses_preserved']
    assert not proof['release_authority'] and not proof['kelvin_qualified']


def test_automatic_constructor_uses_source_roles_not_the_test_pose_recipe(tmp_path):
    source, _, _ = fixture(tmp_path)
    original = source.read_bytes()
    result = access.run(source, tmp_path/'automatic', board_hint='fixture',
        source_sha256=force._hash(source), timeout_s=10., max_trials=8)
    assert result['ok'], result
    assert result['opens'] < result['source_opens']
    assert result['source_family_and_code_unchanged']
    assert source.read_bytes() == original
    assert result['read_only_retired_snapshot_loads'] < result['guarded_paths']
    assert result['constructed_snapshot_loads'] == len(result['trials'])


def test_mutating_geometry_query_cannot_poison_reused_source_snapshot(tmp_path, monkeypatch):
    source, _, _ = fixture(tmp_path)
    original = source.read_bytes(); actual = leaf.path_clear
    def mutate(board, proposal, points, **kwargs):
        clear = actual(board, proposal, points, **kwargs)
        track = pcbnew.PCB_TRACK(board); track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(2,2)); track.SetEnd(pcbnew.VECTOR2I_MM(3,2))
        track.SetWidth(200000); track.SetNetCode(board.GetNetcodeFromNetname('+3V3'))
        board.Add(track)
        return clear
    monkeypatch.setattr(leaf, 'path_clear', mutate)
    result = access.run(source, tmp_path/'mutating-query', board_hint='fixture',
        source_sha256=force._hash(source))
    assert not result['ok'] and not result['trials']
    assert any(r['reason'] == 'read_only_local_branch_snapshot_mutated'
        for r in result['refusals'])
    assert source.read_bytes() == original and result['source_family_and_code_unchanged']


def test_source_verified_owner_ground_is_a_valid_local_return_not_a_forced_bypass_detour(tmp_path):
    source,_,_=fixture(tmp_path);parent=pcbnew.LoadBoard(str(source))
    discard_items(parent,[t for t in parent.GetTracks() if t.GetNetname() in ('GND','MEASURE_MINUS')])
    def route(board,net,points,layer=pcbnew.F_Cu):
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(board);t.SetNetCode(board.GetNetcodeFromNetname(net));t.SetLayer(layer)
            t.SetWidth(200000);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t)
    route(parent,'GND',[(15,10),(15,9),(16,9)])
    route(parent,'GND',[(15,15),(13,15)])
    for at in [(16,9),(13,15)]:
        v=pcbnew.PCB_VIA(parent);v.SetNet(parent.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(*at))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(v)
    route(parent,'GND',[(16,9),(13,9),(13,15)],pcbnew.B_Cu)
    route(parent,'MEASURE_MINUS',[(16,13),(17,13),(17,8),(10,8),(10,13)])
    field._save_field_snapshot(parent,source)
    candidate=force._copy_family(source,tmp_path/'owner-ground');child=pcbnew.LoadBoard(str(candidate))
    owner=child.FindFootprintByReference('U_RENAMED');pad_uuid=force._uid(owner.FindPadByNumber('4'))
    proposal=leaf.plan(child,pad_uuid)
    discard_items(child,[t for t in child.GetTracks() if force._uid(t) in proposal['track_uuids']])
    leaf.add_path(child,proposal,proposal['points_nm'])
    route(child,'GND',[(15,13),(15,15)])
    route(child,'+3V3',[(14,13),(14,10)])
    field._save_field_snapshot(child,candidate)
    proof=access.receive(source,candidate,board_hint='fixture',pad_uuid=pad_uuid)
    assert proof['ok'],proof['errors']
    returns=[r for r in proof['gained_source_isolated_terminals'] if r['role']=='ground_reference']
    assert returns and returns[0]['destination']['role']=='manufacturer_ground'
    assert not proof['release_authority'] and proof['exact_force_copper_barrels_and_component_poses_preserved']


@pytest.mark.parametrize('fault', ['owner_pose', 'cap_pose', 'boundary', 'width', 'extra_foreign', 'no_gain'])
def test_unowned_edits_or_missing_local_gain_refuse(tmp_path, fault):
    source, candidate, pad_uuid = fixture(tmp_path)
    child = pcbnew.LoadBoard(str(candidate))
    if fault in ('owner_pose', 'cap_pose'):
        child.FindFootprintByReference('U_RENAMED' if fault == 'owner_pose' else 'C_RENAMED').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault == 'boundary':
        child.FindFootprintByReference('FIXED').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault == 'width':
        next(t for t in child.GetTracks() if t.GetNetname() == 'MEASURE_MINUS').SetWidth(250000)
    elif fault == 'extra_foreign':
        track = pcbnew.PCB_TRACK(child); track.SetNetCode(child.GetNetcodeFromNetname('MEASURE_PLUS'))
        track.SetLayer(pcbnew.F_Cu); track.SetWidth(200000)
        track.SetStart(pcbnew.VECTOR2I_MM(2,2)); track.SetEnd(pcbnew.VECTOR2I_MM(3,2)); child.Add(track)
    elif fault == 'no_gain':
        discard_items(child, [t for t in child.GetTracks() if t.GetNetname() == '+3V3'
            or (t.GetNetname() == 'GND' and t.GetStart() == pcbnew.VECTOR2I_MM(15,13))])
    field._save_field_snapshot(child, candidate)
    proof = access.receive(source, candidate, board_hint='fixture', pad_uuid=pad_uuid)
    assert not proof['ok'] and not proof['release_authority']


def cohort_fixture(tmp_path,quarter=0,name='RENAMED_COHORT'):
    source,_,minus=fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source))
    discard_items(parent,[t for t in parent.GetTracks() if t.GetNetname()=='GND'])
    def route(board,points,layer):
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(board);t.SetNetCode(board.GetNetcodeFromNetname('GND'))
            t.SetLayer(layer);t.SetWidth(200000)
            t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t)
    route(parent,[(15,10),(15,9)],pcbnew.F_Cu)
    route(parent,[(15,15),(15,16)],pcbnew.F_Cu)
    for at in [(15,9),(15,16)]:
        v=pcbnew.PCB_VIA(parent);v.SetNet(parent.FindNet('GND'))
        v.SetPosition(pcbnew.VECTOR2I_MM(*at));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);parent.Add(v)
    route(parent,[(15,9),(19,9),(19,16),(15,16)],pcbnew.B_Cu)
    field._save_field_snapshot(parent,source)
    candidate=force._copy_family(source,tmp_path/'cohort');child=pcbnew.LoadBoard(str(candidate))
    pads=[force._uid(child.FindFootprintByReference('U_RENAMED').FindPadByNumber(p)) for p in ('4','3')]
    proposals=[leaf.plan(child,u) for u in pads]
    discard_items(child,[t for t in child.GetTracks() if force._uid(t) in
        {u for q in proposals for u in q['track_uuids']}])
    for q,points in zip(proposals,[[(16,13),(16,14),(13,14),(13,9),(10,9),(10,13)],
                                 [(16,15),(16,17),(23,17),(24,17)]]):
        points=[[round(v*1e6) for v in p] for p in points]
        assert leaf.path_clear(child,q,points)
        leaf.add_path(child,q,points)
    for net,points in [('GND',[(15,13),(15,10)]),('+3V3',[(14,13),(14,10)])]:
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(child);t.SetNetCode(child.GetNetcodeFromNetname(net))
            t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
            t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));child.Add(t)
    for board,path in [(parent,source),(child,candidate)]:
        board.FindFootprintByReference('U_RENAMED').SetReference(name)
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,angle)
        field._save_field_snapshot(board,path)
    return source,candidate,pads


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['RENAMED_COHORT','UNRELATED_OWNER'])
def test_same_owner_cohort_restores_both_actual_leaves_and_local_gain(tmp_path,quarter,name):
    source,candidate,pads=cohort_fixture(tmp_path,quarter,name)
    proof=access.receive(source,candidate,board_hint='fixture',pad_uuids=pads)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert len(proof['source_leaves'])==len(proof['new_leaves'])==2
    assert proof['opens']<proof['source_opens']
    assert len(proof['retired_track_uuids'])==5
    assert proof['exact_force_copper_barrels_and_component_poses_preserved']
    assert not proof['release_authority'] and not proof['current_authority']


@pytest.mark.parametrize('fault',['duplicate','both_modes','empty','five','foreign_owner',
                                  'changed_boundary','missing_member','mutual_contact','no_gain'])
def test_cohort_is_not_whole_net_or_reconstructed_member_waiver(tmp_path,fault):
    source,candidate,pads=cohort_fixture(tmp_path)
    child=pcbnew.LoadBoard(str(candidate));kwargs=dict(pad_uuids=pads)
    if fault=='duplicate':kwargs['pad_uuids']=[pads[0],pads[0]]
    elif fault=='both_modes':kwargs['pad_uuid']=pads[0]
    elif fault=='empty':kwargs['pad_uuids']=[]
    elif fault=='five':kwargs['pad_uuids']=pads*2+[pads[0]]
    elif fault=='foreign_owner':kwargs['pad_uuids']=[pads[0],force._uid(child.FindFootprintByReference('OTHER').FindPadByNumber('1'))]
    elif fault=='changed_boundary':child.FindFootprintByReference('OTHER').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='missing_member':discard_items(child,[next(t for t in child.GetTracks() if t.GetNetname()=='MEASURE_PLUS')])
    elif fault=='mutual_contact':
        plus=leaf.plan(child,pads[1]);discard_items(child,[t for t in child.GetTracks() if force._uid(t) in plus['track_uuids']])
        leaf.add_path(child,plus,[[round(v*1e6) for v in p] for p in
            [(16,15),(16,14),(23,14),(24,15),(24,17)]])
    elif fault=='no_gain':
        discard_items(child,[t for t in child.GetTracks() if t.GetNetname()=='+3V3'
            or (t.GetNetname()=='GND' and t.GetStart()==pcbnew.VECTOR2I_MM(15,13))])
    field._save_field_snapshot(child,candidate)
    proof=access.receive(source,candidate,board_hint='fixture',**kwargs)
    assert not proof['ok'] and not proof['release_authority'],proof
