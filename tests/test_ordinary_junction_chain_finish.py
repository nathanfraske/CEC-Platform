"""Renamed/rotated native chains, never a board-specific repair table."""
import json
import pcbnew
import pytest
import cec_ordinary_junction_chain_finish as op
import cec_ordinary_junction_chain_stage as stage
import cec_force_current as force
import cec_field_coupling as field
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,pattern,quarter=0,mirror=False,face=pcbnew.F_Cu):
    net='/unrelated/LOGIC_CONTROL'
    def point(p):
        x,y=p[0]-25,p[1]-25
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 25+x,25+y
    if pattern=='parallel':
        legs=[((25,20),(25,25)),((25,25),(15,25)),((25.05,20.05),(25.05,25.105))]
        pads=[(25.05,20.05),(15,25),(25.05,25.105)]
    elif pattern=='jog':
        legs=[((15,25),(20,25)),((20,25),(20,25.03)),((20,25.03),(22,27.03))]
        pads=[(15,25),(22,27.03)]
    else:
        legs=[((20,20),(22,22)),((22,22),(21.99,22.01)),((21.99,22.01),(21.6,22.01)),
              ((20,20.41),(21.6,22.01)),((20,20),(20,20.41))]
        pads=[(20,20),(20,20.41)]
    board=_board([(*point(p),net) for p in pads],edge=(0,0,50,50));board.SetCopperLayerCount(6)
    for f in board.GetFootprints():
        for p in f.Pads():
            layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetSize(pcbnew.VECTOR2I(600000,450000))
    for a,b in legs:
        t=track(board,net,point(a),point(b),layer=face,width=.2);t.SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(board,source)
    found=op.discover(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',allow_locked_source=True)
    wanted=[q for q in found['requests'] if
        (pattern=='parallel' and q['mode']=='redundant_cut' and len(q['retired_track_uuids'])==1)
        or (pattern=='jog' and q['mode']=='reflow' and len(q['retired_track_uuids'])==3)
        or (pattern=='loop' and q['mode']=='redundant_cut' and len(q['retired_track_uuids'])==4)]
    assert wanted,found
    return source,wanted[0]


@pytest.mark.parametrize('pattern',['parallel','jog','loop'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_complete_native_source_chain_is_received_after_saved_json_roundtrip(tmp_path,pattern,quarter,mirror,face):
    source,request=fixture(tmp_path,pattern,quarter,mirror,face);before=source.read_bytes()
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    q=json.loads(json.dumps(q,allow_nan=False));b,made=op.construct(q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    proof=op.receive(source,child,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['saved_trace_length_mm']>0 and proof['actual_visible_native_material_removed']['ok']
    assert proof['exact_entire_original_source_reconstruction'] and proof['source_width_face_and_roles_exact']
    assert proof['independent_original_ordinary_receiving']['all_prior_native_terminal_partitions_preserved']
    assert proof['new_holes']==proof['new_vias']==0 and not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==before
    assert all(t.GetWidth()==200000 and t.GetLayer()==face and t.IsLocked() for t in b.GetTracks())


@pytest.mark.parametrize('fault',['width','track_pose','pad_pose','extra_track','extra_via','lost_track','plan_point','plan_role'])
def test_worker_cannot_expand_the_exact_native_source_delta(tmp_path,fault):
    source,request=fixture(tmp_path,'jog');q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    b,made=op.construct(q);t=next(iter(b.GetTracks()))
    if fault=='width':t.SetWidth(199999)
    elif fault=='track_pose':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad_pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_track':
        extra=t.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());b.Add(extra)
    elif fault=='extra_via':
        v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetWidth(600000);v.SetDrill(300000);v.SetPosition(pcbnew.VECTOR2I_MM(25,25));v.SetLayerPair(0,2);b.Add(v)
    elif fault=='lost_track':b.Delete(t)
    elif fault=='plan_point':q['request']['replacement_points_nm'][0][0]+=1
    else:q['request']['net']='+5V'
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,q,board_hint='synthetic')
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('fault',['power','unknown_lock_scope','group','mask','widen','free_angle'])
def test_source_authority_is_not_inferred_from_a_nearby_same_net_body(tmp_path,fault):
    source,request=fixture(tmp_path,'jog');b=pcbnew.LoadBoard(str(source));t=next(iter(b.GetTracks()))
    if fault=='power':
        n=pcbnew.NETINFO_ITEM(b,'+5V');b.Add(n)
        for i in [*b.GetTracks(),*(p for f in b.GetFootprints() for p in f.Pads())]:i.SetNet(n)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g)
        for t in b.GetTracks():g.AddItem(t)
    elif fault=='mask':
        for t in b.GetTracks():t.SetHasSolderMask(True)
    elif fault=='widen':
        for t in b.GetTracks():t.SetWidth(500000)
    elif fault=='free_angle':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(12345,54321))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',request=request,allow_locked_source=fault!='unknown_lock_scope')


@pytest.mark.parametrize('kwargs',[dict(max_trials=0),dict(max_trials=17),dict(max_trials=True),dict(allow_locked_source=1),dict(expected_source_sha256='unbound')])
def test_bad_stage_work_bounds_cannot_create_outputs(tmp_path,kwargs):
    settings=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native');settings.update(kwargs)
    output=tmp_path/'no-output'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',output,**settings)
    assert not output.exists()


@pytest.mark.parametrize('pattern',['parallel','jog','loop'])
def test_saved_plan_binds_companion_appearance_not_only_pcb_bytes(tmp_path,pattern):
    source,request=fixture(tmp_path,pattern)
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    digest=force._hash(source)
    force._write(source.with_suffix('.source-rule.json'),dict(source_owned_authority_changed=True))
    assert force._hash(source)==digest
    with pytest.raises(ValueError,match='stale_or_forged'):
        op.construct(q)
