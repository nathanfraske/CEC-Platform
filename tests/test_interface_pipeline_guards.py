import json
from pathlib import Path
from types import SimpleNamespace

import pcbnew
import pytest

import cec_interface_eco as eco
import cec_full_pipeline as pipeline
from cec_native_items import discard_items
from test_interface_eco import fixture_board


def test_replacement_normalization_can_clear_eco_only_after_copper_free_proof(tmp_path, monkeypatch):
    source = fixture_board(tmp_path)
    staged = tmp_path / 'eco.kicad_pcb'
    eco.apply(source, staged, {'alpha': (5,5,0)}, expected_sha256=eco.sha(source))
    with pytest.raises(ValueError, match='requires replacement'):
        pipeline._copy_sidecars(staged, tmp_path / 'wrong.kicad_pcb')
    cfg = SimpleNamespace(pcb=str(staged), sch=str(tmp_path/'source.kicad_sch'),
                          dir=str(tmp_path), params={})
    def sync(_cfg, board_path, **kwargs):
        board=pcbnew.LoadBoard(str(board_path))
        discard_items(board, list(board.GetTracks()))
        pcbnew.SaveBoard(str(board_path), board)
        return {'unexpected_board_refs': [], 'missing_schematic_refs': []}
    monkeypatch.setattr(pipeline, '_run_source_sync_process', sync)
    report=pipeline._normalize_schematic_first_source(cfg, staged, tmp_path/'replacement')
    assert report['ok']
    record=eco.require_rebuilt(report['board'])
    assert record['copper_free_replacement_seed'] and not record['admission_ok']
    assert eco.read_status(staged)['route_authority_invalidated']


def test_derived_rebuild_retains_latest_poses_and_names_actual_source(tmp_path, monkeypatch):
    canonical=fixture_board(tmp_path)
    staged=tmp_path/'derived.kicad_pcb'
    eco.apply(canonical, staged, {'alpha':(6,5,0)}, expected_sha256=eco.sha(canonical))
    cfg=SimpleNamespace(pcb=str(canonical),sch=str(tmp_path/'source.kicad_sch'),
                        dir=str(tmp_path),params={})
    source_hash=eco.sha(staged)
    def sync(_cfg, path, **kwargs):
        board=pcbnew.LoadBoard(str(path))
        discard_items(board,list(board.GetTracks()))
        pcbnew.SaveBoard(str(path),board)
        return {'unexpected_board_refs':[], 'missing_schematic_refs':[]}
    monkeypatch.setattr(pipeline,'_run_source_sync_process',sync)
    assert pipeline._source_normalization_requested(replace_placement=True,
        fresh_placement_only=False,params={},input_board=staged,
        canonical_board=canonical,allow_derived_input=True)
    result=pipeline._normalize_schematic_first_source(cfg,staged,tmp_path/'rebuilt')
    details=json.loads(Path(result['report']).read_text())
    assert details['canonical_board']==str(canonical)
    assert details['normalization_input']==str(staged)
    assert details['derived_interface_rebuild']
    before=pcbnew.LoadBoard(str(staged)); after=pcbnew.LoadBoard(result['board'])
    assert eco.poses(before)==eco.poses(after)
    assert not list(after.GetTracks())
    assert eco.sha(staged)==source_hash
    assert eco.require_rebuilt(result['board'])['copper_free_replacement_seed']


def test_explicit_fresh_non_eco_rebuild_keeps_selected_outline_and_both_sources(tmp_path,monkeypatch):
    canonical=fixture_board(tmp_path)
    selected=tmp_path/'compact-current.kicad_pcb'
    import shutil
    shutil.copy2(canonical,selected)
    board=pcbnew.LoadBoard(str(selected))
    board.FindFootprintByReference('alpha').SetPosition(pcbnew.VECTOR2I_MM(6,5))
    pcbnew.SaveBoard(str(selected),board)
    originals={path:eco.sha(path) for path in (canonical,selected)}
    cfg=SimpleNamespace(pcb=str(canonical),sch=str(tmp_path/'current.kicad_sch'),
                        dir=str(tmp_path),params={})
    def sync(_cfg,path,**kwargs):
        assert _cfg is cfg
        loaded=pcbnew.LoadBoard(str(path));discard_items(loaded,list(loaded.GetTracks()))
        pcbnew.SaveBoard(str(path),loaded)
        return dict(unexpected_board_refs=[],missing_schematic_refs=[])
    monkeypatch.setattr(pipeline,'_run_source_sync_process',sync)
    assert pipeline._source_normalization_requested(replace_placement=True,
        fresh_placement_only=True,params={},input_board=selected,
        canonical_board=canonical,allow_derived_input=True)
    result=pipeline._normalize_schematic_first_source(cfg,selected,tmp_path/'fresh')
    record=json.loads(Path(result['report']).read_text())
    assert record['normalization_input']==str(selected)
    child=pcbnew.LoadBoard(result['board']);parent=pcbnew.LoadBoard(str(selected))
    assert eco.poses(child)==eco.poses(parent) and not list(child.GetTracks())
    assert all(eco.sha(path)==digest for path,digest in originals.items())


def test_observed_successful_sync_cannot_clear_retained_copper(tmp_path, monkeypatch):
    source = fixture_board(tmp_path)
    staged = tmp_path/'eco.kicad_pcb'
    eco.apply(source, staged, {'alpha': (5,5,0)}, expected_sha256=eco.sha(source))
    cfg=SimpleNamespace(pcb=str(staged), sch=str(tmp_path/'source.kicad_sch'),
                        dir=str(tmp_path), params={})
    monkeypatch.setattr(pipeline, '_run_source_sync_process', lambda *a,**k: {})
    with pytest.raises(pipeline.PipelineBlocked, match='copper-free'):
        pipeline._normalize_schematic_first_source(cfg, staged, tmp_path/'retained')


def test_hardware_qualification_is_independently_withholding(tmp_path, monkeypatch):
    import cec_constraints, cec_score, cec_synth_pipeline, cec_fab_profile
    import cec_route_quality, cec_fab_check, cec_hardware_qualification
    board=fixture_board(tmp_path)
    oracle=tmp_path/'oracle.json'; oracle.write_text('{"gate":true}')
    monkeypatch.setattr(cec_synth_pipeline, '_oracle_hints_pours', lambda *a: ({},[],{}))
    monkeypatch.setattr(cec_score,'score',lambda *a: SimpleNamespace(
        gates_pass=True,drc=0,drc_types={},unconnected=0,kelvin_ok=True,
        diffpair_ok=True,tracks=1,vias=0,length=10))
    monkeypatch.setattr(cec_constraints,'release_gate',lambda *a,**k:{'ok':True})
    monkeypatch.setattr(cec_route_quality,'analyze_board',lambda *a:{
        'craft_ok':True,'power_contour_review_ok':True})
    monkeypatch.setattr(cec_fab_profile,'active_profile_name',lambda *a,**k:'fixture')
    monkeypatch.setattr(cec_fab_profile,'stackup_oz',lambda *a:{'F.Cu':1})
    monkeypatch.setattr(cec_fab_check,'check',lambda *a:{})
    monkeypatch.setattr(cec_hardware_qualification,'evaluate',lambda *a:{'ok':False,'requirements':[]})
    cfg=SimpleNamespace(sch=str(tmp_path/'source.kicad_sch'),board='fixture',is_draft=False)
    report=pipeline._independent_signoff(board,cfg,oracle,tmp_path/'signoff.json')
    assert not report['ok'] and report['failed_terms']==['hardware_qualification']
