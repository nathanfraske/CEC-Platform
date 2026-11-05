"""Body-guide projection never substitutes a body for a manufacturing court."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_dense_reference_mapping as dense
import cec_mask_search_reference_mapping as maps
import cec_reference_map_material_identity as identity
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def case(tmp_path, *, back=False, quarter=0):
    b=_board([],edge=(15,15,25,25));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    library=Path(__file__).resolve().parents[1]/'lib/vendor/Resistor_SMD.pretty'
    fp=pcbnew.FootprintLoad(str(library),'R_0402_1005Metric');assert fp is not None
    b.Add(fp);fp.SetReference('Z91');fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    if back:fp.Flip(fp.GetPosition(),False)
    fp.SetOrientationDegrees(quarter*90)
    fp.Reference().SetVisible(True);fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    fp.Reference().SetTextThickness(150000)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    report=tmp_path/'native.json'
    force._write(report,dict(violations=[dict(type='silk_overlap',severity='warning',
        items=[dict(uuid=force._uid(fp.Reference()))])],unconnected_items=[]))
    # Synthetic discovery only; the saved board/native identity is real.
    producer=dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False),
        report=str(report),report_sha256=force._hash(report),source_files={str(source):force._hash(source)})
    grade=tmp_path/'grade.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(source=dict(sha256=force._hash(source),native_producer=producer))))
    return source,grade,force._uid(fp)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_native_fab_rectangle_is_exact_readable_received_and_not_assembly_authority(tmp_path,back,quarter):
    source,grade,owner=case(tmp_path,back=back,quarter=quarter)
    original=source.read_bytes();b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    body=dense.guide_body(fp,True);court=dense.court(fp)
    assert court.covers(body) and body.area<court.area
    q=maps.plan(source,grade=grade,board_hint='arbitrary',maximum_components=1,
        owner_uuid_scope=[owner],reverse_ownership='rigid_root_group_per_component',
        via_ink_policy='native_mask_and_bore',peripheral_reverse_seats=True,
        interrupt_projected_body_guides=True,project_native_fab_body=True)
    assert q['project_native_fab_body']is True
    assert all(r['projection_geometry']=='exact_source_fab_body_not_manufacturing_courtyard'
        and r['full_fab_and_actual_courtyard_and_functional_marks_unchanged']is True
        for r in q['records'])
    assert all(not r.get('leader_xy_mm')or
        [round(v*1e6)for v in r['leader_xy_mm'][0]]!=[round(v*1e6)for v in r['leader_xy_mm'][1]]
        for r in q['records'])
    child=force._copy_family(source,tmp_path/'private');maps.write_private(source,child,q)
    received=maps.receive(source,child,q);assert received['ok']and received['complete'],received
    qpath=tmp_path/'proposal.json';force._write(qpath,q)
    if q['mode']=='opposite_face_projected_courtyard':
        proof=identity.receive(source,child,qpath);assert proof['ok']and proof['same_material'],proof
    saved=pcbnew.LoadBoard(str(child));peer=next(iter(saved.GetFootprints()))
    assert dense.court(peer).equals(court)and dense.guide_body(peer,True).equals(body)
    assert field._field_snapshot_inventory(b)==field._field_snapshot_inventory(saved)
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['empty','extra','filled','noncardinal','outside','arc'])
def test_unknown_or_functionally_ambiguous_fab_geometry_cannot_be_guessed(tmp_path,fault):
    source,_,_=case(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    shape=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_SHAPE'and g.GetLayer()==pcbnew.F_Fab)
    if fault=='empty':fp.Remove(shape)
    elif fault=='extra':
        extra=pcbnew.PCB_SHAPE(fp);extra.SetShape(pcbnew.SHAPE_T_SEGMENT);extra.SetLayer(pcbnew.F_Fab)
        extra.SetStart(pcbnew.VECTOR2I_MM(20,20));extra.SetEnd(pcbnew.VECTOR2I_MM(20.1,20.1));fp.Add(extra)
    elif fault=='filled':shape.SetFillMode(pcbnew.FILL_T_FILLED_SHAPE)
    elif fault=='noncardinal':fp.SetOrientationDegrees(45)
    elif fault=='outside':shape.Move(pcbnew.VECTOR2I_MM(10,0))
    else:shape.SetShape(pcbnew.SHAPE_T_ARC)
    with pytest.raises(ValueError):dense.guide_body(fp,True)


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_fab_body_policy_is_explicit_not_an_inward_courtyard_waiver(tmp_path,value):
    source,grade,_=case(tmp_path)
    with pytest.raises(ValueError,match='explicit_native_fab_body_projection'):
        maps.plan(source,grade=grade,board_hint='arbitrary',project_native_fab_body=value)


def test_full_fab_outline_and_manufacturing_court_are_not_mutation_authority(tmp_path):
    source,grade,owner=case(tmp_path)
    q=maps.plan(source,grade=grade,board_hint='arbitrary',maximum_components=1,
        owner_uuid_scope=[owner],reverse_ownership='rigid_root_group_per_component',
        project_native_fab_body=True,peripheral_reverse_seats=True)
    child=force._copy_family(source,tmp_path/'private');maps.write_private(source,child,q)
    bad=copy.deepcopy(q);bad['records'][0]['actual_manufacturing_courtyard_xy_mm'][0][0]+=.000001
    assert not maps.receive(source,child,bad)['ok']
    del bad['project_native_fab_body']
    assert not maps.receive(source,child,bad)['ok']
