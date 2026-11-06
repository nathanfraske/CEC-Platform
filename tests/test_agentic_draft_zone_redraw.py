"""Explicit zone outlines preserve process; stale fill never becomes admission."""
import copy
import json
from pathlib import Path
import uuid

import pytest
from test_agentic_drafts import pcbnew, drafts, ROOT, syntax, echo, bound_request, uid
from test_agentic_bridges import fixture


POLYGON=[[1000000,1000000],[4000000,1000000],[4000000,4000000],[1000000,4000000]]


def zone_fixture():
    board,nets=fixture();zone=pcbnew.ZONE(board)
    zone.SetNet(nets[0]);zone.SetLayer(pcbnew.F_Cu)
    zone.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetLocalClearance(250000);zone.SetMinThickness(200000)
    zone.SetThermalReliefGap(350000);zone.SetThermalReliefSpokeWidth(450000)
    zone.SetAssignedPriority(4);zone.SetLocked(True)
    zone.Outline().NewOutline()
    for x,y in POLYGON:zone.Outline().Append(x,y)
    board.Add(zone)
    return board,zone


def polygon(zone):
    ring=zone.Outline().COutline(0)
    return [[ring.CPoint(i).x,ring.CPoint(i).y] for i in range(ring.PointCount())]


def configuration(zone):
    return (uid(zone),zone.GetNetname(),tuple(zone.GetLayerSet().Seq()),zone.IsLocked(),
        zone.GetFillMode(),zone.GetPadConnection(),zone.GetLocalClearance(),zone.GetMinThickness(),
        zone.GetThermalReliefGap(),zone.GetThermalReliefSpokeWidth(),zone.GetAssignedPriority())


def test_native_zone_configuration_and_identity_are_preserved(tmp_path):
    board,zone=zone_fixture();before=configuration(zone)
    points=[[1000000,1000000],[5000000,1000000],[5000000,4000000],[1000000,4000000]]
    result=drafts._redraw_zones(board,[dict(uuid=uid(zone),polygon_nm=points)])
    assert configuration(zone)==before and polygon(zone)==points and not zone.IsFilled()
    assert result[0]['source_polygon_nm']==POLYGON
    assert result[0]['refill_required'] and result[0]['source_process_preserved']
    assert result[0]['current_qualified'] is False and result[0]['routing_admitted'] is False
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    saved=next(iter(pcbnew.LoadBoard(str(path)).Zones()))
    assert configuration(saved)==before and polygon(saved)==points


@pytest.mark.parametrize('fault',['extra','stale','duplicate','closure','repeated','bool','float',
    'short','oversized','noncanonical','selfcross','zeroarea','group','keepout','thermal','unnamed',
    'holes','multiple_outlines','hatch','noncopper'])
def test_invalid_zone_batch_cannot_partly_mutate(fault):
    board,zone=zone_fixture();edit=dict(uuid=uid(zone),polygon_nm=copy.deepcopy(POLYGON))
    if fault=='extra':edit['net']='OTHER'
    elif fault=='stale':edit['uuid']=str(uuid.uuid4())
    elif fault=='closure':edit['polygon_nm'].append(edit['polygon_nm'][0])
    elif fault=='repeated':edit['polygon_nm'][2]=edit['polygon_nm'][0]
    elif fault=='bool':edit['polygon_nm'][0][0]=True
    elif fault=='float':edit['polygon_nm'][0][0]=1.0
    elif fault=='short':edit['polygon_nm']=POLYGON[:2]
    elif fault=='oversized':edit['polygon_nm']=[[i,0] for i in range(129)]
    elif fault=='noncanonical':edit['polygon_nm'][1]=[5000000,2000000]
    elif fault=='selfcross':edit['polygon_nm']=[POLYGON[i] for i in [0,2,1,3]]
    elif fault=='zeroarea':edit['polygon_nm']=[[0,0],[1,0],[2,0]]
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(zone)
    elif fault=='keepout':zone.SetIsRuleArea(True)
    elif fault=='thermal':zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault=='unnamed':zone.SetNetCode(0)
    elif fault=='holes':
        zone.Outline().NewHole()
        for x,y in [[2000000,2000000],[3000000,2000000],[3000000,3000000]]:
            zone.Outline().Append(x,y,0,0)
    elif fault=='multiple_outlines':
        zone.Outline().NewOutline()
        for x,y in POLYGON:zone.Outline().Append(x+5000000,y)
    elif fault=='hatch':zone.SetFillMode(pcbnew.ZONE_FILL_MODE_HATCH_PATTERN)
    elif fault=='noncopper':zone.SetLayer(pcbnew.F_SilkS)
    # First edit is valid and targets a different zone. Invalid second edit
    # must not UnFill or replace the first outline.
    first=pcbnew.ZONE(board);first.SetNet(board.FindNet('SUPPLY'));first.SetLayer(pcbnew.F_Cu)
    first.SetFillMode(pcbnew.ZONE_FILL_MODE_POLYGONS);first.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    first.Outline().NewOutline()
    for x,y in POLYGON:first.Outline().Append(x,y)
    board.Add(first)
    valid=dict(uuid=uid(first),polygon_nm=[[x+1000000,y] for x,y in POLYGON])
    edits=[edit,copy.deepcopy(edit)] if fault=='duplicate' else [valid,edit]
    before=polygon(first);config=configuration(first)
    with pytest.raises(ValueError):drafts._redraw_zones(board,edits)
    assert polygon(first)==before and configuration(first)==config


@pytest.mark.parametrize('edits',[None,(),{},[None]*33])
def test_zone_batch_is_explicit_and_bounded(edits):
    board,zone=zone_fixture()
    with pytest.raises(ValueError):drafts._redraw_zones(board,edits)
    assert polygon(zone)==POLYGON


def holes(zone):
    outline=zone.Outline();result=[]
    for i in range(outline.HoleCount(0)):
        r=outline.CHole(0,i)
        result.append([[r.CPoint(j).x,r.CPoint(j).y] for j in range(r.PointCount())])
    return result


def add_holes(zone):
    rings=[[[1500000,1500000],[2000000,1500000],[2000000,2000000],[1500000,2000000]],
           [[2500000,2500000],[3000000,2500000],[3000000,3000000],[2500000,3000000]]]
    for index,ring in enumerate(rings):
        zone.Outline().NewHole(0)
        for x,y in ring:zone.Outline().Append(x,y,0,index)
    return rings


def test_explicit_all_holes_survive_native_roundtrip_and_receipt(tmp_path):
    board,zone=zone_fixture();original=add_holes(zone);before=configuration(zone)
    changed=[[[x+100000,y] for x,y in ring] for ring in original]
    record=drafts._redraw_zones(board,[dict(uuid=uid(zone),polygon_nm=POLYGON,holes_nm=changed)])[0]
    assert record['source_holes_nm']==original and record['holes_nm']==changed
    assert holes(zone)==changed and configuration(zone)==before
    path=tmp_path/'with-holes.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    loaded=pcbnew.LoadBoard(str(path));saved=next(iter(loaded.Zones()))
    assert holes(saved)==changed and polygon(saved)==POLYGON and configuration(saved)==before


@pytest.mark.parametrize('fault',['missing','removed','added','touch_outer','outside',
                                  'touch_hole','overlap','noncanonical','selfcross','closure','typed'])
def test_hole_edit_failures_reject_whole_batch(fault):
    board,zone=zone_fixture();original=add_holes(zone)
    edit=dict(uuid=uid(zone),polygon_nm=copy.deepcopy(POLYGON),holes_nm=copy.deepcopy(original))
    if fault=='missing':del edit['holes_nm']
    elif fault=='removed':edit['holes_nm'].pop()
    elif fault=='added':edit['holes_nm'].append(copy.deepcopy(original[0]))
    elif fault=='touch_outer':edit['holes_nm'][0]=[[1000000,1500000],[2000000,1500000],[2000000,2000000],[1000000,2000000]]
    elif fault=='outside':edit['holes_nm'][0]=[[0,0],[500000,0],[500000,500000],[0,500000]]
    elif fault=='touch_hole':edit['holes_nm'][1]=[[2000000,1500000],[2500000,1500000],[2500000,2000000],[2000000,2000000]]
    elif fault=='overlap':edit['holes_nm'][1]=copy.deepcopy(original[0])
    elif fault=='noncanonical':edit['holes_nm'][0][1][1]+=100000
    elif fault=='selfcross':edit['holes_nm'][0]=[original[0][i] for i in [0,2,1,3]]
    elif fault=='closure':edit['holes_nm'][0].append(copy.deepcopy(original[0][0]))
    else:edit['holes_nm']=()
    first=pcbnew.ZONE(board);first.SetNet(board.FindNet('SUPPLY'));first.SetLayer(pcbnew.F_Cu)
    first.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);first.Outline().NewOutline()
    for x,y in POLYGON:first.Outline().Append(x,y)
    board.Add(first);before=polygon(first)
    valid=dict(uuid=uid(first),polygon_nm=[[x+1000000,y] for x,y in POLYGON])
    with pytest.raises(ValueError):drafts._redraw_zones(board,[valid,edit])
    assert polygon(first)==before and holes(zone)==original


def test_no_holes_cannot_silently_acquire_one():
    board,zone=zone_fixture()
    with pytest.raises(ValueError,match='hole_count'):
        drafts._redraw_zones(board,[dict(uuid=uid(zone),polygon_nm=POLYGON,
            holes_nm=[[[1500000,1500000],[2000000,1500000],[2000000,2000000]]])])


def schema5_request():
    value=bound_request();value.update(schema=5,retired_tracks={'carrier':[],'cover':[]},
        flatbars={'carrier':[],'cover':[]},via_copies={'carrier':[],'cover':[]},
        zone_redraws={'carrier':[],'cover':[]})
    plan=json.loads((ROOT/value['placement']['path']).read_text())
    board=pcbnew.LoadBoard(plan['carrier']['path'])
    zone=next(z for z in board.Zones() if uid(z)=='04b1b0ba-5c8d-45df-921a-770a27d15213')
    points=polygon(zone)
    # Shift the first three collinear vertices inward100um, preserving45/cardinal edges.
    points[0][1]+=100000;points[1][1]+=100000;points[2][1]+=100000
    value['zone_redraws']['carrier']=[dict(uuid=uid(zone),polygon_nm=points)]
    return value,plan


def test_zone_edit_requires_refill_before_output_creation(tmp_path,monkeypatch):
    monkeypatch.chdir(ROOT);value,_=schema5_request()
    with pytest.raises(ValueError,match='requires_native_refill'):
        drafts.stage(value,tmp_path/'stale')
    assert not (tmp_path/'stale').exists()


def test_actual_schema5_stage_refills_and_preserves_sources_and_unrelated_nodes(tmp_path,monkeypatch):
    monkeypatch.chdir(ROOT);value,plan=schema5_request()
    sources={s:Path(plan[s]['path']) for s in ('carrier','cover')}
    before={s:path.read_bytes() for s,path in sources.items()}
    result=drafts.stage(value,tmp_path/'zone-draft',refill=True)
    assert result['complete'] and result['source_unchanged']
    assert not result['routing_admitted'] and not result['release_authority']
    for row in result['boards']:
        side=row['side'];assert sources[side].read_bytes()==before[side]
        assert row['native_fill']['stable'] and row['refill_required'] is False
        source=pcbnew.LoadBoard(str(sources[side]));saved=pcbnew.LoadBoard(row['path'])
        assert {str(k):str(v) for k,v in source.GetProperties().asdict().items()}=={
            str(k):str(v) for k,v in saved.GetProperties().asdict().items()}
        expected={r['uuid']:r['polygon_nm'] for r in value['zone_redraws'][side]}
        assert {r['uuid'] for r in row['zone_redraws']}==set(expected)
        for zone in saved.Zones():
            if uid(zone) in expected:
                assert polygon(zone)==expected[uid(zone)]
                original=next(z for z in source.Zones() if uid(z)==uid(zone))
                assert configuration(zone)==configuration(original)
        _,old=syntax._nodes(sources[side]);_,new=syntax._nodes(row['path'])
        changed=set(row['moved_footprint_uuids'])|{r['source_uuid'] for r in row['redraws']}
        changed|={r['uuid'] for r in row['via_moves']}
        changed|={u for r in row['redraws'] for u in r['group_uuids']}
        changed|={uid(z) for z in source.Zones() if not z.GetIsRuleArea()}
        assert all(echo._freeze(old[u])==echo._freeze(new[u]) for u in set(old)-changed)
