"""Dead proposal labels cannot grant credit or survive destructive edits."""
import pcbnew
import pytest
import cec_supply_consumer_branch as branch
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
import cec_field_coupling as field
import cec_force_current as force
from test_pass_through_supply_branch import fixture


def test_live_allocation_dependencies_refuse_before_any_native_deletion(monkeypatch,tmp_path):
    b,root,anchor,owner,cap,tracks,trunk,group,*_=fixture(monkeypatch,tmp_path)
    for item in (root,anchor,tracks[0]):
        before=field._field_snapshot_inventory(b)
        with pytest.raises(ValueError,match='native_deletion_breaks_typed_supply_annotation'):
            discard_items(b,[trunk,item])
        assert field._field_snapshot_inventory(b)==before


def test_valid_annotation_cannot_be_retired(monkeypatch,tmp_path):
    b,root,anchor,owner,cap,tracks,trunk,group,*_=fixture(monkeypatch,tmp_path)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):branch.retire_stale_anchor_annotation(b,force._uid(group),board_hint='unrelated_identity')
    assert field._field_snapshot_inventory(b)==before


def test_only_already_missing_anchor_label_retired_exact_material_remains(monkeypatch,tmp_path):
    b,root,anchor,owner,cap,tracks,trunk,group,*_=fixture(monkeypatch,tmp_path)
    old_id=force._uid(anchor);group_id=force._uid(group)
    # Model the inherited bug without the newly guarded deletion API.
    anchor.GetParentFootprint().Remove(anchor)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    # KiCad normalizes default synthetic font thickness on first load/save.
    # Establish the actual saved source before testing an exact metadata delta.
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    b=pcbnew.LoadBoard(str(source))
    before_tracks={force._uid(i) for i in b.GetTracks()}
    before=field._field_snapshot_inventory(b)
    plan=branch.retire_stale_anchor_annotation(b,group_id,board_hint='unrelated_identity')
    assert plan['missing_anchor_uuid']==old_id and not plan['physical_route_restored']
    child=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(b,child)
    assert list(b.Groups())==[]
    assert {force._uid(i) for i in b.GetTracks()}==before_tracks
    received=additive.receive(source,child,board_hint='unrelated_identity',retired_stale_consumer_group_uuids=[group_id])
    assert received['ok'] and received['complete'],received
    strict=additive.receive(source,child)
    assert not strict['ok'] and 'original_native_item_removed' in str(strict['errors'])


@pytest.mark.parametrize('missing',['root','member'])
def test_unknown_or_missing_physical_branch_scope_never_retired(monkeypatch,tmp_path,missing):
    b,root,anchor,owner,cap,tracks,trunk,group,*_=fixture(monkeypatch,tmp_path)
    anchor.GetParentFootprint().Remove(anchor)
    if missing=='root':root.GetParentFootprint().Remove(root)
    else:
        group.RemoveItem(tracks[0]);b.Delete(tracks[0])
        for t in list(group.GetItems()):group.RemoveItem(t)
    with pytest.raises(ValueError):branch.retire_stale_anchor_annotation(b,force._uid(group),board_hint='unrelated_identity')
