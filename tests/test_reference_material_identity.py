from pathlib import Path
import pytest
import pcbnew
import wx
quiet=wx.LogNull()
import cec_swig_guard;cec_swig_guard.pin()
import cec_reference_material_identity as op
import cec_field_coupling as field
import cec_source_retaining_ses_import as raw
from test_lastmile import _board


def fixture(tmp_path,turn=0,back=False):
    board=_board([(10,10,'/RENAMED'),(12,10,'/RENAMED')],edge=(0,0,30,30))
    fp=next(iter(board.GetFootprints()));fp.SetReference('RENAMED_OWNER')
    fp.Reference().SetKeepUpright(False)
    if back:fp.Flip(fp.GetPosition(),False)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    source=tmp_path/'source/board.kicad_pcb';child=tmp_path/'child/board.kicad_pcb'
    source.parent.mkdir();child.parent.mkdir();field._save_field_snapshot(board,source)
    fp.Reference().SetPosition(fp.Reference().GetPosition()+pcbnew.VECTOR2I_MM(1,0))
    field._save_field_snapshot(board,child)
    return source,child


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_reference_relation_only(tmp_path,turn,back):
    source,child=fixture(tmp_path,turn,back);before=[p.read_bytes()for p in(source,child)]
    result=op.receive(source,child)
    assert result['ok']and result['same_material'],result
    assert len(result['changed_owner_uuids'])==1
    assert not result['mutation_authority']and not result['full_kelvin_qualification']
    assert result['inherited_electrical_debt']=='unchanged_not_evaluated'
    assert before==[p.read_bytes()for p in(source,child)]


@pytest.mark.parametrize('fault',['rename','hide','upright','value','pad','model','silk','pro','dru','opaque_root','opaque_ref','duplicate_at','duplicate_ref'])
def test_every_unowned_change_refuses(tmp_path,fault):
    source,child=fixture(tmp_path)
    if fault in('pro','dru'):child.with_suffix('.kicad_'+fault).write_text('changed')
    elif fault in('opaque_root','opaque_ref','duplicate_at','duplicate_ref'):
        text=child.read_text()
        if fault=='opaque_root':text=text[:-2]+'(unknown_material 1)\n)'
        else:
            for a,b in raw.children(text):
                fp=text[a:b]
                if raw.kind(fp)!='footprint':continue
                for x,y in raw.children(fp):
                    node=fp[x:y]
                    if raw.kind(node)=='property'and '"Reference"'in node:
                        if fault=='duplicate_ref':text=text[:a+y]+node+text[a+y:]
                        else:
                            extra='(future_property_attribute 1)'if fault=='opaque_ref'else '(at 1 2)'
                            text=text[:a+y-1]+extra+text[a+y-1:]
                        break
                else:continue
                break
        child.write_text(text)
    else:
        board=pcbnew.LoadBoard(str(child))
        # Native serialization may reorder footprint iteration. Mutate the
        # owner whose upright flag was actually set false in the fixture,
        # rather than accidentally assigning true to an unrelated default.
        fp=next(fp for fp in board.GetFootprints()if fp.GetReference()=='RENAMED_OWNER')
        before=child.read_bytes()
        if fault=='rename':fp.SetReference('FORGED')
        elif fault=='hide':fp.Reference().SetVisible(False)
        elif fault=='upright':fp.Reference().SetKeepUpright(True)
        elif fault=='value':fp.SetValue('FORGED')
        elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(2,2))
        elif fault=='model':m=pcbnew.FP_3DMODEL();m.m_Filename='forged.step';fp.Models().push_back(m)
        elif fault=='silk':
            line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_SilkS)
            line.SetStart(pcbnew.VECTOR2I_MM(1,1));line.SetEnd(pcbnew.VECTOR2I_MM(2,1));fp.Add(line)
        field._save_field_snapshot(board,child)
        assert child.read_bytes()!=before,'negative fixture must change saved material'
    result=op.receive(source,child);assert not result['ok'],result


def test_native_opaque_attack_independent_of_saved_projection(tmp_path,monkeypatch):
    source,child=fixture(tmp_path);original=field._save_field_snapshot;calls=[]
    def corrupt(board,path):
        original(board,path);calls.append(path)
        if len(calls)==2:
            text=Path(path).read_text();Path(path).write_text(text[:-2]+'(native_opaque_attack 1)\n)')
    monkeypatch.setattr(field,'_save_field_snapshot',corrupt)
    result=op.receive(source,child)
    assert not result['ok']and result['error']=='non_reference_material_ast_changed',result


@pytest.mark.parametrize('value',[True,0,-1,11,float('nan')])
def test_bounded_no_external_scope(tmp_path,value):
    source,child=fixture(tmp_path);assert not op.receive(source,child,timeout_s=value)['ok']
    with pytest.raises(TypeError):op.receive(source,child,owner_uuids=['forged'])


def test_source_mutation_refuses(tmp_path,monkeypatch):
    source,child=fixture(tmp_path);original=field._save_field_snapshot
    def corrupt(board,path):
        original(board,path);source.write_text(source.read_text()+'\n')
    monkeypatch.setattr(field,'_save_field_snapshot',corrupt)
    result=op.receive(source,child);assert not result['ok']and result['error']=='source_code_family_or_native_changed'
