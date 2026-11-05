"""Bounded, loss-aware identity across the request DTO's JSON boundary.

JSON changes integer object keys to strings and tuples to arrays.  Those
are the only normalizations here; conductor dimensions, booleans, numbers,
proofs and unknown fields are not discarded or coerced.  This is an identity
comparison aid, never a source of electrical or routing authority.
"""
import json
import math
import time


def canonical(value, *, deadline):
    """Return exact canonical JSON, refusing ambiguous or unbounded DTOs."""
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError('finite_request_wire_deadline_required')
    nodes = 0
    characters = 0

    def visit(item, depth):
        nonlocal nodes, characters
        nodes += 1
        if time.monotonic() >= deadline:
            raise ValueError('request_wire_identity_deadline')
        if nodes > 65536 or depth > 64:
            raise ValueError('bounded_request_wire_structure_required')
        kind = type(item)
        if kind is str:
            characters += len(item)
            if characters > 1048576:
                raise ValueError('bounded_request_wire_text_required')
            return item
        if kind is int:
            if item.bit_length() > 4096:
                raise ValueError('bounded_request_wire_integer_required')
            return item
        if kind is float:
            if not math.isfinite(item):
                raise ValueError('finite_request_wire_number_required')
            return item
        if item is None or kind is bool:
            return item
        if kind in (list, tuple):
            if len(item) > 65536:
                raise ValueError('bounded_request_wire_structure_required')
            return [visit(child, depth + 1) for child in item]
        if kind is dict:
            if len(item) > 65536:
                raise ValueError('bounded_request_wire_structure_required')
            result = {}
            for key, child in item.items():
                if type(key) is int:
                    if key.bit_length() > 4096:
                        raise ValueError('bounded_request_wire_integer_required')
                    key = str(key)
                elif type(key) is not str:
                    raise ValueError('string_or_integer_request_wire_key_required')
                if key in result:
                    raise ValueError('ambiguous_request_wire_key')
                # Keys consume the same finite text/node budget as values.
                visit(key, depth + 1)
                result[key] = visit(child, depth + 1)
            return result
        raise ValueError('literal_json_request_wire_value_required')

    normalized = visit(value, 0)
    result = json.dumps(normalized, sort_keys=True, allow_nan=False,
                        separators=(',', ':'))
    if time.monotonic() >= deadline:
        raise ValueError('request_wire_identity_deadline')
    return result
