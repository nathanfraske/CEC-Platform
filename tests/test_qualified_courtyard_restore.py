"""Reviewed package geometry restores missing courts, never other CAD data."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_qualified_courtyard_restore as court
import cec_field_coupling as field
import cec_force_current as force

CONTRACT='TI-RUX0012A-courtyard-v1'


def literal_fixture(tmp_path,turn=0,back=False):
    directory=tmp_path/'source-family';directory.mkdir()
    source,b=fixture(directory,turn=turn,back=back);fp=next(iter(b.GetFootprints()))
    text=pcbnew.PCB_TEXT(b);text.SetText('HISTORICAL LABEL');text.SetLayer(pcbnew.B_SilkS)
    text.SetPosition(pcbnew.VECTOR2I_MM(8,8));b.Add(text)
    group=pcbnew.PCB_GROUP(b);group.SetName('historical source group');b.Add(group);group.AddItem(text)
    zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.In2_Cu);zone.SetNet(next(iter(b.GetTracks())).GetNet())
    outline=zone.Outline();outline.NewOutline()
    for x,y in ((1,1),(2,1),(2,2),(1,2)):outline.Append(x*1000000,y*1000000)
    b.Add(zone);zone.SetFilledPolysList(pcbnew.In2_Cu,outline.CloneDropTriangulation());zone.SetIsFilled(True)
    field._save_field_snapshot(b,source)
    # Authored hide placement and unknown-to-the-operator user metadata must
    # remain literal, even if native no-op serialization reorders properties.
    raw=court.literal.raw_text(source);a,z=court.literal.inventory(raw)[force._uid(fp)]
    part=raw[a:z]
    for i,j in court.literal.children(part):
        node=part[i:j]
        if node.startswith('(property "Value"'):
            at=court.literal.children(node,root_end=True)
            # Place hide last, deliberately unlike KiCad's canonical ordering.
            import re
            node=re.sub(r'\(hide\s+(?:yes|no)\)','',node)
            at=court.literal.children(node,root_end=True)
            node=node[:at]+' (hide yes) '+node[at:]
            part=part[:i]+node+part[j:];break
    at=court.literal.children(part,root_end=True)
    extra='(property "CEC historical opaque" "retain exact \\\"escapes\\\"" (at 0 0) (layer "F.Fab") (uuid "'+str(pcbnew.KIID().AsString())+'") (effects (font (size 1 1) (thickness 0.15))) (hide yes))'
    part=part[:at]+extra+'\n'+part[at:];court.literal.write_raw(source,raw[:a]+part+raw[z:])
    return source


@pytest.mark.parametrize('turn,back',[(0,False),(90,True),(45,False),(135,True)])
def test_literal_writer_retains_authored_order_metadata_group_ink_and_fill(tmp_path,turn,back):
    source=literal_fixture(tmp_path,turn,back);before=force._family(source,'opaque')
    q=court.plan(source,contract_id=CONTRACT,board_hint='opaque',literal_source=True)
    child=tmp_path/'private'/'board.kicad_pcb';assert court.write_private(source,child,q)==child
    r=court.receive(source,child,q,board_hint='opaque',literal_source=True)
    assert r['ok']and r['complete'],r
    assert r['exact_whole_literal_source_plus_courtyard_only']
    assert r['independent_actual_source_child_native_replays']==2
    assert force._family(source,'opaque')==before
    assert not r['routing_admitted']and not r['release_authority']


@pytest.mark.parametrize('fault',['opaque','root_ink','group','fill','pad_1nm','pose_1nm','model','court_1nm','normalize'])
def test_literal_receiver_refuses_opaque_and_one_nm_unowned_mutations(tmp_path,fault):
    source=literal_fixture(tmp_path);q=court.plan(source,contract_id=CONTRACT,board_hint='opaque',literal_source=True)
    child=tmp_path/'private'/'board.kicad_pcb';court.write_private(source,child,q)
    if fault=='opaque':court.literal.write_raw(child,court.literal.raw_text(child).replace('retain exact','MODIFIED exact'))
    elif fault=='group':court.literal.write_raw(child,court.literal.raw_text(child).replace('historical source group','modified source group'))
    else:
        b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
        if fault=='root_ink':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='fill':next(iter(b.Zones())).UnFill()
        elif fault=='pad_1nm':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='pose_1nm':fp.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='model':fp.Models()[0].m_Scale.x=2
        elif fault=='court_1nm':next(g for g in fp.GraphicalItems()if int(g.GetLayer())in court.COURTS).Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(b,child)
    r=court.receive(source,child,q,board_hint='opaque',literal_source=True)
    assert not r['ok']and r['errors'],r


def test_literal_writer_requires_explicit_plan_and_rolls_back_failed_proof(tmp_path,monkeypatch):
    source=literal_fixture(tmp_path);q=court.plan(source,contract_id=CONTRACT,board_hint='opaque')
    child=tmp_path/'private'/'board.kicad_pcb'
    with pytest.raises(ValueError,match='explicit_literal'):court.write_private(source,child,q)
    q=court.plan(source,contract_id=CONTRACT,board_hint='opaque',literal_source=True)
    monkeypatch.setattr(court,'receive',lambda *a,**k:{'ok':False,'errors':['independent refusal']})
    with pytest.raises(ValueError,match='receiving_refused'):court.write_private(source,child,q)
    assert not child.exists()and not child.parent.exists()


@pytest.mark.parametrize('fault',['source','rules','code','existing','duplicate_uuid'])
def test_literal_source_epoch_namespace_and_all_literal_ids_are_bound(tmp_path,monkeypatch,fault):
    source=literal_fixture(tmp_path);q=court.plan(source,contract_id=CONTRACT,board_hint='opaque',literal_source=True)
    child=tmp_path/'private'/'board.kicad_pcb'
    if fault=='duplicate_uuid':
        court.write_private(source,child,q)
        text=court.literal.raw_text(child);b=pcbnew.LoadBoard(str(child));fp=next(iter(b.GetFootprints()))
        incoming=next(g for g in fp.GraphicalItems()if int(g.GetLayer())in court.COURTS)
        old=force._uid(incoming);borrowed=force._uid(next(iter(fp.Pads())))
        court.literal.write_raw(child,text.replace(old,borrowed))
        assert not court.receive(source,child,q,board_hint='opaque',literal_source=True)['ok'];return
    if fault=='source':court.literal.write_raw(source,court.literal.raw_text(source)+'\n')
    elif fault=='rules':source.with_suffix('.opaque-history.json').write_text('{"retain":true}')
    elif fault=='code':monkeypatch.setattr(force,'_code_identity',lambda:{'changed':True})
    else:child.parent.mkdir();child.write_bytes(b'pre-existing immutable')
    with pytest.raises(ValueError):court.write_private(source,child,q)
    if fault=='existing':assert child.read_bytes()==b'pre-existing immutable'
    else:assert not child.exists()


def fixture(tmp_path,turn=0,back=False,missing=True):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    fp=pcbnew.FootprintLoad(str(court.ROOT/'lib/vendor/Package_DFN_QFN.pretty'),'RUX0012A')
    fp.SetFPID(pcbnew.LIB_ID('cec-Package_DFN_QFN','RUX0012A'))
    fp.SetReference('arbitrary_slot_'+str(turn));fp.SetValue('TPS2121RUXR')
    if missing:
        for g in list(fp.GraphicalItems()):
            if int(g.GetLayer()) in court.COURTS:fp.Remove(g)
    b.Add(fp)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    net=pcbnew.NETINFO_ITEM(b,'arbitrary_native_net');b.Add(net)
    for pad in fp.Pads():pad.SetNet(net)
    t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.In2_Cu);t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I_MM(4,4));t.SetEnd(pcbnew.VECTOR2I_MM(5,4));b.Add(t)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source))


def saved(tmp_path,**options):
    source,b=fixture(tmp_path,**options);before=force._hash(source)
    plan=court.plan(source,contract_id=CONTRACT,board_hint='opaque')
    child=court.construct(source,plan);candidate=force._copy_family(source,tmp_path/'private')
    field._save_field_snapshot(child,candidate)
    return source,candidate,plan,before


@pytest.mark.parametrize('turn',range(0,360,90))
@pytest.mark.parametrize('back',[False,True])
def test_saved_native_restoration_keeps_all_other_source_evidence(tmp_path,turn,back):
    source,candidate,plan,digest=saved(tmp_path,turn=turn,back=back)
    assert len(plan['records'])==1 and plan['template_local_bounds_nm']==[-1450000,-1700000,1450000,1700000]
    proof=court.receive(source,candidate,plan,board_hint='opaque')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_original_copper_pads_fills_fields_poses_models_and_rules_exact']
    assert proof['independent_native_noop_source_replay_matched']
    assert len(proof['added_courtyard_graphic_uuids'])==4 and digest==force._hash(source)
    assert not proof['fab_ready'] and not proof['routing_admitted'] and not proof['release_authority']


def test_exact_authored_courtyard_is_not_shrunk_to_the_native_drc_cache():
    data,fp,bindings,bounds=court._load(CONTRACT)
    authored=court._contour(fp);fp.BuildCourtyardCaches()
    cached=fp.GetCourtyard(pcbnew.F_Cu).COutline(0)
    cache_points=[tuple(cached.CPoint(i)) for i in range(cached.PointCount())]
    assert sorted(authored)==sorted((x,y) for x in (-1450000,1450000) for y in (-1700000,1700000))
    assert set(cache_points)!=set(authored)
    assert all(bounds[0]<x<bounds[2] and bounds[1]<y<bounds[3] for x,y in cache_points)


@pytest.mark.parametrize('turn',[45,135,225,315])
@pytest.mark.parametrize('back',[False,True])
def test_authored_segments_survive_native_octilinear_footprint_rotation(tmp_path,turn,back):
    source,candidate,plan,digest=saved(tmp_path,turn=turn,back=back)
    proof=court.receive(source,candidate,plan,board_hint='opaque')
    assert proof['ok'],proof
    fp=next(iter(pcbnew.LoadBoard(str(candidate)).GetFootprints()))
    assert court._contour(fp)==tuple(map(tuple,plan['records'][0]['world_points_nm']))


@pytest.mark.parametrize('options',[{'timeout_s':True},{'timeout_s':0},{'timeout_s':11},
    {'timeout_s':float('nan')},{'max_footprints':0},{'max_footprints':65},{'max_footprints':True},
    {'board_hint':''},{'board_hint':True}])
def test_unbounded_or_truthy_work_is_refused_before_source_reads(options):
    args=dict(contract_id=CONTRACT,board_hint='opaque');args.update(options)
    with pytest.raises(ValueError):court.plan('missing',**args)


@pytest.mark.parametrize('identity',[None,True,'','not_a_reviewed_contract'])
def test_arbitrary_unreviewed_contract_does_not_qualify_a_body(identity):
    with pytest.raises(ValueError):court.plan('missing',contract_id=identity,board_hint='opaque')


@pytest.mark.parametrize('fault',['value','number','pad_size','pad_position','attribute','drill','shape','offset'])
def test_qualified_part_and_complete_pad_pattern_cannot_be_inferred_from_name_alone(tmp_path,fault):
    source,b=fixture(tmp_path);fp=next(iter(b.GetFootprints()));pad=next(iter(fp.Pads()))
    if fault=='value':fp.SetValue('unknown_same_package_claim')
    elif fault=='number':pad.SetNumber('999')
    elif fault=='pad_size':pad.SetSize(pcbnew.VECTOR2I(pad.GetSize().x+1,pad.GetSize().y))
    elif fault=='pad_position':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='attribute':pad.SetAttribute(pcbnew.PAD_ATTRIB_CONN)
    elif fault=='drill':pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
    else:pad.SetOffset(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):court.plan(source,contract_id=CONTRACT,board_hint='opaque')


def test_existing_valid_courtyard_is_not_replaced_or_given_restoration_credit(tmp_path):
    source,b=fixture(tmp_path,missing=False);digest=force._hash(source)
    plan=court.plan(source,contract_id=CONTRACT,board_hint='opaque')
    assert not plan['records'] and digest==force._hash(source)


def test_partial_authored_courtyard_is_an_error_not_permission_to_overwrite_it(tmp_path):
    source,b=fixture(tmp_path);fp=next(iter(b.GetFootprints()))
    line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_CrtYd)
    line.SetWidth(50000);line.SetStart(pcbnew.VECTOR2I_MM(18,18));line.SetEnd(pcbnew.VECTOR2I_MM(22,18));fp.Add(line)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='partial_courtyard'):court.plan(source,contract_id=CONTRACT,board_hint='opaque')


@pytest.mark.parametrize('fault',['track_width','track_delete','net','field','pose','new_copper','courtyard_stroke',
    'courtyard_move','courtyard_layer','courtyard_delete','pad','model'])
def test_saved_receiving_refuses_all_unowned_copper_pose_data_and_contour_changes(tmp_path,fault):
    source,candidate,plan,digest=saved(tmp_path);b=pcbnew.LoadBoard(str(candidate));fp=next(iter(b.GetFootprints()))
    line=next(g for g in fp.GraphicalItems() if int(g.GetLayer()) in court.COURTS)
    track=next(iter(b.GetTracks()))
    if fault=='track_width':track.SetWidth(track.GetWidth()+1)
    elif fault=='track_delete':b.Remove(track)
    elif fault=='net':track.SetNetCode(0)
    elif fault=='field':fp.SetValue('changed_value')
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='new_copper':
        added=pcbnew.PCB_TRACK(b);added.SetStart(pcbnew.VECTOR2I_MM(7,7));added.SetEnd(pcbnew.VECTOR2I_MM(8,7))
        added.SetWidth(200000);added.SetLayer(pcbnew.F_Cu);b.Add(added)
    elif fault=='courtyard_stroke':line.SetWidth(49999)
    elif fault=='courtyard_move':line.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='courtyard_layer':line.SetLayer(pcbnew.F_SilkS)
    elif fault=='courtyard_delete':fp.Remove(line)
    elif fault=='pad':
        pad=next(iter(fp.Pads()));pad.SetSize(pcbnew.VECTOR2I(pad.GetSize().x+1,pad.GetSize().y))
    else:fp.Models()[0].m_Scale.x=2.
    field._save_field_snapshot(b,candidate)
    proof=court.receive(source,candidate,plan,board_hint='opaque')
    assert not proof['ok'] and proof['errors'] and digest==force._hash(source)


@pytest.mark.parametrize('fault',['source_hash','points','fp_uuid','inputs','bounds','contract_id'])
def test_forged_or_stale_source_plan_is_not_construction_or_receiving_authority(tmp_path,fault):
    source,candidate,plan,digest=saved(tmp_path);forged=copy.deepcopy(plan)
    if fault=='source_hash':forged['source_sha256']='0'*64
    elif fault=='points':forged['records'][0]['world_points_nm'][0][0]+=1
    elif fault=='fp_uuid':forged['records'][0]['footprint_uuid']='not_native'
    elif fault=='inputs':forged['input_sha256']={}
    elif fault=='bounds':forged['template_local_bounds_nm'][0]+=1
    else:forged['contract_id']='unreviewed'
    with pytest.raises(ValueError):court.construct(source,forged)
    assert not court.receive(source,candidate,forged,board_hint='opaque')['ok']


@pytest.mark.parametrize('fault',['contract_hash','template_hash','evidence_hash','pad_hash','clearance','stroke','grid'])
def test_reviewed_registry_and_geometric_policy_cannot_be_weakened(tmp_path,monkeypatch,fault):
    raw=json.loads((court.ROOT/'lib/vendor-data/footprint-courtyards/TPS2121RUX-courtyard.json').read_text())
    if fault=='template_hash':raw['template']['sha256']='0'*64
    elif fault=='evidence_hash':raw['evidence'][0]['sha256']='0'*64
    elif fault=='pad_hash':raw['template']['pad_geometry_sha256']='0'*64
    elif fault=='clearance':raw['courtyard_clearance_nm']=249999
    elif fault=='stroke':raw['courtyard_stroke_nm']=49999
    elif fault=='grid':raw['courtyard_grid_nm']=20000
    data=tmp_path/'contract.json';force._write(data,raw)
    index=tmp_path/'index.json';force._write(index,dict(schema=1,contracts={CONTRACT:dict(
        path=str(data),sha256='0'*64 if fault=='contract_hash' else force._hash(data))}))
    monkeypatch.setattr(court,'INDEX',index)
    with pytest.raises(ValueError):court._load(CONTRACT)
