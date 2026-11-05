"""Deleting owned members must preserve all other opaque Source bytes."""
import copy
import pcbnew
import pytest
import cec_source_literal_group_retirement as grouped
import cec_source_literal_retirement as legacy
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path):
    b=_board([],edge=(0,0,25,25));b.Add(pcbnew.NETINFO_ITEM(b,'/SUPPLY'))
    vias=[]
    for x in (5,10,15):
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(x,10))
        via.SetNet(b.FindNet('/SUPPLY'));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLocked(True);b.Add(via);vias.append(via)
    group=pcbnew.PCB_GROUP(b);group.SetName('EXACT_SOURCE_PROCESS_METADATA');b.Add(group)
    for via in vias:group.AddItem(via)
    edge=track(b,'/SUPPLY',(5,10),(10,10))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,{force._uid(vias[0]),force._uid(vias[1]),force._uid(edge)},\
        {force._uid(group):[force._uid(vias[0]),force._uid(vias[1])]}


@pytest.mark.parametrize('formatting',['canonical','comments_crlf'])
def test_only_requested_nodes_and_exact_member_tokens_removed(tmp_path,formatting):
    source,ids,members=fixture(tmp_path);text=raw.raw_text(source)
    if formatting=='comments_crlf':
        gid=next(iter(members));nodes=literal._inventory(text)[0];a,b,node=nodes[gid]
        # A member-like token in a comment must stay untouched.
        span=literal._child(node,'members');i,j=span
        node=node[:i+8]+'\n; keep "'+members[gid][0]+'" comment\n'+node[i+8:]
        text=text[:a]+node+text[b:];text='; retain leading comment\n'+text
        text=text.replace('\n','\r\n')
    old=literal._inventory(text)[0]
    with pytest.raises(ValueError):legacy.subtract(text,ids)
    result=grouped.subtract(text,ids,members);new=literal._inventory(result)[0]
    assert new.keys()==old.keys()-ids
    gid=next(iter(members));assert literal._members(new[gid][2])[1]==[v for v in literal._members(old[gid][2])[1]if v not in ids]
    for uid in new:
        if uid!=gid:assert new[uid][2]==old[uid][2]
    if formatting=='comments_crlf':assert '; keep "'+members[gid][0]+'" comment\r\n'in result


@pytest.mark.parametrize('fault',['omit','unknown_group','extra_member','duplicate','empty','unbounded','unknown_cut','group_cut','bool'])
def test_no_implicit_ownership_or_incomplete_membership_scope(tmp_path,fault):
    source,ids,members=fixture(tmp_path);text=raw.raw_text(source);gid=next(iter(members))
    if fault=='omit':members={}
    elif fault=='unknown_group':members={'invented':members[gid]}
    elif fault=='extra_member':members[gid].append('invented')
    elif fault=='duplicate':members[gid].append(members[gid][0])
    elif fault=='empty':members[gid]=[]
    elif fault=='unbounded':members[gid]=list(map(str,range(9)))
    elif fault=='unknown_cut':ids.add('invented')
    elif fault=='group_cut':ids.add(gid)
    else:members[gid]=True
    with pytest.raises(ValueError):grouped.subtract(text,ids,members)


@pytest.mark.parametrize('fault',[None,'unrelated_native_move','missing_native_member_drop','source_alias'])
def test_projection_requires_exact_independent_native_memberships_and_geometry(tmp_path,fault):
    source,ids,members=fixture(tmp_path);before=source.read_bytes()
    target=force._copy_family(source,tmp_path/'projection');expected=pcbnew.LoadBoard(str(source))
    if fault!='missing_native_member_drop':discard_items(expected,[t for t in expected.GetTracks()if force._uid(t)in ids])
    if fault=='unrelated_native_move':next(iter(expected.GetTracks())).Move(pcbnew.VECTOR2I_MM(.1,0))
    if fault is None:
        proof=grouped.write_native_projection(source,target,ids,members,expected)
        assert proof['only_exact_derived_memberships_removed']and proof['independent_full_native_inventory_and_membership_equal']
        assert not proof['electrical_retirement_authority']and not proof['release_authority']
    else:
        with pytest.raises(ValueError):grouped.write_native_projection(source,source if fault=='source_alias'else target,ids,members,expected)
    assert source.read_bytes()==before
