"""Work budgets must be explicit and bounded, never evidence waivers."""
import pytest
import cec_force_sense_evidence as sense
import cec_native_contour_receiving as receiving
from test_native_contour_receiving import saved


@pytest.mark.parametrize('seconds',[0,-1,True,None,'40',float('inf'),float('nan'),60.01])
def test_bad_lease_refuses_before_source_reconstruction(tmp_path,monkeypatch,seconds):
    def forbidden(*a,**kw):raise AssertionError('invalid lease reached source replay')
    monkeypatch.setattr(receiving,'receive_literal_phase',forbidden)
    proof=receiving.receive(tmp_path/'absent',tmp_path/'also-absent',[],
        board_hint='synthetic',sense_timeout_s=seconds)
    assert not proof['ok'] and not proof['complete'] and proof['errors']==[
        'ValueError:explicit_bounded_native_contour_sense_lease_required']
    assert not proof['release_authority'] and not proof['new_capacity_credited']


@pytest.mark.parametrize('kwargs,expected',[({},10.),({'sense_timeout_s':40.},40.),
    ({'sense_timeout_s':60.},60.),({'sense_timeout_s':.25},.25)])
def test_same_lease_reaches_both_native_replays_but_does_not_waive_unknowns(tmp_path,monkeypatch,kwargs,expected):
    source,child,records=saved(tmp_path);original=(source.read_bytes(),child.read_bytes());calls=[]
    def replay(path,**options):
        calls.append((path,options));return dict(deliberately_unqualified_budget_boundary=True)
    monkeypatch.setattr(sense,'replay',replay)
    # Simulate only the evidence boundary, NOT a successful physical packet.
    # Native immutable-source construction/partition receiving above remains
    # real. Increasing a lease must never turn this refusal into acceptance.
    monkeypatch.setattr(sense,'compare_contour_preservation',lambda *a,**kw:
        dict(comparison_complete=False,same_evidence=False,errors=['unqualified']))
    proof=receiving.receive(source,child,records,board_hint='synthetic',**kwargs)
    assert calls==[(source.resolve(),dict(board_hint='synthetic',timeout_s=expected)),
        (child.resolve(),dict(board_hint='synthetic',timeout_s=expected))]
    assert not proof['ok'] and not proof['complete']
    assert proof['errors']==['ValueError:absolute_signed_contour_cuts_and_unaffected_evidence_required']
    assert proof['sense_timeout_s']==expected
    assert original==(source.read_bytes(),child.read_bytes())
    assert not proof['release_authority'] and not proof['new_capacity_credited']
