"""Code-stale archived green results cannot masquerade as current craft proof."""
import copy
import json
from unittest import mock
import pytest
import pcbnew
import cec_dashboard as dashboard
import cec_route_quality as quality
import cec_synth_pipeline as synth


def clean_gates(identity):
    return dict(ok=True,kelvin_ok=True,drc=0,unconnected=0,route_sanity={
        'craft_ok':True,'craft_policy_identity':identity})


@pytest.mark.parametrize('identity',[None,{},'old',{'schema':0,'modules':{}}])
def test_legacy_or_different_policy_identity_cannot_be_dashboard_clean(identity):
    verdict,failing=dashboard._verdict(clean_gates(identity),{'ok':False})
    assert (verdict,failing)==('UNKNOWN',['route-craft-unverified'])


def test_actual_loaded_identity_is_retained_but_disk_change_withholds_new_analysis():
    loaded=quality.policy_identity();changed=copy.deepcopy(loaded)
    changed['modules']['cec_route_quality.py']='0'*64
    with mock.patch.object(quality,'_read_policy_identity',return_value=changed):
        assert quality.policy_identity()==loaded
        with pytest.raises(ValueError,match='loaded_route_craft_policy_is_stale'):
            quality.analyze_board(pcbnew.BOARD())
        assert dashboard._verdict(clean_gates(loaded),{'ok':False})[0]=='UNKNOWN'
    assert dashboard._verdict(clean_gates(loaded),{'ok':False})==('CLEAN',[])


def test_fresh_saved_oracle_carries_actual_executing_policy_identity(tmp_path):
    path=tmp_path/'saved.kicad_pcb';pcbnew.SaveBoard(str(path),pcbnew.BOARD());before=path.read_bytes()
    report=synth._oracle_route_sanity(str(path))
    assert report['craft_policy_identity']==quality.policy_identity()==quality.policy_identity(current=True)
    assert path.read_bytes()==before


def test_catalog_rechecks_policy_change_without_rewriting_original_archives(tmp_path):
    root=tmp_path/'catalog';entry=root/'unchanged';entry.mkdir(parents=True)
    identity=quality.policy_identity();summary=dict(id='unchanged',epoch=1,panels={},
        gates=clean_gates(identity),thermal={'ok':False},verdict='CLEAN',failing=[])
    path=entry/'summary.json';path.write_text(json.dumps(summary));before=path.read_bytes()
    changed=copy.deepcopy(identity);changed['modules']['cec_route_quality.py']='0'*64
    saved=(dashboard._archive_disk_signature,dict(dashboard._archive_by_id),list(dashboard._archive),dict(dashboard._archive_sync_status))
    try:
        with mock.patch.object(dashboard,'ARCHIVE_ROOT',str(root)):
            dashboard._archive_disk_signature=None
            with mock.patch.object(dashboard,'_current_craft_policy_identity',return_value=identity):
                assert dashboard._load_archive(force=False)
                assert dashboard._archive_by_id['unchanged']['verdict']=='CLEAN'
                assert not dashboard._load_archive(force=False)
            with mock.patch.object(dashboard,'_current_craft_policy_identity',return_value=changed):
                assert dashboard._load_archive(force=False)
                assert dashboard._archive_by_id['unchanged']['verdict']=='UNKNOWN'
            assert path.read_bytes()==before
    finally:
        signature,by_id,archive,status=saved
        dashboard._archive_disk_signature=signature;dashboard._archive_by_id.clear();dashboard._archive_by_id.update(by_id)
        dashboard._archive[:]=archive;dashboard._archive_sync_status.clear();dashboard._archive_sync_status.update(status)


def test_stale_detail_pills_cannot_stay_green_under_unknown_summary():
    assert "const craftUnverified=(cur.failing||[]).includes('route-craft-unverified')"in dashboard.PAGE
    assert "off45===0&&!craftUnverified?'ok':'bad'"in dashboard.PAGE
    assert 'route craft · unverified'in dashboard.PAGE
