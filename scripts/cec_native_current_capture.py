"""Reserve manufacturer-proved control leaves before whole-current search.

An enable and an input can share a net without being interchangeable power
landing sites. Preserve received native EN-to-IN leaves and their real shared
tap. This guard only excludes proposals: it changes no copper, current budget,
width, barrel rating, connectivity or receiving/release authority.
"""
import math
import os
import time

import pcbnew
import cec_control_current_branch as controls
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_force_current as force
import cec_kelvin_copper_cut as cut
from cec_resistive_monitor_branch import _native_exclusive_plan


class Guard:
    def __init__(self, board, source, *, net, board_hint=None, timeout_s=2.):
        if (type(net) is not str or not net or board.GetNetcodeFromNetname(net) <= 0
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10.):
            raise ValueError('bounded_native_current_capture_reservation_required')
        self.board = board; self.net = net
        self.deadline = time.monotonic()+timeout_s
        self.scopes = []; self.cache = {}; self.shapes = {}
        self.calls = self.refusals = self.endpoint_refusals = 0
        self.complete = True
        # Skip expensive topology walks only when no positively typed tied
        # enable on this net exists. Refdes/net names are not component roles.
        owners = []
        for fp in board.GetFootprints():
            model = roles.tied_enable_contract(fp)
            if model and not fp.IsDNP() and any(p.GetNumber() == model['enable_pin']
                    and str(p.GetNetname()) == net for p in fp.Pads()):
                owners.append(fp)
        if not owners:
            self.native = {}; self.exclusive = set(); self.unclassified_owners = 0
            return
        hint = os.environ.get('CEC_THERMAL_BOARD_HINT') or board_hint or str(source or '')
        if not hint or not source:
            raise ValueError('source_bound_native_current_capture_required')
        material = [*(p for fp in board.GetFootprints() for p in fp.Pads()),
            *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]
        if len(material) > 16384:
            raise ValueError('native_current_capture_inventory_bound')
        self.native = {force._uid(i):i for i in material}
        domains = topology.board_current_domains(board, hint)
        inventory = controls.inventory(board, source, domains,
            timeout_s=max(.001, self.deadline-time.monotonic()))
        if not inventory['complete'] or time.monotonic() >= self.deadline:
            raise ValueError('complete_native_control_capture_inventory_required')
        for proof in inventory['proofs']:
            if proof['net'] != net: continue
            received = set(proof['native_exclusive_branch_material_uuids'])
            for uid in proof['leaf_pad_uuids']:
                q = _native_exclusive_plan(board, uid, deadline=self.deadline)
                ids = set(q['native_removed_material_uuids'])
                if not ids or not ids <= received or not q['boundary_uuids']:
                    raise ValueError('exact_received_native_control_capture_required')
                self.scopes.append(dict(control_pad_uuid=uid,
                    exclusive_material_uuids=sorted(ids|{uid}),
                    retained_capture_uuids=sorted(q['boundary_uuids']),
                    manufacturer_sources=proof['manufacturer_sources']))
        if len(self.scopes) > 16 or sum(len(q['exclusive_material_uuids'])
                for q in self.scopes) > 4096:
            raise ValueError('native_control_capture_scope_bound')
        self.exclusive = {u for q in self.scopes for u in q['exclusive_material_uuids']}
        self.unclassified_owners = len(owners)-len(self.scopes)
        if time.monotonic() >= self.deadline:
            raise ValueError('native_current_capture_deadline')

    @property
    def active(self):
        return bool(self.scopes)

    def allows_endpoint(self, endpoint):
        ids = endpoint.get('native_uuids')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 16
                or any(type(u) is not str or not u for u in ids)):
            raise ValueError('exact_native_current_capture_endpoint_required')
        if set(ids) & self.exclusive:
            self.endpoint_refusals += 1
            return False
        return True

    def _native_shape(self, uid, layer):
        key = (uid, layer)
        if key not in self.shapes:
            self.shapes[key] = self.native[uid].GetEffectiveShape(layer)
        return self.shapes[key]

    def _poly(self, uid, layer):
        key = (uid, layer)
        if key not in self.cache:
            item = self.native[uid]; work = cut._Work(self.deadline)
            self.cache[key] = (cut._poly(item.GetFilledPolysList(layer), work)
                if item.GetClass() == 'ZONE' and item.IsFilled()
                else cut._shape(item, layer, False, work))
        return self.cache[key]

    def __call__(self, start, end, width, layer):
        if (type(width) is not int or width <= 0 or type(layer) is not int
                or layer not in self.board.GetEnabledLayers().CuStack()
                or len(start) != 2 or len(end) != 2
                or any(type(v) is not int for v in (*start, *end))):
            raise ValueError('exact_native_current_capture_leg_required')
        self.calls += 1
        if not self.active: return True
        if time.monotonic() >= self.deadline:
            self.complete = False; return False
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(pcbnew.VECTOR2I(*start)); track.SetEnd(pcbnew.VECTOR2I(*end))
        track.SetWidth(width); track.SetLayer(layer)
        shape = track.GetEffectiveShape(layer); polygon = None
        for scope in self.scopes:
            for uid in scope['exclusive_material_uuids']:
                item = self.native[uid]
                if not item.IsOnLayer(layer) or not self._native_shape(uid, layer).Collide(shape, 0):
                    continue
                if polygon is None:
                    polygon = cut._shape(track, layer, False, cut._Work(self.deadline))
                overlap = polygon.intersection(self._poly(uid, layer))
                if overlap.is_empty: continue
                captures = [self._poly(u, layer) for u in scope['retained_capture_uuids']
                    if self.native[u].IsOnLayer(layer)]
                if not captures or not any(c.covers(overlap) for c in captures):
                    self.refusals += 1; return False
        return True

    def allows_ops(self, ops):
        for op in ops:
            if op[0] == 'trk':
                if not self(tuple(op[1]), tuple(op[2]), op[3], int(op[4])): return False
            elif op[0] == 'via':
                at = tuple(op[1]); diameter = round(op[3]*1e6)
                if any(not self(at, at, diameter, int(layer))
                        for layer in self.board.GetEnabledLayers().CuStack()): return False
            else: raise ValueError('native_current_capture_operation_unknown')
        return True

    def report(self):
        return dict(schema=1, scope='source_proved_control_leaf_search_reservation',
            complete=self.complete, net=self.net, scopes=self.scopes,
            unclassified_manufacturer_owners=self.unclassified_owners,
            tested_legs=self.calls, refused_legs=self.refusals,
            refused_endpoints=self.endpoint_refusals,
            shared_native_input_taps_only=True, board_mutated=False,
            current_budget_or_width_changed=False, admission_authority=False,
            barrel_capacity_qualified=False, release_authority=False)
