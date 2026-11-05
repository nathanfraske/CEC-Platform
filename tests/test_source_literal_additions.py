import ast,pathlib
import pytest
import cec_source_literal_additions as m


FP='(footprint "selected" (uuid fp) (pad "1" smd (uuid pad)) (property "Datasheet" "") (future "(; not syntax)") (effects (font (size 1 1))))'
OLD='(segment (uuid old) (net "GND") (width 1))'
SEG='(segment (uuid new) (net "GND") (width .2) (native_future "exact"))'
VIA='(via (uuid barrel) (net "GND") (size .6) (drill .3))'
GND='(zone (uuid ground) (net "GND") (opaque "retain") (filled_polygon (layer "F.Cu") (pts (xy 1 2))))'
POWER='(zone (uuid power) (net "VBUS") (unknown x) (filled_polygon (pts (xy 3 4))))'
PREFIX='; root prefix ()\r\n(kicad_pcb\r\n (version 20260206) (generator "SOURCE") (opaque_root "keep ; ( )")\r\n'
SUFFIX='\r\n) ; untouched root suffix ()\r\n'


def board(*nodes):return PREFIX+'\r\n'.join(nodes)+SUFFIX
def group(name,uid='owner',members='old',extra=''):
    return '(group "'+name+'" (uuid '+uid+') '+extra+' (members '+members+'))'


@pytest.mark.parametrize('kind',['segment','via','arc'])
@pytest.mark.parametrize('legacy',[False,True])
def test_literal_incoming_copper_net_does_not_depend_on_native_graph_normalization(kind,legacy):
    net='7' if legacy else '"renamed/input"'
    text=board('(net 7 "renamed/input")',f'({kind} (uuid incoming) (net {net}))')
    assert m.incoming_copper_nets(text,{'incoming'})=={'incoming':'renamed/input'}


def test_quoted_numeric_net_name_is_not_a_legacy_numeric_id():
    text=board('(net 7 "a different name")','(segment (uuid incoming) (net "7"))')
    assert m.incoming_copper_nets(text,{'incoming'})=={'incoming':'7'}


@pytest.mark.parametrize('node,table',[
    ('(segment (uuid incoming) (net 9))',''),
    ('(segment (uuid incoming))',''),
    ('(segment (uuid incoming) (net "A") (net "B"))',''),
    ('(segment (uuid incoming) (net ""))',''),
    ('(segment (uuid incoming) (net 7))','(net 7 "A") (net 7 "B")'),
    ('(footprint "not copper" (uuid incoming))',''),
])
def test_unknown_ambiguous_or_noncopper_literal_net_refuses(node,table):
    with pytest.raises(ValueError):m.incoming_copper_nets(board(table,node),{'incoming'})


@pytest.mark.parametrize('ids',[[],['missing'],['incoming','incoming'],[None],[''],True])
def test_literal_copper_net_reader_has_explicit_bounded_unique_scope(ids):
    with pytest.raises(ValueError):
        m.incoming_copper_nets(board('(segment (uuid incoming) (net "A"))'),ids)


def test_opaque_source_root_footprints_power_comments_and_new_nodes_remain_literal():
    source=board(FP,OLD,POWER);native=board(
        '(footprint "normalized" (uuid fp) (pad "1" (uuid pad)) (effects (font (thickness .15))))',
        '(segment (uuid old) (width 99))','(zone (uuid power) (net "VBUS") (filled_polygon changed))',SEG,VIA)
    native=native.replace('(generator "SOURCE")','(generator "NATIVE")').replace('(opaque_root "keep ; ( )")','(embedded_fonts no)')
    result=m.assemble(source,native)
    for original in (FP,OLD,POWER,'(generator "SOURCE")','(opaque_root "keep ; ( )")',PREFIX,SUFFIX):assert original in result
    assert SEG in result and VIA in result and '(thickness .15)' not in result
    assert result.endswith(SUFFIX) and '\r\n' in result


def test_only_explicit_actual_ground_native_fills_transplant():
    source=board(FP,OLD,GND,POWER);native=board(FP,OLD,
        '(zone (uuid ground) (net "GND") (opaque "serializer dropped source") (filled_polygon (pts (xy 9 8))))',
        '(zone (uuid power) (net "VBUS") (filled_polygon changed))',SEG)
    result=m.assemble(source,native,ground_ids=['ground'])
    assert '(opaque "retain")' in result and '(filled_polygon (pts (xy 9 8)))' in result
    assert '(xy 1 2)' not in result and POWER in result and FP in result


def test_numeric_legacy_ground_net_requires_original_table_identity():
    source=board('(net 1 "GND")','(zone (uuid ground) (net 1) (filled_polygon old))')
    native=board('(net 1 "GND")','(zone (uuid ground) (net 1) (filled_polygon fresh))')
    assert '(filled_polygon fresh)' in m.assemble(source,native,ground_ids=['ground'])


@pytest.mark.parametrize('name',sorted(m.EXTENSIBLE_GROUPS))
def test_typed_original_groups_extend_only_with_new_native_members_preserving_opaque_text(name):
    sourcegroup=group(name,extra='; source comment\n (future "unchanged")')
    member='new' if name=='CEC_LOCAL_ENDPOINT_NECKDOWN' else 'barrel'
    nativegroup=group(name,members='"'+member+'" old',extra='(future "unchanged")')
    result=m.assemble(board(OLD,sourcegroup),board(OLD,nativegroup,SEG,VIA))
    assert '; source comment' in result and '(future "unchanged")' in result
    # Original source member lexeme/order remains; only incoming native IDs append.
    assert '(members old\r\n\t\t"'+member+'")' in result
    assert SEG in result and VIA in result


def test_unchanged_original_group_is_kept_byte_exact_despite_native_formatting():
    g=group('UNTYPED',extra='; kept comment\n (future x)')
    native=group('UNTYPED',extra='(future x)')
    assert g in m.assemble(board(OLD,g),board(OLD,native,SEG))


def test_new_group_is_exact_native_node_and_only_claims_new_copper():
    g=group('annotation',uid='new-owner',members='new barrel')
    assert g in m.assemble(board(OLD),board(OLD,SEG,VIA,g))


def test_root_uuid_cannot_be_aliased_by_new_material():
    source=board('(uuid root)',OLD)
    native=board('(uuid root)',OLD,SEG.replace('(uuid new)','(uuid root)'))
    with pytest.raises(ValueError,match='duplicate_native_uuid'):
        m.assemble(source,native)


def test_empty_datasheet_font_normalization_never_leaks_into_source_node():
    source=board(FP);native=board('(footprint "selected" (uuid fp) (pad "1" (uuid pad)) (effects (font (thickness .153))))',SEG)
    result=m.assemble(source,native)
    assert FP in result and '(property "Datasheet" "")' in result
    assert '.153' not in result and SEG in result


@pytest.mark.parametrize('fault',['duplicate_top','duplicate_nested','nested_alias',
    'unsupported_footprint','new_zone','new_arc','new_object_no_uuid',
    'unknown_root_object','source_retired','multiple_roots','trailing_scalar'])
def test_malicious_or_unsupported_additive_nodes_refuse(fault):
    source=board(FP,OLD);native=board(FP,OLD,SEG)
    if fault=='duplicate_top':native=board(FP,OLD,SEG,SEG)
    elif fault=='duplicate_nested':native=board(FP,OLD,SEG.replace('(uuid new)','(uuid pad)'))
    elif fault=='nested_alias':native=board('(footprint (uuid fp))',OLD,SEG.replace('(uuid new)','(uuid pad)'))
    elif fault=='unsupported_footprint':native=board(FP,OLD,'(footprint (uuid other))')
    elif fault=='new_zone':native=board(FP,OLD,'(zone (uuid z) (net "GND"))')
    elif fault=='new_arc':native=board(FP,OLD,'(arc (uuid a))')
    elif fault=='new_object_no_uuid':native=board(FP,OLD,'(via (size .6))')
    elif fault=='unknown_root_object':native=board(FP,OLD,'(future_new_object yes)')
    elif fault=='source_retired':native=board(FP,SEG)
    elif fault=='multiple_roots':native+=' (kicad_pcb)'
    else:native+=' unexpected'
    with pytest.raises(ValueError):m.assemble(source,native)


@pytest.mark.parametrize('fault',['unknown_group','rename','metadata','removal',
    'original_claim','duplicate_member','new_group_old_claim','nested_group_claim',
    'via_group_track','power_fill_scope','missing_ground','duplicate_ground',
    'native_ground_renet','keepout_ground'])
def test_invalid_group_mutation_and_non_ground_fill_scope_refuse(fault):
    name='CEC_LOCAL_POFV_SIGNAL_VIA';oldgroup=group(name);newgroup=group(name,members='old barrel');source=board(OLD,oldgroup,GND,POWER);native=board(OLD,newgroup,GND,POWER,SEG,VIA);ground=[]
    if fault=='unknown_group':source=source.replace(name,'UNKNOWN');native=native.replace(name,'UNKNOWN')
    elif fault=='rename':native=native.replace(name,'CEC_LOCAL_PAIR_RETURN_VIA')
    elif fault=='metadata':native=native.replace('(uuid owner)','(uuid owner) (future mutation)')
    elif fault=='removal':native=native.replace('(members old barrel)','(members barrel)')
    elif fault=='original_claim':native=native.replace('(members old barrel)','(members old power)')
    elif fault=='duplicate_member':native=native.replace('(members old barrel)','(members old barrel barrel)')
    elif fault=='new_group_old_claim':native=board(OLD,oldgroup,GND,POWER,SEG,group('annotation',uid='new-owner',members='old'))
    elif fault=='nested_group_claim':native=board(OLD,oldgroup,GND,POWER,SEG,group('a',uid='a',members='new'),group('b',uid='b',members='a'))
    elif fault=='via_group_track':native=native.replace('(members old barrel)','(members old new)')
    elif fault=='power_fill_scope':ground=['power']
    elif fault=='missing_ground':ground=['missing']
    elif fault=='duplicate_ground':ground=['ground','ground']
    elif fault=='native_ground_renet':ground=['ground'];native=native.replace('(net "GND") (opaque','(net "VBUS") (opaque')
    elif fault=='keepout_ground':ground=['ground'];native=native.replace('(uuid ground)','(uuid ground) (keepout (tracks allowed))')
    with pytest.raises(ValueError):m.assemble(source,native,ground_ids=ground)


def test_production_hook_reads_original_before_save_and_reassembles_before_exact_rules():
    path=pathlib.Path(__file__).parents[1]/'scripts/cec_additive_pair_repair.py'
    tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='save_native_additions');calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)]
    def named(name):return sorted(n.lineno for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr==name)
    assert named('raw_text')[0]<named('_save_field_snapshot')[0]<named('assemble')[0]<named('write_raw')[0]<named('LoadBoard')[0]<named('bind_local_via_rule')[0]<named('bind_local_endpoint_rule')[0]
    save=next(n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='_save_field_snapshot')
    assert isinstance(save.args[1],ast.Name) and save.args[1].id=='native_path'
    for rule in ('bind_local_via_rule','bind_local_endpoint_rule'):
        node=next(n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr==rule)
        assert isinstance(node.args[0],ast.Name) and node.args[0].id=='saved_board'
