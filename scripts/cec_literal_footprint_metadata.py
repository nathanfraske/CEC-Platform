"""Exact literal footprint-metadata splicer; no hardware/admission authority.

Callers must separately prove field ownership and native roundtrip. This
utility retains EVERY byte outside the explicitly replaced field spans,
including all other footprints' complete original literal representation.
"""
import json
import re
import cec_component_jumper_metadata as metadata

_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+')
_LIMIT = 16*1024*1024


def _tree(text):
    if type(text) is not str or not 0 < len(text.encode()) <= _LIMIT:
        raise ValueError('bounded_literal_source_required')
    roots=[];stack=[];previous=0;count=0
    for match in _TOKENS.finditer(text):
        gap=text[previous:match.start()]
        if gap and not gap.isspace():
            raise ValueError('literal_token_coverage_required')
        token=match.group();count+=1
        if count>500000:
            raise ValueError('bounded_literal_token_inventory_required')
        if token=='(':
            if len(stack)>=128:
                raise ValueError('bounded_literal_nesting_required')
            stack.append(dict(start=match.start(),tag=None,children=[]))
        elif token==')':
            if not stack:
                raise ValueError('balanced_literal_source_required')
            node=stack.pop();node['end']=match.end()
            if node['tag'] is None:
                raise ValueError('nonempty_literal_node_required')
            (stack[-1]['children'] if stack else roots).append(node)
        else:
            if not stack:
                raise ValueError('literal_root_node_required')
            if stack[-1]['tag'] is None:
                stack[-1]['tag']=token
        previous=match.end()
    if stack or len(roots)!=1 or text[previous:] and not text[previous:].isspace():
        raise ValueError('complete_balanced_literal_source_required')
    if roots[0]['tag']!='kicad_pcb':
        raise ValueError('literal_native_board_required')
    return roots[0]


def _fields(fp, tag, name):
    return [x for x in metadata._children(fp,tag)
            if name is None or len(x)>=3 and metadata._text(x[1])==name]


def splice(text, edits):
    """edits={ref:[{tag,before,after,name?}]}, exact immediate FP children."""
    tree=_tree(text)
    fps={};spans={}
    for node in tree['children']:
        if node['tag']!='footprint':
            continue
        fp=metadata._parse(text[node['start']:node['end']])
        props=_fields(fp,'property','Reference')
        if len(props)!=1:
            raise ValueError('unique_literal_component_reference_required')
        ref=metadata._text(props[0][2])
        if ref in fps:
            raise ValueError('unique_literal_component_reference_required')
        fps[ref]=fp;spans[ref]=node
    if type(edits) is not dict or not set(edits)<=set(fps):
        raise ValueError('existing_literal_component_required')
    replacements=[]
    for ref, changes in edits.items():
        if type(changes) is not list:
            raise ValueError('literal_field_edit_inventory_required')
        claimed=set();appended=[]
        for change in changes:
            if type(change) is not dict or set(change)-{'tag','name','before','after'} or not {'tag','before','after'}<=set(change):
                raise ValueError('exact_literal_field_edit_required')
            tag=change['tag'];name=change.get('name');key=(tag,name)
            if tag not in metadata._FIELDS|{'property'} or tag=='property' and not name or tag!='property' and name is not None or key in claimed:
                raise ValueError('unique_literal_metadata_field_required')
            claimed.add(key)
            actual=_fields(fps[ref],tag,name)
            if len(actual)>1 or (actual[0] if actual else None)!=change['before']:
                raise ValueError('literal_original_field_mismatch')
            before,after=change['before'],change['after']
            if after is not None:
                if not isinstance(after,list) or not after or after[0]!=tag or tag=='property' and (len(after)<3 or metadata._text(after[1])!=name):
                    raise ValueError('literal_replacement_field_mismatch')
                rendered=metadata._render(after)
                if metadata._parse(rendered)!=after:
                    raise ValueError('literal_replacement_not_representable')
            if before==after:
                continue
            matches=[s for s in spans[ref]['children'] if s['tag']==tag
                     and (name is None or _fields(['footprint',metadata._parse(text[s['start']:s['end']])],tag,name))]
            if bool(matches)!=bool(actual) or len(matches)>1:
                raise ValueError('literal_field_span_inventory_mismatch')
            if matches:
                s=matches[0]
                replacements.append((s['start'],s['end'],'' if after is None else rendered))
            elif after is not None:
                appended.append(rendered)
        if appended:
            end=spans[ref]['end']-1
            replacements.append((end,end,'\n\t\t'+'\n\t\t'.join(appended)+'\n\t'))
    previous=len(text)+1
    result=text
    for start,end,replacement in sorted(replacements,reverse=True):
        if not 0<=start<=end<=len(text) or end>previous:
            raise ValueError('nonoverlapping_literal_edits_required')
        result=result[:start]+replacement+result[end:];previous=start
    _tree(result)
    expected=metadata._parse(text)
    after_fps=metadata._footprints(expected)
    for ref,changes in edits.items():
        for change in changes:
            tag,name=change['tag'],change.get('name')
            fp=after_fps[ref]
            old=_fields(fp,tag,name)
            if old:
                index=fp.index(old[0]);fp.pop(index)
                if change['after'] is not None:
                    fp.insert(index,change['after'])
            elif change['after'] is not None:
                fp.append(change['after'])
    if metadata._parse(result)!=expected:
        raise ValueError('literal_complete_AST_delta_mismatch')
    return result
