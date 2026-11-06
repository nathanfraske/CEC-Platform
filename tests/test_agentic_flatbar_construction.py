"""Single real-land construction is deterministic, source-bound and unadmitted."""
import json
import uuid

import pytest
from test_agentic_flatbars import pcbnew, flatbars, repack, ROOT, profile, candidate
from test_agentic_bridges import fixture, track, pad


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import cec_force_current as force
    import cec_full_current_planar_reflow as authority
    import cec_fr as fr
    board,nets=fixture()
    anchor=track(board,nets[0],(2,2),(3,2),face=pcbnew.F_Cu)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    p=profile();partpath=ROOT/'experiments/busbars/xfcn-20x3x2.json'
    fp=partpath.parent/(p['footprint']+'.kicad_mod')
    request=dict(part=dict(path=str(partpath),sha256=repack.inspection.sha(partpath)),
        footprint_sha256=repack.inspection.sha(fp),reference='BB1',
        source_track_uuid=str(anchor.m_Uuid.AsString()),candidate=candidate())
    monkeypatch.setattr(force,'_family',lambda *a:'synthetic source family')
    monkeypatch.setattr(authority,'_model',lambda *a:('supply',{},dict(amps=25)))
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda *a,**kw:lambda n:{'clearance':.2})
    return board,nets,source,request


def build(setup, **kwargs):
    board,_,source,request=setup
    return flatbars.construct(board,source,request,board_hint='synthetic',identity='bound construction',**kwargs)


def inventory(board):
    return [(str(i.m_Uuid.AsString()),i.GetClass())
            for i in [*board.GetTracks(),*board.GetDrawings(),
                      *(i for fp in board.GetFootprints() for i in flatbars._footprint_items(fp))]]


def test_construct_single_real_land_without_false_current_or_contact(setup):
    board,_,source,request=setup;before=source.read_bytes();native=inventory(board)
    settings=board.GetDesignSettings().m_MinClearance
    record=build(setup)
    assert source.read_bytes()==before
    fp=board.FindFootprintByReference('BB1');assert fp is not None
    assert str(fp.m_Uuid.AsString())==record['footprint_uuid']
    assert set(record['added_uuids'])=={str(i.m_Uuid.AsString()) for i in flatbars._footprint_items(fp)}
    assert len(record['added_uuids'])==len(set(record['added_uuids']))
    assert set(native).issubset(set(inventory(board)))
    assert board.GetDesignSettings().m_MinClearance==settings
    land=list(fp.Pads());assert len(land)==1
    assert land[0].GetNetname()=='SUPPLY'
    assert set(land[0].GetLayerSet().Seq())=={pcbnew.F_Cu,pcbnew.F_Mask}
    assert not land[0].HasHole() and not list(fp.Zones())
    assert record['source_current_contract']=={'amps':25}
    assert record['source_copper_touches_land'] is False
    assert record['declared_envelope']['height_max_mm']==pytest.approx(2.4)
    assert all(record[k] is False for k in ['routing_admitted','current_qualified',
        'assembly_qualified','height_allocation_qualified','release_authority',
        'native_open_or_DRC_count_known'])


def test_all_child_uuids_are_deterministic_and_collision_rejected(setup):
    board,_,source,request=setup
    first=build(setup)
    other=pcbnew.LoadBoard(str(source))
    second=flatbars.construct(other,source,request,board_hint='synthetic',identity='bound construction')
    assert first['added_uuids']==second['added_uuids']
    collision=pcbnew.LoadBoard(str(source))
    item=next(iter(collision.GetDrawings()))
    item.m_Uuid.Clone(pcbnew.KIID(first['added_uuids'][-1]))
    before=inventory(collision)
    with pytest.raises(ValueError,match='uuid_collision'):
        flatbars.construct(collision,source,request,board_hint='synthetic',identity='bound construction')
    assert inventory(collision)==before


@pytest.mark.parametrize('fault',['extra','bad_part_hash','bad_fp_hash','stale_track',
                                  'via_track','reference','foreign','hole','outside'])
def test_construct_rejects_without_mutating_board_or_source(setup,fault):
    board,nets,source,request=setup
    if fault=='extra': request['guessed_copper']=True
    elif fault=='bad_part_hash': request['part']['sha256']='0'*64
    elif fault=='bad_fp_hash': request['footprint_sha256']='0'*64
    elif fault=='stale_track': request['source_track_uuid']=str(uuid.uuid4())
    elif fault=='via_track':
        via=pcbnew.PCB_VIA(board);via.SetNet(nets[0]);board.Add(via)
        pcbnew.SaveBoard(str(source),board);request['source_track_uuid']=str(via.m_Uuid.AsString())
    elif fault=='reference':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('BB1');board.Add(fp)
    elif fault=='foreign': track(board,nets[1],(20,15),(20,25),face=pcbnew.F_Cu)
    elif fault=='hole': pad(board,nets[0],at=(20,20))
    else: request['candidate']['at_nm']=[0,0]
    before=inventory(board);source_before=source.read_bytes()
    with pytest.raises(ValueError): build(setup)
    assert inventory(board)==before and source.read_bytes()==source_before


def test_retired_source_anchor_can_bind_but_does_not_imply_touch(setup):
    board,_,_,request=setup
    for item in list(board.GetTracks()):board.Remove(item)
    assert build(setup)['source_copper_touches_land'] is False


def test_real_same_net_copper_contact_is_observed_not_admitted(setup):
    board,nets,_,_=setup
    track(board,nets[0],(19,20),(21,20),face=pcbnew.F_Cu)
    record=build(setup)
    assert record['source_copper_touches_land'] is True
    assert record['current_qualified'] is False and record['routing_admitted'] is False


def test_post_add_source_identity_failure_rolls_back_only_new_part(setup,monkeypatch):
    import cec_force_current as force
    board,_,_,_=setup;before=inventory(board);calls=0
    def changed(*args):
        nonlocal calls
        calls+=1
        return 'changed' if calls>=3 else 'synthetic source family'
    monkeypatch.setattr(force,'_family',changed)
    with pytest.raises(ValueError,match='sources_changed'):build(setup)
    assert inventory(board)==before


def test_part_race_is_rejected_before_insertion(setup,monkeypatch):
    board,_,_,request=setup;before=inventory(board)
    original=repack.inspection.sha;seen=0
    def raced(path):
        nonlocal seen
        if str(path)==request['part']['path']:
            seen+=1
            if seen>1:return '0'*64
        return original(path)
    monkeypatch.setattr(repack.inspection,'sha',raced)
    with pytest.raises(ValueError,match='sources_changed'):build(setup)
    assert inventory(board)==before


@pytest.mark.parametrize('fault',['paste','copper_graphic','rotation','cutout'])
def test_hash_bound_but_unsafe_footprint_is_rejected(setup,tmp_path,fault):
    board,_,_,request=setup;p=profile()
    raw=(ROOT/'experiments/busbars'/(p['footprint']+'.kicad_mod')).read_text()
    if fault=='paste':raw=raw.replace('"F.Cu" "F.Mask"','"F.Cu" "F.Mask" "F.Paste"')
    elif fault=='copper_graphic':raw=raw.replace('(layer "F.Fab"))\n  (fp_rect','(layer "F.Cu"))\n  (fp_rect')
    elif fault=='rotation':raw=raw.replace('(pad "1" smd rect (at 0 0)','(pad "1" smd rect (at 0 0 90)')
    else:raw=raw.replace('(layer "F.Fab"))\n  (fp_rect','(layer "Edge.Cuts"))\n  (fp_rect')
    fp=tmp_path/(p['footprint']+'.kicad_mod');fp.write_text(raw)
    partpath=tmp_path/'part.json';partpath.write_text(json.dumps(p))
    request['part']=dict(path=str(partpath),sha256=repack.inspection.sha(partpath))
    request['footprint_sha256']=repack.inspection.sha(fp)
    before=inventory(board)
    with pytest.raises(ValueError):build(setup)
    assert inventory(board)==before
