"""Native permission areas shared by proposal and copper-construction guards.

Keepouts are permission- and layer-specific, never net-exempt. This uses
KiCad's polygon collision, including concavities/holes, not a bounding box.
Caller-owned caches are valid only while board/footprint geometry is unchanged.
"""


def areas(board,permission,*,cache=None):
    flags={'vias':'GetDoNotAllowVias','tracks':'GetDoNotAllowTracks',
           'zone_fills':'GetDoNotAllowZoneFills', 'pads':'GetDoNotAllowPads',
           'footprints':'GetDoNotAllowFootprints'}
    if permission not in flags:raise ValueError('unsupported native rule-area permission')
    key=('native_rule_areas',permission)
    if cache is not None and key in cache:return cache[key]
    enabled=(set(board.GetEnabledLayers().CuStack()) if hasattr(board,'GetEnabledLayers') else None)
    candidates=list(getattr(board,'Zones',lambda:())())
    for fp in board.GetFootprints():candidates.extend(getattr(fp,'Zones',lambda:())())
    if len(candidates)>4096:raise ValueError('native rule-area inventory bound')
    rows=[];seen={}
    for zone in candidates:
        uid=zone.m_Uuid.AsString()
        layers=set(zone.GetLayerSet().CuStack())
        if enabled is not None:layers &= enabled
        if not layers or not zone.GetIsRuleArea() or not getattr(zone,flags[permission])():continue
        native=zone.Outline()
        if not uid or native.OutlineCount()<=0 or native.Area()<=0:
            raise ValueError('native rule-area geometry unavailable')
        signature=(native.Format(),tuple(sorted(layers)))
        if uid in seen:
            if seen[uid]!=signature:raise ValueError('ambiguous native rule-area identity')
            continue
        seen[uid]=signature
        rows.append(dict(zone=zone,shape=native,layers=tuple(sorted(layers)),
            identity=dict(kind='native_rule_area',uuid=uid,name=zone.GetZoneName(),
                layers=[board.GetLayerName(layer) for layer in sorted(layers)])))
    if cache is not None:cache[key]=rows
    return rows


def optical_areas(board, layer):
    """Native pad/body permissions relevant to an exposed assembly mark.

    Track- or fill-only keepouts are not pad prohibitions. Footprint-local
    areas, polygon holes and concavities retain their native geometry.
    """
    rows = {}
    for permission in ('pads', 'footprints'):
        for row in areas(board, permission):
            if layer in row['layers']:
                rows[row['identity']['uuid']] = row
    return list(rows.values())


def track_conflict(board,start,end,width_nm,layer,*,cache=None):
    """Actual trace capsule versus native permission boundary, without a gap.

    A keepout is not foreign copper: do not add a netclass clearance to its
    boundary. It is never exempt merely because its net code is zero or own.
    """
    import pcbnew
    if type(width_nm) is not int or width_nm<=0:raise ValueError('invalid track width')
    shape=pcbnew.SHAPE_SEGMENT(start,end,width_nm)
    for row in areas(board,'tracks',cache=cache):
        if layer in row['layers'] and row['shape'].Collide(shape,0):
            return dict(row['identity'])
    return None


def via_areas(board, *, cache=None):
    return areas(board,'vias',cache=cache)


def pour_obstacles(board,layers,*,guard_mm=0.0):
    """Same permission boundary for exact territory and raster proposals."""
    import math
    import cec_fr
    if not math.isfinite(guard_mm) or guard_mm<0:raise ValueError('invalid rule-area guard')
    selected=set(layers);result={layer:[] for layer in layers}
    for row in areas(board,'zone_fills'):
        geometry=cec_fr._zone_outline_geometry(row['zone'])
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError('invalid native zone-fill keepout geometry')
        if guard_mm:geometry=geometry.buffer(guard_mm,join_style=2)
        for layer in selected & set(row['identity']['layers']):
            result[layer].append(dict(geometry=geometry,kind='native_rule_area',
                owner=row['identity']['uuid'],detail=row['identity']['name'],net=''))
    return result


def via_conflict(board,at,diameter_nm,*,cache=None):
    import pcbnew
    if diameter_nm<=0:raise ValueError('invalid via diameter')
    shape=pcbnew.SHAPE_CIRCLE(at,int(diameter_nm)//2)
    for row in via_areas(board,cache=cache):
        # No clearance is invented for a rule-area boundary; the physical
        # via land itself must not overlap. Native DRC remains the final gate.
        if row['shape'].Collide(shape,0):return dict(row['identity'])
    return None
