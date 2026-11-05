"""Current/cut-chain baseline must not normalize unowned hidden properties."""
from unittest.mock import patch
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_full_current_planar_reflow as reflow
import cec_source_cut_chain as chain
from test_full_current_planar_reflow import fixture,receive
from test_source_literal_retirement import hidden_field_last


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_current_and_composed_receivers_preserve_actual_hidden_source_records(tmp_path,quarter,face):
    source,child,uid,net,contract,domains=fixture(tmp_path,quarter,prefix='/renamed/',face=face)
    source,child=Path(source),Path(child)
    for path in(source,child):hidden_field_last(path)
    saved=[p.read_bytes()for p in(source,child)]
    proof=receive(source,child,uid,net,contract,domains)
    assert proof['ok']and proof['complete'],proof
    assert proof['literal_native_cut_projection']['independent_full_native_inventory_equal']
    phases=[dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid])]
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains):
        result=chain.receive(source,child,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert result['ok']and result['complete'],result
    assert result['literal_native_cut_projection']['exact_opaque_source_subtraction']
    assert [p.read_bytes()for p in(source,child)]==saved


def test_fixing_internal_projection_does_not_normalize_candidate_footprints(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path)
    for path in(source,child):hidden_field_last(path)
    # A child no-op save changes opaque order but is NOT authorized by a
    # current-track repair. Only the internally constructed cut baseline
    # gets literal Source preservation; the real saved child stays strict.
    b=pcbnew.LoadBoard(str(child));field._save_field_snapshot(b,child)
    result=receive(source,child,uid,net,contract,domains)
    assert not result['ok']and result['errors']
