"""Reviewed native physical envelopes, independent of RF exclusion policy.

Package-specific facts live in a hash-bound library catalog, not board/refdes
exceptions. Unregistered packages are explicitly outside this check's scope.
Repair restores only catalog-authorized graphics in a private proposal; copper,
pose, fields, locks, groups and all unrelated items must survive exact replay.
This is nominal body coverage, not tolerance, stack, current or fab signoff.
"""
from pathlib import Path
import copy
import hashlib
import json
import tempfile

import cec_swig_guard
import pcbnew
cec_swig_guard.pin()

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'lib/vendor/physical-body-contracts.json'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contracts(path=CATALOG):
    path = Path(path).resolve()
    data = json.loads(path.read_text())
    if data.get('schema') != 1 or not isinstance(data.get('contracts'), list):
        raise ValueError('physical_body_catalog_invalid')
    out = {}
    for entry in data['contracts']:
        template = (ROOT / entry['template']).resolve()
        if not template.is_relative_to(ROOT / 'lib'):
            raise ValueError('physical_body_template_outside_library')
        if _hash(template) != entry['template_sha256']:
            raise ValueError('physical_body_template_changed_requires_review')
        if (not entry.get('source') or len(entry.get('nominal_body_mm', ())) != 2
                or any(v <= 0 for v in entry['nominal_body_mm'])
                or set(entry.get('repair_layers', ())) !=
                    {'F.CrtYd', 'B.CrtYd', 'F.SilkS', 'B.SilkS'}):
            raise ValueError('physical_body_contract_invalid')
        for libid in entry['footprints']:
            if libid in out:
                raise ValueError('physical_body_contract_ambiguous')
            out[libid] = dict(entry, template_path=str(template))
    return out


def _placed_template(fp, entry):
    path = Path(entry['template_path'])
    result = pcbnew.FootprintLoad(str(path.parent), path.stem)
    if result is None:
        raise ValueError('physical_body_template_unloadable')
    # Flip() needs the live board's enabled-layer context on KiCad 10.
    # Merely parent the detached comparison object; do not add it to the board.
    result.SetParent(fp.GetBoard())
    if fp.IsFlipped():
        result.Flip(result.GetPosition(), False)
    result.SetOrientationDegrees(fp.GetOrientationDegrees())
    result.SetPosition(fp.GetPosition())
    layer = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    yard = result.GetCourtyard(layer)
    if yard.IsEmpty() or yard.OutlineCount() != 1:
        raise ValueError('physical_body_template_courtyard_invalid')
    return result


def _box(poly):
    if poly.IsEmpty():
        return None
    box = poly.BBox()
    return [box.GetLeft()/1e6, box.GetTop()/1e6,
            box.GetRight()/1e6, box.GetBottom()/1e6]


def _pad_signature(fp):
    rows = []
    for pad in fp.Pads():
        if pad.GetShape() == pcbnew.PAD_SHAPE_CUSTOM:
            raise ValueError('physical_body_custom_pad_datum_unqualified')
        rows.append((str(pad.GetNumber()), pad.GetAttribute(), pad.GetShape(),
            tuple(pad.GetPosition()), tuple(pad.GetSize()), tuple(pad.GetOffset()),
            float(pad.GetOrientationDegrees()) % 360,
            tuple(pad.GetDrillSize()), pad.GetDrillShape(),
            tuple(pad.GetLayerSet().Seq()), float(pad.GetRoundRectRadiusRatio()),
            float(pad.GetChamferRectRatio()), int(pad.GetChamferPositions())))
    return sorted(rows)


def audit(board, *, catalog=None):
    catalog = contracts() if catalog is None else catalog
    checked, uncovered = [], []
    for fp in board.GetFootprints():
        if fp.IsDNP():
            continue
        entry = catalog.get(fp.GetFPIDAsString())
        if entry is None:
            uncovered.append(dict(ref=fp.GetReference(), footprint=fp.GetFPIDAsString()))
            continue
        template = _placed_template(fp, entry)
        if _pad_signature(fp) != _pad_signature(template):
            raise ValueError('physical_body_package_datum_mismatch:'+fp.GetReference())
        layer = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
        required = template.GetCourtyard(layer)
        actual = fp.GetCourtyard(layer)
        missing = pcbnew.SHAPE_POLY_SET(required)
        if not actual.IsEmpty():
            missing.BooleanSubtract(actual)
        area_mm2 = abs(missing.Area())/1e12
        checked.append(dict(ref=fp.GetReference(), uuid=fp.m_Uuid.AsString(),
            footprint=fp.GetFPIDAsString(), ok=area_mm2 <= 1e-12,
            actual_bbox_mm=_box(actual), required_bbox_mm=_box(required),
            missing_area_mm2=area_mm2, template=entry['template_path'],
            template_sha256=entry['template_sha256'], source=entry['source'],
            nominal_body_mm=entry['nominal_body_mm'], tolerance_qualified=False))
    return dict(schema=1, ok=all(row['ok'] for row in checked), checked=checked,
        unregistered=uncovered, checked_packages=len(checked),
        coverage_complete=not uncovered, violations=[r for r in checked if not r['ok']],
        rf_keepout_authority=False, assembly_tolerance_authority=False,
        release_authority=False)


def _restore(board, ids, catalog):
    by_id = {fp.m_Uuid.AsString(): fp for fp in board.GetFootprints()}
    grouped = {item.m_Uuid.AsString() for group in board.Groups() for item in group.GetItems()}
    layers = {pcbnew.F_CrtYd, pcbnew.B_CrtYd, pcbnew.F_SilkS, pcbnew.B_SilkS}
    for uid in ids:
        fp = by_id[uid]
        template = _placed_template(fp, catalog[fp.GetFPIDAsString()])
        for item in list(fp.GraphicalItems()):
            if item.GetClass() != 'PCB_SHAPE' or item.GetLayer() not in layers:
                continue
            if item.m_Uuid.AsString() in grouped:
                raise ValueError('physical_body_graphic_has_external_group_owner')
            # Remove() transfers a borrowed SWIG proxy to Python ownership and
            # can tear down its type registry on KiCad 10. Native destruction
            # keeps the borrowed proxy invalidated instead of detached/reused.
            fp.Delete(item)
        for item in template.GraphicalItems():
            if item.GetClass() != 'PCB_SHAPE' or item.GetLayer() not in layers:
                continue
            new = item.Duplicate()
            new.SetParent(fp)
            # Duplicate() creates a fresh native UUID (m_Uuid is read-only).
            if new.m_Uuid.AsString() == item.m_Uuid.AsString():
                raise ValueError('physical_body_duplicate_has_no_fresh_identity')
            fp.Add(new)


def _normalized(path, ids):
    import cec_additive_route_receiving as receiving
    root, _ = receiving._nodes(path)
    root = copy.deepcopy(root)
    identifiers = []
    def collect(node):
        if not isinstance(node, list):
            return
        if node and node[0] == 'uuid':
            if len(node) != 2:
                raise ValueError('physical_body_native_uuid_invalid')
            identifiers.append(node[1])
        for row in node:
            if isinstance(row, list):
                collect(row)
    collect(root)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('physical_body_native_uuid_ambiguous')
    for node in root[1:]:
        if not isinstance(node, list) or node[0] != 'footprint':
            continue
        uid = next((r[1].strip('"') for r in node[1:]
                    if isinstance(r, list) and r and r[0] == 'uuid'), None)
        if uid not in ids:
            continue
        for item in node[1:]:
            if (not isinstance(item, list) or not item or item[0] not in
                    {'fp_line', 'fp_rect', 'fp_circle', 'fp_arc', 'fp_poly'}):
                continue
            layer = next((r[1].strip('"') for r in item[1:]
                          if isinstance(r, list) and r and r[0] == 'layer'), None)
            if layer not in {'F.CrtYd', 'B.CrtYd', 'F.SilkS', 'B.SilkS'}:
                continue
            for row in item[1:]:
                if isinstance(row, list) and row and row[0] == 'uuid':
                    row[1] = '"INDEPENDENTLY_REPLAYED_GRAPHIC"'
    import cec_copper_echo
    return cec_copper_echo._freeze(root)


def receive(source, candidate):
    """Reconstruct from the immutable parent and registered canonical package."""
    import cec_field_coupling as field
    import cec_force_current as force
    source, candidate = Path(source).resolve(), Path(candidate).resolve()
    parent_hash, child_hash, catalog_hash = _hash(source), _hash(candidate), _hash(CATALOG)
    family = force._family(source)
    code = force._code_identity()
    sidecars = force._sidecars(source)
    if force._sidecars(candidate) != sidecars:
        raise ValueError('physical_body_child_rule_or_sidecar_changed')
    catalog = contracts()
    parent = pcbnew.LoadBoard(str(source))
    before = audit(parent, catalog=catalog)
    ids = {row['uuid'] for row in before['violations']}
    if not ids or len(ids) > 16:
        raise ValueError('physical_body_repair_scope_empty_or_unbounded')
    _restore(parent, ids, catalog)
    with tempfile.TemporaryDirectory(prefix='cec-body-receiving-') as work:
        replay = Path(work)/'board.kicad_pcb'
        field._save_field_snapshot(parent, replay)
        if _normalized(replay, ids) != _normalized(candidate, ids):
            raise ValueError('physical_body_child_not_exact_graphic_reconstruction')
    child = pcbnew.LoadBoard(str(candidate))
    after = audit(child, catalog=catalog)
    if not after['ok']:
        raise ValueError('physical_body_child_remains_undersized')
    if (_hash(source), _hash(candidate), _hash(CATALOG)) != (parent_hash, child_hash, catalog_hash):
        raise ValueError('physical_body_authority_changed_during_receiving')
    if contracts() != catalog:
        raise ValueError('physical_body_template_changed_during_receiving')
    if (family != force._family(source) or code != force._code_identity()
            or force._sidecars(candidate) != sidecars):
        raise ValueError('physical_body_saved_family_or_code_changed_during_receiving')
    return dict(schema=1, ok=True, source_sha256=parent_hash, candidate_sha256=child_hash,
        catalog_sha256=catalog_hash, before=before, after=after,
        corrected_packages=len(ids), exact_independent_reconstruction=True,
        source_family_unchanged=True, rules_and_sidecars_unchanged=True,
        code_epoch_sha256=hashlib.sha256(json.dumps(code,sort_keys=True).encode()).hexdigest(),
        copper_or_pose_changes=0, routing_admitted=False, release_authority=False)


def repair_private(source, directory):
    """Construct a separate graphics correction, not a placement waiver."""
    import cec_force_current as force
    import cec_field_coupling as field
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if directory.exists() or directory == source.parent:
        raise ValueError('physical_body_repair_requires_fresh_private_directory')
    source_hash = _hash(source)
    catalog = contracts()
    board = pcbnew.LoadBoard(str(source))
    before = audit(board, catalog=catalog)
    ids = {row['uuid'] for row in before['violations']}
    if not ids or len(ids) > 16:
        raise ValueError('physical_body_repair_scope_empty_or_unbounded')
    target = force._copy_family(source, directory)
    _restore(board, ids, catalog)
    field._save_field_snapshot(board, target)
    if _hash(source) != source_hash:
        raise ValueError('physical_body_parent_changed')
    result = receive(source, target)
    result['board'] = str(target)
    return result
