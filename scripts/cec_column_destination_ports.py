"""Plan-local destination contacts on actual whole-current planar cores.

A typed supply terminal remains the demand. A nearby same-net item is not
automatically its port: holes, sliver contacts and under-width necks split
the actual conservative native copper first. No vertical edge or barrel
rating is created here. Every saved column/current/native receiver remains
independently mandatory, and no proposal is routing or release authority.
"""
import copy
import math
import time

import pcbnew
from shapely.geometry import Point
from shapely.ops import unary_union
import cec_field_coupling as field
import cec_force_current as force
import cec_kelvin_copper_cut as cut
import cec_native_track_ports as tracks


def interleave_pairs(left,right):
    """Try a new destination port before funding another root alias."""
    if not 0<=len(left)<=8 or not 0<=len(right)<=8:
        raise ValueError('bounded_column_port_pair_domain_required')
    return [(left[i],right[rank-i])for rank in range(len(left)+len(right)-1)
        for i in range(len(left))if 0<=rank-i<len(right)]


def source_portfolio(candidates,demand_nm,*,width_nm,source_pad_port=None,max_ports=8):
    """Nearest, actual Source output, then angular breadth; hints only.

    A finite nearest-only menu can spend every origin in the same crowded
    collector shadow, even though its real regulator remains available.
    None of these choices grants clearance, current or route authority.
    """
    import cec_native_via_frontier as frontier
    if (not 0<=len(candidates)<=4096 or type(max_ports)is not int or not 1<=max_ports<=8
            or type(width_nm)is not int or width_nm<=0
            or source_pad_port is not None and source_pad_port not in candidates):
        raise ValueError('bounded_actual_source_port_domain_required')
    by_point={}
    for choice in sorted(candidates,key=lambda q:(q[2],q[0])):
        by_point.setdefault(choice[0],choice)
    ranked=frontier._rank_points(set(by_point),demand_nm,diverse=True)
    ordered=([by_point[ranked[0]]]if ranked else[])
    if source_pad_port is not None:ordered.append(source_pad_port)
    ordered.extend(by_point[p]for p in ranked)
    result=[]
    for choice in ordered:
        if any(math.dist(choice[0],q[0])<width_nm for q in result):continue
        result.append(choice)
        if len(result)==max_ports:break
    return result


def paired_launch_web(first_legs,second_legs,face):
    """Both independently legal launches can share the actual Source tap.

    Joining remote columns by folding back through the first column is not
    the only topology. A Source-rooted two-arm web has the same two actual
    surface contacts; saved whole-current and single-axis cuts still decide.
    Only new exact collinear copper is coalesced, never retained Source.
    """
    import cec_proposed_collinear_copper as union
    raw=[('trk',tuple(a),tuple(b),int(w),int(face))for a,b,w in [*first_legs,*second_legs]]
    merged,_=union.normalize(raw)
    return [(o[1],o[2],o[3])for o in merged]


class DestinationPorts:
    def __init__(self,board,material,contract,*,guard,deadline):
        self.board=board;self.material=list(material);self.guard=guard
        self.deadline=deadline;self.layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
        if (type(deadline)not in(int,float)or not math.isfinite(deadline)
                or not 1<=len(self.material)<=512):
            raise ValueError('bounded_planar_destination_context_required')
        self.floors=dict(contract['required_by_layer_nm'])
        if any(type(self.floors.get(l))is not int or self.floors[l]<=0 for l in self.layers):
            raise ValueError('positive_literal_source_current_floors_required')
        self.live={force._uid(i):i for i in self.material}
        if len(self.live)!=len(self.material)or len({i.GetNetname()for i in self.material})!=1:
            raise ValueError('one_exact_destination_material_inventory_required')
        self.epoch=self._geometry_epoch()
        self.work=cut._Work(deadline);self.cores={};self.holes=None;self.rows=[]

    def _geometry_epoch(self):
        # The common field inventory deliberately does not encode every pad
        # contour parameter. A local core cache must bind those too, for each
        # actual copper face, including pad-local rotation and offsets.
        pads=[]
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                pads.append((force._uid(p),p.GetOrientationDegrees(),
                    tuple((int(l),int(p.GetShape(l)),tuple(p.GetOffset(l)),tuple(p.GetDelta(l)),
                        p.GetRoundRectRadiusRatio(l),p.GetChamferRectRatio(l),int(p.GetChamferPositions(l)))
                        for l in p.GetLayerSet().CuStack())))
        return field._field_snapshot_inventory(self.board),tuple(sorted(pads))

    def _live(self):
        self.work.tick()
        if self._geometry_epoch()!=self.epoch:
            raise ValueError('planar_destination_source_geometry_changed')
        self.work.tick()

    def _hole_void(self):
        if self.holes is not None:return self.holes
        physical=[*(p for f in self.board.GetFootprints()for p in f.Pads()),*self.board.GetTracks()]
        if len(physical)>16384:raise ValueError('destination_physical_inventory_bound')
        holes=[]
        for item in physical:
            self.work.tick()
            if item.GetClass()=='PCB_VIA' or item.GetClass()=='PAD'and item.HasHole():
                cut._simple_drill(item,self.layers);holes.append(cut._hole(item,True,self.work))
        self.holes=unary_union(holes);return self.holes

    def _layer(self,face):
        if face in self.cores:return self.cores[face]
        import cec_ordinary_power_columns as columns
        material=[]
        for item in self.material:
            self.work.tick()
            if not item.IsOnLayer(face):continue
            if item.GetClass()not in('PAD','PCB_TRACK','PCB_VIA'):
                raise ValueError('simple_planar_destination_material_required')
            if item.GetClass()=='PAD'and(item.HasHole()or item.GetShape()not in(
                    pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                    pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)):
                raise ValueError('simple_planar_destination_land_required')
            material.append(cut._shape(item,face,False,self.work))
        lower=unary_union(material).difference(self._hole_void())
        radius=math.ceil(self.floors[face]/2)+10
        self.cores[face]=columns._verified_cores(lower,radius,self.work)
        return self.cores[face]

    def sites(self,terminal,*,toward_nm,width_nm,max_ports=8):
        self._live();uid=force._uid(terminal)
        # Resolve the real retained item from the exact Source inventory,
        # never geometry supplied by a separate same-UUID object.
        terminal=self.live.get(uid)
        if terminal is None:raise ValueError('actual_destination_source_land_required')
        faces=tuple(map(int,terminal.GetLayerSet().CuStack()))
        if (uid not in self.live or terminal.GetClass()!='PAD'or terminal.HasHole()
                or len(faces)!=1 or faces[0]not in self.layers
                or type(width_nm)is not int or width_nm<self.floors[faces[0]]
                or type(max_ports)is not int or not 1<=max_ports<=8
                or len(toward_nm)!=2 or any(type(v)is not int for v in toward_nm)):
            raise ValueError('literal_single_face_destination_demand_required')
        import cec_ordinary_power_columns as columns
        face=faces[0];at=tuple(terminal.GetPosition());cores=self._layer(face)
        radius=math.ceil(self.floors[face]/2)+10
        land=cut._shape(terminal,face,False,self.work).difference(self._hole_void())
        padcores=columns._verified_cores(land,radius,self.work)
        shared=[core for core in cores if any(core.intersection(p).area>0 for p in padcores)]
        choices=[]
        for item in self.material:
            self.work.tick();owner=force._uid(item)
            if not item.IsOnLayer(face)or not self.guard.allows_endpoint({'native_uuids':[owner]}):continue
            if item.GetClass()=='PCB_TRACK'and item.GetWidth()>=width_nm:
                points=[tuple(item.GetStart()),tuple(item.GetEnd()),
                    *tracks.sites(item,toward_nm=toward_nm,max_sites=4)]
            elif item.GetClass()=='PAD'and(not item.HasHole())and(
                    owner==uid or min(item.GetSize())>=width_nm):
                points=[tuple(item.GetPosition())]
            else:continue
            for point in points:
                if any(core.covers(Point(point))for core in shared):choices.append((point,face,owner))
        choices.sort(key=lambda q:(q[0]!=at,math.dist(q[0],toward_nm),q[2],q[0]))
        result=[]
        for choice in choices:
            # This only chooses a finite set of exact Source points. It does
            # not snap/move Source, enlarge a pad or declare nearby aliases
            # electrically or geometrically interchangeable.
            if any(math.dist(choice[0],p[0])<width_nm for p in result):continue
            result.append(choice)
            if len(result)==max_ports:break
        self.rows.append(dict(typed_demand_uuid=uid,face=face,
            current_core_components=len(shared),offered_ports=[dict(position_nm=list(q[0]),
                source_uuid=q[2])for q in result]))
        self._live();return result

    def report(self):
        return dict(scope='plan_local_planar_destination_port_hints',
            native_square_containment_checked=True,vertical_edges_credited=0,
            source_geometry_changed=False,rows=copy.deepcopy(self.rows),
            current_qualified=False,routing_admitted=False,release_authority=False,
            saved_typed_terminal_and_all_single_axis_cuts_still_required=True,no_path_proof=False)
