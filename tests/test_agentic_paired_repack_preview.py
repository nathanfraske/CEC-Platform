"""Mechanical proposals must never mutate or masquerade as routed boards."""
import copy
import json
import os

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew

from cec_pipeline import repack
from test_native_assembly_translation import fixture, board_with_body


def request_at(tmp_path, x=4_000_000):
    carrier, cover, contract = fixture()
    request = {'schema': 1}
    for side, board in [('carrier', carrier), ('cover', cover)]:
        path = tmp_path / (side+'.kicad_pcb')
        pcbnew.SaveBoard(str(path), board)
        request[side] = dict(path=str(path), sha256=repack.inspection.sha(path), poses=[])
    request['carrier']['poses'] = [dict(reference='arbitrary-mover',
                                       at_nm=[x, 5_000_000], rotation_deg=0)]
    path = tmp_path / 'contract.json'
    path.write_text(json.dumps(contract))
    request['contract'] = dict(path=str(path), sha256=repack.inspection.sha(path))
    return request


def test_preview_is_read_only_and_never_routing_admission(tmp_path):
    request = request_at(tmp_path); original = copy.deepcopy(request)
    result, data = repack.preview(request)
    assert result['placement_screen_ok'] and result['source_unchanged']
    for field in ('routing_admitted','pcb_files_modified','BOM_changed',
                  'native_DRC_run','electrical_or_current_qualified','release_authority'):
        assert result[field] is False
    assert request == original
    for side in ('carrier','cover','contract'):
        assert repack.inspection.sha(request[side]['path']) == request[side]['sha256']
    assert data['moved'] == [['arbitrary-mover'], []]


def test_paired_vent_failure_cannot_pass_placement_screen(tmp_path):
    result, _ = repack.preview(request_at(tmp_path, 6_250_000))
    assert result['source_assembly_screen_ok']
    assert not result['placement_screen_ok']
    assert result['after']['violations']


@pytest.mark.parametrize('value',[None, False, 0, {}, ''])
def test_falsey_nonlist_poses_are_not_empty_scope(tmp_path,value):
    request=request_at(tmp_path);request['cover']['poses']=value
    with pytest.raises(ValueError,match='pose_lists'):
        repack.preview(request)


@pytest.mark.parametrize('mutation', ['schema','hash','unknown','no_motion','large','angle'])
def test_invalid_requests_fail_closed(tmp_path,mutation):
    request=request_at(tmp_path);pose=request['carrier']['poses'][0]
    if mutation=='schema':request['schema']=True
    elif mutation=='hash':request['carrier']['sha256']='0'*64
    elif mutation=='unknown':pose['reference']='nonexistent'
    elif mutation=='no_motion':pose['at_nm']=[5_000_000,5_000_000]
    elif mutation=='large':pose['at_nm']=[70_000_000,5_000_000]
    else:pose['rotation_deg']=45
    with pytest.raises(ValueError):repack.preview(request)


def test_same_face_test_checks_actual_moved_courtyards():
    board=board_with_body('one','low-package',(5,5))
    other=board_with_body('two','low-package',(5.5,5))
    fp=other.FindFootprintByReference('two').Duplicate(False);board.Add(fp)
    result=repack._same_face(board,{'one'},set())
    assert not result['ok'] and result['conflicts'][0]['references']==['one','two']
    assert repack._same_face(board,set(),set())['ok']


@pytest.mark.parametrize('target',['contract','request','hardlink','symlink','board'])
def test_output_cannot_overwrite_sources_or_aliases(tmp_path,target):
    request=request_at(tmp_path);request_path=tmp_path/'request.json'
    request_path.write_text(json.dumps(request))
    if target=='contract':output=tmp_path/'contract.json'
    elif target=='request':output=request_path
    elif target=='board':output=tmp_path/'carrier.kicad_pcb'
    else:
        output=tmp_path/'alias.json';source=tmp_path/'carrier.kicad_pcb'
        if target=='hardlink':os.link(source,output)
        else:output.symlink_to(source)
    with pytest.raises(ValueError):repack._outputs(request_path,request,output)
    assert repack.inspection.sha(request['carrier']['path'])==request['carrier']['sha256']


def test_plot_uses_arbitrary_board_bounds_and_no_fixed_project_label(tmp_path):
    pytest.importorskip('matplotlib')
    result,data=repack.preview(request_at(tmp_path));output=tmp_path/'study.png'
    repack.plot(data,output)
    assert output.stat().st_size>1000


def test_report_and_image_cannot_alias_each_other(tmp_path):
    request=request_at(tmp_path);report=tmp_path/'report.json';plot=tmp_path/'plot.png'
    report.write_text('{}');os.link(report,plot)
    with pytest.raises(ValueError,match='distinct_preview_output_files'):
        repack._outputs(tmp_path/'request.json',request,report,plot)


def test_expired_preview_does_not_claim_result(tmp_path,monkeypatch):
    request=request_at(tmp_path);times=iter([0.,10.])
    monkeypatch.setattr(repack.time,'monotonic',lambda:next(times))
    with pytest.raises(ValueError,match='time_budget'):repack.preview(request)


def port_fixture(at=(5,5),turn=0):
    board=board_with_body('port','test-side-entry',(5,5))
    fp=board.FindFootprintByReference('port')
    pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetPosition(pcbnew.VECTOR2I_MM(6,5));fp.Add(pad)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
    port=dict(side='carrier',reference='port',footprint='test-side-entry',pad_pair=['1','2'],
              exit_normal='left',mouth_offset_nm=1_000_000,mouth_width_nm=2_000_000,
              allowed_edges=['left','right','top','bottom'],evidence='synthetic geometry')
    from shapely.geometry import box,mapping
    return board,[dict(outline=mapping(box(0,0,20,20)))],port


@pytest.mark.parametrize('at,turn,edge', [((5,19),0,'bottom'),((19,5),90,'right'),
                                       ((5,1),180,'top'),((1,5),270,'left')])
def test_numbered_pad_frame_tracks_rotation_and_real_perimeter(at,turn,edge):
    board,data,port=port_fixture(at,turn)
    row=repack._edge_exits([board],data,[port])[0]
    assert row['edge']==edge and row['ok']
    assert not row['cable_and_tool_access_qualified']


def test_interior_port_and_disallowed_edge_are_caught():
    board,data,port=port_fixture()
    assert not repack._edge_exits([board],data,[port])[0]['ok']
    board,data,port=port_fixture((1,5),270);port['allowed_edges']=['top','right','bottom']
    row=repack._edge_exits([board],data,[port])[0]
    assert row['exits_external_perimeter'] and not row['ok']


def test_internal_hole_is_not_external_edge():
    from shapely.geometry import Polygon,mapping
    board,data,port=port_fixture()
    # A large internal opening contains both mouth and some outward travel.
    data[0]['outline']=mapping(Polygon([(0,0),(20,0),(20,20),(0,20)],
                                        [[(3,4),(8,4),(8,19),(3,19)]]))
    assert not repack._edge_exits([board],data,[port])[0]['ok']


@pytest.mark.parametrize('mutation',['normal','duplicate','pad','dimension','package','back'])
def test_bad_port_binding_refuses_instead_of_guessing(mutation):
    board,data,port=port_fixture();ports=[port]
    if mutation=='normal':port['exit_normal']='guess'
    elif mutation=='duplicate':ports.append(copy.deepcopy(port))
    elif mutation=='pad':port['pad_pair']=['1','absent']
    elif mutation=='dimension':port['mouth_width_nm']=True
    elif mutation=='package':port['footprint']='unknown-package'
    else:board.FindFootprintByReference('port').SetLayer(pcbnew.B_Cu)
    with pytest.raises(ValueError):repack._edge_exits([board],data,ports)
