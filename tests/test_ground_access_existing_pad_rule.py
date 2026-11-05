"""Source-defined in-pad ground entries never create a smaller global rule."""
import json
import os
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_existing_local_pofv_pad_rule as rule
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_access_completion as op
import cec_native_drc_runner as native
from test_ground_access_completion import fixture as base


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,pad,point=base(tmp_path,quarter=quarter,mirror=mirror,layer=layer,
        mode='vip',observed=True)
    pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNRELATED_PROCESS_SEED');b.Add(fp)
    land=pcbnew.PAD(fp);land.SetNumber('z');land.SetNet(b.FindNet('GND'))
    land.SetPosition(pcbnew.VECTOR2I_MM(24,5));land.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    land.SetAttribute(pcbnew.PAD_ATTRIB_SMD);land.SetShape(pcbnew.PAD_SHAPE_RECT)
    land.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(land)
    v=pcbnew.PCB_VIA(b);v.SetPosition(land.GetPosition());v.SetNet(land.GetNet())
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(300000);v.SetDrill(200000);b.Add(v)
    evidence=fr.group_local_pofv_signal_vias(b,[v]);assert evidence
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({
        'net_settings':{'classes':[dict(name='Default',track_width=.2,clearance=.2,
            via_diameter=.6,via_drill=.3)]},'board':{'design_settings':{'rules':{
        'min_via_diameter':.5,'min_through_hole_diameter':.3,'min_via_annular_width':.1,
        'min_hole_to_hole':.254,'min_clearance':.2}}}}))
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    return source,force._uid(pad)


def saved(tmp_path,**options):
    source,uid=fixture(tmp_path,**options)
    args=dict(board_hint='synthetic',pad_uuid=uid,use_existing_local_pad_rule=True)
    q=json.loads(json.dumps(op.plan(source,**args)))
    child=Path(op.write_private(q,tmp_path/'child')['candidate'])
    return source,child,args,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_only_source_declared_minimum_direct_entry_is_exactly_received(tmp_path,quarter,mirror,layer):
    source,child,args,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    original=source.read_bytes();rules=source.with_suffix('.kicad_dru').read_bytes()
    r=op.receive(source,child,**args)
    assert r['ok'] and r['complete'],r
    assert q['ops']==[['via',q['ops'][0][1],200000,300000]]
    assert r['saved_return_witness_mm']==0 and r['new_holes']==1
    assert r['all_source_known_returns']['ok'] and r['every_source_native_partition_identical']
    a,b=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    groups=[next(g for g in board.Groups() if g.GetName()==rule.GROUP) for board in (a,b)]
    before,after=[{force._uid(v) for v in g.GetItems()} for g in groups]
    assert after-before==set(r['added_native_uuids']) and before<=after
    assert force._sidecars(source)==force._sidecars(child) and source.read_bytes()==original
    assert source.with_suffix('.kicad_dru').read_bytes()==rules==child.with_suffix('.kicad_dru').read_bytes()
    assert not r['current_qualified'] and not r['fab_ready'] and not r['release_authority']


@pytest.mark.parametrize('fault',['group','floor','new_width','new_hole','offcentre','unowned_member',
    'rule','source_lock','unlocked_via'])
def test_saved_delta_cannot_extend_any_other_qualification(tmp_path,fault):
    source,child,args,q=saved(tmp_path);b=pcbnew.LoadBoard(str(child))
    original={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in b.GetTracks() if force._uid(t) not in original)
    group=next(g for g in b.Groups() if g.GetName()==rule.GROUP)
    if fault=='group':group.RemoveItem(via)
    elif fault=='floor':
        path=child.with_suffix('.kicad_pro');project=json.loads(path.read_text())
        project['board']['design_settings']['rules']['min_via_diameter']=.499999
        path.write_text(json.dumps(project))
    elif fault=='new_width':via.SetWidth(299999)
    elif fault=='new_hole':via.SetDrill(199999)
    elif fault=='offcentre':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unowned_member':group.AddItem(next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'))
    elif fault=='rule':child.with_suffix('.kicad_dru').write_text('(version 1)')
    elif fault=='source_lock':group.SetLocked(True)
    else:via.SetLocked(False)
    field._save_field_snapshot(b,child);r=op.receive(source,child,**args)
    assert not r['ok'] and not r['complete'] and r['errors'],r


@pytest.mark.parametrize('fault',['missing_rule','missing_group','moved_source_pad','locked_group',
    'non_boolean','conflicting_mode'])
def test_local_rule_optin_remains_literal_saved_pad_scoped(tmp_path,fault):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    args=dict(board_hint='synthetic',pad_uuid=uid,use_existing_local_pad_rule=True)
    if fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='missing_group':
        g=next(iter(b.Groups()))
        for item in list(g.GetItems()):g.RemoveItem(item)
        field._save_field_snapshot(b,source)
    elif fault=='moved_source_pad':
        # Rule resolution on a private displaced pad cannot borrow the saved rule.
        pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if force._uid(p)==uid)
        pad.Move(pcbnew.VECTOR2I(1,0))
        with pytest.raises(ValueError):op._existing_pad_rule(b,pad)
        return
    elif fault=='locked_group':next(iter(b.Groups())).SetLocked(True);field._save_field_snapshot(b,source)
    elif fault=='non_boolean':args['use_existing_local_pad_rule']=1
    else:args['prefer_source_track_root']=True
    with pytest.raises(ValueError):op.plan(source,**args)


def test_existing_rule_group_native_control_is_not_a_blanket_drill_floor_waiver(tmp_path):
    source,child,args,q=saved(tmp_path);build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('explicit native reporting build required')
    b=pcbnew.LoadBoard(str(child));old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in b.GetTracks() if force._uid(t) not in old);uid=force._uid(via)
    def faults(path,label):
        report=tmp_path/(label+'.json');r=native.run(path,report,reporting_build=Path(build),timeout_s=10.)
        assert r['ok'] and r['complete'] and not r['native_inventory']['potentially_truncated'],r
        return {v['type'] for v in json.loads(report.read_text())['violations']
            if v['type'] in ('via_diameter','drill_out_of_range','annular_width')
            and any(i.get('uuid')==uid for i in v['items'])}
    assert not faults(child,'actual-group')
    next(iter(b.Groups())).RemoveItem(via)
    control=force._copy_family(child,tmp_path/'not-qualified');field._save_field_snapshot(b,control)
    assert faults(control,'group-negative-control')=={'via_diameter','drill_out_of_range','annular_width'}
