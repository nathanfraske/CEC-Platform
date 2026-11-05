"""Warm, Source-bound joint-cell pose pages; proposals, never admission.

Every column has 48 explicit cardinal cap/owner/spacing states. Positive
stationary-column collisions reject a whole identical-column range; all other
states receive actual courtyard, native column and surface checks. Unknowns
are recorded, not called impossible. A continuation cannot skip an unattempted
prefix or silently reuse another Source/helper/settings context.
"""
import collections,copy,hashlib,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_static_foreign_column_filter as columns
import cec_existing_local_pofv_pad_rule as rule
import cec_escape_pose_frontier as surfaces
import cec_ground_access_completion as entry
import cec_source_local_ground_search as ground
import cec_field_coupling as fields
import cec_kelvin_copper_cut as cut
from cec_retained_forest_macro import compiler

_SELF=Path(__file__).resolve();_SELF_HASH=force._hash(_SELF)
SPACINGS=(.8,1.2,1.6)
def _digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def points(origin,radius_nm,grid_nm):
    if (type(origin) not in (tuple,list) or len(origin)!=2 or any(type(v) is not int for v in origin)
            or type(radius_nm) is not int or not 0<radius_nm<=32000000
            or type(grid_nm) is not int or not 250000<=grid_nm<=1000000):
        raise ValueError('bounded_literal_ground_cell_lattice_required')
    n=radius_nm//grid_nm
    result=[(origin[0]+x*grid_nm,origin[1]+y*grid_nm)
        for x in range(-n,n+1) for y in range(-n,n+1) if (x*grid_nm)**2+(y*grid_nm)**2<=radius_nm**2]
    return sorted(result,key=lambda p:((p[0]-origin[0])**2+(p[1]-origin[1])**2,p))

def decode(index):
    if type(index) is not int or index<0:raise ValueError('literal_nonnegative_ground_cell_state_index_required')
    column,state=divmod(index,48);cap,rest=divmod(state,12);owner,spacing=divmod(rest,3)
    return column,90*cap,90*owner,SPACINGS[spacing]

def cursor(binding,next_index,total,unknown_count):
    data=dict(schema=1,binding=binding,next_index=next_index,total_states=total,unknown_states=unknown_count)
    return dict(**data,checksum=_digest(data))

def walk(total,binding,blocked,check,*,resume=None,page_states=16384,maximum_offers=4,timeout_s=30.,clock=time.monotonic):
    if (type(total) is not int or total<0 or type(binding) is not str or len(binding)!=64
            or type(page_states) is not int or not 1<=page_states<=32768
            or type(maximum_offers) is not int or not 1<=maximum_offers<=8
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=45):
        raise ValueError('bounded_ground_cell_page_required')
    start=0;unknown=0
    if resume is not None:
        if type(resume) is not dict or set(resume)!={'schema','binding','next_index','total_states','unknown_states','checksum'}:
            raise ValueError('exact_ground_cell_continuation_required')
        q={k:v for k,v in resume.items() if k!='checksum'}
        if (q['schema']!=1 or q['binding']!=binding or q['total_states']!=total
                or type(q['next_index']) is not int or not 0<=q['next_index']<=total
                or type(q['unknown_states']) is not int or not 0<=q['unknown_states']<=q['next_index']
                or resume['checksum']!=_digest(q)):
            raise ValueError('ground_cell_source_helpers_settings_or_cursor_changed')
        start=q['next_index'];unknown=q['unknown_states']
    index=start;end=min(total,start+page_states);deadline=clock()+timeout_s
    counts=collections.Counter();ranges=[];offers=[];examples=[];cached={}
    while index<end and clock()<deadline and len(offers)<maximum_offers:
        column,*state=decode(index)
        if column not in cached:cached[column]=blocked(column)
        refusal=cached[column]
        if refusal is not None:
            stop=min(end,(column+1)*48);ranges.append(dict(start=index,end=stop,kind='positive_stationary_column_refusal'))
            counts['exact_static_foreign_copper_refused_states']+=stop-index
            counts['exact_static_foreign_copper_refused_columns']+=1;index=stop;continue
        result=check(column,*state)
        if type(result) is not dict or not result.get('kind'):raise ValueError('typed_actual_native_cell_outcome_required')
        kind=result['kind'];ranges.append(dict(start=index,end=index+1,kind=kind));counts[kind]+=1
        if kind=='bounded_native_unknown':unknown+=1
        if result.get('offer') is not None:offers.append(result['offer'])
        if len(examples)<32 and result.get('diagnostic') is not None:
            examples.append(dict(state_index=index,kind=kind,diagnostic=result['diagnostic']))
        index+=1
    assert sum(v['end']-v['start'] for v in ranges)==index-start
    assert all(a['end']==b['start'] for a,b in zip(ranges,ranges[1:]))
    return dict(start_index=start,next_index=index,total_states=total,actual_examined_ranges=ranges,
        no_gap_or_overlap_in_actual_attempted_prefix=True,all_finite_states_attempted=index==total,
        unknown_states_across_prefix=unknown,finite_menu_closed_without_unknowns=index==total and unknown==0,
        deadline_reached=clock()>=deadline,counts=dict(counts),offers=offers,examples=examples,
        continuation=cursor(binding,index,total,unknown),global_no_path_or_optimal_placement_proof=False,
        complete_native_routing_and_independent_saved_receiving_still_required=True)

def prepare(frame,*,radius_mm=16.,grid_mm=.5):
    if (type(frame) is not dict or type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
            or not 0<radius_mm<=32 or type(grid_mm) not in (int,float) or not math.isfinite(grid_mm)
            or not .25<=grid_mm<=1):raise ValueError('bounded_source_ground_cell_frame_required')
    seed=copy.deepcopy(frame);source=Path(seed['source']).resolve();digest=force._hash(source)
    if seed['source_sha256']!=digest:raise ValueError('exact_saved_ground_cell_source_required')
    epoch=force._code_identity();family=force._family(source,seed['board_hint']);parent=pcbnew.LoadBoard(str(source))
    req=seed['source_selected_bypass'];owner_ref=req['ref'];caps=set(seed['poses'])-{owner_ref}
    if len(caps)!=1:raise ValueError('one_source_selected_owner_and_bypass_required')
    cap_ref=next(iter(caps));refs={cap_ref,owner_ref};posed={}
    for ref in refs:
        fp=parent.FindFootprintByReference(ref)
        if fp is None:raise ValueError('literal_cell_footprints_required')
        posed[ref]=[fp.GetPosition().x/1e6+.001,fp.GetPosition().y/1e6+.001,fp.GetOrientationDegrees()]
    board,packet=compiler.compile(source,posed,board_hint=seed['board_hint'],max_shift_mm=radius_mm,
        allow_owned_locked_escapes=True,rebuild_projected_ground=True,
        required_ground_pad_entries=seed['required_ground_pad_entries'])
    actual=packet['source_plan']['selected_bypasses'][cap_ref]
    if actual['owner']!=owner_ref or actual['pin']!=str(req['pin']) or actual['rail']!=req['rail']:
        raise ValueError('source_selected_bypass_assignment_changed')
    cap,owner=[board.FindFootprintByReference(r) for r in (cap_ref,owner_ref)]
    gp=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    vp=next(p for p in cap.Pads() if p.GetNetname()==req['rail']);power=owner.FindPadByNumber(str(req['pin']))
    origin=tuple(next(p for p in parent.FindFootprintByReference(cap_ref).Pads() if p.GetNetname()=='GND').GetPosition())
    oldposes={r:tuple(parent.FindFootprintByReference(r).GetPosition()) for r in refs}
    moving_ids={force._uid(board.FindFootprintByReference(r)) for r in refs}
    def stationary():return {k:v for k,v in fields._field_snapshot_inventory(board).items()
        if not(k[0]=='pad' and k[1] in moving_ids)}
    _,_,geometry=entry._existing_pad_rule(board,gp)
    helpers={str(_SELF):_SELF_HASH,str(Path(columns.__file__).resolve()):force._hash(Path(columns.__file__)),
        **packet['source_stationary_ground_retention_extension']['helper_sha256']}
    settings=dict(radius_mm=radius_mm,grid_mm=grid_mm,cap_angles=[0,90,180,270],owner_angles=[0,90,180,270],
        supply_spacing_mm=list(SPACINGS),new_ground_rule_geometry=geometry)
    identity=_digest(dict(source_sha256=digest,source_family=family,code_identity=epoch,frame=seed,settings=settings,helpers=helpers))
    lattice=points(origin,round(radius_mm*1e6),round(grid_mm*1e6))
    return dict(source=source,digest=digest,epoch=epoch,family=family,seed=seed,parent=parent,board=board,
        refs=refs,cap=cap,owner=owner,gp=gp,vp=vp,power=power,oldposes=oldposes,stationary=stationary,
        stationary_binding=stationary(),indices=columns.snapshot(board,sorted(moving_ids),gp.GetNetCode()),
        diameter_nm=round(geometry[0]*1e6),geometry=geometry,
        gap_nm=max(200000,int(board.GetDesignSettings().m_MinClearance),int(ground.cells._netclass(board,'GND')['clearance'])),
        lattice=lattice,settings=settings,helpers=helpers,identity=identity)

def scan(context,*,resume=None,page_states=16384,maximum_offers=4,timeout_s=30.):
    c=context;board=c['board'];cap,owner,gp,vp,power=[c[k] for k in ('cap','owner','gp','vp','power')]
    def immutable():
        if (force._hash(c['source'])!=c['digest'] or force._family(c['source'],c['seed']['board_hint'])!=c['family']
                or force._code_identity()!=c['epoch'] or c['stationary']()!=c['stationary_binding']
                or any(force._hash(Path(p))!=h for p,h in c['helpers'].items())):
            raise ValueError('ground_cell_source_helpers_or_stationary_material_changed')
    immutable()
    def move(fp,pad,point):
        old=pad.GetPosition();fp.Move(pcbnew.VECTOR2I(round(point[0])-old.x,round(point[1])-old.y))
    def pose(fp):return [fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,float(fp.GetOrientationDegrees())]
    def blocked(column):return columns.collision(c['indices'],c['lattice'][column],c['diameter_nm'],c['gap_nm'])
    def check(column,cap_angle,owner_angle,spacing):
        point=c['lattice'][column];cap.SetOrientationDegrees(cap_angle);move(cap,gp,point)
        vector=(vp.GetPosition().x-gp.GetPosition().x,vp.GetPosition().y-gp.GetPosition().y);length=math.hypot(*vector)
        if not length:raise ValueError('distinct_source_capacitor_lands_required')
        owner.SetOrientationDegrees(owner_angle)
        move(owner,power,(vp.GetPosition().x+vector[0]/length*spacing*1e6,vp.GetPosition().y+vector[1]/length*spacing*1e6))
        if any(math.dist(tuple(fp.GetPosition()),c['oldposes'][fp.GetReference()])>c['settings']['radius_mm']*1e6 for fp in (cap,owner)):
            return dict(kind='source_shift_bound_refused')
        court=surfaces.courtyard_screen(board,c['refs'])
        if not court['ok']:return dict(kind='native_courtyard_refused')
        target={r:pose(board.FindFootprintByReference(r)) for r in c['refs']};rule.bind_projected_source_poses(board,target)
        pre=ground._preflight(board,gp,point,c['geometry'],foreign_cache={})
        if not pre['ok']:return dict(kind='full_native_column_refused',diagnostic=pre)
        try:surface=surfaces.surface_screen(board,c['refs'],selected_refs=c['refs'],allow_native_ground_refill=True,timeout_s=2.)
        except cut.Unknown as exc:return dict(kind='bounded_native_unknown',diagnostic=str(exc))
        if not surface['ok']:return dict(kind='native_surface_refused',diagnostic=surface)
        offer=copy.deepcopy(c['seed']);offer.update(poses=target,max_shift_mm=c['settings']['radius_mm'],rebuild_projected_ground=True)
        offer['ground_first_joint_origin']=dict(native_column_preflight=pre,actual_courtyards_and_surface_passed=True,
            source_shift_bounds_mm=c['settings']['radius_mm'],source_supply_owner_and_pin_unchanged=True,
            no_source_current_budget_or_priority_bus_changed=True,complete_native_macro_routing_and_saved_receiving_still_required=True)
        return dict(kind='source_guarded_joint_pose_offer',offer=offer)
    result=walk(len(c['lattice'])*48,c['identity'],blocked,check,resume=resume,page_states=page_states,
        maximum_offers=maximum_offers,timeout_s=timeout_s)
    immutable()
    return dict(ok=True,complete=True,source=str(c['source']),source_sha256=c['digest'],code_identity=c['epoch'],
        helper_sha256=c['helpers'],source_owner=owner.GetReference(),source_cap=cap.GetReference(),
        settings=c['settings'],column_inventory=len(c['lattice']),coverage=result,
        warm_source_context_reused=True,source_family_and_stationary_material_unchanged=True,
        no_board_saved=True,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
