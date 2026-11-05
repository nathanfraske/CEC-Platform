"""Bounded, read-only native fabrication witnesses, independent of net names.

KiCad 10.0.5's hole-to-hole provider omits non-round pad drills.  This audit
uses each supported native through drill's actual capsule, including rotated
slots, and tests every physical pair.  It is not a connectivity certificate.
Unsupported geometry and unfinished inventories are explicitly incomplete.
"""
import hashlib
import math
import os
from pathlib import Path
import re
import time

MM = 1_000_000


def _remaining():
    from cec_operation_budget import available_timeout
    if available_timeout(1., os.environ, reserve_s=0) <= 0:
        raise ValueError("enclosing_fab_geometry_budget_exhausted")


def hole_rule_floor(board_path):
    """Conservatively retain all numeric source DRU hole-spacing minima.

    Conditions cannot lower a factory floor.  Expressions cannot silently
    become zero; they require a stronger evaluator before this can certify.
    """
    from cec_copper_echo import _parse
    path = Path(board_path).with_suffix('.kicad_dru')
    if not path.exists():
        return 0., dict(present=False, sha256=None)
    payload = path.read_bytes()
    if len(payload) > 262144:
        raise ValueError('hole_rule_inventory_budget_exhausted')
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|#[^\r\n]*|[()]|[^\s()#]+',
                        payload.decode('utf-8'))
    rows = _parse(['(', 'rules', *[t for t in tokens if not t.startswith('#')], ')'])
    pending, count, floor = [rows], 0, 0.
    while pending:
        row = pending.pop()
        count += 1
        if count > 4096:
            raise ValueError('hole_rule_inventory_budget_exhausted')
        if len(row) > 1 and row[:2] == ['constraint', 'hole_to_hole']:
            for value in row[2:]:
                if not isinstance(value, list) or not value or value[0] != 'min':
                    continue
                match = re.fullmatch(r'(\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(mm|mil|in)',
                    value[1]) if len(value) == 2 and isinstance(value[1], str) else None
                if not match:
                    raise ValueError('unsupported_hole_rule_minimum')
                number = float(value[1][:-len(match[2])]) * {'mm':1., 'mil':.0254, 'in':25.4}[match[2]]
                if not math.isfinite(number) or number < 0:
                    raise ValueError('invalid_hole_rule_minimum')
                floor = max(floor, number)
        pending.extend(value for value in row if isinstance(value, list))
    return floor, dict(present=True, sha256=hashlib.sha256(payload).hexdigest(),
                      method='maximum_numeric_minimum_across_all_conditions')


def _identity(item):
    pos = item.GetPosition()
    row = dict(uuid=item.m_Uuid.AsString(), kind=item.GetClass(),
               at_mm=[pos.x/MM, pos.y/MM])
    if item.GetClass() in ('PAD', 'PCB_VIA'):
        row['net'] = item.GetNetname()
    if item.GetClass() == 'PAD':
        row.update(reference=item.GetParentFootprint().GetReference(),
                   pad=item.GetNumber())
    return row


def audit_holes(board, rules, *, board_path=None, max_items=8192,
                max_pairs=2_000_000, max_findings=4096, timeout_s=30.):
    """Every supported native drill pair, including same-net and NPTH pairs.

    PTH/NPTH and via/pad factory floors differ from via/via.  Capped/filled
    via-to-pad distance uses the published strict greater-than floor.  Board
    and source DRU minima only strengthen these floors.  No local owner rule
    or drill-net identity provides a manufacturing exception.
    """
    import pcbnew
    from cec_kelvin_copper_cut import _simple_drill
    report = dict(schema=1, origin='independent_native_drill_capsules', complete=False,
                  release_authority=False, inventory=[], findings=[], unsupported=[],
                  examined_pairs=0, total_pairs=None, same_net_pairs=0)
    started = time.monotonic()
    try:
        if (not math.isfinite(timeout_s) or timeout_s <= 0
                or any(not isinstance(value, int) or isinstance(value, bool)
                       for value in (max_items, max_pairs, max_findings))
                or max_items < 1 or max_pairs < 0 or max_findings < 1):
            raise ValueError('invalid_hole_audit_budget')
        def budget():
            _remaining()
            if time.monotonic()-started >= timeout_s:
                raise ValueError('native_hole_audit_budget_exhausted')
        budget()
        settings = board.GetDesignSettings()
        dru_floor, dru = hole_rule_floor(board_path) if board_path else (0., dict(present=False))
        floors = dict(board_mm=settings.m_HoleToHoleMin/MM, source_dru_mm=dru_floor,
                      process_mm=float(rules['h2h']),
                      factory_via_via_mm=float(rules['h2h_via_via']),
                      factory_pad_pad_mm=float(rules['h2h_pad_pad']),
                      factory_via_pad_mm=float(rules['h2h_via_pad']))
        if any(not math.isfinite(value) or value < 0 for value in floors.values()):
            raise ValueError('invalid_hole_spacing_authority')
        report.update(floors=floors, source_dru=dru,
                      default_vias_filled=bool(settings.m_FillVias),
                      default_vias_capped=bool(settings.m_CapVias))
        copper = list(board.GetEnabledLayers().CuStack())
        footprints, tracks = list(board.GetFootprints()), list(board.GetTracks())
        pads = [pad for fp in footprints for pad in fp.Pads()]
        drilled = [p for p in pads if p.HasHole()] + [t for t in tracks if t.GetClass() == 'PCB_VIA']
        report['drill_count'] = len(drilled)
        if len(drilled) > max_items:
            raise ValueError('native_hole_inventory_budget_exhausted')
        shapes, seen = [], set()
        for item in drilled:
            budget()
            row = _identity(item)
            report['inventory'].append(row)
            try:
                if not row['uuid'] or row['uuid'] in seen:
                    raise ValueError('ambiguous_native_drill_identity')
                seen.add(row['uuid'])
                if not _simple_drill(item, copper):
                    raise ValueError('unsupported_native_drill')
                if item.GetPrimaryDrillShape() not in (
                        pcbnew.PAD_DRILL_SHAPE_CIRCLE, pcbnew.PAD_DRILL_SHAPE_OBLONG):
                    raise ValueError('unsupported_primary_drill_shape')
                shape = item.GetEffectiveHoleShape()
                if shape.Type() != pcbnew.SH_SEGMENT or shape.GetWidth() <= 0:
                    raise ValueError('unsupported_native_drill_capsule')
                segment = shape.GetSeg()
                row.update(capsule_start_nm=[segment.A.x, segment.A.y],
                           capsule_end_nm=[segment.B.x, segment.B.y],
                           capsule_width_nm=shape.GetWidth(),
                           plated=(item.GetClass() == 'PCB_VIA' or
                                   item.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
                # FROM_BOARD=0, ON=1, OFF=2 in KiCad's optional-bool modes.
                # Native effective flags resolve inherited board defaults.
                row['filled_or_capped'] = bool(item.GetPrimaryDrillFilledFlag()
                    or item.GetPrimaryDrillCappedFlag()
                    or (item.GetClass() == 'PCB_VIA' and (
                        (item.GetFillingMode() == 0 and settings.m_FillVias)
                        or (item.GetCappingMode() == 0 and settings.m_CapVias))))
                shapes.append((row, shape))
            except Exception as exc:
                report['unsupported'].append(dict(item=row, reason=str(exc)))
        report['total_pairs'] = len(drilled)*(len(drilled)-1)//2
        if report['total_pairs'] > max_pairs:
            raise ValueError('native_hole_pair_budget_exhausted')
        common = max(floors['board_mm'], floors['source_dru_mm'], floors['process_mm'])
        for index, (left, a) in enumerate(shapes):
            for right, b in shapes[index+1:]:
                if report['examined_pairs'] % 256 == 0:
                    budget()
                report['examined_pairs'] += 1
                if left['net'] == right['net']:
                    report['same_net_pairs'] += 1
                kinds = {left['kind'], right['kind']}
                family = ('via_via' if kinds == {'PCB_VIA'} else
                          'pad_pad' if kinds == {'PAD'} else 'via_pad')
                factory = floors['factory_'+family+'_mm']
                floor = max(common, factory)
                strict = (family == 'via_pad' and floor == factory
                          and (left['filled_or_capped'] or right['filled_or_capped']))
                threshold = int(round(floor*MM)) + int(strict)
                if a.Collide(b, threshold):
                    if len(report['findings']) >= max_findings:
                        raise ValueError('native_hole_finding_report_budget_exhausted')
                    # Reporting distance only: the pass/fail witness is the
                    # native capsule collision above, not this rounded value.
                    gap = (a.GetSeg().Distance(b.GetSeg())
                           - (a.GetWidth()+b.GetWidth())/2)/MM
                    report['findings'].append(dict(type='factory_native_hole_spacing',
                        origin=report['origin'], left=left, right=right, pair_class=family,
                        signed_gap_mm=gap, floor_mm=floor,
                        comparator='>' if strict else '>=',
                        description='Native physical drill gap %.6f mm requires %s %.6f mm'
                            % (gap, '>' if strict else '>=', floor)))
        budget()
        report['complete'] = (not report['unsupported']
                              and report['examined_pairs'] == report['total_pairs'])
    except Exception as exc:
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
    report['elapsed_s'] = round(time.monotonic()-started, 6)
    return report


def legend_floor_rules(rules):
    """Validate all legend floors even when the visible inventory is empty."""
    result = {}
    for key in ('silk', 'silk_height'):
        value = rules[key]
        if isinstance(value, bool):
            raise ValueError('invalid_legend_factory_floor')
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('invalid_legend_factory_floor')
        result[key] = value
    return result


def _solid_legend_feature(item):
    """A lower bound for native filled disks/rectangles, not arbitrary art.

    Ignore a positive border stroke rather than crediting it as extra material.
    Circle radii and rectangle corners come from the actual native object.
    Integer square roots round edge lengths inward after native rotation.
    Rounded rectangles additionally subtract both corner radii, retaining only
    their guaranteed interior core. Polygons, hatches and custom fills remain
    unknown; an overall bounding box does not prove their minimum feature.
    """
    import pcbnew
    if not item.IsSolidFill() or item.GetWidth() < 0:
        raise ValueError('filled_legend_minimum_feature_not_certified')
    if item.GetShape() == pcbnew.SHAPE_T_CIRCLE:
        radius = item.GetRadius()
        if not isinstance(radius, int) or radius <= 0:
            raise ValueError('degenerate_native_solid_legend')
        return dict(feature_mm=2*radius/MM,
                    feature_witness='native_solid_circle_inscribed_diameter',
                    radius_nm=radius, border_stroke_not_credited=True)
    if item.GetShape() == pcbnew.SHAPE_T_RECT:
        corners = list(item.GetRectCorners())
        if len(corners) != 4:
            raise ValueError('unsupported_native_rectangle_corners')
        points = [(int(p.x), int(p.y)) for p in corners]
        edges = [math.isqrt((a[0]-b[0])**2+(a[1]-b[1])**2)
                 for a,b in zip(points, points[1:]+points[:1])]
        radius = item.GetCornerRadius()
        if not isinstance(radius, int) or radius < 0:
            raise ValueError('unsupported_native_rectangle_corner_radius')
        feature = min(edges)-2*radius
        if feature <= 0:
            raise ValueError('degenerate_native_solid_legend')
        return dict(feature_mm=feature/MM,
                    feature_witness='native_solid_rectangle_interior_core',
                    corners_nm=[list(p) for p in points], corner_radius_nm=radius,
                    border_stroke_not_credited=True)
    raise ValueError('filled_legend_minimum_feature_not_certified')


def audit_legend(board, rules, *, max_items=32768, timeout_s=20.):
    """Native visible silk dimensions; unsupported fill/font geometry blocks.

    Collision/edge/pad clearance is delegated to the separate full-severity
    native DRC.  This witness does not claim exhaustiveness for that provider.
    """
    import pcbnew
    report = dict(schema=1, origin='independent_native_legend_dimensions', complete=False,
                  release_authority=False, inventory=[], findings=[], unsupported=[])
    started = time.monotonic()
    try:
        if (not math.isfinite(timeout_s) or timeout_s <= 0
                or not isinstance(max_items, int) or isinstance(max_items, bool)
                or max_items < 1):
            raise ValueError('invalid_legend_audit_budget')
        floors = legend_floor_rules(rules)
        footprints = list(board.GetFootprints())
        graphics = list(board.GetDrawings())
        for fp in footprints:
            graphics.extend(fp.GraphicalItems())
            graphics.extend((fp.Reference(), fp.Value()))
        seen = set()
        for item in graphics:
            if item.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            if hasattr(item, 'IsVisible') and not item.IsVisible():
                continue
            _remaining()
            if time.monotonic()-started >= timeout_s or len(report['inventory']) >= max_items:
                raise ValueError('native_legend_audit_budget_exhausted')
            row = _identity(item)
            # Native footprint fields can also occur in GraphicalItems().
            if row['uuid'] in seen:
                continue
            seen.add(row['uuid'])
            row['layer'] = board.GetLayerName(item.GetLayer())
            report['inventory'].append(row)
            kind = item.GetClass()
            try:
                if kind in ('PCB_TEXT', 'PCB_FIELD'):
                    text = item.GetShownText(False)
                    row['text'] = text
                    if not text:
                        continue
                    if item.GetFont() is not None:
                        raise ValueError('outline_or_custom_font_stroke_not_certified')
                    row.update(height_mm=item.GetTextSize().y/MM,
                               stroke_mm=item.GetTextThickness()/MM)
                    minima = {'height_mm':floors['silk_height'], 'stroke_mm':floors['silk']}
                elif kind == 'PCB_SHAPE':
                    if item.IsAnyFill():
                        row.update(_solid_legend_feature(item))
                        minima = {'feature_mm':floors['silk']}
                    elif item.GetShape() not in (pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_ARC,
                            pcbnew.SHAPE_T_CIRCLE, pcbnew.SHAPE_T_RECT, pcbnew.SHAPE_T_POLY):
                        raise ValueError('unsupported_legend_shape')
                    else:
                        row['stroke_mm'] = item.GetWidth()/MM
                        minima = {'stroke_mm':floors['silk']}
                else:
                    raise ValueError('unsupported_legend_item')
                for field, floor in minima.items():
                    if not math.isfinite(floor) or floor <= 0:
                        raise ValueError('invalid_legend_factory_floor')
                    if row[field] + 1e-9 < floor:
                        report['findings'].append(dict(type='factory_native_legend_dimension',
                            origin=report['origin'], item=row, dimension=field,
                            actual_mm=row[field], floor_mm=floor,
                            description='Visible native silk %s %.6f mm is below %.6f mm'
                                % (field, row[field], floor)))
            except Exception as exc:
                report['unsupported'].append(dict(item=row, reason=str(exc)))
        report['complete'] = not report['unsupported']
    except Exception as exc:
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
    report['elapsed_s'] = round(time.monotonic()-started, 6)
    return report
