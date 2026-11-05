"""Ground-only saving cannot normalize retained reference/footprint records."""
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as ground
import cec_source_literal_additions as literal
from cec_source_retaining_ses_import import children,kind,raw_text,write_raw
from test_ground_access_completion import fixture
from test_ground_access_existing_pad_rule import fixture as local_fixture


def opaque_reference(source,owner_uuid):
    """Legal native Source ordering that the writer otherwise normalizes."""
    text=raw_text(source);nodes,*_=literal._inventory(text)
    a,b,fp=nodes[owner_uuid]
    matches=[]
    for start,end in children(fp):
        node=fp[start:end]
        if kind(node)=='property' and literal._atoms(node[1:next(x for x,y in children(node))])[1][0]=='Reference':
            matches.append((start,end,node))
    assert len(matches)==1
    start,end,ref=matches[0]
    hidden=[(x,y)for x,y in children(ref)if kind(ref[x:y])=='hide']
    assert len(hidden)==1
    x,y=hidden[0];flag=ref[x:y];ref=ref[:x]+ref[y:]
    # KiCad accepts this property-child order, but not semicolon comments.
    # Only legal whitespace/order differs from the native writer's choice.
    ref=ref[:-1]+'\n\n'+flag+'\n)'
    fp=fp[:start]+ref+fp[end:];write_raw(source,text[:a]+fp+text[b:])
    return raw_text(source)


def source(tmp_path,**options):
    b,path,pad,_=fixture(tmp_path,observed=True,**options)
    owner=pad.GetParentFootprint();owner.Reference().SetVisible(False)
    field._save_field_snapshot(b,path)
    original=opaque_reference(path,force._uid(owner))
    return path,force._uid(pad),force._uid(owner),original


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('mode',['reuse','vip','dogbone'])
def test_actual_saved_replay_preserves_literal_source_in_all_native_frames(tmp_path,quarter,layer,mode):
    parent,pad,owner,original=source(tmp_path,quarter=quarter,layer=layer,mode=mode)
    args=dict(board_hint='synthetic',pad_uuid=pad)
    q=ground.plan(parent,**args)
    saved=ground.write_private(q,tmp_path/'literal-child');child=Path(saved['candidate'])
    before,*_=literal._inventory(original);after,*_=literal._inventory(raw_text(child))
    for uid,(_,_,node) in before.items():
        if kind(node)=='footprint':assert after[uid][2]==node
    assert after[owner][2]==before[owner][2] and raw_text(parent)==original
    assert force._sidecars(parent)==force._sidecars(child)
    strict=additive.receive(parent,child,board_hint='synthetic')
    assert strict['ok']and strict['complete'],strict
    proof=ground.receive(parent,child,**args)
    assert proof['ok']and proof['complete'],proof
    assert proof['saved_return_witness_mm']<=1.5 and proof['all_source_known_returns']['ok']
    assert not proof['current_qualified']and not proof['fab_ready']and not proof['release_authority']


def test_serializer_normalization_is_still_rejected_instead_of_waived(tmp_path):
    parent,pad,_,_=source(tmp_path,mode='vip');args=dict(board_hint='synthetic',pad_uuid=pad)
    q=ground.plan(parent,**args);b=ground.construct(q);additive._ground_refill(b)
    child=force._copy_family(parent,tmp_path/'normalized-child');field._save_field_snapshot(b,child)
    strict=additive.receive(parent,child,board_hint='synthetic')
    assert not strict['ok']and not strict['complete']
    proof=ground.receive(parent,child,**args)
    assert not proof['ok']and not proof['complete']and proof['errors']


def test_literal_saving_extends_only_the_existing_rule_group(tmp_path):
    parent,pad=local_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(parent));owner=next(p.GetParentFootprint()for f in b.GetFootprints()
        for p in f.Pads()if force._uid(p)==pad)
    owner.Reference().SetVisible(False);field._save_field_snapshot(b,parent)
    original=opaque_reference(parent,force._uid(owner));sidecars=force._sidecars(parent)
    args=dict(board_hint='synthetic',pad_uuid=pad,use_existing_local_pad_rule=True)
    q=ground.plan(parent,**args);saved=ground.write_private(q,tmp_path/'existing-rule-child')
    child=Path(saved['candidate']);r=ground.receive(parent,child,**args)
    assert r['ok']and r['complete'],r
    assert force._sidecars(parent)==force._sidecars(child)==sidecars and raw_text(parent)==original
    assert r['saved_return_witness_mm']==0 and r['new_holes']==1


@pytest.mark.parametrize('fault',['width','hole','position','unlocked','source_value','sidecar'])
def test_new_writer_does_not_hide_any_real_saved_delta(tmp_path,fault):
    parent,pad,_,_=source(tmp_path,mode='vip');args=dict(board_hint='synthetic',pad_uuid=pad)
    q=ground.plan(parent,**args);saved=ground.write_private(q,tmp_path/'literal-child')
    child=Path(saved['candidate']);b=pcbnew.LoadBoard(str(child))
    old={force._uid(t)for t in pcbnew.LoadBoard(str(parent)).GetTracks()}
    via=next(t for t in b.GetTracks()if force._uid(t)not in old)
    if fault=='width':via.SetWidth(via.GetWidth()+1)
    elif fault=='hole':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='position':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unlocked':via.SetLocked(False)
    elif fault=='source_value':next(iter(b.GetFootprints())).SetValue('unowned real change')
    else:child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    # Native saving is intentionally NOT passed through the opaque producer:
    # a receiver must see and refuse every actually changed saved child.
    field._save_field_snapshot(b,child)
    r=ground.receive(parent,child,**args)
    assert not r['ok']and not r['complete']and r['errors']


def test_snapshot_cannot_publish_into_source_or_a_non_source_copy(tmp_path):
    parent,pad,_,original=source(tmp_path,mode='vip')
    q=ground.plan(parent,board_hint='synthetic',pad_uuid=pad);b=ground.construct(q)
    with pytest.raises(ValueError,match='distinct_private'):
        ground._save_additive_snapshot(b,parent,parent)
    child=force._copy_family(parent,tmp_path/'not-a-source-copy');child.write_text('(kicad_pcb)')
    with pytest.raises(ValueError,match='exact_private_source_copy'):
        ground._save_additive_snapshot(b,parent,child)
    assert raw_text(parent)==original
