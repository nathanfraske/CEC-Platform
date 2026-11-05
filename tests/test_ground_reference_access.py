"""A stationary REF return cannot acquire nearby gratuitous ground copper."""
import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_ground_reference_access as ground
import cec_local_branch_access as access
from test_local_branch_access import fixture


def return_fixture(tmp_path):
    source,_,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));tasks=ground._tasks(board,'fixture')
    assert len(tasks)==1 and tasks[0]['verified_ground_alternatives'][0]['pin']=='2'
    child=force._copy_family(source,tmp_path/'ground-only')
    t=pcbnew.PCB_TRACK(board);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(board.GetNetcodeFromNetname('GND'))
    t.SetWidth(200000);t.SetStart(pcbnew.VECTOR2I(*tasks[0]['a_nm']))
    t.SetEnd(pcbnew.VECTOR2I(*tasks[0]['verified_ground_alternatives'][0]['at_nm']));board.Add(t)
    field._save_field_snapshot(board,child)
    return source,child


def test_source_true_ground_anchor_is_added_without_replacing_bypass_assignment(tmp_path):
    source,child=return_fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    before=source.read_bytes();row=access.targets(board,board_hint='fixture')[0]
    assert row['cap']=='C_RENAMED' and row['cap_pad']=='2'
    assert row['verified_ground_alternatives'][0]['role']=='manufacturer_ground'
    proof=ground.receive(source,child,board_hint='fixture')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['opens']<proof['source_opens']
    assert proof['exact_parent_material_and_poses_preserved']
    assert not proof['release_authority'] and not proof['kelvin_qualified']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['spur','cycle','wrong_end','narrow','unrelated','pose','barrel'])
def test_added_reference_path_cannot_hide_unowned_or_degenerate_material(tmp_path,fault):
    source,child=return_fixture(tmp_path);b=pcbnew.LoadBoard(str(child))
    tasks=ground._tasks(pcbnew.LoadBoard(str(source)),'fixture');a=tasks[0]['a_nm'];target=tasks[0]['verified_ground_alternatives'][0]['at_nm']
    incoming=next(t for t in b.GetTracks() if list(t.GetStart())==a and list(t.GetEnd())==target)
    if fault=='wrong_end':incoming.SetEnd(pcbnew.VECTOR2I(target[0],target[1]+100000))
    elif fault=='narrow':incoming.SetWidth(100000)
    elif fault=='pose':b.FindFootprintByReference('U_RENAMED').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I(*target));v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(incoming.GetNetCode());b.Add(v)
    else:
        points=([tuple(target),(target[0]+1000000,target[1])] if fault=='spur' else
            [tuple(target),(target[0]+1000000,target[1]),(target[0]+1000000,target[1]+1000000),
                (target[0],target[1]+1000000),tuple(target)] if fault=='cycle' else [(2_000_000,2_000_000),(3_000_000,2_000_000)])
        for x,y in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(incoming.GetNetCode());t.SetWidth(200000)
            t.SetStart(pcbnew.VECTOR2I(*x));t.SetEnd(pcbnew.VECTOR2I(*y));b.Add(t)
    field._save_field_snapshot(b,child)
    result=ground.receive(source,child,board_hint='fixture')
    assert not result['ok'] and result['errors'] and not result['release_authority']


def test_stationary_constructor_uses_the_source_verified_true_ground_pad(tmp_path):
    source,_,_=fixture(tmp_path)
    result=ground.run(source,tmp_path/'auto-ground',board_hint='fixture',source_sha256=force._hash(source))
    assert result['ok'],result
    assert result['opens']<result['source_opens'] and result['source_family_and_code_unchanged']


def test_assigned_bypass_return_is_an_independently_received_destination(tmp_path):
    source,_,_=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    from cec_native_items import discard_items
    discard_items(board,[t for t in board.GetTracks() if t.GetNetname()=='MEASURE_MINUS'])
    field._save_field_snapshot(board,source)
    task=ground._tasks(board,'fixture')[0]
    target=ground._destinations(task)[-1]
    assert target['role']=='assigned_bypass_return' and target['ref']==task['cap']
    child=force._copy_family(source,tmp_path/'bypass-return')
    t=pcbnew.PCB_TRACK(board);t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(board.GetNetcodeFromNetname(task['net']));t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I(*task['a_nm']));t.SetEnd(pcbnew.VECTOR2I(*target['at_nm']))
    board.Add(t);field._save_field_snapshot(board,child)
    result=ground.receive(source,child,board_hint='fixture')
    assert result['ok'] and result['complete'],result['errors']
    assert result['gained_references'][0]['destination']['role']=='assigned_bypass_return'
    assert not result['release_authority'] and not result['current_authority']


def test_unconnected_bypass_return_never_becomes_an_arbitrary_ground_anchor(tmp_path):
    source,_,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source))
    from cec_native_items import discard_items
    discard_items(board,[t for t in board.GetTracks() if t.GetNetname()=='GND'])
    assert not ground._tasks(board,'fixture')
