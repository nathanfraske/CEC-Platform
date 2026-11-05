"""Keep source-contact copper exact while rebuilding only an owned interior."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_local_branch_access as access
import cec_measurement_leaf as leaf
from cec_native_items import discard_items
from test_local_branch_access import fixture


def contact_tail_fixture(tmp_path,quarter=0):
    source,_,pad=fixture(tmp_path)
    child=force._copy_family(source,tmp_path/'exact-tail')
    b=pcbnew.LoadBoard(str(child));q=leaf.plan(b,pad)
    edge=next(t for t in b.GetTracks() if force._uid(t)==q['track_uuids'][-1])
    copy=edge.Duplicate();copy.m_Uuid.Clone(pcbnew.KIID(force._uid(edge)))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in q['track_uuids']])
    points=[[round(v*1e6) for v in xy] for xy in [(16,13),(17,13),(17,12),(10,12),(10,13)]]
    assert leaf.path_clear(b,q,points)
    new=leaf.add_path(b,q,points);discard_items(b,[new[-1]]);b.Add(copy)
    field._save_field_snapshot(b,child)
    for path in (source,child):
        native=pcbnew.LoadBoard(str(path))
        for item in [*native.GetFootprints(),*native.GetTracks(),*native.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        field._save_field_snapshot(native,path)
    return source,child,pad,q['track_uuids'][-1]


@pytest.mark.parametrize('quarter',range(4))
def test_exact_native_contact_tail_has_less_retirement_not_more_authority(tmp_path,quarter):
    source,child,pad,tail=contact_tail_fixture(tmp_path,quarter)
    r=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert r['ok'] and r['complete'],r
    assert r['preserved_exact_measurement_contact_tail_uuids']==[tail]
    assert tail not in r['retired_track_uuids'] and tail not in r['added_native_uuids']
    assert len(r['retired_track_uuids'])==2
    assert r['only_exact_typed_measurement_leaf_changed'] and not r['release_authority']


@pytest.mark.parametrize('fault',['width','pose','lock','net'])
def test_source_tail_identity_never_authorizes_changed_contact_material(tmp_path,fault):
    source,child,pad,tail=contact_tail_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child));edge=next(t for t in b.GetTracks() if force._uid(t)==tail)
    if fault=='width':edge.SetWidth(250000)
    elif fault=='pose':edge.SetEnd(pcbnew.VECTOR2I_MM(10,13.01))
    elif fault=='lock':edge.SetLocked(not edge.IsLocked())
    else:edge.SetNetCode(b.GetNetcodeFromNetname('GND'))
    if fault=='net':
        # The identity-preserving writer may reject net propagation even
        # before receiving; that is a stricter refusal, not a test failure.
        try:field._save_field_snapshot(b,child)
        except field._ProposalUnknown as exc:
            assert str(exc)=='native_field_snapshot_changed_saved_identity'
            return
    else:field._save_field_snapshot(b,child)
    r=access.receive_measurement_reflow(source,child,board_hint='fixture',pad_uuid=pad)
    assert not r['ok'] and r['errors'],r
