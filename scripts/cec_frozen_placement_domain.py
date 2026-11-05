"""Carry a committed power dependency into bounded placement search.

This is a search-domain restriction, not authority to replan frozen copper.
The existing native postfreeze commit proof is also the dry-run trial proof.
"""
import copy
import json
import math
from pathlib import Path

import cec_placement_evidence_identity as identity


def bind(board, candidate):
    board = Path(board).resolve()
    state = board.with_suffix('.pourfirst-state.json')
    contract = {'schema': 1, 'board': str(board), 'state': str(state),
                'board_sha256': identity.digest(board),
                'state_sha256': identity.digest(state),
                'outline_mm': [float(candidate.W), float(candidate.H)]}
    if not contract['board_sha256'] or not contract['state_sha256']:
        raise ValueError('missing frozen placement authority')
    return contract


class Domain:
    def __init__(self, contract, *, clearance_mm=0.3):
        import pcbnew
        import cec_power_guard_geometry as geometry
        self.contract = dict(contract)
        self.clearance = float(clearance_mm)
        if not math.isfinite(self.clearance) or self.clearance < 0:
            raise ValueError('invalid frozen placement clearance')
        for key in ('board', 'state'):
            if not contract.get(key + '_sha256') or identity.digest(contract[key]) != contract[key + '_sha256']:
                raise ValueError('frozen placement authority changed: ' + key)
        self.state = json.loads(Path(contract['state']).read_text())
        if self.state.get('placement_scope') != 'complete' or not isinstance(self.state.get('placements'), dict):
            raise ValueError('incomplete frozen placement authority')
        self.board = pcbnew.LoadBoard(contract['board'])
        self.footprints = {str(fp.GetReference()): fp for fp in self.board.GetFootprints()}
        self.positions = {ref: (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6,
                               float(fp.GetOrientationDegrees())) for ref, fp in self.footprints.items()}
        for ref, expected in self.state['placements'].items():
            actual = self.positions.get(ref)
            if (actual is None or len(expected) != 3
                    or not all(math.isfinite(float(value)) for value in expected)
                    or abs(actual[0] - float(expected[0])) > .01
                    or abs(actual[1] - float(expected[1])) > .01
                    or abs((actual[2] - float(expected[2]) + 180.) % 360. - 180.) > .01):
                raise ValueError('frozen placement source snapshot mismatch: ' + str(ref))
        self.back = {ref for ref, fp in self.footprints.items() if fp.IsFlipped()}
        token_nets = {}
        for ref, fp in self.footprints.items():
            for pad in fp.Pads():
                token_nets.setdefault(ref + '-' + str(pad.GetPadName()), set()).add(str(pad.GetNetname()))
        terminals = geometry.frozen_terminal_tokens(self.state, token_nets)
        frozen = set(self.state.get('frozen_nets') or ())
        self.fixed = {}
        for ref, fp in self.footprints.items():
            nets = {str(pad.GetNetname()) for pad in fp.Pads()} & frozen
            if not nets:
                continue
            tokens = {ref + '-' + str(pad.GetPadName()) for pad in fp.Pads()}
            if terminals is None or tokens & terminals:
                self.fixed[ref] = {'reason': 'owns_frozen_net', 'nets': sorted(nets)}
            elif geometry.frozen_pad_contacts(self.board, fp, self.state, self.clearance):
                self.fixed[ref] = {'reason': 'original_pad_touches_frozen_power', 'nets': sorted(nets)}

    def search_regions(self):
        """Feed the commit guard's reservations into geometric negotiation.

        Ref-level consumer exemptions match the native guard, not an arbitrary
        same-net body waiver. Consumers still require its exact pad-contact
        proof, and physical power owners remain fixed.
        """
        import cec_power_guard_geometry as geometry
        frozen = set(self.state.get('frozen_nets') or ())
        consumers = sorted(ref for ref, fp in self.footprints.items()
                           if any(str(p.GetNetname()) in frozen for p in fp.Pads()))
        return [dict(row, all_layers=True, exempt_refs=consumers,
                     clearance_mm=self.clearance, authority='frozen_placement_commit')
                for row in geometry.placement_reservations(self.state)]

    def search_pad_collisions(self, placements):
        """Exact consumer-pad obstructions with tangent witnesses for search.

        A body-level exemption does not exempt its pads. Cache immutable
        source-relative poses; native footprints are restored on every path.
        These rows guide proposals and never replace the full commit proof.
        """
        import pcbnew
        import cec_power_guard_geometry as geometry
        if not hasattr(self, '_pad_obstacles'):
            obstacles = []
            for row in geometry.reservations(self.state):
                box = (row['x0'], row['x1'], row['y0'], row['y1'])
                shape = pcbnew.SHAPE_POLY_SET(); shape.NewOutline()
                for x,y in ((box[0],box[2]),(box[1],box[2]),(box[1],box[3]),(box[0],box[3])):
                    shape.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
                obstacles.append((geometry.copper_layer(self.board,row['layer']),shape,row['net'],box))
            for via in self.state.get('vias') or ():
                x,y = float(via['x_mm']),float(via['y_mm'])
                radius = max(.4,float(via.get('diameter_mm') or 0)/2)
                obstacles.append((None,pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I_MM(x,y),pcbnew.FromMM(radius)),
                                  via.get('net'),(x-radius,x+radius,y-radius,y+radius)))
            self._pad_obstacles = obstacles
            self._pad_collision_cache = {}
        result = []
        frozen = set(self.state.get('frozen_nets') or ())
        for ref, pose in sorted(placements.items()):
            fp = self.footprints.get(ref)
            if (fp is None or ref in self.fixed or tuple(pose)==self.positions[ref]
                    or not any(str(p.GetNetname()) in frozen for p in fp.Pads())):
                continue
            if len(pose)!=3 or not all(math.isfinite(float(v)) for v in pose):
                raise ValueError('invalid native collision pose')
            key = (ref,tuple(float(v) for v in pose))
            if key not in self._pad_collision_cache:
                rows = []
                try:
                    fp.SetPosition(pcbnew.VECTOR2I_MM(pose[0],pose[1]));fp.SetOrientationDegrees(pose[2])
                    for pad in fp.Pads():
                        bb = pad.GetBoundingBox()
                        member = (bb.GetLeft()/1e6,bb.GetRight()/1e6,bb.GetTop()/1e6,bb.GetBottom()/1e6)
                        for index,(layer,shape,net,box) in enumerate(self._pad_obstacles):
                            layers = list(pad.GetLayerSet().CuStack()) if layer is None else [layer]
                            if not any(pad.IsOnLayer(int(side)) and pad.GetEffectiveShape(int(side)).Collide(
                                    shape,pcbnew.FromMM(self.clearance)) for side in layers):
                                continue
                            obstacle = (box[0]-self.clearance,box[1]+self.clearance,
                                        box[2]-self.clearance,box[3]+self.clearance)
                            area = max(0.,min(member[1],obstacle[1])-max(member[0],obstacle[0])) * max(
                                0.,min(member[3],obstacle[3])-max(member[2],obstacle[2]))
                            rows.append(dict(ref=ref,pad=str(pad.GetPadName()),net=net,
                                region_index=-(index+1),box=obstacle,member_box=member,
                                overlap_mm2=area,kind='frozen_consumer_pad'))
                finally:
                    x,y,a = self.positions[ref]
                    fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.SetOrientationDegrees(a)
                self._pad_collision_cache[key] = rows
            result.extend(dict(row) for row in self._pad_collision_cache[key])
        return result

    def assess(self, candidate):
        import pcbnew
        import cec_full_pipeline as pipeline
        if [float(candidate.W), float(candidate.H)] != self.contract['outline_mm']:
            return {'ok': False, 'reason': 'frozen_outline_requires_replan'}
        if set(candidate.P) != set(self.positions):
            return {'ok': False, 'reason': 'frozen_population_changed'}
        if set(getattr(candidate, 'back_refs', ()) or ()) != self.back:
            return {'ok': False, 'reason': 'frozen_face_change_requires_replan'}
        moved = []
        try:
            for ref, pose in candidate.P.items():
                if len(pose) != 3 or not all(math.isfinite(float(value)) for value in pose):
                    return {'ok': False, 'reason': 'invalid_candidate_pose', 'ref': ref}
                if tuple(pose) == self.positions[ref]:
                    continue
                fp = self.footprints[ref]
                moved.append(ref)
                fp.SetPosition(pcbnew.VECTOR2I_MM(float(pose[0]), float(pose[1])))
                fp.SetOrientationDegrees(float(pose[2]))
            return pipeline._sync_safe_postfreeze_placement_delta(
                self.contract['board'], clearance_mm=self.clearance,
                dry_run=True, loaded_board=self.board, state_override=self.state)
        finally:
            for ref in moved:
                x, y, rotation = self.positions[ref]
                self.footprints[ref].SetPosition(pcbnew.VECTOR2I_MM(x, y))
                self.footprints[ref].SetOrientationDegrees(rotation)

    def filter_moves(self, candidate, moves, *, sample_limit=16):
        """Screen complete proposals before a finite routing trial quota.

        Saved-board copper can be empty while the sidecar already owns the
        current corridors. Use the same native independence proof as commit,
        not the approximate body reservation or a same-net exemption.
        This is a dependency screen, not physical or routing admission.
        """
        eligible, fixed = filter_fixed_moves(moves, candidate.P, self.fixed)
        retained, rejected = [], []
        reason_counts = {}
        for move in eligible:
            trial = copy.copy(candidate)
            trial.P = dict(candidate.P)
            trial.P.update(move.get('placements') or {move['ref']: move['position']})
            proof = self.assess(trial)
            if proof.get('ok'):
                retained.append(move)
            else:
                reason = str(proof.get('reason') or 'frozen_dependency_refused')
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                if len(rejected) < max(0, int(sample_limit)):
                    rejected.append({'kind': move.get('kind'), 'ref': move.get('ref'),
                                     'proof': proof})
        native_refused = len(eligible) - len(retained)
        return retained, {'applicable': True, 'proposed': len(moves),
            'retained': len(retained), 'refused': len(moves) - len(retained),
            'fixed_pruning': fixed, 'native_checked': len(eligible),
            'native_refused': native_refused, 'reason_counts': reason_counts,
            'samples': rejected, 'samples_truncated': native_refused - len(rejected),
            'authority': 'unchanged_frozen_power_plan', 'allows_power_replan': False}


def candidate_guard(candidate):
    contract = getattr(candidate, 'frozen_placement_contract', None)
    if not contract:
        return {'ok': True, 'applicable': False}
    return dict(Domain(contract).assess(candidate), applicable=True)


def filter_fixed_moves(moves, positions, fixed):
    """Prune forbidden root/compound moves before the fair trial quota."""
    retained, refused = [], []
    for move in moves:
        proposed = move.get('placements') or {move['ref']: move['position']}
        hits = []
        for ref, pose in proposed.items():
            if ref not in fixed:
                continue
            old = positions.get(ref)
            if (old is None or len(pose) != 3
                    or not all(math.isfinite(float(value)) for value in pose)
                    or abs(float(pose[0]) - old[0]) > .01
                    or abs(float(pose[1]) - old[1]) > .01
                    or abs((float(pose[2]) - old[2] + 180.) % 360. - 180.) > .01):
                hits.append(ref)
        if hits:
            refused.append({'kind': move.get('kind'), 'refs': sorted(hits)})
        else:
            retained.append(move)
    return retained, {'proposed': len(moves), 'retained': len(retained),
                      'refused': len(refused), 'samples': refused[:16],
                      'samples_truncated': max(0, len(refused)-16)}
