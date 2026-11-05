"""Planner-local negative geometry is exact, fresh and never a verdict cache."""
from pathlib import Path
import pcbnew
import pytest
from shapely.geometry import box
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as masks
import cec_force_current as force
from test_dense_reference_mapping import fixture


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('policy',['reserve_native_lands','native_mask_and_bore'])
@pytest.mark.parametrize('bodies',[False,True])
def test_cached_and_uncached_exact_obstacles_and_rejection_parity(tmp_path,back,policy,bodies):
    source,_,uid=fixture(tmp_path,back=back)
    board=pcbnew.LoadBoard(str(source));fp=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    face=pcbnew.B_SilkS if back else pcbnew.F_SilkS;excluded={force._uid(fp.Reference())}
    preparation=dense._ObstaclePreparation(board);raw=source.read_bytes()
    before=dense._obstacle_epoch(board)
    options=dict(assembled_bodies=bodies,via_ink_policy=policy)
    first=dense.obstacles(board,face,excluded,.15,**options)
    cached=dense.obstacles(board,face,excluded,.15,_prepared=preparation,**options)
    again=dense.obstacles(board,face,excluded,.15,_prepared=preparation,**options)
    assert first.wkb==cached.wkb==again.wkb
    for x in (15.,18.,20.,22.,25.):
        candidate=box(x,19.7,x+.4,20.3)
        assert first.intersects(candidate)==cached.intersects(candidate)
    assert before==dense._obstacle_epoch(board)and source.read_bytes()==raw


def test_material_extraction_once_with_bodies_added_separately(tmp_path,monkeypatch):
    source,_,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    fp=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    prep=dense._ObstaclePreparation(board);calls=[];real=dense._obstacle_material
    excluded={force._uid(fp.Reference())}
    expected=dense.obstacles(board,pcbnew.F_SilkS,excluded,.15,assembled_bodies=True)
    def observe(*args):calls.append(args[1:]);return real(*args)
    monkeypatch.setattr(dense,'_obstacle_material',observe)
    hard=dense.obstacles(board,pcbnew.F_SilkS,excluded,.15,assembled_bodies=False,_prepared=prep)
    bodies=dense.obstacles(board,pcbnew.F_SilkS,excluded,.15,assembled_bodies=True,_prepared=prep)
    assert len(calls)==1 and bodies.wkb==expected.wkb
    dense.obstacles(board,pcbnew.B_SilkS,excluded,.15,assembled_bodies=False,_prepared=prep)
    dense.obstacles(board,pcbnew.F_SilkS,set(),.15,assembled_bodies=False,_prepared=prep)
    dense.obstacles(board,pcbnew.F_SilkS,excluded,.15,assembled_bodies=False,
        via_ink_policy='native_mask_and_bore',_prepared=prep)
    assert len(calls)==4


def test_two_actual_owner_exclusions_and_clearances_do_not_share_results(tmp_path):
    source,_,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    first=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    library=Path(__file__).resolve().parents[1]/'lib/vendor/Package_SO.pretty'
    other=pcbnew.FootprintLoad(str(library),'SOIC-8_3.9x4.9mm_P1.27mm')
    board.Add(other);other.SetReference('OTHER_OWNER');other.SetPosition(pcbnew.VECTOR2I_MM(23,23))
    other.Reference().SetVisible(True);other.Reference().SetLayer(pcbnew.F_SilkS)
    prep=dense._ObstaclePreparation(board);results=[]
    for owner in(first,other):
        excluded={force._uid(owner.Reference())}
        for gap in(.15,.25):
            options=dict(assembled_bodies=False,via_ink_policy='native_mask_and_bore')
            expected=dense.obstacles(board,pcbnew.F_SilkS,excluded,gap,**options)
            result=dense.obstacles(board,pcbnew.F_SilkS,excluded,gap,_prepared=prep,**options)
            assert result.wkb==expected.wkb;results.append(result.wkb)
    assert len(set(results))==4 and len(prep.base)==2


@pytest.mark.parametrize('fault',['text','pose','pad','drawing','property','environment','other_board'])
def test_no_in_memory_mutation_or_foreign_board_can_reuse_preparation(tmp_path,monkeypatch,fault):
    source,_,uid=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    fp=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    prep=dense._ObstaclePreparation(board)
    def read(actual=board):return dense.obstacles(actual,pcbnew.F_SilkS,set(),.15,
        assembled_bodies=False,_prepared=prep)
    read()
    if fault=='text':fp.Reference().SetText('CHANGED')
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad':list(fp.Pads())[0].SetSize(pcbnew.VECTOR2I(123000,456000))
    elif fault=='drawing':
        item=pcbnew.PCB_SHAPE(board);item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetLayer(pcbnew.F_SilkS);item.SetStart(pcbnew.VECTOR2I_MM(19,19))
        item.SetEnd(pcbnew.VECTOR2I_MM(20,20));board.Add(item)
    elif fault=='property':
        props=board.GetProperties();props['NEW_NATIVE_CONTEXT']='changed';board.SetProperties(props)
    elif fault=='environment':monkeypatch.setenv('CEC_TEST_OBSTACLE_EPOCH','changed')
    else:board=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='reference_obstacle_native_inputs_changed'):
        read(board)


def test_fresh_invocation_recomputes_changed_source_geometry(tmp_path):
    source,grade,uid=fixture(tmp_path);first=pcbnew.LoadBoard(str(source))
    a=dense.obstacles(first,pcbnew.F_SilkS,set(),.15,assembled_bodies=False,
        _prepared=dense._ObstaclePreparation(first))
    fp=next(f for f in first.GetFootprints()if force._uid(f)==uid)
    fp.Reference().Move(pcbnew.VECTOR2I_MM(2,0));pcbnew.SaveBoard(str(source),first)
    second=pcbnew.LoadBoard(str(source))
    b=dense.obstacles(second,pcbnew.F_SilkS,set(),.15,assembled_bodies=False,
        _prepared=dense._ObstaclePreparation(second))
    assert a.wkb!=b.wkb
    # Existing stale saved-Source grade still refuses the real public plan.
    with pytest.raises(ValueError):dense.plan(source,grade=grade,board_hint='explicit_synthetic_legend')


@pytest.mark.parametrize('back',[False,True])
def test_real_mask_planner_uses_local_preparation_without_changing_proposal(tmp_path,monkeypatch,back):
    source,grade,_=fixture(tmp_path,back=back);before=source.read_bytes();calls=[]
    real=masks.masks.native_mask_artwork
    def observe(board,face):calls.append(face);return real(board,face)
    monkeypatch.setattr(masks.masks,'native_mask_artwork',observe)
    cached=masks.plan(source,grade=grade,board_hint='explicit_synthetic_legend',maximum_components=1)
    assert len(calls)==len(set(calls))==2
    # Disable only the local reuse, retaining the exact old geometry path.
    original=masks._private.obstacles
    def uncached(*args,**kwargs):kwargs.pop('_prepared',None);return original(*args,**kwargs)
    monkeypatch.setattr(masks._private,'obstacles',uncached)
    fresh=masks.plan(source,grade=grade,board_hint='explicit_synthetic_legend',maximum_components=1)
    assert cached==fresh and source.read_bytes()==before


def test_caller_object_is_not_planner_geometry_authority(tmp_path):
    source,_,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='planner_owned_reference_obstacle_preparation_required'):
        dense.obstacles(board,pcbnew.F_SilkS,set(),.15,assembled_bodies=False,_prepared={})
