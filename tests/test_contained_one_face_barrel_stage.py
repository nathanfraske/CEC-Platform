"""The stage selects actual warnings, never a supplied board/refdes list."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_contained_one_face_barrel_stage as stage
from test_contained_one_face_barrel_retirement import fixture


def reporting_build():
    import os
    path=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not path:pytest.skip('explicit native DRC test build required')
    return Path(path)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
def test_native_warning_drives_saved_stage_and_independent_receiving(tmp_path,face):
    source,b,v,t,net=fixture(tmp_path,face)
    digest=force._hash(source);original=source.read_bytes()
    result=stage.run(source,tmp_path/'run',board_hint='unclassified-test',
        expected_source_sha256=digest,reporting_build=reporting_build(),allow_locked_source=True)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['retired_native_dangling_barrels']==1
    assert result['independent_whole_source_receiving']['ok']
    assert result['new_native_fault_ids']==[] and source.read_bytes()==original
    assert not source.with_suffix('.kicad_prl').exists()
    assert not result['fab_ready'] and not result['release_authority']


@pytest.mark.parametrize('bad',[0,9,True])
def test_stage_does_not_create_output_with_invalid_scope(tmp_path,bad):
    source,*_=fixture(tmp_path)
    out=tmp_path/'not-created'
    with pytest.raises(ValueError):stage.run(source,out,board_hint='unclassified-test',
        expected_source_sha256=force._hash(source),reporting_build='not-used',maximum_barrels=bad)
    assert not out.exists()


def test_truncated_native_observation_cannot_grant_any_cut(tmp_path,monkeypatch):
    source,*_=fixture(tmp_path);original=source.read_bytes()
    monkeypatch.setattr(stage.native,'run',lambda *a,**k:dict(ok=True,complete=True,
        native_inventory=dict(potentially_truncated=True)))
    result=stage.run(source,tmp_path/'refused',board_hint='unclassified-test',
        expected_source_sha256=force._hash(source),reporting_build='not-used',allow_locked_source=True)
    assert not result['ok'] and not result['changed']
    assert result['candidate']==str(source.resolve()) and source.read_bytes()==original
    assert not list((tmp_path/'refused').glob('UNADMITTED*'))
