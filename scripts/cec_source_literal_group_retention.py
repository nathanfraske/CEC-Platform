"""Preserve untouched Source groups through a native writer projection.

Only quoting of a valid group's UUID may differ. Group membership, order,
locks, names and opaque fields must be exact. This operates on an internally
replayed Source, never grants a received child permission to change groups.
"""
import copy
import re

import cec_copper_echo as syntax
import cec_source_retaining_ses_import as raw


def _signature(text):
    node=syntax._parse(syntax._TOKEN.findall(text))
    if not node or node[0]!='group':
        raise ValueError('literal_group_node_required')
    node=copy.deepcopy(node)
    ids=[row for row in node[1:]if isinstance(row,list)and row and row[0]=='uuid']
    members=[row for row in node[1:]if isinstance(row,list)and row and row[0]=='members']
    if len(ids)!=1 or len(ids[0])!=2 or len(members)!=1:
        raise ValueError('one_native_group_uuid_and_members_required')
    value=ids[0][1]
    bare=value[1:-1]if value.startswith('"')and value.endswith('"')else value
    if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',bare):
        raise ValueError('valid_native_group_uuid_required')
    values=members[0][1:]
    if any(type(v)is not str for v in values)or len({v.strip('"')for v in values})!=len(values):
        raise ValueError('ambiguous_native_group_members')
    ids[0][1]=bare
    # Do not use the copper parser's numerical canonicalizer here. Unknown
    # group fields remain token-exact, even for 1 versus 1.0 spellings.
    def freeze(value):
        return tuple(freeze(v)for v in value)if isinstance(value,list)else value
    return freeze(node)


def retain(source_text,native_text,excluded_group_uuids=()):
    if (type(excluded_group_uuids)not in(list,tuple,set)
            or len(excluded_group_uuids)>8
            or any(type(u)is not str or not u for u in excluded_group_uuids)
            or len(set(excluded_group_uuids))!=len(excluded_group_uuids)):
        raise ValueError('bounded_explicit_group_projection_exclusions_required')
    def groups(text):
        return {u:(a,b,text[a:b])for u,(a,b)in raw.inventory(text).items()
            if raw.kind(text[a:b])=='group'}
    before,after=groups(source_text),groups(native_text)
    excluded=set(excluded_group_uuids)
    if before.keys()!=after.keys()or not excluded<=before.keys():
        raise ValueError('same_complete_source_group_population_required')
    for uid in before.keys()-excluded:
        if _signature(before[uid][2])!=_signature(after[uid][2]):
            raise ValueError('untouched_source_group_changed:'+uid)
    result=native_text
    for a,b,node in sorted((after[u][0],after[u][1],before[u][2])for u in before.keys()-excluded)[::-1]:
        result=result[:a]+node+result[b:]
    return result
