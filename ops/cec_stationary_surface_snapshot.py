"""Reuse fixed native surface obstacles only inside an exact stationary snapshot.

Moving selected SMD lands are always decoded afresh. Fixed primitive geometry,
local clearance, real zone intent/fill, holes, policy and sidecars are rebound
before and after each check. Unsupported fixed copper graphics/custom pad
geometry use the unchanged cold checker. No caching across native epochs,
positive placement/admission credit, or fabricated no-path proof is granted.
"""
import hashlib,math,time
from pathlib import Path
import pcbnew
import cec_escape_pose_frontier as surface
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_kelvin_copper_cut as cut
import cec_cell_row_rebuild as row

_SELF=Path(__file__).resolve();_HASH=force._hash(_SELF)
_HELPERS={str(Path(q.__file__).resolve()):force._hash(Path(q.__file__)) for q in (surface,field,fr,cut)}
def identity():
    result={str(_SELF):_HASH,**_HELPERS}
    if any(force._hash(Path(p))!=h for p,h in result.items()):raise ValueError('stationary_surface_snapshot_helpers_changed')
    return result

def _graphics(board,selected,layers):
    return [g for fp in board.GetFootprints() if fp.GetReference() not in selected
        for g in [*fp.GraphicalItems(),*fp.GetFields()] if any(g.IsOnLayer(l) for l in layers)]+[
        g for g in board.GetDrawings() if any(g.IsOnLayer(l) for l in layers)]

class Snapshot:
    def __init__(self,board,refs,*,allow_native_ground_refill=True,timeout_s=10.):
        if (type(refs) not in (set,tuple,list) or not 1<=len(refs)<=8 or len(set(refs))!=len(refs)
                or type(allow_native_ground_refill) is not bool):raise ValueError('bounded_stationary_surface_snapshot_required')
        self.board=board;self.refs=set(refs);self.allow=allow_native_ground_refill;self.helpers=identity()
        self.owner_ids={force._uid(f) for f in board.GetFootprints() if f.GetReference() in self.refs}
        if len(self.owner_ids)!=len(self.refs):raise ValueError('exact_selected_surface_owners_required')
        pads=self._pads();self.layers={l for p,l in pads};self.supported=not bool(_graphics(board,self.refs,self.layers))
        supported={pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL}
        if any(p.GetShape() not in supported for f in board.GetFootprints() if f.GetReference() not in self.refs for p in f.Pads()):
            self.supported=False
        self.binding=self._binding() if self.supported else None
        if self.supported:
            work=self._work(timeout_s)
            self.obstacles,self.refill,_=surface._surface_obstacles(board,self.refs,self.layers,
                work=work,allow_native_ground_refill=self.allow)
            work.tick()
            if self.binding!=self._binding():raise ValueError('stationary_surface_changed_during_snapshot')
        identity();self.checks=0
    def _work(self,seconds):
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
            raise ValueError('bounded_stationary_surface_native_lease_required')
        return cut._Work(time.monotonic()+seconds)
    def _pads(self):
        result=[]
        for ref in sorted(self.refs):
            fp=self.board.FindFootprintByReference(ref)
            if fp is None or force._uid(fp) not in self.owner_ids:raise ValueError('selected_surface_owner_identity_changed')
            for pad in fp.Pads():
                faces=list(map(int,pad.GetLayerSet().CuStack()))
                if pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or len(faces)!=1:
                    raise ValueError('single_face_selected_surface_lands_required')
                result.append((pad,faces[0]))
        return result
    def _binding(self):
        board=self.board;local=fr._foreign_clearance_resolver(board);rows=[]
        settings=board.GetDesignSettings();layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
        rows.append(('settings',settings.m_MinClearance,settings.m_HoleClearance,layers,
            tuple(sorted((str(k),str(v)) for k,v in dict(board.GetProperties()).items()))))
        path=Path(board.GetFileName()) if board.GetFileName() else None
        if path and path.is_file():rows.append(('sidecars',force._sidecars(path)))
        for fp in board.GetFootprints():
            if force._uid(fp) in self.owner_ids:continue
            rows.append(('footprint',force._uid(fp),fp.GetReference(),fp.GetFPIDAsString(),fp.IsFlipped()))
            for p in fp.Pads():
                rows.append(('pad',force._uid(p),p.GetNumber(),p.GetNetCode(),p.GetNetname(),tuple(p.GetPosition()),
                    tuple(p.GetSize()),tuple(p.GetOffset()),p.GetShape(),p.GetRoundRectRadiusRatio(),
                    p.GetOrientationDegrees(),p.GetAttribute(),tuple(p.GetDrillSize()),p.GetDrillShape(),
                    tuple(p.GetLayerSet().Seq()),tuple((l,int(local(p,l))) for l in self.layers)))
        for t in board.GetTracks():
            kind=t.GetClass()
            if kind=='PCB_VIA':geometry=(tuple(t.GetPosition()),t.GetDrillValue(),int(t.TopLayer()),int(t.BottomLayer()),
                int(t.GetViaType()),tuple((l,t.GetWidth(l)) for l in self.layers))
            elif kind=='PCB_TRACK':geometry=(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetLayer(),t.GetWidth())
            elif kind=='PCB_ARC':geometry=(tuple(t.GetStart()),tuple(t.GetMid()),tuple(t.GetEnd()),t.GetLayer(),t.GetWidth())
            else:raise ValueError('unsupported_stationary_surface_track_type')
            rows.append((kind,force._uid(t),t.GetNetCode(),t.GetNetname(),geometry,
                tuple((l,int(local(t,l))) for l in self.layers)))
        for z in board.Zones():
            rows.append(('zone',force._uid(z),z.GetNetCode(),z.GetZoneName(),z.GetIsRuleArea(),z.GetDoNotAllowFootprints(),
                tuple(z.GetLayerSet().Seq()),z.Outline().Format(),z.IsFilled(),
                tuple((l,z.GetFilledPolysList(l).Format()) for l in self.layers if z.IsOnLayer(l)),
                tuple((l,int(local(z,l))) for l in self.layers)))
        # Any newly added copper graphic must invalidate a supported cache.
        if _graphics(board,self.refs,self.layers):rows.append(('new_unsupported_copper_graphics',True))
        return hashlib.sha256(repr(rows).encode()).hexdigest()
    def check(self,*,timeout_s=10.):
        work=self._work(timeout_s);identity();pads=self._pads()
        if {l for p,l in pads}!=self.layers:raise ValueError('stationary_surface_query_layers_changed')
        if not self.supported:
            return surface.surface_screen(self.board,self.refs,selected_refs=self.refs,
                allow_native_ground_refill=self.allow,timeout_s=timeout_s)
        if self.binding!=self._binding():raise ValueError('stationary_surface_material_policy_or_sidecars_changed')
        before=row._source_binding(self.board);local=fr._foreign_clearance_resolver(self.board)
        conflicts=surface._surface_hits(self.board,pads,self.obstacles,local,work)
        if before!=row._source_binding(self.board) or self.binding!=self._binding():
            raise ValueError('stationary_surface_check_changed_native_snapshot')
        work.tick();identity();self.checks+=1
        return dict(ok=not conflicts,conflicts=conflicts,source_unchanged=True,native_ground_refill_still_required=self.refill,
            warm_stationary_obstacles_reused=True,moving_land_shapes_redecoded=True,
            snapshot_checks=self.checks,routing_admitted=False,release_authority=False,no_path_proof=False,
            final_native_drc_and_whole_board_receiving_still_required=True)
