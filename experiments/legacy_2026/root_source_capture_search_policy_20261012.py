"""Choose search memory from a complete actual source-capture inventory.

No routing, current, geometry or receiving permission is granted here.
Empty, complete inventories need no accumulated-run state; protected or
unclassified owners retain the real capture predicate. Unknown metadata
does not mean an empty inventory.
"""


def source_capture_search_predicate(guard):
    if not callable(guard):
        raise ValueError('actual_source_capture_guard_required')
    active = guard.active
    complete = guard.complete
    owners = guard.unclassified_owners
    if (type(active) is not bool or type(complete) is not bool or not complete
            or type(owners) is not int or not 0 <= owners <= 4096):
        raise ValueError('complete_typed_source_capture_inventory_required')
    if not active and owners == 0:
        return None

    def reserved(start, end, width, layer):
        return guard(tuple(start), tuple(end), width, layer)

    return reserved
