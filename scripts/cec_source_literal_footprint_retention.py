"""Keep every unselected Source footprint subtree byte-exact after a pose.

The native serializer owns only explicitly selected footprint subtrees. This
pure text projection grants no pose, population, copper or manufacturing
authority; the existing independent saved-pose receiver still reconstructs
the selected objects and checks every native contact and unselected object.
"""
import cec_source_literal_additions as literal


def retain(source_text, native_text, selected_footprint_uuids):
    if (type(selected_footprint_uuids) not in (list, tuple, set)
            or not 1 <= len(selected_footprint_uuids) <= 8
            or any(type(uid) is not str or not uid for uid in selected_footprint_uuids)
            or len(set(selected_footprint_uuids)) != len(selected_footprint_uuids)):
        raise ValueError('finite_explicit_selected_footprint_projection_required')
    old, *_ = literal._inventory(source_text)
    new, *_ = literal._inventory(native_text)
    before = {uid: span for uid, span in old.items() if literal.kind(span[2]) == 'footprint'}
    after = {uid: span for uid, span in new.items() if literal.kind(span[2]) == 'footprint'}
    selected = set(selected_footprint_uuids)
    if before.keys() != after.keys() or not selected <= before.keys():
        raise ValueError('same_complete_source_footprint_population_required')
    edits = [(after[uid][0], after[uid][1], before[uid][2]) for uid in before.keys()-selected]
    result = native_text
    for start, end, node in sorted(edits, reverse=True):
        result = result[:start]+node+result[end:]
    final, *_ = literal._inventory(result)
    if any(final[uid][2] != before[uid][2] for uid in before.keys()-selected):
        raise ValueError('unselected_source_footprint_literal_not_preserved')
    if any(final[uid][2] != after[uid][2] for uid in selected):
        raise ValueError('selected_native_footprint_projection_changed')
    return result
