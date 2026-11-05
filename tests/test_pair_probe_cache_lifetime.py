"""Shared pair probes must see current opposite-member copper after edits."""
import hashlib
import inspect
from pathlib import Path

import pcbnew
import pytest

import cec_native_items
import cec_precision_route as route
from test_ribbon_physical_prefilter import fixture


def legacy_stub():
    source = inspect.getsource(route._route_paired_stub)
    old = 'partner_track_cache = {}'
    assert source.count(old) == 1
    scope = {}
    exec(compile(source.replace(old, 'partner_track_cache = partner_shape_cache'),
                 '<legacy-partner-track-cache>', 'exec'), route.__dict__, scope)
    return scope['_route_paired_stub']


def raw_legacy_or_current(use_legacy):
    return legacy_stub() if use_legacy else route._route_paired_stub


@pytest.mark.parametrize('layer,quarter', [('F.Cu', 0), ('B.Cu', 1), ('In2.Cu', 2)])
@pytest.mark.parametrize('edit', ['add', 'remove', 'move', 'resize', 'net', 'layer', 'arc', 'via'])
def test_loaded_probe_tracks_current_geometry(tmp_path, layer, quarter, edit):
    source, pair, endpoints, avoid, _ = fixture(tmp_path, 'clear', quarter, layer)
    before_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    results = {}
    for old in (False, True):
        board = pcbnew.LoadBoard(str(source))
        layer_id = board.GetLayerID(layer)
        p_start, p_end, n_start, n_end = endpoints
        middle = tuple((a+b)/2 for a,b in zip(p_start, p_end))
        # Offset normal to the tested P route (orientation/translation invariant).
        dx, dy = p_end[0]-p_start[0], p_end[1]-p_start[1]
        nx, ny = -dy/8, dx/8
        obstacle = None

        def put(kind, away):
            if kind == 'arc':
                item = pcbnew.PCB_ARC(board)
                item.SetStart(route._v(middle[0]+3*nx-.7*ny, middle[1]+3*ny+.7*nx))
                item.SetEnd(route._v(middle[0]+3*nx+.7*ny, middle[1]+3*ny-.7*nx))
                item.SetMid(route._v(middle[0]+4*nx, middle[1]+4*ny))
            elif kind == 'via':
                item = pcbnew.PCB_VIA(board)
                item.SetPosition(route._v(middle[0]+3*nx, middle[1]+3*ny))
                item.SetViaType(pcbnew.VIATYPE_THROUGH)
                item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                item.SetDrill(pcbnew.FromMM(.3))
            else:
                item = pcbnew.PCB_TRACK(board)
                shift = 3. if away else 0.
                item.SetStart(route._v(middle[0]+nx*shift-ny*.7,
                                      middle[1]+ny*shift+nx*.7))
                item.SetEnd(route._v(middle[0]+nx*shift+ny*.7,
                                    middle[1]+ny*shift-nx*.7))
            item.SetNet(board.FindNet(pair['n']))
            if kind != 'via':
                item.SetLayer(layer_id)
            item.SetWidth(pcbnew.FromMM(.6 if kind == 'via' else .2))
            board.Add(item)
            return item

        if edit in ('remove', 'move', 'resize', 'net', 'layer', 'arc', 'via'):
            obstacle = put(edit, edit == 'move')
            if edit == 'resize':
                # A centerline outside the clearance becomes a collision solely
                # through width growth, without changing its UUID or endpoints.
                delta = route._v(nx*.55, ny*.55)
                obstacle.Move(delta)
            elif edit == 'net':
                obstacle.SetNet(board.FindNet(pair['p']))
            elif edit == 'layer':
                obstacle.SetLayer(pcbnew.B_Cu if layer_id != pcbnew.B_Cu else pcbnew.F_Cu)

        cache = {}
        solve = raw_legacy_or_current(old)
        ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
        solve(board, pair, endpoints, layer=layer, allow_detour=False,
              partner_shape_cache=cache)
        # Retire only copper emitted by the warm-up call, not the obstacle.
        cec_native_items.discard_items(board, [t for t in board.GetTracks()
            if t.m_Uuid.AsString() not in ids])
        if edit == 'add':
            obstacle = put(edit, False)
        elif edit == 'remove':
            cec_native_items.discard_items(board, [obstacle])
        elif edit in ('move', 'via'):
            obstacle.Move(route._v(-nx*3, -ny*3))
        elif edit == 'resize':
            obstacle.SetWidth(pcbnew.FromMM(1.2))
        elif edit == 'net':
            obstacle.SetNet(board.FindNet(pair['n']))
        elif edit == 'layer':
            obstacle.SetLayer(layer_id)
        elif edit == 'arc':
            # Replacing the same-id native shape is not an item-count change.
            obstacle.SetMid(route._v(middle[0], middle[1]))
        shared = solve(board, pair, endpoints, layer=layer, allow_detour=False,
                       partner_shape_cache=cache)
        # Reference uses a completely fresh probe on the identical live state.
        cec_native_items.discard_items(board, [t for t in board.GetTracks()
            if t.m_Uuid.AsString() not in ids and t != obstacle])
        fresh = route._route_paired_stub(board, pair, endpoints, layer=layer,
                                        allow_detour=False)
        shared_clear = shared.get('admission', {}).get('direct', {}).get('p', {}).get('partner_copper')
        # Success reports use local_search; a separate exact native predicate is
        # the independent reference regardless of reporting shape.
        exact = route._partner_tracks_clear(board, p_start, p_end,
            pcbnew.FromMM(pair['width']), layer_id, board.GetNetcodeFromNetname(pair['n']),
            clearance_nm=pcbnew.FromMM(route._pair_clearance(board, pair, .2)))
        if shared_clear is None:
            shared_clear = True
        results[old] = (shared_clear, exact, bool(shared.get('refused')), bool(fresh.get('refused')))
        if not old:
            assert shared_clear == exact, (edit, results[old])
            assert bool(shared.get('refused')) == bool(fresh.get('refused'))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before_sha
    assert results[True][0] != results[True][1], (edit, results)
