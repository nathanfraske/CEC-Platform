"""Source-canonical diode geometry, not a clamp or current qualification.

Only a half turn about the exact unchanged Ground land is owned.  The other
land must be isolated in Source.  All copper stays authored; separate typed
full-current routing and all enclosing gates remain mandatory.
"""
import math
from pathlib import Path
import time
import pcbnew
import cec_force_current as force
import cec_source_ground_leaf as leaf
import cec_source_reference_group_transport as reference
from cec_footprint_fields import footprint_properties


def _need(value, reason):
    if not value: raise ValueError(reason)


def _left(deadline):
    remaining=deadline-time.monotonic()
    _need(remaining>0,'source_diode_pivot_deadline')
    return min(10.,remaining)


def _live(proof,deadline):
    _left(deadline)
    _need(all(force._hash(Path(p))==h for p,h in proof['schematic_files_sha256'].items())
        and force._hash(Path(proof['exporter']['exporter']))==proof['exporter']['exporter_sha256'],
        'canonical_diode_Source_or_exporter_changed')


def _canonical(board,source,fp,hint,deadline):
    root=leaf.source_nc._root(board,hint)
    _need(root is not None,'canonical_diode_hierarchy_required')
    root=Path(root).resolve(strict=True)
    files,hashes,instances=leaf._hierarchy(root,deadline)
    tree,exporter=leaf._export(root,deadline);comps,nets,node_net=leaf._tables(tree)
    identity=leaf._identity(board,fp.GetReference(),comps,instances,deadline)
    component=comps[fp.GetReference()];kind=leaf.synth._val(leaf.synth._first(component,'libsource'),'part','')
    _need(kind in ('D','D_Schottky','D_Zener','D_TVS','D_TVS_ALT'),
        'canonical_two_pin_diode_symbol_required')
    libraries=[b for tag,b in identity[2].children if tag=='lib_symbols']
    _need(len(libraries)==1,'complete_diode_embedded_library_required')
    library=leaf.synth.parse_sexpr(libraries[0])
    symbols=[s for s in leaf.synth._kids(library,'symbol')if len(s)>1 and s[1]==identity[3]['lib_id']]
    _need(len(symbols)==1 and leaf.synth._first(symbols[0],'extends')is None,
        'complete_diode_embedded_symbol_required')
    todo=[symbols[0]];pins=[];count=0
    while todo:
        _left(deadline);node=todo.pop();count+=1
        _need(count<=4096,'bounded_diode_embedded_symbol_required')
        if isinstance(node,list)and node:
            if node[0]=='pin':pins.append(node)
            todo.extend(x for x in node if isinstance(x,list))
    _need(len(pins)==2 and {leaf.synth._val(x,'number','')for x in pins}=={'1','2'}
        and all(x[1]=='passive'for x in pins),'exact_two_passive_diode_pins_required')
    blocks=[b for tag,b in identity[2].children if tag=='symbol'
        and leaf.sch.prop_value(b,'Reference')==fp.GetReference()]
    props=footprint_properties(fp)
    exported={leaf.synth._val(x,'name',''):leaf.synth._val(x,'value','')for x in leaf.synth._kids(component,'property')}
    _need(len(blocks)==1,'one_diode_Source_instance_required')
    for key in ('Manufacturer','MPN','LCSC'):
        _need(props.get(key) and leaf.sch.prop_value(blocks[0],key)==props[key]
            and exported.get(key)==props[key],'selected_diode_Source_field_mismatch:'+key)
    for pad in fp.Pads():
        _need(leaf._pin(identity,pad.GetNumber())['type']=='passive'
            and node_net.get((fp.GetReference(),pad.GetNumber()))==pad.GetNetname(),
            'actual_diode_Source_pin_net_required')
        if pad.GetNetname()!='GND':
            native={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==pad.GetNetname()}
            _need(native==nets.get(pad.GetNetname(),set()),'complete_diode_supply_Source_membership_required')
    result=dict(symbol_kind=kind,schematic_files_sha256=hashes,exporter=exporter,
        symbol_uuid=identity[3]['uuid'],selected_fields={k:props[k]for k in ('Manufacturer','MPN','LCSC')},
        protection_model_inferred=False,current_authority=False)
    _live(result,deadline)
    return result


def inspect(board,source,*,owner_uuid,ground_pad_uuid,group_uuid,board_hint,deadline):
    """Private fresh witness used by both producer and independent receiver."""
    _left(deadline);fps=[f for f in board.GetFootprints()if force._uid(f)==owner_uuid]
    _need(len(fps)==1,'unique_Source_diode_owner_required');fp=fps[0];pads=list(fp.Pads())
    face=pcbnew.B_Cu if fp.IsFlipped()else pcbnew.F_Cu
    _need(not fp.IsLocked()and not fp.IsDNP()and len(pads)==2
        and {p.GetNumber()for p in pads}=={'1','2'}and len({p.GetNetname()for p in pads})==2
        and not list(fp.Zones())and not any(int(i.GetLayer())in {*map(int,board.GetEnabledLayers().CuStack()),int(pcbnew.Edge_Cuts)}
            for i in [*fp.GraphicalItems(),*fp.GetFields()])and all(not p.IsLocked()and not p.GetParentGroup()and not p.HasHole()
            and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and list(p.GetLayerSet().CuStack())==[face]
            and p.GetNetCode()>0 for p in pads),'unlocked_exact_two_surface_pin_diode_required')
    ground=[p for p in pads if p.GetNetname()=='GND']
    _need(len(ground)==1 and force._uid(ground[0])==ground_pad_uuid,'exact_Source_diode_Ground_pivot_required')
    other=next(p for p in pads if p.GetNetname()!='GND')
    import cec_fr as fr
    graph=fr._read_only_route_connectivity(board)
    _need(not any(force._uid(i)!=force._uid(other)for i in graph.GetConnectedItems(other)),
        'diode_other_land_must_be_Source_isolated')
    canonical=_canonical(board,Path(source),fp,board_hint,deadline)
    import cec_full_current_planar_reflow as full
    kind,domain,contract=full._model(board,Path(source),str(other.GetNetname()),board_hint)
    _need(kind=='aggregate_source_sink','diode_requires_existing_complete_aggregate_current_domain')
    groups=[g for g in board.Groups()if any(force._uid(i)==owner_uuid for i in g.GetItems())]
    _need(len(groups)==1 and force._uid(groups[0])==group_uuid,'exact_closed_Source_diode_reference_map_required')
    map_proof=reference.inspect_many(source,[(owner_uuid,group_uuid)],timeout_s=_left(deadline))[0]
    return dict(owner_uuid=owner_uuid,ground_pad_uuid=ground_pad_uuid,group_uuid=group_uuid,
        canonical_source=canonical,reference_map=map_proof,aggregate_contract=contract,
        aggregate_domain=domain,source_isolated_pad_uuid=force._uid(other),
        current_qualified=False,protection_qualified=False,release_authority=False)


def project_reference(board,proof,deadline):
    """Move ONLY independently recognized closed-map ink; pose tier owns FP."""
    _left(deadline);fp=next(f for f in board.GetFootprints()if force._uid(f)==proof['owner_uuid'])
    pivot=next(p for p in fp.Pads()if force._uid(p)==proof['ground_pad_uuid'])
    center=tuple(fp.GetPosition());at=tuple(pivot.GetPosition())
    delta=tuple(2*(at[k]-center[k])for k in (0,1))
    expected,_=reference._cardinal_derive(proof['reference_map'],2,delta,6.)
    old={force._uid(x):x for x in board.GetDrawings()};new={force._uid(x):x for x in expected.GetDrawings()}
    for uid in proof['reference_map']['member_uuids']:
        if uid==proof['owner_uuid']:continue
        _need(uid in old and uid in new,'exact_diode_reference_member_required')
        item,target=old[uid],new[uid]
        if item.GetClass()=='PCB_SHAPE':item.SetStart(target.GetStart());item.SetEnd(target.GetEnd())
        elif item.GetClass()=='PCB_TEXT':item.SetTextPos(target.GetTextPos());item.SetTextAngle(target.GetTextAngle())
        else:raise ValueError('unsupported_diode_reference_map_member')
    _left(deadline)


def receive(source,candidate,*,owner_uuid,ground_pad_uuid,reference_group_uuid,board_hint,timeout_s=10.):
    import cec_pose_additive_reconstruction as pose
    return pose.receive(source,candidate,selected_footprint_uuids=[owner_uuid],board_hint=board_hint,
        timeout_s=timeout_s,max_shift_mm=6.,selected_pivot_pad_uuids={owner_uuid:ground_pad_uuid},
        reference_group_uuids=[reference_group_uuid],allow_source_two_pin_diode_pivot=True)


def plan(source,*,owner_uuid,ground_pad_uuid,reference_group_uuid,board_hint,timeout_s=10.):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_Source_diode_pivot_lease_required')
    deadline=time.monotonic()+timeout_s;source=Path(source).resolve(strict=True)
    sha=force._hash(source);epoch=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source))
    witness=inspect(board,source,owner_uuid=owner_uuid,ground_pad_uuid=ground_pad_uuid,
        group_uuid=reference_group_uuid,board_hint=board_hint,deadline=deadline)
    project_reference(board,witness,deadline)
    import cec_native_placement_context as motion
    fp=next(f for f in board.GetFootprints()if force._uid(f)==owner_uuid)
    pivot=motion.rotate_isolated_local_cells(board,{fp.GetReference():180},
        pivot_pad_uuids={fp.GetReference():ground_pad_uuid},timeout_s=_left(deadline))
    import cec_escape_pose_frontier as frontier
    court=frontier.courtyard_screen(board,[fp.GetReference()])
    copper=frontier.surface_screen(board,[fp.GetReference()],timeout_s=_left(deadline),allow_native_ground_refill=True)
    _live(witness['canonical_source'],deadline)
    _need(sha==force._hash(source)and epoch==force._code_identity()and family==force._family(source,board_hint),
        'Source_diode_pivot_identity_changed')
    q=dict(scope='Source_canonical_two_pin_diode_stationary_Ground_half_turn',
        source=str(source),source_sha256=sha,code_identity=epoch,
        request=dict(owner_uuid=owner_uuid,ground_pad_uuid=ground_pad_uuid,
            reference_group_uuid=reference_group_uuid,board_hint=board_hint),
        witness=witness,pivot=pivot,pose_screen=dict(ok=bool(court['ok']and copper['ok']),courtyard=court,surface=copper),
        protection_qualified=False,current_qualified=False,release_authority=False)
    return board,q


def save_private(board,candidate,proposal):
    """Literal-preserving writer only; independent saved receiving is required."""
    _need(proposal.get('pose_screen',{}).get('ok')is True,
        'positive_Source_diode_pose_screen_required')
    _need(force._hash(Path(proposal['source']))==proposal['source_sha256']
        and force._code_identity()==proposal['code_identity'],'fresh_Source_diode_pivot_required')
    import cec_field_coupling as field
    import cec_source_literal_footprint_retention as footprints
    import cec_source_retaining_ses_import as raw
    field._save_field_snapshot(board,candidate)
    raw.write_raw(candidate,footprints.retain(raw.raw_text(proposal['source']),raw.raw_text(candidate),
        [proposal['request']['owner_uuid']]))
    # Groups never acquire a native serializer normalization allowance.
    import cec_source_literal_additions as literal
    inventory,*_=literal._inventory(raw.raw_text(proposal['source']))
    groups={uid for uid,(_,_,node)in inventory.items()if raw.kind(node)=='group'}
    if groups:raw.write_raw(candidate,raw.retain_replay_source_nodes(raw.raw_text(proposal['source']),
        raw.raw_text(candidate),groups,set()))
    return dict(saved=True,received=False,release_authority=False)
