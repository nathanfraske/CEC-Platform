"""Distinct stage Ground policy is actually used by the complete compiler."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
from test_linear_stage_ground_entries import fixture


@pytest.mark.parametrize('back',[False,True])
def test_real_Source_stage_ground_does_not_enter_low_power_portal(tmp_path,monkeypatch,back):
    source,posed,partial,hint,owner,calls=fixture(tmp_path,monkeypatch,back=back)
    plan=escape.prepare(source,partial['poses'],board_hint=hint,
        allow_linear_power_stage_reconstruction=True)
    original=escape.assigned_ground_entries
    seen=[]
    def no_stage_portal(board,bypasses,**kwargs):
        assert not any(q['owner']==owner for q in bypasses.values())
        seen.append(copy.deepcopy(bypasses))
        return original(board,bypasses,**kwargs)
    monkeypatch.setattr(escape,'assigned_ground_entries',no_stage_portal)
    before=escape.row._source_binding(source),escape.row._source_binding(posed)
    requests=escape.obligations(source,posed,plan)
    independent=[q for q in requests.values()if q.get('independent_linear_stage_ground_demand')]
    assert seen==[{}]and len(independent)==4
    assert all(q['reach_mm']==.8 and not q['same_package_ground_link_proposal_allowed']for q in independent)
    assert all('selected_bypass_entry'not in q and 'retained_projected_source_return'not in q for q in independent)
    assert len([q for q in requests.values()if q['kind']=='local_supply'])==3
    assert before==(escape.row._source_binding(source),escape.row._source_binding(posed))


def test_bad_Source_stage_proof_cannot_be_excluded_from_legacy_policy(tmp_path,monkeypatch):
    source,posed,partial,hint,owner,calls=fixture(tmp_path,monkeypatch)
    plan=escape.prepare(source,partial['poses'],board_hint=hint,
        allow_linear_power_stage_reconstruction=True)
    plan['source_linear_power_stages'][owner]['current_authority']=True
    before=escape.row._source_binding(source),escape.row._source_binding(posed)
    with pytest.raises(ValueError):escape._obligations(source,posed,plan)
    assert before==(escape.row._source_binding(source),escape.row._source_binding(posed))
