"""PROTOTYPE: exact retained reference association, not print admission.

The enclosing operator must derive ``owner_groups`` from a freshly received
producer manifest, never from a historical success flag or an exception list.
This query proves only that those complete, actual associations are identical
at two immutable boundaries. It deliberately does NOT recognize interrupted
guides as closed bodies, reconstruct their producer, or accept unrelated PCB
changes. Copper cuts, holes and fills are outside the evidence returned here;
all current mask, print, manufacturing and whole-parent gates remain due.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_force_current as force
import cec_source_reference_group_transport as transport
import cec_source_retaining_ses_import as raw


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic() < deadline, 'association_query_deadline')


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _dependencies():
    return {str(path): force._hash(path) for path in (
        Path(__file__).resolve(), Path(force.__file__).resolve(),
        Path(transport.__file__).resolve(), Path(raw.__file__).resolve(),
        Path(transport.ast.__file__).resolve(), Path(transport.syntax.__file__).resolve())}


def _literal_tree(text, deadline):
    """Include nested pad/field IDs: native loading must not hide duplicates."""
    tree = transport.syntax._parse(transport.syntax._TOKEN.findall(text))
    _need(tree and tree[0] == 'kicad_pcb', 'association_query_native_board_root_required')
    seen = set(); pending = [tree]; count = 0
    while pending:
        node = pending.pop(); count += 1
        _need(count <= 500000, 'association_query_literal_inventory_bound')
        if count % 256 == 0:
            _tick(deadline)
        if not isinstance(node, list):
            continue
        if node and node[0] == 'uuid':
            _need(len(node) == 2 and type(node[1]) is str,
                  'association_query_literal_uuid_required')
            uid = node[1].strip('"')
            _need(uid and uid not in seen, 'association_query_unique_literal_uuids_required')
            seen.add(uid)
        pending.extend(n for n in node if isinstance(n, list))
    nodes = {}
    for node in tree[1:]:
        if not isinstance(node, list):
            continue
        ids = [n[1].strip('"') for n in node[1:] if isinstance(n, list)
               and n[:1] == ['uuid'] and len(n) == 2]
        _need(len(ids) <= 1, 'association_query_unique_root_identity_required')
        if ids:
            nodes[ids[0]] = node
    return tree, nodes


def _process(source, board, tree):
    rules = transport._cardinal_rules(source, board)
    _need(type(rules) is dict and all(type(rules.get(k)) in (int, float)
        and math.isfinite(rules[k]) and rules[k] > 0
        for k in ('silk_height', 'silk', 'silk_clearance')),
        'association_query_positive_current_fab_floors_required')
    settings = board.GetDesignSettings()
    signature = dict(cardinal_rules=rules,
        native_silk_floors_nm=[settings.m_MinSilkTextHeight,
            settings.m_MinSilkTextThickness, settings.m_SilkClearance],
        copper_layer_count=board.GetCopperLayerCount(),
        enabled_copper_layers=list(map(int, board.GetEnabledLayers().CuStack())),
        literal_process=repr(transport.syntax._freeze([n for n in tree[1:]
            if isinstance(n, list) and n and n[0] in ('general', 'layers', 'setup', 'property')])),
        companion_sha256=force._sidecars(source))
    return json.loads(json.dumps(signature, sort_keys=True, allow_nan=False))


def _pad_signature(fp):
    return sorted((force._uid(p), p.GetNumber(), p.GetNetname(),
        tuple(p.GetPosition()), tuple(p.GetSize()), tuple(p.GetDrillSize()),
        tuple(map(int, p.GetLayerSet().Seq())), p.GetPinFunction(), p.GetPinType())
        for p in fp.Pads())


def _members(node):
    rows = [n for n in node[1:] if isinstance(n, list) and n[:1] == ['members']]
    _need(len(rows) == 1 and all(type(v) is str for v in rows[0][1:]),
          'association_query_one_literal_membership_required')
    return transport.ast._members(node)


def _subtree_ids(node):
    ids = set(); pending = [node]
    while pending:
        value = pending.pop()
        if not isinstance(value, list):
            continue
        if value[:1] == ['uuid']:
            ids.add(value[1].strip('"'))
        pending.extend(n for n in value if isinstance(n, list))
    return ids


def _boundary(path, selections, deadline):
    _tick(deadline)
    _need(path.stat().st_size <= 64 * 1024 * 1024, 'association_query_saved_board_size_bound')
    text = path.read_text(); tree, nodes = _literal_tree(text, deadline)
    spans = raw.inventory(text)
    board = pcbnew.LoadBoard(str(path))
    _need(board is not None, 'association_query_native_board_required')
    groups = list(board.Groups()); fps = list(board.GetFootprints())
    _need(len(groups) <= 2048 and len(fps) <= 4096,
          'association_query_native_inventory_bound')
    group_by_id = {force._uid(g): g for g in groups}
    fp_by_id = {force._uid(fp): fp for fp in fps}
    _need(len(group_by_id) == len(groups) and len(fp_by_id) == len(fps),
          'association_query_unique_native_owners_required')
    references = Counter(fp.GetReference() for fp in fps)
    process = _process(path, board, tree); records = []; claimed = set()
    for owner_uid, group_uid in selections:
        _tick(deadline)
        _need(owner_uid in fp_by_id and group_uid in group_by_id
              and owner_uid in nodes and group_uid in nodes,
              'association_query_actual_owner_and_group_required')
        fp = fp_by_id[owner_uid]; group = group_by_id[group_uid]
        items = list(group.GetItems()); member_ids = [force._uid(i) for i in items]
        _need(3 <= len(items) <= 258 and len(set(member_ids)) == len(items)
              and owner_uid in member_ids and not claimed.intersection(member_ids),
              'association_query_complete_disjoint_native_members_required')
        _need(nodes[group_uid][0] == 'group' and nodes[owner_uid][0] == 'footprint'
              and _members(nodes[group_uid]) == set(member_ids),
              'association_query_exact_literal_native_members_required')
        _need(group.GetName() == transport.PREFIX + fp.GetReference()
              and group.IsLocked() and not group.GetParentGroup()
              and not fp.IsLocked() and not fp.IsDNP() and not fp.Reference().IsVisible()
              and references[fp.GetReference()] == 1,
              'association_query_actual_hidden_unique_owner_required')
        protected = set(member_ids) | {group_uid}
        # The owner's COMPLETE subtree includes lands and fields, even though
        # these are not root members of its annotation group. Another group
        # must not acquire one behind an otherwise identical owner literal.
        ownership_ids = protected | _subtree_ids(nodes[owner_uid])
        for other in groups:
            _tick(deadline)
            other_uid = force._uid(other)
            if other_uid == group_uid:
                continue
            _need(not any(other.ContainsItem(i) for i in [group, *items])
                  and other_uid in nodes
                  and not _members(nodes[other_uid]).intersection(ownership_ids),
                  'association_query_no_nested_or_duplicate_ownership_required')
        _need(all(sum(g.ContainsItem(i) for g in groups) == 1 for i in items)
              and all(group.ContainsItem(i) and i.GetParentGroup() is not None for i in items),
              'association_query_unique_actual_parent_required')
        owned_fps = [i for i in items if i.GetClass() == 'FOOTPRINT']
        labels = [i for i in items if i.GetClass() == 'PCB_TEXT']
        guides = [i for i in items if i.GetClass() == 'PCB_SHAPE']
        _need(len(owned_fps) == len(labels) == 1 and len(guides) >= 1
              and 2 + len(guides) == len(items) and force._uid(owned_fps[0]) == owner_uid,
              'association_query_only_owner_label_and_guides_required')
        label = labels[0]; face = pcbnew.F_SilkS if fp.IsFlipped() else pcbnew.B_SilkS
        size = label.GetTextSize(); stroke = label.GetTextThickness()
        floors = process['native_silk_floors_nm']; rules = process['cardinal_rules']
        _need(label.GetText() == fp.GetReference() and label.IsVisible() and label.IsLocked()
              and label.GetLayer() == face and label.IsMirrored() == (face == pcbnew.B_SilkS)
              and size.x == size.y and size.x >= max(round(rules['silk_height'] * 1e6), floors[0])
              and stroke >= max(round(rules['silk'] * 1e6), floors[1])
              and label.GetTextAngle().AsDegrees() % 180 in (0, 90)
              and not label.IsBold() and not label.IsItalic()
              and label.GetHorizJustify() == pcbnew.GR_TEXT_H_ALIGN_CENTER
              and label.GetVertJustify() == pcbnew.GR_TEXT_V_ALIGN_CENTER,
              'association_query_current_readable_opposite_label_required')
        label_node = nodes.get(force._uid(label))
        _need(label_node is not None and not any(isinstance(n, list) and n[:1] == ['hide']
            and n[1:] != ['no'] for n in label_node),
            'association_query_literal_label_visibility_required')
        _need(all(i.IsLocked() and i.GetShape() == pcbnew.SHAPE_T_SEGMENT
            and i.GetLayer() == face and i.GetWidth() == stroke and i.GetStart() != i.GetEnd()
            for i in guides), 'association_query_actual_locked_opposite_guides_required')
        _need(protected <= spans.keys(), 'association_query_complete_literal_subtrees_required')
        literals = {uid: text[spans[uid][0]:spans[uid][1]] for uid in sorted(protected)}
        records.append(dict(owner_uuid=owner_uid, group_uuid=group_uid,
            member_uuids=sorted(member_ids), literal_subtrees=literals,
            native_pad_signature=_pad_signature(fp)))
        claimed.update(member_ids)
    _tick(deadline)
    return process, records


def compare(mapped, source, owner_groups, *, board_hint, timeout_s=10.):
    """Query exact association identity; a fresh producer replay is still owed.

    ``owner_groups`` is a bounded sequence of (owner_uuid, group_uuid) pairs.
    No caller mask, excluded UUIDs, permitted delta, cached proof or native
    working board is accepted. Different copper does not authorize that copper.
    """
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10
        and type(board_hint) is str and bool(board_hint)
        and type(owner_groups) in (list, tuple) and 1 <= len(owner_groups) <= 128
        and all(type(row) in (list, tuple) and len(row) == 2
            and all(type(uid) is str and uid for uid in row) for row in owner_groups),
        'bounded_explicit_association_query_required')
    selections = [tuple(row) for row in owner_groups]
    _need(len({o for o, _ in selections}) == len(selections)
          and len({g for _, g in selections}) == len(selections)
          and not {o for o, _ in selections}.intersection(g for _, g in selections),
          'association_query_unique_owner_group_pairs_required')
    deadline = time.monotonic() + timeout_s; paths = []
    for value in (mapped, source):
        path = Path(value)
        _need(path.is_absolute() and not path.is_symlink(), 'association_query_literal_saved_path_required')
        path = path.resolve(strict=True)
        _need(path.is_file() and path.suffix == '.kicad_pcb', 'association_query_saved_pcb_required')
        paths.append(path)
    _need(paths[0] != paths[1], 'association_query_distinct_boundaries_required')
    _tick(deadline)
    epoch = force._code_identity(); dependencies = _dependencies()
    hashes = [force._hash(p) for p in paths]
    families = [force._family(p, board_hint) for p in paths]
    old_process, old_records = _boundary(paths[0], selections, deadline)
    new_process, new_records = _boundary(paths[1], selections, deadline)
    _need(old_process == new_process, 'association_query_process_or_fab_floors_changed')
    _need(old_records == new_records, 'association_query_complete_literal_association_changed')
    _need(hashes == [force._hash(p) for p in paths]
          and families == [force._family(p, board_hint) for p in paths]
          and epoch == force._code_identity() and dependencies == _dependencies(),
          'association_query_Source_family_or_code_changed')
    _tick(deadline)
    records = [dict(owner_uuid=r['owner_uuid'], group_uuid=r['group_uuid'],
        member_uuids=r['member_uuids'], complete_literal_subtree_sha256={
            uid: _digest(text) for uid, text in r['literal_subtrees'].items()}) for r in new_records]
    return dict(schema=1, scope='prototype_exact_retained_reference_association_query',
        ok=True, complete=True, mapped_source=str(paths[0]), mapped_source_sha256=hashes[0],
        source=str(paths[1]), source_sha256=hashes[1], source_families=families,
        code_identity=epoch, dependency_sha256=dependencies, board_hint=board_hint,
        records=records, process_signature=new_process, source_unchanged=True,
        association_only=True, association_identity_preserved=True, producer_replay_still_required=True,
        caller_uuid_selection_is_not_producer_authority=True,
        current_mask_print_and_whole_parent_receiving_still_required=True,
        unrelated_PCB_changes_not_received=True, closed_body_authority=False,
        mask_authority=False, copper_admission=False, current_authority=False,
        pose_authority=False, print_admission=False, release_authority=False)
