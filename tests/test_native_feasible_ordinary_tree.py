"""Native-feasible component selection, strict geometry and exact rollback."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_native_ordinary_tree as tree
from test_explicit_native_ordinary_work_lease import many_native_ports


def fixture(tmp_path,rotation=0,back=False):
    b,ids,net,pads=many_native_ports()
    def at(point):
        x,y=point.x-15000000,point.y-15000000
        for _ in range(rotation//90):x,y=-y,x
        return pcbnew.VECTOR2I(x+15000000,y+15000000)
    for p in pads:p.SetPosition(at(p.GetPosition()))
    for t in b.GetTracks():
        first,last=at(t.GetStart()),at(t.GetEnd());t.SetStart(first);t.SetEnd(last)
        if back:t.SetLayer(pcbnew.B_Cu if t.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu)
    for first,last in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*first));edge.SetEnd(pcbnew.VECTOR2I_MM(*last));b.Add(edge)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),ids,net


def construct(b,source,ids,**kwargs):
    return tree.construct(b,source,board_hint='synthetic',source_track_uuids=ids,
        maximum_source_tracks=64,maximum_ports=16,timeout_s=10.,per_edge_timeout_s=1.,**kwargs)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_real_native_tree_joins_components_but_never_cuts_or_moves_originals(tmp_path,rotation,back):
    source,b,ids,_=fixture(tmp_path,rotation,back);original=source.read_bytes();before=field._field_snapshot_inventory(b)
    proof=construct(b,source,ids)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['added_track_uuids'] and len(proof['final_native_components']['components'])==1
    # Real retained PTH barrels are not requests for redundant face routes.
    assert len(proof['attempts'])==len(proof['initial_native_components']['components'])-1
    assert not proof['final_native_components']['missing_source_via_face_contacts']
    assert all(field._field_snapshot_inventory(b).get(k)==v for k,v in before.items())
    assert set(ids)<={force._uid(t) for t in b.GetTracks()} and source.read_bytes()==original
    assert not proof['source_cut_authorized'] and not proof['route_admitted'] and not proof['shielding_qualified']
    assert proof['field_search_pruning']['tested_legs']>0 and not proof['no_path_proof']


def test_one_bounded_pair_failure_does_not_poison_other_real_component_bridges(tmp_path,monkeypatch):
    source,b,ids,_=fixture(tmp_path);real=fr._guarded_profiled_lastmile_legs;calls=[]
    def search(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:return None
        return real(*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',search)
    proof=construct(b,source,ids)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['attempts'][0]['status']=='bounded_search_unavailable'
    assert all(call['refinement_grids_mm']==(.2,.1) and callable(call['run_guard']) for call in calls)
    assert not proof['no_path_proof']


@pytest.mark.parametrize('partial',[False,True])
def test_failed_finite_search_rolls_back_real_additions_and_never_claims_no_path(tmp_path,monkeypatch,partial):
    source,b,ids,_=fixture(tmp_path);before=field._field_snapshot_inventory(b);original=source.read_bytes()
    real=fr._guarded_profiled_lastmile_legs;calls=[]
    def search(*args,**kwargs):
        calls.append(1)
        return real(*args,**kwargs) if partial and len(calls)==1 else None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',search)
    proof=construct(b,source,ids,maximum_edge_attempts=2)
    assert not proof['ok'] and not proof['complete'] and proof['errors']
    assert proof['all_proposed_additions_rolled_back_exactly'] and field._field_snapshot_inventory(b)==before
    assert source.read_bytes()==original and not proof['no_path_proof'] and not proof['source_tracks_retired']
    assert len(calls)<=2


def test_untrusted_path_result_cannot_bypass_exact_native_canonical_guards(tmp_path,monkeypatch):
    source,b,ids,_=fixture(tmp_path);before=field._field_snapshot_inventory(b)
    def malformed(board,first,last,width,*args,**kwargs):
        return [(first,first+pcbnew.VECTOR2I(12345,54321),width)]
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',malformed)
    proof=construct(b,source,ids)
    assert not proof['ok'] and not proof['complete'] and proof['all_proposed_additions_rolled_back_exactly']
    assert field._field_snapshot_inventory(b)==before


def test_actual_field_search_prunes_parallel_cross_layer_runs_and_keeps_whole_predicate(tmp_path):
    source,b,ids,old_net=fixture(tmp_path)
    pwm=pcbnew.NETINFO_ITEM(b,'RENAMED_PWM_CONTROL');adc=pcbnew.NETINFO_ITEM(b,'RENAMED_ADC_INPUT')
    b.Add(pwm);b.Add(adc)
    for item in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:
        if str(item.GetNetname())==old_net:item.SetNet(pwm)
    victim=pcbnew.PCB_TRACK(b);victim.SetNet(adc);victim.SetLayer(pcbnew.B_Cu);victim.SetWidth(200000)
    victim.SetStart(pcbnew.VECTOR2I_MM(11.3,20.7));victim.SetEnd(pcbnew.VECTOR2I_MM(17.5,20.7));b.Add(victim)
    assert pcbnew.SaveBoard(str(source),b);b=pcbnew.LoadBoard(str(source))
    proof=construct(b,source,ids)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['field_search_pruning']['conservative_cross_layer_proposal_refusals']>0
    assert not proof['shielding_qualified'] and not proof['route_admitted']
    live={force._uid(t):t for t in b.GetTracks()}
    proposed=[dict(net=str(live[u].GetNetname()),layer=int(live[u].GetLayer()),
        start_nm=list(live[u].GetStart()),end_nm=list(live[u].GetEnd()),width_nm=live[u].GetWidth())
        for u in proof['added_track_uuids']]
    verified=field.assess_proposed_tracks(b,proposed,board_hint='synthetic')
    assert verified['ok'] and verified['complete'],verified


@pytest.mark.parametrize('fault',['changed_source','not_whole_face','locked','group','power_width','lease'])
def test_typed_source_and_mutation_permissions_remain_mandatory(tmp_path,fault):
    source,b,ids,_=fixture(tmp_path)
    if fault=='changed_source':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='not_whole_face':ids=ids[:-1]
    elif fault in ('locked','group','power_width'):
        t=next(t for t in b.GetTracks() if force._uid(t)==ids[0])
        if fault=='locked':t.SetLocked(True)
        elif fault=='group':
            g=pcbnew.PCB_GROUP(b);g.SetName('unrelated-existing-owner');b.Add(g);g.AddItem(t)
        else:
            for item in b.GetTracks():
                if force._uid(item) in ids:item.SetWidth(500000)
        field._save_field_snapshot(b,source)
    before=field._field_snapshot_inventory(b)
    kwargs=dict(maximum_edge_attempts=True) if fault=='lease' else {}
    proof=construct(b,source,ids,**kwargs)
    assert not proof['ok'] and not proof['complete'] and proof['errors']
    assert field._field_snapshot_inventory(b)==before and not proof['route_admitted']


def via_face_fixture(tmp_path,rotation=0,back=False):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'/renamed/scalar');b.Add(net)
    def at(x,y):
        x,y=round(x*1e6)-10000000,round(y*1e6)-10000000
        for _ in range(rotation//90):x,y=-y,x
        return pcbnew.VECTOR2I(x+10000000,y+10000000)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    other=pcbnew.F_Cu if back else pcbnew.B_Cu
    for i,x in enumerate((5,15)):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('J'+str(i+1));b.Add(fp)
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber('1');p.SetNet(net);p.SetPosition(at(x,10))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        p.SetLayerSet(pcbnew.LSET.AllCuMask())
    via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetPosition(at(10,12));via.SetWidth(600000)
    via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via);ids=[]
    points=[(5,10),(5,12),(10,12),(15,12),(15,10)]
    for layer in (face,other):
        for first,last in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(layer);t.SetWidth(200000)
            t.SetStart(at(*first));t.SetEnd(at(*last));b.Add(t)
            if layer==face:ids.append(force._uid(t))
    for first,last in [((0,0),(30,0)),((30,0),(30,30)),((30,30),(0,30)),((0,30),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*first));edge.SetEnd(pcbnew.VECTOR2I_MM(*last));b.Add(edge)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),ids,force._uid(via),int(face)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_native_quotient_cannot_bypass_required_via_face_contact(tmp_path,rotation,back):
    source,b,ids,via,face=via_face_fixture(tmp_path,rotation,back)
    initial=tree.retained_port_components(b,'/renamed/scalar',face,ids)
    assert len(initial['components'])==1 and initial['missing_source_via_face_contacts']==[via]
    before=field._field_snapshot_inventory(b);proof=construct(b,source,ids)
    assert proof['ok'] and proof['complete'],proof['errors']
    final=proof['final_native_components']
    assert len(final['components'])==1 and final['missing_source_via_face_contacts']==[]
    assert final['retained_via_face_contacts'][via]
    assert proof['attempts'][0]['purpose']=='preserve_source_via_face_contact'
    assert all(field._field_snapshot_inventory(b).get(k)==v for k,v in before.items())
    assert not proof['source_tracks_retired'] and not proof['route_admitted']


def test_failed_via_face_repair_rolls_back_even_when_quotient_is_connected(tmp_path,monkeypatch):
    source,b,ids,via,face=via_face_fixture(tmp_path);before=field._field_snapshot_inventory(b)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    proof=construct(b,source,ids)
    assert not proof['ok'] and not proof['complete'] and proof['all_proposed_additions_rolled_back_exactly']
    assert field._field_snapshot_inventory(b)==before and not proof['no_path_proof']


def test_saved_via_face_repair_passes_independent_uncapped_native_drc(tmp_path):
    import json,os
    from pathlib import Path
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    from cec_native_items import discard_items
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('independent uncapped native build required')
    source,b,ids,via,face=via_face_fixture(tmp_path);proof=construct(b,source,ids)
    assert proof['ok'] and proof['complete'],proof['errors']
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
    child=tmp_path/'child.kicad_pcb';field._save_field_snapshot(b,child)
    reports=[]
    for i,path in enumerate((source,child)):
        dest=tmp_path/('drc-'+str(i)+'.json')
        result=native.run(path,dest,reporting_build=Path(build),timeout_s=10.)
        assert result['ok'] and result['complete'] and not result['native_inventory']['potentially_truncated']
        report=json.loads(dest.read_text());assert not report['unconnected_items'];reports.append(report)
    assert not ({admission._canonical_identity(v) for v in reports[1]['violations']}
        -{admission._canonical_identity(v) for v in reports[0]['violations']})
    assert not any(v['type']=='via_dangling' for v in reports[1]['violations'])
