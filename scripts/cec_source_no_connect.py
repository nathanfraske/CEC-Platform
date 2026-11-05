"""Literal current-schematic no-connect evidence for an isolated PCB land.

One-terminal nets and names such as 'unconnected' are not intent authority.
Require one matching current-project symbol, an exact marker on its actual
pin, no wire/label/peer at that point, and no native same-net copper. This
records an unchanged design decision, not electrical or release approval.
"""
import math
from pathlib import Path
import time

import cec_board_policy as policy
import cec_beta_manifest as manifest
import cec_force_current as force
import cec_sch_lint as schematic
from cec_footprint_fields import footprint_properties


def _root(board,board_hint):
    declared=Path(board_hint)
    if declared.suffix=='.kicad_sch':
        if not declared.is_file():raise ValueError('declared_noconn_schematic_missing')
        return declared.resolve()
    located=policy.policy_path(board.GetFileName(),board_hint=board_hint)
    directory=Path(located).resolve().parent if located else (
        declared.resolve().parent if declared.is_file() else Path(board.GetFileName()).resolve().parent)
    for project in manifest.PROJECTS:
        if directory==(Path(policy.ROOT)/'beta'/project['directory']).resolve():
            root=directory/project['schematic']
            if not root.is_file():raise ValueError('current_manifest_noconn_schematic_missing')
            return root
    # Never choose an alphabetically convenient leaf or obsolete flat sheet.
    # Outside the current manifest, an explicit root or one unique sibling
    # schematic is required before any no-connect exemption is possible.
    siblings=list(directory.glob('*.kicad_sch'))
    return siblings[0].resolve() if len(siblings)==1 else None


def _nm(point):return tuple(round(v*1e6) for v in point)


def bindings_current(proofs):
    """Check only independently derived proof bindings, never grant intent."""
    if type(proofs) is not list or len(proofs)>64:raise ValueError('bounded_source_noconn_proofs_required')
    files={}
    for proof in proofs:
        if proof.get('scope')!='literal_current_schematic_no_connect_and_isolated_native_land':
            raise ValueError('typed_source_noconn_proof_required')
        hashes=proof.get('schematic_files_sha256')
        if type(hashes) is not dict or not 1<=len(hashes)<=64:raise ValueError('bounded_source_noconn_files_required')
        for path,digest in hashes.items():
            if (type(path) is not str or not path or type(digest) is not str or len(digest)!=64
                    or path in files and files[path]!=digest):raise ValueError('exact_source_noconn_file_binding_required')
            files[path]=digest
    return all(force._hash(Path(path))==digest for path,digest in files.items())


def plan(board,pad_uuid,*,board_hint,timeout_s=10.):
    return plan_many(board,[pad_uuid],board_hint=board_hint,timeout_s=timeout_s)[pad_uuid]


def plan_many(board,pad_uuids,*,board_hint,timeout_s=10.):
    """One fresh bounded Source snapshot; no cross-invocation cache or proof input."""
    if (type(board_hint) is not str or not board_hint
            or type(pad_uuids) not in (list,tuple) or not 1<=len(pad_uuids)<=64
            or any(type(u)is not str or not u for u in pad_uuids)
            or len(set(pad_uuids))!=len(pad_uuids)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_source_noconn_context_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_noconn_deadline')
    from cec_cell_row_rebuild import _source_binding
    binding=_source_binding(board);pads=[p for f in board.GetFootprints() for p in f.Pads()]
    tracks=list(board.GetTracks());zones=list(board.Zones())
    if len(pads)+len(tracks)>16384:raise ValueError('source_noconn_native_inventory_bound')
    inventory={}
    for p in pads:inventory.setdefault(force._uid(p),[]).append(p)
    if any(len(inventory.get(u,[]))!=1 for u in pad_uuids):
        raise ValueError('unique_source_noconn_land_required')
    graphics=[*board.GetDrawings(),*(g for f in board.GetFootprints() for g in f.GraphicalItems())]
    eligible=[];result={u:None for u in pad_uuids}
    for u in pad_uuids:
        tick();pad=inventory[u][0];net=pad.GetNetCode()
        if (net>0 and len([p for p in pads if p.GetNetCode()==net])==1
                and not any(t.GetNetCode()==net for t in tracks)
                and not any(z.GetNetCode()==net and not z.GetIsRuleArea() for z in zones)
                and not any(getattr(g,'GetNetCode',lambda:0)()==net for g in graphics)):
            eligible.append(pad)
    root=_root(board,board_hint) if eligible else None
    queue=[root];files={};hashes={};total=0
    if root is None:queue=[]
    while queue:
        tick();path=queue.pop(0)
        if path in files:raise ValueError('source_noconn_repeated_or_cyclic_sheet_instance')
        if not path.is_file():raise ValueError('source_noconn_hierarchy_file_missing')
        size=path.stat().st_size;total+=size
        if len(files)>=64 or size>4*1024*1024 or total>16*1024*1024:
            raise ValueError('source_noconn_schematic_inventory_bound')
        hashes[str(path)]=force._hash(path);sf=schematic.SchFile(str(path));files[path]=sf
        for sheet in sf.sheets:
            if not sheet['file']:raise ValueError('source_noconn_missing_declared_sheet_file')
            queue.append((path.parent/sheet['file']).resolve())
    if root is not None:
        for pad in eligible:
            tick();result[force._uid(pad)]=_land_proof(pad,root,files,hashes,binding,tick)
    tick()
    if hashes!={str(p):force._hash(p) for p in files} or binding!=_source_binding(board):
        raise ValueError('source_noconn_schematic_or_native_epoch_changed')
    tick()
    return result


def _land_proof(pad,root,files,hashes,binding,tick):
    fp=pad.GetParentFootprint();pad_uuid=force._uid(pad)
    selected=[(path,sf,symbol) for path,sf in files.items() for symbol in sf.symbols
        if symbol['ref']==fp.GetReference()]
    if not selected:return None
    if len(selected)!=1:raise ValueError('unique_current_schematic_noconn_symbol_required')
    path,sf,symbol=selected[0]
    blocks=[block for tag,block in sf.children if tag=='symbol'
        and schematic.prop_value(block,'Reference')==fp.GetReference()]
    if len(blocks)!=1:raise ValueError('unique_current_schematic_noconn_instance_required')
    block=blocks[0];props=footprint_properties(fp)
    for name,expected in [('Value',fp.GetValue()),('Footprint',fp.GetFPIDAsString()),('MPN',props.get('MPN'))]:
        if not expected or schematic.prop_value(block,name)!=expected:
            raise ValueError('current_schematic_noconn_component_identity_mismatch:'+name)
    if '(mirror ' in block or symbol['pos'][2]%90:
        raise ValueError('supported_exact_schematic_noconn_transform_required')
    pins=[p for p in symbol['pins'] if p['num']==pad.GetNumber()]
    if len(pins)!=1:raise ValueError('unique_current_schematic_noconn_pin_required')
    at=_nm(pins[0]['pos']);markers=[m for m in sf.no_connects if _nm(m['pos'])==at]
    if not markers:return None
    if len(markers)!=1 or not markers[0]['uuid']:
        raise ValueError('unique_exact_schematic_noconn_marker_required')
    occupied=[p for s in sf.symbols for p in s['pins'] if _nm(p['pos'])==at]
    if len(occupied)!=1:raise ValueError('source_noconn_marker_has_other_pin_contact')
    if (any(_nm(v['pos'])==at for v in [*sf.labels,*sf.junctions])
            or any(_nm(p['pos'])==at for s in sf.sheets for p in s['pins'])):
        raise ValueError('source_noconn_marker_has_other_declared_contact')
    for wire in sf.wires:
        tick();points=list(map(_nm,wire['pts']))
        for a,b in zip(points,points[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1];px,py=at[0]-a[0],at[1]-a[1]
            if a==b and at!=a:continue
            if dx*py==dy*px and 0<=px*dx+py*dy<=dx*dx+dy*dy:
                raise ValueError('source_noconn_marker_has_wire_contact')
    tick()
    return dict(scope='literal_current_schematic_no_connect_and_isolated_native_land',pad_uuid=pad_uuid,
        owner=fp.GetReference(),pin=pad.GetNumber(),net=str(pad.GetNetname()),
        root_schematic=str(root),schematic=str(path),schematic_files_sha256=hashes,
        symbol_uuid=symbol['uuid'],marker_uuid=markers[0]['uuid'],schematic_pin_at_nm=list(at),
        source_native_binding=binding,unchanged_no_connect_not_a_routing_failure=True,
        manufacturer_electrical_use_qualified=False,current_authority=False,release_authority=False)
