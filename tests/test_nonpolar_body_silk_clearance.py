"""Optional chip body lines never authorize hiding labels or changing copper."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_nonpolar_body_silk_clearance as silk
import cec_field_coupling as field
import cec_force_current as force


def fixture(tmp_path,kind='C',size='0402_1005',turn=0,back=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    namespace={'C':'Capacitor_SMD','R':'Resistor_SMD'}[kind];name=kind+'_'+size+'Metric'
    fp=pcbnew.FootprintLoad(str(silk.ROOT/'lib/vendor'/(namespace+'.pretty')),name)
    assert fp is not None
    fp.SetFPID(pcbnew.LIB_ID('cec-'+namespace,name));b.Add(fp)
    fp.SetReference('UNRELATED_781');fp.SetValue('retained authored value')
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    body=[g for g in fp.GraphicalItems() if g.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)]
    fp.Reference().SetLayer(body[0].GetLayer());fp.Reference().SetVisible(True)
    fp.Reference().SetPosition(body[0].GetStart());fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    fp.Value().SetLayer(body[1].GetLayer());fp.Value().SetVisible(True)
    fp.Value().SetPosition(body[1].GetStart());fp.Value().SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    net=pcbnew.NETINFO_ITEM(b,'ARBITRARY_CONTROL_NOT_A_BOARD_NAME');b.Add(net)
    for pad in fp.Pads():pad.SetNet(net)
    track=pcbnew.PCB_TRACK(b);track.SetNet(net);track.SetWidth(200000);track.SetLayer(pcbnew.In2_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(3,3));track.SetEnd(pcbnew.VECTOR2I_MM(4,3));b.Add(track)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,force._uid(fp)


def saved(tmp_path,**options):
    source,uid=fixture(tmp_path,**options)
    proposal=json.loads(json.dumps(silk.plan(source,selected_footprint_uuids=[uid],board_hint='opaque')))
    b=silk.construct(source,proposal);candidate=force._copy_family(source,tmp_path/'private')
    field._save_field_snapshot(b,candidate)
    return source,candidate,proposal


@pytest.mark.parametrize('kind,size',[('C','0402_1005'),('C','0603_1608'),('R','0402_1005'),('R','0805_2012')])
@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_symmetric_library_bodies_all_faces_and_rotations(tmp_path,kind,size,turn,back):
    source,candidate,proposal=saved(tmp_path,kind=kind,size=size,turn=turn,back=back)
    digest=force._hash(source);proof=silk.receive(source,candidate,proposal,board_hint='opaque')
    assert proof['ok'] and proof['complete'] and proof['changed'],proof
    assert len(proof['removed_body_graphic_uuids'])==2
    assert proof['all_source_labels_copper_pads_fills_courtyards_fab_drawings_poses_models_and_rules_exact']
    assert not proof['release_authority'] and force._hash(source)==digest
    again=silk.plan(candidate,selected_footprint_uuids=proposal['selected_footprint_uuids'],board_hint='opaque')
    assert not again['records']


@pytest.mark.parametrize('fault',['pad_size','pad_number','drill','shape','dnp','locked_owner','hidden_reference',
    'unknown_id','wrong_namespace','body_width','body_position','extra_marker','filled_body','locked_body','group_body','group_owner'])
def test_source_name_is_not_geometry_or_polarity_authority(tmp_path,fault):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    pad=next(iter(fp.Pads()));body=next(g for g in fp.GraphicalItems() if g.GetLayer()==pcbnew.F_SilkS)
    if fault=='pad_size':pad.SetSize(pcbnew.VECTOR2I(pad.GetSize().x+1,pad.GetSize().y))
    elif fault=='pad_number':pad.SetNumber('3')
    elif fault=='drill':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000))
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='locked_owner':fp.SetLocked(True)
    elif fault=='hidden_reference':fp.Reference().SetVisible(False)
    elif fault=='unknown_id':fp.SetFPID(pcbnew.LIB_ID('cec-Capacitor_SMD','C_Polarized_0402_1005Metric'))
    elif fault=='wrong_namespace':fp.SetFPID(pcbnew.LIB_ID('Unreviewed','C_0402_1005Metric'))
    elif fault=='body_width':body.SetWidth(body.GetWidth()+1)
    elif fault=='body_position':body.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_marker':
        marker=pcbnew.PCB_SHAPE(fp);marker.SetLayer(pcbnew.F_SilkS);marker.SetShape(pcbnew.SHAPE_T_CIRCLE)
        marker.SetWidth(120000);marker.SetStart(pcbnew.VECTOR2I_MM(21,21));marker.SetEnd(pcbnew.VECTOR2I_MM(21.2,21));fp.Add(marker)
    elif fault=='filled_body':body.SetShape(pcbnew.SHAPE_T_RECT);body.SetFilled(True)
    elif fault=='locked_body':body.SetLocked(True)
    else:
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(body if fault=='group_body' else fp)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):silk.plan(source,selected_footprint_uuids=[uid],board_hint='opaque')


@pytest.mark.parametrize('fault',['text','font','visibility','text_pose','text_layer','pose','pad','courtyard',
    'fab','body_addition','track_width','track_delete','copper_addition','value','outline'])
def test_saved_native_receiving_refuses_every_unowned_change(tmp_path,fault):
    source,candidate,proposal=saved(tmp_path);b=pcbnew.LoadBoard(str(candidate));fp=next(iter(b.GetFootprints()))
    track=next(iter(b.GetTracks()))
    if fault=='text':fp.Reference().SetText('changed')
    elif fault=='font':fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault=='visibility':fp.Value().SetVisible(False)
    elif fault=='text_pose':fp.Reference().Move(pcbnew.VECTOR2I(1,0))
    elif fault=='text_layer':fp.Value().SetLayer(pcbnew.F_Fab)
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault in ('courtyard','fab'):
        next(g for g in fp.GraphicalItems() if g.GetLayer()==(pcbnew.F_CrtYd if fault=='courtyard' else pcbnew.F_Fab)).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='body_addition':
        marker=pcbnew.PCB_SHAPE(fp);marker.SetLayer(pcbnew.F_SilkS);marker.SetShape(pcbnew.SHAPE_T_SEGMENT)
        marker.SetWidth(120000);marker.SetStart(pcbnew.VECTOR2I_MM(21,21));marker.SetEnd(pcbnew.VECTOR2I_MM(21.2,21));fp.Add(marker)
    elif fault=='track_width':track.SetWidth(track.GetWidth()+1)
    elif fault=='track_delete':b.Remove(track)
    elif fault=='copper_addition':
        added=pcbnew.PCB_TRACK(b);added.SetWidth(200000);added.SetLayer(pcbnew.F_Cu)
        added.SetStart(pcbnew.VECTOR2I_MM(3,4));added.SetEnd(pcbnew.VECTOR2I_MM(4,4));b.Add(added)
    elif fault=='value':fp.SetValue('changed')
    else:
        edge=pcbnew.PCB_SHAPE(b);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetWidth(100000);edge.SetStart(pcbnew.VECTOR2I_MM(0,0));edge.SetEnd(pcbnew.VECTOR2I_MM(1,0));b.Add(edge)
    field._save_field_snapshot(b,candidate)
    proof=silk.receive(source,candidate,proposal,board_hint='opaque')
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('options',[{'selected_footprint_uuids':[]},{'selected_footprint_uuids':['x','x']},
    {'selected_footprint_uuids':['x']*9},{'selected_footprint_uuids':True},{'board_hint':''},{'board_hint':True},
    {'timeout_s':True},{'timeout_s':0},{'timeout_s':11},{'timeout_s':float('nan')}])
def test_invalid_scope_and_deadline_refuse_before_source_io(options):
    args=dict(selected_footprint_uuids=['x'],board_hint='opaque');args.update(options)
    with pytest.raises(ValueError):silk.plan('missing',**args)


@pytest.mark.parametrize('fault',['source_hash','graphics','fields','library_hash','scope'])
def test_forged_plan_is_not_retirement_authority(tmp_path,fault):
    source,candidate,proposal=saved(tmp_path);forged=copy.deepcopy(proposal)
    if fault=='source_hash':forged['source_sha256']='0'*64
    elif fault=='graphics':forged['records'][0]['graphic_uuid']='unknown'
    elif fault=='fields':forged['records'][0]['colliding_authored_field_uuids']=[]
    elif fault=='library_hash':forged['input_sha256']={}
    else:forged['selected_footprint_uuids']=['unknown']
    with pytest.raises(ValueError):silk.construct(source,forged)
    assert not silk.receive(source,candidate,forged,board_hint='opaque')['ok']


def test_clear_source_body_does_not_get_repair_credit(tmp_path):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(20,16));fp.Value().SetPosition(pcbnew.VECTOR2I_MM(20,24))
    field._save_field_snapshot(b,source)
    proposal=silk.plan(source,selected_footprint_uuids=[uid],board_hint='opaque')
    assert not proposal['records']
