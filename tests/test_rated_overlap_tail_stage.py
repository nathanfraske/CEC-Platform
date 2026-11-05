"""Removing an overlapped hairpin needs rated trim and whole-source replay."""
from unittest import mock
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_overlap_tail_stage as stage
from test_lastmile import _board
from test_field_proposals import track
from test_contained_one_face_barrel_stage import reporting_build


def fixture(tmp_path,face=pcbnew.F_Cu,rotate=False):
    xy=lambda p:(p[1],p[0]) if rotate else p
    net='/SYNTHETIC/RENAMED-RAIL'
    b=_board([(*xy(p),net) for p in ((3,6),(11,6),(7,10))],edge=(0,0,14,14));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        if face in (pcbnew.F_Cu,pcbnew.B_Cu):fp.SetLayer(face)
        for p in fp.Pads():
            if face not in (pcbnew.F_Cu,pcbnew.B_Cu):
                p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
                p.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                mask=pcbnew.LSET();mask.AddLayer(face);p.SetLayerSet(mask)
    trunk=track(b,net,xy((3,6)),xy((11,6)),layer=face)
    long=track(b,net,xy((7,3)),xy((7,10)),layer=face)
    short=track(b,net,xy((7,3)),xy((7,6)),layer=face)
    long.SetLocked(True);short.SetLocked(True)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    # Explicit synthetic test authority. Real boards use the existing registry.
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,margin_included=False,geometry_margin=1.25),
        branch_sharing_assumed=False,routing_layers=['F.Cu','In2.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.2,'In2.Cu':.2,'B.Cu':.2})})
    return source,b,long,short,trunk,catalog


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_native_whole_rated_delete_and_trim_removes_hairpin_without_new_dangling_endpoint(tmp_path,face,rotate):
    source,b,long,short,trunk,catalog=fixture(tmp_path,face,rotate);original=source.read_bytes()
    with mock.patch.object(stage.loops.topology,'distributed_supply_contracts',return_value=catalog):
        r=stage.run(source,tmp_path/'run',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=reporting_build(),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],(r['errors'],[(a.get('refusal')) for a in r['attempts']])
    assert r['before']['issue_count']==1 and r['after']['issue_count']==0
    assert r['independent_original_source_receiving']['independent_full_load_literal_receiving']['ok']
    assert not r['independent_original_source_receiving']['new_native_fault_ids']
    assert source.read_bytes()==original and not source.with_suffix('.kicad_prl').exists()
    assert not r['fab_ready'] and not r['release_authority']


@pytest.mark.parametrize('mode',['no_contract','inferred_sharing','no_lock_permission','under_floor','protected_group'])
def test_overlap_geometry_never_overrides_source_budget_lock_or_owner(tmp_path,mode):
    source,b,long,short,trunk,catalog=fixture(tmp_path);allow=True
    if mode=='no_contract':catalog['contracts']={}
    elif mode=='inferred_sharing':next(iter(catalog['contracts'].values()))['branch_sharing_assumed']=True
    elif mode=='no_lock_permission':allow=False
    elif mode=='under_floor':next(iter(catalog['contracts'].values()))['required_by_layer_mm']['F.Cu']=.3
    else:
        g=pcbnew.PCB_GROUP(b);g.SetName('fixed-source-owner');b.Add(g);g.AddItem(short)
        field._save_field_snapshot(b,source)
    original=source.read_bytes()
    with mock.patch.object(stage.loops.topology,'distributed_supply_contracts',return_value=catalog):
        r=stage.run(source,tmp_path/'refused',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=reporting_build(),allow_locked_source=allow)
    assert r['ok'] and not r['changed'] and r['candidate']==str(source.resolve()),r['errors']
    assert source.read_bytes()==original


def test_unknown_native_reporting_cannot_propose_or_accept_an_overlap_cut(tmp_path,monkeypatch):
    source,*_=fixture(tmp_path)
    monkeypatch.setattr(stage.native,'run',lambda *a,**kw:dict(ok=True,complete=False,
        native_inventory=dict(potentially_truncated=True)))
    r=stage.run(source,tmp_path/'truncated',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build='not-used',allow_locked_source=True)
    assert not r['ok'] and not r['changed'] and not r['attempts']


def test_ambiguous_native_source_identity_refuses_read_only_request_discovery(tmp_path):
    source,b,long,short,trunk,catalog=fixture(tmp_path)
    extra=short.Duplicate();b.Add(extra);extra.m_Uuid.Clone(pcbnew.KIID(force._uid(short)))
    with pytest.raises(ValueError,match='ambiguity'):stage.requests(b,allow_locked_source=True)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
def test_explicit_rated_acute_loop_cut_and_trim_preserves_all_real_source_joins(tmp_path,face,rotate):
    xy=lambda p:(p[1],p[0]) if rotate else p
    net='/TEST/RENAMED-AGGREGATE-RAIL'
    b=_board([(*xy(p),net) for p in ((3,5.5),(11,5.5),(5,3))],edge=(0,0,14,14));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if face not in (pcbnew.F_Cu,pcbnew.B_Cu):
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
                pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                if face==pcbnew.B_Cu:fp.SetLayer(face)
                mask=pcbnew.LSET();mask.AddLayer(face);pad.SetLayerSet(mask)
    track(b,net,xy((3,5.5)),xy((11,5.5)),layer=face)
    long=track(b,net,xy((5,3)),xy((8,6)),layer=face)
    short=track(b,net,xy((8,6)),xy((8,5.5)),layer=face)
    source=tmp_path/'acute.kicad_pcb';field._save_field_snapshot(b,source);original=source.read_bytes()
    assert not stage.requests(b)
    requests=stage.requests(b,include_acute_excursions=True)
    assert requests==[dict(net=net,retired_track_uuid=force._uid(short),retained_track_uuid=force._uid(long))]
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,margin_included=True,geometry_margin=1.),branch_sharing_assumed=False,
        routing_layers=['F.Cu','In2.Cu','B.Cu'],required_by_layer_mm={'F.Cu':.2,'In2.Cu':.2,'B.Cu':.2})})
    with mock.patch.object(stage.loops.topology,'distributed_supply_contracts',return_value=catalog):
        r=stage.run(source,tmp_path/'acute-run',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=reporting_build(),include_acute_excursions=True)
    assert r['ok'] and r['complete'] and r['changed'],[(a.get('refusal')) for a in r['attempts']]
    assert r['before']['issue_count']==1 and r['after']['issue_count']==0
    assert source.read_bytes()==original and not r['release_authority']


@pytest.mark.parametrize('value',[1,None,'yes'])
def test_acute_request_mode_is_explicit_not_truthy(tmp_path,value):
    _,b,*_=fixture(tmp_path)
    with pytest.raises(ValueError):stage.requests(b,include_acute_excursions=value)
