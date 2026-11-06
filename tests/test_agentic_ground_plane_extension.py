"""Native saved-geometry proof for generic, source-rooted ground extension."""
from copy import deepcopy
from pathlib import Path
import sys
import time
import shutil

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pcbnew
from cec_pipeline import groundplanes as ground

MM = 1000000


def rect(x0, y0, x1, y1):
    return [[int(x*MM), int(y*MM)] for x, y in
            ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]


def fixture(tmp_path, *, cutout=False, foreign=False):
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(net)
    zone = pcbnew.ZONE(board); zone.SetNet(net); zone.SetLayer(pcbnew.F_Cu)
    zone.SetMinThickness(100000)
    rings = [rect(1,1,5,5)] + ([list(reversed(rect(2,2,3,3)))] if cutout else [])
    zone.Outline().Append(ground._poly(rings)); zone.SetLocked(True); board.Add(zone)
    filled=ground._poly(rings); filled.Fracture(False)
    zone.SetFilledPolysList(pcbnew.F_Cu, filled); zone.SetIsFilled(True)
    points=rect(0,0,10,10)
    for a,b in zip(points,points[1:]+points[:1]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(50000);board.Add(edge)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net)
    track.SetStart(pcbnew.VECTOR2I(2000000,3500000));track.SetEnd(pcbnew.VECTOR2I(4000000,3500000))
    track.SetWidth(300000);track.SetLayer(pcbnew.F_Cu);board.Add(track)
    if foreign:
        other = pcbnew.ZONE(board); other.SetNet(net); other.SetLayer(pcbnew.B_Cu)
        other.Outline().Append(ground._poly([rect(1,1,5,5)])); board.Add(other)
        other.SetFilledPolysList(pcbnew.B_Cu, ground._poly([rect(1,1,5,5)])); other.SetIsFilled(True)
    import cec_zone_fill
    selected=pcbnew.ZONES();selected.append(zone)
    cec_zone_fill.compile_selected(board,selected,timeout_s=8.,initialize_selected=True)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    board = pcbnew.LoadBoard(str(source)); zone = list(board.Zones())[0]
    uid = zone.m_Uuid.AsString()
    operation = dict(kind='ground_plane_extension', zone_uuid=uid, outline_nm=rect(1,1,7,5))
    record = ground._plan(board, source, operation, time.monotonic()+8)
    zone.Outline().RemoveAllContours()
    zone.Outline().Append(ground._poly([operation['outline_nm'], *rings[1:]]))
    selected=pcbnew.ZONES();selected.append(zone)
    cec_zone_fill.compile_selected(board,selected,timeout_s=8.,initialize_selected=True)
    candidate = tmp_path/'candidate.kicad_pcb'; pcbnew.SaveBoard(str(candidate), board)
    for suffix in ('.kicad_pro', '.kicad_prl'):
        companion=source.with_suffix(suffix)
        if companion.exists(): shutil.copyfile(companion, candidate.with_suffix(suffix))
    return source, candidate, operation, record


def receive(values):
    return ground.receive(*values, board_hint=None)


@pytest.mark.parametrize('cutout', [False, True])
def test_saved_extension_preserves_source_cutouts_and_locked_geometry(tmp_path, cutout):
    values = fixture(tmp_path, cutout=cutout)
    result = receive(values)
    assert result['ok'] and result['complete']
    assert result['faces'][0]['added_area2_nm2'] > 0
    assert not result['current_qualified'] and not result['release_authority']


@pytest.mark.parametrize('fault', ['detached', 'removed', 'outside', 'cutout', 'foreign', 'unlock', 'settings'])
def test_saved_geometry_and_unowned_authority_refuse(tmp_path, fault):
    values = fixture(tmp_path, cutout=fault=='cutout', foreign=fault=='foreign')
    source, candidate, operation, record = values
    board = pcbnew.LoadBoard(str(candidate)); zone = ground._zone(board, operation['zone_uuid'])
    if fault == 'foreign':
        other = next(z for z in board.Zones() if z.m_Uuid.AsString()!=operation['zone_uuid'])
        other.SetFilledPolysList(pcbnew.B_Cu, ground._poly([rect(1,1,6,5)]))
    elif fault == 'unlock': zone.SetLocked(False)
    elif fault == 'settings': zone.SetMinThickness(110000)
    else:
        rings = {'removed':[rect(1.1,1,7,5)], 'outside':[rect(1,1,8,5)],
                 'cutout':[rect(1,1,7,5)], 'detached':[rect(1,1,5,5)]}[fault]
        shape = ground._poly(rings)
        if fault=='detached': shape.Append(ground._poly([rect(6,1,7,5)]))
        zone.SetFilledPolysList(pcbnew.F_Cu, shape)
    pcbnew.SaveBoard(str(candidate), board)
    with pytest.raises(Exception): receive(values)


@pytest.mark.parametrize('fault', ['extra', 'float', 'unaligned', 'shrink', 'selfcross', 'record'])
def test_exact_operation_and_fresh_record_required(tmp_path, fault):
    values = list(fixture(tmp_path)); op=deepcopy(values[2])
    if fault=='record': values[3]['source_zone_locked']=False
    elif fault=='extra': op['unlock']=True
    elif fault=='float': op['outline_nm'][0][0]=1000000.0
    elif fault=='unaligned': op['outline_nm'][1][1]+=1
    elif fault=='shrink': op['outline_nm']=rect(2,1,7,5)
    else: op['outline_nm']=[op['outline_nm'][i] for i in (0,2,1,3)]
    values[2]=op
    with pytest.raises(Exception): receive(values)


def test_actual_native_constructor_calls_selected_zone_filler(tmp_path, monkeypatch):
    source, _, operation, _ = fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source))
    import cec_zone_fill
    selected=pcbnew.ZONES(); selected.append(ground._zone(board,operation['zone_uuid']))
    cec_zone_fill.compile_selected(board, selected, timeout_s=8., initialize_selected=True)
    pcbnew.SaveBoard(str(source),board)
    board=pcbnew.LoadBoard(str(source))
    seen=[]
    original=cec_zone_fill.compile_selected
    def observed(native, selected, **kwargs):
        seen.append([z.m_Uuid.AsString() for z in selected])
        return original(native, selected, **kwargs)
    monkeypatch.setattr(cec_zone_fill, 'compile_selected', observed)
    record=ground.construct(board, source, operation, board_hint=None, request={'operations':[operation]})
    assert seen == [[operation['zone_uuid']]]
    candidate=tmp_path/'native.kicad_pcb'; pcbnew.SaveBoard(str(candidate),board)
    for suffix in ('.kicad_pro','.kicad_prl'):
        companion=source.with_suffix(suffix)
        if companion.exists(): shutil.copyfile(companion,candidate.with_suffix(suffix))
    result=ground.receive(source,candidate,operation,record,board_hint=None)
    assert result['ok'] and result['faces'][0]['added_area2_nm2']>0


def test_project_companion_tamper_is_independently_refused(tmp_path):
    values=fixture(tmp_path)
    values[0].with_suffix('.kicad_pro').write_text('{"source":true}')
    values[1].with_suffix('.kicad_pro').write_text('{"source":false}')
    with pytest.raises(ValueError, match='project_companions'): receive(values)


def test_non_copper_selected_face_is_not_ignored(tmp_path):
    source, _, operation, _=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source)); zone=ground._zone(board, operation['zone_uuid'])
    layers=zone.GetLayerSet(); layers.AddLayer(pcbnew.F_SilkS); zone.SetLayerSet(layers)
    with pytest.raises(ValueError, match='non_copper'): ground._plan(board, source, operation, time.monotonic()+8)


def test_large_rooted_addition_with_100nm_neck_is_not_native_filler_output(tmp_path):
    values=fixture(tmp_path);source,candidate,operation,record=values
    board=pcbnew.LoadBoard(str(candidate));zone=ground._zone(board,operation['zone_uuid'])
    original=pcbnew.LoadBoard(str(source))
    initial=ground._zone(original,operation['zone_uuid']).GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    substituted=initial.CloneDropTriangulation()
    substituted.BooleanAdd(ground._poly([rect(4.9,2,6.1,2.0001)]))
    substituted.BooleanAdd(ground._poly([rect(6,1,7,5)]))
    substituted.Fracture(False)
    deadline=time.monotonic()+8
    # Preserve every source atom; a large genuinely rooted component still
    # cannot authorize a 100nm neck under the 100000nm source zone setting.
    assert record['source_min_thickness_nm']==100000
    assert ground._difference(initial,substituted,deadline).OutlineCount()==0
    assert ground._difference(substituted,zone.Outline(),deadline).OutlineCount()==0
    assert substituted.OutlineCount()==1
    assert ground._area2(ground._difference(substituted,initial,deadline),deadline)>2*100000**2
    zone.SetFilledPolysList(pcbnew.F_Cu,substituted)
    pcbnew.SaveBoard(str(candidate),board)
    for suffix in ('.kicad_pro','.kicad_prl'):
        if source.with_suffix(suffix).exists():shutil.copyfile(source.with_suffix(suffix),candidate.with_suffix(suffix))
    with pytest.raises(ValueError,match='exact_independent_native_fill'):receive(values)


def test_receiver_independently_refills_only_selected_source_zone(tmp_path,monkeypatch):
    values=fixture(tmp_path,foreign=True);source,_,operation,_=values
    import cec_zone_fill
    native_fill=cec_zone_fill.compile_selected;seen=[]
    def observed(board,selected,**kwargs):
        seen.append((Path(board.GetFileName()),[z.m_Uuid.AsString() for z in selected],kwargs))
        return native_fill(board,selected,**kwargs)
    def forbidden(*args,**kwargs):raise AssertionError('receiver must not call constructor')
    monkeypatch.setattr(ground,'construct',forbidden)
    monkeypatch.setattr(cec_zone_fill,'compile_selected',observed)
    assert receive(values)['ok']
    assert len(seen)==1
    assert seen[0][0]==source and seen[0][1]==[operation['zone_uuid']]
    assert 0<seen[0][2]['timeout_s']<=8 and seen[0][2]['initialize_selected'] is True


def test_independent_native_fill_failure_is_not_skipped(tmp_path,monkeypatch):
    values=fixture(tmp_path)
    import cec_zone_fill
    def failed(*args,**kwargs):raise RuntimeError('independent native fill refused')
    monkeypatch.setattr(cec_zone_fill,'compile_selected',failed)
    with pytest.raises(RuntimeError,match='independent native fill refused'):receive(values)
