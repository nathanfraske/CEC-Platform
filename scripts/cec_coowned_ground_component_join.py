"""Explicit full-class input-capacitor/control Ground island joins.

This is not the legacy low-power join, a decoupler-placement certificate,
new current authority, or a fabrication/ripple/thermal qualification.
Every saved receive independently re-exports the canonical schematic and
derives every actual co-owned native contact before accepting any join.
"""
import cec_ground_component_join as join


def plan(board, *, board_hint, pad_uuid, timeout_s=10., max_pairs=24, max_length_mm=12.):
    if type(pad_uuid) is not str or not pad_uuid:
        raise ValueError('explicit_coowned_source_ground_pad_required')
    return join._plan(board, board_hint=board_hint, timeout_s=timeout_s,
        max_pairs=max_pairs, max_length_mm=max_length_mm, pad_uuid=pad_uuid,
        coowned_input_control=True)


def construct_private(board, proposal, *, board_hint):
    return join._construct_private(board, proposal, board_hint=board_hint,
        coowned_input_control=True)


def receive(source, candidate, *, board_hint, pad_uuid, timeout_s=10.):
    if type(pad_uuid) is not str or not pad_uuid:
        raise ValueError('explicit_coowned_source_ground_pad_required')
    return join._receive(source, candidate, board_hint=board_hint, timeout_s=timeout_s,
        coowned_input_control_pad_uuid=pad_uuid)
