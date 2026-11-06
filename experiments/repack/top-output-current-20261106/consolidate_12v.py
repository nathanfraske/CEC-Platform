"""Source-owned additive consolidation of the actual 12 V output collector.

Same-priority bank overlay was correctly refused. Extend its existing owner
by the exact complete-pad-grid envelope instead; retain all original copper
objects, zone process and prior saved power fills, with independent receiving.
"""
from pathlib import Path
import copy
import json
import time
from cec_pipeline.native import _native
from cec_pipeline import power
import cec_pad_bank_collector as bank
import cec_rectilinear_copper as owner
import cec_force_current as force
import cec_additive_route_receiving as syntax
import cec_field_coupling as field
import cec_zone_fill as fill
import cec_suite_inspection as inspect
import cec_native_drc_runner as native
import cec_current_debt as current

SOURCE = Path('experiments/repack/paired-closed-v2-20261105/carrier/board.kicad_pcb')
SHA = 'b52754d95fad20386528c9b5cd9abdc44c6697032baff1d7ebaeded2f95ab8f1'
WORK = Path('experiments/repack/top-output-current-20261106/consolidated12-v1')
ZONE = '8299e7ca-b54e-408f-b4da-f843235b9b5a'
TRACKS = ['0ea308d8-0916-4f7c-96f4-d428e85f5fe1','d0b6d2b4-9cfe-47c3-8b24-d3a99d99fb06',
          'dcf4ab3a-cc44-4be4-8096-d77bbfebfa0e','faf3f80b-7c71-40bf-a5b8-53efb056a54c']


def main():
    assert force._hash(SOURCE) == SHA and not WORK.exists()
    pcb, quiet = _native(); board = pcb.LoadBoard(str(SOURCE))
    zone = next(z for z in board.Zones() if force._uid(z) == ZONE)
    pads = [force._uid(p) for p in board.FindFootprintByReference('TB1').Pads()]
    policy = dict(margin_nm=1000,grid_nm=1000,chamfer_nm=250000)
    net, padrows, trackrows, shapes, contour, cut = bank._geometry(board,pads,TRACKS,
        pcb.F_Cu,policy,time.monotonic()+8.)
    assert net == zone.GetNetname() == '/SENSE12V_LO'
    model = power.parameters(board,SOURCE,dict(track_uuids=TRACKS),'atx-24pin-rev3')
    bank._clear(board,owner._fill_envelope(contour,style='chamfer45',margin_nm=4),
        net,pcb.F_Cu,model['clearance_nm'],time.monotonic()+8.,own_zone_uuid=ZONE)
    old_outline = zone.Outline().CloneDropTriangulation()
    old_fill = zone.GetFilledPolysList(pcb.F_Cu).CloneDropTriangulation()
    merged = old_outline.CloneDropTriangulation(); merged.BooleanAdd(owner._poly(contour))
    assert merged.OutlineCount() == 1 and not merged.HoleCount(0)
    loss = old_outline.CloneDropTriangulation(); loss.BooleanSubtract(merged)
    assert loss.OutlineCount() == 0
    zone.UnFill(); zone.Outline().RemoveAllContours(); zone.Outline().Append(merged)
    selected = pcb.ZONES(); selected.append(zone)
    fill.compile_selected(board,selected,timeout_s=8.,initialize_selected=True)
    loss = old_fill.CloneDropTriangulation(); loss.BooleanSubtract(zone.GetFilledPolysList(pcb.F_Cu))
    # Native refill of a merged contour can create quantization differences.
    # Refuse rather than silently erase original power material.
    assert not loss.OutlineCount(), ('source_saved_power_fill_lost',loss.Area())
    for shape in shapes:
        missing = shape.CloneDropTriangulation(); missing.BooleanSubtract(zone.GetFilledPolysList(pcb.F_Cu))
        assert not missing.OutlineCount(), 'source_bank_shape_not_covered'
    syntax._ground_refill(board)
    target = force._copy_family(SOURCE,WORK/'carrier'); raw = WORK/'native.kicad_pcb'
    field._save_field_snapshot(board,raw)
    root, old = syntax._nodes(SOURCE); _, fresh = syntax._nodes(raw)
    changed = {ZONE} | {force._uid(z) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND'}
    lookup = {id(n):uid for uid,n in old.items()}
    root[1:] = [fresh[lookup[id(n)]] if lookup.get(id(n)) in changed else n for n in root[1:]]
    target.write_text(syntax._render(root)+'\n')
    saved = pcb.LoadBoard(str(target))
    assert field._field_snapshot_inventory(saved) == field._field_snapshot_inventory(board)
    report = dict(source=str(SOURCE),source_sha256=SHA,candidate=str(target),
        candidate_sha256=force._hash(target),source_current_model=model,
        source_pad_rows=padrows,retained_track_rows=trackrows,added_bank_polygon_nm=contour,
        original_outline_and_saved_fill_wholly_retained=True,source_bank_shapes_fully_covered=True,
        existing_zone_uuid=ZONE,all_settings_and_non_ground_owners_except_selected_unchanged=True,
        current_thermal_qualified=False,release_authority=False)
    inspect.write_json(WORK/'construction.json',report)
    result = native.run(target,WORK/'native-drc.json',timeout_s=10.,
        reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',
        footprint_table='checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
    inspect.write_json(WORK/'native-drc.runner.json',result)
    assert result['ok'] and result['complete']
    raw = json.loads((WORK/'native-drc.json').read_text())
    print('native',dict(errors=sum(v['severity']=='error' for v in raw['violations']),opens=len(raw['unconnected_items'])),flush=True)
    check = current.receive(SOURCE,target,board_hint='atx-24pin-rev3')
    inspect.write_json(WORK/'current.json',check)
    print('current',{k:v for k,v in check.items() if k not in ('before_result','after_result')},flush=True)
    assert force._hash(SOURCE) == SHA


if __name__ == '__main__':
    main()
