"""Only expected ORIGINAL signatures are reused; every Source is freshly read."""
import pcbnew
import pytest
import cec_nonpolar_print_context as op
import cec_field_coupling as field
import cec_force_current as force
from test_nonpolar_print_context import fixture as original_fixture


def fixture(tmp_path,monkeypatch,quarter=0,back=False,fault=None):
    source,table,ids,library=original_fixture(tmp_path,monkeypatch,quarter*90,back)
    board=pcbnew.LoadBoard(str(source))
    reference=next(f for f in board.GetFootprints()if force._uid(f)==ids[0])
    third=pcbnew.FootprintLoad(str(library),'R_1206_3216Metric');board.Add(third)
    third.SetFPID(reference.GetFPID());third.SetReference('RENAMED_THIRD');third.SetValue('actual_source')
    if back:third.Flip(pcbnew.VECTOR2I(0,0),False)
    third.SetOrientationDegrees(quarter*90);third.SetPosition(pcbnew.VECTOR2I(40000001,27000003))
    third.Reference().SetVisible(True);ids.append(force._uid(third))
    if fault=='pad':next(iter(third.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='fab_field':
        next(g for g in third.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='mask':next(iter(third.Pads())).SetLocalSolderMaskMargin(1)
    elif fault=='court':
        next(g for g in third.GraphicalItems()if g.GetLayer()in(pcbnew.F_CrtYd,pcbnew.B_CrtYd)).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(board,source)
    return source,table,ids


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_private_expected_cache_is_shared_within_plan_never_between_plans(tmp_path,monkeypatch,quarter,back):
    source,table,ids=fixture(tmp_path,monkeypatch,quarter,back);original=op._physical_match;seen=[]
    raw=source.read_bytes()
    def observe(actual,template,**kwargs):
        cache=kwargs['expected_cache'];before=len(cache)
        matched=original(actual,template,**kwargs)
        seen.append((cache,before,len(cache),force._uid(actual)))
        return matched
    monkeypatch.setattr(op,'_physical_match',observe)
    def plan():return op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric'],
        expected_instance_uuids=ids,board_hint='different_labels')
    first=plan();first_cache=seen[0][0]
    assert all(cache is first_cache for cache,_,_,_ in seen)
    assert any(before>0 and before==after for _,before,after,_ in seen),[(a,b,c)for _,a,b,c in seen]
    assert len({uid for _,_,_,uid in seen})==3
    seen.clear();second=plan()
    assert first==second and seen[0][0]is not first_cache and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['pad','fab_field','mask','court'])
@pytest.mark.parametrize('back',[False,True])
def test_changed_same_fpid_source_never_reuses_another_instances_pass(tmp_path,monkeypatch,fault,back):
    source,table,ids=fixture(tmp_path,monkeypatch,back=back,fault=fault)
    raw=source.read_bytes()
    with pytest.raises(ValueError):
        op.plan(source,library_table=table,footprint_ids=['cec-Resistor_SMD:R_1206_3216Metric'],
            expected_instance_uuids=ids,board_hint='different_labels')
    assert source.read_bytes()==raw
