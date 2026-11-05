"""Literal ERC-only repair for two exact manufacturer-selected DBV supplies.

This operator changes no circuit connectivity, physical geometry, load budget
or runtime routing permission. Source intake/export/parity must be repeated.
"""
import copy
import hashlib
import re
import cec_sch_lint as sch
import cec_synth_pipeline as synth

CONTRACTS={
 'INA181A2IDBVR':dict(pin='6',name='VS',count=6,
    footprints=('p:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL','cec-Package_TO_SOT_SMD:SOT-23-6',
        'cec-Package_TO_SOT_SMD:SOT-23-6_TI_DBV0006A'),
    source='https://www.ti.com/lit/ds/symlink/ina181.pdf',revision='SBOS793H',table='5-1',page=4),
 'TLV7011DBVR':dict(pin='5',name='VCC',count=5,
    footprints=('p:TSOT-23-5_L2.9-W1.6-P0.95-LS2.8-BL','cec-Package_TO_SOT_SMD:SOT-23-5'),
    source='https://www.ti.com/lit/ds/symlink/tlv7011.pdf',revision='SLVSDM5F',table='Pin Functions',page=3)}


def _symbols(text):
    root=synth.parse_sexpr(text)
    container=synth._first(root,'lib_symbols') if root[0]=='kicad_sch' else root
    if container is None or container[0]not in ('lib_symbols','kicad_symbol_lib'):
        raise ValueError('canonical_symbol_container_required')
    return list(synth._kids(container,'symbol'))


def _pins(symbol):
    queue=[symbol];result=[]
    while queue:
        node=queue.pop()
        if isinstance(node,list)and node:
            if node[0]=='pin':result.append(node)
            queue.extend(c for c in node if isinstance(c,list))
    return result


def _contract(symbol):
    name=str(symbol[1]).split(':')[-1];c=CONTRACTS.get(name)
    if c is None:return None
    props={p[1]:p[2]for p in synth._kids(symbol,'property')if len(p)>2}
    if props.get('MPN')!=name or props.get('Value')!=name or props.get('Footprint')not in c['footprints']:
        raise ValueError('exact_selected_mpn_value_package_required')
    if synth._first(symbol,'extends')is not None:raise ValueError('inherited_symbol_out_of_scope')
    pins=_pins(symbol)
    if len(pins)!=c['count']or {synth._val(p,'number','')for p in pins}!={str(i)for i in range(1,c['count']+1)}:
        raise ValueError('complete_unique_physical_pin_inventory_required')
    target=[p for p in pins if synth._val(p,'number','')==c['pin']]
    if len(target)!=1 or synth._val(target[0],'name','')!=c['name']:
        raise ValueError('manufacturer_named_physical_supply_pin_required')
    if target[0][1]not in ('unspecified','power_in'):raise ValueError('contradictory_existing_pin_type')
    return name,c,target[0]


def plan_text(text):
    symbols=_symbols(text);rows=[];edits=[];seen=set()
    for symbol in symbols:
        found=_contract(symbol)
        if found is None:continue
        name,c,pin=found
        if symbol[1]in seen:raise ValueError('duplicate_selected_symbol')
        seen.add(symbol[1])
        if pin[1]=='power_in':continue
        # Locate native literal symbol/pin blocks; never serialize the file.
        roots=list(sch.iter_children(text))
        container=next((b for tag,b in roots if tag=='lib_symbols'),text)
        blocks=[b for tag,b in sch.iter_children(container)if tag=='symbol'
            and synth.parse_sexpr(b)[1]==symbol[1]]
        if len(blocks)!=1 or text.count(blocks[0])!=1:raise ValueError('unique_literal_symbol_required')
        block=blocks[0];queue=[block];literal=[]
        while queue:
            child=queue.pop()
            for tag,b in sch.iter_children(child):
                if tag=='pin'and synth._val(synth.parse_sexpr(b),'number','')==c['pin']:literal.append(b)
                elif tag=='symbol':queue.append(b)
        if len(literal)!=1 or block.count(literal[0])!=1:raise ValueError('unique_literal_pin_required')
        old=literal[0];m=re.match(r'\(pin\s+(unspecified)\b',old)
        if not m:raise ValueError('literal_unspecified_type_required')
        offset=text.index(block)+block.index(old)+m.start(1)
        edits.append((offset,offset+len('unspecified'),'power_in'))
        rows.append(dict(symbol=symbol[1],mpn=name,pin=c['pin'],name=c['name'],old='unspecified',new='power_in',manufacturer=c))
    result=text
    for a,b,value in sorted(edits,reverse=True):result=result[:a]+value+result[b:]
    return dict(text=result,changes=rows,source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        candidate_sha256=hashlib.sha256(result.encode()).hexdigest(),current_authority=False,release_authority=False)


def receive_text(before,after):
    """Independent parsed role-delta check plus exact literal token replay."""
    old=_symbols(before);new=_symbols(after)
    if len(old)!=len(new):raise ValueError('symbol_inventory_changed')
    restored=copy.deepcopy(new);count=0
    for a,b,r in zip(old,new,restored):
        ca=_contract(a);cb=_contract(b)
        if a==b:continue
        if ca is None or cb is None or ca[0]!=cb[0]or ca[2][1]!='unspecified'or cb[2][1]!='power_in':
            raise ValueError('unowned_symbol_or_role_changed')
        rp=next(p for p in _pins(r)if synth._val(p,'number','')==ca[1]['pin']);rp[1]='unspecified'
        if r!=a:raise ValueError('non_type_symbol_change')
        count+=1
    # Whole document literal replay also protects instance UUIDs, nets,
    # hierarchy, whitespace and every node outside embedded libraries.
    expected=plan_text(before)
    if expected['text']!=after or count!=len(expected['changes']):raise ValueError('non_type_literal_change')
    return dict(ok=True,complete=True,changed_pin_types=count,all_other_bytes_exact=True,
                connectivity_parts_geometry_budgets_unchanged=True,current_authority=False,release_authority=False)


def receive_netlist_types(before,after):
    """Independently replay library and instance-node ERC annotations only.

    KiCad exports a pin's electrical type both in libparts and every connected
    net node. Reverting only the former leaves a genuine type-only difference;
    ignoring all node metadata would instead hide unrelated electrical edits.
    """
    import cec_source_netlist_semantics as semantic
    restored=copy.deepcopy(after);lib_changes=[];node_changes=[]
    oldparts=list(synth._kids(synth._first(before,'libparts')or[],'libpart'))
    newparts=list(synth._kids(synth._first(restored,'libparts')or[],'libpart'))
    if len(oldparts)!=len(newparts):raise ValueError('exported_libpart_inventory_changed')
    changed={}
    for old,new in zip(oldparts,newparts):
        if old==new:continue
        key=(synth._val(old,'lib',''),synth._val(old,'part',''));c=CONTRACTS.get(key[1])
        if c is None or key!=(synth._val(new,'lib',''),synth._val(new,'part','')):
            raise ValueError('unowned_exported_library_role_change')
        pins=[list(synth._kids(synth._first(p,'pins')or[],'pin'))for p in(old,new)]
        if any(len(rows)!=c['count'] or {synth._val(p,'num','')for p in rows}!=
                {str(i)for i in range(1,c['count']+1)}for rows in pins):
            raise ValueError('exported_complete_physical_pin_inventory_required')
        selected=[[p for p in rows if synth._val(p,'num','')==c['pin']][0]for rows in pins]
        if any(synth._val(p,'name','')!=c['name']for p in selected):
            raise ValueError('exported_named_supply_pin_changed')
        if [synth._val(p,'type','')for p in selected]!=['unspecified','power_in']:
            raise ValueError('exact_exported_supply_type_delta_required')
        synth._first(selected[1],'type')[1]='unspecified'
        if old!=new:raise ValueError('exported_non_type_library_change')
        if key in changed:raise ValueError('ambiguous_exported_supply_library')
        changed[key]=c;lib_changes.append(dict(library=key[0],part=key[1],pin=c['pin'],name=c['name']))
    components={}
    for comp in synth._kids(synth._first(before,'components')or[],'comp'):
        ref=synth._val(comp,'ref','')
        if not ref or ref in components:raise ValueError('unique_exported_component_reference_required')
        components[ref]=comp
    oldnets=list(synth._kids(synth._first(before,'nets')or[],'net'))
    newnets=list(synth._kids(synth._first(restored,'nets')or[],'net'))
    if len(oldnets)!=len(newnets):raise ValueError('exported_net_inventory_changed')
    seen=set()
    for oldnet,newnet in zip(oldnets,newnets):
        if synth._val(oldnet,'name','')!=synth._val(newnet,'name',''):
            raise ValueError('exported_net_name_or_order_changed')
        oldnodes=list(synth._kids(oldnet,'node'));newnodes=list(synth._kids(newnet,'node'))
        if len(oldnodes)!=len(newnodes):raise ValueError('exported_node_inventory_changed')
        for a,b in zip(oldnodes,newnodes):
            if a==b:continue
            ref=synth._val(a,'ref','');pin=synth._val(a,'pin','');comp=components.get(ref)
            if comp is None:raise ValueError('source_part_for_exported_pin_required')
            lib=synth._first(comp,'libsource')or[]
            key=(synth._val(lib,'lib',''),synth._val(lib,'part',''));c=changed.get(key)
            fields=synth._first(comp,'fields')or[]
            mpns=[f[-1]for f in synth._kids(fields,'field')if synth._val(f,'name','')=='MPN']
            if (c is None or pin!=c['pin'] or mpns!=[key[1]]
                    or synth._val(comp,'value','')!=key[1]
                    or synth._val(comp,'footprint','')not in c['footprints']
                    or synth._val(a,'pinfunction','')!=synth._val(b,'pinfunction','')
                    or synth._val(a,'pinfunction','')not in (c['name'],c['name']+'_'+c['pin'])
                    or [synth._val(n,'pintype','')for n in(a,b)]!=['unspecified','power_in']):
                raise ValueError('exact_manufacturer_part_named_node_type_required')
            if (ref,pin)in seen:raise ValueError('duplicate_exported_supply_node')
            seen.add((ref,pin));synth._first(b,'pintype')[1]='unspecified'
            if a!=b:raise ValueError('non_type_exported_node_change')
            node_changes.append(dict(ref=ref,part=key[1],pin=pin,name=c['name'],
                net=synth._val(oldnet,'name','')))
    if semantic.metadata(restored)['netlist_semantic_sha256']!=semantic.metadata(before)['netlist_semantic_sha256']:
        raise ValueError('exported_non_type_semantics_changed')
    return dict(ok=True,complete=True,libpart_changes=lib_changes,node_changes=node_changes,
        all_other_export_semantics_exact=True,connectivity_and_parts_unchanged=True,
        current_authority=False,release_authority=False)
