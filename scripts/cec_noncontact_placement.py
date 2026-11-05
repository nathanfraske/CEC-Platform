"""Move electrically detached SMDs while retaining the entire native board.

This is a deliberately narrow proposal materializer, not copper qualification.
It never acquires route ownership, strips copper, refreshes a netlist, refills
zones, or accepts a board. Native DRC/craft and source freshness remain the
caller's admission gates. Attached packages require an owned route transaction.
"""
from pathlib import Path
import hashlib
import json
import math
import shutil
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


REPORT_SUFFIXES = ('.cellreport.json', '.railreport.json')


def _report_dependencies(report, footprint_nets):
    """Conservative observation scope, never a fabricated component name.

    Freeze native references mentioned anywhere in the structured report,
    plus every terminal owner on its explicitly preserved/constructed force
    nets. This also retains future-return/failed-portal observations verbatim.
    The caller additionally supplies all declared blueprint members.
    """
    refs = set(footprint_nets)
    selected = set()
    def walk(value):
        if isinstance(value, str) and value in refs:
            selected.add(value)
        elif isinstance(value, dict):
            for key,item in value.items():
                if key in ('ref','owner_ref','anchor_ref','cap_ref') and isinstance(item,str) and item not in refs:
                    raise ValueError('construction report references an absent native member')
                walk(key);walk(item)
        elif isinstance(value, list):
            for item in value:walk(item)
    walk(report)
    nets=set(report.get('preserved_nets') or ())
    for row in ((report.get('force_lanes') or {}).get('results') or {}).values():
        if isinstance(row,dict):nets.update(row.get('nets') or ())
    selected.update(ref for ref,owned in footprint_nets.items() if nets & owned)
    return selected


def bind(path, candidate, *, immutable_refs=(), retain_reports=False,
         freeze_native_dependencies=False):
    """Bind an immutable source and unchanged outline/face/population domain."""
    path = Path(path).resolve()
    fixed=set(immutable_refs)
    reports={}
    domain = None
    if retain_reports or freeze_native_dependencies:
        import pcbnew
        board=pcbnew.LoadBoard(str(path))
        footprint_nets={fp.GetReference():{p.GetNetname() for p in fp.Pads()} for fp in board.GetFootprints()}
        if set(footprint_nets)!=set(candidate.P) or not fixed<=set(footprint_nets):
            raise ValueError('construction evidence population mismatch')
        for suffix in (REPORT_SUFFIXES if retain_reports else ()):
            report_path=path.with_suffix(suffix)
            if not report_path.is_file():continue
            report=json.loads(report_path.read_text())
            if (report.get('schema')!=1 or report.get('board')!=path.name
                    or type(report.get('total')) is not int or report['total']<0
                    or type(report.get('laid')) is not int or not 0<=report['laid']<=report['total']):
                raise ValueError('construction evidence identity/count mismatch')
            members=_report_dependencies(report,footprint_nets)|fixed
            fixed.update(members)
            reports[suffix]=dict(sha256=sha(report_path),members=sorted(members))
        if freeze_native_dependencies:
            # Publish the narrow native search domain BEFORE spending exact
            # route trials. This is not an ownership waiver: attached parts,
            # holes, copper graphics and same-layer zones stay immovable.
            footprints=list(board.GetFootprints())
            if any(not _same_pose(candidate.P[fp.GetReference()],_pose(fp)) for fp in footprints):
                raise ValueError('noncontact search must bind the exact source poses')
            tracks=list(board.GetTracks())
            zone_layers={layer for zone in board.Zones() for layer in zone.GetLayerSet().CuStack()}
            reasons={}
            for fp in footprints:
                ref=fp.GetReference();pads=list(fp.Pads());why=[]
                if ref in fixed:why.append('declared_or_construction_member')
                if fp.IsLocked():why.append('locked')
                if not pads or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                        or p.GetDrillSize().x or p.GetDrillSize().y for p in pads):
                    why.append('requires_hole_free_smd')
                if (any(item.GetLayer()==pcbnew.Edge_Cuts or item.GetLayer() in board.GetEnabledLayers().CuStack()
                        for item in fp.GraphicalItems()) or list(fp.Zones())):
                    why.append('boundary_or_copper_graphics')
                if any(set(p.GetLayerSet().CuStack()) & zone_layers for p in pads):
                    why.append('zone_coupled_layer')
                peers=[pad for other in footprints if other is not fp for pad in other.Pads()]
                if _contact(fp,tracks+peers):why.append('native_copper_attachment')
                if why:fixed.add(ref);reasons[ref]=why
            domain=dict(schema=1,movable_refs=sorted(set(candidate.P)-fixed),
                immutable_reasons=reasons,release_authority=False,grants_copper_ownership=False)
    contract = dict(schema=1, purpose='noncontact-placement-proposal',
                source=str(path), source_sha256=sha(path),
                rules={suffix:sha(path.with_suffix(suffix))
                       for suffix in ('.kicad_pro','.kicad_dru')
                       if path.with_suffix(suffix).is_file()},
                outline_mm=[float(candidate.W),float(candidate.H)],
                back_refs=sorted(candidate.back_refs or ()),
                immutable_refs=sorted(fixed), reports=reports,
                release_authority=False, grants_copper_ownership=False)
    if domain is not None:contract['native_domain']=domain
    return contract


def _pose(fp):
    point = fp.GetPosition()
    return point.x/1e6, point.y/1e6, fp.GetOrientationDegrees()


def _same_pose(a,b):
    return (abs(a[0]-b[0])<=1e-6 and abs(a[1]-b[1])<=1e-6
            and abs((a[2]-b[2]+180)%360-180)<=1e-6)


def _native_text(board):
    """Serialize without SaveBoard's connectivity mutation/format setup."""
    import pcbnew
    with tempfile.TemporaryDirectory(prefix='cec-native-snapshot-') as work:
        path=Path(work)/'board.kicad_pcb'
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
        return path.read_bytes()


def _contact(fp, tracks):
    """Any original/new contact, including foreign nets, requires an owner."""
    for pad in fp.Pads():
        for item in tracks:
            layers = set(pad.GetLayerSet().CuStack()) & set(item.GetLayerSet().CuStack())
            if any(pad.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer),0)
                   for layer in layers):
                return dict(pad=pad.GetNumber(),copper_uuid=item.m_Uuid.AsString())
    return None


def materialize(candidate, output):
    """Write only a proved non-contact delta to a distinct proposal file.

    Saving can itself alter native net assignments. Restore moved poses in a
    reloaded diagnostic object and require its *entire* native serialization
    to equal the baseline, not just a same-track-count check. The real output
    retains the proposed positions. No in-place/source commit is allowed.
    """
    import pcbnew
    from cec_local_copper_cell import copper_inventory
    contract = candidate.noncontact_placement_contract
    source, output = Path(contract['source']).resolve(), Path(output).resolve()
    if (contract.get('schema') != 1 or contract.get('purpose') != 'noncontact-placement-proposal'
            or contract.get('release_authority') is not False
            or contract.get('grants_copper_ownership') is not False):
        raise ValueError('invalid noncontact placement contract')
    def check_source():
        current_rules={ext:sha(source.with_suffix(ext))
                       for ext in ('.kicad_pro','.kicad_dru') if source.with_suffix(ext).is_file()}
        if sha(source) != contract['source_sha256'] or current_rules != contract['rules']:
            raise ValueError('noncontact placement source/rules changed')
        for suffix,row in contract.get('reports',{}).items():
            if suffix not in REPORT_SUFFIXES or sha(source.with_suffix(suffix))!=row['sha256']:
                raise ValueError('noncontact construction evidence changed')
    check_source()
    if source == output:
        raise ValueError('noncontact placement requires a distinct proposal output')
    if ([float(candidate.W),float(candidate.H)] != contract['outline_mm'] or
            sorted(candidate.back_refs or ()) != contract['back_refs']):
        raise ValueError('noncontact placement cannot change outline or faces')
    board = pcbnew.LoadBoard(str(source))
    if board is None:
        raise ValueError('noncontact placement source unreadable')
    footprints = {fp.GetReference():fp for fp in board.GetFootprints()}
    if len(footprints) != len(list(board.GetFootprints())) or set(footprints) != set(candidate.P):
        raise ValueError('noncontact placement population mismatch')
    if sorted(ref for ref,fp in footprints.items() if fp.IsFlipped()) != contract['back_refs']:
        raise ValueError('noncontact placement source face mismatch')
    old = {ref:_pose(fp) for ref,fp in footprints.items()}
    moved = []
    for ref,pose in candidate.P.items():
        if len(pose)!=3 or not all(math.isfinite(float(v)) for v in pose):
            raise ValueError('noncontact placement requires finite poses')
        if not _same_pose(pose,old[ref]):
            moved.append(ref)
    tracks = list(board.GetTracks())
    if set(moved)&set(contract.get('immutable_refs',())):
        raise ValueError('noncontact placement would invalidate construction evidence members')
    copper_before = copper_inventory(board)
    original = _native_text(board)
    zone_layers = {layer for zone in board.Zones() for layer in zone.GetLayerSet().CuStack()}
    def contacts(ref):
        peers = [pad for other,fp in footprints.items() if other!=ref for pad in fp.Pads()]
        return _contact(footprints[ref],tracks+peers)
    for ref in moved:
        fp = footprints[ref]
        pads = list(fp.Pads())
        if (fp.IsLocked() or not pads or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or p.GetDrillSize().x or p.GetDrillSize().y for p in pads)):
            raise ValueError('noncontact placement requires unlocked hole-free SMD: '+ref)
        if (any(item.GetLayer()==pcbnew.Edge_Cuts or item.GetLayer() in board.GetEnabledLayers().CuStack()
                for item in fp.GraphicalItems()) or list(fp.Zones())):
            raise ValueError('noncontact placement cannot move boundaries/copper graphics: '+ref)
        if any(set(p.GetLayerSet().CuStack()) & zone_layers for p in pads):
            raise ValueError('noncontact placement requires zone-disjoint pad layers: '+ref)
        if contacts(ref):
            raise ValueError('noncontact placement original copper attachment: '+ref)
    for ref in moved:
        x,y,angle = candidate.P[ref]
        footprints[ref].SetPosition(pcbnew.VECTOR2I_MM(x,y))
        footprints[ref].SetOrientationDegrees(angle)
    if any(contacts(ref) for ref in moved):
        raise ValueError('noncontact placement would create copper contact')
    # The normalizers and whole-board proof run on disposable native objects.
    # A failed save/reload proof never replaces an existing output.
    with tempfile.TemporaryDirectory(prefix='cec-noncontact-') as work:
        trial = Path(work)/'board.kicad_pcb'
        if moved:
            pcbnew.SaveBoard(str(trial),board)
            restored = pcbnew.LoadBoard(str(trial))
            if restored is None or copper_inventory(restored) != copper_before:
                raise ValueError('noncontact placement native copper changed during save')
            for ref in moved:
                fp = restored.FindFootprintByReference(ref)
                if fp is None or not _same_pose(_pose(fp),candidate.P[ref]):
                    raise ValueError('noncontact placement saved pose mismatch')
                x,y,angle=old[ref]
                fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.SetOrientationDegrees(angle)
            if _native_text(restored) != original:
                raise ValueError('noncontact placement changed more than declared poses')
        else:
            shutil.copy2(source,trial)
        check_source()
        output.parent.mkdir(parents=True,exist_ok=True)
        for ext in ('.kicad_pro','.kicad_dru','.kicad_prl'):
            if source.with_suffix(ext).is_file():
                shutil.copy2(source.with_suffix(ext),output.with_suffix(ext))
        for suffix,row in contract.get('reports',{}).items():
            report=json.loads(source.with_suffix(suffix).read_text())
            report['board']=output.name
            report['noncontact_retention']=dict(
                source_sha256=contract['source_sha256'],source_report_sha256=row['sha256'],
                output_sha256=sha(trial),unchanged_members=row['members'],
                exact_native_remainder_preserved=True,release_authority=False)
            from cec_placement_checkpoint import atomic_json
            atomic_json(output.with_suffix(suffix),report)
        shutil.copy2(trial,output)
    return str(output)
