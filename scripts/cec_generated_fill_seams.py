"""Coalesce compatible generated microfill zones without changing their union.

Independent exact fill, source/sink and DRC admission remain mandatory. This
changes representation, not the planned power territory or its width budget.
"""


def _fill_signature(zone):
    return (zone.GetNetname(), tuple(zone.GetLayerSet().CuStack()),
            zone.GetFillMode(), zone.GetLocalClearance(), zone.GetPadConnection(),
            zone.GetMinThickness(), zone.GetThermalReliefGap(),
            zone.GetThermalReliefSpokeWidth(), zone.GetIslandRemovalMode(), zone.GetMinIslandArea(),
            zone.GetCornerSmoothingType(), zone.GetCornerRadius())


def coalesce(board, *, managed_nets):
    """Absorb owned orthofill patches into compatible, touching owned parents.

    Never touch authored/locked zones, layer stacks, unlike fill settings, or
    patches whose priority reduction could change a foreign zone's territory.
    A disconnected union stays separate. Native refill handles real clearances.
    """
    import cec_fr
    import pcbnew
    zones = list(board.Zones())
    managed = set(managed_nets)
    parents = [z for z in zones if not z.GetIsRuleArea() and not z.IsLocked()
               and z.GetFillMode() == pcbnew.ZONE_FILL_MODE_POLYGONS
               and z.GetNetname() in managed
               # Use the materializer's ownership vocabulary. Frozen
               # pour-first, slab and over/under parents need the same seam
               # treatment as a direct pour; representation is not policy.
               and (z.GetZoneName() or '').startswith(cec_fr._GENERATED_ZONE_PREFIXES)
               and not (z.GetZoneName() or '').startswith('orthofill:')
               and len(tuple(z.GetLayerSet().CuStack())) == 1]
    patches = sorted([z for z in zones if not z.GetIsRuleArea() and not z.IsLocked()
                      and z.GetNetname() in managed
                      and (z.GetZoneName() or '').startswith('orthofill:')],
                     key=lambda z: (z.GetZoneName(), z.m_Uuid.AsString()))
    removed = []; report = dict(schema=1, merged=[], rejected=[])
    for patch in patches:
        shape = cec_fr._zone_outline_geometry(patch)
        signature = _fill_signature(patch)
        choices = []
        for parent in parents:
            if _fill_signature(parent) != signature:
                continue
            base = cec_fr._zone_outline_geometry(parent)
            if base.intersection(shape).length <= 1e-6:
                continue
            merged = base.union(shape)
            if merged.geom_type != 'Polygon' or not merged.is_valid:
                continue
            layer = signature[1][0]
            lower = parent.GetAssignedPriority(); upper = patch.GetAssignedPriority()
            if lower > upper:
                continue
            # A lower-priority parent must not surrender a patch's previous
            # precedence over intervening foreign copper. No priority waiver.
            if any(z.GetNetname() != patch.GetNetname() and not z.GetIsRuleArea()
                   and z.IsOnLayer(layer) and lower <= z.GetAssignedPriority() <= upper
                   and cec_fr._zone_outline_geometry(z).intersection(shape).area > 1e-12
                   for z in zones):
                continue
            choices.append((-base.intersection(shape).length,
                            parent.GetZoneName(), parent.m_Uuid.AsString(), parent, merged))
        if not choices:
            report['rejected'].append(patch.GetZoneName())
            continue
        _, _, _, parent, merged = min(choices, key=lambda row: row[:3])
        original = cec_fr._zone_outline_geometry(parent)
        if not cec_fr._replace_zone_outline(parent, merged):
            raise RuntimeError('generated fill seam produced an invalid native outline')
        actual = cec_fr._zone_outline_geometry(parent)
        if actual.symmetric_difference(merged).area > 1e-9:
            cec_fr._replace_zone_outline(parent, original)
            raise RuntimeError('generated fill seam changed the intended copper union')
        report['merged'].append(dict(patch=patch.GetZoneName(),
            parent=parent.GetZoneName(), layer=pcbnew.LayerName(layer),
            net=patch.GetNetname(), patch_bounds_mm=list(shape.bounds),
            outline_union_changed=False))
        removed.append(patch)
    # Native deletion last: no traversal of a deleted SWIG zone proxy.
    for patch in removed:
        board.Delete(patch)
    report['merged_count'] = len(removed)
    return report
