"""Native saved pivots, not coordinate recipes or invented power budgets."""
import json,os,sys
from pathlib import Path
import pcbnew,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cec_fixed_supply_ground_pivot as worker
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_additive_route_receiving as additive
import cec_native_drc_runner as native
from test_ground_tee_tail import fixture as ground_fixture
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False):
    source,b,*_=ground_fixture(tmp_path)
    net=pcbnew.NETINFO_ITEM(b,'/ARBITRARY_FEED');b.Add(net)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('C_RENAMED_PIVOT');fp.SetValue('100nF')
    fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));fp.SetPosition(pcbnew.VECTOR2I_MM(16.5,15));b.Add(fp)
    for number,n,at in [('1',net,(17,15)),('2',b.FindNet('GND'),(16,15))]:
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(n);p.SetPosition(pcbnew.VECTOR2I_MM(*at))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.55,.65));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    fp.Reference().SetLayer(pcbnew.F_SilkS);fp.Value().SetLayer(pcbnew.F_Fab)
    track(b,'GND',(16,15),(15,14));track(b,net.GetNetname(),(17,15),(20,15))
    seed_fp=pcbnew.FOOTPRINT(b);seed_fp.SetReference('UNRELATED_SAVED_PROCESS_OWNER');seed_fp.SetPosition(pcbnew.VECTOR2I_MM(19,18));b.Add(seed_fp)
    seed=pcbnew.PAD(seed_fp);seed.SetNumber('1');seed.SetPosition(seed_fp.GetPosition());seed.SetNet(b.FindNet('GND'))
    seed.SetShape(pcbnew.PAD_SHAPE_RECT);seed.SetSize(pcbnew.VECTOR2I_MM(.5,.5));seed.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    seed.SetLayerSet(pcbnew.PAD.SMDMask());seed_fp.Add(seed)
    via=pcbnew.PCB_VIA(b);via.SetPosition(seed.GetPosition());via.SetNet(seed.GetNet());via.SetWidth(300000);via.SetDrill(200000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    origin=pcbnew.VECTOR2I_MM(15,15)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if quarter:item.Rotate(origin,pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if mirror:
            # A through barrel has no single-side process to flip. Mirror
            # its literal position without assigning the transient B.Cu
            # item-layer representative that the native writer normalizes.
            if item.GetClass()=='FOOTPRINT' and any(p.HasHole() for p in item.Pads()):continue
            if item.GetClass()=='PCB_VIA':item.SetPosition(pcbnew.VECTOR2I(2*origin.x-item.GetPosition().x,item.GetPosition().y))
            else:item.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    evidence=fr.group_local_pofv_signal_vias(b,[via]);assert evidence
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    b=pcbnew.LoadBoard(str(source));additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));pad=b.FindFootprintByReference('C_RENAMED_PIVOT').FindPadByNumber('2')
    return source,b,force._uid(pad)


def candidate(tmp_path,source,b,pad_uuid,turn=90):
    scope=worker.plan(b,source,board_hint='synthetic',pad_uuid=pad_uuid,turn_degrees=turn)
    made=worker.construct(b,source,scope,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'private');field._save_field_snapshot(b,child)
    return child,made


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_fixed_supply_pivot_keeps_all_native_tracks_and_shortens_ground_after_saved_replay(tmp_path,quarter,mirror):
    source,b,uid=fixture(tmp_path,quarter,mirror);raw=source.read_bytes();sidecars=force._sidecars(source)
    child,made=candidate(tmp_path,source,b,uid);r=worker.receive(source,child,board_hint='synthetic',pad_uuid=uid,turn_degrees=90)
    assert r['ok'] and r['complete'],r
    assert r['saved_return_mm']==0 and r['return_gain_mm']>1 and r['all_original_ground_returns']['ok']
    assert r['source_supply_pad_centre_and_all_source_tracks_preserved'] and r['source_bypass_assignments_preserved']
    assert r['source_rules_and_dimensions_preserved'] and r['actual_supply_contact_webs']
    assert r['actual_ground_reference_contacts'] and r['exact_source_process_geometry_rederived']
    assert not r['retired_native_uuids'] and len(r['added_native_uuids'])==1
    assert not r['current_or_barrel_capacity_qualified'] and not r['release_authority']
    assert force._sidecars(child)==sidecars and source.read_bytes()==raw
    old={force._uid(t):force._item_key(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    new={force._uid(t):force._item_key(t) for t in pcbnew.LoadBoard(str(child)).GetTracks()}
    assert all(new[u]==v for u,v in old.items())


@pytest.mark.parametrize('fault',['value','anchor','other_pad','old_track','old_via','new_drill','new_width',
    'new_net','unrelated_part','missing_group','sidecar','extra_foreign','extra_ground','unlocked_new_entry',
    'missing_new_entry','noncardinal','false_turn'])
def test_saved_pivot_cannot_borrow_authority_for_an_unowned_or_unqualified_change(tmp_path,fault):
    source,b,uid=fixture(tmp_path);child,made=candidate(tmp_path,source,b,uid);b=pcbnew.LoadBoard(str(child))
    fp=b.FindFootprintByReference('C_RENAMED_PIVOT');incoming=next(t for t in b.GetTracks() if force._uid(t) in made['added_native_uuids'])
    turn=90
    if fault=='value':fp.SetValue('47uF')
    elif fault=='anchor':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='other_pad':fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(.7,.7))
    elif fault=='old_track':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(210000)
    elif fault=='old_via':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t!=incoming).SetDrill(400000)
    elif fault=='new_drill':incoming.SetDrill(100000)
    elif fault=='new_width':incoming.SetWidth(290000)
    elif fault=='new_net':incoming.SetNet(b.FindNet('/ARBITRARY_FEED'))
    elif fault=='unrelated_part':b.FindFootprintByReference('RETAINED_TEST_LOAD').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_group':next(g for g in b.Groups() if g.ContainsItem(incoming)).RemoveItem(incoming)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='extra_foreign':track(b,'/ARBITRARY_FEED',(26,26),(27,26))
    elif fault=='extra_ground':track(b,'GND',(26,17),(27,17))
    elif fault=='unlocked_new_entry':incoming.SetLocked(False)
    elif fault=='missing_new_entry':
        from cec_native_items import discard_items
        discard_items(b,[incoming])
    elif fault=='noncardinal':fp.SetOrientationDegrees(fp.GetOrientationDegrees()+1)
    elif fault=='false_turn':turn=270
    raw=source.read_bytes()
    if fault=='new_net':
        # The native snapshot guard independently catches the writer's
        # attempted foreign-net normalization before receiving can run.
        with pytest.raises(field._ProposalUnknown):field._save_field_snapshot(b,child)
        assert source.read_bytes()==raw
        return
    field._save_field_snapshot(b,child)
    r=worker.receive(source,child,board_hint='synthetic',pad_uuid=uid,turn_degrees=turn)
    assert not r['ok'] and r['errors'] and not r['release_authority'],r
    assert source.read_bytes()==raw


@pytest.mark.parametrize('turn',[True,0,360,45,None,90.0])
def test_no_implicit_or_unbounded_pivot_scope_is_accepted(tmp_path,turn):
    source,b,uid=fixture(tmp_path)
    with pytest.raises(ValueError):worker.plan(b,source,board_hint='synthetic',pad_uuid=uid,turn_degrees=turn)


@pytest.mark.parametrize('fault',['locked','resized','no_rule','unknown_profile','locked_group'])
def test_source_context_must_be_native_capacitor_and_saved_factory_rule(tmp_path,fault):
    source,b,uid=fixture(tmp_path);fp=b.FindFootprintByReference('C_RENAMED_PIVOT')
    if fault=='locked':fp.SetLocked(True)
    elif fault=='resized':fp.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(3,3))
    elif fault=='no_rule':source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='locked_group':next(g for g in b.Groups() if g.GetName()==worker.saved_rule.GROUP).SetLocked(True)
    else:
        p=b.GetProperties();p['CEC_FAB_PROFILE']='unknown';b.SetProperties(p)
    with pytest.raises(ValueError):worker.plan(b,source,board_hint='synthetic',pad_uuid=uid,turn_degrees=90)


def test_native_saved_custom_rule_group_is_decisive_not_a_default_floor_waiver(tmp_path):
    source,b,uid=fixture(tmp_path);child,made=candidate(tmp_path,source,b,uid)
    build=Path(os.environ.get('CEC_NATIVE_DRC_TEST_BUILD','/home/codex/.cache/cec/native-drc-10.0.5'))
    def faults(path,label):
        out=tmp_path/(label+'.json');result=native.run(path,out,reporting_build=build,timeout_s=10.)
        assert result['ok'] and result['complete'] and not result['native_inventory']['potentially_truncated']
        return {q['type'] for q in json.loads(out.read_text())['violations'] if q['type'] in
            ('via_diameter','drill_out_of_range','annular_width') and any(i.get('uuid') in made['added_native_uuids'] for i in q['items'])}
    assert not faults(child,'in-exact-group')
    b=pcbnew.LoadBoard(str(child));via=next(t for t in b.GetTracks() if force._uid(t) in made['added_native_uuids'])
    next(g for g in b.Groups() if g.ContainsItem(via)).RemoveItem(via)
    control=force._copy_family(child,tmp_path/'group-only-control');field._save_field_snapshot(b,control)
    assert faults(control,'outside-exact-group')=={'via_diameter','drill_out_of_range','annular_width'}


def test_catalog_rediscovers_native_ground_capacitor_and_all_cardinal_pivots_without_mutation(tmp_path):
    source,b,uid=fixture(tmp_path);raw=source.read_bytes();before=field._field_snapshot_inventory(b)
    found=worker.discover(b,source,board_hint='synthetic',max_capacitors=1)
    assert found['complete'] and len(found['offers'])==3 and found['eligible_capacitors_considered']==1
    assert {q['ground_pad_uuid'] for q in found['offers']}=={uid}
    assert {q['turn_degrees'] for q in found['offers']}=={90,180,270}
    assert found['catalog_is_bounded_not_global_impossibility'] and not found['electrical_or_release_authority']
    assert raw==source.read_bytes() and field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('limit',[True,0,33,None,1.0])
def test_discovery_bounds_cannot_silently_expand_or_use_boolean_counts(tmp_path,limit):
    source,b,_=fixture(tmp_path)
    with pytest.raises(ValueError):worker.discover(b,source,board_hint='synthetic',max_capacitors=limit)
