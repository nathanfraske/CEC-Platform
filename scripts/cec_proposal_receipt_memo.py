"""Exact, ephemeral receipt reuse within one unchanged native route plan.

Not a persisted cache, source admission or release authority. Native board
serialization, original companions, resolved contracts and active fabrication
context must remain identical. A caller creates a new memo after EVERY copper
or placement mutation. Only a completed positive proposal receipt is stored;
unknown/refused work never becomes a pass, even when its work lease expires.
"""
import hashlib
import json
import math
from pathlib import Path
import tempfile

import pcbnew
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force


def proposal_key(net, operations):
    """Order-preserving exact material key AFTER native reuse normalization."""
    rows = []
    def point(raw):
        values=tuple(raw)
        if len(values)!=2 or any(type(v) is not int for v in values):
            raise ValueError('noninteger_private_proposal_point')
        return values
    for op in operations:
        if op[0] == 'via':
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in op[2:4]):
                raise ValueError('nonfinite_private_proposal_barrel')
            rows.append(('via', point(op[1]),
                int(round(op[2]*1e6)), int(round(op[3]*1e6))))
        elif op[0] == 'trk':
            if type(op[3]) is not int or type(op[4]) is not int:
                raise ValueError('noninteger_private_proposal_track')
            rows.append(('trk', point(op[1]), point(op[2]), op[3], op[4]))
        else:
            raise ValueError('unsupported_private_proposal_key')
    return str(net), tuple(rows)


class NativePlanReceiptMemo:
    def __init__(self, board, *, netclass_resolver=None, max_entries=16):
        if type(max_entries) is not int or not 1 <= max_entries <= 64:
            raise ValueError('bounded_private_receipt_memo_required')
        self.board, self.resolve, self.max_entries = board, netclass_resolver, max_entries
        self.entries = set()
        self.hits = self.stored = self.changed_context_refusals = 0
        self.valid = True
        self.context = self._context()

    def _context(self):
        # Serialize with the NON-normalizing native writer. Unlike a count,
        # bbox, pointer or partial pad signature, these bytes bind pad/custom
        # shape/orientation/hole data, zones/fills/settings, rules, properties,
        # groups and all other source material consumed by either validator.
        board = self.board
        before = field._field_snapshot_inventory(board)
        name = board.GetFileName() or ''
        with tempfile.TemporaryDirectory(prefix='cec-proposal-memo-') as work:
            path = Path(work)/'source.kicad_pcb'
            try:
                pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
            finally:
                board.SetFileName(name)
            native_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if before != field._field_snapshot_inventory(board):
            raise ValueError('proposal_memo_writer_changed_source_material')
        classes = [(str(net),self.resolve(str(net)) if self.resolve else None)
            for net in sorted(map(str,board.GetNetsByName()))]
        contracts = json.dumps(classes,sort_keys=True,allow_nan=False,separators=(',',':'))
        companions = force._family(Path(name),name) if name and Path(name).is_file() else None
        # Some project design-setting floors are live only: KiCad does not
        # serialize them in the PCB itself. Bind the geometry/return/craft
        # floors separately, rather than treating serialization as a proxy
        # for that unsaved rule state.
        settings=board.GetDesignSettings()
        rules=tuple((key,int(getattr(settings,key))) for key in (
            'm_MinClearance','m_HoleClearance','m_HoleToHoleMin','m_TrackMinWidth',
            'm_ViasMinSize','m_MinThroughDrill','m_ViasMinAnnularWidth',
            'm_CopperEdgeClearance','m_MinSilkClearance','m_MinTextHeight',
            'm_MinTextThickness','m_MaxError') if hasattr(settings,key))
        return (native_hash,name,contracts,companions,rules,fab.active_profile_name(board))

    def _unchanged(self):
        if self.valid and self.context == self._context():
            return True
        self.valid = False
        self.entries.clear()
        self.changed_context_refusals += 1
        return False

    def lookup(self, key):
        if not self.valid:
            return False
        if key not in self.entries:
            return None
        if not self._unchanged():
            return False
        self.hits += 1
        return True

    def remember(self, key):
        """Called only after BOTH required validators return completed True."""
        if not self._unchanged():
            return False
        if len(self.entries) < self.max_entries:
            self.entries.add(key)
            self.stored += 1
        return True

    def report(self):
        return dict(schema=1,scope='private_unchanged_plan_exact_positive_proposal_receipts',
            hits=self.hits,stored=self.stored,changed_context_refusals=self.changed_context_refusals,
            persisted=False,release_authority=False,saved_board_receiving_still_required=True)
