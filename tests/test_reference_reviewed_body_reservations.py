"""Reviewed body obstacles permit labels, not missing-court/overlap waivers."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_additive_route_receiving as ast
import cec_reference_field_seating as seats
import cec_qualified_courtyard_restore as court
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture

CONTRACT='TI-RUX0012A-courtyard-v1'


def with_remote_missing_body(tmp_path,*,back=False,fault=None):
    source,grade,uid=fixture(tmp_path,roomy=True)
    board=pcbnew.LoadBoard(str(source))
    part=pcbnew.FootprintLoad(str(court.ROOT/'lib/vendor/Package_DFN_QFN.pretty'),'RUX0012A')
    part.SetFPID(pcbnew.LIB_ID('cec-Package_DFN_QFN','RUX0012A'))
    part.SetValue('TPS2121RUXR');part.SetReference('U_REMOTE');board.Add(part)
    for graphic in list(part.GraphicalItems()):
        if int(graphic.GetLayer())in court.COURTS:part.Remove(graphic)
    part.SetPosition(pcbnew.VECTOR2I_MM(49,49))
    if back:part.Flip(part.GetPosition(),False)
    if fault=='value':part.SetValue('UNREVIEWED-PART')
    elif fault=='land':next(iter(part.Pads())).SetSize(pcbnew.VECTOR2I(999999,999999))
    elif fault=='partial':
        line=pcbnew.PCB_SHAPE(part);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
        line.SetWidth(50000);line.SetStart(pcbnew.VECTOR2I_MM(48,48));line.SetEnd(pcbnew.VECTOR2I_MM(49,48));part.Add(line)
    field._save_field_snapshot(board,source)
    data=json.loads(grade.read_text());row=data['boards']['candidate']
    row['sha256']=force._hash(source);row['native_producer']['source_files']={str(source):force._hash(source)}
    force._write(grade,data)
    return source,grade,uid,force._uid(part)


def test_remote_missing_reviewed_body_is_reserved_but_never_added_to_candidate(tmp_path):
    source,grade,uid,remote=with_remote_missing_body(tmp_path)
    before=source.read_bytes()
    with pytest.raises(ValueError,match='closed_source_courtyard'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend')
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',
        reviewed_courtyard_contract_ids=[CONTRACT])
    assert [r['footprint_uuid']for r in q['records']]==[uid]
    proof=q['reviewed_body_reservations'][0]
    assert proof['contract_id']==CONTRACT and proof['records'][0]['footprint_uuid']==remote
    assert proof['input_sha256'] and not proof['release_authority']
    child=force._copy_family(source,tmp_path/'private')
    seats.write_private(source,child,json.loads(json.dumps(q)))
    r=seats.receive(source,child,q);assert r['ok']and r['complete'],r
    assert source.read_bytes()==before
    old,new=ast._nodes(source)[1],ast._nodes(child)[1]
    assert old[remote]==new[remote]
    saved=pcbnew.LoadBoard(str(child));owner=next(fp for fp in saved.GetFootprints()if force._uid(fp)==remote)
    assert not [g for g in owner.GraphicalItems()if int(g.GetLayer())in court.COURTS]
    assert q['reviewed_bodies_are_obstacles_only_not_source_courtyard_or_overlap_admission']


@pytest.mark.parametrize('fault',['value','land','partial'])
def test_reviewed_label_context_never_guesses_wrong_part_lands_or_partial_courtyard(tmp_path,fault):
    source,grade,_,_=with_remote_missing_body(tmp_path,fault=fault)
    before=source.read_bytes()
    with pytest.raises(ValueError):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',
            reviewed_courtyard_contract_ids=[CONTRACT])
    assert source.read_bytes()==before


def test_unknown_body_on_other_face_does_not_block_unchanged_front_policy(tmp_path):
    source,grade,_,_=with_remote_missing_body(tmp_path,back=True,fault='value')
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend')
    assert q['records']and q['reviewed_body_reservations']==[]


@pytest.mark.parametrize('ids',[None,'a',[''],[True],[CONTRACT,CONTRACT],list(map(str,range(9)))])
def test_only_explicit_finite_distinct_contract_ids_are_accepted(tmp_path,ids):
    source,grade,_=fixture(tmp_path,roomy=True)
    with pytest.raises(ValueError,match='bounded_explicit_reviewed'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',reviewed_courtyard_contract_ids=ids)


@pytest.mark.parametrize('fault',['envelope','input_hash','source_hash','omit_contract','opaque_reservation'])
def test_json_reservations_are_rederived_not_external_envelope_authority(tmp_path,fault):
    source,grade,_,_=with_remote_missing_body(tmp_path)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',reviewed_courtyard_contract_ids=[CONTRACT])
    bad=copy.deepcopy(q);body=bad['reviewed_body_reservations'][0]
    if fault=='envelope':body['records'][0]['world_points_nm'][0][0]+=1
    elif fault=='input_hash':body['input_sha256'][next(iter(body['input_sha256']))]='0'*64
    elif fault=='source_hash':body['source_sha256']='0'*64
    elif fault=='omit_contract':bad['request']['reviewed_courtyard_contract_ids']=[]
    else:bad['reviewed_body_reservations'].append({'external_success':True})
    with pytest.raises(ValueError):seats.construct(source,bad)


def test_changed_manufacturer_evidence_is_not_label_obstacle_authority(tmp_path,monkeypatch):
    source,grade,_,_=with_remote_missing_body(tmp_path)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',reviewed_courtyard_contract_ids=[CONTRACT])
    dependencies=q['reviewed_body_reservations'][0]['input_sha256'];target=next(p for p in dependencies if p.endswith('.pdf'))
    original=force._hash
    monkeypatch.setattr(force,'_hash',lambda p:'0'*64 if str(Path(p).resolve())==target else original(p))
    with pytest.raises(ValueError,match='evidence_changed'):seats.construct(source,q)
