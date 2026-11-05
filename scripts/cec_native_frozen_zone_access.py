"""Use actual saved pour material only in an explicitly frozen native trial.

An outline remains the default future-copper reservation. A private additive
or narrowly received source-cut construction may use an existing empty pocket
only after independently matching every reserved zone to a saved source. No
zone fill, outline, clearance or identity may change during this context.
This is search geometry, not current, contact or release qualification.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import math
from pathlib import Path
import time
import tempfile
import pcbnew

_ACTIVE = ContextVar('cec_native_frozen_zone_access', default=None)


def _zone_row(zone):
    layers=tuple(int(l) for l in zone.GetLayerSet().CuStack())
    return (str(zone.m_Uuid.AsString()),str(zone.GetNetname()),zone.GetNetCode(),
        bool(zone.GetIsRuleArea()),layers,int(zone.GetLocalClearance()),
        bool(zone.IsFilled()),zone.Outline().Format(),
        tuple((l,bool(zone.HasFilledPolysForLayer(l)),zone.GetFilledPolysList(l).Format())
              for l in layers))


def _zones(board):
    rows={str(z.m_Uuid.AsString()):_zone_row(z) for z in board.Zones()}
    if len(rows)!=len(list(board.Zones())):
        raise ValueError('frozen_zone_identity_ambiguous')
    return rows


def cache_token(board):
    active=_ACTIVE.get()
    return active['token'] if active is not None and active['board'] is board else None


def obstacle(board,zone,layer):
    """Default outline; typed clone of the exact source fill when frozen."""
    active=_ACTIVE.get()
    if active is None or active['board'] is not board:
        return zone.Outline()
    if time.monotonic()>=active['deadline']:
        raise ValueError('frozen_native_zone_search_deadline')
    uid=str(zone.m_Uuid.AsString())
    if uid not in active['rows'] or _zone_row(zone)!=active['rows'][uid]:
        raise ValueError('frozen_reserved_zone_changed')
    if active['selected_ids'] is not None and uid not in active['selected_ids']:
        # A local explicit scope never changes the default reservation of
        # another zone. It stays an authored-outline obstacle, not a newly
        # available hole or implicitly received mutable fill.
        return zone.Outline()
    key=(uid,int(layer))
    if key not in active['shapes']:
        raise ValueError('frozen_reserved_zone_layer_not_independently_bound')
    # Do not expose the context's authoritative clone to a mutable caller.
    return pcbnew.SHAPE_POLY_SET(active['shapes'][key])


@contextmanager
def frozen(board,source,*,timeout_s=10.,max_zones=32,zone_uuids=None,
           allow_unreserved_ground_refill=False):
    """Finite source-bound search mode; all saved-board receivers still apply.

    Callers must save the construction and receive exact source-plus-delta,
    unchanged non-GND fills, DRC, field, current, and terminal partitions.
    Enter again against the current saved parent after any zone refill.
    """
    import cec_fr as fr
    import cec_native_fill_geometry as fill
    if (type(timeout_s) not in (float,int) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_zones) is not int or not 1<=max_zones<=32
            or type(allow_unreserved_ground_refill) is not bool):
        raise ValueError('bounded_frozen_zone_search_required')
    deadline=time.monotonic()+timeout_s
    if _ACTIVE.get() is not None:
        raise ValueError('nested_frozen_zone_search_not_allowed')
    selected=None
    if zone_uuids is not None:
        if (type(zone_uuids) not in (list,tuple,set,frozenset) or not 1<=len(zone_uuids)<=max_zones
                or any(type(u) is not str or not u for u in zone_uuids)
                or len(set(zone_uuids))!=len(zone_uuids)):
            raise ValueError('bounded_explicit_frozen_reserved_zone_scope_required')
        selected=set(zone_uuids)
    source=Path(source).resolve()
    if not source.is_file():raise ValueError('saved_frozen_zone_source_required')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    parent=pcbnew.LoadBoard(str(source));parent_rows=_zones(parent);rows=_zones(board)
    refilled=[]
    if allow_unreserved_ground_refill:
        # A retained GND barrel does not gain a new power-pour antipad when
        # ONLY ordinary GND planes have been refilled around moving parts.
        # Compare complete serialized zone authorship, not a few getters:
        # every foreign/reserved fill stays exact; only unreserved GND's
        # generated filled polygons may differ. No live zone is modified.
        if rows.keys()!=parent_rows.keys() or len(rows)>256:
            raise ValueError('frozen_zones_differ_from_saved_source')
        import cec_additive_route_receiving as additive
        import cec_copper_echo as syntax
        import cec_field_coupling as field
        parent_zones={str(z.m_Uuid.AsString()):z for z in parent.Zones()}
        allowed=set()
        for z in board.Zones():
            uid=str(z.m_Uuid.AsString());old=parent_zones[uid]
            if (not z.GetIsRuleArea() and z.GetNetname()==old.GetNetname()=='GND'
                    and not any(fr._zone_is_route_reservation(b,q,l)
                        for b,q in ((board,z),(parent,old)) for l in q.GetLayerSet().CuStack())):
                allowed.add(uid)
            elif rows[uid]!=parent_rows[uid]:
                raise ValueError('frozen_zones_differ_from_saved_source')
        with tempfile.TemporaryDirectory(prefix='cec-source-ground-fill-match-') as work:
            snapshot=Path(work)/'read-only.kicad_pcb'
            field._save_field_snapshot(board,snapshot)
            _,current_nodes=additive._nodes(snapshot);_,source_nodes=additive._nodes(source)
            for uid in rows:
                if time.monotonic()>=deadline:raise ValueError('frozen_native_zone_search_deadline')
                def authored(node):
                    return syntax._freeze([q for q in node if not (uid in allowed
                        and isinstance(q,list) and q and q[0] in ('filled_polygon','fill_segments'))])
                if authored(current_nodes[uid])!=authored(source_nodes[uid]):
                    raise ValueError('frozen_zones_differ_from_saved_source')
        refilled=sorted(uid for uid in allowed if rows[uid]!=parent_rows[uid])
    elif rows!=parent_rows:
        raise ValueError('frozen_zones_differ_from_saved_source')
    if time.monotonic()>=deadline:raise ValueError('frozen_native_zone_search_deadline')
    shapes={};reserved=set();vertices=0
    for z in board.Zones():
        uid=str(z.m_Uuid.AsString())
        if selected is not None and uid not in selected:continue
        for layer in z.GetLayerSet().CuStack():
            if not fr._zone_is_route_reservation(board,z,layer):continue
            reserved.add(uid)
            if len(reserved)>max_zones:raise ValueError('frozen_reserved_zone_count_bound')
            if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
                raise ValueError('frozen_reserved_zone_fill_unknown')
            native=z.GetFilledPolysList(layer)
            _,count=fill.identity(native,deadline)
            vertices+=count
            if vertices>200000:raise ValueError('frozen_native_zone_vertex_bound')
            shapes[(uid,int(layer))]=pcbnew.SHAPE_POLY_SET(native)
    if selected is not None and selected!=reserved:
        raise ValueError('explicit_frozen_reserved_zone_scope_unavailable')
    active=dict(board=board,rows=rows,shapes=shapes,deadline=deadline,
        token=object(),source_sha256=digest,selected_ids=selected)
    handle=_ACTIVE.set(active)
    receipt=dict(scope='source_frozen_actual_pour_material_search',source_sha256=digest,
        reserved_zones=len(reserved),native_layer_shapes=len(shapes),
        exact_native_fill_vertices=vertices,source_and_zones_unchanged=False,
        explicit_frozen_zone_uuids=None if selected is None else sorted(selected),
        allowed_unreserved_ground_refill=allow_unreserved_ground_refill,
        source_ground_refill_zone_uuids=refilled,
        unselected_zones_keep_authored_outline_reservations=True,
        release_authority=False,power_authority=False,receiving_still_required=True)
    try:
        yield receipt
        if _zones(board)!=rows or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise ValueError('frozen_zone_or_saved_source_changed_during_search')
        receipt['source_and_zones_unchanged']=True
    finally:
        _ACTIVE.reset(handle)


def search(board,source,callback,*,timeout_s=10.,max_zones=32,zone_uuids=None):
    """Dispatch one bounded search against independently matched source fills.

    A new lease is owed for each search, not for an entire construction wave.
    The callback may inspect or propose ordinary routes but may not change
    any zone. This returns search evidence only; it does not save, admit or
    qualify either proposed copper or an electrical/current transition.
    """
    if not callable(callback):
        raise ValueError('bounded_native_search_callback_required')
    with frozen(board,source,timeout_s=timeout_s,max_zones=max_zones,zone_uuids=zone_uuids) as receipt:
        result=callback()
    return result,receipt
