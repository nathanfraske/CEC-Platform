import pytest
import cec_full_pipeline as pipeline

def requested(**kwargs):
    defaults=dict(replace_placement=True,fresh_placement_only=True,params={},
                  input_board='/declared/board.kicad_pcb',canonical_board='/declared/board.kicad_pcb')
    return pipeline._source_normalization_requested(**dict(defaults,**kwargs))

def test_fresh_replacement_uses_current_schematics_without_board_special_case():
    assert requested()
    assert not requested(replace_placement=False)
    assert not requested(fresh_placement_only=False)
    assert requested(fresh_placement_only=False,params={'schematic_first_normalization':True})

def test_derived_copper_is_never_silently_stripped():
    with pytest.raises(pipeline.PipelineBlocked):
        requested(input_board='/derived/routed.kicad_pcb')
    assert not requested(replace_placement=False,input_board='/derived/routed.kicad_pcb')


def test_incremental_derived_input_stays_subject_to_live_intake_not_staging_normalization():
    assert not requested(fresh_placement_only=False,
        params={'schematic_first_normalization':True},
        input_board='/derived/current-candidate.kicad_pcb')
    with pytest.raises(pipeline.PipelineBlocked):
        requested(params={'schematic_first_normalization':True},
                  input_board='/derived/current-candidate.kicad_pcb')


def test_explicit_derived_replacement_rebuilds_only_a_verified_interface_eco(tmp_path):
    import cec_interface_eco as eco
    import json
    board=tmp_path/'derived.kicad_pcb'
    board.write_text('native fixture bytes')
    kwargs=dict(input_board=board, fresh_placement_only=False,
                allow_derived_input=True)
    assert not requested(**kwargs)
    certificate=board.with_suffix('.interface-eco.json')
    row={'output_sha256':eco.sha(board), 'route_authority_invalidated':True}
    certificate.write_text(json.dumps(row))
    assert requested(**kwargs)
    assert not requested(**dict(kwargs, replace_placement=False))
    assert not requested(**dict(kwargs, allow_derived_input=False))
    assert requested(**dict(kwargs, fresh_placement_only=True))
    row['route_authority_invalidated']=False
    certificate.write_text(json.dumps(row))
    assert not requested(**kwargs)
    row['route_authority_invalidated']=True
    row['output_sha256']='stale'
    certificate.write_text(json.dumps(row))
    with pytest.raises(pipeline.PipelineBlocked, match='board bytes'):
        requested(**kwargs)


@pytest.mark.parametrize('failure', ['pending', 'missing_rule', 'changed_rule'])
@pytest.mark.parametrize('fresh',[False,True])
def test_derived_rebuild_refuses_incomplete_or_changed_eco(tmp_path, failure, fresh):
    import cec_interface_eco as eco
    import json
    board=tmp_path/'derived.kicad_pcb'; board.write_text('native fixture bytes')
    rule=board.with_suffix('.kicad_dru'); rule.write_text('(version 1)')
    row={'output_sha256':eco.sha(board),'route_authority_invalidated':True,
         'design_rule_hashes':{'.kicad_dru':eco.sha(rule)}}
    board.with_suffix('.interface-eco.json').write_text(json.dumps(row))
    if failure=='pending': board.with_suffix('.interface-eco.pending.json').write_text('{}')
    elif failure=='missing_rule': rule.unlink()
    else: rule.write_text('changed rules')
    with pytest.raises(pipeline.PipelineBlocked):
        requested(input_board=board, fresh_placement_only=fresh, allow_derived_input=True)


def test_explicit_fresh_geometry_rebuild_normalizes_selected_derived_source_not_staging(tmp_path):
    source=tmp_path/'selected.kicad_pcb';source.write_text('selected current geometry')
    staging=tmp_path/'manifest.kicad_pcb';staging.write_text('older larger staging seed')
    before=source.read_bytes(),staging.read_bytes()
    assert requested(input_board=source,canonical_board=staging,allow_derived_input=True)
    assert not requested(input_board=source,canonical_board=staging,
                         allow_derived_input=True,replace_placement=False)
    with pytest.raises(pipeline.PipelineBlocked):
        requested(input_board=source,canonical_board=staging,allow_derived_input=False)
    assert (source.read_bytes(),staging.read_bytes())==before
