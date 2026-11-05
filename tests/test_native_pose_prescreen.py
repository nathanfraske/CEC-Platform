"""A cheap reject saves compilation but never admits a physical placement."""
import ast
import math
from pathlib import Path
from unittest.mock import patch

import pcbnew
import pytest
import cec_native_pose_prescreen as subject
import cec_cell_row_rebuild as row


def fixture():
    board=pcbnew.BOARD()
    for ref,x in [('arbitrary_owner',10),('arbitrary_follower',12),('fixed_obstacle',16)]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(x,10));board.Add(fp)
        g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_RECT);g.SetLayer(pcbnew.F_CrtYd)
        g.SetStart(pcbnew.VECTOR2I_MM(x-.5,9.5));g.SetEnd(pcbnew.VECTOR2I_MM(x+.5,10.5));g.SetWidth(50000);fp.Add(g)
    return board


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_native_positive_and_negative_restore_original_source(angle):
    board=fixture();before=row._source_binding(board)
    refused=subject.screen(board,{'arbitrary_owner':[16,10,angle]})
    assert not refused['ok'] and row._source_binding(board)==before
    passed=subject.screen(board,{'arbitrary_owner':[9,10,angle]})
    assert passed['ok'] and row._source_binding(board)==before
    assert not any(passed[k] for k in ('body_edge_keepout_screened','source_copper_retirement_authority',
        'routing_admitted','release_authority'))


def test_both_selected_and_stationary_members_keep_final_courtyard_scope():
    board=fixture();before=row._source_binding(board)
    result=subject.screen(board,{'arbitrary_owner':[14,10,0],'arbitrary_follower':[14,10,90]})
    assert not result['ok'] and row._source_binding(board)==before
    result=subject.screen(board,{'arbitrary_owner':[9,10,90],'arbitrary_follower':[12,10,0]},
        selected_refs=['arbitrary_owner'])
    assert result['ok'] and row._source_binding(board)==before


def test_native_exception_also_restores_without_source_serialization():
    board=fixture();before=row._source_binding(board)
    with patch('cec_escape_pose_frontier.courtyard_screen',side_effect=RuntimeError('native failure')):
        with pytest.raises(RuntimeError):subject.screen(board,{'arbitrary_owner':[9,11,90]})
    assert row._source_binding(board)==before


@pytest.mark.parametrize('poses',[{}, {'unknown':[1,2,0]}, {'arbitrary_owner':[math.nan,2,0]},
    {'arbitrary_owner':[True,2,0]}, {'arbitrary_owner':[1,2]}])
def test_invalid_or_unknown_pose_cannot_reach_preparation(poses):
    with pytest.raises(ValueError):subject.screen(fixture(),poses)


def test_missing_selected_courtyard_is_not_an_optimistic_pass():
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('unknown_court');board.Add(fp)
    assert not subject.screen(board,{'unknown_court':[1,2,0]})['ok']


def test_both_production_frontiers_prescreen_before_expensive_source_compile():
    root=Path(subject.__file__).parent
    for name,function in [('cec_escape_pose_frontier.py','frontier'),('cec_native_cell_pose_domains.py','receive_selection')]:
        tree=ast.parse((root/name).read_text())
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==function)
        prescreen=[n.lineno for n in ast.walk(fn) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id=='prescreen' and n.func.attr=='screen']
        prepare=[n.lineno for n in ast.walk(fn) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id in ('escape','compiler') and n.func.attr in ('prepare','compile')]
        assert prescreen and prepare and min(prescreen)<min(prepare)
