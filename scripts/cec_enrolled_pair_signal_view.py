"""Source-proved fitted-device signal edges, never PCB copper.

This module has no generic graph hook and no current/Ground/Kelvin consumer.
Only exact saved Source/candidate USB-pair receiving may request this view.
"""
import time
import json
import weakref
from pathlib import Path

import pcbnew
import cec_component_internal_connections as enrolled
import cec_component_jumper_metadata as metadata
import cec_force_current as force
import cec_native_partition_pair as partitions


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _fp_native(fp):
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    io.Format(fp)
    return metadata._parse(io.GetStringOutput(False))


def _owners(board, saved, pair):
    """Discover literal enrolled banks touching this declared pair only."""
    names = {pair['p'], pair['n']}
    result = []
    for fp in board.GetFootprints():
        rows = saved[fp.GetReference()]
        pads = {}
        for pad in fp.Pads():
            pads.setdefault(str(pad.GetNumber()), []).append(pad)
        touching = [g for g in rows if any(
            str(p.GetNetname()) in names for pin in g for p in pads.get(pin, []))]
        if not touching:
            continue
        _need(not fp.IsDNP() and not fp.GetDuplicatePadNumbersAreJumpers(),
              'fitted_explicit_signal_component_required')
        # No partial enrollment: selected model must independently prove every
        # native group/pin, and no model may secretly connect a nonpair role.
        _need(len(touching) == len(rows) and all(
            len(pads.get(pin, [])) == 1 for g in rows for pin in g),
            'complete_unique_pair_bank_inventory_required')
        for group in rows:
            nets = {str(pads[pin][0].GetNetname()) for pin in group}
            _need(len(nets) == 1 and nets <= names,
                  'enrolled_edges_must_be_same_declared_signal_net')
        result.append(force._uid(fp))
    _need(len(result) <= 4, 'bounded_enrolled_signal_owners_required')
    return sorted(result)


_DERIVATION_TOKEN = object()
_ISSUED = weakref.WeakSet()


class _SignalView:
    """Opaque live proof; neither caller edge lists nor serialized flags work."""
    def __setattr__(self, name, value):
        if hasattr(self, '_seal'):
            raise ValueError('immutable_enrolled_signal_view_required')
        object.__setattr__(self, name, value)

    def _payload(self):
        return json.dumps([self.proofs, self.names, self.deadline, self.native, self.edges],
                          sort_keys=True, allow_nan=False)

    def __init__(self, proofs, boards, pair, deadline, *, _token=None):
        _need(_token is _DERIVATION_TOKEN, 'independently_derived_signal_view_required')
        self.proofs = proofs
        self.names = (pair['p'], pair['n'])
        self.deadline = deadline
        self.native = {}
        self.edges = {}
        for proof, board in zip(proofs, boards):
            fps = {force._uid(fp): fp for fp in board.GetFootprints()}
            edges = []
            for owner in proof['owners']:
                fp = fps[owner['owner_uuid']]
                _need(not fp.IsDNP() and not owner['restored_source_fields'],
                      'already_enrolled_selected_signal_part_required')
                self.native[owner['owner_uuid']] = _fp_native(fp)
                pads = {str(p.GetNumber()): p for p in fp.Pads()}
                expected = metadata._groups(owner['exported_contract']['groups'])
                actual = metadata._groups(owner['source_groups'])
                _need(actual == expected and expected,
                      'actual_saved_signal_enrollment_required')
                for group in expected:
                    members = [pads[pin] for pin in group]
                    net = str(members[0].GetNetname())
                    _need(net in self.names and all(str(p.GetNetname()) == net for p in members),
                          'same_pair_signal_edges_only')
                    edges.append((net, tuple(force._item_key(p) for p in members)))
            self.edges[proof['source']] = edges
        _need(self.edges[proofs[0]['source']] == self.edges[proofs[1]['source']],
              'unchanged_enrolled_signal_edge_inventory_required')
        self._seal = self._payload()

    def check(self, board):
        _need(type(self) is _SignalView and self in _ISSUED
              and time.monotonic() < self.deadline,
              'live_bounded_enrolled_signal_view_required')
        _need(self._payload() == self._seal, 'enrolled_signal_view_mutated')
        for proof in self.proofs:
            enrolled._live(proof, self.deadline)
        fps = {force._uid(fp): fp for fp in board.GetFootprints()}
        _need(all(uid in fps and not fps[uid].IsDNP()
                  and _fp_native(fps[uid]) == native for uid, native in self.native.items()),
              'actual_signal_component_changed_after_source_proof')


def derive(source, candidate, parent, child, pair, *, board_hint, timeout_s=10.):
    """Fresh independent model proofs on both actual saved boundaries.

    None means no selected literal banks: strict legacy physical checks stay.
    A malformed/unknown/stale selected bank raises; it never becomes None.
    """
    deadline = enrolled._deadline(timeout_s)
    paths = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(paths[0] != paths[1], 'distinct_saved_signal_boundaries_required')
    boards = [parent, child]
    tables = [metadata.read_saved(p) for p in paths]
    ids = [_owners(b, t, pair) for b, t in zip(boards, tables)]
    _need(ids[0] == ids[1], 'source_candidate_enrolled_signal_owners_changed')
    if not ids[0]:
        return None
    saved = [metadata._footprints(metadata._parse(p.read_text())) for p in paths]
    refs = [fp.GetReference() for fp in parent.GetFootprints() if force._uid(fp) in ids[0]]
    _need(all(saved[0][ref] == saved[1][ref] for ref in refs),
          'enrolled_signal_part_pad_pose_fields_or_groups_changed')
    proofs = [enrolled.plan(p, board_hint=board_hint, owner_uuids=owners,
                           timeout_s=enrolled._remaining(deadline))
              for p, owners in zip(paths, ids)]
    for left, right in zip(proofs[0]['owners'], proofs[1]['owners']):
        _need(left['manufacturer'] == right['manufacturer']
              and left['exported_contract'] == right['exported_contract']
              and left['owner_uuid'] == right['owner_uuid'],
              'source_candidate_selected_signal_model_changed')
    view = _SignalView(proofs, boards, pair, deadline, _token=_DERIVATION_TOKEN)
    _ISSUED.add(view)
    view.check(parent); view.check(child)
    return view


def _merge(parts, edges):
    result = [set(p) for p in parts]
    for _net, pads in edges:
        hits = [i for i, part in enumerate(result) if part.intersection(pads)]
        _need(all(any(p in part for part in result) for p in pads),
              'enrolled_signal_pad_missing_from_native_inventory')
        merged = set().union(*(result[i] for i in hits))
        result = [p for i, p in enumerate(result) if i not in hits] + [merged]
    return result


def preserved(view, parent, child, transition):
    """Electrical projection AFTER full physical inventory, not a new graph."""
    _need(type(view) is _SignalView, 'fresh_enrolled_signal_view_required')
    view.check(parent); view.check(child)
    left = _merge(transition['source_parts'], view.edges[view.proofs[0]['source']])
    right = _merge(transition['child_parts'], view.edges[view.proofs[1]['source']])
    lost = [part for part in left if not any(part <= target for target in right)]
    return dict(preserved=not lost, demoted_parts=lost,
                physical_preservation=transition['preserved'],
                scope='fresh_source_enrolled_pair_signal_electrical_projection',
                PCB_copper_current_ground_field_and_Kelvin_credit=False)


def completion(view, board, pair, *, max_items=8192):
    """Actual physical item components plus only fresh same-net device edges."""
    _need(type(view) is _SignalView and view in _ISSUED
          and (pair['p'], pair['n']) == view.names,
          'fresh_same_pair_signal_view_required')
    _need(type(max_items) is int and 1 <= max_items <= 32768,
          'bounded_pair_signal_inventory_required')
    view.check(board)
    report = dict(complete=True, connected=True, nets={},
                  scope='fresh_source_enrolled_pair_signal_electrical_projection',
                  PCB_copper_current_ground_field_and_Kelvin_credit=False)
    edges = view.edges[view.proofs[0]['source']]
    for name in view.names:
        pads = [p for fp in board.GetFootprints() for p in fp.Pads() if str(p.GetNetname()) == name]
        _need(len(pads) >= 2, 'complete_pair_signal_pad_inventory_required')
        # The generic physical inventory remains untouched. Its existing
        # island splitter receives only actual selected-net objects; every
        # proxy still owns its real BOARD through the original native zone.
        inventory = partitions._inventory(_PairInventoryView(board, name), view.deadline,
            dict(items=max_items, polygons=4096, vertices=200000))
        parts = _merge(inventory['components'], [(n, p) for n, p in edges if n == name])
        reached = next(p for p in parts if force._item_key(pads[0]) in p)
        unreachable = [force._uid(p) for p in pads if force._item_key(p) not in reached]
        disconnected = [force._uid(t) for t in inventory['objects'] if t.GetClass() in
                        ('PCB_TRACK', 'PCB_VIA', 'PCB_ARC') and force._item_key(t) not in reached]
        # An orphan filled island is material even when its owner zone UUID
        # also owns another island touching a pad. Never credit the UUID.
        orphan_islands = [str(force._item_key(t)) for t in inventory['objects']
                          if t.GetClass() not in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC')
                          and force._item_key(t) not in reached]
        report['nets'][name] = dict(connected=not unreachable and not disconnected and not orphan_islands, pad_count=len(pads),
            unreachable_pad_uuids=sorted(unreachable), disconnected_copper_uuids=sorted(disconnected),
            disconnected_zone_island_keys=sorted(orphan_islands))
        report['connected'] &= not unreachable and not disconnected and not orphan_islands
    view.check(board)
    return report


class _PairFootprintView:
    def __init__(self, fp, name):
        self.fp, self.name = fp, name

    def Pads(self):
        return [p for p in self.fp.Pads() if str(p.GetNetname()) == self.name]


class _PairInventoryView:
    def __init__(self, board, name):
        self.board, self.name = board, name

    def GetFootprints(self):
        return [_PairFootprintView(fp, self.name) for fp in self.board.GetFootprints()]

    def GetTracks(self):
        return [t for t in self.board.GetTracks() if str(t.GetNetname()) == self.name]

    def Zones(self):
        return [z for z in self.board.Zones() if str(z.GetNetname()) == self.name]
