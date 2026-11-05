"""Pure leaf rerouting is not supply, placement, or release authority."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_local_branch_access as access
import cec_measurement_leaf as leaf
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_local_branch_access import fixture


def reflow_fixture(tmp_path,quarter=0,name='INPUT_STAGE'):
    source,child,pad=fixture(tmp_path)
    before=pcbnew.LoadBoard(str(source));after=pcbnew.LoadBoard(str(child))
    old={force._uid(t) for t in before.GetTracks()}
    replacement=leaf.plan(after,pad)
    discard_items(after,[t for t in after.GetTracks()
        if force._uid(t) not in old|set(replacement['track_uuids'])])
    for b,path in ((before,source),(after,child)):
        b.FindFootprintByReference('U_RENAMED').SetReference(name)
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        field._save_field_snapshot(b,path)
    return source,child,pad


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['INPUT_STAGE','ARBITRARY_STAGE_71'])
def test_exact_leaf_only_reflow_preserves_opens_and_does_not_claim_downstream_gain(tmp_path,quarter,name):
    source,child,pad=reflow_fixture(tmp_path,quarter,name)
    original=[p.read_bytes() for p in (source,child)]
    r=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert r['ok'] and r['complete'],r['errors']
    assert r['source_opens']==r['opens']
    assert r['downstream_route_not_admitted'] and not r['open_reduction_certified']
    assert not r['release_authority'] and not r['kelvin_qualified']
    assert original==[p.read_bytes() for p in (source,child)]
    # The historical local-cell API still requires a genuine isolated gain.
    old=access.receive(source,child,board_hint='fixture',pad_uuid=pad)
    assert not old['ok'] and any('no_source_isolated_cell_terminal_gain' in e for e in old['errors'])


@pytest.mark.parametrize('quarter',range(4))
def test_typed_chain_independently_retypes_pure_measurement_scope(tmp_path,quarter):
    source,child,pad=reflow_fixture(tmp_path,quarter)
    r=chain.receive(source,child,board_hint='fixture',per_phase_leases=True,
        phases=[dict(kind='measurement_leaf_reflow',candidate=str(child),pad_uuid=pad)])
    assert r['ok'] and r['complete'],r['errors']
    assert len(r['retired_track_uuids'])==3 and not r['retired_via_uuids']
    assert not r['current_authority'] and not r['release_authority']


@pytest.mark.parametrize('fault',['barrel','foreign_track','owner_motion','boundary_motion','width','new_contact'])
def test_leaf_receipt_never_grants_other_material_or_contact_authority(tmp_path,fault):
    source,child,pad=reflow_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child));q=leaf.plan(b,pad)
    if fault=='owner_motion':b.FindFootprintByReference('INPUT_STAGE').Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='boundary_motion':b.FindFootprintByReference('FIXED').Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='width':next(t for t in b.GetTracks() if force._uid(t) in q['track_uuids']).SetWidth(250000)
    elif fault=='barrel':
        t=pcbnew.PCB_VIA(b);t.SetPosition(pcbnew.VECTOR2I_MM(3,3));t.SetWidth(600000);t.SetDrill(300000)
        t.SetViaType(pcbnew.VIATYPE_THROUGH);t.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);t.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(t)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(3,3));t.SetEnd(pcbnew.VECTOR2I_MM(4,3))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(b.GetNetcodeFromNetname('GND' if fault=='foreign_track' else 'MEASURE_MINUS'));b.Add(t)
    field._save_field_snapshot(b,child)
    r=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert not r['ok'] and r['errors'] and not r['release_authority']


@pytest.mark.parametrize('scope',[None,'',True,[],['x']])
def test_chain_rejects_ambiguous_measurement_leaf_identity(tmp_path,scope):
    source,child,_=reflow_fixture(tmp_path)
    r=chain.receive(source,child,board_hint='fixture',
        phases=[dict(kind='measurement_leaf_reflow',candidate=str(child),pad_uuid=scope)])
    assert not r['ok'] and r['errors']
