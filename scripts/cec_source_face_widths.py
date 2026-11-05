"""Complete Source demand widths, without leaking thin-inner-layer floors.

Only a positive, independently rederived current model can explain a scalar
request as an actual-face physics/class floor. Unexplained Source widths stay
net-global: this is not permission to narrow an oversized Source conductor or
to infer a load, sharing, via capacity, or a width-qualified connection path.
"""
import math

import cec_decoupler_cell as cells


def envelope(board, requests, net, current):
    """Recompute from the COMPLETE fresh Source requests, never a caller map."""
    if type(requests) is not dict or len(requests) > 64:
        raise ValueError('complete_source_face_width_requests_required')
    base = max(int(board.GetDesignSettings().m_TrackMinWidth),
        int(cells._netclass(board, net)['width']))
    widths = []
    relevant = []
    for request in requests.values():
        if request.get('net') != net:
            continue
        width = request.get('width_nm', 0)
        if type(width) is not int or width < 0:
            raise ValueError('exact_source_face_demand_width_required')
        widths.append(width); relevant.append(request)
    legacy = max([base, *widths])
    enabled = set(map(int, board.GetEnabledLayers().CuStack()))
    if current is None or net == 'GND':
        return {face: legacy for face in enabled}
    authority = current.get('current_authority', {})
    floors = current.get('required_by_layer_nm')
    if (any(type(authority.get(k)) not in (int, float)
            or not math.isfinite(authority[k]) or authority[k] <= 0
            for k in ('amps', 'geometry_margin'))
            or type(authority.get('margin_included')) is not bool
            or type(floors) is not dict
            or any(type(face) is not int or type(width) is not int or width <= 0
                for face, width in floors.items())
            or not enabled <= set(floors)):
        # Incomplete/legacy synthetic models earn no face-specific credit.
        # Preserve their former net-global demand AND every valid physical
        # floor. Original current-authority receivers still own refusal.
        return {face: max(legacy, floors.get(face, 0)
            if type(floors) is dict and type(floors.get(face)) is int else 0)
            for face in enabled}
    result = {face: max(base, floors[face]) for face in enabled}
    opaque = base
    for request in relevant:
        access = []
        for end in ('a', 'b'):
            raw = request.get(end, {}).get('layers')
            if (type(raw) not in (list, tuple) or not raw
                    or any(type(face) is not int or face not in enabled for face in raw)):
                access = []; break
            access.append(set(raw))
        common = access[0] & access[1] if len(access) == 2 else set()
        width = request.get('width_nm', 0)
        # Disjoint/ambiguous access cannot earn narrower receiving. Nor can
        # an over-floor Source width, even when its face is perfectly known:
        # terminal connectivity alone does not prove that width along a path.
        if not common or width > min(result[face] for face in common):
            opaque = max(opaque, width)
    return {face: max(width, opaque) for face, width in result.items()}
