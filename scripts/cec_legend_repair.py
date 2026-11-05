"""Generic, bounded manufacturing-legend dimension repair proposals.

Dimension repair alters visible silk text/stroke dimensions only; the separate
line-art clipper retains only substrate-supported portions of body strokes.
Neither moves a part, pad, bore, outline or copper object; nor hides, deletes or
relabels text.
Growing ink can create a clearance conflict, so the caller's independent
factory/whole-board transaction must admit the result before publication.
This is not a silkscreen seater or a substitute for visual review.
"""
from __future__ import annotations

import math
import time

import cec_fab_native_geometry as native


def _items(board):
    values = list(board.GetDrawings())
    for footprint in board.GetFootprints():
        values.extend(footprint.GraphicalItems())
        values.extend((footprint.Reference(), footprint.Value()))
    return {item.m_Uuid.AsString(): item for item in values}


def repair_dimension_minima(board, rules, *, allow_locked_graphic_uuids=(),
                            max_items=32768, timeout_s=20.):
    """Plan all dimensional edits first; invalid/incomplete intake never edits.

    Unsupported filled art is reported and retained. Hidden fields and all
    non-silk layers are outside this scope. Text aspect ratios, identities,
    strings, mirror/angle/anchor/justification and graphic paths stay unchanged.
    No source file is saved; the enclosing construction owns save/admission.
    """
    report = dict(schema=1, complete=False, release_authority=False,
                  scope='visible_native_legend_dimensions_only', applied_count=0,
                  changes=[], refused=[], unsupported=[],
                  requires_fresh_clearance_and_visual_receiving=True)
    started = time.monotonic()
    try:
        floors = native.legend_floor_rules(rules)
        if (not math.isfinite(timeout_s) or timeout_s <= 0
                or not isinstance(max_items,int) or isinstance(max_items,bool)
                or max_items < 1):
            raise ValueError('invalid_legend_repair_budget')
        def tick():
            native._remaining()
            if time.monotonic()-started >= timeout_s:
                raise ValueError('legend_repair_budget_exhausted')
        tick()
        before = native.audit_legend(board,rules,max_items=max_items,
                                    timeout_s=max(.000001,timeout_s-(time.monotonic()-started)))
        report['dimension_findings_before'] = len(before['findings'])
        report['unsupported'] = before['unsupported']
        if before.get('error'):
            raise ValueError('legend_repair_intake_incomplete: '+before['error'])
        values = _items(board)
        allowed = {str(value) for value in allow_locked_graphic_uuids if value}
        targets = {}
        for finding in before['findings']:
            row = finding['item']; uid = row['uuid']
            if finding['dimension'] == 'feature_mm':
                report['refused'].append(dict(uuid=uid,reason='solid_feature_requires_shape_reconstruction'))
                continue
            targets.setdefault(uid,set()).add(finding['dimension'])
        proposals = []
        for uid, fields in sorted(targets.items()):
            tick()
            item = values[uid]
            if item.IsLocked() and uid not in allowed:
                report['refused'].append(dict(uuid=uid,reason='locked_legend_item'))
                continue
            kind = item.GetClass()
            row = dict(uuid=uid,kind=kind,layer=int(item.GetLayer()))
            if kind in ('PCB_TEXT','PCB_FIELD'):
                size = item.GetTextSize()
                if size.x <= 0 or size.y <= 0 or item.GetFont() is not None:
                    raise ValueError('unsupported_native_text_dimension')
                height = max(size.y,math.ceil(floors['silk_height']*native.MM))
                # Integer ceil preserves the original aspect ratio outward.
                width = (size.x*height+size.y-1)//size.y
                thickness = max(item.GetTextThickness(),math.ceil(floors['silk']*native.MM))
                row.update(before_size_nm=[size.x,size.y],after_size_nm=[width,height],
                    before_stroke_nm=item.GetTextThickness(),after_stroke_nm=thickness)
            elif kind=='PCB_SHAPE' and not item.IsAnyFill():
                thickness=max(item.GetWidth(),math.ceil(floors['silk']*native.MM))
                row.update(before_stroke_nm=item.GetWidth(),after_stroke_nm=thickness)
            else:
                raise ValueError('unexpected_legend_dimension_mutation')
            proposals.append((item,row))
        # All unsupported/incomplete plans are detected before any mutation.
        tick()
        import pcbnew
        for item,row in proposals:
            if row['kind'] in ('PCB_TEXT','PCB_FIELD'):
                item.SetTextSize(pcbnew.VECTOR2I(*row['after_size_nm']))
                item.SetTextThickness(row['after_stroke_nm'])
            else:
                item.SetWidth(row['after_stroke_nm'])
            report['changes'].append(row)
        report['applied_count']=len(report['changes'])
        after=native.audit_legend(board,rules,max_items=max_items,
                                 timeout_s=max(.000001,timeout_s-(time.monotonic()-started)))
        report.update(dimension_findings_after=len(after['findings']),
                      remaining_dimension_findings=after['findings'],
                      unsupported=after['unsupported'],
                      dimension_inventory_complete=after['complete'])
        if after.get('error'):
            raise ValueError('legend_repair_receiving_incomplete: '+after['error'])
        # Complete describes this correction operation, not a factory pass.
        report['complete']=True
    except Exception as exc:
        # This helper does not own a saved candidate. Undo only its declared
        # dimensional changes if receiving fails, without consulting a lease
        # that may already be exhausted. The caller still quarantines failures.
        values = _items(board) if report['changes'] else {}
        for row in reversed(report['changes']):
            item=values[row['uuid']]
            if row['kind'] in ('PCB_TEXT','PCB_FIELD'):
                import pcbnew
                item.SetTextSize(pcbnew.VECTOR2I(*row['before_size_nm']))
                item.SetTextThickness(row['before_stroke_nm'])
            else:
                item.SetWidth(row['before_stroke_nm'])
        report['rolled_back_count']=len(report['changes'])
        report['applied_count']=0
        report['error']='%s: %s' % (type(exc).__name__,exc)
    report['elapsed_s']=round(time.monotonic()-started,6)
    return report


def clip_line_art_to_material(board, *, clearance_mm, graphic_uuid_scope=None,
                              allow_locked_graphic_uuids=(), max_items=32768,
                              timeout_s=10.):
    """Propose substrate-clipped line art, never erase labels or pin markers.

    Only unfilled silk SEGMENT graphics are eligible. All retained pieces must
    pass native whole-stroke clearance against every outline and cutout. Fully
    outside graphics, text, filled art, groups and protected graphics are not
    erased. Native DRC and visual receiving remain the caller's responsibility.
    The complete finite plan is validated before changing any source object.
    """
    import pcbnew
    import cec_board_geometry as geometry
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    started=time.monotonic()
    report=dict(schema=1,complete=False,release_authority=False,applied_count=0,
        changes=[],refused=[],scope='native_substrate_clipped_silk_line_art_only',
        requires_fresh_clearance_and_visual_receiving=True)
    try:
        if (not math.isfinite(clearance_mm) or clearance_mm<=0
                or not math.isfinite(timeout_s) or timeout_s<=0
                or not isinstance(max_items,int) or isinstance(max_items,bool) or max_items<1):
            raise ValueError('invalid_silk_clip_policy_or_budget')
        def tick():
            native._remaining()
            if time.monotonic()-started>=timeout_s:
                raise ValueError('silk_clip_budget_exhausted')
        tick()
        outline=geometry.outline_material(board)
        boundaries=geometry.material_boundaries(outline)
        def points(chain):
            return [(chain.CPoint(i).x/native.MM,chain.CPoint(i).y/native.MM)
                    for i in range(chain.PointCount())]
        polygons=[Polygon(points(outline.COutline(i)),
            [points(outline.CHole(i,h)) for h in range(outline.HoleCount(i))])
            for i in range(outline.OutlineCount())]
        if any(not p.is_valid for p in polygons):
            raise ValueError('invalid_native_substrate_polygon')
        material=unary_union(polygons)
        values=_items(board)
        scope=None if graphic_uuid_scope is None else {str(u) for u in graphic_uuid_scope}
        if scope is not None and not scope<=values.keys():
            raise ValueError('silk_clip_source_scope_stale')
        grouped={i.m_Uuid.AsString() for g in board.Groups() for i in g.GetItems()}
        allowed={str(u) for u in allow_locked_graphic_uuids}
        inventory=[(u,i) for u,i in sorted(values.items()) if scope is None or u in scope]
        if len(inventory)>max_items:raise ValueError('silk_clip_inventory_bound')
        plans=[]
        for uid,item in inventory:
            tick()
            if item.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS):continue
            if (item.GetClass()!='PCB_SHAPE' or item.GetShape()!=pcbnew.SHAPE_T_SEGMENT
                    or item.IsAnyFill()):continue
            a,b=item.GetStart(),item.GetEnd()
            margin=math.ceil(clearance_mm*native.MM+item.GetWidth()/2)
            if geometry.material_leg_clear(outline,boundaries,a,b,margin):continue
            parent=item.GetParent()
            parent_locked=parent.GetClass()=='FOOTPRINT' and parent.IsLocked()
            if uid in grouped or ((item.IsLocked() or parent_locked) and uid not in allowed):
                report['refused'].append(dict(uuid=uid,reason='owned_or_locked_silk_graphic'));continue
            line=LineString([(a.x/native.MM,a.y/native.MM),(b.x/native.MM,b.y/native.MM)])
            # A small positive reserve prevents floating-to-native rounding
            # from leaving stroke ends tangent to the required factory gap.
            clipped=line.intersection(material.buffer(-(margin/native.MM+.02),join_style=2))
            parts=[]
            def collect(part):
                if part.geom_type=='LineString' and part.length>0:parts.append(part)
                elif hasattr(part,'geoms'):
                    for child in part.geoms:collect(child)
            collect(clipped)
            if not parts:
                report['refused'].append(dict(uuid=uid,reason='would_erase_entire_graphic'));continue
            pieces=[]
            refused_piece=False
            for part in parts:
                lo,hi=sorted((line.project(Point(part.coords[0])),
                              line.project(Point(part.coords[-1]))))
                ends=[line.interpolate(at) for at in (lo,hi)]
                p,q=[pcbnew.VECTOR2I(round(v.x*native.MM),round(v.y*native.MM)) for v in ends]
                if (p==q or (q-p).EuclideanNorm()<item.GetWidth()
                        or not geometry.material_leg_clear(outline,boundaries,p,q,margin)):
                    refused_piece=True;break
                pieces.append((lo,p,q))
            if refused_piece:
                # Keep the entire source graphic rather than discarding a
                # sliver, emitting an unmanufacturable fragment or aborting
                # unrelated safe proposals. This refusal remains unresolved
                # for full native DRC/visual receiving; it is not a waiver.
                report['refused'].append(dict(uuid=uid,
                    reason='cannot_retain_manufacturable_native_piece'));continue
            pieces.sort(key=lambda r:r[0])
            plans.append((item,parent,pieces,dict(uuid=uid,
                source_start_nm=[a.x,a.y],source_end_nm=[b.x,b.y],width_nm=item.GetWidth(),
                clearance_mm=clearance_mm,retained_pieces_nm=[[[p.x,p.y],[q.x,q.y]] for _,p,q in pieces])))
        tick()
        for item,parent,pieces,row in plans:
            for index,(_,p,q) in enumerate(pieces):
                piece=item if index==0 else item.Duplicate()
                piece.SetStart(p);piece.SetEnd(q)
                if index:parent.Add(piece)
            report['changes'].append(row)
        report['applied_count']=len(report['changes']);report['complete']=True
    except Exception as exc:
        report['error']='%s: %s' % (type(exc).__name__,exc)
    report['elapsed_s']=round(time.monotonic()-started,6)
    return report
