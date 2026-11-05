import copy
from pathlib import Path
import wx
quiet=wx.LogNull()
import pcbnew
import cec_swig_guard;cec_swig_guard.pin()
import pytest
import cec_ink_material_identity as op
import cec_field_coupling as field
import cec_force_current as force
import cec_source_retaining_ses_import as raw
from test_lastmile import _board


def remove_ink(text):
    cuts=[]
    for a,z in raw.children(text):
        if raw.kind(text[a:z])!='footprint':continue
        for x,y in raw.children(text[a:z]):
            node=text[a+x:a+y]
            if raw.kind(node)=='fp_line'and ('"F.SilkS"'in node or '"B.SilkS"'in node):cuts.append((a+x,a+y))
    for a,z in reversed(cuts):text=text[:a]+text[z:]
    return text


def fixture(tmp_path,turn=0,back=False):
    b=_board([(10,10,'/RENAMED'),(12,10,'/RENAMED')],edge=(0,0,30,30));fps=list(b.GetFootprints());fp=fps[0]
    fp.SetReference('RENAMED_OWNER');fp.SetFPID(pcbnew.LIB_ID('source','actual-package'))
    for layer in(pcbnew.F_SilkS,pcbnew.B_SilkS,pcbnew.F_Fab):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(layer);line.SetWidth(150000)
        line.SetStart(pcbnew.VECTOR2I_MM(9,9));line.SetEnd(pcbnew.VECTOR2I_MM(11,9));fp.Add(line)
    if back:fp.Flip(fp.GetPosition(),False)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(10,10));t.SetEnd(pcbnew.VECTOR2I_MM(12,10));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(next(iter(fp.Pads())).GetNetCode());b.Add(t)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(12,10));v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(t.GetNetCode());b.Add(v)
    source=tmp_path/'source/board.kicad_pcb';child=tmp_path/'child/board.kicad_pcb'
    source.parent.mkdir();child.parent.mkdir();field._save_field_snapshot(b,source)
    for suffix,text in(('.kicad_pro','{}'),('.kicad_dru','(version 1)')):
        source.with_suffix(suffix).write_text(text);child.with_suffix(suffix).write_text(text)
    child.write_text(remove_ink(source.read_text()))
    return source,child


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_whole_raw_and_native_identity_preserves_unknown_debt(tmp_path,turn,back):
    source,child=fixture(tmp_path,turn,back);before=[p.read_bytes()for p in(source,child)]
    result=op.receive(source,child)
    assert result['ok']and result['comparison_complete']and result['same_material'],result
    assert result['omitted_silk_line_counts']['saved']==[2,0]
    assert result['full_kelvin_qualification']is False and result['kelvin_isolation_qualified']is None
    assert not result['ink_authority']and not result['admitted']and result['independent_print_scope_receiving_required']
    assert before==[p.read_bytes()for p in(source,child)]


@pytest.mark.parametrize('fault',['track','via_drill','padshape','custompoly','padangle','pin','net','model','property','group','stack','fill','root_unknown','non_silk_line','fab_line','pro','dru'])
def test_no_other_saved_ast_or_sidecar_attributes_are_ignored(tmp_path,fault):
    source,child=fixture(tmp_path);text=child.read_text()
    if fault in('pro','dru'):child.with_suffix('.kicad_'+fault).write_text('changed')
    elif fault in('custompoly','fill','root_unknown','stack','group'):
        # These full native AST payloads remain significant even when the
        # source loader would ignore unknown fields. No weak native inventory.
        extra={'custompoly':'(footprint "custom" (pad "1" smd custom (at 1 1) (size 1 1) (layers "F.Cu") (primitives (gr_poly (pts (xy 0 0)(xy 1 0)(xy 0 1)) (width 0)(fill yes)))))',
          'fill':'(zone (filled_polygon (layer "F.Cu") (pts (xy 0 0)(xy 1 0)(xy 0 1))))',
          'root_unknown':'(future_physical "changed")','stack':'(setup (stackup (copper_finish "changed")))',
          'group':'(group "changed" (uuid "01010101-0101-0101-0101-010101010101") (members))'}[fault]
        at=text.rfind(')');child.write_text(text[:at]+extra+text[at:])
    else:
        b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()));pad=next(iter(fp.Pads()))
        if fault=='track':next(t for t in b.GetTracks()if t.GetClass()=='PCB_TRACK').SetWidth(300000)
        elif fault=='via_drill':next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA').SetDrill(310000)
        elif fault=='padshape':pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
        elif fault=='padangle':pad.SetOrientation(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
        elif fault=='pin':pad.SetNumber('99')
        elif fault=='net':pad.SetNetCode(0)
        elif fault=='property':fp.SetValue('changed-value')
        elif fault=='model':m=pcbnew.FP_3DMODEL();m.m_Filename='changed.step';fp.Models().push_back(m)
        elif fault in('non_silk_line','fab_line'):
            g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_Cu if fault=='non_silk_line'else pcbnew.F_Fab);g.SetStart(pcbnew.VECTOR2I_MM(1,1));g.SetEnd(pcbnew.VECTOR2I_MM(2,1));fp.Add(g)
        field._save_field_snapshot(b,child)
    result=op.receive(source,child);assert not result['ok'],result


def test_opaque_identical_source_metadata_is_bound_not_discarded(tmp_path):
    source,child=fixture(tmp_path)
    for path in(source,child):
        text=path.read_text();at=text.rfind(')');path.write_text(text[:at]+'(title_block (comment 1 "Opaque exact"))'+text[at:])
    result=op.receive(source,child);assert result['ok'],result.get('error')


def test_even_identical_unsupported_native_source_refuses(tmp_path):
    source,child=fixture(tmp_path)
    for path in(source,child):
        text=path.read_text();at=text.rfind(')');path.write_text(text[:at]+'(future_setting "unknown")'+text[at:])
    result=op.receive(source,child);assert not result['ok']and result['error']=='complete_native_board_required'


@pytest.mark.parametrize('timeout',[True,0,-1,11,float('nan')])
def test_timeout_and_no_external_proof_interface(tmp_path,timeout):
    source,child=fixture(tmp_path);assert not op.receive(source,child,timeout_s=timeout)['ok']
    with pytest.raises(TypeError):op.receive(source,child,proof={'same_material':True})


def test_source_drift_during_native_proof_refuses(tmp_path,monkeypatch):
    source,child=fixture(tmp_path);save=field._save_field_snapshot;changed=False
    def mutate(*a,**kw):
        nonlocal changed
        value=save(*a,**kw)
        if not changed:changed=True;source.write_text(source.read_text()+'\n')
        return value
    monkeypatch.setattr(field,'_save_field_snapshot',mutate)
    assert 'source_code_family_or_native_changed'in op.receive(source,child)['error']


def polygon(delta=0):
    p=pcbnew.SHAPE_POLY_SET();p.NewOutline()
    for x,y in((0,0),(100000+delta,0),(100000,100000),(0,100000)):p.Append(x,y)
    return p


def test_real_custom_pad_full_primitives_are_identity_not_size_only(tmp_path):
    source,child=fixture(tmp_path)
    for path in(source,child):
        b=pcbnew.LoadBoard(str(path));p=next(iter(next(iter(b.GetFootprints())).Pads()))
        p.SetShape(pcbnew.PAD_SHAPE_CUSTOM);p.AddPrimitivePoly(pcbnew.F_Cu,polygon(),0,True)
        field._save_field_snapshot(b,path)
    assert op.receive(source,child)['ok']
    b=pcbnew.LoadBoard(str(child));p=next(iter(next(iter(b.GetFootprints())).Pads()))
    p.DeletePrimitivesList(pcbnew.F_Cu);p.AddPrimitivePoly(pcbnew.F_Cu,polygon(1),0,True)
    field._save_field_snapshot(b,child)
    assert op.receive(source,child)['error']=='non_ink_saved_ast_changed'


def test_actual_native_zone_saved_fill_is_compared_without_refill(tmp_path):
    source,child=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));z=pcbnew.ZONE(b)
    z.SetLayer(pcbnew.F_Cu);z.SetNetCode(1);z.Outline().NewOutline()
    for x,y in((5,5),(15,5),(15,15),(5,15)):z.Outline().Append(int(x*1e6),int(y*1e6))
    z.SetFilledPolysList(pcbnew.F_Cu,polygon());z.SetIsFilled(True);b.Add(z);field._save_field_snapshot(b,source)
    child.write_text(remove_ink(source.read_text()))
    assert op.receive(source,child)['ok']
    b=pcbnew.LoadBoard(str(child));z=next(iter(b.Zones()));z.SetFilledPolysList(pcbnew.F_Cu,polygon(1));field._save_field_snapshot(b,child)
    assert op.receive(source,child)['error']=='non_ink_saved_ast_changed'


@pytest.mark.parametrize('fault',['code','native','deadline'])
def test_fresh_complete_proof_rechecks_code_native_and_lease(tmp_path,monkeypatch,fault):
    source,child=fixture(tmp_path);save=field._save_field_snapshot;state={'changed':False}
    def observed(*a,**kw):value=save(*a,**kw);state['changed']=True;return value
    monkeypatch.setattr(field,'_save_field_snapshot',observed)
    if fault=='code':
        original=force._code_identity;monkeypatch.setattr(force,'_code_identity',lambda:'changed'if state['changed']else original())
    elif fault=='native':
        original=force._hash
        monkeypatch.setattr(force,'_hash',lambda p:'changed'if state['changed']and Path(p).name=='pcbnew.py'else original(p))
    else:monkeypatch.setattr(op.time,'monotonic',lambda:20. if state['changed']else 0.)
    assert not op.receive(source,child)['ok']


def test_full_native_comparison_is_required_even_after_raw_relation(tmp_path,monkeypatch):
    source,child=fixture(tmp_path);save=field._save_field_snapshot
    def changed_native(board,path):
        value=save(board,path)
        if Path(path).name=='1.kicad_pcb':
            text=Path(path).read_text();at=text.rfind(')');Path(path).write_text(text[:at]+'(changed_native_material yes)'+text[at:])
        return value
    monkeypatch.setattr(field,'_save_field_snapshot',changed_native)
    assert op.receive(source,child)['error']=='non_ink_complete_native_ast_changed'


def test_groups_are_preserved_without_granting_ink_ownership(tmp_path):
    source,child=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(f for f in b.GetFootprints()if list(f.GraphicalItems()))
    line=next(g for g in fp.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS))
    group=pcbnew.PCB_GROUP(b);group.SetName('retain-exact-members');b.Add(group);group.AddItem(fp);group.AddItem(line)
    field._save_field_snapshot(b,source);child.write_text(remove_ink(source.read_text()))
    # Even identical geometry is NOT print ownership. The print receiver must
    # independently refuse an unrecognized group-owned owner. This relation
    # proves only that all actually serialized group nodes stayed identical.
    result=op.receive(source,child);assert result['ok']and not result['ink_authority']
    child.write_text(child.read_text().replace('retain-exact-members','changed-owner'))
    assert op.receive(source,child)['error']=='non_ink_saved_ast_changed'
