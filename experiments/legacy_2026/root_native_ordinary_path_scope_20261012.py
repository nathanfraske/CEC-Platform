"""Validate a caller-owned finite planar path, without route/owner authority."""
import cec_route_quality as craft


def points(values):
    if (type(values) not in (list, tuple) or not 4 <= len(values) <= 64
            or len(values) % 2 or any(type(v) is not int or abs(v) > 2000000000 for v in values)):
        raise ValueError('bounded_integer_native_path_required')
    result = [tuple(values[i:i+2]) for i in range(0, len(values), 2)]
    if len(set(result)) != len(result):
        raise ValueError('native_path_repeated_vertex')
    if any(not craft.is_canonical_stroke(a, b, tolerance_nm=0) for a, b in zip(result, result[1:])):
        raise ValueError('exact_cardinal_or_fortyfive_path_required')
    return result
