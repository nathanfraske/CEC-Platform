"""RF opt-out does not authorize an undersized physical component body."""
import json
from pathlib import Path

import pcbnew
import pytest

import cec_physical_body as body
import cec_field_coupling as field
import cec_placement_geometry as geometry


def _rectangle(fp, layer, xmin, ymin, xmax, ymax):
    for a, b in zip([(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)],
                    [(xmax,ymin),(xmax,ymax),(xmin,ymax),(xmin,ymin)]):
        line=pcbnew.PCB_SHAPE(fp); line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(layer); line.SetWidth(50000)
        line.SetStart(pcbnew.VECTOR2I_MM(*a)); line.SetEnd(pcbnew.VECTOR2I_MM(*b))
        fp.Add(line)


def fixture(tmp_path, monkeypatch, *, cropped=True, rotation=0., flipped=False):
    directory=tmp_path/'fixture.pretty';directory.mkdir()
    library_board=pcbnew.BOARD()
    template=pcbnew.FOOTPRINT(library_board)
    template.SetFPID(pcbnew.LIB_ID('fixture','PADLESS_BODY'))
    _rectangle(template,pcbnew.F_CrtYd,-2.,-6.,2.,3.)
    _rectangle(template,pcbnew.F_SilkS,-2.,-6.,2.,3.)
    for number, x in [(1,-1.),(2,1.)]:
        pad=pcbnew.PAD(template);pad.SetNumber(str(number))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.6));pad.SetPosition(pcbnew.VECTOR2I_MM(x,0.))
        pad.SetLayerSet(pcbnew.PAD.SMDMask());template.Add(pad)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(directory),template)
    path=directory/'PADLESS_BODY.kicad_mod'
    entry=dict(template_path=str(path),template_sha256=body._hash(path),
        nominal_body_mm=[4.,9.],source='https://manufacturer.example/body-geometry')
    catalog={'fixture:PADLESS_BODY':entry}
    monkeypatch.setattr(body,'contracts',lambda:catalog)
    authority=tmp_path/'catalog.json';authority.write_text(json.dumps(catalog))
    monkeypatch.setattr(body,'CATALOG',authority)
    board=pcbnew.BOARD()
    fp=pcbnew.FootprintLoad(str(directory),'PADLESS_BODY')
    fp.SetParent(board)
    fp.SetFPID(pcbnew.LIB_ID('fixture','PADLESS_BODY'));fp.SetReference('RENAMED_DEVICE')
    if cropped:
        for shape in fp.GraphicalItems():
            for get, set_ in [(shape.GetStart,shape.SetStart),(shape.GetEnd,shape.SetEnd)]:
                point=get()
                if point.y < -1000000:
                    point.y=-1000000;set_(point)
    if flipped:fp.Flip(fp.GetPosition(),False)
    fp.SetOrientationDegrees(rotation);fp.SetPosition(pcbnew.VECTOR2I_MM(15.,15.))
    board.Add(fp)
    for a,b in [((0.,0.),(30.,0.)),((30.,0.),(30.,30.)),
                ((30.,30.),(0.,30.)),((0.,30.),(0.,0.))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(50000)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    net=pcbnew.NETINFO_ITEM(board,'UNCHANGED_NET');board.Add(net)
    for pad in fp.Pads():pad.SetNet(net)
    track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.F_Cu);track.SetNet(net)
    track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(2.,2.))
    track.SetEnd(pcbnew.VECTOR2I_MM(3.,2.));board.Add(track)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'meta':{'version':1},'net_settings':{}}))
    return source,board,fp,catalog


@pytest.mark.parametrize('rotation',[0.,90.,180.,270.])
@pytest.mark.parametrize('flipped',[False,True])
def test_cropped_native_envelope_fails_and_body_is_preserved_on_both_sides(
        tmp_path,monkeypatch,rotation,flipped):
    source,board,_,catalog=fixture(tmp_path,monkeypatch,rotation=rotation,flipped=flipped)
    before=body.audit(board,catalog=catalog)
    assert not before['ok'] and before['checked'][0]['missing_area_mm2'] > 19.
    receipt=body.repair_private(source,tmp_path/'private')
    assert receipt['ok'] and receipt['after']['ok']
    assert receipt['exact_independent_reconstruction'] and receipt['copper_or_pose_changes']==0
    assert not receipt['release_authority'] and not receipt['routing_admitted']


def test_correct_body_has_no_repair_and_unregistered_scope_is_not_hidden(tmp_path,monkeypatch):
    source,board,_,catalog=fixture(tmp_path,monkeypatch,cropped=False)
    result=body.audit(board,catalog=catalog)
    assert result['ok'] and not result['violations']
    with pytest.raises(ValueError,match='scope_empty'):
        body.repair_private(source,tmp_path/'private')
    unknown=pcbnew.FOOTPRINT(board);unknown.SetFPID(pcbnew.LIB_ID('fixture','UNREVIEWED'))
    unknown.SetReference('RENAMED_UNKNOWN');board.Add(unknown)
    result=body.audit(board,catalog=catalog)
    assert result['ok'] and not result['coverage_complete']
    assert result['unregistered'][0]['ref']=='RENAMED_UNKNOWN'


@pytest.mark.parametrize('fault',['pose','track','pad_net','rules','graphic','duplicate_uuid'])
def test_independent_receiver_rejects_any_unowned_or_wrong_child_change(tmp_path,monkeypatch,fault):
    source,_,_,_=fixture(tmp_path,monkeypatch)
    result=body.repair_private(source,tmp_path/'private');candidate=Path(result['board'])
    board=pcbnew.LoadBoard(str(candidate));fp=board.FindFootprintByReference('RENAMED_DEVICE')
    if fault=='pose':fp.Move(pcbnew.VECTOR2I_MM(.1,0.))
    elif fault=='track':next(iter(board.GetTracks())).SetWidth(210000)
    elif fault=='pad_net':fp.FindPadByNumber('1').SetNetCode(0)
    elif fault=='rules':candidate.with_suffix('.kicad_pro').write_text('{}')
    elif fault=='graphic':
        shape=next(s for s in fp.GraphicalItems() if s.GetLayer()==pcbnew.F_SilkS)
        shape.Move(pcbnew.VECTOR2I_MM(.1,0.))
    else:
        shapes=list(fp.GraphicalItems());shapes[0].m_Uuid.Clone(shapes[1].m_Uuid)
    if fault!='rules':field._save_field_snapshot(board,candidate)
    with pytest.raises(ValueError,match='not_exact|sidecar_changed|uuid_ambiguous'):
        body.receive(source,candidate)


def test_native_placement_gate_reports_body_error_and_projection_keeps_it(tmp_path,monkeypatch):
    source,_,_,_=fixture(tmp_path,monkeypatch)
    result=geometry.evaluate(source,timeout_s=10)
    assert not result['ok'] and result['assembly_count']==0
    assert result['type_counts']['physical_body_envelope_missing']==1
    projected=geometry.craft_projection(result)
    assert not projected['ok'] and not projected['error']
    assert 'physical_body' in projected['domains']
    assert projected['violations'][0]['domain']=='physical_body'


def test_changed_package_pad_datum_cannot_use_registered_body(tmp_path,monkeypatch):
    _,board,fp,catalog=fixture(tmp_path,monkeypatch)
    fp.FindPadByNumber('1').Move(pcbnew.VECTOR2I_MM(.1,0.))
    with pytest.raises(ValueError,match='datum_mismatch'):
        body.audit(board,catalog=catalog)
