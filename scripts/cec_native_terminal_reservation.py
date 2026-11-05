"""Read-only future through-access reservations for unresolved native SMD pads.

This is a bounded search exclusion, not copper, connectivity, via ownership,
shielding or admission. Seats must already be legal in the current source
after any independently owned rip-up. Rebuild for each board mutation. The
ordinary/coupled constructor and independent saved-board receivers still
prove every actual route and barrel.
"""
from __future__ import annotations

import math
import pcbnew
import cec_fab_profile as fab
import cec_fr as fr


class Guard:
    def __init__(self, board, pad_uuids, *, diameter_mm=.35, drill_mm=.25):
        if (not isinstance(pad_uuids, (list, tuple)) or not 1 <= len(pad_uuids) <= 8
                or len(set(pad_uuids)) != len(pad_uuids)
                or any(not isinstance(u, str) or not u for u in pad_uuids)
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in (diameter_mm, drill_mm))):
            raise ValueError('bounded_native_terminal_reservation_required')
        profile = fab.get_profile(fab.board_profile_name(board))
        if not profile or not fab.pofv_dimensions(profile, diameter_mm, drill_mm)[0]:
            raise ValueError('explicit_source_factory_process_required')
        diameter, drill = fr._nm(diameter_mm), fr._nm(drill_mm)
        pads = {str(p.m_Uuid.AsString()): p for f in board.GetFootprints() for p in f.Pads()}
        self.rows = []; self.calls = self.refusals = 0
        clearance = fr._foreign_clearance_resolver(board)
        for uid in pad_uuids:
            pad = pads.get(uid)
            if pad is None or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not pad.GetNetname():
                raise ValueError('actual_connected_native_SMD_terminal_required')
            at = pcbnew.VECTOR2I(*tuple(pad.GetPosition()))
            blocking, lands = fab.via_at_pad_conflicts(board, at, diameter, drill, pad.GetNetCode())
            if (blocking is not None or not lands
                    or not fab.via_pad_decision(board, pad, at, diameter, drill, pad.GetNetCode())[0]):
                raise ValueError('native_full_land_containment_required')
            gap = max(board.GetDesignSettings().m_MinClearance,
                      *(int(clearance(pad, int(l))) for l in pad.GetLayerSet().CuStack()))
            if not fr._via_spot_clear(board, at, diameter, gap, {pad.GetNetCode()},
                    drill_nm=drill, net_code=pad.GetNetCode(), foreign_cache={},
                    contained_layers=set(map(int, pad.GetLayerSet().CuStack()))):
                raise ValueError('future_terminal_seat_not_currently_native_legal')
            self.rows.append(dict(pad_uuid=uid, net=str(pad.GetNetname()), at_nm=tuple(at),
                                  diameter_nm=diameter, clearance_nm=gap))

    @property
    def active(self):
        return bool(self.rows)

    def __call__(self, start, end, width_nm, layer):
        if (type(width_nm) is not int or width_nm <= 0
                or any(type(v) is not int for v in (*start, *end))):
            raise ValueError('invalid_native_terminal_reservation_leg')
        self.calls += 1
        # Through access occupies every copper layer, not just the SMD face.
        for row in self.rows:
            # Exact integer capsule/disk comparison avoids SWIG's asymmetric
            # shape overloads and floating grid rounding at tangent contacts.
            dx,dy=end[0]-start[0],end[1]-start[1]
            px,py=row['at_nm'][0]-start[0],row['at_nm'][1]-start[1]
            length2=dx*dx+dy*dy; dot=px*dx+py*dy
            limit2=row['diameter_nm']+width_nm+2*row['clearance_nm']
            if dot<=0 or not length2:
                hit=4*(px*px+py*py)<=limit2*limit2
            elif dot>=length2:
                ex,ey=px-dx,py-dy; hit=4*(ex*ex+ey*ey)<=limit2*limit2
            else:
                cross=px*dy-py*dx; hit=4*cross*cross<=limit2*limit2*length2
            if hit:
                self.refusals += 1
                return False
        return True

    def report(self):
        return dict(schema=1, scope='native_future_terminal_search_exclusion_only',
                    reservations=self.rows, tested_legs=self.calls, conservative_refusals=self.refusals,
                    board_mutated=False, copper_added=False, connectivity_credited=False,
                    routing_admitted=False, release_authority=False, no_path_proof=False)
