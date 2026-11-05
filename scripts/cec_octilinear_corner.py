"""Exact integer corner classification/insets; no copper or net authority."""
import math


def kind(first, second):
    """Classify a true 90-degree pair of cardinal OR diagonal vectors."""
    values = (first, second)
    if any(not isinstance(v, (tuple, list)) or len(v) != 2
            or any(type(x) is not int or abs(x) > 2000000000 for x in v) for v in values):
        raise ValueError('exact_finite_integer_corner_vectors_required')
    if any(v == (0, 0) or list(v) == [0, 0] for v in values):
        return None
    if any(x and y and abs(x) != abs(y) for x, y in values):
        return None
    if first[0]*second[0]+first[1]*second[1] != 0:
        return None
    return 'diagonal' if first[0] and first[1] else 'cardinal'


def coordinate_inset(first, second, *, maximum_nm, minimum_nm):
    """Bound actual path retreat, not a diagonal's longer x+y distance.

    Nanometre rounding must never exceed the requested physical maximum or
    forty percent of either leg, or silently fall below its physical minimum.
    A diagonal pair becomes a cardinal bridge; a cardinal pair a 45 bridge.
    """
    if any(type(n) is not int or not 0 < n <= 2000000000 for n in (maximum_nm, minimum_nm)):
        raise ValueError('positive_finite_integer_chamfer_bounds_required')
    style = kind(first, second)
    if style is None:
        return None
    squared_scale = 2 if style == 'diagonal' else 1
    step = min(math.isqrt(maximum_nm*maximum_nm//squared_scale),
        *(2*max(abs(x), abs(y))//5 for x, y in (first, second)))
    return step if step > 0 and step*step*squared_scale >= minimum_nm*minimum_nm else None


def coordinate_insets(first,second,*,maximum_nm,minimum_nm,max_candidates=8):
    """Finite descending cutbacks, including the unchanged physical minimum.

    A failed preferred chord is not a proof that every smaller legal chord is
    blocked. This supplies geometry only; every caller must recheck complete
    copper, contact and process permissions for EACH sample before mutation.
    """
    if type(max_candidates) is not int or not 1<=max_candidates<=8:
        raise ValueError('bounded_corner_cutback_portfolio_required')
    start=coordinate_inset(first,second,maximum_nm=maximum_nm,minimum_nm=minimum_nm)
    if start is None:return []
    scale=2 if kind(first,second)=='diagonal' else 1
    minimum=math.isqrt(minimum_nm*minimum_nm//scale)
    if minimum*minimum*scale<minimum_nm*minimum_nm:minimum+=1
    result=[start]
    while len(result)<max_candidates-1:
        value=result[-1]//2
        if value<minimum:break
        result.append(value)
    if max_candidates>1 and result[-1]!=minimum:result.append(minimum)
    return result
