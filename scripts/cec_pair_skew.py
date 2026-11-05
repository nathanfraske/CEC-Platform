"""Shared existing USB/CAN whole-route length-skew admission.

These are the existing repository signoff limits, not new electrical budgets.
Lengths use the signoff convention: summed straight copper per member net.
"""
import math


def evaluate(kind, p_length_mm, n_length_mm):
    p, n = float(p_length_mm), float(n_length_mm)
    limit = 3.81 if kind == 'usb' else 4.0
    valid = all(math.isfinite(value) and value >= 0 for value in (p, n))
    skew = abs(p - n) if valid else None
    return dict(schema=1, ok=bool(valid and skew <= limit + 1e-6),
                p_length_mm=p if math.isfinite(p) else None,
                n_length_mm=n if math.isfinite(n) else None,
                skew_mm=skew, limit_mm=limit,
                reason='nonfinite_or_negative_length' if not valid else
                       'within_limit' if skew <= limit + 1e-6 else 'whole_pair_skew_exceeded')


def from_board(board, pair):
    lengths={net:sum(math.hypot(t.GetEnd().x-t.GetStart().x,
                               t.GetEnd().y-t.GetStart().y)/1e6
                     for t in board.GetTracks()
                     if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net)
             for net in (pair['p'],pair['n'])}
    return evaluate(pair.get('kind'), lengths[pair['p']], lengths[pair['n']])
