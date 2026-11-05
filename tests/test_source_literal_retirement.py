"""No serializer normalization or arbitrary ownership from a literal cut."""
import pcbnew
import pytest
import cec_source_literal_retirement as op
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
import cec_field_coupling as field
import cec_force_current as force
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path):
    b=_board([(5,5,'/CONTROL'),(15,5,'/CONTROL')],edge=(0,0,25,25))
    a=track(b,'/CONTROL',(5,5),(15,5));z=track(b,'/OTHER',(5,10),(15,10))
    p=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,p)
    return p,force._uid(a),force._uid(z)


def hidden_field_last(path):
    """Legal opaque child order that a native no-op save does not preserve."""
    b=pcbnew.LoadBoard(str(path))
    for fp in b.GetFootprints():fp.Reference().SetVisible(False)
    field._save_field_snapshot(b,path)
    text=raw.raw_text(path);inventory=literal._inventory(text)[0]
    for _,(a,z,node) in sorted(inventory.items(),key=lambda x:x[1][0],reverse=True):
        if literal.kind(node)!='footprint':continue
        x,y=next((x,y)for x,y in raw.children(node)
            if literal.kind(node[x:y])=='property'and '"Reference"'in node[x:y])
        prop=node[x:y];span=literal._child(prop,'hide');assert span
        i,j=span;hidden=prop[i:j];prop=prop[:i]+prop[j:];prop=prop[:-1]+hidden+prop[-1:]
        node=node[:x]+prop+node[y:];text=text[:a]+node+text[z:]
    raw.write_raw(path,text)


def test_only_literal_selected_node_is_removed_with_comments_crlf_and_unknown_root(tmp_path):
    p,a,z=fixture(tmp_path);text=raw.raw_text(p)
    text=text.replace('(kicad_pcb','; retained leading comment\r\n(kicad_pcb',1)
    text=text[:-2]+'\n(property "opaque project data" "never normalize")\n'+text[-2:]
    old=literal._inventory(text)[0];projected=op.subtract(text,[a]);new=literal._inventory(projected)[0]
    assert set(new)==set(old)-{a} and all(new[u][2]==old[u][2] for u in new)
    assert '; retained leading comment\r\n' in projected and 'opaque project data' in projected
    assert old[z][2] in projected and old[a][2] not in projected


@pytest.mark.parametrize('scope',[[],[False],['invented'],['x','x'],True])
def test_no_ambiguous_missing_duplicate_or_unbounded_scope(tmp_path,scope):
    p,_,_=fixture(tmp_path)
    with pytest.raises(ValueError):op.subtract(raw.raw_text(p),scope)


def test_footprints_and_groups_are_not_root_copper_retirement(tmp_path):
    p,_,_=fixture(tmp_path);nodes=literal._inventory(raw.raw_text(p))[0]
    uid=next(u for u,v in nodes.items() if literal.kind(v[2])=='footprint')
    with pytest.raises(ValueError,match='root_native_segment_or_via'):op.subtract(raw.raw_text(p),[uid])


def test_group_member_never_silently_disappears(tmp_path):
    p,a,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(p));group=pcbnew.PCB_GROUP(b);group.SetName('ORIGINAL')
    b.Add(group);group.AddItem(next(t for t in b.GetTracks() if force._uid(t)==a));field._save_field_snapshot(b,p)
    with pytest.raises(ValueError,match='group_membership'):op.subtract(raw.raw_text(p),[a])


def test_hidden_field_child_order_is_not_rewritten_by_independent_ordinary_projection(tmp_path):
    import cec_ordinary_route_receiving as ordinary
    from test_ordinary_route_receiving import fixture as ordinary_fixture
    source,child,uid,_=ordinary_fixture(tmp_path)
    for p in (source,child):
        b=pcbnew.LoadBoard(str(p))
        for fp in b.GetFootprints():fp.Reference().SetVisible(False)
        field._save_field_snapshot(b,p)
        text=raw.raw_text(p);inventory=literal._inventory(text)[0]
        for _,(a,z,node) in sorted(inventory.items(),key=lambda x:x[1][0],reverse=True):
            if literal.kind(node)!='footprint':continue
            field_span=next((x,y) for x,y in raw.children(node)
                if literal.kind(node[x:y])=='property' and '"Reference"' in node[x:y])
            x,y=field_span;prop=node[x:y];span=literal._child(prop,'hide');assert span
            i,j=span;hidden=prop[i:j];prop=prop[:i]+prop[j:];prop=prop[:-1]+hidden+prop[-1:]
            node=node[:x]+prop+node[y:];text=text[:a]+node+text[z:]
        raw.write_raw(p,text)
    saved=[p.read_bytes() for p in (source,child)]
    proof=ordinary.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],timeout_s=10.)
    assert proof['ok'] and proof['complete'],proof
    assert [p.read_bytes() for p in (source,child)]==saved


@pytest.mark.parametrize('fault',['wrong_native','source_target_alias','grouped_cut'])
def test_literal_projection_requires_independent_native_equality_and_private_target(tmp_path,fault):
    from cec_native_items import discard_items
    source,uid,other=fixture(tmp_path);target=force._copy_family(source,tmp_path/'projection')
    if fault=='grouped_cut':
        b=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_GROUP(b);g.SetName('retained_owner');b.Add(g)
        g.AddItem(next(t for t in b.GetTracks()if force._uid(t)==uid));field._save_field_snapshot(b,source)
    saved=source.read_bytes();expected=pcbnew.LoadBoard(str(source))
    if fault!='wrong_native':
        discard_items(expected,[t for t in expected.GetTracks()if force._uid(t)==uid])
    with pytest.raises(ValueError):op.write_native_projection(source,source if fault=='source_target_alias'else target,[uid],expected)
    assert source.read_bytes()==saved


def test_projection_preserves_opaque_source_and_matches_full_native_subtraction(tmp_path):
    from cec_native_items import discard_items
    source,uid,other=fixture(tmp_path);hidden_field_last(source);before=source.read_bytes()
    target=force._copy_family(source,tmp_path/'projection');basis=pcbnew.LoadBoard(str(source))
    discard_items(basis,[t for t in basis.GetTracks()if force._uid(t)==uid])
    proof=op.write_native_projection(source,target,[uid],basis)
    assert proof['exact_opaque_source_subtraction']and proof['independent_full_native_inventory_equal']
    assert not proof['electrical_retirement_authority']and source.read_bytes()==before
    old=literal._inventory(raw.raw_text(source))[0];new=literal._inventory(raw.raw_text(target))[0]
    assert new.keys()==old.keys()-{uid}and all(new[u][2]==old[u][2]for u in new)


def test_pair_subtraction_producer_keeps_opaque_source_nodes(tmp_path):
    import cec_paired_route_reconstruction as paired
    from cec_native_items import discard_items
    source,uid,_=fixture(tmp_path);hidden_field_last(source);before=source.read_bytes()
    target=force._copy_family(source,tmp_path/'pair-source-projection')
    basis=pcbnew.LoadBoard(str(source))
    discard_items(basis,[t for t in basis.GetTracks()if force._uid(t)==uid])
    result=paired._write_source_projection(source,target,{uid},basis,factory_groups=set())
    assert result['exact_opaque_source_subtraction']
    assert result['independent_full_native_inventory_equal']
    assert not result['electrical_retirement_authority']and source.read_bytes()==before
    old=literal._inventory(raw.raw_text(source))[0];new=literal._inventory(raw.raw_text(target))[0]
    assert new.keys()==old.keys()-{uid}
    assert all(new[u][2]==old[u][2]for u in new)
