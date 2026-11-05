"""Native lifetime operations; callers retain all electrical/ownership policy."""


def create_empty_board():
    """Create a native scratch board without activating/unloading a project.

    KiCad's Python BOARD() calls CreateEmptyBoard/GetDefaultProject. If a
    prior SaveBoard renamed the blank project, GetDefaultProject recreates it
    with LoadProject's active default and can delete a still-live Source
    project. Establish the blank project NON-actively first. This neither
    changes Source settings nor replaces any geometry/ownership check.
    """
    import pcbnew
    manager=pcbnew.GetSettingsManager()
    if manager is None:
        raise ValueError('native_empty_board_settings_manager_required')
    if manager.GetProject('') is None:
        # Missing on-disk default settings may make LoadProject return False
        # despite establishing the project. Its actual presence is decisive.
        manager.LoadProject('',False)
    if manager.GetProject('') is None:
        raise ValueError('native_empty_board_nonactivating_default_project_required')
    return pcbnew.BOARD()


def _native_pointer(item):
    """Some fresh KiCad constructors wrap their SWIG pointer twice."""
    value=item;seen=set()
    for _ in range(8):
        try:return int(value)
        except (TypeError,ValueError):pass
        if id(value) in seen or not hasattr(value,'this'):
            raise ValueError('native_container_pointer_identity_unavailable')
        seen.add(id(value));value=value.this
    raise ValueError('native_container_pointer_identity_unavailable')


def _prepare_deletion(board,items):
    """Shared lifetime/group preflight, not electrical retirement authority."""
    selected = {}
    for item in items:
        selected.setdefault(str(item.m_Uuid.AsString()), item)
    prefix='CEC_LOCAL_SUPPLY_ALLOCATION_V1|'
    for group in board.Groups():
        if not group.GetName().startswith(prefix):continue
        parts=group.GetName()[len(prefix):].split('|')
        if len(parts)!=3:raise ValueError('native_deletion_consumer_annotation_identity_unknown')
        dependencies=set(parts[:2])|set(parts[2].split(','))|{
            str(i.m_Uuid.AsString()) for i in group.GetItems()}
        if dependencies & selected.keys():
            raise ValueError('native_deletion_breaks_typed_supply_annotation:'+str(group.m_Uuid.AsString()))
    for group in list(board.Groups()):
        for item in selected.values():
            if group.ContainsItem(item):group.RemoveItem(item)
    return selected


def discard_items(board, items):
    """Permanently discard selected board items, never detach them for reuse.

    Capture identities before invalidating any proxies, deduplicate aliases,
    and remove group membership before native destruction. Callers must not
    dereference any alias afterward. For a reversible edit, retain serialized
    geometry/a board checkpoint; this operation deliberately does not return
    reusable native objects. It does not decide which copper may be removed.

    KiCad's Remove() hands borrowed proxies to Python ownership. In KiCad 10
    that finalization path was observed over-decrementing the SWIG type-registry
    capsule. Delete() keeps destruction native and clears the selected proxy.
    """
    # Typed allocation groups contain electrical boundary references in the
    # name as well as actual members. Deleting an anchor used to leave a
    # seemingly live allocation pointing at a nonexistent conductor. Refuse
    # before changing membership or destroying ANY proxy. Explicit retirement
    # of an already-invalid annotation is a separate, independently received
    # operation, not permission to invalidate a valid current proof.
    selected=_prepare_deletion(board,items)
    for item in selected.values():
        board.Delete(item)
    return len(selected)


def discard_footprint_children(board,footprint,items):
    """Native-only destruction of literal children in a PRIVATE footprint.

    FOOTPRINT.Remove has the same borrowed-proxy lifetime hazard as
    BOARD.Remove. Retain no detached proxy; validate every parent before
    group preflight, then use the container's native Delete path.
    """
    if footprint.GetClass()!='FOOTPRINT':raise ValueError('native_footprint_container_required')
    parent_uuid=str(footprint.m_Uuid.AsString());rows=list(items)
    if footprint.GetBoard() is None or _native_pointer(footprint.GetBoard())!=_native_pointer(board):
        raise ValueError('literal_native_footprint_board_parent_required')
    if not rows or any(not hasattr(item,'GetParentFootprint') or item.GetParentFootprint() is None
            or str(item.GetParentFootprint().m_Uuid.AsString())!=parent_uuid
            or _native_pointer(item.GetParentFootprint())!=_native_pointer(footprint) for item in rows):
        raise ValueError('literal_native_footprint_child_parent_required')
    selected=_prepare_deletion(board,rows)
    for item in selected.values():footprint.Delete(item)
    return len(selected)
