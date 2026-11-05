"""Stationary leaf receiving must not normalize unrelated opaque Source records."""
import cec_swig_guard
cec_swig_guard.pin()
import wx
QUIET = wx.LogNull()
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_local_branch_access as access
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
from test_measurement_leaf_reflow import reflow_fixture
from test_source_literal_retirement import hidden_field_last


def opaque_fixture(tmp_path,quarter=0,count=3):
    source,child,pad=reflow_fixture(tmp_path,quarter,name='UNRELATED_STAGE_29')
    parent,after=[pcbnew.LoadBoard(str(path)) for path in (source,child)]
    group=pcbnew.PCB_GROUP(parent);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);parent.Add(group)
    clone=pcbnew.PCB_GROUP(after);clone.SetName(group.GetName());clone.m_Uuid.Clone(group.m_Uuid);after.Add(clone)
    for index in range(count):
        via=pcbnew.PCB_VIA(parent);via.SetPosition(pcbnew.VECTOR2I_MM(2+index%11,21+index//11))
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(parent.GetNetcodeFromNetname('GND'))
        parent.Add(via);group.AddItem(via)
        other=via.Duplicate();other.m_Uuid.Clone(via.m_Uuid)
        other.SetNetCode(after.GetNetcodeFromNetname('GND'));after.Add(other);clone.AddItem(other)
    # A real two-land, same-net native jumper record on an unrelated part.
    fp=parent.FindFootprintByReference('OTHER');native=next(iter(fp.Pads()))
    extra=native.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetNumber('2');fp.Add(extra)
    target=after.FindFootprintByReference('OTHER');copy=extra.Duplicate();copy.m_Uuid.Clone(extra.m_Uuid)
    copy.SetNetCode(after.GetNetcodeFromNetname('MEASURE_PLUS'));target.Add(copy)
    for board,path in ((parent,source),(after,child)):
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
        field._save_field_snapshot(board,path)
        hidden_field_last(path)
        text=raw.raw_text(path);nodes=literal._inventory(text)[0]
        edits=[]
        for uid,(start,end,node)in nodes.items():
            if uid==force._uid(group):
                span=literal._child(node,'members');assert span
                a,z=span;members=sorted(literal._members(node)[1],reverse=True)
                node=node[:a]+'(members '+' '.join('"'+m+'"'for m in members)+')'+node[z:]
                edits.append((start,end,node))
            elif uid==force._uid(fp):
                at=literal._child(node,'uuid')[1]
                node=node[:at]+'\n(duplicate_pad_numbers_are_jumpers no)\n(jumper_pad_groups ("1" "2"))'+node[at:]
                edits.append((start,end,node))
        for start,end,node in sorted(edits,reverse=True):text=text[:start]+node+text[end:]
        raw.write_raw(path,text)
        additive.bind_local_via_rule(pcbnew.LoadBoard(str(path)),path)
    return source,child,pad,force._uid(group),force._uid(fp)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('count',[3,85])
def test_opaque_unowned_group_fields_and_jumpers_survive_typed_leaf_replay(tmp_path,quarter,count):
    source,child,pad,group,jumper=opaque_fixture(tmp_path,quarter,count)
    before=[p.read_bytes()for p in(source,child)]
    _,old=additive._nodes(source);_,new=additive._nodes(child)
    assert syntax._freeze(old[group])==syntax._freeze(new[group])
    assert syntax._freeze(old[jumper])==syntax._freeze(new[jumper])
    proof=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert proof['ok'] is True and proof['complete'] is True,dict(errors=proof['errors'],
        additive_errors=proof.get('independent_exact_retirement_additive_replay',{}).get('errors'))
    projection=proof['independent_source_minus_leaf_projection']
    assert projection['exact_opaque_source_subtraction'] is True
    assert projection['independent_full_native_inventory_equal'] is True
    assert projection['electrical_retirement_authority'] is False
    assert proof['independent_exact_retirement_additive_replay']['ok'] is True
    assert proof['source_opens']==proof['opens']
    assert proof['exact_force_copper_barrels_and_component_poses_preserved'] is True
    assert proof['kelvin_qualified'] is False and proof['release_authority'] is False
    assert before==[p.read_bytes()for p in(source,child)]


@pytest.mark.parametrize('fault',['missing_member','duplicate_member','forged_member',
    'hidden_field','jumper_metadata','unowned_cut','new_foreign'])
def test_literal_projection_cannot_waive_membership_metadata_or_cut_forgery(tmp_path,fault):
    source,child,pad,group,jumper=opaque_fixture(tmp_path)
    before=source.read_bytes();text=raw.raw_text(child);nodes=literal._inventory(text)[0]
    uid=group if fault in('missing_member','duplicate_member','forged_member') else jumper
    start,end,node=nodes[uid]
    if fault in('missing_member','duplicate_member','forged_member'):
        span=literal._child(node,'members');a,z=span;members=list(literal._members(node)[1])
        if fault=='missing_member':members.pop()
        elif fault=='duplicate_member':members.append(members[0])
        else:members.append(next(u for u,(_,_,n)in nodes.items()if literal.kind(n)=='segment'))
        node=node[:a]+'(members '+' '.join('"'+m+'"'for m in members)+')'+node[z:]
        text=text[:start]+node+text[end:]
    elif fault=='hidden_field':
        assert '(hide yes)'in node
        node=node.replace('(hide yes)','(hide no)',1);text=text[:start]+node+text[end:]
    elif fault=='jumper_metadata':
        assert '(duplicate_pad_numbers_are_jumpers no)'in node
        node=node.replace('(duplicate_pad_numbers_are_jumpers no)','(duplicate_pad_numbers_are_jumpers yes)',1)
        text=text[:start]+node+text[end:]
    elif fault=='unowned_cut':
        b=pcbnew.LoadBoard(str(child))
        uid=next(force._uid(t)for t in b.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND')
        a,z,_=nodes[uid];text=text[:a]+text[z:]
    else:
        b=pcbnew.LoadBoard(str(child));track=pcbnew.PCB_TRACK(b);track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(200000);track.SetNetCode(b.GetNetcodeFromNetname('GND'))
        track.SetStart(pcbnew.VECTOR2I_MM(2,2));track.SetEnd(pcbnew.VECTOR2I_MM(3,2));b.Add(track)
        field._save_field_snapshot(b,child);text=raw.raw_text(child)
    raw.write_raw(child,text)
    proof=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert proof['ok'] is False and proof['errors'],proof
    assert proof['release_authority'] is False and proof['kelvin_qualified'] is False
    assert source.read_bytes()==before
