import copy
from pathlib import Path
import pcbnew,pytest
import cec_reference_map_material_identity as op
import cec_force_current as force
import cec_field_coupling as field
import cec_mask_search_reference_mapping as maps
from test_root_reference_mapping import saved


def fixture(tmp_path,**kwargs):
    source,child,q,uid,manifest=saved(tmp_path,**kwargs)
    path=tmp_path/'proposal.json';force._write(path,q)
    return source,child,path,q,uid,manifest


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_owned_reverse_map_relation(tmp_path,quarter,back):
    source,child,path,q,uid,m=fixture(tmp_path,quarter=quarter,back=back)
    r=op.receive(source,child,path);assert r['ok']and r['same_material'],r
    assert set(r['owned_root_annotation_uuids'])==set(m['added_root_annotation_uuids'])|set(m['added_reverse_group_uuids'])
    assert not r['mutation_authority']and not r['full_kelvin_qualification']and not r['admitted']


@pytest.mark.parametrize('fault',['scope','font','hide_unrelated','extra_fp','pad','copper','group','member','property','pro','dru'])
def test_unowned_changes_never_masked(tmp_path,fault):
    source,child,path,q,uid,m=fixture(tmp_path)
    if fault=='scope':
        q['records'][0]['footprint_uuid']='forged';force._write(path,q)
    elif fault in('pro','dru'):child.with_suffix('.kicad_'+fault).write_text('forged')
    else:
        b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
        if fault=='font':next(d for d in b.GetDrawings()if d.GetClass()=='PCB_TEXT').SetTextSize(pcbnew.VECTOR2I_MM(.1,.1))
        elif fault=='hide_unrelated':fp.Value().SetVisible(False)
        elif fault=='property':fp.SetValue('forged')
        elif fault=='extra_fp':b.Add(pcbnew.FOOTPRINT(b))
        elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(3,3))
        elif fault=='copper':
            t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));t.SetWidth(200000);b.Add(t)
        elif fault=='group':next(iter(b.Groups())).SetLocked(False)
        elif fault=='member':next(iter(b.Groups())).RemoveItem(fp)
        field._save_field_snapshot(b,child)
    assert not op.receive(source,child,path)['ok']


def test_native_opaque_attack_after_independent_scope(tmp_path,monkeypatch):
    source,child,path,q,uid,m=fixture(tmp_path);real=maps.receive
    passed=[False];original=field._save_field_snapshot
    def scope(*a):
        result=real(*a);assert result['ok'];passed[0]=True;return result
    def attack(board,target):
        original(board,target)
        if passed[0]and Path(target).name=='1.kicad_pcb':
            text=Path(target).read_text();Path(target).write_text(text[:-2]+'(opaque_native_material 1)\n)')
    monkeypatch.setattr(maps,'receive',scope);monkeypatch.setattr(field,'_save_field_snapshot',attack)
    r=op.receive(source,child,path)
    assert not r['ok']and r['error']=='non_map_native_ast_changed',r


def test_raw_opaque_attribute_is_not_annotation(tmp_path):
    source,child,path,*_=fixture(tmp_path);text=child.read_text();child.write_text(text[:-2]+'(future_material 1)\n)')
    assert not op.receive(source,child,path)['ok']


@pytest.mark.parametrize('timeout',[True,0,-1,11,float('nan')])
def test_limits_no_external_scope(tmp_path,timeout):
    source,child,path,*_=fixture(tmp_path);assert not op.receive(source,child,path,timeout_s=timeout)['ok']
    with pytest.raises(TypeError):op.receive(source,child,path,allowed_uuids=['forged'])
