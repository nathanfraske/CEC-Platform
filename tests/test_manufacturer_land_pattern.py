"""Manufacturer alternatives retain identity; arbitrary geometry never does."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_manufacturer_land_pattern as pattern
import cec_source_cut_chain as chain


def fixture(tmp_path, *, quarter=0, back=False, name='ARBITRARY_DEVICE'):
    b=pcbnew.BOARD()
    fp=pcbnew.FootprintLoad(str(pattern.LIB),'SOT-23-6')
    fp.SetFPIDAsString('cec-Package_TO_SOT_SMD:SOT-23-6')
    fp.SetReference(name);fp.SetValue('INA181A2IDBVR')
    fp.SetField('MPN','INA181A2IDBVR')
    b.Add(fp)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(quarter*90)
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    for p in fp.Pads():
        net=pcbnew.NETINFO_ITEM(b,'DISTINCT_'+p.GetNumber());b.Add(net);p.SetNetCode(net.GetNetCode())
    uid=force._uid(fp)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'candidate')
    b=pcbnew.LoadBoard(str(child));q=pattern.plan(b,[uid]);pattern.materialize(b,q)
    field._save_field_snapshot(b,child)
    return source,child,uid


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('name',['SENSOR','NO_BOARD_SPECIFIC_ROLE_781'])
def test_exact_alternative_at_rotated_mirrored_arbitrary_packages(tmp_path,quarter,back,name):
    source,child,uid=fixture(tmp_path,quarter=quarter,back=back,name=name)
    saved=[p.read_bytes() for p in (source,child)]
    r=pattern.receive(source,child,board_hint='fixture',footprint_uuids=[uid])
    assert r['ok'] and r['complete'],r
    assert r['all_prior_native_terminal_and_copper_partitions_preserved']
    assert r['modified_native_uuids']==[uid] and not r['added_native_uuids']
    assert not r['current_authority'] and not r['release_authority'] and not r['assembly_qualified']
    assert saved==[p.read_bytes() for p in (source,child)]
    b=pcbnew.LoadBoard(str(child));fp=b.FindFootprintByReference(name)
    assert all(tuple(p.GetSize())==(1100000,600000) for p in fp.Pads())
    assert all(49999<=p.GetRoundRectCornerRadius()<=50001 for p in fp.Pads())


@pytest.mark.parametrize('fault',['net','pad_size','pad_uuid','mask','extra_track',
    'courtyard','pose','description','hidden_field','value','mpn','sidecar'])
def test_received_pattern_never_waives_other_native_changes(tmp_path,fault):
    source,child,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child));fp=list(b.GetFootprints())[0];p=list(fp.Pads())[0]
    if fault=='net':p.SetNetCode(list(fp.Pads())[1].GetNetCode())
    elif fault=='pad_size':p.SetSize(pcbnew.VECTOR2I_MM(1.2,.6))
    elif fault=='pad_uuid':p.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='mask':p.SetLocalSolderMaskMargin(100000)
    elif fault=='extra_track':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(2,2));t.SetEnd(pcbnew.VECTOR2I_MM(3,2))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(p.GetNetCode());b.Add(t)
    elif fault=='courtyard':pattern._courts(fp)[0].SetWidth(60000)
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='description':fp.SetLibDescription('worker-authorized pad change')
    elif fault=='hidden_field':fp.SetField('NEW_POLICY','allow_anything')
    elif fault=='value':fp.SetValue('INA181A1IDBVR')
    elif fault=='mpn':fp.SetField('MPN','INA181A2IDCKR')
    field._save_field_snapshot(b,child)
    if fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    r=pattern.receive(source,child,board_hint='fixture',footprint_uuids=[uid])
    assert not r['ok'] and not r['complete'] and r['errors'],r


@pytest.mark.parametrize('fault',['missing_mpn','dck_mpn','unknown_mpn','modified_land',
    'unknown_fpid','mismatched_value','modified_court','missing_pin'])
def test_source_package_must_be_positive_selected_catalog_geometry(tmp_path,fault):
    source,child,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=list(b.GetFootprints())[0];p=list(fp.Pads())[0]
    if fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='dck_mpn':fp.SetField('MPN','INA181A2IDCKR')
    elif fault=='unknown_mpn':fp.SetField('MPN','GENERIC_SOT23')
    elif fault=='modified_land':p.Move(pcbnew.VECTOR2I_MM(.001,0))
    elif fault=='unknown_fpid':fp.SetFPIDAsString('other:SOT-23-6')
    elif fault=='mismatched_value':fp.SetValue('TJA1051T/3')
    elif fault=='modified_court':pattern._courts(fp)[0].Move(pcbnew.VECTOR2I_MM(.001,0))
    elif fault=='missing_pin':p.SetNumber('0')
    with pytest.raises(ValueError):pattern.plan(b,[uid])


@pytest.mark.parametrize('ids',[[],[True],['x','x'],['a','b','c','d','e']])
def test_bound_selected_identity_scope(tmp_path,ids):
    source,child,uid=fixture(tmp_path)
    r=pattern.receive(source,child,board_hint='fixture',footprint_uuids=ids)
    assert not r['ok'] and r['errors']


def test_worker_proposal_is_rederived_before_materialization(tmp_path):
    source,child,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));q=pattern.plan(b,[uid])
    q['patterns'][0]['drawing']='arbitrary requested geometry'
    with pytest.raises(ValueError,match='source_rederivation'):pattern.materialize(b,q)


def test_original_inner_edge_contact_cannot_be_lost(tmp_path):
    source,child,uid=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=list(b.GetFootprints())[0];p=fp.FindPadByNumber('1')
    # Old land reaches x=19.525, while the TI land stops at x=19.25.
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(19.48,19.05))
    t.SetEnd(pcbnew.VECTOR2I_MM(20,19.05));t.SetWidth(100000)
    t.SetLayer(pcbnew.F_Cu);t.SetNetCode(p.GetNetCode());b.Add(t)
    field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));q=pattern.plan(b,[uid]);pattern.materialize(b,q)
    field._save_field_snapshot(b,child)
    r=pattern.receive(source,child,board_hint='fixture',footprint_uuids=[uid])
    assert not r['ok'] and any('lost_prior_native' in e for e in r['errors']),r


def test_chain_accepts_only_first_exact_catalog_phase_and_replays_full_source(tmp_path):
    source,child,uid=fixture(tmp_path)
    final=force._copy_family(child,tmp_path/'final');b=pcbnew.LoadBoard(str(final))
    p=list(list(b.GetFootprints())[0].Pads())[0]
    t=pcbnew.PCB_TRACK(b);t.SetStart(p.GetPosition())
    t.SetEnd(pcbnew.VECTOR2I_MM(16,19.05));t.SetWidth(200000)
    t.SetLayer(pcbnew.F_Cu);t.SetNetCode(p.GetNetCode());b.Add(t)
    field._save_field_snapshot(b,final)
    phases=[dict(kind='manufacturer_land_pattern',candidate=str(child),footprint_uuids=[uid]),
        dict(kind='additive',candidate=str(final))]
    r=chain.receive(source,final,board_hint='fixture',phases=phases,per_phase_leases=True)
    assert r['ok'] and r['complete'] and r['strict_manufacturer_land_patterns_received'],r
    assert r['manufacturer_modified_footprint_uuids']==[uid]
    assert len(r['source_manufacturer_land_pattern_replays'])==1
    assert r['whole_original_cut_additions_ground_and_rule_replay']['ok']
    with pytest.raises(ValueError,match='must_be_first_phase'):
        chain._phases(list(reversed(phases)),child)


def test_native_shared_pad_metadata_is_rebound_once_without_mutating_raw_report(tmp_path):
    import copy
    import cec_received_route_evidence as evidence
    source,child,uid=fixture(tmp_path)
    old,new=pcbnew.LoadBoard(str(source)),pcbnew.LoadBoard(str(child))
    proposal=pattern.plan(old,[uid]);pad=list(list(new.GetFootprints())[0].Pads())[0]
    shared=dict(uuid=force._uid(pad),footprint_uuid=uid,ref=pad.GetParentFootprint().GetReference(),
        pad=pad.GetNumber(),net=pad.GetNetname(),position_nm=list(pad.GetPosition()))
    report=dict(first=shared,second=[shared]);raw=copy.deepcopy(report)
    proof=dict(ok=True,complete=True,strict_manufacturer_land_patterns_received=True,
        source_manufacturer_land_pattern_replays=[proposal])
    adjusted,observations=evidence._rebind_received_package_positions(old,new,report,proof)
    assert report==raw and report['first'] is report['second'][0]
    assert adjusted['first'] is adjusted['second'][0]
    source_pad=next(p for fp in old.GetFootprints() for p in fp.Pads() if force._uid(p)==force._uid(pad))
    assert adjusted['first']['position_nm']==list(source_pad.GetPosition())
    assert not observations[0]['qualification_granted']
