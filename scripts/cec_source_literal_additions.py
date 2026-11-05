"""Opaque-source additive producer. Independent native/current replay remains authority."""
import json
import re
from cec_source_retaining_ses_import import children, kind

EXTENSIBLE_GROUPS = frozenset((
    'CEC_LOCAL_POFV_SIGNAL_VIA', 'CEC_LOCAL_ENDPOINT_NECKDOWN',
    'CEC_LOCAL_PAIR_RETURN_VIA'))
ROOT_METADATA = frozenset(('version','generator','generator_version','general',
    'paper','layers','setup','net','embedded_fonts','title_block','property','embedded_files'))
OBJECT_KINDS = frozenset(('segment','via','arc','zone','footprint','group',
    'gr_line','gr_arc','gr_rect','gr_poly','gr_text','gr_text_box','gr_circle',
    'dimension','target','image'))


def _atoms(text):
    """Scalar tokens with exact lexemes; reject nested/ambiguous member syntax."""
    result=[];i=0
    while i<len(text):
        if text[i].isspace():i+=1;continue
        if text[i]==';':
            i=text.find('\n',i)
            if i<0:break
            continue
        start=i
        if text[i]=='"':
            i+=1;escaped=False
            while i<len(text):
                c=text[i];i+=1
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':break
            else:raise ValueError('unterminated_scalar')
            token=text[start:i]
            try:value=json.loads(token)
            except ValueError as exc:raise ValueError('unsupported_scalar_escape') from exc
        else:
            match=re.match(r'[^\s();"]+',text[i:])
            if not match:raise ValueError('nested_or_invalid_scalar')
            token=match.group();value=token;i+=len(token)
        result.append((value,token))
    return result


def _root(text):
    if type(text) is not str or len(text.encode('utf-8'))>64*1024*1024:
        raise ValueError('bounded_native_text_required')
    # children() checks quoting/comments. This additional scan forbids a second
    # root or a trailing token; untouched leading/trailing comments are legal.
    depth=0;quoted=escaped=comment=False;start=end=None
    for i,c in enumerate(text):
        if comment:
            if c=='\n':comment=False
            continue
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
            continue
        if c==';':comment=True;continue
        if c=='"':
            if depth==0:raise ValueError('outside_root_scalar')
            quoted=True
        elif c=='(':
            if depth==0:
                if start is not None:raise ValueError('multiple_native_roots')
                start=i
            depth+=1
        elif c==')':
            depth-=1
            if depth<0:raise ValueError('unbalanced_native_root')
            if depth==0:end=i
        elif depth==0 and not c.isspace():raise ValueError('outside_root_scalar')
    if depth or quoted or start is None or end is None:raise ValueError('unbalanced_native_root')
    node=text[start:end+1]
    if kind(node)!='kicad_pcb':raise ValueError('native_board_root_required')
    spans=[(a+start,b+start) for a,b in children(node)]
    if len(spans)>30000:raise ValueError('native_node_bound')
    return spans,end


def _child(node,name):
    matches=[(a,b) for a,b in children(node) if kind(node[a:b])==name]
    if len(matches)>1:raise ValueError('duplicate_'+name+'_child')
    return matches[0] if matches else None


def _uuid(node):
    span=_child(node,'uuid')
    if span is None:return None
    a,b=span;tokens=_atoms(node[a+1:b-1])
    if len(tokens)!=2 or not tokens[1][0]:raise ValueError('exact_native_uuid_required')
    return tokens[1][0]


def _inventory(text):
    spans,end=_root(text);result={};seen=set();stack=[text[a:b] for a,b in spans]
    while stack:
        node=stack.pop();uid=_uuid(node)
        if kind(node)=='uuid':
            tokens=_atoms(node[1:-1])
            if len(tokens)!=2 or not tokens[1][0]:raise ValueError('exact_native_uuid_required')
            uid=tokens[1][0]
        if uid:
            if uid in seen:raise ValueError('duplicate_native_uuid')
            seen.add(uid)
            if len(seen)>100000:raise ValueError('native_uuid_bound')
        stack.extend(node[a:b] for a,b in children(node) if kind(node[a:b])!='uuid')
    for a,b in spans:
        node=text[a:b];uid=_uuid(node)
        if uid:result[uid]=(a,b,node)
        elif kind(node) in OBJECT_KINDS:raise ValueError('native_object_without_uuid')
    return result,seen,spans,end


def _members(group):
    span=_child(group,'members')
    if span is None:raise ValueError('exact_group_members_required')
    a,b=span;tokens=_atoms(group[a+1:b-1])
    values=[v for v,t in tokens[1:]]
    if len(values)>4096 or len(set(values))!=len(values) or any(not v for v in values):
        raise ValueError('bounded_unique_group_members_required')
    return span,values,{v:t for v,t in tokens[1:]}


def _group_name(group):
    first=min((a for a,b in children(group)),default=len(group)-1)
    tokens=_atoms(group[1:first])
    if len(tokens)!=2 or tokens[0][0]!='group':raise ValueError('exact_group_name_required')
    return tokens[1][0]


def _canonical(node):
    """Token-only comparison removes formatting/comments, never field values."""
    parts=[];i=0;quoted=escaped=False
    # Split parentheses outside strings, while retaining exact scalar values.
    while i<len(node):
        if node[i].isspace():i+=1;continue
        if node[i]==';':
            i=node.find('\n',i)
            if i<0:break
            continue
        if node[i] in '()':parts.append(node[i]);i+=1;continue
        if node[i]=='"':
            start=i;i+=1;escaped=False
            while i<len(node):
                c=node[i];i+=1
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':break
            else:raise ValueError('unterminated_scalar')
            parts.append(('scalar',json.loads(node[start:i])))
        else:
            match=re.match(r'[^\s();"]+',node[i:])
            if not match:raise ValueError('invalid_native_token')
            parts.append(('scalar',match.group()));i+=len(match.group())
    return tuple(parts)


def _net_names(text,spans):
    mapping={}
    for a,b in spans:
        node=text[a:b]
        if kind(node)=='net':
            tokens=_atoms(node[1:-1])
            if len(tokens)==3:
                key,value=tokens[1][0],tokens[2][0]
                if key in mapping and mapping[key]!=value:raise ValueError('ambiguous_root_net')
                mapping[key]=value
    return mapping


def _ground(zone,nets):
    if kind(zone)!='zone' or _child(zone,'keepout') is not None:return False
    identities=[]
    for name in ('net','net_name'):
        span=_child(zone,name)
        if span:
            a,b=span;tokens=_atoms(zone[a+1:b-1])
            if len(tokens)!=2:raise ValueError('exact_zone_net_required')
            value=tokens[1][0];identities.append(nets.get(value,value) if name=='net' else value)
    return bool(identities) and all(value=='GND' for value in identities)


def incoming_copper_nets(text,uuids):
    """Read literal saved net names BEFORE native connectivity normalization.

    A numeric legacy ID needs an explicit root mapping. A quoted numeric
    name is a name, never a lookup key. This grants no ownership/admission.
    """
    if (type(uuids) not in (set,list,tuple,frozenset) or not 1<=len(uuids)<=512
            or len(set(uuids))!=len(uuids)
            or any(type(u) is not str or not u for u in uuids)):
        raise ValueError('bounded_literal_copper_identity_scope_required')
    inventory,_,spans,_=_inventory(text)
    nets=_net_names(text,spans);result={}
    for uid in uuids:
        if uid not in inventory:raise ValueError('literal_saved_copper_identity_missing')
        node=inventory[uid][2]
        if kind(node) not in ('segment','via','arc'):
            raise ValueError('literal_saved_copper_object_required')
        span=_child(node,'net')
        if span is None:raise ValueError('literal_saved_copper_net_missing')
        a,b=span;tokens=_atoms(node[a+1:b-1])
        if len(tokens)!=2:raise ValueError('literal_saved_copper_net_ambiguous')
        value,lexeme=tokens[1]
        if not lexeme.startswith('"'):
            if value not in nets:raise ValueError('literal_saved_copper_net_id_unresolved')
            value=nets[value]
        if not value:raise ValueError('literal_saved_copper_net_name_required')
        result[uid]=value
    return result


def assemble(source_text,native_text,*,ground_ids=()):
    """Retain original root/all source nodes; append only exact native additions.

    Only existing actual GND filled_polygon children and monotone members of
    the three independently received typed groups may change. This producer
    grants no group, fabrication, route or current qualification.
    """
    old,source_ids,source_spans,_=_inventory(source_text)
    new,native_ids,native_spans,_=_inventory(native_text)
    if not old.keys()<=new.keys():raise ValueError('source_native_item_retirement_forbidden')
    added={uid:node for uid,(a,b,node) in new.items() if uid not in old}
    if set(added)&source_ids:raise ValueError('new_uuid_aliases_nested_source_item')
    if any(kind(node) not in ('segment','via','group') for node in added.values()):
        raise ValueError('unsupported_new_native_node')
    source_kinds={kind(source_text[a:b]) for a,b in source_spans}
    for a,b in native_spans:
        node=native_text[a:b]
        if _uuid(node) is None and kind(node) not in ROOT_METADATA|source_kinds:
            raise ValueError('unsupported_new_root_node')
    copper={uid for uid,node in added.items() if kind(node) in ('segment','via')}
    for uid,node in added.items():
        if kind(node)=='group':
            span,members,tokens=_members(node)
            if not members or not set(members)<=copper:raise ValueError('new_group_claims_nonnew_copper')
    if len(set(ground_ids))!=len(ground_ids) or not set(ground_ids)<=old.keys():
        raise ValueError('exact_existing_ground_scope_required')
    old_nets=_net_names(source_text,source_spans);new_nets=_net_names(native_text,native_spans)
    replacements={}
    for uid in ground_ids:
        original=old[uid][2];regenerated=new[uid][2]
        if not _ground(original,old_nets) or not _ground(regenerated,new_nets):
            raise ValueError('only_existing_native_ground_fills_allowed')
        from cec_source_retaining_ses_import import replace_fills
        replacements[uid]=replace_fills(original,regenerated)
    for uid,(a,b,original) in old.items():
        if kind(original)!='group':continue
        regenerated=new[uid][2]
        if kind(regenerated)!='group':raise ValueError('source_group_kind_mutated')
        span,before,old_tokens=_members(original);other,after,new_tokens=_members(regenerated)
        a0,b0=span;a1,b1=other
        if _canonical(original[:a0]+original[b0:])!=_canonical(regenerated[:a1]+regenerated[b1:]):
            raise ValueError('source_group_nonmember_fields_mutated')
        if set(before)==set(after):continue
        incoming=set(after)-set(before)
        if (_group_name(original) not in EXTENSIBLE_GROUPS or not set(before)<=set(after)
                or not incoming or not incoming<=copper):
            raise ValueError('source_group_extension_not_exact_new_copper')
        if _group_name(original)!='CEC_LOCAL_ENDPOINT_NECKDOWN' and any(kind(added[u])!='via' for u in incoming):
            raise ValueError('typed_via_group_extension_requires_new_vias')
        newline='\r\n' if '\r\n' in source_text else '\n'
        members_node=original[a0:b0];end=children(members_node,root_end=True)
        extension=''.join(newline+'\t\t'+new_tokens[u] for u in after if u in incoming)
        replacements[uid]=original[:a0]+members_node[:end]+extension+members_node[end:]+original[b0:]
    result=source_text
    for uid,node in sorted(replacements.items(),key=lambda row:old[row[0]][0],reverse=True):
        a,b,_=old[uid];result=result[:a]+node+result[b:]
    _,end=_root(result);newline='\r\n' if '\r\n' in source_text else '\n'
    if added:result=result[:end]+newline+newline.join(added.values())+newline+result[end:]
    final,_,_,_=_inventory(result)
    if final.keys()!=old.keys()|added.keys():raise ValueError('literal_additive_identity_mismatch')
    return result
