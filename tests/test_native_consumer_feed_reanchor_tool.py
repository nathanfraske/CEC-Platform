"""Opaque native input-feed construction and its independently owned delta."""
import json
import pcbnew,pytest
import cec_native_consumer_feed_reanchor as repair
import cec_force_current as force
import cec_field_coupling as field
from test_consumer_branch_reanchor import fixture


def case(tmp_path,monkeypatch,quarter=0,back=False):
    source,unused,b,ids,new=fixture(monkeypatch,tmp_path,angle=90*quarter,mirrored=back)
    b=pcbnew.LoadBoard(str(source))
    for a,z in [((-50,-50),(70,-50)),((70,-50),(70,70)),((70,70),(-50,70)),((-50,70),(-50,-50))]:
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    field._save_field_snapshot(b,source)
    live={force._uid(t):t for t in b.GetTracks()};pads={force._uid(p):p for fp in b.GetFootprints() for p in fp.Pads()}
    args=dict(board_hint='arbitrary',root_pad_uuid=ids['root'],retired_track_uuids=[ids['obsolete']],anchor_uuid=ids['anchor'],
        layer=int(pcbnew.B_Cu if back else pcbnew.F_Cu),launch_uuid=ids['portal'],
        points_nm=[list(live[ids['portal']].GetPosition()),list(pads[ids['anchor']].GetPosition())])
    monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=True,complete=True,synthetic_fixture_only=True))
    return source,args,ids


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_existing_island_terminal_launch_and_one_real_tap_reconstruct_exactly(tmp_path,monkeypatch,quarter,back):
    source,args,ids=case(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes();proposal=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'actual-child');field._save_field_snapshot(repair.construct(source,proposal),child)
    got=repair.receive(source,child,proposal,board_hint='arbitrary')
    assert got['ok'] and got['complete'],got['errors']
    assert got['existing_aggregate_and_input_budgets_exact'] and got['exact_native_source_reconstruction']
    assert got['all_surviving_native_partitions_preserved'] and not got['new_vias'] and not got['pads_moved']
    assert {r['uuid'] for r in got['exact_floor_widenings']}=={ids['exclusive']}
    assert proposal['scope']['budget']['current_authority']['amps']==3.0004
    assert proposal['scope']['budget']['aggregate_current_authority']['amps']==20.
    assert source.read_bytes()==raw and not got['current_or_barrel_qualified'] and not got['release_authority']


@pytest.mark.parametrize('fault',['root','tap_same_as_old','retire_trunk','retire_group','wrong_layer','raw_diagonal',
    'launch_outside_island','launch_point_not_native','unknown_package','extra_load'])
def test_source_typing_and_retained_native_launch_are_mandatory(tmp_path,monkeypatch,fault):
    source,args,ids=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    if fault=='root':args['root_pad_uuid']=ids['anchor']
    elif fault=='tap_same_as_old':args['anchor_uuid']=ids['portal']
    elif fault=='retire_trunk':args['retired_track_uuids'].append(ids['trunk'])
    elif fault=='retire_group':args['retired_track_uuids'].append(force._uid(next(t for g in b.Groups() for t in g.GetItems())))
    elif fault=='wrong_layer':args['layer']=int(pcbnew.In2_Cu)
    elif fault=='raw_diagonal':args['points_nm'][-1][1]+=1
    elif fault=='launch_outside_island':args['launch_uuid']=ids['anchor']
    elif fault=='launch_point_not_native':args['points_nm'][0][0]+=1
    elif fault=='unknown_package':
        next(fp for fp in b.GetFootprints() if force._uid(fp)==ids['owner']).SetFPID(pcbnew.LIB_ID('unfamiliar','UNKNOWN_PACKAGE'))
    elif fault=='extra_load':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('ARBITRARY_LOAD');b.Add(fp);p=pcbnew.PAD(fp);p.SetNumber('1')
        p.SetNet(b.FindNet('/arbitrary/FEED'));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetPosition(pcbnew.VECTOR2I_MM(14,8));fp.Add(p)
    field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,TypeError,KeyError)):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','tap','group','pose','unowned_track','sidecar','proposal','current_unknown'])
def test_saved_child_cannot_forge_budget_tap_width_or_collateral_changes(tmp_path,monkeypatch,fault):
    source,args,ids=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'actual-child');field._save_field_snapshot(repair.construct(source,proposal),child)
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and not t.GetParentGroup())
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='tap':proposal['scope']['anchor_uuid']=ids['portal']
    elif fault=='group':next(iter(b.Groups())).SetName('OTHER_OWNER')
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unowned_track':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='proposal':proposal['width_nm']-=1
    elif fault=='current_unknown':monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=True,complete=False))
    field._save_field_snapshot(b,child);got=repair.receive(source,child,proposal,board_hint='arbitrary')
    assert not got['ok'] and got['errors'] and not got['release_authority']


def test_same_net_stem_outside_the_capture_aperture_is_a_real_search_obstacle(tmp_path,monkeypatch):
    source,args,ids=case(tmp_path,monkeypatch);b,scope=repair.source_scope(source,**{k:args[k] for k in
        ('board_hint','root_pad_uuid','retired_track_uuids','anchor_uuid')})
    t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('/arbitrary/FEED'));t.SetLayer(pcbnew.F_Cu);t.SetWidth(1250000)
    t.SetStart(pcbnew.VECTOR2I_MM(25,8));t.SetEnd(pcbnew.VECTOR2I_MM(25,16));b.Add(t)
    guard=repair.single_tap_guard(b,scope,ids['anchor'],int(pcbnew.F_Cu))
    assert not guard([25000000,15000000],[25000000,8000000],500000)
    assert guard([20000000,8000000],[25000000,8000000],500000)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_terminal_direction_distinguishes_real_pad_capture_from_exposed_backtracking(tmp_path,monkeypatch,quarter,back):
    source,args,ids=case(tmp_path,monkeypatch,quarter,back)
    b,scope=repair.source_scope(source,**{k:args[k] for k in
        ('board_hint','root_pad_uuid','retired_track_uuids','anchor_uuid')})
    t=next(t for t in b.GetTracks() if force._uid(t)==ids['trunk'])
    at=list(t.GetStart());other=list(t.GetEnd());ray=[(other[i]-at[i])//15 for i in (0,1)]
    guard=repair.terminal_approach_guard(b,scope['net'],args['layer'],500000,[at,args['points_nm'][0]])
    assert not guard([at[i]+ray[i] for i in (0,1)],at,500000)
    angled=[at[0]+ray[0]-ray[1],at[1]+ray[1]+ray[0]]
    assert guard(angled,at,500000)
    assert guard([at[i]-ray[i] for i in (0,1)],at,500000)
    assert guard([at[0]-ray[1],at[1]+ray[0]],at,500000)
    p=next(p for fp in b.GetFootprints() for p in fp.Pads() if force._uid(p)==ids['anchor'])
    p.SetNet(b.FindNet('OTHER'))
    exposed=repair.terminal_approach_guard(b,scope['net'],args['layer'],500000,[at,args['points_nm'][0]])
    assert not exposed(angled,at,500000)
