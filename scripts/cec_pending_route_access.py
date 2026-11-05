"""Read-only future entry/held-fill constraints for atomic reconstruction.

Pending endpoint disks are obligations, NOT native copper or plating. They
live in separate exact-shape indexes: native connectivity/port discovery can
never mistake a planning reservation for a material connection. Actual held
source fills use only saved filled polygons, never outlines or FEM overlays.
"""
import pcbnew
import cec_fr as fr
import cec_force_current as force


class Guard:
    def __init__(self,board,rows,*,net,clearance_nm,clearance_for,held_source=None,held_zone_uuids=()):
        self.board=board;self.held_source=held_source
        self.net=net;self.gap=clearance_nm;self.rows=[];self.held=[];self.index={}
        self.calls=0;self.refusals=0;self.via_calls=0;self.via_refusals=0
        self.layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
        if (type(rows) not in (list,tuple) or not 1<=len(rows)<=128
                or any(type(r) is not dict for r in rows)
                or type(net) is not str or not net or not callable(clearance_for)
                or type(clearance_nm) is not int or not 0<=clearance_nm<=2000000):
            raise ValueError('bounded_literal_pending_route_access_context_required')
        for r in rows:
            if (type(r) is not dict or type(r.get('uid')) is not str or not r['uid']
                    or type(r.get('net')) is not str or not r['net']
                    or type(r.get('width')) is not int or not 0<r['width']<=20000000
                    or type(r.get('layer')) is not int or r['layer'] not in self.layers
                    or any(type(r.get(k)) not in (list,tuple) or len(r[k])!=2
                        or any(type(v) is not int or abs(v)>2147483647 for v in r[k]) for k in ('start','end'))):
                raise ValueError('literal_native_pending_entry_geometry_required')
            if r['net']==net:continue
            gap=clearance_for(r['net'])
            if type(gap) is not int or not 0<=gap<=2000000:
                raise ValueError('literal_pending_entry_clearance_required')
            for key in ('start','end'):
                at=pcbnew.VECTOR2I(*r[key]);shape=pcbnew.SHAPE_SEGMENT(at,at,r['width'])
                identity=dict(kind='pending_route_entry_not_material',uuid=r['uid'],net=r['net'],
                    endpoint=key,at_nm=list(at),layer_id=r['layer'])
                self.rows.append((r['layer'],shape,shape.BBox(),identity,gap))
        if len({r['uid'] for r in rows})!=len(rows):
            raise ValueError('unique_native_pending_entry_identity_required')
        if (type(held_zone_uuids) not in (list,tuple,set,frozenset) or len(held_zone_uuids)>1024
                or any(type(u) is not str or not u for u in held_zone_uuids)
                or len(set(held_zone_uuids))!=len(held_zone_uuids)
                or held_zone_uuids and held_source is None):
            raise ValueError('literal_actual_held_source_zone_scope_required')
        if held_source is not None:
            if tuple(map(int,held_source.GetEnabledLayers().CuStack()))!=self.layers:
                raise ValueError('same_native_stack_for_held_source_fill_required')
            source_zones={force._uid(z):z for z in held_source.Zones()}
            if not set(held_zone_uuids)<=source_zones.keys():
                raise ValueError('actual_held_source_zone_identity_required')
            local_gap=fr._foreign_clearance_resolver(held_source)
            for uid in held_zone_uuids:
                z=source_zones[uid]
                if z.GetIsRuleArea():raise ValueError('held_native_copper_zone_not_rule_area_required')
                if str(z.GetNetname())==net:continue
                if not z.IsFilled():raise ValueError('actual_filled_source_priority_polygon_required')
                gap=max(clearance_for(str(z.GetNetname())),z.GetLocalClearance())
                if type(gap) is not int or not 0<=gap<=2000000:
                    raise ValueError('bounded_native_held_fill_clearance_required')
                for l in z.GetLayerSet().CuStack():
                    if not z.HasFilledPolysForLayer(l):continue
                    shape=z.GetFilledPolysList(l)
                    if not shape.OutlineCount():continue
                    actual_gap=max(gap,local_gap(z,l))
                    self.held.append((int(l),shape,shape.BBox(),dict(kind='actual_held_source_fill',
                        uuid=force._uid(z),net=str(z.GetNetname()),layer_id=int(l)),actual_gap))

    def _indexes(self,layer):
        if layer not in self.index:
            a=[(s,b,i,g) for l,s,b,i,g in self.rows if l==layer]
            z=[(s,b,i,g) for l,s,b,i,g in self.held if l==layer]
            self.index[layer]=(fr._bucket_foreign_shapes(z),fr._bucket_foreign_shapes(a))
        return self.index[layer]

    def planar(self,start,end,width_nm,layer):
        if (type(width_nm) is not int or not 0<width_nm<=40000000
                or type(layer) is not int or layer not in self.layers):
            raise ValueError('literal_pending_search_native_stroke_required')
        self.calls+=1;zones,entries=self._indexes(layer)
        ok=fr._snapshot_foreign_clear(start,end,width_nm,self.gap,zones,entries)
        if not ok:self.refusals+=1
        return bool(ok)

    def via(self,point,drill_nm,diameter_nm):
        if (type(drill_nm) is not int or type(diameter_nm) is not int
                or not 0<drill_nm<diameter_nm<=40000000):
            raise ValueError('literal_full_depth_pending_via_geometry_required')
        self.via_calls+=1
        # Uniform proposed barrels only. Actual asymmetric padstacks use
        # their own per-face receiver; never borrow a smaller internal land.
        ok=all(self.planar(point,point,diameter_nm,l) for l in self.layers)
        if not ok:self.via_refusals+=1
        return bool(ok)

    def operations(self,ops):
        for op in ops:
            if op[0]=='trk':
                if not self.planar(op[1],op[2],op[3],op[4]):return False
            elif op[0]=='via':
                if not self.via(op[1],round(op[2]*1e6),round(op[3]*1e6)):return False
            else:raise ValueError('literal_pending_search_operation_required')
        return True

    def report(self):
        return dict(schema=1,net=self.net,pending_endpoint_disks=len(self.rows),
            actual_source_filled_layer_polygons=len(self.held),planar_queries=self.calls,
            planar_refusals=self.refusals,via_queries=self.via_calls,via_refusals=self.via_refusals,
            pending_disks_are_native_copper=False,pending_disks_are_plating=False,
            board_mutated=False,source_current_or_clearance_reduced=False,release_authority=False)
