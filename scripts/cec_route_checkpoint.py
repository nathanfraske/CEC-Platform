"""Bounded atomic route work, never a fabrication or routing certificate.

Each worker owns two flat slots. A completed stage is only an untrusted proposal
until the coordinator checks its entire file family and freshly grades it. No
reader scans arbitrary temporary PCBs, and a killed writer cannot replace the
last committed pointer with a partial copy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from cec_placement_checkpoint import atomic_json, sha, source_valid

STAGES = frozenset((
    'local_power_prefix', 'precision_route', 'critical_pair_fallback',
    'critical_control_route', 'priority_power_local_pin_access',
    'pre_power_signal_access', 'priority_current_route',
    'priority_power_distribution', 'routed_power_reuse',
    'routed_power_compile', 'automatic_pin_escape', 'detailed_route',
    'decoupler_cell_finish'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
        separators=(',', ':')).encode()).hexdigest()


def read_slot(root, slot, *, context):
    root = Path(root).resolve()
    if slot not in ('slot-0', 'slot-1'):
        raise ValueError('invalid route checkpoint slot')
    directory = root / slot
    if directory.is_symlink() or not directory.resolve().is_relative_to(root):
        raise ValueError('route checkpoint slot escapes its store')
    certificate = directory / 'checkpoint.json'
    if certificate.is_symlink():
        raise ValueError('route checkpoint certificate cannot be a symlink')
    row = json.loads(certificate.read_text())
    if (row.get('schema') != 1 or row.get('kind') != 'unadmitted-route-work'
            or row.get('context') != context or row.get('stage') not in STAGES
            or row.get('release_accepted') is not False
            or row.get('routing_admitted') is not False
            or row.get('board') != str(directory / 'board.kicad_pcb')
            or not source_valid(row.get('sources') or [])):
        raise ValueError('route checkpoint identity or source authority changed')
    files = row.get('artifacts') or []
    if (not files or len({f['name'] for f in files}) != len(files)
            or sum(f['name'] == 'board.kicad_pcb' for f in files) != 1):
        raise ValueError('route checkpoint lacks a unique board family')
    for item in files:
        path = directory / item['name']
        if (Path(item['name']).name != item['name'] or path.is_symlink()
                or not path.is_file() or sha(path) != item['sha256']
                or path.stat().st_size != item['size']):
            raise ValueError('route checkpoint artifact missing or changed')
    if sha(row['board']) != row.get('sha256'):
        raise ValueError('route checkpoint board digest mismatch')
    rank = row.get('rank')
    if (not isinstance(rank, list) or len(rank) != 2
            or any(type(v) is not int or v < 0 for v in rank)):
        raise ValueError('invalid route checkpoint native counts')
    return row


def committed(root, *, context):
    """Only pointer-referenced, digest-bound slots; unknown files are ignored."""
    root = Path(root)
    if not (root / 'current.json').exists():
        return [], []
    if root.is_symlink() or (root / 'current.json').is_symlink():
        raise ValueError('route checkpoint store/pointer cannot be a symlink')
    pointer = json.loads((root / 'current.json').read_text())
    entries = pointer.get('committed')
    if (pointer.get('context') != context or not isinstance(entries, list)
            or not 1 <= len(entries) <= 2
            or len({e['slot'] for e in entries}) != len(entries)):
        raise ValueError('route checkpoint pointer identity mismatch')
    accepted, refused = [], []
    for item in entries:
        try:
            row = read_slot(root, item['slot'], context=context)
            if sha(Path(row['board']).parent / 'checkpoint.json') != item['sha256']:
                raise ValueError('route checkpoint pointer digest mismatch')
            accepted.append(row)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            refused.append({'slot': item.get('slot'), 'error': str(exc)})
    return accepted, refused


class Store:
    def __init__(self, root, *, context, sources, max_family_bytes=64 * 1024**2):
        if Path(root).is_symlink():
            raise ValueError('route checkpoint store cannot be a symlink')
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.context = context
        identity = dict(schema=1, kind='route-checkpoint-store', context=context)
        owner = self.root / 'owner.json'
        if owner.exists():
            if owner.is_symlink() or json.loads(owner.read_text()) != identity:
                raise ValueError('route checkpoint ownership mismatch')
        elif any(self.root.iterdir()):
            raise ValueError('cannot adopt a nonempty route checkpoint store')
        else:
            atomic_json(owner, identity)
        self.sources = [{'path': str(Path(p).resolve()), 'sha256': sha(p)}
                        for p in sources]
        self.max_family_bytes = int(max_family_bytes)
        if self.max_family_bytes <= 0:
            raise ValueError('invalid checkpoint storage bound')

    def publish(self, source, *, stage, rank, copier):
        if stage not in STAGES or (not isinstance(rank, list) or len(rank) != 2
                or any(type(v) is not int or v < 0 for v in rank)):
            raise ValueError('invalid completed route stage or measured counts')
        previous, errors = committed(self.root, context=self.context)
        if errors:
            raise ValueError('prior committed checkpoint is damaged')
        if previous and rank >= min(row['rank'] for row in previous):
            return dict(published=False, reason='native_counts_not_improved')
        if not source_valid(self.sources):
            raise ValueError('route input authority changed before checkpoint')
        source = Path(source).resolve()
        original = sha(source)
        if source.stat().st_size > self.max_family_bytes:
            raise ValueError('route checkpoint exceeds storage bound')
        active = Path(previous[0]['board']).parent.name if previous else 'slot-1'
        slot = self.root / ('slot-1' if active == 'slot-0' else 'slot-0')
        if slot.is_symlink() or not slot.resolve().is_relative_to(self.root):
            raise ValueError('route checkpoint slot escapes its store')
        slot.mkdir(exist_ok=True)
        if source.is_relative_to(slot):
            raise ValueError('checkpoint source is its inactive slot')
        for old in slot.iterdir():
            if not old.is_file() or old.is_symlink():
                raise ValueError('unexpected entry in owned checkpoint slot')
        # Remove the inactive pointer entry BEFORE reusing its files. The
        # active complete family remains readable throughout a killed copy.
        kept = [row for row in previous if Path(row['board']).parent != slot]
        if kept:
            self._point(kept)
        for old in slot.iterdir():
            old.unlink()  # only this validated flat, inactive owned slot
        target = slot / 'board.kicad_pcb'
        copied = sorted({target, *(Path(p).resolve() for p in copier(source, target))})
        if any(p.parent != slot or p.is_symlink() or not p.is_file() for p in copied):
            raise ValueError('route checkpoint copy escaped its artifact family')
        if sum(p.stat().st_size for p in copied) > self.max_family_bytes:
            for path in copied:
                path.unlink()  # validated inactive owned flat slot only
            raise ValueError('route checkpoint family exceeds storage bound')
        if sha(target) != original or sha(source) != original:
            raise ValueError('route board changed while publishing')
        row = dict(schema=1, kind='unadmitted-route-work', context=self.context,
            board=str(target), sha256=original, stage=stage, rank=rank,
            routing_admitted=False, release_accepted=False,
            sources=self.sources, created_epoch=time.time(),
            artifacts=[dict(name=p.name, sha256=sha(p), size=p.stat().st_size)
                       for p in copied])
        atomic_json(slot / 'checkpoint.json', row)
        read_slot(self.root, slot.name, context=self.context)
        self._point([row, *kept])
        return dict(published=True, **row)

    def _point(self, rows):
        atomic_json(self.root / 'current.json', dict(schema=1, context=self.context,
            committed=[dict(slot=Path(row['board']).parent.name,
                sha256=sha(Path(row['board']).parent / 'checkpoint.json')) for row in rows]))


def publisher(root, cfg, source, seed):
    """Lazy per-worker callback; the native coordinator is the admission owner."""
    store = None

    def publish(*, stage, status, artifact):
        nonlocal store
        if status != 'passed' or stage not in STAGES or not artifact:
            return None
        import cec_full_pipeline as pipeline
        import cec_score
        if store is None:
            store = Store(root, context=context(cfg, source, seed),
                          sources=pipeline._source_files(cfg, source))
        score = cec_score.score(str(artifact))
        source_path = Path(artifact)
        family_bytes = sum(p.stat().st_size for p in source_path.parent.glob(
            source_path.stem + '.*') if p.is_file())
        if family_bytes > store.max_family_bytes:
            raise ValueError('route checkpoint source family exceeds storage bound')
        result = store.publish(artifact, stage=stage,
            rank=[score.drc, score.unconnected],
            copier=lambda a, b: pipeline._copy_sidecars(a, b, cfg=cfg))
        if result.get('published'):
            print('[route-checkpoint] %s saved: DRC %d / open %d (awaiting coordinator admission)'
                  % (stage, score.drc, score.unconnected), flush=True)
        return result
    return publish


def context(cfg, source, seed):
    return dict(family=cfg.board, source_sha256=sha(source), seed=int(seed),
                params_sha256=digest(cfg.params))


def optical_mark(footprint):
    """An actual unconnected optical mark, not an arbitrary FID-prefixed part."""
    return bool('fiducial' in str(footprint.GetFPIDAsString()).lower()
                and not any(p.GetNetCode() != 0 for p in footprint.Pads()))


def optical_preservation(source, target):
    """Receive only native translations of actual unconnected optical marks.

    Every other item, pad primitive, rule and fill is exact. The only sidecar
    update allowed is the translated mark's pose in the existing placement
    map. This grants neither functional placement nor copper ownership.
    """
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as native
    import cec_copper_echo as sexpr
    report = dict(ok=False, complete=False, release_authority=False,
                  grants_local_copper_ownership=False, errors=[])
    try:
        _, old = native._nodes(source)
        _, new = native._nodes(target)
        _, old_fixed = force._preservation_snapshot(source)
        _, new_fixed = force._preservation_snapshot(target)
        if old.keys() != new.keys() or old_fixed != new_fixed:
            raise ValueError('optical_move_changed_native_inventory_or_settings')
        first, last = (pcbnew.LoadBoard(str(p)) for p in (source, target))
        original = {fp.m_Uuid.AsString(): fp for fp in first.GetFootprints()}
        final = {fp.m_Uuid.AsString(): fp for fp in last.GetFootprints()}
        moved = {}
        for uid in old:
            if sexpr._freeze(old[uid]) == sexpr._freeze(new[uid]):
                continue
            if (uid not in original or uid not in final
                    or not optical_mark(original[uid]) or not optical_mark(final[uid])
                    or native._without(old[uid], 'at') != native._without(new[uid], 'at')
                    or original[uid].GetOrientationDegrees() != final[uid].GetOrientationDegrees()):
                raise ValueError('optical_move_changed_non_optical_item:' + uid)
            fp = final[uid]
            point = fp.GetPosition()
            moved[fp.GetReference()] = [point.x/1e6, point.y/1e6,
                                      fp.GetOrientationDegrees()]
        old_sidecars, new_sidecars = force._sidecars(source), force._sidecars(target)
        for suffix in old_sidecars.keys() | new_sidecars.keys():
            if old_sidecars.get(suffix) == new_sidecars.get(suffix):
                continue
            if suffix != '.pourfirst-state.json':
                raise ValueError('optical_move_changed_sidecar:' + suffix)
            prior = json.loads(Path(source).with_suffix(suffix).read_text())
            after = json.loads(Path(target).with_suffix(suffix).read_text())
            if not isinstance(prior.get('placements'), dict):
                raise ValueError('optical_move_placement_map_unknown')
            for ref, pose in moved.items():
                if ref not in prior['placements']:
                    raise ValueError('optical_move_placement_ref_unknown')
                prior['placements'][ref] = pose
            if prior != after:
                raise ValueError('optical_move_changed_non_optical_placement_authority')
        report.update(ok=True, complete=True, moved_refs=sorted(moved),
                      original_copper_pads_rules_fills_exact=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    return report


def physical_zones(rows, nets):
    """Manufactured zone declarations, not regenerated KiCad object IDs."""
    return sorted(repr(row[1:]) for row in rows if not row[3] and row[1] in nets)


def normalize_complete_pair_additions(parent, source, out, cfg, *, max_vias=8):
    """Bounded removal of new via stubs on previously complete qualified pairs.

    Never remove source copper or reroute a pair. This only proposes deleting
    via geometry absent from the parent's fully connected pair contract;
    independent native preservation/score/physics must prove the result.
    """
    import pcbnew
    import cec_fr, cec_placement_route_prefix as pairs
    import cec_full_pipeline as pipeline
    contract = pairs.capture(str(parent))
    if pairs.check_qualified_pairs(str(source), contract).get('ok'):
        return str(source), dict(changed=False)
    nets = {row[key] for row in contract.get('qualified_critical_pairs', ())
            if row.get('qualified') for key in ('p','n')}
    original = pcbnew.LoadBoard(str(parent))
    board = pcbnew.LoadBoard(str(source))
    def via_key(item):
        p = item.GetPosition()
        return (item.GetNetname(), p.x, p.y, item.TopLayer(), item.BottomLayer(),
                item.GetWidth(item.TopLayer()), item.GetDrillValue())
    owned = {via_key(t) for t in original.GetTracks() if t.GetClass() == 'PCB_VIA'}
    additions = [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA'
                 and t.GetNetname() in nets and via_key(t) not in owned]
    if not additions or len(additions) > max_vias:
        raise ValueError('qualified pair changed without a bounded generated-via correction')
    target = Path(out) / 'board.kicad_pcb'
    pipeline._copy_sidecars(source, target, cfg=cfg)
    removed = [dict(uuid=t.m_Uuid.AsString(), net=t.GetNetname()) for t in additions]
    # Remove() transfers borrowed proxies to Python ownership and can tear
    # down KiCad 10's SWIG registry when this function returns. Native Delete
    # is the shared lifetime-safe operation for permanent, proved removals.
    from cec_native_items import discard_items
    discard_items(board, additions)
    pcbnew.SaveBoard(str(target), board)
    if not cec_fr.refill_zones_isolated(str(target)):
        raise ValueError('pair-addition correction refill refused')
    # The later assembly allocator may move non-electrical optical marks;
    # require all other native continuation terms here, including zero lost
    # input copper. Full incumbent gates still decide selection afterwards.
    proof = preservation(parent, target, cfg)
    pipeline.atomic_json(Path(out) / 'preservation.json', proof)
    if not proof.get('ok'):
        raise ValueError('generated pair-via removal failed native continuation admission')
    return str(target), dict(changed=True, removed=removed,
                            preservation=str(Path(out) / 'preservation.json'))


def assembly_normalize(source, out, cfg):
    """One existing generic allocator pass on a private copy, no route changes.

    Assembly marks are movable around finished copper. Functional placements,
    source bytes and every track/via remain owned by the independent admission
    below, and the full oracle must still pass every previous incumbent gate.
    """
    import cec_synth_pipeline as synth, cec_full_pipeline as pipeline
    import pcbnew
    before = synth._oracle_fiducials(str(source))
    if before.get('ok'):
        return str(source), dict(changed=False, before=before)
    board = pcbnew.LoadBoard(str(source))
    fids = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith('FID')]
    if not fids or not all(optical_mark(fp) for fp in fids):
        raise ValueError('assembly repair requires unconnected optical fiducial footprints')
    import cec_force_current
    target = cec_force_current._copy_family(source, Path(out))
    repair = synth.repair_fiducials_to_edge_band(str(target), allow_existing_copper=True)
    if not repair.get('ok') or not synth._oracle_fiducials(str(target)).get('ok'):
        raise ValueError('bounded assembly mark relocation refused')
    exact = optical_preservation(source, target)
    proof = preservation(source, target, cfg)
    proof['exact_optical_translation'] = exact
    if not proof.get('ok') or not exact.get('ok') or not exact.get('complete'):
        raise ValueError('assembly relocation changed functional routing authority')
    pipeline.atomic_json(Path(out) / 'preservation.json', proof)
    return str(target), dict(changed=repair.get('changed'), before=before, repair=repair,
                            preservation=str(Path(out) / 'preservation.json'))


def preservation(source, target, cfg):
    """Independent additive continuation guard, not a release waiver."""
    import pcbnew
    import cec_fr, cec_ground_plane, cec_score, cec_stage_admission
    import cec_full_pipeline as pipeline, cec_synth_pipeline as synth
    import cec_placement_route_prefix as pairs
    import cec_local_power_prefix as power
    before_board = pcbnew.LoadBoard(str(source))
    after_board = pcbnew.LoadBoard(str(target))
    bound, _authority = synth.config_with_board_route_authority(cfg, str(target))
    with synth._oracle_env(bound.params):
        nets = {t.GetNetname() for t in before_board.GetTracks()}
        contract = cec_fr.copper_geometry_prefix_contract(str(source), nets)
        copper = cec_fr.check_copper_geometry_prefix(str(target), contract)
        # Retaining source copper/pairs does not require authority to replace
        # an unresolved local power solve. This contract grants no such right;
        # actual frozen-power obligations below still have to be proved.
        pair_contract = pairs.capture(str(source), include_local_authority=False)
        pair = pairs.check_qualified_pairs(str(target), pair_contract)
        parent_state = Path(source).with_suffix('.pourfirst-state.json')
        parent = json.loads(parent_state.read_text()) if parent_state.is_file() else {}
        child_state = Path(target).with_suffix('.pourfirst-state.json')
        child = json.loads(child_state.read_text()) if child_state.is_file() else {}
        required = set(parent.get('frozen_nets') or ()) | set(child.get('frozen_nets') or ())
        physically_owned = required & {z.GetNetname() for z in before_board.Zones()
                                      if not z.GetIsRuleArea()}
        physically_owned.update(z.GetNetname() for z in before_board.Zones()
                                if not z.GetIsRuleArea() and z.GetNetname() != 'GND')
        def zones(board):
            return physical_zones(cec_ground_plane._zone_declaration_signature(board), physically_owned)
        before = cec_score.score(str(source))
        after = cec_score.score(str(target))
        score = cec_stage_admission.evaluate(before, after)
        proofs = synth._priority_power_authority_isolated(str(target), sorted(required)) if required else {}
        connected = power.power_connected(proofs, required, after.detail.get('unconn_nets') or ())
    poses = pipeline._placement_position_signature(source) == pipeline._placement_position_signature(target)
    snapshot_a = pipeline._placement_board_snapshot(source)
    snapshot_b = pipeline._placement_board_snapshot(target)
    first, last = snapshot_a['placements'], snapshot_b['placements']
    moved = {ref for ref in first if first[ref] != last.get(ref)}
    first_marks = {fp.GetReference() for fp in before_board.GetFootprints() if optical_mark(fp)}
    last_marks = {fp.GetReference() for fp in after_board.GetFootprints() if optical_mark(fp)}
    assembly_only = bool(set(first) == set(last) and moved <= first_marks & last_marks
        and snapshot_a['back_refs'] == snapshot_b['back_refs']
        and (not moved or synth._oracle_fiducials(str(target)).get('ok')))
    outline = snapshot_a.get('outline_mm') == snapshot_b.get('outline_mm')
    return dict(ok=bool(copper['ok'] and pair['ok'] and (poses or assembly_only) and outline
                and zones(before_board) == zones(after_board) and score['accepted'] and connected),
        parent_copper=copper, qualified_pairs=pair, retention_only=True,
        grants_local_copper_ownership=False, placement_unchanged=poses,
        functional_placement_unchanged=bool(poses or assembly_only),
        assembly_only_moves=sorted(moved) if assembly_only else [],
        outline_unchanged=outline, power_zones_unchanged=zones(before_board) == zones(after_board),
        score_admission=score, power_obligations=dict(required=sorted(required),
            proofs=proofs, ok=connected), release_accepted=False)
