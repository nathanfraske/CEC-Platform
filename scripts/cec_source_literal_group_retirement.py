"""Opaque exact copper/member subtraction; supplies NO retirement authority.

Electrical receivers must independently derive every cut and factory-group
member. The legacy ungrouped literal writer stays strict. This writer owns
only the spelling of an already-proved exact subtraction.
"""
import json
import re
from pathlib import Path

import cec_source_literal_additions as literal


def _drop_members(node, selected):
    (a,b),values,_=literal._members(node)
    if not selected or not selected<=set(values):
        raise ValueError('actual_exact_group_members_required')
    spans=[];i=a+1
    while i<b-1:
        if node[i].isspace():i+=1;continue
        if node[i]==';':
            end=node.find('\n',i)
            i=b-1 if end<0 else end
            continue
        start=i
        if node[i]=='"':
            i+=1;escaped=False
            while i<b-1:
                c=node[i];i+=1
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':break
            else:raise ValueError('unterminated_group_member')
            value=json.loads(node[start:i])
        else:
            match=re.match(r'[^\s();"]+',node[i:b-1])
            if not match:raise ValueError('literal_scalar_group_member_required')
            value=match.group();i+=len(value)
        if value in selected:spans.append((start,i))
    if len(spans)!=len(selected):raise ValueError('unique_exact_member_spelling_required')
    result=node
    for x,y in reversed(spans):result=result[:x]+result[y:]
    if literal._members(result)[1]!=[v for v in values if v not in selected]:
        raise ValueError('literal_member_subtraction_changed_unselected_members')
    return result


def subtract(source_text, uuids, group_member_retirements):
    if (type(uuids)not in(list,tuple,set,frozenset)or not 1<=len(uuids)<=132
            or len(set(uuids))!=len(uuids)or any(type(u)is not str or not u for u in uuids)
            or type(group_member_retirements)is not dict or not 1<=len(group_member_retirements)<=4):
        raise ValueError('bounded_exact_grouped_copper_subtraction_required')
    selected=set(uuids);nodes,_,_,_=literal._inventory(source_text)
    if (not selected<=nodes.keys()
            or any(literal.kind(nodes[u][2])not in('segment','via')for u in selected)):
        raise ValueError('actual_root_native_segment_or_via_retirement_required')
    expected={uid:set(literal._members(node)[1])&selected for uid,(_,_,node)in nodes.items()
        if literal.kind(node)=='group'and set(literal._members(node)[1])&selected}
    supplied={}
    for uid,values in group_member_retirements.items():
        if (type(uid)is not str or not uid or type(values)not in(list,tuple,set,frozenset)
                or not 1<=len(values)<=8 or len(set(values))!=len(values)
                or any(type(v)is not str or not v for v in values)):
            raise ValueError('finite_literal_group_membership_scope_required')
        supplied[uid]=set(values)
    if supplied!=expected:
        raise ValueError('exact_all_and_only_touched_group_memberships_required')
    changes={u:''for u in selected}
    changes.update({u:_drop_members(nodes[u][2],values)for u,values in supplied.items()})
    result=source_text
    for uid in sorted(changes,key=lambda u:nodes[u][0],reverse=True):
        a,b,_=nodes[uid];result=result[:a]+changes[uid]+result[b:]
    actual,_,_,_=literal._inventory(result)
    if actual.keys()!=nodes.keys()-selected or any(actual[u][2]!=(changes[u]if u in supplied else nodes[u][2])for u in actual):
        raise ValueError('grouped_literal_retirement_changed_unowned_source')
    return result


def write_native_projection(source,target,uuids,group_member_retirements,expected_native):
    import pcbnew
    import cec_source_retaining_ses_import as raw
    from cec_cell_row_rebuild import _source_binding
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target or not source.is_file()or not target.is_file():
        raise ValueError('distinct_existing_private_grouped_cut_projection_required')
    text=raw.raw_text(source)
    raw.write_raw(target,subtract(text,uuids,group_member_retirements))
    actual=pcbnew.LoadBoard(str(target))
    if _source_binding(actual)!=_source_binding(expected_native):
        raise ValueError('grouped_literal_cut_differs_from_independent_native_subtraction')
    if raw.raw_text(source)!=text:raise ValueError('grouped_projection_changed_source')
    return dict(exact_opaque_source_subtraction=True,only_exact_derived_memberships_removed=True,
        independent_full_native_inventory_and_membership_equal=True,
        group_member_retirements={k:sorted(v)for k,v in group_member_retirements.items()},
        electrical_retirement_authority=False,release_authority=False)
