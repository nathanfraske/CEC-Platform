"""Guard reconstruction-only progress independently of placement search.

An improved constructor report is a proposal, never routing or release
authority. No board, component, net-name, or coordinate exceptions live here.
"""
import hashlib
import json


def fixed_domain(path, *, include_poses=True):
    """Bind the immutable native domain, optionally excluding rigid XY poses.

    Movable proposals still bind relative pad geometry, faces, population and
    complete contours. The caller must separately prove every emitted pose
    matches the proposed candidate; this grants no unowned copper mutation.
    """
    import pcbnew
    import cec_board_geometry
    board = pcbnew.LoadBoard(str(path))
    outline = cec_board_geometry.outline_material(board)

    def xy(point):
        return [int(point.x), int(point.y)]

    def contour(chain):
        points = [tuple(xy(chain.CPoint(i))) for i in range(chain.PointCount())]
        # KiCad may choose another starting vertex or winding on serialization.
        return min(tuple(p[i:] + p[:i]) for p in (points, points[::-1])
                   for i in range(len(p)))

    components = []
    for fp in board.GetFootprints():
        pads = [dict(number=p.GetNumber(), net=p.GetNetname(),
                     at=xy(p.GetPosition() if include_poses else p.GetFPRelativePosition()),
                     size=xy(p.GetSize()),
                     drill=xy(p.GetDrillSize()), shape=int(p.GetShape()),
                     attribute=int(p.GetAttribute()),
                     angle=round(float(p.GetOrientationDegrees() -
                         (0 if include_poses else fp.GetOrientationDegrees())) % 360, 6),
                     layers=[int(layer) for layer in p.GetLayerSet().Seq()])
                for p in fp.Pads()]
        components.append(dict(ref=fp.GetReference(),
            footprint=str(fp.GetFPID().GetLibItemName()),
            at=xy(fp.GetPosition()) if include_poses else None, layer=int(fp.GetLayer()),
            angle=round(float(fp.GetOrientationDegrees()) % 360, 6) if include_poses else None,
            pads=sorted(pads, key=lambda p: json.dumps(p, sort_keys=True))))
    boundaries = sorted((contour(outline.COutline(i)),
        sorted(contour(outline.CHole(i, h)) for h in range(outline.HoleCount(i))))
        for i in range(outline.OutlineCount()))
    payload = dict(components=sorted(components, key=lambda c: c['ref']),
                   boundaries=boundaries, copper_layers=board.GetCopperLayerCount())
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def admit(before, after, *, before_score, after_score,
          fixed_domain_unchanged, prefix_ok, source_ok, frozen_ok,
          require_blocking_progress=True):
    """Require strict craft progress AND independent native non-regression."""
    import cec_synth_pipeline as synth
    import cec_placement_geometry as geometry
    import cec_stage_admission
    old_key = synth.placement_craft_blocking_key(before)
    new_key = synth.placement_craft_blocking_key(after)
    native = cec_stage_admission.evaluate(before_score, after_score)
    reasons = []
    required_score = ('drc', 'unconnected', 'unconn_nets', 'structural_drc_identities',
                      'kelvin_ok', 'diffpair_ok')
    if any(key not in row for row in (before_score, after_score) for key in required_score):
        reasons.append('native_score_evidence_unavailable')
    for label, ok in (('fixed_domain_changed', fixed_domain_unchanged),
                      ('protected_copper_changed', prefix_ok),
                      ('source_intake_failed', source_ok),
                      ('frozen_authority_changed', frozen_ok)):
        if not ok:
            reasons.append(label)
    if before.get('errors') or after.get('errors'):
        reasons.append('craft_evidence_error')
    if any(geometry.assembly_pairs(row.get('native_geometry')) is None
           for row in (before, after)):
        reasons.append('native_placement_evidence_unavailable')
    if geometry.craft_conflict_keys(after.get('native_geometry')) - \
            geometry.craft_conflict_keys(before.get('native_geometry')):
        reasons.append('new_native_placement_conflict')
    progress = (new_key < old_key if require_blocking_progress else
                synth.placement_craft_key(after) < synth.placement_craft_key(before))
    if (not progress or any(new > old for old, new in zip(old_key, new_key))):
        reasons.append('no_pareto_craft_improvement')
    if not native['accepted']:
        reasons.append('native_copper_regression')
    for key in ('route_blocking', 'route_non_octilinear'):
        if (key not in before_score or key not in after_score
                or after_score[key] > before_score[key]):
            reasons.append(key + '_regressed_or_unavailable')
    if (before_score.get('foreign_status') == 'error'
            or after_score.get('foreign_status') == 'error'
            or 'foreign_blocking' not in before_score
            or 'foreign_blocking' not in after_score
            or after_score['foreign_blocking'] > before_score['foreign_blocking']):
        reasons.append('foreign_pour_regressed_or_unavailable')
    return dict(schema=1, accepted=not reasons, reasons=reasons,
                before_key=list(old_key), after_key=list(new_key),
                native_admission=native, fixed_domain_unchanged=fixed_domain_unchanged,
                release_authority=False, routing_admitted=False)
