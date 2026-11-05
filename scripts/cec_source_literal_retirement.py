"""Exact root-copper subtraction; no electrical retirement authority.

Callers independently prove source ownership, old boundaries/partitions and
all saved receiving. This helper only preserves opaque source bytes while
subtracting literal ungrouped segment/via nodes. Native serialization is not
allowed to normalize unrelated footprint properties during reconstruction.
"""
import cec_source_literal_additions as literal


def subtract(source_text,uuids):
    if (type(uuids) not in (list,tuple,set,frozenset) or not 1<=len(uuids)<=132
            or len(set(uuids))!=len(uuids) or any(type(u) is not str or not u for u in uuids)):
        raise ValueError('bounded_exact_literal_copper_retirement_required')
    selected=set(uuids);nodes,_,_,_=literal._inventory(source_text)
    if not selected<=nodes.keys() or any(literal.kind(nodes[u][2]) not in ('segment','via') for u in selected):
        raise ValueError('actual_root_native_segment_or_via_retirement_required')
    if any(set(literal._members(node)[1])&selected
            for _,_,node in nodes.values() if literal.kind(node)=='group'):
        raise ValueError('literal_source_group_membership_cannot_be_retired')
    result=source_text
    for uid in sorted(selected,key=lambda u:nodes[u][0],reverse=True):
        a,b,_=nodes[uid];result=result[:a]+result[b:]
    remaining,_,_,_=literal._inventory(result)
    if (set(remaining)!=set(nodes)-selected
            or any(remaining[u][2]!=nodes[u][2] for u in remaining)):
        raise ValueError('literal_retirement_changed_unrelated_source_node')
    return result


def write_native_projection(source,target,uuids,expected_native):
    """Exact opaque Source-minus-cut, checked against independent native cuts.

    This is NOT an electrical retirement receiver. Callers already owe the
    Source-owned cut, all boundaries/current rules and saved additive replay.
    A native no-op save can reorder a hidden footprint property's children;
    preserving the literal parent is stronger than normalizing those records.
    """
    from pathlib import Path
    import pcbnew
    import cec_field_coupling as field
    import cec_source_retaining_ses_import as raw
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target or not source.is_file() or not target.is_file():
        raise ValueError('distinct_existing_private_literal_cut_projection_required')
    text=raw.raw_text(source)
    raw.write_raw(target,subtract(text,uuids))
    actual=pcbnew.LoadBoard(str(target))
    if field._field_snapshot_inventory(actual)!=field._field_snapshot_inventory(expected_native):
        raise ValueError('literal_retirement_differs_from_independent_native_subtraction')
    if raw.raw_text(source)!=text:
        raise ValueError('literal_projection_changed_source')
    return dict(exact_opaque_source_subtraction=True,independent_full_native_inventory_equal=True,
        electrical_retirement_authority=False)
