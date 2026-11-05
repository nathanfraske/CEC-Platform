"""A Source-owned complete post-filter pair is not arbitrary Sense rip-up."""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_measurement_filter_span_reflow as operation
import cec_field_coupling as field
import cec_force_current as force
from test_measurement_filter_span_reflow import fixture as span_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False):
    f,args,_=span_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    def transform(p):
        x,y=p
        if mirror:x=40000000-x
        for _ in range(quarter):x,y=y,40000000-x
        return [x,y]
    incoming=[]
    for net,points in [('negative_input',[(8000000,10000000),(8000000,17000000),(9000000,18000000)]),
            ('negative_input',[(7000000,20000000),(7000000,18000000),(9000000,18000000)])]:
        points=list(map(transform,points))
        for a,z in zip(points,points[1:]):
            track(f['board'],net,tuple(v/1e6 for v in a),tuple(v/1e6 for v in z),width=.25)
    field._save_field_snapshot(f['board'],f['source'])
    for t in f['board'].GetTracks():
        if t.GetNetname()in('positive_input','negative_input'):
            incoming.append(dict(net=t.GetNetname(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
    return f,args,incoming


def saved(tmp_path,monkeypatch,**options):
    f,args,rows=fixture(tmp_path,monkeypatch,**options);q=operation.plan_pair(f['source'],**args)
    assert q==json.loads(json.dumps(q))
    result=operation.write_pair_private(q,tmp_path/'child',rows)
    return f,args,rows,q,Path(result['candidate'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_whole_source_three_land_nodes_native_reconstruction_all_frames(tmp_path,monkeypatch,quarter,mirror):
    f,args,rows,q,child=saved(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    raw=f['source'].read_bytes();proof=operation.receive_pair(f['source'],child,**args)
    assert proof['ok'] and proof['complete'],proof
    assert q['scope']==operation.PAIR_SCOPE and len(q['nodes'])==2
    assert all(len(row['pad_uuids'])==3 for row in q['nodes'].values())
    assert proof['geometry']['each_post_filter_node_whole_native_connected']
    assert proof['original_native_partitions']['preserved'] and proof['exact_saved_subtract_add_refill']['ok']
    assert not any(proof[k]for k in('current_authority','Kelvin_qualified','routing_admitted','release_authority'))
    assert f['source'].read_bytes()==raw


@pytest.mark.parametrize('fault',('extra_pad','via','back_pad','DNP','group','incomplete','mixed_width'))
def test_both_nodes_must_be_complete_positive_front_only_Source_not_just_the_seed(tmp_path,monkeypatch,fault):
    f,args,rows=fixture(tmp_path,monkeypatch);b=f['board'];net='negative_input'
    pads=[p for fp in b.GetFootprints()for p in fp.Pads()if p.GetNetname()==net]
    tracks=[t for t in b.GetTracks()if t.GetNetname()==net]
    if fault=='extra_pad':
        p=pcbnew.PAD(f['owner']);p.SetNumber('99');p.SetNet(pads[0].GetNet())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(pcbnew.VECTOR2I_MM(44,44));f['owner'].Add(p)
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(tracks[0].GetStart());v.SetNet(pads[0].GetNet());v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    elif fault=='back_pad':
        layers=pcbnew.LSET()
        for layer in(pcbnew.B_Cu,pcbnew.B_Paste,pcbnew.B_Mask):layers.AddLayer(layer)
        pads[0].SetLayerSet(layers);pads[0].SetLayer(pcbnew.B_Cu)
    elif fault=='DNP':pads[0].GetParentFootprint().SetDNP(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='incomplete':tracks[0].SetStart(pcbnew.VECTOR2I_MM(45,45))
    else:tracks[0].SetWidth(249999)
    field._save_field_snapshot(b,f['source'])
    with pytest.raises(ValueError):operation.plan_pair(f['source'],**args)


@pytest.mark.parametrize('fault',('width','face','unlock','part','value','extra_track','omit_node','new_via','sidecar'))
def test_saved_ownership_factory_source_process_and_terminal_completion_stay_strict(tmp_path,monkeypatch,fault):
    f,args,rows,q,child=saved(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(child));tracks=list(b.GetTracks())
    if fault=='width':tracks[0].SetWidth(249999)
    elif fault=='face':tracks[0].SetLayer(pcbnew.In2_Cu)
    elif fault=='unlock':tracks[0].SetLocked(not q['nodes'][tracks[0].GetNetname()]['locked'])
    elif fault=='part':b.FindFootprintByReference('arbitrary_input').SetField('MPN','UNKNOWN')
    elif fault=='value':b.FindFootprintByReference('K7').SetValue('1nF')
    elif fault=='extra_track':track(b,'positive_input',(40,40),(41,40),width=.25)
    elif fault=='omit_node':
        from cec_native_items import discard_items
        discard_items(b,[t for t in tracks if t.GetNetname()=='negative_input'])
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(tracks[0].GetStart());v.SetNet(tracks[0].GetNet());v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    else:child.with_suffix('.kicad_pro').write_text('{}')
    if fault!='sidecar':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),b)
    proof=operation.receive_pair(f['source'],child,**args)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def test_geometry_hints_cannot_choose_smaller_dimensions_or_a_force_net(tmp_path,monkeypatch):
    f,args,rows=fixture(tmp_path,monkeypatch);q=operation.plan_pair(f['source'],**args)
    for key,value in(('width_nm',1),('layer',6),('current_a',.001)):
        bad=[dict(row)for row in rows];bad[0][key]=value
        with pytest.raises(ValueError):operation.write_pair_private(q,tmp_path/('bad-'+key),bad)
    bad=[dict(row)for row in rows];bad[0]['net']='force_a'
    with pytest.raises(ValueError):operation.write_pair_private(q,tmp_path/'bad-force',bad)
