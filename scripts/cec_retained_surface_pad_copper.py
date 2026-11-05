"""Exact retained SMD-metal envelope portals; no role or new Cu authority.

A straight capsule is its central rectangle plus two endpoint disks. Its
rectangle must be inside a conservative native solid SMD-land polygon; each
disk must be inside that land or an unchanged full-width track kernel. Hole
voids are identical on both sides of this set-inclusion comparison, never
counted as copper or new barrel/ampacity authority. Saved physical partitions
and current/field/DRC/return checks still decide any caller's transaction.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_native_track_ports as ports
import cec_fr as fr


class SourcePads:
    def __init__(self,board,net,face,width,excluded,deadline):
        if (type(net) is not str or not net or type(face) is not int or not board.IsLayerEnabled(face)
                or type(width) is not int or not 0<width<=10000000):
            raise ValueError('explicit_native_surface_pad_copper_context_required')
        self.board,self.net,self.face,self.width,self.deadline=board,net,face,width,deadline
        self.tracks=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net
            and int(t.GetLayer())==face and t.GetWidth()>=width and force._uid(t) not in excluded]
        self.pads=[p for f in board.GetFootprints() if not f.IsDNP() for p in f.Pads()
            if p.GetNetname()==net and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
            and tuple(p.GetLayerSet().CuStack())==(face,) and p.GetShape() in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT)
            and min(p.GetSize().x,p.GetSize().y)>0]
        if len(self.pads)+len(self.tracks)>16384:raise ValueError('retained_native_pad_inventory_bound')
        self.polys={};self.disks={};self.rectangles={};self.kernels={};self.prefixes={}

    def tick(self):
        if time.monotonic()>=self.deadline:raise ValueError('retained_native_pad_copper_deadline')

    def polygon(self,pad):
        self.tick();uid=force._uid(pad)
        if uid not in self.polys:
            shape=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(shape,self.face,0,1,pcbnew.ERROR_INSIDE)
            if shape.OutlineCount()!=1 or shape.HoleCount(0):raise ValueError('one_solid_native_smd_land_required')
            self.polys[uid]=shape
        return self.polys[uid]

    def core(self,pad,at):
        key=(force._uid(pad),tuple(at));self.tick()
        if key not in self.disks:
            edge=pcbnew.PCB_TRACK(self.board);edge.SetLayer(self.face);edge.SetWidth(self.width)
            edge.SetStart(pcbnew.VECTOR2I(*at));edge.SetEnd(pcbnew.VECTOR2I(*at))
            disk=pcbnew.SHAPE_POLY_SET();edge.TransformShapeToPolygon(disk,self.face,0,1,pcbnew.ERROR_OUTSIDE)
            valid=bool(disk.OutlineCount());disk.BooleanSubtract(self.polygon(pad))
            self.disks[key]=valid and not disk.OutlineCount()
        return self.disks[key]

    def endpoint(self,pad,at):
        if self.core(pad,at):return dict(kind='native_solid_smd_disk',uuid=force._uid(pad))
        at=tuple(at)
        if at not in self.kernels:
            self.kernels[at]=next((force._uid(t) for t in sorted(self.tracks,key=force._uid)
                if ports.on_centerline(t,at)),None)
        if self.kernels[at]:return dict(kind='unchanged_full_width_native_track_disk',uuid=self.kernels[at])
        return None

    def segment(self,pad,a,z):
        self.tick();a,z=tuple(a),tuple(z)
        if a==z:return None
        dx,dy=z[0]-a[0],z[1]-a[1]
        if dx and dy and abs(dx)!=abs(dy):return None
        key=(force._uid(pad),tuple(sorted((a,z))))
        if key not in self.rectangles:
            # Outward integer rounding overcovers the actual central rectangle.
            norm=math.hypot(dx,dy);nx=math.ceil(abs(dy)*self.width/(2*norm))*(-1 if dy>0 else 1)
            ny=math.ceil(abs(dx)*self.width/(2*norm))*(1 if dx>0 else -1)
            shape=pcbnew.SHAPE_POLY_SET();shape.NewOutline()
            for x,y in ((a[0]+nx,a[1]+ny),(z[0]+nx,z[1]+ny),(z[0]-nx,z[1]-ny),(a[0]-nx,a[1]-ny)):shape.Append(x,y)
            shape.BooleanSubtract(self.polygon(pad));self.rectangles[key]=not shape.OutlineCount()
        if not self.rectangles[key]:return None
        first,last=self.endpoint(pad,a),self.endpoint(pad,z)
        if not first or not last:return None
        return dict(pad_uuid=force._uid(pad),layer=self.face,width_nm=self.width,start_nm=list(a),end_nm=list(z),
            central_rectangle_inside_native_error_inside_land=True,endpoint_disk_sources=[first,last],
            polygon_error_bound_nm=1,unchanged_drill_voids_subtracted_not_copper_credit=True,
            new_copper_connection_current_or_fabrication_authority=False)

    def credit(self,segments):
        remaining=[];proof=[]
        for row in segments:
            self.tick();a,z=row['start_nm'],row['end_nm'];found=None
            if row['net']!=self.net or row['layer']!=self.face or row['width_nm']!=self.width:
                raise ValueError('literal_retained_pad_segment_context_required')
            for pad in sorted(self.pads,key=force._uid):
                if not all(pad.GetBoundingBox().Contains(pcbnew.VECTOR2I(*p)) for p in (a,z)):continue
                found=self.segment(pad,a,z)
                if found:break
            if found:proof.append(found)
            else:remaining.append(row)
        return remaining,proof

    def contact_cover(self,selected,item):
        """Every old shared contact envelope already lies in an unchanged land.

        This is material preservation, not an inferred nearby-pad connection.
        Conservative outer contact polygons must fit a conservative inner
        source-land polygon. Identical saved drill voids subtract on both sides.
        """
        self.tick()
        if item.GetClass() not in ('PAD','PCB_TRACK','PCB_VIA'):return None
        other=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(other,self.face,0,1,pcbnew.ERROR_OUTSIDE)
        shared=pcbnew.SHAPE_POLY_SET()
        for track in selected:
            self.tick();shape=pcbnew.SHAPE_POLY_SET();track.TransformShapeToPolygon(shape,self.face,0,1,pcbnew.ERROR_OUTSIDE)
            shape.BooleanIntersection(other);shared.BooleanAdd(shape)
        if not shared.OutlineCount():return None
        for pad in sorted(self.pads,key=force._uid):
            self.tick();missing=shared.CloneDropTriangulation();missing.BooleanSubtract(self.polygon(pad))
            if not missing.OutlineCount():
                return dict(contact_uuid=force._uid(item),pad_uuid=force._uid(pad),layer=self.face,
                    entire_old_shared_contact_envelope_in_unchanged_native_land=True,
                    native_outer_contact_vs_inner_pad_error_bound_nm=1,
                    unchanged_hole_voids_not_copper_or_barrel_capacity=True)
        return None

    def ingress(self,pad,at):
        key=force._uid(pad),tuple(at)
        if key in self.prefixes:return self.prefixes[key]
        if self.core(pad,at):result=[[tuple(at)]]
        elif not self.endpoint(pad,at):result=[]
        else:
            result=[]
            for dx,dy in ((1,0),(0,1),(-1,0),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                for step in (1000,10000,25000,50000,100000,200000,500000):
                    self.tick();target=(at[0]+dx*step,at[1]+dy*step)
                    if (pad.GetBoundingBox().Contains(pcbnew.VECTOR2I(*target)) and self.core(pad,target)
                            and self.segment(pad,at,target)):
                        result.append([tuple(at),target]);break
            result.sort(key=lambda p:(math.dist(p[0],p[-1]),p));result=result[:2]
        self.prefixes[key]=result;return result

    def paths(self,pad,a,z):
        results=[]
        for first in self.ingress(pad,a):
            for reverse in self.ingress(pad,z):
                for middle in fr._canonical_45_xy_paths(first[-1],reverse[-1]):
                    points=[*first[:-1],*map(tuple,middle),*list(reversed(reverse))[1:]]
                    if len(set(points))!=len(points):continue
                    if all(self.segment(pad,p,q) for p,q in zip(points,points[1:])):results.append(points)
        return results
