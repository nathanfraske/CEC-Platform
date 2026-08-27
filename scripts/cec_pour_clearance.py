#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""Transactional evacuation of foreign copper from high-current pours.

Detection belongs to :mod:`cec_constraints`; this module is the bounded route
repair actuator.  It removes only the exact track/via UUIDs convicted by the
union of canonical corridor geometry and actual laid zone outlines, records
every disturbed net for the residual router, and never mutates the input board.
KiCad SWIG removals are isolated in a disposable worker process because
continuing in the same interpreter after ``BOARD.Remove`` can invalidate
unrelated board proxies.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew

import cec_constraints
import cec_fr


def _summary_counts(summary):
    return (int(summary.get("n_tracks", 0)),
            int(summary.get("n_vias", 0)))


def _merge_records(derived_tracks=(), derived_vias=(), laid_items=()):
    """Union checker convictions by physical UUID, retaining all sources."""
    merged = {}
    for source, kind, rows in (
            ("derived", "track", derived_tracks or ()),
            ("derived", "via", derived_vias or ()),
            ("laid", None, laid_items or ())):
        for original in rows:
            if source == "laid" and original.get("kind") not in (
                    "track", "via"):
                continue
            row = dict(original)
            row_kind = kind or row.get("kind")
            uuid = row.get("uuid")
            if not uuid:
                continue
            if uuid not in merged:
                row["kind"] = row_kind
                row["sources"] = [source]
                merged[uuid] = row
            else:
                current = merged[uuid]
                current["sources"] = sorted(
                    set(current.get("sources") or ()) | {source})
                labels = set(current.get("pours") or ())
                labels.update(row.get("pours") or ())
                if row.get("pour"):
                    labels.add(row["pour"])
                if row.get("pour_net"):
                    labels.add(row["pour_net"])
                if labels:
                    current["pours"] = sorted(labels)
    return list(merged.values())


def _combined_summary(board_path):
    derived = cec_constraints.foreign_on_pour_summary(board_path)
    try:
        laid = cec_constraints.laid_pour_incursion_summary(
            board_path, item_limit=None)
    except Exception as exc:                              # noqa: BLE001
        laid = {
            "applicable": True, "status": "error",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "n_parts": 0, "n_tracks": 0, "n_vias": 0, "items": [],
        }
    records = _merge_records(
        derived.get("tracks"), derived.get("vias"), laid.get("items"))
    tracks = [row for row in records if row.get("kind") == "track"]
    vias = [row for row in records if row.get("kind") == "via"]
    errored = (derived.get("status") == "error"
               or laid.get("status") == "error")
    by_pour = {}
    for row in records:
        labels = (row.get("pours") or
                  [row.get("pour_net") or row.get("pour") or "unnamed"])
        for label in labels:
            counts = by_pour.setdefault(str(label), {})
            key = ("via:" if row.get("kind") == "via" else "") + str(
                row.get("net") or "<no net>")
            counts[key] = counts.get(key, 0) + 1
    return {
        "schema": 1,
        "applicable": bool(derived.get("applicable")
                           or laid.get("applicable")),
        "status": "error" if errored else "ok",
        "error": "; ".join(str(value) for value in (
            derived.get("error"), laid.get("error")) if value) or None,
        "n_tracks": len(tracks), "n_vias": len(vias),
        "n_parts": int(laid.get("n_parts", 0)),
        "by_pour": by_pour, "tracks": tracks, "vias": vias,
        "derived": derived, "laid": laid,
    }


def evacuate_board(board, board_path, *, protected_nets=()):
    """Remove exact foreign-on-pour primitives from an already loaded board.

    Safety ownership dominates stale lock flags: a locked track produced by an
    older route wave is still removed and reported.  Caller-declared
    ``protected_nets`` are stronger; any conflict on one refuses the whole
    transaction so authored/contract copper is never silently edited.
    """
    protected = {str(net) for net in (protected_nets or ()) if str(net)}
    try:
        tracks, vias = cec_constraints._foreign_pour_records(
            board, board_path)
    except cec_constraints.PourRegionError as exc:
        return {
            "schema": 1, "ok": False, "status": "error",
            "reason": "pour_region_unverifiable", "error": str(exc),
            "removed_count": 0, "removed_nets": [], "removed_items": [],
        }
    laid = cec_constraints.laid_pour_incursion_summary(
        board, item_limit=None)
    conflicts = _merge_records(tracks, vias, laid.get("items"))
    if tracks is None and not conflicts:
        return {
            "schema": 1, "ok": True, "status": "na", "applicable": False,
            "removed_count": 0, "removed_nets": [], "removed_items": [],
        }

    blocked = [row for row in conflicts if row.get("net") in protected]
    if blocked:
        return {
            "schema": 1, "ok": False, "status": "blocked",
            "reason": "protected_net_intrudes_high_current_pour",
            "protected_nets": sorted(protected), "blocked_items": blocked,
            "removed_count": 0, "removed_nets": [], "removed_items": [],
        }

    doomed = {row.get("uuid") for row in conflicts if row.get("uuid")}
    removed = []
    for item in list(board.GetTracks()):
        uuid = item.m_Uuid.AsString()
        if uuid not in doomed:
            continue
        record = next(row for row in conflicts if row.get("uuid") == uuid)
        removed.append(record)
        board.Remove(item)
    missing = sorted(doomed - {row.get("uuid") for row in removed})
    return {
        "schema": 1, "ok": not missing, "status": "ok" if not missing else "error",
        "applicable": True, "protected_nets": sorted(protected),
        "detected_tracks": sum(
            row.get("kind") == "track" for row in conflicts),
        "detected_vias": sum(
            row.get("kind") == "via" for row in conflicts),
        "derived_detected_tracks": len(tracks or ()),
        "derived_detected_vias": len(vias or ()),
        "laid_detected_tracks": int(laid.get("n_tracks", 0)),
        "laid_detected_vias": int(laid.get("n_vias", 0)),
        "removed_count": len(removed),
        "removed_tracks": sum(
            row.get("kind") == "track" for row in removed),
        "removed_vias": sum(row.get("kind") == "via" for row in removed),
        "removed_locked_count": sum(bool(row.get("locked")) for row in removed),
        "removed_nets": sorted({row.get("net") for row in removed if row.get("net")}),
        "removed_items": removed, "missing_uuids": missing,
    }


def _worker(board_path, report_path, protected_nets):
    board = pcbnew.LoadBoard(board_path)
    report = evacuate_board(
        board, board_path, protected_nets=protected_nets)
    if report.get("ok"):
        pcbnew.SaveBoard(board_path, board)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(report, sink, indent=2, sort_keys=True)
        sink.write("\n")


def _inspect_worker(board_path, report_path):
    summary = _combined_summary(board_path)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(summary, sink, indent=2, sort_keys=True)
        sink.write("\n")


def inspect_file(board_path, *, timeout=180):
    """Measure foreign copper against both pour authorities in fresh pcbnew.

    KiCad's legacy SWIG bindings retain process-global board/connectivity
    state after repeated LoadBoard operations.  A release or dashboard verdict
    must therefore not share the long-lived placer/router interpreter.
    """
    board_path = os.path.abspath(board_path)
    fd, report_path = tempfile.mkstemp(
        prefix="cec-pour-inspection-", suffix=".json",
        dir=os.path.dirname(board_path))
    os.close(fd)
    command = [sys.executable, os.path.abspath(__file__), "--inspect",
               "--board", board_path, "--report", report_path]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=float(timeout))
        if completed.returncode:
            return {
                "applicable": True, "status": "error",
                "error": "pour inspection worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout or
                     "no diagnostic")[-1200:]),
                "n_tracks": 0, "n_vias": 0, "by_pour": {},
                "tracks": [], "vias": [], "n_pours": 0,
            }
        with open(report_path, encoding="utf-8") as source_report:
            return json.load(source_report)
    except Exception as exc:                              # noqa: BLE001
        return {
            "applicable": True, "status": "error",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "n_tracks": 0, "n_vias": 0, "by_pour": {},
            "tracks": [], "vias": [], "n_pours": 0,
        }
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def evacuate_file(source, destination, *, protected_nets=(), refill=True):
    """Copy ``source`` and transactionally clear every convicted primitive.

    The result is a legal *repair base*, not a connectivity waiver: removed
    nets are explicit residual-route obligations and final signoff still
    requires zero opens.  On any refusal/error the destination is restored to
    the source bytes.
    """
    source = os.path.abspath(source)
    destination = os.path.abspath(destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = inspect_file(source)
    # A clean inspection is already the desired transactional postcondition.
    # Do not load and re-save an unchanged board in another pcbnew process:
    # aside from needless work, KiCad's legacy SWIG/property registries can
    # fault during that no-op SaveBoard on otherwise valid generated boards.
    if (before.get("status") != "error"
            and sum(_summary_counts(before)) == 0):
        return {
            "schema": 1, "ok": True, "status": "ok",
            "reason": "already_clear",
            "applicable": bool(before.get("applicable")),
            "protected_nets": sorted({
                str(net) for net in protected_nets if str(net)}),
            "detected_tracks": 0, "detected_vias": 0,
            "removed_count": 0, "removed_tracks": 0,
            "removed_vias": 0, "removed_locked_count": 0,
            "removed_nets": [], "removed_items": [],
            "missing_uuids": [], "source": source,
            "destination": destination, "before": before,
            "after": before, "post_clean": True,
            "rolled_back": False,
        }

    fd, report_path = tempfile.mkstemp(
        prefix="cec-pour-evacuation-", suffix=".json",
        dir=os.path.dirname(destination))
    os.close(fd)
    command = [sys.executable, os.path.abspath(__file__), "--worker",
               "--board", destination, "--report", report_path]
    for net in sorted({str(net) for net in protected_nets if str(net)}):
        command.extend(["--protected-net", net])
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError(
                "pour evacuation worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout)[-1200:]))
        with open(report_path, encoding="utf-8") as source_report:
            report = json.load(source_report)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass

    if report.get("ok") and refill and report.get("removed_count"):
        if not cec_fr.refill_zones(destination):
            report.update({"ok": False, "status": "error",
                           "reason": "zone_refill_failed"})

    after = inspect_file(destination) if report.get("ok") else before
    post_clean = (after.get("status") != "error"
                  and sum(_summary_counts(after)) == 0)
    report.update({
        "source": source, "destination": destination,
        "before": before, "after": after,
        "post_clean": bool(post_clean),
    })
    if report.get("ok") and not post_clean:
        report.update({"ok": False, "status": "error",
                       "reason": "foreign_copper_survived_evacuation"})
    if not report.get("ok"):
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["rolled_back"] = True
    else:
        report["rolled_back"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--board")
    parser.add_argument("--report")
    parser.add_argument("--protected-net", action="append", default=[])
    parser.add_argument("source", nargs="?")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args(argv)
    if args.inspect:
        if not args.board or not args.report:
            parser.error("--inspect requires --board and --report")
        _inspect_worker(args.board, args.report)
        # pcbnew's deprecated SWIG bindings can fault while finalizing child
        # proxies even after a read-only inspection. The private worker has
        # already closed its durable JSON output, so skip unsafe finalizers.
        os._exit(0)
    if args.worker:
        if not args.board or not args.report:
            parser.error("--worker requires --board and --report")
        _worker(args.board, args.report, args.protected_net)
        # Remove() invalidates unrelated child proxies. Saving and reporting
        # succeeded; exiting here is the process-isolation contract, matching
        # the other pcbnew mutation workers in this pipeline.
        os._exit(0)
    if not args.source or not args.destination:
        parser.error("source and destination are required")
    print(json.dumps(evacuate_file(
        args.source, args.destination,
        protected_nets=args.protected_net), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
