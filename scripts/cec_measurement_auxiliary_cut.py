"""Own an existing manufacturer-declared, same-net package input strap.

A package strap and its external measurement departure need not have equal
widths. Their scopes remain separate: only a literal short native strap can
leave the external leaf's view, and it creates its own mandatory restoration
request. No force copper, barrel, external branch or guessed pin may be cut.
"""
import math
import time

import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_pair_semantics as semantics


def _reference_map(board, fp, *, deadline):
    """Recognize an unchanged saved annotation association, never an unlock."""
    from pathlib import Path
    from cec_cell_row_rebuild import _source_binding
    import cec_source_reference_group_transport as maps
    source=Path(board.GetFileName()).resolve(strict=True)
    saved=pcbnew.LoadBoard(str(source))
    if saved is None or _source_binding(board)!=_source_binding(saved):
        raise ValueError('auxiliary_reference_map_requires_exact_saved_native_Source')
    groups=[g for g in board.Groups() if g.ContainsItem(fp)]
    if len(groups)!=1 or fp.GetParentGroup() is None:
        raise ValueError('one_closed_Source_reference_map_required')
    left=deadline-time.monotonic()
    if left<=0:raise ValueError('native_auxiliary_strap_source_deadline')
    return maps.inspect_many(source,[(force._uid(fp),force._uid(groups[0]))],
        timeout_s=min(10.,left))[0]


def plan(board,pad_uuid,*,timeout_s=10.,allow_source_reference_maps=False):
    if (type(pad_uuid) is not str or not pad_uuid or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(allow_source_reference_maps) is not bool):
        raise ValueError('bounded_native_auxiliary_strap_source_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_auxiliary_strap_source_deadline')
    from cec_cell_row_rebuild import _source_binding
    from cec_return_escape import smd_surface_layer
    binding=_source_binding(board)
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    tracks=list(board.GetTracks())
    if len(pads)+len(tracks)>16384:raise ValueError('native_auxiliary_strap_inventory_bound')
    roots=[p for p in pads if force._uid(p)==pad_uuid]
    if len(roots)!=1:raise ValueError('unique_native_auxiliary_measurement_root_required')
    root=roots[0];fp=root.GetParentFootprint();model=roles.footprint_contract(fp)
    paired=semantics.footprint_input_contract(fp)
    auxiliary=semantics.current_auxiliary_input_contract(paired[0]) if paired else None
    reference_map=None
    if fp.GetParentGroup() is not None and allow_source_reference_maps:
        reference_map=_reference_map(board,fp,deadline=deadline)
    if (not model or not paired or not auxiliary or fp.IsLocked() or fp.IsDNP()
            or fp.GetParentGroup() is not None and reference_map is None
            or len(list(fp.Pads()))!=len(model['pins'])
            or set(p.GetNumber() for p in fp.Pads())!=set(model['pins'])
            or root.GetNumber() not in paired[1]):
        raise ValueError('complete_manufacturer_auxiliary_measurement_package_required')
    declared=[q for q in auxiliary[1] if q[1]==root.GetNumber()]
    if len(declared)!=1:raise ValueError('unique_declared_auxiliary_and_paired_input_required')
    pin=declared[0][0];others=[p for p in fp.Pads() if p.GetNumber()==pin]
    if len(others)!=1:raise ValueError('unique_native_auxiliary_input_required')
    peer=others[0];face=smd_surface_layer(root)
    if (face is None or face!=smd_surface_layer(peer) or root.GetNetCode()<=0
            or root.GetNetCode()!=peer.GetNetCode() or root.GetNetname()!=peer.GetNetname()
            or any(model['pins'].get(p.GetNumber())!='measurement' or p.HasHole()
                or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.GetParentGroup() is not None
                for p in (root,peer))
            or not 0<math.dist(tuple(root.GetPosition()),tuple(peer.GetPosition()))<=4000000):
        raise ValueError('literal_same_net_surface_auxiliary_measurement_pair_required')
    ends={tuple(root.GetPosition()),tuple(peer.GetPosition())}
    direct=[t for t in tracks if t.GetClass()=='PCB_TRACK' and t.GetNetCode()==root.GetNetCode()
        and t.GetLayer()==face and {tuple(t.GetStart()),tuple(t.GetEnd())}==ends]
    if len(direct)!=1:raise ValueError('unique_literal_native_package_strap_required')
    strap=direct[0];uid=force._uid(strap)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    dx,dy=[abs(a-b) for a,b in zip(tuple(strap.GetStart()),tuple(strap.GetEnd()))]
    if (uid in grouped or strap.GetParentGroup() is not None or strap.HasSolderMask()
            or not max(100000,int(board.GetDesignSettings().m_TrackMinWidth))<=strap.GetWidth()<=350000
            or dx and dy and dx!=dy):
        raise ValueError('bounded_ungrouped_native_measurement_strap_required')
    def poly(item,error):
        value=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(value,face,0,1000,error)
        return value
    # An external tap is not swallowed merely because its net matches. All
    # surviving native same-net contacts must be inside the two actual lands.
    material=[*pads,*tracks,*[z for z in board.Zones() if not z.GetIsRuleArea()]]
    own={uid,pad_uuid,force._uid(peer)}
    for item in material:
        tick()
        if force._uid(item) in own or item.GetNetCode()!=root.GetNetCode() or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled():raise ValueError('native_auxiliary_strap_fill_unknown')
            other=item.GetFilledPolysList(face)
        else:other=poly(item,pcbnew.ERROR_OUTSIDE)
        contact=poly(strap,pcbnew.ERROR_OUTSIDE);contact.BooleanIntersection(other)
        for p in (root,peer):contact.BooleanSubtract(poly(p,pcbnew.ERROR_INSIDE))
        if contact.OutlineCount():
            raise ValueError('native_auxiliary_strap_has_unowned_interior_contact:'+force._uid(item))
    tick()
    if binding!=_source_binding(board):raise ValueError('native_auxiliary_strap_source_changed')
    points=[list(root.GetPosition()),list(peer.GetPosition())]
    return dict(schema=1,scope='source_typed_same_net_auxiliary_measurement_strap',
        pad_uuid=pad_uuid,device=paired[0],owner=fp.GetReference(),pin=root.GetNumber(),
        net=str(root.GetNetname()),layer=int(face),width_nm=int(strap.GetWidth()),
        track_uuids=[uid],points_nm=points,boundary_uuids=[force._uid(peer)],
        source_length_mm=strap.GetLength()/1e6,source_boundary_entry_nm=points,
        source_native_binding=binding,manufacturer_source=model['source'],
        auxiliary_pin=pin,paired_input_pin=root.GetNumber(),
        source_locked_track_uuids=[uid] if strap.IsLocked() else [],
        separate_external_measurement_restoration_required=True,
        **({'source_reference_map':reference_map} if reference_map is not None else {}),
        release_authority=False,current_authority=False,kelvin_qualified=False)
