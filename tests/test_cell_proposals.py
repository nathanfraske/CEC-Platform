import copy
import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cec_cell_proposals import ranked_joint_proposals


def proposal(score, *, angle=0, blockers=(), x=3.):
    return dict(kind='decoupler_cell_reorient', ref='OWNER', owner_ref='OWNER',
                joint_rank=score, external_blockers=list(blockers),
                placements={'OWNER': (1., 2., angle), 'BYPASS': (x, 2., 0.)},
                position=(1., 2., angle), budget_priority=0)


@pytest.mark.parametrize('offset', [0., 197.5])
def test_qualified_rotated_tail_precedes_first_orientation(offset):
    incumbent={'OWNER': (1.+offset, 2., 0.), 'BYPASS': (10.+offset, 2., 0.)}
    rows=[proposal((.9,.9,0.)), proposal((0.,0.,0.), angle=270)]
    for row in rows:
        row['placements']={r:(p[0]+offset,p[1],p[2]) for r,p in row['placements'].items()}
    before=copy.deepcopy(rows)
    ranked=ranked_joint_proposals(rows, incumbent)
    assert ranked[0] is rows[1]
    assert rows == before
    assert len(ranked) == len(rows)


def test_external_eviction_and_pose_displacement_are_explicit_preferences():
    incumbent={'OWNER': (1.,2.,0.), 'BYPASS': (10.,2.,0.)}
    rows=[proposal((0,0,0), blockers=('NEIGHBOR',)),
          proposal((0,0,0), x=3.), proposal((0,0,0), x=9.)]
    assert ranked_joint_proposals(rows,incumbent) == [rows[2],rows[1],rows[0]]


@pytest.mark.parametrize('score', [None, (), (0,0), (math.nan,0,0), (-1,0,0)])
def test_unknown_scores_do_not_outrank_known_evidence(score):
    incumbent={'OWNER': (1.,2.,0.), 'BYPASS': (10.,2.,0.)}
    bad=proposal(score); good=proposal((0,0,0))
    assert ranked_joint_proposals([bad,good,bad],incumbent) == [good,bad,bad]


def test_ranked_head_survives_one_exact_trial_budget():
    import cec_synth_pipeline as synth
    incumbent={'OWNER': (1.,2.,0.), 'BYPASS': (10.,2.,0.)}
    rows=[proposal((.9,.9,0.)),proposal((0,0,0),angle=270)]
    assert synth._bounded_diverse_move_specs(rows,1)[0] is rows[0]
    ranked=ranked_joint_proposals(rows,incumbent)
    assert synth._bounded_diverse_move_specs(ranked,1)[0] is rows[1]


def test_owner_generator_applies_ranking_before_bounded_selection():
    import cec_synth_pipeline as synth
    candidate=SimpleNamespace(P={'OWNER': (10.,10.,0.),'BYPASS': (15.,10.,0.),
                                 'BYPASS2': (15.,15.,0.)})
    rows=[dict(owner_ref='OWNER',cap_ref='BYPASS',actionable=True,
               owner_supply_position_mm=(11.,10.),
               owner_ground_positions_mm=[{'position':(9.,10.)}],
               cap_position_mm=(15.,10.),cap_supply_position_mm=(14.,10.),
               cap_ground_position_mm=(16.,10.),supply_access_ok=False)]
    rows.append(dict(rows[0], cap_ref='BYPASS2', cap_position_mm=(15.,15.),
                     cap_supply_position_mm=(14.,15.),cap_ground_position_mm=(16.,15.)))
    def solve(candidate,owner,pose,*args,**kwargs):
        return [dict(placements={owner:pose,'BYPASS':(13.,10.,pose[2]),
                                 'BYPASS2':(13.,15.,pose[2])},
                     external_blockers=[],joint_rank=(0.,0.,0.) if pose[2]==270 else (1.,1.,0.))]
    with patch.object(synth,'_select_local_cell_placements',side_effect=solve):
        moves=synth._decoupler_owner_move_specs(candidate,rows,comps={},allow_owner_translation=False)
    chosen=synth._bounded_diverse_move_specs(moves,1)
    assert chosen[0]['kind']=='decoupler_cell_reorient'
    assert chosen[0]['delta_deg']==270
