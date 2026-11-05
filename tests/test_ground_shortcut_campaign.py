"""Short saved return witnesses are not a reason to skip a compact board."""
import json,os
from pathlib import Path
import pcbnew
import pytest
import cec_ground_return_shortcut as owner
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_ground_return_shortcut import fixture as original_fixture
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,params,pad,via,point=original_fixture(tmp_path,quarter,mirror,layer)
    cut=[t for t in b.GetTracks() if t.GetNetname()=='GND' and force._uid(t)!=params['target_via_uuid']]
    discard_items(b,cut)
    for a,z in [((8,8),(9.5,8)),((9.5,8),(10.3,8.8)),((10.3,8.8),(12,8.8))]:
        track(b,'GND',[x/1e6 for x in point(*a)],[x/1e6 for x in point(*z)],layer=layer,width=.2).SetLocked(True)
    # A second pre-existing plane barrel gives a short but indirect source
    # return. Reusing the other barrel adds no acute same-face convergence.
    old_via=via.Duplicate();old_via.m_Uuid.Clone(pcbnew.KIID());old_via.SetPosition(point(12,8.8));b.Add(old_via)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,params


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_under_three_mm_returns_are_discovered_in_every_rigid_frame_without_new_authority(tmp_path,quarter,mirror,layer):
    source,params=fixture(tmp_path,quarter,mirror,layer);raw=source.read_bytes()
    default=owner.discover(source,board_hint='synthetic')
    assert not any(p['pad_uuid']==params['pad_uuid'] for p in default['plans'])
    q=owner.discover(source,board_hint='synthetic',minimum_return_mm=.5)
    selected=[p for p in q['plans'] if p['pad_uuid']==params['pad_uuid']]
    assert selected and 2.5<selected[0]['source_return_witness_mm']<3.
    assert selected[0]['new_explicit_path_mm']==2.5 and selected[0]['width_nm']==200000
    assert selected[0]['new_holes']==0 and not selected[0]['current_or_fabrication_qualified']
    assert source.read_bytes()==raw and not q['source_geometry_mutated']


@pytest.mark.parametrize('quarter',[0,2])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_bounded_short_return_campaign_remeasures_and_never_counts_removed_copper(tmp_path,quarter,layer,monkeypatch,capsys):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,params=fixture(tmp_path,quarter=quarter,layer=layer);raw=source.read_bytes()
    r=owner.run_campaign(source,tmp_path/'campaign',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),minimum_return_mm=.5,max_passes=4)
    assert r['ok'] and r['complete'] and r['changed'] and not r['errors'],r
    assert 1<=len(r['phase_receipts'])<=4 and r['shortened_return_witness_mm']>.1
    assert r['summed_terminal_return_witness_gains_not_removed_copper_length'] and r['original_copper_material_retained']
    assert r['minimum_return_is_search_ranking_not_receiving_or_current_authority']
    assert not r['new_holes'] and not r['current_qualified'] and not r['whole_board_cleanliness_or_no_path_proof']
    cursor=force._hash(source);seen={cursor};gain=0.
    for phase in r['phase_receipts']:
        q=json.loads(Path(phase['path']).read_text());assert q['source_sha256']==cursor and q['minimum_return_mm']==.5
        assert q['ok'] and q['complete'] and q['changed'] and not q['errors']
        accepted=next(a for a in q['attempts'] if a['accepted']);proof=accepted['independent_saved_phase']
        assert proof['ok'] and proof['complete'] and not proof['retired_track_uuids'] and proof['new_holes']==0
        assert proof['proposal']['width_nm']==200000 and accepted['opens']==0 and not accepted['new_native_fault_ids']
        cursor=q['candidate_sha256'];assert cursor not in seen;seen.add(cursor);gain+=q['shortened_return_witness_mm']
    assert gain==pytest.approx(r['shortened_return_witness_mm']) and source.read_bytes()==raw
    # Exercise the real completed campaign's CLI representation without
    # rerunning its physical work or editing an already-owned output family.
    import sys
    monkeypatch.setattr(owner,'run_campaign',lambda *a,**kw:r)
    monkeypatch.setattr(sys,'argv',['ground-stage','--source',str(source),'--out',str(tmp_path/'campaign'),
        '--board-hint','synthetic','--expected-source-sha256',force._hash(source),'--reporting-build',native,
        '--minimum-return-mm','.5','--max-passes','4'])
    capsys.readouterr();assert owner.main()==0
    result=json.loads(capsys.readouterr().out);assert result['shortened_return_witness_mm']==r['shortened_return_witness_mm']
    assert result['receipt']==str(tmp_path/'campaign/campaign.json') and not result['errors']


@pytest.mark.parametrize('value',[None,True,0,-.1,16.01,float('nan'),float('inf'),'.5'])
@pytest.mark.parametrize('operation',[owner.run,owner.run_campaign])
def test_untyped_or_unbounded_search_threshold_fails_before_any_output(tmp_path,value,operation):
    with pytest.raises(ValueError):operation(tmp_path/'missing',tmp_path/'never',board_hint='synthetic',
        expected_source_sha256='0'*64,reporting_build=tmp_path/'native',minimum_return_mm=value)
    assert not (tmp_path/'never').exists()


@pytest.mark.parametrize('value',[True,0,5,1.5,float('nan'),'4'])
def test_campaign_cannot_create_unbounded_work_or_a_directory_for_invalid_limits(tmp_path,value):
    with pytest.raises(ValueError):owner.run_campaign(tmp_path/'missing',tmp_path/'never',board_hint='synthetic',
        expected_source_sha256='0'*64,reporting_build=tmp_path/'native',max_passes=value)
    assert not (tmp_path/'never').exists()


@pytest.mark.parametrize('fault',['failure','repeat'])
def test_campaign_stops_on_failed_receiving_or_a_repeated_source_instead_of_spinning(tmp_path,monkeypatch,fault):
    source,params=fixture(tmp_path);raw=source.read_bytes();digest=force._hash(source);calls=[]
    def refused(parent,dest,**kw):
        calls.append(str(parent));dest.mkdir()
        q=dict(ok=fault=='repeat',complete=fault=='repeat',changed=fault=='repeat',candidate=str(parent),candidate_sha256=digest)
        force._write(dest/'stage.json',q);return q
    monkeypatch.setattr(owner,'run',refused)
    r=owner.run_campaign(source,tmp_path/'campaign',board_hint='synthetic',expected_source_sha256=digest,
        reporting_build=tmp_path/'native',minimum_return_mm=.5,max_passes=4)
    assert not r['ok'] and not r['complete'] and r['errors'] and len(calls)==1 and not r['phase_receipts']
    assert r['candidate_sha256']==digest and not r['changed'] and source.read_bytes()==raw
