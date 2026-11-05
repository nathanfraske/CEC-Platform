"""Exact retained copper endpoint access, never guessed cross-layer access."""


def endpoint_layers(board, point_nm, net_code):
    import pcbnew
    import cec_fr as fr
    if (not isinstance(point_nm,(list,tuple)) or len(point_nm)!=2
            or any(type(v) is not int for v in point_nm)
            or type(net_code) is not int or net_code<=0):
        raise ValueError('exact_native_endpoint_identity_required')
    point=tuple(point_nm)
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    result=set()
    for item in board.GetTracks():
        if int(item.GetNetCode())!=net_code:
            continue
        if item.GetClass()=='PCB_TRACK' and point in (tuple(item.GetStart()),tuple(item.GetEnd())):
            result.add(int(item.GetLayer()))
        elif item.GetClass()=='PCB_VIA' and point==tuple(item.GetPosition()):
            result.update(map(int,fr._through_barrel_layers(board,item)))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if (int(pad.GetNetCode())==net_code and point==tuple(pad.GetPosition())
                    and pad.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)):
                if pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH:
                    result.update(map(int,fr._pth_barrel_layers(board,pad)))
                else:
                    faces=set(map(int,pad.GetLayerSet().CuStack()))&{int(pcbnew.F_Cu),int(pcbnew.B_Cu)}
                    if len(faces)==1 and len(list(pad.GetLayerSet().CuStack()))==1:
                        result.update(faces)
    return result&enabled
