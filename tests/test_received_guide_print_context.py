"""Canonical printing needs positive map replay, not closed-body inference."""
import copy
import json
from pathlib import Path
import shutil
import pcbnew
import pytest
from shapely.geometry import box
import cec_nonpolar_print_context as print_op
import cec_mask_search_reference_mapping as maps
import cec_force_current as force
import cec_field_coupling as field
from test_nonpolar_print_context import fixture
from test_interrupted_reference_guides import opening


def case(tmp_path, monkeypatch, *, back=False, turn=0, with_signal=False):
    source,table,ids,library=fixture(tmp_path,monkeypatch,turn=turn,back=back,
        selected_name='R_0402_1005Metric')
    b=pcbnew.LoadBoard(str(source));props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    fp=next(f for f in b.GetFootprints()if force._uid(f)==ids[0]);fp.SetReference('Z91')
    fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1));fp.Reference().SetTextThickness(150000)
    for a,z in zip([(0,0),(60,0),(60,40),(0,40)],[(60,0),(60,40),(0,40),(0,0)]):
        line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.Edge_Cuts)
        line.SetStart(pcbnew.VECTOR2I_MM(*a));line.SetEnd(pcbnew.VECTOR2I_MM(*z));line.SetWidth(50000);b.Add(line)
    opening(b,box(0,0,60,40),pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    if with_signal:
        net=pcbnew.NETINFO_ITEM(b,'/existing_channel');b.Add(net)
        track=pcbnew.PCB_TRACK(b);track.SetNet(net);track.SetStart(pcbnew.VECTOR2I_MM(45,30))
        track.SetEnd(pcbnew.VECTOR2I_MM(46,30));track.SetWidth(200000);track.SetLayer(pcbnew.B_Cu);b.Add(track)
    field._save_field_snapshot(b,source)
    report=tmp_path/'native.json';force._write(report,dict(violations=[dict(type='silk_overlap',
        severity='warning',items=[dict(uuid=force._uid(fp.Reference()))])],unconnected_items=[]))
    producer=dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False),report=str(report),
        report_sha256=force._hash(report),source_files={str(source):force._hash(source)})
    grade=tmp_path/'grade.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(source=dict(sha256=force._hash(source),native_producer=producer))))
    q=maps.plan(source,grade=grade,board_hint='renamed',maximum_components=1,owner_uuid_scope=[ids[0]],
        reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore',
        peripheral_reverse_seats=True,project_native_fab_body=True,interrupt_projected_body_guides=True)
    assert q['mode']=='opposite_face_projected_courtyard'
    qpath=tmp_path/'mapping.json';force._write(qpath,q)
    target=tmp_path/'mapped';shutil.copytree(source.parent,target);mapped=target/source.name
    maps.write_private(source,mapped,q);assert maps.receive(source,mapped,q)['ok']
    declaration=dict(source=dict(path=str(source),sha256=force._hash(source)),
        proposal=dict(path=str(qpath),sha256=force._hash(qpath)))
    options=dict(library_table=table,footprint_ids=['cec-Resistor_SMD:R_0402_1005Metric'],
        expected_instance_uuids=ids,board_hint='renamed')
    return source,mapped,declaration,options


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_actual_received_body_guides_can_survive_complete_canonical_print_replay(tmp_path,monkeypatch,back,turn):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch,back=back,turn=turn)
    before=ancestor.read_bytes();mapped_before=mapped.read_bytes()
    with pytest.raises(ValueError):print_op.plan(mapped,**options)
    q=print_op.plan(mapped,**options,reference_mapping_transition=declaration)
    assert q['reference_mapping_transition']==declaration
    received=[r['source_reference_map']for r in q['records']if r.get('source_reference_map')]
    assert len(received)==1 and received[0]['closed_assembly_body_authority']is False
    artifact=print_op.construct_private(mapped,q,tmp_path/'printed')
    r=print_op.receive(mapped,artifact['candidate'],q)
    assert r['ok']and r['complete'],r
    assert ancestor.read_bytes()==before and mapped.read_bytes()==mapped_before


@pytest.mark.parametrize('fault',['source-sha','proposal-sha','extra-field','callback','missing-source','wrong-source'])
def test_serialized_success_or_wrong_boundary_does_not_authorize_hidden_refs(tmp_path,monkeypatch,fault):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch)
    bad=copy.deepcopy(declaration)
    if fault=='source-sha':bad['source']['sha256']='0'*64
    elif fault=='proposal-sha':bad['proposal']['sha256']='0'*64
    elif fault=='extra-field':bad['ok']=True
    elif fault=='callback':bad={'ok':True,'complete':True,'owner_uuid':'anything'}
    elif fault=='missing-source':bad.pop('source')
    else:bad['source']=dict(path=str(mapped),sha256=force._hash(mapped))
    with pytest.raises(ValueError):print_op.plan(mapped,**options,reference_mapping_transition=bad)


@pytest.mark.parametrize('fault',['pad','fab','field','new-ink'])
def test_received_association_cannot_hide_subsequent_source_mutation(tmp_path,monkeypatch,fault):
    ancestor,mapped,declaration,options=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(mapped));fp=next(f for f in b.GetFootprints()if f.GetReference()=='Z91')
    if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='fab':next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_Fab).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='field':fp.SetValue('forged')
    else:
        g=pcbnew.PCB_TEXT(b);g.SetLayer(pcbnew.B_SilkS);g.SetText('unowned');b.Add(g)
    field._save_field_snapshot(b,mapped)
    with pytest.raises(ValueError):print_op.plan(mapped,**options,reference_mapping_transition=declaration)
