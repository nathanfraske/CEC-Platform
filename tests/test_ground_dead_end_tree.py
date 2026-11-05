"""Native dead-end trees may not become permission to cut a mesh or return."""
import copy
import json
import math

import pcbnew
import pytest
import cec_ground_dead_end_tree as trees
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path, angle=0, mirror=1, short_tee=False):
    source, board = ground_fixture(tmp_path)
    def xy(p):
        a = math.radians(angle); x, y = p[0]*mirror, p[1]
        return (round(12+x*math.cos(a)-y*math.sin(a), 6),
                round(14+x*math.sin(a)+y*math.cos(a), 6))
    root = pcbnew.PCB_VIA(board); root.SetNetCode(board.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy((0, 0))))
    root.SetViaType(pcbnew.VIATYPE_THROUGH); root.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    root.SetWidth(pcbnew.FromMM(.6)); root.SetDrill(pcbnew.FromMM(.3)); board.Add(root)
    kept = track(board, 'GND', xy((0, 0)), xy((3, 0)))
    kept.SetWidth(pcbnew.FromMM(.3))
    stem = track(board, 'GND', xy((2, 0)), xy((2, 2)))
    left = track(board, 'GND', xy((2, 2)), xy((1, 3)))
    right = track(board, 'GND', xy((2.115 if short_tee else 2, 2)), xy((4, 4)))
    branch = [stem, left, right]
    if short_tee:
        branch.append(track(board, 'GND', xy((2, 2)), xy((2.115, 2))))
    additive._ground_refill(board); field._save_field_snapshot(board, source)
    return source, board, branch, kept, root, xy


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [1, -1])
@pytest.mark.parametrize('short_tee', [False, True])
def test_actual_native_tree_has_one_plane_connected_root_and_exact_saved_replay(tmp_path, angle, mirror, short_tee):
    source, board, branch, kept, root, _ = fixture(tmp_path, angle, mirror, short_tee)
    raw = source.read_bytes()
    packet = json.loads(json.dumps(trees.plan(board, force._uid(branch[1]))))
    assert set(packet['retired_track_uuids']) == {force._uid(t) for t in branch}
    assert packet['retained_plane_path_uuids'] == [force._uid(kept), force._uid(root)]
    trees.subtract(board, packet)
    candidate = force._copy_family(source, tmp_path/'candidate')
    additive._ground_refill(board); field._save_field_snapshot(board, candidate)
    proof = trees.receive(source, candidate, packet, board_hint='unclassified-test')
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_surviving_native_partitions_preserved']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes() == raw


@pytest.mark.parametrize('obstruction', ['pad', 'foreign_pad', 'locked', 'group',
    'second_root', 'cycle', 'interior', 'missing_root', 'unfilled', 'width', 'length'])
def test_native_contact_mesh_or_uncertainty_refuses_without_mutation(tmp_path, obstruction):
    _, board, branch, kept, root, xy = fixture(tmp_path)
    if obstruction in ('pad', 'foreign_pad'):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference('UNRELATED_OWNER'); board.Add(fp)
        pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber('1')
        pad.SetNetCode(board.GetNetcodeFromNetname('GND' if obstruction == 'pad' else '/CONTROL'))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy((4, 4)))); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mask = pcbnew.LSET(); mask.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(mask)
    elif obstruction == 'locked': branch[0].SetLocked(True)
    elif obstruction == 'group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(branch[0])
    elif obstruction == 'second_root':
        other = track(board, 'GND', xy((4, 4)), xy((5, 4))); other.SetWidth(pcbnew.FromMM(.3))
    elif obstruction == 'cycle': track(board, 'GND', xy((1, 3)), xy((4, 4)))
    elif obstruction == 'interior': track(board, 'GND', xy((1, 1)), xy((3, 1)))
    elif obstruction == 'missing_root': root.SetPosition(pcbnew.VECTOR2I_MM(29, 29))
    elif obstruction == 'unfilled':
        for zone in board.Zones():
            if str(zone.GetNetname()) == 'GND': zone.UnFill()
    elif obstruction == 'width':
        for t in branch: t.SetWidth(pcbnew.FromMM(.5))
    elif obstruction == 'length': branch[2].SetEnd(pcbnew.VECTOR2I_MM(*xy((30, 30))))
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError): trees.plan(board, force._uid(branch[1]))
    assert before == field._field_snapshot_inventory(board)


@pytest.mark.parametrize('change', ['stale', 'forged'])
def test_stale_or_forged_plan_cannot_subtract(tmp_path, change):
    _, board, branch, kept, _, _ = fixture(tmp_path)
    packet = trees.plan(board, force._uid(branch[1]))
    if change == 'stale': track(board, '/CONTROL', (21, 20), (22, 20))
    else:
        packet = copy.deepcopy(packet); packet['retired_track_uuids'].append(force._uid(kept))
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError, match='stale_or_forged'): trees.subtract(board, packet)
    assert before == field._field_snapshot_inventory(board)


def test_saved_receiving_refuses_unrelated_native_material_change(tmp_path):
    source, board, branch, kept, _, _ = fixture(tmp_path)
    packet = trees.plan(board, force._uid(branch[1])); trees.subtract(board, packet)
    kept.SetWidth(pcbnew.FromMM(.4))
    candidate = force._copy_family(source, tmp_path/'changed')
    additive._ground_refill(board); field._save_field_snapshot(board, candidate)
    assert not trees.receive(source, candidate, packet, board_hint='unclassified-test')['ok']


@pytest.mark.parametrize('kwargs', [dict(timeout_s=0), dict(timeout_s=11),
    dict(max_tracks=33), dict(max_tracks=True), dict(max_length_mm=float('inf')),dict(mixed_width=1)])
def test_unbounded_cleanup_refused(tmp_path, kwargs):
    _, board, branch, _, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError): trees.plan(board, force._uid(branch[1]), **kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[1,-1])
def test_finite_native_cap_junction_does_not_require_equal_centreline_endpoints(tmp_path,angle,mirror):
    source,b,branch,kept,root,xy=fixture(tmp_path,angle,mirror)
    branch[2].SetStart(pcbnew.VECTOR2I_MM(*xy((2.04,2))))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    p=json.loads(json.dumps(trees.plan(b,force._uid(branch[1]))))
    assert p['native_simple_sheet_endpoint_offset_witness']['inside_union_holes']==0
    assert set(p['retired_track_uuids'])=={force._uid(t) for t in branch}
    trees.subtract(b,p);child=force._copy_family(source,tmp_path/'offset-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=trees.receive(source,child,p,board_hint='unclassified-test')
    assert proof['ok'] and proof['complete'],proof


def test_inside_union_may_not_turn_a_real_copper_loop_into_a_tree(tmp_path):
    _,b,branch,_,_,xy=fixture(tmp_path)
    branch[2].SetStart(pcbnew.VECTOR2I_MM(*xy((2.04,2))))
    track(b,'GND',xy((1,3)),xy((4,4)))
    with pytest.raises(ValueError,match='hole_free_inside_sheet'):trees.plan(b,force._uid(branch[1]))


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[1,-1])
def test_adjacent_short_bends_share_one_real_annular_root_not_independent_false_boundaries(tmp_path,angle,mirror):
    source,b=ground_fixture(tmp_path)
    def xy(p):
        x,y=p;x*=mirror;r=math.radians(angle)
        return round(12+x*math.cos(r)-y*math.sin(r),6),round(14+x*math.sin(r)+y*math.cos(r),6)
    root=pcbnew.PCB_VIA(b);root.SetNetCode(b.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy((0,0))));root.SetWidth(600000);root.SetDrill(300000)
    root.SetViaType(pcbnew.VIATYPE_THROUGH);root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(root)
    points=[(0,0),(0,-.36),(.06,-.42),(1,-1.36),(2,-1.36)]
    edges=[track(b,'GND',xy(a),xy(c)) for a,c in zip(points,points[1:])]
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    p=json.loads(json.dumps(trees.plan(b,force._uid(edges[-1]))))
    assert p['coalesced_actual_retained_annular_contact']['actual_outer_land_minus_outside_drill']
    assert any(not row['endpoint_centres_nm'] for row in p['subsumed_retained_barrel_endpoint_contacts'])
    trees.subtract(b,p);child=force._copy_family(source,tmp_path/'annular-root-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=trees.receive(source,child,p,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result


def barrel_land_fixture(tmp_path,angle=0,back=False,stem_mm=.24):
    source,b=ground_fixture(tmp_path)
    def xy(x,y):
        a=math.radians(angle)
        return round(12+x*math.cos(a)-y*math.sin(a),6),round(14+x*math.sin(a)+y*math.cos(a),6)
    root=pcbnew.PCB_VIA(b);root.SetNetCode(b.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy(0,0)));root.SetWidth(600000);root.SetDrill(300000)
    root.SetViaType(pcbnew.VIATYPE_THROUGH);root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(root)
    edges=[track(b,'GND',xy(0,0),xy(0,stem_mm)),
        track(b,'GND',xy(0,stem_mm),xy(1,1+stem_mm)),
        track(b,'GND',xy(1,1+stem_mm),xy(2,1+stem_mm))]
    for edge in edges:edge.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,b,root,edges


@pytest.mark.parametrize('angle',[0,45,90,135,180,225,270,315])
@pytest.mark.parametrize('back',[False,True])
def test_subpad_stem_and_adjacent_endpoint_share_one_real_retained_barrel_land(tmp_path,angle,back):
    source,b,root,edges=barrel_land_fixture(tmp_path,angle,back)
    packet=trees.plan(b,force._uid(edges[-1]))
    assert len(packet['subsumed_retained_barrel_endpoint_contacts'])==1
    assert packet['retained_boundary_uuid']==force._uid(root)
    assert set(packet['retired_track_uuids'])=={force._uid(t) for t in edges}
    trees.subtract(b,packet);child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=trees.receive(source,child,packet,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved'] and not proof['current_qualified']


def test_outside_endpoint_without_positive_actual_annular_patch_is_not_subsumed(tmp_path):
    _,b,root,edges=barrel_land_fixture(tmp_path,stem_mm=.26)
    # Neither a centre outside the 50 um land inset nor an annulus too
    # narrow for that independent finite-contact disk proves this boundary.
    root.SetDrill(500000)
    with pytest.raises(ValueError,match='retained_boundary_is_interior'):trees.plan(b,force._uid(edges[-1]))


def test_outside_endpoint_requires_its_separate_finite_annular_material_proof(tmp_path):
    _,b,root,edges=barrel_land_fixture(tmp_path,stem_mm=.26)
    p=trees.plan(b,force._uid(edges[-1]))
    assert p['coalesced_actual_retained_annular_contact']['actual_outer_land_minus_outside_drill']
    assert any(not r['endpoint_centres_nm'] for r in p['subsumed_retained_barrel_endpoint_contacts'])
    assert not p['current_qualified'] and not p['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[1,-1])
def test_explicit_mixed_width_removes_whole_pad_free_unused_chain_without_new_native_tails(tmp_path,angle,mirror):
    source,b=ground_fixture(tmp_path)
    def xy(p):
        x,y=p;x*=mirror;r=math.radians(angle)
        return round(12+x*math.cos(r)-y*math.sin(r),6),round(14+x*math.sin(r)+y*math.cos(r),6)
    root=pcbnew.PCB_VIA(b);root.SetNetCode(b.GetNetcodeFromNetname('GND'))
    root.SetPosition(pcbnew.VECTOR2I_MM(*xy((0,0))));root.SetWidth(600000);root.SetDrill(300000)
    root.SetViaType(pcbnew.VIATYPE_THROUGH);root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(root)
    points=[(0,0),(2,0),(3,1),(3,2)]
    edges=[track(b,'GND',xy(a),xy(c),width=.3) for a,c in zip(points,points[1:])]
    seed=track(b,'GND',xy((3,2)),xy((3,2.3)));edges.append(seed)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    ordinary=trees.plan(b,force._uid(seed))
    assert ordinary['retired_track_uuids']==[force._uid(seed)] and not ordinary['mixed_width']
    p=json.loads(json.dumps(trees.plan(b,force._uid(seed),mixed_width=True,max_tracks=32)))
    assert set(p['retired_track_uuids'])=={force._uid(e) for e in edges}
    assert set(p['actual_source_widths_nm'].values())=={200000,300000}
    trees.subtract(b,p);child=force._copy_family(source,tmp_path/'whole-mixed-chain')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=trees.receive(source,child,p,board_hint='unclassified-test')
    assert proof['ok'] and proof['complete'],proof


def test_mixed_width_never_erases_a_real_smd_return_or_wide_ground_bus(tmp_path):
    _,b,branch,kept,root,xy=fixture(tmp_path)
    kept.SetWidth(400000)
    p=trees.plan(b,force._uid(branch[1]),mixed_width=True,max_tracks=32)
    assert force._uid(kept) not in p['retired_track_uuids']
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetNetCode(b.GetNetcodeFromNetname('GND'))
    mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(mask)
    pad.SetPosition(pcbnew.VECTOR2I_MM(*xy((4,4))));pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    with pytest.raises(ValueError):trees.plan(b,force._uid(branch[1]),mixed_width=True,max_tracks=32)


@pytest.mark.parametrize('format',['legacy','native_sheet'])
def test_exact_historical_packet_replays_with_fresh_native_proofs_not_weakened_unknown_fields(tmp_path,format):
    source,b,branch,kept,root,_=fixture(tmp_path)
    p=trees.plan(b,force._uid(branch[1]))
    extra={'mixed_width','actual_source_widths_nm'}
    if format=='legacy':extra|={'native_simple_sheet_endpoint_offset_witness','coalesced_actual_retained_annular_contact'}
    p={k:v for k,v in p.items() if k not in extra}
    trees.subtract(b,p);child=force._copy_family(source,tmp_path/'historic-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    result=trees.receive(source,child,p,board_hint='unclassified-test')
    assert result['ok'] and result['complete'],result


def test_arbitrary_missing_scope_fields_are_not_a_historical_format(tmp_path):
    _,b,branch,_,_,_=fixture(tmp_path);p=trees.plan(b,force._uid(branch[1]))
    p.pop('actual_source_widths_nm')
    with pytest.raises(ValueError,match='stale_or_forged'):trees.subtract(b,p)
