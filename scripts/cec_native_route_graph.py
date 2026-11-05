"""Validate an unordered two-terminal copper collection without moving it.

Bridge constructors return source stub, destination stub, then middle copper;
that is not a walk ordering. Exact track/via topology determines ordering.
Only a fully captured common convex native SMD land may explain a different
surface launch. No coordinate tolerance, hidden face jump, arbitrary same-net
island, clearance waiver, current capacity or fabrication claim is granted.
"""
import math
import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_native_route_walk as walk


def validate_bridge(board,operations,*,net,start,end,faces,start_layers,end_layers,width_nm):
    if (type(net) is not str or not net or board.FindNet(net) is None
            or type(operations) not in (list,tuple) or not 1<=len(operations)<=256
            or type(width_nm) is not int or not 0<width_nm<=10000000
            or type(faces) not in (list,tuple) or not 1<=len(faces)<=6
            or len(set(faces))!=len(faces) or not set(faces)<=set(board.GetEnabledLayers().CuStack())
            or any(type(l) is not int for l in faces)
            or any(type(ls) not in (list,tuple) or not ls or any(type(l) is not int for l in ls) or not set(ls)<=set(faces)
                for ls in (start_layers,end_layers))):
        raise ValueError('bounded_actual_native_bridge_graph_required')
    def point(p):
        if type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p):
            raise ValueError('exact_native_bridge_graph_point_required')
        return tuple(p)
    start,end=point(start),point(end);code=board.GetNetcodeFromNetname(net)
    if code<=0:raise ValueError('positive_actual_native_bridge_net_required')
    pads=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode()==code
        and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
        and p.GetShape() in (pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_OVAL,pcbnew.PAD_SHAPE_ROUNDRECT)]
    capture_cache={};pad_polygons={}
    def captured(p,at,face):
        key=(force._uid(p),at,face)
        if key in capture_cache:return capture_cache[key]
        if (force._uid(p),face) not in pad_polygons:
            land=pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(land,face,0,1,pcbnew.ERROR_INSIDE)
            pad_polygons[(force._uid(p),face)]=land
        # This is strictly positive GEOMETRIC width capture, not the force
        # receiver's separate 50-um current-contact margin. Use the actual
        # native rounded/oval boundary, not a roundrect bounding rectangle.
        disc=pcbnew.PCB_TRACK(board);disc.SetStart(pcbnew.VECTOR2I(*at));disc.SetEnd(disc.GetStart())
        disc.SetWidth(width_nm+2);disc.SetLayer(face)
        remainder=pcbnew.SHAPE_POLY_SET();disc.TransformShapeToPolygon(remainder,face,0,1,pcbnew.ERROR_OUTSIDE)
        remainder.BooleanSubtract(pad_polygons[(force._uid(p),face)])
        result=not remainder.OutlineCount();capture_cache[key]=result
        return result
    def attachment(anchor,node,allowed):
        x,y,face=node
        if face not in allowed:return None
        if (x,y)==anchor:return dict(exact_input_anchor=True,layer=face,at_nm=[x,y])
        matches=[p for p in pads if list(map(int,p.GetLayerSet().CuStack()))==[face]
            and captured(p,anchor,face) and captured(p,(x,y),face)]
        if len(matches)!=1:return None
        return dict(exact_input_anchor=False,common_native_smd_pad_uuid=force._uid(matches[0]),
            anchor_nm=list(anchor),actual_surface_launch_nm=[x,y],layer=face,
            complete_trace_width_captured_by_one_convex_native_land=True,
            positive_native_geometric_inset_nm=1,force_current_margin_not_inferred=True,
            smd_land_is_not_plated_layer_access=True)
    adjacent={};edges={};barrels={};nodes=set()
    def edge(index,a,b,op):
        edges[index]=(a,b,op);adjacent.setdefault(a,[]).append(index);adjacent.setdefault(b,[]).append(index)
        nodes.update((a,b))
    for i,op in enumerate(operations):
        if type(op) not in (list,tuple) or not op:raise ValueError('literal_native_bridge_graph_operation_required')
        if op[0]=='trk':
            if len(op)!=5 or type(op[3]) is not int or op[3]!=width_nm or type(op[4]) is not int or op[4] not in faces:
                raise ValueError('native_bridge_graph_width_or_face_changed')
            a,b=point(op[1]),point(op[2]);dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
            if a==b or dx and dy and dx!=dy:raise ValueError('native_bridge_graph_noncanonical_or_zero_stroke')
            edge(i,(*a,op[4]),(*b,op[4]),op)
        elif op[0]=='via':
            if (len(op)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in op[2:])
                    or not 0<op[2]<op[3]<=10):raise ValueError('native_bridge_graph_barrel_geometry_required')
            at=point(op[1])
            if at in barrels:raise ValueError('native_bridge_graph_duplicate_barrel')
            barrels[at]=(i,op)
        else:raise ValueError('unknown_native_bridge_graph_operation')
    for at,(i,op) in barrels.items():
        touched={l for x,y,l in nodes if (x,y)==at}
        if len(touched)==1:
            extra=[l for l in faces if l not in touched and
                (attachment(start,(*at,l),start_layers) or attachment(end,(*at,l),end_layers))]
            if len(extra)!=1:raise ValueError('native_bridge_graph_barrel_terminal_face_not_unique')
            touched.add(extra[0])
        if len(touched)!=2:raise ValueError('native_bridge_graph_barrel_is_decorative_or_branched')
        left,right=sorted(touched);edge(i,(*at,left),(*at,right),op)
    terminals=[node for node in nodes if len(adjacent[node])==1]
    if len(terminals)!=2 or any(len(adjacent[n])>2 for n in nodes):
        raise ValueError('native_bridge_graph_is_not_one_two_terminal_path')
    choices=[]
    for a,b in (terminals,terminals[::-1]):
        first,last=attachment(start,a,start_layers),attachment(end,b,end_layers)
        if first is not None and last is not None:choices.append((a,b,first,last))
    if len(choices)!=1:raise ValueError('native_bridge_graph_boundaries_not_unique_actual_surface_attachments')
    at,target,first,last=choices[0];origin=at;visited=set();ordered=[]
    while at!=target:
        options=[i for i in adjacent[at] if i not in visited]
        if len(options)!=1:raise ValueError('native_bridge_graph_disconnected_or_cyclic')
        i=options[0];visited.add(i);a,b,op=edges[i];other=b if a==at else a
        ordered.append(('trk',list(at[:2]),list(other[:2]),width_nm,at[2]) if op[0]=='trk'
            else ('via',list(at[:2]),op[2],op[3]))
        at=other
    if len(visited)!=len(operations):raise ValueError('native_bridge_graph_contains_unconnected_material')
    proof=walk.validate(ordered,start=list(origin[:2]),end=list(target[:2]),faces=faces,
        start_layers=[origin[2]],end_layers=[target[2]],width_nm=width_nm)
    return dict(ok=True,complete=True,ordered_operations=ordered,strict_ordered_walk=proof,
        source_surface_attachment=first,destination_surface_attachment=last,
        every_input_operation_used_exactly_once=True,geometry_changed=False,
        source_clearance_current_or_fabrication_qualified=False,release_authority=False)
