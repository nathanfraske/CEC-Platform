"""Retained CONTROL/Ground-tie ports in the existing macro observer.

Used only after the existing observer independently compares the complete
Source-rederived boundary authority. Fixed control pins remain control, their
native owners/groups and thin attachment chains remain exact, and the actual
capacitor Ground roots still owe all existing local-return/process checks.
"""
import hashlib
import inspect
import time

import pcbnew
import cec_source_ground_boundary_connection as observer
import cec_reference_map_reownership as ink
import cec_selected_cap_ground_boundary as ownership


MAX_STRAP_CONTACT_CHECKS = 65536


def _require(ok, reason):
    if not ok:
        raise ValueError('retained_control_' + reason)


def _groups_for(board, items):
    """Only the fixed owner's/straps' groups, not unrelated moving groups."""
    return sorted((ownership.force._uid(g), g.GetName(), bool(g.IsLocked()),
        tuple(sorted(ownership.force._uid(i) for i in g.GetItems())))
        for g in board.Groups() if any(g.ContainsItem(i) for i in items))


def _owner_identity(board, pad):
    fp = pad.GetParentFootprint()
    fields = sorted((ownership.force._uid(t), t.GetName(), t.GetText(), tuple(t.GetPosition()),
        t.GetTextAngle().AsDegrees(), int(t.GetLayer()), tuple(t.GetTextSize()),
        t.GetTextThickness(), t.IsVisible(), t.IsLocked(), t.IsMirrored(),
        t.IsKeepUpright(), t.GetFontName(), t.IsBold(), t.IsItalic(),
        int(t.GetHorizJustify()), int(t.GetVertJustify())) for t in fp.GetFields())
    art = []
    for item in fp.GraphicalItems():
        _require(item.GetClass() in ('PCB_TEXT', 'PCB_SHAPE'), 'unsupported_fixed_owner_art')
        art.append((ownership.force._uid(item), ink._geometry(item)))
    return ownership._stable(dict(uuid=ownership.force._uid(fp), at_nm=list(fp.GetPosition()),
        orientation=fp.GetOrientationDegrees(), flipped=bool(fp.IsFlipped()),
        attributes=int(fp.GetAttributes()), fields=fields, art=sorted(art),
        pads=sorted((ownership._item(board, p) for p in fp.Pads()), key=lambda p:p['uuid']),
        groups=_groups_for(board, [fp, *fp.Pads()])))


def _source_control_straps(parent, controls, class_width, deadline):
    """Bind actual thin CONTROL attachment chains, never a width authority.

    A full Source-class edge is a separate macro cut and stops this traversal.
    Merely belonging to the same GND net/fill does not annex another branch.
    Native exact shape contact is used conservatively, including tangency.
    """
    tracks = [t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
        and t.GetNetname() == 'GND' and t.GetWidth() < class_width]
    _require(len(tracks) <= ownership.MAX_ITEMS, 'strap_inventory_bound')
    found = {}; frontier = list(controls); checks = 0
    while frontier:
        peer = frontier.pop()
        for track in tracks:
            observer._tick(deadline)
            uid = ownership.force._uid(track)
            if uid in found or not peer.IsOnLayer(track.GetLayer()):
                continue
            checks += 1
            _require(checks <= MAX_STRAP_CONTACT_CHECKS, 'strap_contact_work_bound')
            face = int(track.GetLayer())
            if not peer.GetEffectiveShape(face).Collide(track.GetEffectiveShape(face), 0):
                continue
            found[uid] = track; frontier.append(track)
    return found


def retained_control_ports(parent, board, authority, context, deadline):
    """Called ONLY after the real observer's exact fresh authority comparison.

    No caller receipt is promoted.  Canonical/MPN roles are supplied by the
    independently rederived Source ownership helper and are checked again
    against both native owners.  These fixed ports are explicitly NOT roots.
    """
    if authority.get('source_selected_cap_multiport_scope') != ownership.SCOPE:
        return {}
    observer._tick(deadline)
    source = ownership._items(parent); live = ownership._items(board)
    controls = {}; rows = authority.get('exact_retained_ports')
    _require(type(rows) is list, 'fresh_ports_required')
    for row in rows:
        if row.get('role') != 'control':
            continue
        item = row.get('item', {}); uid = item.get('uuid')
        _require(uid not in controls and item.get('kind') == 'PAD'
            and row.get('immutable_retained') is True
            and row.get('primary_manufacturer_role') == 'control'
            and row.get('control_remains_control') is True
            and row.get('functional_ground_return') is False
            and row.get('supplies_cut_or_ground_current_authority') is False,
            'literal_fixed_control_port_required')
        before, after = source.get(uid), live.get(uid)
        _require(before is not None and after is not None
            and before.GetClass() == after.GetClass() == 'PAD'
            and before.GetNetname() == after.GetNetname() == 'GND'
            and not before.HasHole() and before.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
            and item == ownership._item(parent, before)
            and item == ownership._item(board, after)
            and _owner_identity(parent, before) == _owner_identity(board, after),
            'fixed_pad_owner_or_group_identity_changed')
        first = before.GetParentFootprint(); last = after.GetParentFootprint()
        original = observer.roles.footprint_contract(first)
        current = observer.roles.footprint_contract(last)
        _require(original is not None and original == current
            and original['pins'].get(before.GetNumber()) == 'control'
            and first.GetReference() in context['fresh']['stationary_device_owners'],
            'fresh_control_role_required')
        controls[uid] = before
    straps = _source_control_straps(parent, controls.values(),
        authority['source_full_class_width_nm'], deadline)
    for uid, before in straps.items():
        observer._tick(deadline); after = live.get(uid)
        _require(after is not None and after.GetClass() == 'PCB_TRACK'
            and ownership._item(parent, before) == ownership._item(board, after)
            and _groups_for(parent, [before]) == _groups_for(board, [after]),
            'source_thin_strap_changed_or_deleted')
    return {uid:dict(pad_uuid=uid, role='control', control_remains_control=True,
        fixed_source_pad_owner_group_unchanged=True,
        retained_thin_strap_uuids=sorted(straps), functional_ground_return=False,
        root_or_width_or_current_authority=False) for uid in controls}
