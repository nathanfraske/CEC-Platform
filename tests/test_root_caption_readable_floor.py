"""Explicit reviewed caption floor enlargement, never arbitrary styling."""
import copy

import pcbnew
import pytest
import cec_root_caption_seating as op
from test_root_caption_seating import fixture,refresh


def small(tmp_path,back=False,angle=0,size=(.9,.9),stroke=130000):
    source,grade,args=fixture(tmp_path,back,angle)
    b=pcbnew.LoadBoard(str(source));t=next(i for i in b.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
    t.SetTextSize(pcbnew.VECTOR2I_MM(*size));t.SetTextThickness(stroke)
    op.seats.field._save_field_snapshot(b,source);refresh(source,grade,args['caption_uuid'])
    return source,grade,args


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,37,90,180])
def test_exact_native_readable_floor_enlargement_and_full_query_proof(tmp_path,back,angle):
    source,_,args=small(tmp_path,back,angle)
    with pytest.raises(ValueError,match='below_readable'):op.plan(source,**args)
    p=op.plan(source,**args,raise_to_readable_floor=True)
    assert p['readable_floor']==dict(size_nm=[1000000,1000000],stroke_nm=150000)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,p)
    proof=op.receive(source,child,p);assert proof['ok'],proof
    identity=op.query_input_identity(source,child,p);assert identity['ok'],identity
    assert not proof['translation_only']and not identity['release_authority']
    b=pcbnew.LoadBoard(str(child));t=next(i for i in b.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
    assert tuple(t.GetTextSize())==(1000000,1000000)and t.GetTextThickness()==150000
    assert t.GetTextAngle().AsDegrees()==angle and t.IsMirrored()is back


@pytest.mark.parametrize('size,stroke,expected',[
    ((1.2,.9),130000,([1200000,1000000],150000)),
    ((1.2,1.4),180000,([1200000,1400000],180000))])
def test_dimensions_and_stroke_never_shrink(tmp_path,size,stroke,expected):
    source,_,args=small(tmp_path,size=size,stroke=stroke)
    p=op.plan(source,**args,raise_to_readable_floor=True)
    assert p['readable_floor']==dict(size_nm=expected[0],stroke_nm=expected[1])
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,p)
    proof=op.query_input_identity(source,child,p);assert proof['ok'],proof


@pytest.mark.parametrize('flag',[1,0,None,'true',[],{}])
def test_opt_in_is_strict_boolean(tmp_path,flag):
    source,_,args=small(tmp_path)
    with pytest.raises(ValueError,match='strict_boolean'):op.plan(source,**args,raise_to_readable_floor=flag)


@pytest.mark.parametrize('fault',['size','stroke','angle','mirror','layer','text','opaque','other_field'])
def test_enlargement_cannot_normalize_arbitrary_candidate_mutations(tmp_path,fault):
    source,_,args=small(tmp_path);p=op.plan(source,**args,raise_to_readable_floor=True)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,p)
    if fault=='opaque':
        text=child.read_text();a,z=op._root_text(text,args['caption_uuid'])
        op.raw.write_raw(child,text[:z-1]+' (future_caption_metadata "FORGED")'+text[z-1:])
    else:
        b=pcbnew.LoadBoard(str(child));t=next(i for i in b.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
        if fault=='size':t.SetTextSize(pcbnew.VECTOR2I_MM(1.1,1.1))
        elif fault=='stroke':t.SetTextThickness(160000)
        elif fault=='angle':t.SetTextAngle(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
        elif fault=='mirror':t.SetMirrored(True)
        elif fault=='layer':t.SetLayer(pcbnew.B_SilkS)
        elif fault=='text':t.SetText('changed')
        else:next(iter(b.GetFootprints())).Reference().SetTextThickness(200000)
        op.seats.field._save_field_snapshot(b,child)
    assert not op.receive(source,child,p)['ok']
    assert not op.query_input_identity(source,child,p)['ok']


def test_scope_and_forged_floor_cannot_authorize_functional_roles_or_arbitrary_resize(tmp_path):
    source,_,args=small(tmp_path)
    with pytest.raises(ValueError):op.plan(source,**(args|dict(caption_scope='pin_label')),raise_to_readable_floor=True)
    p=op.plan(source,**args,raise_to_readable_floor=True);q=copy.deepcopy(p)
    q['readable_floor']['size_nm']=[1100000,1100000]
    with pytest.raises(ValueError):op.construct(source,q)


def test_raw_floor_edit_preserves_unknown_source_metadata_but_does_not_own_it(tmp_path):
    source,_,args=small(tmp_path);text=source.read_text();a,z=op._root_text(text,args['caption_uuid'])
    opaque=text[:z-1]+' (future_caption_metadata "KEEP")'+text[z-1:]
    changed=op._edited(opaque,args['caption_uuid'],[39000000,40000000],
        dict(size_nm=[1000000,1000000],stroke_nm=150000))
    assert '(future_caption_metadata "KEEP")'in changed
    assert changed==opaque.replace('(at 40 40','(at 39 40').replace('(size 0.9 0.9)','(size 1 1)').replace('(thickness 0.13)','(thickness 0.15)')


def test_search_uses_final_enlarged_native_glyph(tmp_path,monkeypatch):
    source,_,args=small(tmp_path);seen=[];original=op.seats.dense.polygon
    def observe(item,layer):
        if op.force._uid(item)==args['caption_uuid']:
            seen.append((tuple(item.GetTextSize()),item.GetTextThickness()))
        return original(item,layer)
    monkeypatch.setattr(op.seats.dense,'polygon',observe)
    op.plan(source,**args,raise_to_readable_floor=True)
    assert seen==[((1000000,1000000),150000)]
