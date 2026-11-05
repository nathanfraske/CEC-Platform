"""Literal unassigned mechanical-mount isolation; never Ground/net authority.

The default-off library reconciler consumes this rejection-only prerequisite.
No net-zero objects are treated as one electrical net. A complete unchanged
main-land envelope must remain clear of EVERY other native copper object.
Whole-board factory, connectivity, current and saved receiving still apply.
"""
import copy
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force

MODE='source_unassigned_mechanical'

def need(ok,why):
    if not ok:raise ValueError(why)

def tick(deadline):need(time.monotonic()<deadline,'unassigned_mount_isolation_deadline')

def _json(path):
    need(path.stat().st_size<=2*1024*1024,'bounded_mount_policy_file_required')
    def unique(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'ambiguous_mount_policy_json_key');result[key]=value
        return result
    return json.loads(path.read_text(),object_pairs_hook=unique,
        parse_constant=lambda v:(_ for _ in()).throw(ValueError('nonfinite_mount_policy_json')))

def _projection(params,terminals):
    need(type(params)is dict and len(params)<=8192 and all(type(k)is str for k in params),
        'literal_mount_policy_mapping_required')
    result={k:copy.deepcopy(v)for k,v in params.items()if k.startswith('mount_')
        or k=='source_sync_extra_pad_nets'}
    net=params.get('mount_net')
    need(net is None or type(net)is str and not net,'declared_mount_net_requires_electrical_reconciliation')
    need(params.get('mount_contact_diameter_mm')is None,'declared_mount_contact_requires_electrical_reconciliation')
    need(params.get('mount_contact')in(None,False)and type(params.get('mount_contact'))in(type(None),bool),
        'active_or_unknown_mount_contact_refuses_unassigned_mode')
    for key in('mount_electrical_role','mount_function'):
        value=params.get(key)
        need(value is None or type(value)is str and value in('none','isolated','mechanical','unassigned'),
            'active_or_unknown_'+key+'_refuses_unassigned_mode')
    need(params.get('mount_hole_type')in(None,'pth'),'source_unassigned_mount_requires_declared_pth_or_absence')
    known={'mount_net','mount_contact','mount_contact_diameter_mm','mount_electrical_role'}
    need(not any(k not in known and k.startswith(('mount_net_','mount_contact_','mount_electrical_'))
        for k in params),'unknown_mount_electrical_declaration')
    if 'source_sync_extra_pad_nets'in params:
        assignments=params['source_sync_extra_pad_nets']
        need(type(assignments)is dict and len(assignments)<=4096
            and all(type(k)is str and k and type(v)is str and v for k,v in assignments.items()),
            'literal_board_only_terminal_net_declarations_required')
        need(not set(assignments).intersection(terminals),'selected_mechanical_mount_has_declared_board_only_net')
    return result

def policy_binding(board_hint,terminals):
    """Bind all construction-policy layers, including strict manifest absence.

    Any independently active electrical declaration vetoes this narrow mode;
    it cannot be cleared by a caller override or a permissive manifest parse.
    """
    import cec_board_policy as policy
    import cec_fresh_wave as fresh
    import cec_synth_pipeline as synth
    need(type(board_hint)is str and board_hint and type(terminals)in(list,tuple)
        and terminals and all(type(t)is str and t for t in terminals),'explicit_mechanical_policy_context_required')
    cfg=synth.Config.load(board_hint);directory=Path(cfg.dir).resolve(strict=True)
    contexts={'effective_Config':_projection(cfg.params,terminals)}
    legacy=fresh.BOARD_PARAMS.get(cfg.board,{})
    contexts['legacy_construction']=_projection(legacy,terminals)
    candidates={directory/'board-manifest.json'}
    candidates.update(Path(fresh.ROOT)/root/cfg.board/'board-manifest.json'for root in('beta','modules','hubs'))
    inputs={}
    for path in sorted(candidates):
        path=path.resolve();exists=path.exists()
        need(not exists or path.is_file(),'mount_manifest_must_be_regular_file')
        inputs[str(path)]=force._hash(path)if exists else None
        if exists:
            payload=_json(path);need(type(payload)is dict,'literal_mount_manifest_required')
            declarations=payload.get('placement_directives',{})
            contexts[str(path)]=_projection(declarations,terminals)
    local=directory/policy.POLICY_FILENAME
    resolved=policy.policy_path(directory,board_hint=cfg.board)
    for path in{local.resolve(),*( [Path(resolved).resolve()]if resolved else[])}:
        inputs[str(path)]=force._hash(path)if path.exists()else None
        if not path.exists():continue
        # A valid Config can live outside the repository roots. The ordinary
        # loader's path walk may then return no policy even though this exact
        # canonical directory has one. Hashing that file is not sufficient:
        # independently validate/project its declarations before loading any
        # effective overlay. An active local electrical role always vetoes.
        payload=_json(path)
        need(type(payload)is dict and payload.get('schema')==policy.SCHEMA,
            'literal_supported_mount_policy_required')
        aliases=payload.get('aliases',[])
        need(type(payload.get('board'))is str and payload['board']
            and type(aliases)is list and len(aliases)<=256
            and all(type(v)is str and v for v in aliases)
            and cfg.board in(payload['board'],*aliases),'canonical_mount_policy_identity_required')
        contexts[str(path)]=_projection(payload.get('params',{}),terminals)
    loaded=policy.load(directory,board_hint=cfg.board)
    contexts['declarative_policy']=_projection(loaded.get('params',{}),terminals)
    need(all((force._hash(p)if Path(p).is_file()else None)==sha for p,sha in inputs.items()),
        'mount_policy_inputs_changed_during_binding')
    result=dict(board_hint=board_hint,canonical_directory=str(directory),inputs=inputs,
        policy_fingerprint=loaded.get('fingerprint'),electrical_projections=contexts,
        selected_terminals=sorted(terminals),no_electrical_role_or_current_authority=True)
    return json.loads(json.dumps(result,sort_keys=True,allow_nan=False))

def isolated(board,fp,main,satellites,*,deadline):
    """Conservative native full-envelope proof, including all foreign net0.

    The disk includes the main bore too: no missing/hollow native shape can
    conceal foreign metal in an old/new drill void. It is rejection-only.
    """
    import cec_fr as fr
    import cec_native_fill_geometry as fills
    own=list(fp.Pads());enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    faces=sorted(set(map(int,main.GetLayerSet().CuStack()))&enabled)
    need(faces and len(own)==9 and len(satellites)==8,'complete_unassigned_mount_faces_required')
    need(all(p.GetNetCode()==0 and not p.GetNetname()for p in own),
        'uniform_literal_unassigned_mount_terminal_required')
    need(all(tuple(p.GetOffset())==(0,0)and p.Padstack().Mode()==pcbnew.PADSTACK.MODE_NORMAL
        for p in own),'ordinary_centered_unassigned_mount_padstack_required')
    need(fp.GetParentGroup()is None and all(p.GetParentGroup()is None for p in own),
        'unassigned_mount_has_unowned_native_group')
    # PAD.IsLocked includes the footprint's inherited anchor lock. Direct
    # pad-lock edit authority is checked from literal Source pad nodes by
    # the owning reconciler, not inferred from that combined native flag.
    radius=int(main.GetSize().x)//2
    for pad in satellites:
        tick(deadline);x,y=map(int,pad.GetFPRelativePosition());size=int(pad.GetSize().x)
        available=2*radius-size
        need(available>=0 and (2*x)**2+(2*y)**2<=available**2,
            'satellite_outside_unchanged_main_land_envelope')
    center=main.GetPosition();circle=pcbnew.SHAPE_CIRCLE(center,(int(main.GetSize().x)+1)//2)
    resolve=fr._foreign_clearance_resolver(board)
    gap=max(0,int(board.GetDesignSettings().m_MinClearance))
    others=[p for owner in board.GetFootprints()if force._uid(owner)!=force._uid(fp)for p in owner.Pads()]
    others+=list(board.GetTracks());zones=list(board.Zones())
    artwork=[*board.GetDrawings(),*(g for owner in board.GetFootprints()for g in owner.GraphicalItems())]
    need(len(others)+len(zones)+len(artwork)<=16384,'unassigned_mount_native_inventory_bound')
    checked=0;zone_hashes={}
    for face in faces:
        for item in others:
            tick(deadline)
            if not item.IsOnLayer(face):continue
            need(not item.GetEffectiveShape(face).Collide(circle,max(gap,resolve(item,face))),
                'unassigned_mount_envelope_has_foreign_copper:'+force._uid(item))
            checked+=1
        for item in artwork:
            tick(deadline)
            if int(item.GetLayer())!=face:continue
            need(not item.GetEffectiveShape().Collide(circle,gap),
                'unassigned_mount_envelope_has_copper_artwork:'+force._uid(item))
            checked+=1
        for zone in zones:
            tick(deadline)
            if zone.GetIsRuleArea()or not zone.IsOnLayer(face):continue
            need(zone.IsFilled()and zone.HasFilledPolysForLayer(face),
                'unassigned_mount_requires_complete_actual_saved_fills')
            poly=zone.GetFilledPolysList(face)
            need(not poly.Collide(circle,max(gap,int(zone.GetLocalClearance()),resolve(zone,face))),
                'unassigned_mount_envelope_has_filled_copper:'+force._uid(zone))
            zone_hashes[force._uid(zone)+':'+str(face)]=fills.identity(poly,deadline)[0];checked+=1
    tick(deadline)
    return dict(complete=True,isolated=True,main_pad_uuid=force._uid(main),
        actual_faces=faces,foreign_shape_checks=checked,actual_zone_fill_identities=zone_hashes,
        net0_not_used_as_a_shared_net=True,outer_main_land_envelope_used=True,
        no_current_ground_or_factory_qualification=True)
