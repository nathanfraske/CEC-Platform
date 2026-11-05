"""Resolve a PRIVATE transport proposal without overriding planner refusals.

Actual prescribed pad motion is a construction request, not accepted copper.
All other refused nodes retain their literal source position. This prevents
a rectangular fallback from silently undoing a stationary/body constraint.
"""


def offset(key, delta_nm, *, prescribed_pad_motion, stationary_pad_contact,
           approved_offsets, refused_keys, fallback_inside):
    if (type(key) is not tuple or len(key) != 3 or
            type(key[0]) is not int or type(key[1]) is not int or
            type(key[2]) is not tuple or len(key[2]) != 2 or
            any(type(v) is not int for v in key[2]) or
            type(delta_nm) not in (list, tuple) or len(delta_nm) != 2 or
            any(type(v) is not int for v in delta_nm) or
            type(approved_offsets) is not dict or type(refused_keys) is not set or
            any(type(flag) is not bool for flag in
                (prescribed_pad_motion, stationary_pad_contact, fallback_inside))):
        raise ValueError('explicit_native_motion_resolution_inputs_required')
    if prescribed_pad_motion and stationary_pad_contact:
        raise ValueError('moving_and_stationary_native_pad_contact_conflict')
    if stationary_pad_contact:
        return (0, 0)
    if prescribed_pad_motion:
        return tuple(delta_nm)
    if key in refused_keys:
        return (0, 0)
    if key in approved_offsets:
        value = approved_offsets[key]
        if (type(value) not in (tuple, list) or len(value) != 2 or
                any(type(v) is not int for v in value)):
            raise ValueError('literal_integer_approved_native_motion_required')
        return tuple(value)
    return tuple(delta_nm) if fallback_inside else (0, 0)
