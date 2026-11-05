"""Ambiguous branch ownership may retain copper, never grant mutation rights."""
import pcbnew
import pytest
import cec_pad_incident_tracks as contacts
import cec_certificate_repair as repair
import cec_local_copper_cell as copper
from test_pad_incident_tracks import setup


@pytest.mark.parametrize('kind', ['contained', 'shared', 'overlapping'])
@pytest.mark.parametrize('protection', ['plain', 'locked', 'grouped', 'generated_locked'])
@pytest.mark.parametrize('back,offset', [(False, (0,0)), (True, (17,-8))])
def test_native_fixed_boundary_never_moves_or_removes_source_copper(tmp_path, kind, protection, back, offset):
    board, owner, pad, route = setup(back=back, offset=offset)
    owner.SetReference('RENAMED_OWNER')
    peer = board.FindFootprintByReference('PEER'); peer.SetReference('RENAMED_PEER')
    other = next(p for p in peer.Pads() if p.GetNumber() == '1')
    next(p for p in peer.Pads() if p.GetNumber() == '2').SetNet(
        next(p for p in owner.Pads() if p.GetNumber() == '2').GetNet())
    companion_refs = []
    if kind == 'contained':
        route.SetStart(pad.GetPosition() - pcbnew.VECTOR2I_MM(.1, 0))
        route.SetEnd(pad.GetPosition() + pcbnew.VECTOR2I_MM(.1, 0))
    else:
        companion_refs = [peer.GetReference()]
        if kind == 'overlapping':
            peer.Move(pad.GetPosition() - other.GetPosition())
        else:
            route.SetStart(pad.GetPosition()); route.SetEnd(other.GetPosition())
            # A stationary native barrel makes this a shared trunk rather
            # than the separately proved, owned two-pad internal rigid path.
            via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet())
            via.SetPosition(pcbnew.VECTOR2I((route.GetStart().x+route.GetEnd().x)//2,
                                           (route.GetStart().y+route.GetEnd().y)//2))
            via.SetWidth(600000); via.SetDrill(300000)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    if protection in ('locked', 'generated_locked'): route.SetLocked(True)
    if protection == 'grouped':
        group = pcbnew.PCB_GROUP(board); group.SetName('native-source-group')
        board.Add(group); group.AddItem(route)
    members = [owner] + ([peer] if companion_refs else [])
    pads = [p for fp in members for p in fp.Pads() if p.IsOnCopperLayer()]
    proof = contacts.inspect(board, iter(pads))
    assert proof['ok'] and not proof['release_authority'], proof
    rows = [r for r in proof['contacts'] if r['track_uuid'] == route.m_Uuid.AsString()]
    assert len(rows) == (1 if kind == 'contained' else 2)
    assert all(r['fixed_boundary'] and r['far_nm'] == r['contact_nm'] for r in rows)
    assert all(r['contact_nm'] in [list(route.GetStart()), list(route.GetEnd())] for r in rows)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    original = copper.copper_inventory(board)
    target = repair.asdict(repair.FootprintRepairTarget(ref=owner.GetReference(),
        companion_refs=tuple(companion_refs), target_net=pad.GetNetname(),
        endpoint_ref='REMOTE', endpoint_pad='1', endpoint_x_mm=50, endpoint_y_mm=50,
        hit_count=1, distance_mm=1, priority=(0,)))
    changed, move = repair._relocate_footprint_worker(str(source), target,
        dict(rotation_delta_deg=0, dx_mm=0, dy_mm=1),
        generated_locked_uuids=(route.m_Uuid.AsString(),) if protection == 'generated_locked' else ())
    assert changed, move
    saved = pcbnew.LoadBoard(str(source))
    assert copper.copper_inventory(saved) == original
    assert not move['removed_track_uuids'] and not move['moved_internal_track_uuids']
    anchors = [a for a in move['preserved_anchors'] if a['track_uuid'] == route.m_Uuid.AsString()]
    assert len(anchors) == len(rows)
    # Boundary discovery is not connectivity approval. Before restoring the
    # obligations the relocated pads have genuinely lost the old trunk.
    saved.BuildConnectivity()
    for row in rows:
        moved = saved.FindFootprintByReference(row['ref'])
        land = next(p for p in moved.Pads() if p.GetNumber() == row['pad'])
        linked = {i.m_Uuid.AsString() for i in saved.GetConnectivity().GetConnectedItems(land)}
        assert row['track_uuid'] not in linked
    for row in rows:
        moved = saved.FindFootprintByReference(row['ref'])
        land = next(p for p in moved.Pads() if p.GetNumber() == row['pad'])
        restored = pcbnew.PCB_TRACK(saved); restored.SetNet(land.GetNet())
        restored.SetLayer(row['layer']); restored.SetWidth(200000)
        restored.SetStart(land.GetPosition()); restored.SetEnd(pcbnew.VECTOR2I(*row['contact_nm']))
        saved.Add(restored)
    saved.BuildConnectivity()
    for row in rows:
        moved = saved.FindFootprintByReference(row['ref'])
        land = next(p for p in moved.Pads() if p.GetNumber() == row['pad'])
        linked = {i.m_Uuid.AsString() for i in saved.GetConnectivity().GetConnectedItems(land)}
        assert row['track_uuid'] in linked


@pytest.mark.parametrize('mode', ['contained', 'shared'])
def test_native_membership_is_required_even_for_retained_boundary(monkeypatch, mode):
    board, _, pad, route = setup()
    pads = [pad]
    if mode == 'contained':
        route.SetEnd(pad.GetPosition() + pcbnew.VECTOR2I(20,0))
    else:
        peer = board.FindFootprintByReference('PEER'); other = next(iter(peer.Pads()))
        other.SetPosition(pad.GetPosition()); pads.append(other)
    class Disconnected:
        def GetConnectedItems(self, _): return []
    class View:
        def GetTracks(self): return board.GetTracks()
        def BuildConnectivity(self): return True
        def GetConnectivity(self): return Disconnected()
    proof = contacts.inspect(View(), pads)
    assert not proof['ok'] and proof['faults']
    assert all('not_native' in f['reason'] for f in proof['faults'])
