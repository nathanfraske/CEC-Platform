"""A one-part pose cannot normalize untouched opaque Source footprint text."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_retained_passive_pose_stage as stage
import cec_source_literal_additions as syntax
import cec_source_literal_footprint_retention as retention
import cec_source_retaining_ses_import as raw
from test_retained_passive_pose_stage import fixture


def tree(value,uid,hidden):
    return '(footprint "opaque:'+value+'" (uuid "'+uid+'") '+hidden+')'


@pytest.mark.parametrize('name', ['arbitrary','renamed/with-space','escaped \\" label'])
def test_only_selected_native_subtree_is_replaced(name):
    a,b='00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002'
    olda=tree(name,a,'(property "Reference" "A" (hide yes) (effects (font (size 1 1))))')
    oldb=tree('static',b,'\n\t(property "Reference" "B" (hide yes) (effects (font (size 1 1))))\n')
    newa=tree('moved',a,'(at 12 13)');newb=tree('static',b,'(property "Reference" "B" (effects (font (size 1 1))) (hide yes))')
    source='(kicad_pcb '+olda+' '+oldb+')';native='(kicad_pcb '+newa+' '+newb+')'
    result=retention.retain(source,native,[a]);inventory=syntax._inventory(result)[0]
    assert inventory[a][2]==newa and inventory[b][2]==oldb
    assert source=='(kicad_pcb '+olda+' '+oldb+')'


@pytest.mark.parametrize('scope', [[],['missing'],[True],['a','a'],'a',None,list(map(str,range(9)))])
def test_projection_scope_is_bounded_and_explicit(scope):
    a='00000000-0000-4000-8000-000000000001';source='(kicad_pcb '+tree('x',a,'')+')'
    with pytest.raises(ValueError):retention.retain(source,source,scope)


def test_added_or_missing_footprint_population_is_not_hidden():
    a,b='00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002'
    source='(kicad_pcb '+tree('x',a,'')+')'
    native='(kicad_pcb '+tree('x',a,'')+' '+tree('y',b,'')+')'
    with pytest.raises(ValueError):retention.retain(source,native,[a])
    with pytest.raises(ValueError):retention.retain(native,source,[a])


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_real_saved_pose_and_independent_receiver_keep_unselected_literals(tmp_path,back,quarter):
    source,owner,group,ref,pose=fixture(tmp_path,back=back,quarter=quarter)
    board=pcbnew.LoadBoard(str(source));extra=pcbnew.FOOTPRINT(board)
    extra.SetReference('UNTOUCHED_ARBITRARY');extra.Reference().SetVisible(False)
    extra.SetPosition(pcbnew.VECTOR2I_MM(27,26));board.Add(extra)
    field._save_field_snapshot(board,source);uid=force._uid(extra)
    text=raw.raw_text(source);start,end,node=syntax._inventory(text)[0][uid]
    opaque=node.replace('(footprint ', '(footprint  ',1).replace('\n','\n\t',1)
    raw.write_raw(source,text[:start]+opaque+text[end:])
    before=source.read_bytes();q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group])
    result=stage.construct(source,tmp_path/'literal-received',q,timeout_s=10.)
    assert result['ok'] and result['complete'],result
    target=Path(result['candidate']);final=syntax._inventory(raw.raw_text(target))[0]
    assert final[uid][2]==opaque
    assert stage.receive(source,target,q,timeout_s=10.)['ok']
    assert source.read_bytes()==before
