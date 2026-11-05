"""Read-only native reference-plane proposals for complete-pair return fields.

Candidate contact is necessary, not final admission: the actual output still
has to be refilled and every required barrel independently rechecked. The
preview is transaction-local and never changes the routing board's zones.
"""
import os
from pathlib import Path
import tempfile
from functools import wraps

import pcbnew


_CONTEXT_ATTRIBUTE = '_cec_pair_reference_candidates'


def _net_items(board):
    items = list(board.GetTracks()) + list(board.Zones())
    items.extend(pad for fp in board.GetFootprints() for pad in fp.Pads())
    result = {}
    for item in items:
        uid = item.m_Uuid.AsString()
        if not uid or uid in result:
            raise ValueError('preview requires unique native net-bearing UUIDs')
        result[uid] = item
    return result


def _authorship(board):
    return {uid:(item.GetClass(),str(item.GetNetname()),int(item.GetNetCode()))
            for uid,item in _net_items(board).items()}


def _restore_preview_authorship(preview, authored):
    """Restore only exact source UUID/net declarations on the private preview.

    Native loading can infer a new floating signal barrel's net from a stale
    filled plane. That inferred contact is not authored signal ownership and
    must not remove its antipad from the candidate reference calculation.
    """
    items = _net_items(preview)
    if items.keys() != authored.keys() or any(
            items[uid].GetClass() != row[0] for uid,row in authored.items()):
        raise ValueError('native preview changed source primitive identities')
    restored = 0
    for uid,(_kind,name,_code) in authored.items():
        item = items[uid]
        if str(item.GetNetname()) == name:
            continue
        restored += 1
        if not name:
            item.SetNetCode(0)
            continue
        net = preview.FindNet(name)
        if net is None:
            preview.Add(pcbnew.NETINFO_ITEM(preview,name))
            net = preview.FindNet(name)
        item.SetNet(net)
    return restored


def candidate_contact_filter(board):
    """Return the transaction-local proposal filter, if one is active."""
    context = getattr(board, _CONTEXT_ATTRIBUTE, None)
    return context['accept'] if context is not None else None


def with_candidate_reference(function):
    """Share one lazy native preview across a bounded precision transaction.

    Signal-transition returns need the same check as the final PTH sweep.
    The first prospective return establishes this snapshot; subsequent foreign
    copper checks still use the live board. Later antipad/island changes must
    pass the separate final refill. This is never final plane-contact evidence.
    Scoped cleanup prevents a placement change or later routing invocation
    from inheriting an obsolete preview, including exceptional exits.
    """
    @wraps(function)
    def wrapped(board, *args, **kwargs):
        previous = getattr(board, _CONTEXT_ATTRIBUTE, None)
        state = dict(compiled=False, evidence=None, contact=None)

        def accept(point, diameter):
            if not state['compiled']:
                contact, evidence = compile_contact_filter(board)
                state.update(compiled=True, contact=contact, evidence=evidence)
            return state['contact'] is None or state['contact'](point, diameter)

        setattr(board, _CONTEXT_ATTRIBUTE, dict(accept=accept))
        try:
            result = function(board, *args, **kwargs)
            if isinstance(result, dict) and state['compiled']:
                result['return_reference_preview'] = state['evidence']
            return result
        finally:
            if previous is None:
                delattr(board, _CONTEXT_ATTRIBUTE)
            else:
                setattr(board, _CONTEXT_ATTRIBUTE, previous)
    return wrapped


def compile_contact_filter(board):
    import cec_fr
    import cec_ground_plane as ground

    original_name = board.GetFileName() or ''
    layers, profile = ground._dedicated_ground_layers(board, original_name)
    if not profile:
        return None, dict(applicable=False, reason='no_declared_reference_profile')
    if not layers:
        raise ValueError('declared profile has no enabled reference planes')
    authored = _authorship(board)
    with tempfile.TemporaryDirectory(prefix='cec-return-reference-') as work:
        target = str(Path(work)/'preview.kicad_pcb')
        try:
            # The convenience SaveBoard wrapper rebuilds live connectivity
            # and can relabel an unfinished signal via as GND through the old
            # filled plane. The native format writer does not mutate the live
            # routing board. Loading its private snapshot still needs the
            # exact UUID-bound authorship replay below, before fresh refill.
            writer = pcbnew.PCB_IO_KICAD_SEXPR()
            writer.SaveBoard(target, board)
        finally:
            board.SetFileName(original_name)
            if _authorship(board) != authored:
                raise ValueError('native reference snapshot mutated live net authorship')
        if original_name and os.path.isfile(original_name):
            cec_fr.copy_project_sidecars(original_name, target)
        preview = pcbnew.LoadBoard(target)
        restored = _restore_preview_authorship(preview,authored)
        # The source profile remains the authority; a temporary basename must
        # not silently select a different stackup or the legacy fallback.
        preview.SetFileName(original_name)
        filled = ground.fill_board(preview, board_path=original_name)
        if not filled.get('ok'):
            raise ValueError('reference preview refused: %s' % filled.get('reasons'))
        received = _authorship(preview)
        if any(uid not in received or received[uid][:2] != row[:2]
               for uid,row in authored.items()):
            raise ValueError('reference refill changed authored native net ownership')
        polygons = {int(layer):[zone.GetFilledPolysList(layer)
                    for zone in preview.Zones()
                    if not zone.GetIsRuleArea() and zone.GetNetname() == 'GND'
                    and zone.IsOnLayer(layer)] for layer,_ in layers}

    def contact(point, diameter):
        # Keep the native owner alive as long as borrowed filled polygons.
        _owner = preview
        at = pcbnew.VECTOR2I(round(point[0]*1e6), round(point[1]*1e6))
        land = pcbnew.SHAPE_SEGMENT(at, at, round(diameter*1e6))
        return bool(polygons) and all(any(poly.Collide(land,0) for poly in rows)
                                      for rows in polygons.values())

    return contact, dict(applicable=True, profile=profile,
        layers=[name for _,name in layers], preview_filled=True,
        live_board_net_authorship_unchanged=True,
        authored_native_net_count=len(authored),authored_net_restorations=restored,
        preview_authorship_received_after_refill=True,
        scope='candidate-filter-only', final_native_refill_required=True)
