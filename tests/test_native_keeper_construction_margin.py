"""Native construction margin is new copper, never a loss or spill tolerance."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_rectilinear_copper as owner
import cec_native_keeper_extension_receiving as receiving
import cec_native_keeper_extension_stage as stage
from test_native_keeper_independent_group import board_case


@pytest.mark.parametrize('angle', [0,90,180,270])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('margin', [1000,3000,5000])
def test_actual_native_margin_is_derived_saved_and_independently_replayed(tmp_path,angle,layer,margin):
    b,t,z,kwargs=board_case(angle=angle,layer=layer)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source);original=source.read_bytes()
    plan=receiving.plan(b,[force._uid(t)],**kwargs,retain_existing_keeper_group=True,
        envelope_margin_nm=margin)
    assert plan['envelope_margin_nm']==margin
    small=receiving.plan(b,[force._uid(t)],**kwargs,retain_existing_keeper_group=True,
        envelope_margin_nm=1)
    assert plan['polygon_nm']!=small['polygon_nm']
    child=force._copy_family(source,tmp_path/'child');c=pcbnew.LoadBoard(str(child))
    ids=[force._uid(t)];zid=force._uid(z)
    made=owner.materialize(c,plan,allow_locked_track_uuids=ids,
        allow_grouped_track_uuids=ids,allow_grouped_zone_uuids=[zid])
    owner.fill(c,plan,zid,regional_source=pcbnew.LoadBoard(str(source)))
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    proof=receiving.receive_literal_phase(source,child,[dict(plan=plan,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['every_source_conductor_and_original_keeper_fill_retained']
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('margin', [0,-1,True,1.5,100001,float('nan')])
def test_invalid_margin_refuses_before_native_mutation_or_stage_output(tmp_path,margin):
    b,t,z,kwargs=board_case();source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source);original=source.read_bytes()
    with pytest.raises(ValueError,match='construction_margin'):
        receiving.plan(b,[force._uid(t)],**kwargs,envelope_margin_nm=margin)
    out=tmp_path/'stage'
    with pytest.raises(ValueError):
        stage.run(source,out,board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=tmp_path/'native',envelope_margin_nm=margin)
    assert not out.exists() and source.read_bytes()==original
