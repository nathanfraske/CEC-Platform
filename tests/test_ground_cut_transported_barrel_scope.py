"""An inner class-width cut root is the actual transported process barrel."""
import copy
import json
import pcbnew
import pytest
import cec_cell_ground_cut_boundaries as ground
import cec_force_current as force
import cec_fr as fr
import cec_field_coupling as field
from cec_native_items import discard_items


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for name in ['GND','RAIL']:board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_BYPASS');fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));board.Add(fp)
    for i,name in enumerate(['GND','RAIL']):
        p=pcbnew.PAD(fp);p.SetNumber(str(i+1));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);p.SetLayerSet(ls)
        p.SetNet(board.FindNet(name));p.SetPosition(pcbnew.VECTOR2I_MM(10,10+i*2));fp.Add(p)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    fr.group_local_pofv_signal_vias(board,[via])
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(via.GetNet());edge.SetWidth(500000);edge.SetLayer(pcbnew.In2_Cu)
    edge.SetStart(via.GetPosition());edge.SetEnd(pcbnew.VECTOR2I_MM(12,10));board.Add(edge)
    fixed=pcbnew.PCB_VIA(board);fixed.SetNet(via.GetNet());fixed.SetPosition(edge.GetEnd())
    fixed.SetWidth(600000);fixed.SetDrill(300000);fixed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(fixed)
    if quarter:
        at=pcbnew.VECTOR2I_MM(15,15);turn=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [fp,*board.GetTracks()]:item.Rotate(at,turn)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    # Explicit saved synthetic geometry context; no current/load authority.
    project=source.with_suffix('.kicad_pro')
    data=json.loads(project.read_text()) if project.exists() else {
        'net_settings':{'classes':[dict(name='Default',track_width=.2,clearance=.2,
            via_diameter=.6,via_drill=.3)],
            'netclass_patterns':[]}}
    settings=data['net_settings'];spec=copy.deepcopy(next(c for c in settings['classes']if c['name']=='Default'))
    spec.update(name='EXPLICIT_SYNTHETIC_GROUND',track_width=.5)
    settings['classes'].append(spec)
    settings['netclass_assignments']=dict(settings.get('netclass_assignments')or{})
    settings['netclass_assignments']['GND']='EXPLICIT_SYNTHETIC_GROUND'
    project.write_text(json.dumps(data))
    a,b=[pcbnew.LoadBoard(str(source))for _ in range(2)]
    owner=b.FindFootprintByReference(fp.GetReference());owner.Move(pcbnew.VECTOR2I_MM(.5,.5))
    moved=next(t for t in b.GetTracks()if force._uid(t)==force._uid(via));moved.Move(pcbnew.VECTOR2I_MM(.5,.5))
    discard_items(b,[t for t in b.GetTracks()if force._uid(t)==force._uid(edge)])
    pad=a.FindFootprintByReference(fp.GetReference()).FindPadByNumber('1')
    proof=dict(uuid=force._uid(via),source_owner_pad_uuids=[force._uid(pad)])
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=ground.row._source_binding(a),retired_track_uuids=[force._uid(edge)],
        poses={fp.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]},
        selected_bypasses={fp.GetReference():{'synthetic_explicit_selected_bypass':True}},device_contracts={})
    return a,b,proposal,proof


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_inner_ground_cut_keeps_verified_transported_source_barrel_context(tmp_path,monkeypatch,quarter,back):
    a,b,p,motion=fixture(tmp_path,monkeypatch,quarter,back)
    before=[ground.row._source_binding(x)for x in(a,b)]
    r=ground.requests(a,b,p,transported_source_barrels=[motion])
    assert len(r)==1
    request=next(iter(r.values()))
    assert request['width_nm']==500000 and request['kind']=='ground_boundary'
    assert request['retained_source_ground_fragment']['whole_original_current_plane_and_saved_partition_receiving_required']
    assert before==[ground.row._source_binding(x)for x in(a,b)]


@pytest.mark.parametrize('fault',['missing','forged_owner','width','drill','group','wrong_pose','foreign','unknown_barrel'])
def test_no_claim_or_dimension_change_can_create_cut_barrel_authority(tmp_path,monkeypatch,fault):
    a,b,p,motion=fixture(tmp_path,monkeypatch);motion=copy.deepcopy(motion)
    via=next(t for t in b.GetTracks()if force._uid(t)==motion['uuid'])
    if fault=='missing':motions=[]
    else:
        motions=[motion]
        if fault=='forged_owner':motion['source_owner_pad_uuids']=['unknown']
        elif fault=='width':via.SetWidth(510000)
        elif fault=='drill':via.SetDrill(310000)
        elif fault=='group':via.GetParentGroup().RemoveItem(via)
        elif fault=='wrong_pose':via.Move(pcbnew.VECTOR2I(1000,0))
        elif fault=='foreign':via.SetNet(b.FindNet('RAIL'))
        elif fault=='unknown_barrel':motion['uuid']='unknown'
    with pytest.raises(ValueError):ground.requests(a,b,p,transported_source_barrels=motions)
