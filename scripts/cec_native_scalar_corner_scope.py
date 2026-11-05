"""Read-only bounded scalar finishing scope, independent of board identities.

Skip launch and too-short vertices before funding the finite mutation scope.
This is scheduling only: the native chamfer engine and independent receiver
still decide whether an eligible proposal preserves every real contact.
"""
from collections import Counter, defaultdict
import math
import time
from cec_octilinear_corner import kind as corner_kind, coordinate_inset
from cec_route_corner_contacts import native_pad_anchor


def select(board, eligible_nets, *, minimum_chamfer_nm=50000,
           maximum_chamfer_nm=200000,
           maximum_width_nm=499000, maximum_candidates=16,
           maximum_scoped_tracks=32, maximum_items=16384,
           junction_tolerance_nm=20000, timeout_s=10.):
    bounds = ((minimum_chamfer_nm, 1, 1000000),
              (maximum_chamfer_nm, 1, 2000000),
              (maximum_width_nm, 1, 10000000),
              (maximum_candidates, 1, 128),
              (maximum_scoped_tracks, 2, 256),
              (maximum_items, 2, 32768),
              (junction_tolerance_nm, 0, 1000000))
    if (any(type(value) is not int or not lower <= value <= upper
            for value, lower, upper in bounds)
            or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10):
        raise ValueError('bounded_native_scalar_scope_required')
    if (not isinstance(eligible_nets, (set, frozenset))
            or any(not isinstance(net, str) or not net for net in eligible_nets)):
        raise ValueError('positive_scalar_net_scope_required')
    deadline = time.monotonic() + timeout_s
    tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(tracks) + len(pads) > maximum_items:
        raise ValueError('native_scalar_inventory_exceeds_bound')
    uids = [t.m_Uuid.AsString() for t in tracks]
    if len(uids) != len(set(uids)):
        raise ValueError('native_scalar_duplicate_track_identity')
    grouped = {t.m_Uuid.AsString() for t in tracks
               if any(g.ContainsItem(t) for g in board.Groups())}
    vias = [t for t in tracks if t.GetClass() == 'PCB_VIA']
    vertices = defaultdict(list)
    for t in tracks:
        if t.GetClass() != 'PCB_TRACK':
            continue
        for at in (tuple(t.GetStart()), tuple(t.GetEnd())):
            vertices[str(t.GetNetname()), int(t.GetLayer()), at].append(t)
    scope, selected, skipped = set(), [], Counter()
    body_tees=[]
    complete = True
    for (net, layer, at), items in sorted(vertices.items()):
        if time.monotonic() >= deadline:
            complete = False
            break
        if (net not in eligible_nets or len(items) != 2
                or items[0].GetWidth() != items[1].GetWidth()
                or not 0 < items[0].GetWidth() <= maximum_width_nm
                or any(t.m_Uuid.AsString() in grouped for t in items)):
            continue
        vectors = []
        for t in items:
            other = t.GetEnd() if tuple(t.GetStart()) == at else t.GetStart()
            vectors.append((other.x - at[0], other.y - at[1]))
        if corner_kind(*vectors) is None:
            continue
        # Mirror only the engine's immutable launch policy. This grants no
        # freedom to move pads/barrels and is not a contact-preservation proof.
        corner = items[0].GetStart() if tuple(items[0].GetStart()) == at else items[0].GetEnd()
        if (any(v.GetNetname() == net and
                math.hypot(v.GetPosition().x-at[0], v.GetPosition().y-at[1])
                <= junction_tolerance_nm for v in vias)
                or any(native_pad_anchor(p,corner,layer_id=layer) for p in pads)):
            skipped['immutable_launch'] += 1
            continue
        # A third real track can contact this vertex on its interior without
        # contributing an endpoint to the map. The native constructor already
        # protects such tees. Do not repeatedly schedule them as cosmetic
        # failures. Exact integer projection and native copper contact are
        # both required; another net/layer or a nearby bbox is not a tee.
        witnesses=[]
        for t in tracks:
            if (t in items or t.GetClass()!='PCB_TRACK' or t.GetNetname()!=net
                    or int(t.GetLayer())!=layer):continue
            a,b=t.GetStart(),t.GetEnd()
            if any(abs(p.x-at[0])<=junction_tolerance_nm and abs(p.y-at[1])<=junction_tolerance_nm
                    for p in (a,b)):continue
            dx,dy=b.x-a.x,b.y-a.y;px,py=at[0]-a.x,at[1]-a.y
            length2=dx*dx+dy*dy;projection=px*dx+py*dy
            if (not length2 or not 0<projection<length2
                    or (px*dy-py*dx)**2>junction_tolerance_nm**2*length2):continue
            if t.GetEffectiveShape(layer).Collide(corner):witnesses.append(t.m_Uuid.AsString())
        if witnesses:
            skipped['immutable_body_tee']+=1
            body_tees.append(dict(net=net,layer=layer,at_nm=list(at),
                source_track_uuids=sorted(t.m_Uuid.AsString() for t in items),
                actual_native_body_track_uuids=sorted(witnesses)))
            continue
        # Share exact physical-length/quantization semantics with the native
        # engine. A pair of diagonal tracks is not a free-angle exception.
        if coordinate_inset(*vectors, maximum_nm=maximum_chamfer_nm,
                minimum_nm=minimum_chamfer_nm) is None:
            skipped['too_short'] += 1
            continue
        ids = {t.m_Uuid.AsString() for t in items}
        if len(selected) >= maximum_candidates or len(scope | ids) > maximum_scoped_tracks:
            complete = False
            break
        scope |= ids
        selected.append(dict(net=net, layer=layer, at_nm=list(at),
                             source_track_uuids=sorted(ids)))
    return dict(selected=selected, scope=sorted(scope),
                skipped=dict(skipped), inventory_complete=complete,
                immutable_body_tees=body_tees,
                mutation_or_contact_authority_granted=False)
