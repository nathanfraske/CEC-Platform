"""Exact contact containment for live, straight native track capsules.

Let S be a closed round-capped source segment and R a same-width collinear
subsegment. In the slab between R's endpoint projections S and R have the
same strip material. If R retains an endpoint of S, that endpoint's entire
original round cap is retained too. A peer capsule's projection extrema are
its endpoint extrema plus/minus (peer_width / 2) * sqrt(d dot d). Therefore
bounding the peer between the non-retained slab boundaries proves that ALL
of S intersect peer is in R. Squaring a NONNEGATIVE integer margin proves
the bound exactly; neither floating roots nor polygon-area tolerances occur.

This sufficient theorem does not union-credit fragments or prove routing,
retirement, process, current, clearance, return, or release authority. A false
result is not proof of lost contact: another construction/theorem may work.
"""
import cec_swig_guard

cec_swig_guard.pin()
import pcbnew

MAX_ITEMS = 16384
MAX_REPLACEMENTS = 16
MAX_COORDINATE = 2000000000


def _uid(item):
    return str(item.m_Uuid.AsString())


def _inventory(board):
    if not isinstance(board, pcbnew.BOARD):
        raise ValueError('literal_native_board_required')
    result = {}
    for item in board.GetTracks():
        if len(result) >= MAX_ITEMS:
            raise ValueError('bounded_native_track_inventory_required')
        uid = _uid(item)
        if not uid or uid in result:
            raise ValueError('unique_native_track_identities_required')
        result[uid] = item
    return result


def _geometry(board, item):
    if (not isinstance(item, pcbnew.PCB_TRACK)
            or item.GetClass() != 'PCB_TRACK'):
        raise ValueError('literal_straight_native_track_required')
    a, b = tuple(item.GetStart()), tuple(item.GetEnd())
    width, face = int(item.GetWidth()), int(item.GetLayer())
    code, net = int(item.GetNetCode()), str(item.GetNetname())
    if (a == b or any(type(v) is not int or abs(v) > MAX_COORDINATE
                      for p in (a, b) for v in p)
            or not 0 < width <= MAX_COORDINATE
            or any(abs(v) + (width + 1) // 2 > MAX_COORDINATE
                   for point in (a, b) for v in point)
            or code <= 0 or not net
            or face not in tuple(map(int, board.GetEnabledLayers().CuStack()))):
        raise ValueError('bounded_positive_assigned_copper_capsule_required')
    return dict(uuid=_uid(item), start_nm=list(a), end_nm=list(b),
                width_nm=width, layer_id=face, net=net, net_code=code)


def _retained_geometry(g):
    # Exact source geometry, not a producer's retained/qualified boolean.
    return (g['start_nm'], g['end_nm'], g['width_nm'], g['layer_id'], g['net'])


def _interval(source, peer, replacement):
    if (replacement['net'] != source['net']
            or replacement['layer_id'] != source['layer_id']
            or replacement['width_nm'] != source['width_nm']):
        return None, 'same_source_net_face_and_width_required'
    a, b = source['start_nm'], source['end_nm']
    d = [b[i] - a[i] for i in (0, 1)]
    square = sum(v * v for v in d)
    projections = []
    for point in (replacement['start_nm'], replacement['end_nm']):
        v = [point[i] - a[i] for i in (0, 1)]
        if v[0] * d[1] != v[1] * d[0]:
            return None, 'exact_collinear_replacement_required'
        projections.append(sum(v[i] * d[i] for i in (0, 1)))
    low, high = sorted(projections)
    if not 0 <= low < high <= square:
        return None, 'replacement_interval_must_be_inside_source_axis'
    extrema = [sum((point[i] - a[i]) * d[i] for i in (0, 1))
               for point in (peer['start_nm'], peer['end_nm'])]
    lower_margin, upper_margin = min(extrema) - low, high - max(extrema)
    support_squared_times_four = peer['width_nm'] ** 2 * square

    def boundary(retained_cap, margin):
        return dict(original_source_cap_retained=retained_cap,
                    margin_nm_squared=margin,
                    nonnegative_margin=margin >= 0,
                    four_margin_squared=4 * margin * margin,
                    peer_width_squared_times_axis_squared=support_squared_times_four,
                    proved=bool(retained_cap or margin >= 0
                                and 4 * margin * margin >= support_squared_times_four))

    lower = boundary(low == 0, lower_margin)
    upper = boundary(high == square, upper_margin)
    witness = dict(replacement_uuid=replacement['uuid'],
                   axis_nm=d, axis_squared_nm2=square,
                   interval_projection_nm2=[low, high],
                   peer_endpoint_projections_nm2=extrema,
                   lower=lower, upper=upper)
    return witness, (None if lower['proved'] and upper['proved']
                     else 'peer_projection_not_contained_in_retained_capsule_interval')


def prove(source_board, source_track_uuid, peer_track_uuid, candidate_board,
          replacement_track_uuids):
    """Re-derive one exact source-contact witness from actual live UUIDs.

    Each proposed replacement is examined independently. One sufficient
    collinear interval is required; disconnected intervals never receive
    blanket union credit. The peer must remain literally at its source
    geometry in the candidate. Other proposal/board gates remain the caller's
    responsibility. Unsupported or missing native material is unknown.
    """
    result = dict(schema=1, ok=False, complete=False, reason=None,
                  method='exact_integer_native_capsule_contact_containment',
                  source_track_uuid=source_track_uuid, peer_track_uuid=peer_track_uuid,
                  examined_replacements=[], no_union_credit=True,
                  current_qualified=False, routing_admitted=False,
                  retirement_authorized=False, release_authority=False)
    try:
        if (type(source_track_uuid) is not str or not source_track_uuid
                or type(peer_track_uuid) is not str or not peer_track_uuid
                or source_track_uuid == peer_track_uuid
                or type(replacement_track_uuids) not in (list, tuple)
                or not 1 <= len(replacement_track_uuids) <= MAX_REPLACEMENTS
                or any(type(u) is not str or not u for u in replacement_track_uuids)
                or len(set(replacement_track_uuids)) != len(replacement_track_uuids)):
            raise ValueError('bounded_explicit_unique_native_capsule_scope_required')
        original, candidate = _inventory(source_board), _inventory(candidate_board)
        if (source_track_uuid not in original or peer_track_uuid not in original
                or peer_track_uuid not in candidate
                or not set(replacement_track_uuids) <= candidate.keys()):
            raise ValueError('actual_source_peer_and_replacement_identities_required')
        source = _geometry(source_board, original[source_track_uuid])
        peer = _geometry(source_board, original[peer_track_uuid])
        retained = _geometry(candidate_board, candidate[peer_track_uuid])
        replacements = [_geometry(candidate_board, candidate[u])
                        for u in replacement_track_uuids]
        if (source['net_code'] != peer['net_code'] or source['net'] != peer['net']
                or source['layer_id'] != peer['layer_id']):
            raise ValueError('same_positive_source_peer_net_and_face_required')
        if _retained_geometry(peer) != _retained_geometry(retained):
            raise ValueError('retained_peer_geometry_changed')
        if any(q['net_code'] != retained['net_code'] for q in replacements):
            raise ValueError('replacement_must_share_actual_candidate_peer_net')
        result.update(source_capsule=source, peer_capsule=peer,
                      replacement_capsules=replacements)
        if not original[source_track_uuid].GetEffectiveShape(source['layer_id']).Collide(
                original[peer_track_uuid].GetEffectiveShape(peer['layer_id']), 0):
            result.update(complete=True, reason='no_actual_source_peer_contact')
            return result
        witnesses = []
        for replacement in replacements:
            witness, refusal = _interval(source, peer, replacement)
            result['examined_replacements'].append(dict(
                uuid=replacement['uuid'], sufficient=refusal is None,
                reason=refusal, witness=witness))
            if refusal is None:
                witnesses.append(witness)
        result.update(complete=True, ok=bool(witnesses),
                      reason=('entire_source_peer_contact_retained' if witnesses
                              else 'no_single_sufficient_collinear_source_interval'),
                      witnesses=witnesses,
                      all_old_contact_points_retained=bool(witnesses))
    except (ValueError, TypeError, AttributeError, RuntimeError, KeyError) as exc:
        result['reason'] = type(exc).__name__ + ':' + str(exc)
    return result
