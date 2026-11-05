"""Small in-flight route polish; the coordinator still owns final admission.

Only the existing unanchored, degree-two acute-vertex primitive is enabled.
No via, footprint, zone, track-width, or authored locked copper changes are
authorized here. Native whole-board grading and parent preservation follow.
"""
from pathlib import Path


def native_acute_polish(board_path):
    import pcbnew
    import cec_fab_repair as fab
    import cec_local_copper_cell as copper
    import cec_route_quality as quality
    import cec_full_pipeline as pipeline
    board_path = Path(board_path)
    source_sha = pipeline.sha256_file(board_path)
    board = pcbnew.LoadBoard(str(board_path))
    before = copper.copper_inventory(board)
    initial = quality.analyze_board(board)
    count = fab.repair_acute_vertices(board)
    after = copper.copper_inventory(board)
    changed = sorted(uid for uid, geometry in before.items() if after.get(uid)!=geometry)
    locked = {t.m_Uuid.AsString() for t in board.GetTracks() if t.IsLocked()}
    final = quality.analyze_board(board)
    if (locked.intersection(changed) or set(before)!=set(after)
            or final['issue_count'] >= initial['issue_count'] or
            final['non_octilinear_count'] > initial['non_octilinear_count']):
        return dict(changed=False,reason='no_safe_craft_gain',release_authority=False)
    if count:
        pcbnew.SaveBoard(str(board_path),board)
    return dict(changed=bool(count),acute_vertices=count,changed_track_uuids=changed,
        before_issues=initial['issue_count'],after_issues=final['issue_count'],
        source_sha256=source_sha,output_sha256=pipeline.sha256_file(board_path),
        release_authority=False,requires_independent_admission=True)


def apply(board_path, *, timeout_s=30):
    import cec_certificate_repair as repair
    return repair._spawn_apply(native_acute_polish,(str(board_path),),timeout_s=timeout_s)
