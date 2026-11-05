"""Actual circular through-via lands for all-face clearance, not capacity.

Only complete native normal/front-inner-back stacks are accepted. Every
enabled face retains a legal land and the full-depth drilled bore. A smaller
unused inner land grants no current sharing, barrel rating or layer waiver.
"""
import pcbnew


def inspect(board,via,*,at,maximum_diameter_nm,drill_nm,net_code,clearance_nm):
    faces=list(board.GetEnabledLayers().CuStack());settings=board.GetDesignSettings()
    if (via.GetClass()!='PCB_VIA' or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or tuple(via.GetPosition())!=tuple(at) or net_code is None or net_code<=0
            or via.GetNetCode()!=net_code or drill_nm is None or via.GetDrillValue()!=int(drill_nm)
            or set(via.GetLayerSet().CuStack())!=set(faces)
            or via.Padstack().Mode() not in (pcbnew.PADSTACK.MODE_NORMAL,pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)):
        raise ValueError('exact_complete_native_circular_through_padstack_required')
    widths={int(layer):int(via.GetWidth(layer)) for layer in faces}
    hole_gap=max(0,int(settings.m_HoleClearance)-int(clearance_nm))
    minimum_annulus=max(int(settings.m_ViasMinAnnularWidth),hole_gap)
    if (not widths or max(widths.values())!=int(maximum_diameter_nm)
            or int(drill_nm)<int(settings.m_MinThroughDrill)
            or any(width<int(settings.m_ViasMinSize) or width<=int(drill_nm)
                or width-int(drill_nm)<2*minimum_annulus for width in widths.values())):
        raise ValueError('every_native_via_land_and_drilled_bore_must_meet_board_floors')
    for layer,width in widths.items():
        shape=via.GetEffectiveShape(layer);box=shape.BBox();centre=box.GetCenter()
        if (shape.Type()!=pcbnew.SH_CIRCLE or abs(box.GetWidth()-width)>1
                or abs(box.GetHeight()-width)>1 or math_distance_squared(tuple(centre),tuple(at))>2):
            raise ValueError('native_via_effective_shape_differs_from_declared_circle')
    return widths


def math_distance_squared(first,last):
    return sum((a-b)**2 for a,b in zip(first,last))
