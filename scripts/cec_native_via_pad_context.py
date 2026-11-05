"""Actual per-face pad exclusions for an explicit native through padstack.

An enlarged inner land is not surface copper. The real surface land must
still be fully contained by one same-net SMD under the board's unchanged
POFV profile. Every enabled face is checked; THT/NPTH, foreign, multiple-face
and unprovable pad overlaps are refused. This is geometry, not current or
barrel qualification, and does not alter the legacy uniform-via path.
"""
import pcbnew
import cec_fab_profile as fab
import cec_native_via_land_context as native


def conflicts(board, via, *, at, maximum_diameter_nm, drill_nm, net_code, clearance_nm):
    widths = native.inspect(board, via, at=at, maximum_diameter_nm=maximum_diameter_nm,
        drill_nm=drill_nm, net_code=net_code, clearance_nm=clearance_nm)
    enabled = set(widths)
    pads = [(fp, pad) for fp in board.GetFootprints() for pad in fp.Pads()]
    if len(pads) > 16384:
        raise ValueError('native_layered_via_pad_inventory_bound')
    allowed = []
    for fp, pad in pads:
        faces = tuple(map(int, pad.GetLayerSet().CuStack()))
        hits = []
        for layer in faces:
            if layer in enabled and pad.GetEffectiveShape(layer).Collide(at, widths[layer] // 2):
                hits.append(layer)
        if not hits:
            continue
        unique_surface = (len(faces) == 1 and faces[0] in (pcbnew.F_Cu, pcbnew.B_Cu)
            and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD)
        for layer in hits:
            ok, why = fab.via_pad_decision(board, pad, at, widths[layer], drill_nm, net_code)
            record = dict(ref=fp.GetReference(), pad=pad.GetNumber(), net=pad.GetNetname(),
                layer=board.GetLayerName(layer), native_diameter_nm=widths[layer], reason=why)
            if not unique_surface or not ok:
                if not unique_surface:
                    record['reason'] = 'native layered POFV requires one actual surface SMD face'
                return pad, allowed + [record]
            allowed.append(record)
    return None, allowed
