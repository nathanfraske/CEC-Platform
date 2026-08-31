#!/usr/bin/env python3
"""Canonical, fail-closed CEC PCB production pipeline.

This is the one start-to-finish entry point for a current BETA board.  It
composes the existing specialist engines instead of maintaining another
placer/router implementation:

    current hierarchy + BOM + board policy
      -> source/intake equivalence
      -> fixed-outline, route-aware placement (optional replacement)
      -> multiresolution pin-access/fanout/congestion preflight
      -> priority route oracle (bypass cells, pairs, controls, power objects,
         access tiers, residual route, certificate repair and finishing)
      -> independent constraint/DRC/connectivity/fab admission
      -> manufacturing package OR a withheld review artifact
      -> dashboard archive

Every stage is content addressed.  A resumed stage is reused only when its
input digest and every recorded artifact hash still match.  Manufacturing
outputs are never emitted from a failing route or a DRAFT source tree.
"""

from __future__ import annotations

import argparse
import ast
import copy
import csv
import datetime as _dt
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA = 1

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# KiCad ships wxPython with verbose debug handlers.  Every spawned placement
# or routing worker imports this module again; without process-local
# suppression, duplicate image-handler warnings can expand unattended wave
# logs by megabytes and hide the actual placement/router failure evidence.
# This affects diagnostics only -- no PCB operation or admission decision.
try:
    import wx
    wx.Log.SetLogLevel(wx.LOG_Error)
    wx.DisableAsserts()
except Exception:                                      # noqa: BLE001
    pass


class PipelineBlocked(RuntimeError):
    """A hard admission stage refused to spend later pipeline work."""


def _board_identity(cfg):
    """Return the stable manifest/provenance key, not the local policy slug."""
    return getattr(cfg, "board_key", "") or cfg.board


def _json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def digest_value(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".%s." % path.name, suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _artifact_rows(paths):
    rows = []
    for raw in sorted({str(Path(path).resolve()) for path in paths if path}):
        if not os.path.isfile(raw):
            raise FileNotFoundError("stage artifact is missing: %s" % raw)
        rows.append({
            "path": raw,
            "size": os.path.getsize(raw),
            "sha256": sha256_file(raw),
        })
    return rows


def artifacts_match(rows):
    return bool(rows) and all(
        os.path.isfile(row.get("path", ""))
        and os.path.getsize(row["path"]) == int(row.get("size", -1))
        and sha256_file(row["path"]) == row.get("sha256")
        for row in rows
    )


class StageJournal:
    """Atomic stage ledger with hash-verified resume."""

    def __init__(self, path, board, *, resume=True):
        self.path = Path(path).resolve()
        self.resume = bool(resume)
        if self.resume and self.path.is_file():
            with self.path.open(encoding="utf-8") as handle:
                self.data = json.load(handle)
            if self.data.get("schema") != SCHEMA:
                raise ValueError("unsupported pipeline journal schema")
            if self.data.get("board") != board:
                raise ValueError("journal board does not match requested board")
        else:
            self.data = {
                "schema": SCHEMA,
                "board": board,
                "run_id": _dt.datetime.now(_dt.timezone.utc).strftime(
                    "%Y%m%dT%H%M%SZ"
                ),
                "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "stages": {},
            }
            self._write()

    def _write(self):
        self.data["updated_utc"] = _dt.datetime.now(
            _dt.timezone.utc
        ).isoformat()
        atomic_json(self.path, self.data)

    def run(self, name, input_digest, action):
        old = self.data["stages"].get(name) or {}
        if (
            self.resume
            and old.get("status") == "complete"
            and old.get("input_digest") == input_digest
            and artifacts_match(old.get("artifacts") or ())
        ):
            print("  [%-24s] RESUME %s" % (name, input_digest[:12]), flush=True)
            return dict(old.get("result") or {})

        started = time.monotonic()
        self.data["stages"][name] = {
            "status": "running",
            "input_digest": input_digest,
            "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        self._write()
        print("  [%-24s] RUN    %s" % (name, input_digest[:12]), flush=True)
        try:
            raw = dict(action() or {})
            artifacts = _artifact_rows(raw.pop("_artifacts", ()))
            record = {
                "status": "complete",
                "input_digest": input_digest,
                "elapsed_s": round(time.monotonic() - started, 3),
                "artifacts": artifacts,
                "result": raw,
            }
            self.data["stages"][name] = record
            self._write()
            print(
                "  [%-24s] %-6s %.1fs" % (
                    name, "PASS" if raw.get("ok", True) else "BLOCK",
                    record["elapsed_s"],
                ),
                flush=True,
            )
            return raw
        except Exception as exc:
            self.data["stages"][name] = {
                "status": "failed",
                "input_digest": input_digest,
                "elapsed_s": round(time.monotonic() - started, 3),
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc()[-12000:],
            }
            self._write()
            print("  [%-24s] ERROR  %s" % (name, exc), flush=True)
            raise


def _run(command, *, cwd=ROOT, timeout=1800):
    process = subprocess.run(
        [str(part) for part in command], cwd=str(cwd), capture_output=True,
        text=True, timeout=timeout
    )
    if process.returncode:
        raise RuntimeError(
            "command failed (%d): %s\n%s" % (
                process.returncode, " ".join(map(str, command)),
                (process.stderr or process.stdout or "no diagnostic")[-4000:],
            )
        )
    return process


def _copy_sidecars(source_board, destination_board, cfg=None):
    """Copy one executable PCB artifact family without dropping authority.

    A pour plan and frozen pour-first state are inputs to preflight and routing,
    not optional reports.  Every canonical stage boundary must preserve them
    when it renames ``foo.kicad_pcb`` to ``board.kicad_pcb``; otherwise the
    next stage reconstructs legacy geometry and quite correctly fails closed.
    """
    import cec_fr

    source_board = Path(source_board).resolve()
    destination_board = Path(destination_board).resolve()
    destination_board.parent.mkdir(parents=True, exist_ok=True)
    if source_board != destination_board:
        shutil.copy2(source_board, destination_board)
    copied = [str(destination_board)]
    copied.extend(cec_fr.copy_project_sidecars(
        str(source_board), str(destination_board)))
    for extension in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        source = source_board.with_suffix(extension)
        if not source.is_file() and cfg is not None:
            candidates = sorted(Path(cfg.dir).glob("*" + extension))
            source = candidates[0] if candidates else source
        if source.is_file():
            destination = destination_board.with_suffix(extension)
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            copied.append(str(destination))
    authority_pcb = getattr(cfg, "pcb", None) if cfg is not None else None
    if authority_pcb:
        authority = Path(authority_pcb).resolve().with_suffix(".kicad_pro")
        destination = destination_board.with_suffix(".kicad_pro")
        project_authority = _merge_project_rule_authority(
            authority, destination)
        if not project_authority.get("ok"):
            raise RuntimeError(
                "project rule authority could not be staged: %s" %
                project_authority.get("reason", "unknown"))
        if project_authority.get("applicable"):
            copied.append(str(destination))
    return list(dict.fromkeys(copied))


def _project_rule_authority_delta(authority_path, target_path):
    """Compare a candidate project with the current manifest project rules.

    A PCB is not a complete route artifact without its sibling project.  In
    particular, silently replacing a seven-class project with KiCad's lone
    ``Default`` class changes track/via geometry while leaving the board bytes
    untouched.  The manifest PCB's project is therefore the minimum authority:
    derived candidates may add classes and bindings, but cannot omit or mutate
    the current ones.
    """
    authority_path = Path(authority_path).resolve()
    target_path = Path(target_path).resolve()
    if not authority_path.is_file():
        return {"schema": 1, "applicable": False, "ok": True,
                "reason": "manifest_project_sidecar_absent",
                "authority": str(authority_path), "target": str(target_path)}
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": 1, "applicable": True, "ok": False,
                "reason": "manifest_project_sidecar_unreadable",
                "authority": str(authority_path), "target": str(target_path),
                "error": "%s: %s" % (type(exc).__name__, exc)}
    target = {}
    target_missing = not target_path.is_file()
    if not target_missing:
        try:
            target = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {"schema": 1, "applicable": True, "ok": False,
                    "reason": "candidate_project_sidecar_unreadable",
                    "authority": str(authority_path),
                    "target": str(target_path),
                    "error": "%s: %s" % (type(exc).__name__, exc)}

    authority_ns = authority.get("net_settings") or {}
    target_ns = target.get("net_settings") or {}
    authority_classes = {
        str(row.get("name")): row
        for row in authority_ns.get("classes") or () if row.get("name")}
    target_classes = {
        str(row.get("name")): row
        for row in target_ns.get("classes") or () if row.get("name")}
    missing_classes = sorted(set(authority_classes) - set(target_classes))
    mismatched_classes = sorted(
        name for name in set(authority_classes) & set(target_classes)
        if authority_classes[name] != target_classes[name])

    authority_patterns = {
        (str(row.get("netclass")), str(row.get("pattern")))
        for row in authority_ns.get("netclass_patterns") or ()
        if row.get("netclass") and row.get("pattern")}
    target_patterns = {
        (str(row.get("netclass")), str(row.get("pattern")))
        for row in target_ns.get("netclass_patterns") or ()
        if row.get("netclass") and row.get("pattern")}
    missing_patterns = sorted(authority_patterns - target_patterns)
    canonical_by_pattern = {
        pattern: netclass for netclass, pattern in authority_patterns}
    conflicting_patterns = sorted(
        (netclass, pattern, canonical_by_pattern[pattern])
        for netclass, pattern in target_patterns
        if pattern in canonical_by_pattern
        and canonical_by_pattern[pattern] != netclass)
    repair_required = bool(
        target_missing or missing_classes or mismatched_classes
        or missing_patterns or conflicting_patterns)
    return {
        "schema": 1, "applicable": True, "ok": True,
        "reason": ("manifest_project_rules_need_staging" if repair_required
                   else "manifest_project_rules_present"),
        "authority": str(authority_path), "target": str(target_path),
        "target_missing": target_missing,
        "repair_required": repair_required,
        "missing_classes": missing_classes,
        "mismatched_classes": mismatched_classes,
        "missing_patterns": [list(row) for row in missing_patterns],
        "conflicting_patterns": [list(row) for row in conflicting_patterns],
    }


def _merge_project_rule_authority(authority_path, target_path):
    """Stage the current manifest rule floor without dropping derived extras."""
    report = _project_rule_authority_delta(authority_path, target_path)
    if not report.get("ok") or not report.get("applicable"):
        return report
    authority_path = Path(authority_path).resolve()
    target_path = Path(target_path).resolve()
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    target = ({} if not target_path.is_file() else
              json.loads(target_path.read_text(encoding="utf-8")))
    before = json.dumps(target, sort_keys=True, separators=(",", ":"))

    authority_ns = authority.get("net_settings") or {}
    target_ns = target.setdefault("net_settings", {})
    authority_classes = list(authority_ns.get("classes") or ())
    authority_names = {
        str(row.get("name")) for row in authority_classes if row.get("name")}
    target_extras = [
        row for row in target_ns.get("classes") or ()
        if str(row.get("name")) not in authority_names]
    target_ns["classes"] = authority_classes + target_extras

    authority_patterns = list(authority_ns.get("netclass_patterns") or ())
    canonical_pattern_text = {
        str(row.get("pattern")) for row in authority_patterns
        if row.get("pattern")}
    target_pattern_extras = [
        row for row in target_ns.get("netclass_patterns") or ()
        if str(row.get("pattern")) not in canonical_pattern_text]
    target_ns["netclass_patterns"] = (
        authority_patterns + target_pattern_extras)
    if "meta" in authority_ns:
        target_ns["meta"] = authority_ns["meta"]
    if "net_colors" in authority_ns and "net_colors" not in target_ns:
        target_ns["net_colors"] = authority_ns["net_colors"]
    authority_assignments = authority_ns.get("netclass_assignments")
    target_assignments = target_ns.get("netclass_assignments")
    if isinstance(authority_assignments, dict):
        merged_assignments = dict(target_assignments or {})
        merged_assignments.update(authority_assignments)
        target_ns["netclass_assignments"] = merged_assignments
    elif "netclass_assignments" not in target_ns:
        target_ns["netclass_assignments"] = authority_assignments

    authority_rules = (((authority.get("board") or {}).get(
        "design_settings") or {}).get("rules"))
    if authority_rules is not None:
        target.setdefault("board", {}).setdefault(
            "design_settings", {})["rules"] = authority_rules
    if authority.get("tuning_profiles") is not None:
        target["tuning_profiles"] = authority["tuning_profiles"]
    target.setdefault("meta", {})["filename"] = target_path.name
    after = json.dumps(target, sort_keys=True, separators=(",", ":"))
    written = after != before
    if written:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(target, indent=2) + "\n", encoding="utf-8")
    report.update({"written": written,
                   "reason": ("manifest_project_rules_staged" if written
                              else "manifest_project_rules_present")})
    return report


def _route_params_for_board(cfg, board):
    """Bind route policy to the executable state beside this exact board.

    Config policy can name the original placement's frozen state.  Canonical
    stages deliberately rename board artifacts, so prefer a copied sibling
    state when present.  This keeps preflight and every route worker on the
    same content-addressed ownership geometry.
    """
    params = dict(getattr(cfg, "params", {}) or {})
    board = Path(board).resolve()
    frozen_state = board.with_name(
        board.name.removesuffix(".kicad_pcb") +
        ".pourfirst-state.json")
    if frozen_state.is_file():
        params["pourfirst_state"] = str(frozen_state)
    return params


def _placement_delta(before, after, *, tolerance_mm=0.01,
                     tolerance_deg=0.01):
    """Return material placement changes between two complete candidates."""
    changes = []
    before = dict(before or {})
    after = dict(after or {})
    for ref in sorted(set(before) | set(after)):
        old = before.get(ref)
        new = after.get(ref)
        if old is None or new is None or len(old) != 3 or len(new) != 3:
            changes.append({"ref": ref, "before": old, "after": new})
            continue
        rotation_delta = abs(((float(new[2]) - float(old[2]) + 180.0)
                              % 360.0) - 180.0)
        if (abs(float(new[0]) - float(old[0])) > tolerance_mm
                or abs(float(new[1]) - float(old[1])) > tolerance_mm
                or rotation_delta > tolerance_deg):
            changes.append({
                "ref": ref,
                "before": [float(value) for value in old],
                "after": [float(value) for value in new],
                "dx_mm": round(float(new[0]) - float(old[0]), 6),
                "dy_mm": round(float(new[1]) - float(old[1]), 6),
                "rotation_delta_deg": round(rotation_delta, 6),
            })
    return changes


def _exact_admit_placement_route_authority(cfg, board, state_path):
    """Prove a frozen placement power state with KiCad's filled copper.

    The territory planner's raster graph is a search authority, not a final
    electrical connectivity engine.  Materialize the frozen zones and vias on
    a disposable copy, fill them in an isolated KiCad process, and require
    every declared current-domain source/sink pad to occupy one component.
    This is intentionally run before routing so an approximate 4/4 path count
    cannot defer a missing connector leg or fill-carved pinch point downstream.
    """
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    state_path = Path(state_path).resolve()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "frozen_state_unreadable",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "state": str(state_path),
        }
    frozen_nets = tuple(state.get("frozen_nets") or ())
    if (state.get("placement_scope") != "complete" or not frozen_nets
            or not state.get("pours") or not state.get("corridors")):
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "complete_frozen_power_authority_missing",
            "state": str(state_path),
        }

    params = dict(cfg.params or {})
    params["pourfirst_state"] = str(state_path)
    try:
        with tempfile.TemporaryDirectory(
                prefix="cec-placement-power-admit-") as work:
            exact_state = Path(work) / "exact-state.json"
            exact_board = Path(work) / "exact-power.kicad_pcb"
            with synth._oracle_env(params), \
                    synth._placement_craft_spawn_output_capture() as capture:
                try:
                    compiled = synth._compile_post_priority_power_state(
                        str(board), [], str(exact_state), str(exact_board))
                except Exception:
                    native_tail = synth._placement_craft_native_tail(capture)
                    raise
    except Exception as exc:                           # noqa: BLE001
        result = {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "exact_filled_power_admission_failed",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "state": str(state_path),
            "protected_nets": list(frozen_nets),
        }
        if locals().get("native_tail"):
            result["native_tail"] = native_tail[-4096:]
        return result

    admission = dict(compiled.get("exact_admission") or {})
    if not admission.get("passed"):
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": (admission.get("reason")
                       or "exact_filled_power_admission_failed"),
            "state": str(state_path),
            "protected_nets": list(frozen_nets),
            "admission": admission,
        }

    # Persist the exact certificate beside the abstract search state.  Route
    # stages still re-admit after adding priority copper, but dashboards and
    # resumable stage journals can now distinguish a merely found raster path
    # from a filled-copper placement authority.
    state["exact_admission"] = admission
    state["exact_admission_context"] = {
        "schema": 1,
        "board_sha256": sha256_file(board),
        "thermal_board_hint": params.get("thermal_board_hint"),
    }
    atomic_json(state_path, state)
    return {
        "schema": 1, "ok": True, "applicable": True,
        "reason": "exact_filled_power_admitted",
        "state": str(state_path),
        "protected_nets": list(frozen_nets),
        "open_before": list(admission.get("open_before") or ()),
        "open_after": list(admission.get("open_after") or ()),
        "exact_before": admission.get("exact_before"),
        "exact_after": admission.get("exact_after"),
        "new_structural_drc": list(
            admission.get("new_structural_drc") or ()),
    }


def _ensure_placement_route_authority(cfg, board):
    """Publish exact pour-first authority for an admitted open placement.

    Placement craft uses the exact power planner as an oracle, but an oracle
    pass alone does not create the route-stage ownership sidecar.  Reusing the
    old uniform-stamp recipe after placement therefore asks preflight to solve
    a different board.  Preserve a matching exact sibling state when one
    exists; otherwise freeze the already-admitted complete placement through
    the ordinary pour-first compiler and persist its state beside the PCB.
    """
    import pcbnew
    import cec_fr
    import cec_synth_pipeline as synth
    from cec_placement_session import PlacementSession

    board = Path(board).resolve()
    if not (cfg.params.get("pour_first") or cfg.params.get("pour_plan")):
        return {"schema": 1, "ok": True, "applicable": False,
                "reason": "power_route_authority_not_requested",
                "_artifacts": []}
    loaded = pcbnew.LoadBoard(str(board))
    if loaded is None:
        return {"schema": 1, "ok": False, "applicable": True,
                "reason": "placement_board_unreadable", "_artifacts": []}
    if any(True for _item in loaded.GetTracks()):
        # Existing routed copper is preserved and audited in place.  This
        # helper owns only the open-placement -> frozen-power transition.
        return {"schema": 1, "ok": True, "applicable": False,
                "reason": "routed_board_preserved", "_artifacts": []}

    _bound, existing = synth.config_with_board_route_authority(
        cfg, str(board))
    replaced_exact_invalid_state = None
    if existing.get("ok") and existing.get("bound"):
        state = Path(existing["state"]).resolve()
        exact = _exact_admit_placement_route_authority(
            cfg, board, state)
        if exact.get("ok"):
            return {**existing, "schema": 1, "reused": True,
                    "exact_admission": exact,
                    "_artifacts": [str(state)]}
        # A state can match every footprint and still carry an old or
        # over-pruned geometry recipe. Rebuild once from the same admitted
        # placement with the current generic planner instead of publishing a
        # stale false authority or requiring a component move.
        replaced_exact_invalid_state = exact

    placement = synth.read_placement(str(board))
    params = dict(cfg.params or {})
    for key in ("pourfirst_state", "pourfirst_outline_mm",
                "pourfirst_seen_placements", "pourfirst_avoid_boxes"):
        params.pop(key, None)
    # Craft admission has already closed on this exact placement.  The freeze
    # must record its geometry, not launch a second placement optimizer.
    params["pourfirst_craft_trials"] = 0
    session = PlacementSession(
        cfg.board, W=placement.W, H=placement.H,
        profile=cfg.profile, params=params, pins=dict(cfg.pins or {}),
        strat="rehydrated-placement", seed=0)
    candidate = synth.placement_candidate_from_board(
        session.cfg, str(board))
    structural = set(session.anchors_roles) | set(session.shunts)
    if not structural:
        structural = set(candidate.P)
    candidate.pourfirst_anchor_refs = tuple(sorted(structural))
    candidate.pourfirst_structural_refs = tuple(sorted(structural))
    report = synth.pour_first_stage(
        session, label="canonical-%s" % cfg.board,
        artifact=False, candidate=candidate)
    if report.get("error") or not report.get("state"):
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "exact_route_authority_freeze_failed",
            "error": report.get("error") or "missing state",
            "planner": report, "_artifacts": [],
        }

    # The exact current-corridor transaction may discover that a bounded
    # anchor/cell move is required to make the filled copper physically
    # possible.  That winning placement and its frozen state are one atomic
    # result.  Publishing only the JSON state left the PCB at the losing
    # coordinate and guaranteed a self-inflicted contract mismatch on the
    # very next exact-admission call.
    winning_candidate = getattr(
        session, "pourfirst_candidate", None) or candidate
    placement_delta = _placement_delta(
        candidate.P, winning_candidate.P)
    if placement_delta:
        synth.materialize(winning_candidate, session.cfg, str(board))

    source_state = Path(report["state"]).resolve()
    state = json.loads(source_state.read_text(encoding="utf-8"))
    artifacts = []
    source_skeleton = Path(str(state.get("skeleton") or ""))
    if source_skeleton.is_file():
        stable_skeleton = board.with_name(
            board.stem + ".pourfirst-skeleton.kicad_pcb")
        shutil.copy2(source_skeleton, stable_skeleton)
        artifacts.append(str(stable_skeleton))
        artifacts.extend(cec_fr.copy_project_sidecars(
            str(source_skeleton), str(stable_skeleton)))
        state["skeleton"] = str(stable_skeleton)
    stable_state = board.with_name(board.stem + ".pourfirst-state.json")
    atomic_json(stable_state, state)
    artifacts.append(str(stable_state))
    cfg.params["pourfirst_state"] = str(stable_state)

    exact = _exact_admit_placement_route_authority(
        cfg, board, stable_state)

    _bound, verified = synth.config_with_board_route_authority(
        cfg, str(board))
    verified.update({
        "schema": 1, "reused": False,
        "placement_changed": bool(placement_delta),
        "placement_delta": placement_delta,
        "exact_admission": exact,
        "replaced_exact_invalid_state": replaced_exact_invalid_state,
        "planner": {
            "path_found": report.get("path_found") or [],
            "no_path": report.get("no_path") or [],
            "frozen_nets": report.get("frozen_nets") or [],
            "corridor_rects": report.get("corridor_rects"),
            "bridge_vias": report.get("bridge_vias"),
            "wall_s": report.get("wall_s"),
        },
        "_artifacts": list(dict.fromkeys(artifacts)),
    })
    if not exact.get("ok"):
        verified.update({
            "ok": False,
            "reason": "exact_filled_power_admission_failed",
        })
    return verified


def _source_files(cfg, input_board):
    paths = [Path(input_board).resolve(), Path(cfg.sch).resolve()]
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_sch")))
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_pro")))
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_dru")))
    paths.extend(sorted(Path(cfg.dir).glob("pipeline-policy.json")))
    paths.extend(sorted((Path(cfg.dir) / "bom").glob("*.csv")))
    return sorted({path for path in paths if path.is_file()})


def _files_signature(paths, *, root=ROOT):
    rows = []
    for path in sorted(Path(path).resolve() for path in paths):
        try:
            name = str(path.relative_to(root.resolve()))
        except ValueError:
            name = str(path)
        rows.append({
            "path": name, "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {"sha256": digest_value(rows), "files": rows}


def _code_signature(*names):
    paths = [HERE / name for name in names]
    return _files_signature([path for path in paths if path.is_file()])["sha256"]


def _callable_signature(*functions):
    """Hash a stage wrapper and its same-module callable closure.

    Hashing only the wrapper body misses edits to helpers called by that
    wrapper; placement then resumed stale evidence after its power-replan
    publisher changed. Hashing the entire coordinator over-invalidates every
    stage for an unrelated route/signoff edit. Follow direct same-module call
    names recursively to get the dependency boundary intended by the journal.
    Imported implementation modules remain owned by ``_code*_signature``.
    """
    rows = []
    by_file = {}
    for function in functions:
        path = Path(inspect.getsourcefile(function) or "").resolve()
        by_file.setdefault(path, set()).add(function.__name__)
    for path, roots in sorted(by_file.items(), key=lambda row: str(row[0])):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        definitions = {
            node.name: node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        pending = list(sorted(roots))
        found = set()
        while pending:
            name = pending.pop()
            if name in found or name not in definitions:
                continue
            found.add(name)
            node = definitions[name]
            for child in ast.walk(node):
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id in definitions
                        and child.func.id not in found):
                    pending.append(child.func.id)
        rows.extend({
            "module": str(path), "qualname": name,
            "source": ast.get_source_segment(source, definitions[name]),
        } for name in sorted(found))
    return digest_value(rows)


def _local_code_closure(*names):
    """Return the recursive local Python import closure for stage entry files.

    A resumable stage is only content addressed if edits to its transitive
    implementation dependencies invalidate the journal.  Curated flat lists
    missed ``cec_fr.py`` beneath the synthesis coordinator and reused a stale
    route after a router fix.  Parse imports (including function-local imports)
    and follow every module that resolves beside this coordinator.
    """
    pending = [HERE / name for name in names]
    found = set()
    while pending:
        path = pending.pop()
        if not path.is_file():
            continue
        path = path.resolve()
        if path in found:
            continue
        found.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for module in modules:
            candidate = HERE / (module.split(".", 1)[0] + ".py")
            if candidate.is_file() and candidate.resolve() not in found:
                pending.append(candidate)
    return tuple(sorted(found))


def _code_closure_signature(*names):
    return _files_signature(_local_code_closure(*names))["sha256"]


def _source_intake(cfg, input_board, report_path, *, allow_derived_input=False):
    import cec_beta_electrical_audit
    import cec_beta_manifest
    import cec_constraints
    import cec_generalization_gate

    manifest_errors = []
    board_key = _board_identity(cfg)
    manifest_entry = cec_beta_manifest.BY_BOARD.get(board_key)
    if manifest_entry is None:
        manifest_errors.append(
            "%s is not in the authoritative current-BETA manifest" % board_key
        )
    else:
        expected = (ROOT / "beta" / manifest_entry["directory"]).resolve()
        if Path(cfg.dir).resolve() != expected:
            manifest_errors.append(
                "configuration resolved %s, expected current BETA %s" % (
                    Path(cfg.dir).resolve(), expected
                )
            )
        expected_schematic = expected / manifest_entry["schematic"]
        if Path(cfg.sch).resolve() != expected_schematic.resolve():
            manifest_errors.append(
                "root schematic is not the manifest root: %s" % cfg.sch
            )

    canonical_board = Path(cfg.pcb).resolve() if cfg.pcb else None
    canonical_input = bool(
        canonical_board is not None
        and Path(input_board).resolve() == canonical_board)
    if canonical_board is not None and not canonical_input \
            and not allow_derived_input:
        manifest_errors.append(
            "input board is not the current manifest PCB: %s (got %s); "
            "derived/probe artifacts require explicit allow_derived_input"
            % (canonical_board, Path(input_board).resolve())
        )

    route_geometry_deferred = bool(allow_derived_input and not canonical_input)
    project_rule_authority = _project_rule_authority_delta(
        (canonical_board.with_suffix(".kicad_pro")
         if canonical_board is not None else
         Path(input_board).resolve().with_suffix(".kicad_pro")),
        Path(input_board).resolve().with_suffix(".kicad_pro"),
    )
    intake = cec_constraints.intake_gate(
        str(input_board), {"sch": str(cfg.sch)},
        defer_route_geometry=route_geometry_deferred,
    )
    generalization = cec_generalization_gate.audit(ROOT)
    try:
        platform_electrical = cec_beta_electrical_audit.audit(
            str(ROOT / "beta"))
        electrical_findings = [
            row for row in platform_electrical.get("findings", ())
            if board_key in {
                name.strip()
                for name in str(row.get("board", "")).split("+")
                if name.strip()
            }
        ]
        electrical_blockers = [
            row for row in electrical_findings
            if row.get("severity") == "BLOCKER"
        ]
        electrical = {
            "ok": not electrical_blockers,
            "blocker_count": len(electrical_blockers),
            "warning_count": sum(
                row.get("severity") == "WARN" for row in electrical_findings),
            "findings": electrical_findings,
            "reasons": [
                "%s%s: %s" % (
                    row.get("code", "ELECTRICAL"),
                    (" " + row["ref"]) if row.get("ref") else "",
                    row.get("message", "source electrical audit failed"),
                ) for row in electrical_blockers
            ],
        }
    except Exception as exc:                              # noqa: BLE001
        electrical = {
            "ok": False,
            "blocker_count": 1,
            "warning_count": 0,
            "findings": [],
            "reasons": ["electrical audit crashed: %s: %s" % (
                type(exc).__name__, exc)],
        }
    report = {
        "schema": SCHEMA,
        "board": board_key,
        "root_schematic": str(Path(cfg.sch).resolve()),
        "hierarchical_sheet_count": len(list(Path(cfg.dir).glob("*.kicad_sch"))),
        "manifest_errors": manifest_errors,
        "canonical_board": (str(canonical_board)
                            if canonical_board is not None else None),
        "canonical_input": canonical_input,
        "derived_input_allowed": bool(allow_derived_input),
        "route_geometry_deferred": route_geometry_deferred,
        "project_rule_authority": project_rule_authority,
        "intake": intake,
        "electrical_source_audit": electrical,
        "generalization_gate": generalization,
        "draft": cfg.is_draft,
        "ok": (not manifest_errors and bool(project_rule_authority.get("ok"))
               and bool(intake.get("ok"))
               and bool(electrical.get("ok"))
               and bool(generalization.get("ok"))),
    }
    atomic_json(report_path, report)
    return report


PLACEMENT_CONSTRAINT_CATEGORIES = frozenset({"placement", "mechanical"})

# Historical registry categories describe the design concern, not always the
# earliest stage at which the checker can produce meaningful evidence.  These
# checks require routed copper and therefore cannot reject an otherwise valid
# placement before the route/repair stage has run.  They remain hard/strong at
# post-route and release; this only corrects their stage ownership.
PLACEMENT_ROUTE_TIME_IDS = frozenset({
    "board-routing-complete",
    "ic-power-ground-connected",
    "trace-width-high-current",
})


def _placement_constraint_gate(board, cfg):
    """Hoist deterministic placement/mechanical contracts before routing.

    The full release gate also contains route-only EMC checks, so running it on
    an intentionally unrouted placement would be a false refusal.  Category
    ownership lets this stage admit only constraints it can already prove,
    while the complete gate remains authoritative after routing.
    """
    import cec_constraints

    try:
        rows = cec_constraints.run(str(board), {"sch": str(cfg.sch)})
        blocked = [
            (constraint, status, detail)
            for constraint, status, detail, _payload in rows
            if constraint.category in PLACEMENT_CONSTRAINT_CATEGORIES
            and constraint.id not in PLACEMENT_ROUTE_TIME_IDS
            and constraint.status == "ratified"
            and constraint.checkable == "yes"
            and constraint.severity in ("hard", "strong")
            and status in ("FAIL", "ERROR")
        ]
        return {
            "ok": not blocked,
            "phase": "placement",
            "categories": sorted(PLACEMENT_CONSTRAINT_CATEGORIES),
            "checked": sum(
                constraint.category in PLACEMENT_CONSTRAINT_CATEGORIES
                and constraint.id not in PLACEMENT_ROUTE_TIME_IDS
                for constraint, _status, _detail, _payload in rows),
            "blockers": [
                {"id": constraint.id, "category": constraint.category,
                 "severity": constraint.severity, "status": status,
                 "detail": detail}
                for constraint, status, detail in blocked
            ],
        }
    except Exception as exc:                              # noqa: BLE001
        return {
            "ok": False, "phase": "placement",
            "categories": sorted(PLACEMENT_CONSTRAINT_CATEGORIES),
            "checked": 0,
            "blockers": [{
                "id": "placement-constraint-gate", "category": "placement",
                "severity": "hard", "status": "ERROR",
                "detail": "%s: %s" % (type(exc).__name__, exc),
            }],
        }


def _placement_craft_gate(evidence, *, routed_input):
    """Admit routed seeds whose only craft defect is repairable local copper.

    The decoupler oracle intentionally checks both component geometry and the
    immediate routed supply/return cell.  On an unrouted placement both are
    placement-owned.  On an explicitly preserved routed seed, an assigned
    capacitor with legal geometry may fail solely because old copper occupies
    every dogbone/via site; that must reach the route repair stage.  Missing,
    distant, or bad-return placement remains blocking.
    """
    import cec_synth_pipeline as synth
    return synth.placement_craft_admission(
        evidence, allow_route_access_repair=bool(routed_input))


def _frozen_placement_contract(board_path, *, tolerance_mm=0.01):
    """Validate a complete pour-first placement beside ``board_path``.

    A complete frozen state is a placement authority, not merely a routing
    hint.  Generic clean-margin optimization must not move components after
    the power geometry was solved.  Explicit post-freeze repairs (fiducials,
    service connectors, and their electrically owned followers) update the
    sibling state transactionally and are checked again at stage admission.
    """
    import pcbnew

    board_path = Path(board_path).resolve()
    state_path = board_path.with_name(
        board_path.name.removesuffix(".kicad_pcb")
        + ".pourfirst-state.json")
    if not state_path.is_file():
        return {"schema": 1, "applicable": False, "ok": True,
                "reason": "no_sibling_state"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": 1, "applicable": True, "ok": False,
                "state": str(state_path), "reason": "state_unreadable",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    if state.get("placement_scope") != "complete":
        return {"schema": 1, "applicable": False, "ok": True,
                "state": str(state_path),
                "reason": "state_is_not_complete_placement_authority"}
    placements = state.get("placements")
    if not isinstance(placements, dict) or not placements:
        return {"schema": 1, "applicable": True, "ok": False,
                "state": str(state_path),
                "reason": "complete_state_has_no_placements"}

    board = pcbnew.LoadBoard(str(board_path))
    mismatches = []
    for ref, expected in sorted(placements.items()):
        footprint = board.FindFootprintByReference(str(ref))
        if (footprint is None or not isinstance(expected, (list, tuple))
                or len(expected) != 3):
            mismatches.append({"ref": str(ref), "reason": "missing"})
            continue
        position = footprint.GetPosition()
        actual = [position.x / 1e6, position.y / 1e6,
                  float(footprint.GetOrientationDegrees())]
        rotation_delta = abs(
            ((actual[2] - float(expected[2]) + 180.0) % 360.0) - 180.0)
        if (abs(actual[0] - float(expected[0])) > tolerance_mm
                or abs(actual[1] - float(expected[1])) > tolerance_mm
                or rotation_delta > 0.01):
            mismatches.append({"ref": str(ref),
                               "expected": list(expected),
                               "actual": actual})
    return {"schema": 1, "applicable": True,
            "ok": not mismatches, "state": str(state_path),
            "placements": len(placements),
            "mismatches": mismatches[:24]}


def _sync_safe_postfreeze_placement_delta(board_path, *, clearance_mm=0.3):
    """Commit a craft repair that provably cannot invalidate frozen power.

    The complete state is normally immutable.  A placement-craft blocker may
    still be repaired after it exists when every moved footprint is foreign to
    the frozen nets and its new courtyard clears exact F.Cu power territory
    and every through-via reservation.  Only then is the placement snapshot
    updated atomically.  Anything ambiguous remains a hard placement failure.
    """
    import cec_synth_pipeline as synth
    import pcbnew

    board_path = Path(board_path).resolve()
    state_path = board_path.with_name(
        board_path.name.removesuffix(".kicad_pcb")
        + ".pourfirst-state.json")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": 1, "ok": False, "updated": False,
                "reason": "state_unreadable",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    placements = state.get("placements")
    if (state.get("placement_scope") != "complete"
            or not isinstance(placements, dict)):
        return {"schema": 1, "ok": False, "updated": False,
                "reason": "not_complete_placement_authority"}

    board = pcbnew.LoadBoard(str(board_path))
    frozen_nets = {str(net) for net in state.get("frozen_nets") or ()}
    changed = []
    for ref, expected in sorted(placements.items()):
        footprint = board.FindFootprintByReference(str(ref))
        if footprint is None or not isinstance(expected, (list, tuple)) \
                or len(expected) != 3:
            return {"schema": 1, "ok": False, "updated": False,
                    "reason": "placement_identity_changed", "ref": str(ref)}
        position = footprint.GetPosition()
        actual = [position.x / 1e6, position.y / 1e6,
                  float(footprint.GetOrientationDegrees())]
        rotation_delta = abs(
            ((actual[2] - float(expected[2]) + 180.0) % 360.0) - 180.0)
        if (abs(actual[0] - float(expected[0])) > 0.01
                or abs(actual[1] - float(expected[1])) > 0.01
                or rotation_delta > 0.01):
            changed.append((str(ref), footprint, actual))
    if not changed:
        return {"schema": 1, "ok": True, "updated": False,
                "reason": "no_delta", "refs": []}

    avoid = list(synth._pourfirst_exact_avoid_boxes(
        state.get("pours") or ()))
    # Frozen bridge vias occupy every copper layer.  The state schema does
    # not require a diameter on historical files, so reserve a conservative
    # 0.8 mm land plus the same clearance used for pour territory.
    for via in state.get("vias") or ():
        if via.get("x_mm") is None or via.get("y_mm") is None:
            continue
        radius = max(0.4, float(via.get("diameter_mm") or 0.0) / 2.0)
        x, y = float(via["x_mm"]), float(via["y_mm"])
        avoid.append({"kind": "bridge_via", "net": via.get("net"),
                      "x0": x - radius, "x1": x + radius,
                      "y0": y - radius, "y1": y + radius})

    clearance = max(0.0, float(clearance_mm))
    refused = []
    for ref, footprint, actual in changed:
        pad_nets = {str(pad.GetNetname()) for pad in footprint.Pads()
                    if str(pad.GetNetname())}
        owned = sorted(pad_nets & frozen_nets)
        if owned:
            refused.append({"ref": ref, "reason": "owns_frozen_net",
                            "nets": owned})
            continue
        x0, x1, y0, y1 = synth._footprint_courtyard_box(footprint)
        hits = []
        for row in avoid:
            if (x1 + clearance <= float(row["x0"])
                    or float(row["x1"]) <= x0 - clearance
                    or y1 + clearance <= float(row["y0"])
                    or float(row["y1"]) <= y0 - clearance):
                continue
            hits.append({"kind": row.get("kind"), "net": row.get("net")})
        if hits:
            refused.append({"ref": ref,
                            "reason": "new_courtyard_hits_frozen_power",
                            "hits": hits[:8]})
    if refused:
        return {"schema": 1, "ok": False, "updated": False,
                "reason": "postfreeze_delta_not_power_independent",
                "refused": refused}

    for ref, _footprint, actual in changed:
        placements[ref] = actual
    scratch = state_path.with_name(".%s.tmp-%d" %
                                   (state_path.name, os.getpid()))
    try:
        scratch.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
        os.replace(scratch, state_path)
    finally:
        if scratch.exists():
            scratch.unlink()
    return {"schema": 1, "ok": True, "updated": True,
            "state": str(state_path),
            "refs": [ref for ref, _footprint, _actual in changed]}


def _route_access_repair_allowed(intake, placement):
    """Derived route geometry remains repair-owned even with clean craft.

    The earlier handoff keyed this only to a decoupler-access deferral.  A
    routed seed with good local bypass geometry but foreign-on-pour copper then
    reached the route oracle with repair disabled, despite intake explicitly
    naming route geometry as deferred.  Either authority is sufficient.
    """
    return bool(
        (intake or {}).get("route_geometry_deferred")
        or ((placement or {}).get("craft_gate") or {}).get(
            "deferred_to_route"))


def _placement_fiducials_reconsiderable(board, *, replace=False):
    """Allow free corner-band fiducial seating on every open placement.

    ``--replace-placement`` is sufficient but not necessary: a resumed open
    placement is still placement-owned, and forcing signals to detour around a
    stale fiducial reverses that ownership. Existing routed copper remains a
    strict byte-preservation boundary.
    """
    if replace:
        return True
    import pcbnew
    loaded = pcbnew.LoadBoard(str(Path(board).resolve()))
    return bool(loaded is not None
                and not any(True for _item in loaded.GetTracks()))


def _transactional_fiducial_edge_repair(cfg, board, *, reconsider_all=False):
    """Move open-placement fiducials only when exact craft does not regress.

    Airwire pressure is a useful ranker but does not know the final width of a
    parallel current bundle.  A candidate corner site can therefore look
    cheaper while closing a just-repaired power corridor.  Snapshot both the
    PCB and its optional placement-authority state, apply the ordinary generic
    fiducial repair, and compare complete fast exact-craft keys.  Any
    regression restores the byte-identical pre-move artifacts; the final full
    diagnostic pass remains independently authoritative.
    """
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    stem = (str(board)[:-len(".kicad_pcb")]
            if str(board).endswith(".kicad_pcb") else str(board))
    state = Path(stem + ".pourfirst-state.json")
    before_evidence = synth.placement_craft_evidence(
        str(board), cfg=cfg, relief_diagnostics=False)
    before_key = tuple(synth.placement_craft_key(before_evidence))
    with tempfile.TemporaryDirectory(prefix="cec-fiducial-transaction-") \
            as scratch:
        scratch = Path(scratch)
        board_snapshot = scratch / board.name
        shutil.copy2(board, board_snapshot)
        state_existed = state.is_file()
        state_snapshot = scratch / state.name
        if state_existed:
            shutil.copy2(state, state_snapshot)
        repair = synth.repair_fiducials_to_edge_band(
            str(board), reconsider_all=bool(reconsider_all))
        if not repair.get("changed") or not repair.get("ok"):
            repair["craft_guard"] = {
                "applicable": False,
                "reason": ("unchanged" if repair.get("ok")
                           else "repair_failed"),
                "before_key": list(before_key),
            }
            return repair
        after_evidence = synth.placement_craft_evidence(
            str(board), cfg=cfg, relief_diagnostics=False)
        after_key = tuple(synth.placement_craft_key(after_evidence))
        guard = {
            "applicable": True,
            "before_key": list(before_key),
            "proposed_key": list(after_key),
            "accepted": after_key <= before_key,
        }
        if after_key > before_key:
            shutil.copy2(board_snapshot, board)
            if state_existed:
                shutil.copy2(state_snapshot, state)
            elif state.exists():
                state.unlink()
            rejected = list(repair.get("moved") or ())
            repair.update({
                "changed": False,
                "rolled_back": True,
                "rollback_reason": "exact_craft_regression",
                "rejected_moves": rejected,
                "moved": [],
                "craft_guard": guard,
            })
            return repair
        repair["craft_guard"] = guard
        return repair


def _bounded_post_fiducial_craft_repair(
        cfg, board, fiducial_repair, *, max_trials, rounds, epochs):
    """Give a changed fiducial layout one bounded electrical legalization.

    Global fiducial selection intentionally runs after ordinary placement
    craft.  Moving a datum can expose the next exact current-corridor cut even
    when the aggregate craft key does not regress, so merely re-measuring the
    board leaves that newly actionable cut stranded at admission.  On an open
    placement only, run the normal generic craft repair once against the
    post-fiducial artifact.  The existing repair engine is transactional and
    monotonic; this wrapper adds a strict one-shot ordering boundary rather
    than an unbounded placement/fiducial loop.
    """
    import pcbnew
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    if not (fiducial_repair or {}).get("ok"):
        return {"schema": 1, "ok": False, "changed": False,
                "applicable": False, "reason": "fiducial_repair_failed"}
    if not (fiducial_repair or {}).get("changed"):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False, "reason": "fiducials_unchanged"}
    loaded = pcbnew.LoadBoard(str(board))
    if loaded is None:
        return {"schema": 1, "ok": False, "changed": False,
                "applicable": False, "reason": "board_unloadable"}
    if any(True for _item in loaded.GetTracks()):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False,
                "reason": "routed_board_preserved"}

    before = synth.placement_craft_evidence(str(board), cfg=cfg)
    if before.get("ok"):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": True, "reason": "post_fiducial_craft_clean",
                "before_key": list(synth.placement_craft_key(before))}

    signature_before = _placement_position_signature(board)
    candidate = synth.placement_candidate_from_board(cfg, str(board))
    candidate, repair = synth.repair_placement_craft_epochs(
        cfg, candidate, max_trials=int(max_trials), rounds=int(rounds),
        epochs=int(epochs))
    if repair.get("changed"):
        synth.materialize(candidate, cfg, str(board))
    after = synth.placement_craft_evidence(str(board), cfg=cfg)
    signature_after = _placement_position_signature(board)
    result = dict(repair)
    result.update({
        "schema": 1,
        "applicable": True,
        "one_shot": True,
        "before_key": list(synth.placement_craft_key(before)),
        "after_key": list(synth.placement_craft_key(after)),
        "after_ok": bool(after.get("ok")),
        "placement_signature_before": signature_before,
        "placement_signature_after": signature_after,
        "repeated_placement": signature_after == signature_before,
    })
    return result


def _finalize_fiducials_after_route_authority(
        cfg, board, *, priority_applicable=False):
    """Seat optical datums after constrained placement and exact power.

    Fiducials are deliberately late mechanical features.  They may use any
    legal open corner sector, but they may not make the exact current-copper
    authority rebuild or move a component and may not break an important-route
    hard gate.  Snapshot the complete placement/power family, try the global
    reseat, exact-admit that same authority, and roll the family back on any
    dependency.  This establishes a generic ordering boundary instead of a
    board-specific coordinate override.
    """
    import cec_synth_pipeline as synth

    board = Path(board).resolve()

    def rebind_config():
        bound, report = synth.config_with_board_route_authority(
            cfg, str(board))
        if report.get("ok") and report.get("bound"):
            cfg.params = dict(bound.params)
        return report

    with tempfile.TemporaryDirectory(
            prefix="cec-fiducials-last-") as scratch:
        snapshot = Path(scratch) / "before"
        _snapshot_placement_authority(board, snapshot)
        repair = _transactional_fiducial_edge_repair(
            cfg, board, reconsider_all=True)
        result = {
            "schema": 1,
            "ok": bool(repair.get("ok")),
            "applicable": True,
            "changed": bool(repair.get("changed")),
            "accepted": False,
            "repair": repair,
        }
        if not repair.get("ok") or not repair.get("changed"):
            result["reason"] = (
                "repair_failed" if not repair.get("ok") else
                "globally_optimal_sites_already_seated")
            result["authority_binding"] = rebind_config()
            return result

        authority = _ensure_placement_route_authority(cfg, board)
        applicable = bool(authority.get("applicable", True))
        exact_independent = bool(
            authority.get("ok")
            and (not applicable or (
                authority.get("reused") is True
                and not authority.get("placement_changed"))))
        priority_evidence = {}
        priority_gate = {"schema": 1, "ok": True, "applicable": False}
        if exact_independent and priority_applicable:
            priority_evidence = _measure_placement_priority_routes(
                cfg, board)
            priority_gate = _placement_priority_route_gate(
                priority_evidence, applicable=True)
        accepted = bool(exact_independent and priority_gate.get("ok"))
        if not accepted:
            _restore_placement_authority(board, snapshot)
            binding = rebind_config()
            result.update({
                "ok": True,
                "changed": False,
                "rolled_back": True,
                "reason": (
                    "exact_power_dependency" if not exact_independent
                    else "important_route_gate_regression"),
                "proposed_authority": {
                    key: value for key, value in authority.items()
                    if key != "_artifacts"},
                "proposed_priority_gate": priority_gate,
                "authority_binding": binding,
            })
            return result

        binding = rebind_config()
        result.update({
            "ok": True,
            "accepted": True,
            "reason": "late_global_fiducial_set_exactly_admitted",
            "route_authority": authority,
            "priority_route_evidence": priority_evidence,
            "priority_route_gate": priority_gate,
            "authority_binding": binding,
        })
        return result


def _placement_priority_route_gate(evidence, *, applicable=True):
    """Admit placement only when its important-route launch is feasible.

    Ordinary straight-ray warnings remain useful ranking evidence: a detailed
    router can often reach those pads with a bend.  Declared critical routes,
    critical pin escapes, BGA/package fanout, and critical negotiated
    reachability are different.  Those are placement-owned requirements and
    must close before residual routing is allowed to spend time.
    """
    if not applicable:
        return {"schema": 1, "ok": True, "applicable": False,
                "reason": "routed_board_preserved", "blockers": []}
    evidence = dict(evidence or {})
    if evidence.get("error"):
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "placement_route_evidence_error",
            "blockers": [{"term": "analysis", "count": 1,
                          "detail": str(evidence.get("error"))}],
        }
    terms = (
        ("critical_route_refused_count", "declared_priority_route"),
        ("critical_declaration_error_count", "critical_net_declaration"),
        ("critical_pin_access_blocked_count", "critical_pin_escape"),
        ("critical_unroutable_count", "critical_global_reachability"),
        ("fanout_blocked_count", "package_fanout"),
    )
    blockers = []
    for field, term in terms:
        count = int(evidence.get(field, 0) or 0)
        if count:
            blockers.append({"term": term, "field": field, "count": count})
    return {
        "schema": 1, "ok": not blockers, "applicable": True,
        "reason": ("important_routes_feasible" if not blockers else
                   "important_route_placement_blocked"),
        "blockers": blockers,
        "evidence_key": [
            int(evidence.get(field, 0) or 0) for field, _term in terms],
    }


def _compact_priority_repair_round_history(report):
    """Expose why each bounded route-placement round stopped.

    Full per-pad craft evidence remains on the repair report. Co-optimization
    history needs a small causal index so a dashboard or unattended manager
    can identify the responsible stage without loading megabytes of repeated
    geometry certificates.
    """
    summaries = []
    for round_report in (report or {}).get("rounds") or ():
        zero_refusal = []
        for row in round_report.get("kelvin_probe_results") or ():
            if int(row.get("critical_route_refused_count", 1) or 0) == 0:
                zero_refusal.append({
                    "move_index": row.get("move_index"),
                    "kind": row.get("kind"),
                    "refs": list(row.get("refs") or ()),
                })
        craft_rejected = []
        for row in round_report.get("finalist_craft_rejected") or ():
            craft = row.get("craft") or {}
            failed_terms = [
                term for term in (
                    "decoupler", "stranded", "detection_cell",
                    "pair_launch", "critical_terminal_order",
                    "pour_territory", "power_body_clearance")
                if isinstance(craft.get(term), dict)
                and not craft[term].get("ok")
            ]
            craft_rejected.append({
                "move_index": row.get("move_index"),
                "kind": row.get("kind"),
                "refs": list(row.get("refs") or ()),
                "failed_terms": failed_terms,
                "baseline_key": list(row.get("baseline_key") or ()),
                "candidate_key": list(row.get("candidate_key") or ()),
            })
        summaries.append({
            "round": round_report.get("round"),
            "reason": round_report.get("reason"),
            "attempted": int(round_report.get("attempted", 0) or 0),
            "legal": int(round_report.get("legal", 0) or 0),
            "kelvin_screened": int(
                round_report.get("kelvin_screened", 0) or 0),
            "pair_probed": int(round_report.get("pair_probed", 0) or 0),
            "full_evaluated": int(
                round_report.get("full_evaluated", 0) or 0),
            "accepted": bool(round_report.get("accepted")),
            "move_space": dict(round_report.get("move_space") or {}),
            "zero_refusal_candidates": zero_refusal,
            "stale_power_handoffs": list(
                round_report.get("finalist_stale_power_handoff") or ()),
            "craft_rejected": craft_rejected,
            "macro_legalization_rejected_count": len(
                round_report.get("macro_legalization_rejected") or ()),
            "power_replan_candidate_count": len(
                round_report.get("power_replan_candidates") or ()),
            "timing_s": dict(round_report.get("timing_s") or {}),
        })
    return summaries


def _repair_placement_priority_routes(cfg, board, *, completion_report=None):
    """Run the existing exact route-placement repair on an open board.

    This adapter is intentionally board-neutral.  It rehydrates the complete
    placement, binds the exact sibling power authority, and lets failure
    certificates name the movable endpoint/blocker groups.  The repair engine
    remains the admission owner: every proposal must be physically legal,
    preserve placement craft, and strictly improve the complete exact route
    evidence key.
    """
    import pcbnew
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    loaded = pcbnew.LoadBoard(str(board))
    if loaded is None:
        return {"schema": 1, "ok": False, "changed": False,
                "reason": "placement_board_unreadable"}
    if any(True for _item in loaded.GetTracks()):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False, "reason": "routed_board_preserved"}
    trials = int(cfg.params.get("placement_route_repair_trials", 0) or 0)
    rounds = int(cfg.params.get("placement_route_repair_rounds", 0) or 0)
    if trials <= 0 or rounds <= 0:
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False, "reason": "policy_disabled"}

    bound, authority = synth.config_with_board_route_authority(
        cfg, str(board))
    requires_power_authority = bool(
        cfg.params.get("pour_first") or cfg.params.get("pour_plan"))
    if (not authority.get("ok")
            or (requires_power_authority and not authority.get("bound"))):
        return {
            "schema": 1, "ok": False, "changed": False,
            "applicable": True,
            "reason": "exact_route_authority_not_bound",
            "route_authority": authority,
        }
    candidate = synth.placement_candidate_from_board(bound, str(board))
    # A disposable placement microvariant must not inherit the detailed
    # router's 240-second per-pair effort.  Keep this on the copied/bound
    # analysis config only; production preflight and detailed routing retain
    # their independent full precision budget.
    bound.params["placement_route_pair_timeout_s"] = float(cfg.params.get(
        "placement_route_pair_timeout_s", 120.0) or 120.0)
    with synth._oracle_env(bound.params), \
            synth._placement_route_preflight_env():
        repaired, report = synth.repair_route_preflight_iterative(
            bound, candidate, max_trials=trials, rounds=rounds,
            full_evals=int(cfg.params.get(
                "placement_route_repair_full_evals", 4) or 4),
            grid_mm=float(cfg.params.get(
                "placement_route_preflight_grid_mm", 1.0) or 1.0),
            iters=int(cfg.params.get(
                "placement_route_preflight_iters", 4) or 4),
            backend=str(cfg.params.get(
                "placement_route_preflight_backend", "auto")),
            multiresolution=bool(cfg.params.get(
                "placement_route_preflight_multiresolution", True)),
            completion_report=completion_report)
    if report.get("changed"):
        synth.materialize(repaired, bound, str(board))
    evidence = dict(getattr(repaired, "route_preflight", {}) or {})
    return {
        **report,
        "schema": 1,
        "ok": not bool(evidence.get("error")),
        "applicable": True,
        "result_evidence": evidence,
        "route_authority": authority,
    }


def _repair_placement_priority_routes_with_power_replan(
        cfg, board, ordinary_report):
    """Evaluate physically legal moves that conflict only with stale power.

    The ordinary repair correctly refuses to place signal components inside
    the current exact power territory.  Some of those destinations are legal
    after the power planner is rerun for the new placement, however.  Evaluate
    only the bounded handoff exported by that repair, regenerate exact power
    for every microvariant, and accept only a complete post-authority key
    improvement.  This never routes a signal over a pour and never weakens the
    ordinary collision gate.
    """
    import cec_route_preflight
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    rows = []
    seen = set()
    for round_report in (ordinary_report.get("rounds") or ()):
        for row in (round_report.get("power_replan_candidates") or ()):
            placements = row.get("placements") or {}
            signature = json.dumps(
                placements, sort_keys=True, separators=(",", ":"))
            if not placements or signature in seen:
                continue
            seen.add(signature)
            rows.append(dict(row))
    limit = max(0, int(cfg.params.get(
        "placement_power_replan_candidates", 2) or 2))
    rows = rows[:limit]
    report = {
        "schema": 1, "attempted": len(rows), "evaluated": 0,
        "accepted": False, "changed": False,
        "baseline_key": list(ordinary_report.get("result_key")
                             or ordinary_report.get("baseline_key") or ()),
        "trials": [],
    }
    if not rows:
        report["reason"] = "no_stale_power_only_candidate"
        return {**ordinary_report, "power_replan": report}

    baseline_key = tuple(report["baseline_key"])
    best = None
    power_keys = ("pourfirst_state", "pourfirst_outline_mm",
                  "pourfirst_seen_placements", "pourfirst_avoid_boxes")
    with tempfile.TemporaryDirectory(
            prefix="cec-placement-power-replan-") as work:
        work = Path(work)
        for index, row in enumerate(rows):
            started = time.monotonic()
            trial_cfg = copy.deepcopy(cfg)
            for key in power_keys:
                trial_cfg.params.pop(key, None)
            candidate = synth.placement_candidate_from_board(
                trial_cfg, str(board))
            candidate.P.update({
                str(ref): tuple(float(value) for value in position)
                for ref, position in (row.get("placements") or {}).items()
            })
            trial_board = work / ("trial-%02d.kicad_pcb" % index)
            trial_report = {
                "index": index,
                "kind": row.get("kind"),
                "source_kind": row.get("source_kind"),
                "refs": list(row.get("refs") or ()),
                "proposal": dict(row.get("proposal") or {}),
            }
            try:
                synth.materialize(candidate, trial_cfg, str(trial_board))
                pads = synth._oracle_pads_in_bounds(str(trial_board))
                courtyards = synth._oracle_courtyard_overlaps(
                    str(trial_board))
                craft = synth.placement_craft_evidence(
                    str(trial_board), cfg=trial_cfg)
                craft_gate = _placement_craft_gate(
                    craft, routed_input=False)
                constraints = _placement_constraint_gate(
                    trial_board, trial_cfg)
                physical_ok = bool(
                    pads.get("ok") and courtyards.get("ok")
                    and craft_gate.get("ok") and constraints.get("ok"))
                trial_report["physical"] = {
                    "ok": physical_ok,
                    "pads_in_bounds": bool(pads.get("ok")),
                    "courtyards": bool(courtyards.get("ok")),
                    "craft": bool(craft_gate.get("ok")),
                    "constraints": bool(constraints.get("ok")),
                }
                if not craft_gate.get("ok"):
                    craft_terms = []
                    for term in (
                            "decoupler", "stranded", "detection_cell",
                            "pair_launch", "critical_terminal_order",
                            "pour_territory", "power_body_clearance"):
                        value = craft.get(term)
                        if isinstance(value, dict) and not value.get("ok"):
                            craft_terms.append(term)
                    trial_report["physical"].update({
                        "craft_failed_terms": craft_terms,
                        "craft_gate_blockers": list(
                            craft_gate.get("blockers") or ()),
                        "decoupler_violations": list(
                            (craft.get("decoupler") or {}).get(
                                "violations") or ())[:12],
                        "critical_terminal_violations": list(
                            (craft.get("critical_terminal_order") or {}).get(
                                "violations") or ())[:12],
                        "power_body_violations": list(
                            (craft.get("power_body_clearance") or {}).get(
                                "violations") or ())[:12],
                        "power_planner_failures": dict(
                            (craft.get("power_body_clearance") or {}).get(
                                "planner_failures") or {}),
                    })
                if not physical_ok:
                    trial_report["reason"] = "physical_gate_refused"
                    continue
                authority = _ensure_placement_route_authority(
                    trial_cfg, trial_board)
                trial_report["route_authority"] = {
                    key: value for key, value in authority.items()
                    if key not in ("_artifacts", "planner")}
                if not authority.get("ok"):
                    trial_report["reason"] = "power_replan_refused"
                    continue
                evidence = _measure_placement_priority_routes(
                    trial_cfg, trial_board)
                key = tuple(
                    cec_route_preflight.placement_evidence_key(evidence))
                gate = _placement_priority_route_gate(
                    evidence, applicable=True)
                report["evaluated"] += 1
                trial_report.update({
                    "key": list(key), "gate": gate,
                    "critical_route_refused_count": int(evidence.get(
                        "critical_route_refused_count", 0) or 0),
                })
                if key < baseline_key and (
                        best is None or key < best[0]):
                    # Preserve the exact board+power authority that produced
                    # this verdict. Re-materializing only the placement after
                    # the scratch directory disappears both repeats the
                    # expensive power solve and can publish coordinates that
                    # differ from an authority-time legalizer move.
                    payload = _capture_placement_authority_payload(
                        trial_board)
                    best = (key, row, evidence, trial_report, payload)
            except Exception as exc:                    # noqa: BLE001
                trial_report.update({
                    "reason": "power_replan_exception",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
            finally:
                trial_report["wall_s"] = round(
                    time.monotonic() - started, 3)
                report["trials"].append(trial_report)

    if best is None:
        report["reason"] = "no_post_power_authority_improvement"
        return {**ordinary_report, "power_replan": report}

    best_key, winning_row, evidence, winning_trial, payload = best
    published = _publish_placement_authority_payload(board, payload)
    # The exact admitted PCB and its matching sibling authority are now the
    # canonical artifact family. Clear config projections belonging to the
    # pre-move placement; the normal binder will rediscover the new sibling
    # state without rebuilding it.
    for key in power_keys:
        cfg.params.pop(key, None)
    report.update({
        "accepted": True, "changed": True,
        "reason": "strict_post_power_authority_improvement",
        "selected_index": int(winning_trial["index"]),
        "selected_key": list(best_key),
        "selected_move": winning_row,
        "published_authority": published,
    })
    result = dict(ordinary_report)
    result.update({
        "schema": 2, "ok": True, "changed": True,
        "accepted_count": int(ordinary_report.get(
            "accepted_count", 0) or 0) + 1,
        "stop_reason": "power_replan_candidate_accepted",
        "result_key": list(best_key),
        "result_evidence": evidence,
        "power_replan": report,
    })
    return result


def _measure_placement_priority_routes(cfg, board):
    """Measure placement with the configured critical/power owner order."""
    import cec_synth_pipeline as synth

    board = Path(board).resolve()
    bound, authority = synth.config_with_board_route_authority(
        cfg, str(board))
    requires_power_authority = bool(
        cfg.params.get("pour_first") or cfg.params.get("pour_plan"))
    if (not authority.get("ok")
            or (requires_power_authority and not authority.get("bound"))):
        return {"error": "exact route authority is not bound",
                "route_authority": authority}
    candidate = synth.placement_candidate_from_board(bound, str(board))
    bound.params["placement_route_pair_timeout_s"] = float(cfg.params.get(
        "placement_route_pair_timeout_s", 120.0) or 120.0)
    with synth._oracle_env(bound.params), \
            synth._placement_route_preflight_env():
        measured = synth.rerank_route_preflight(
            bound, [candidate], topk=1,
            grid_mm=float(cfg.params.get(
                "placement_route_preflight_grid_mm", 1.0) or 1.0),
            iters=int(cfg.params.get(
                "placement_route_preflight_iters", 4) or 4),
            backend=str(cfg.params.get(
                "placement_route_preflight_backend", "auto")),
            multiresolution=bool(cfg.params.get(
                "placement_route_preflight_multiresolution", True)))[0]
    return dict(measured.route_preflight or {})


def _placement_authority_family(board):
    """Return the small transactional artifact family for placement/power.

    Placement, the exact pour-first state, and the skeleton it names are one
    authority.  A route-aware placement experiment must be able to roll all of
    them back together; restoring only the PCB recreates the stale-sidecar bug
    this stage is specifically intended to prevent.
    """
    board = Path(board).resolve()
    base = board.with_suffix("")
    skeleton = board.with_name(board.stem + ".pourfirst-skeleton.kicad_pcb")
    skeleton_base = skeleton.with_suffix("")
    paths = [board]
    for root in (base, skeleton_base):
        paths.extend(Path(str(root) + extension) for extension in (
            ".kicad_pro", ".kicad_dru", ".pourplan.json",
            ".railreport.json", ".pourfirst-state.json"))
    paths.append(skeleton)
    # Keep deterministic ordering and do not let a malformed board name make
    # the transaction touch anything outside its own sibling artifact family.
    return tuple(sorted(set(paths), key=lambda path: str(path)))


def _snapshot_placement_authority(board, destination):
    """Copy one placement/power authority into a bounded scratch directory."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    board = Path(board).resolve()
    manifest = []
    for source in _placement_authority_family(board):
        if not source.is_file():
            continue
        name = source.name
        shutil.copy2(source, destination / name)
        manifest.append(name)
    (destination / "manifest.json").write_text(
        json.dumps({"schema": 1, "files": manifest}, indent=1,
                   sort_keys=True) + "\n",
        encoding="utf-8")
    return {"schema": 1, "board": str(board), "files": manifest,
            "directory": str(destination)}


def _restore_placement_authority(board, snapshot):
    """Restore exactly one bounded sibling authority snapshot."""
    board = Path(board).resolve()
    snapshot = Path(snapshot).resolve()
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {str(name) for name in manifest.get("files") or ()}
    allowed = {path.name: path for path in _placement_authority_family(board)}
    if not names or board.name not in names or not names.issubset(allowed):
        raise ValueError("placement authority snapshot is incomplete or unsafe")
    for name, target in allowed.items():
        source = snapshot / name
        if name in names:
            shutil.copy2(source, target)
        elif target.is_file():
            target.unlink()
    return {"schema": 1, "ok": True, "board": str(board),
            "files": sorted(names)}


def _capture_placement_authority_payload(board):
    """Capture one scratch placement/power transaction by artifact role.

    The scratch board stem is intentionally different from the canonical
    board stem, so filenames cannot be copied verbatim. Role suffixes retain
    the exact PCB, frozen-power state, skeleton, and small project sidecars in
    memory until the bounded temporary search closes.
    """
    board = Path(board).resolve()
    stem = board.stem
    files = {}
    for source in _placement_authority_family(board):
        if not source.is_file() or not source.name.startswith(stem):
            continue
        role = source.name[len(stem):]
        if not role:
            continue
        files[role] = source.read_bytes()
    if ".kicad_pcb" not in files:
        raise RuntimeError("placement authority payload has no PCB")
    return {"schema": 1, "source_stem": stem, "files": files}


def _publish_placement_authority_payload(board, payload):
    """Atomically publish a captured transaction under a new board stem."""
    board = Path(board).resolve()
    payload = payload or {}
    source_stem = str(payload.get("source_stem") or "")
    files = payload.get("files") if isinstance(
        payload.get("files"), dict) else payload
    allowed = {}
    for target in _placement_authority_family(board):
        if target.name.startswith(board.stem):
            allowed[target.name[len(board.stem):]] = target
    roles = set(files or {})
    if ".kicad_pcb" not in roles or not roles.issubset(allowed):
        raise ValueError("placement authority payload roles are incomplete")

    def rebase_json_paths(value):
        if isinstance(value, dict):
            return {key: rebase_json_paths(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [rebase_json_paths(item) for item in value]
        if isinstance(value, str) and source_stem:
            name = Path(value).name
            if name.startswith(source_stem):
                role = name[len(source_stem):]
                if role in allowed:
                    return str(allowed[role])
        return value

    board.parent.mkdir(parents=True, exist_ok=True)
    for role in sorted(roles):
        target = allowed[role]
        data = files[role]
        if role.endswith(".json"):
            try:
                decoded = json.loads(data.decode("utf-8"))
                data = (json.dumps(
                    rebase_json_paths(decoded), indent=1,
                    sort_keys=True) + "\n").encode("utf-8")
            except (AttributeError, UnicodeDecodeError,
                    TypeError, ValueError, json.JSONDecodeError):
                # Some historical sidecars use a non-JSON placeholder in
                # tests or handoff fixtures. Preserve those bytes verbatim;
                # production authority JSON is rebased above.
                pass
        with tempfile.NamedTemporaryFile(
                mode="wb", prefix=target.name + ".",
                suffix=".tmp", dir=str(target.parent), delete=False) as sink:
            temporary = Path(sink.name)
            sink.write(data)
            sink.flush()
            os.fsync(sink.fileno())
        os.replace(str(temporary), str(target))
    # A transaction replaces the complete small sibling family. Remove stale
    # roles not present in the admitted payload, never anything outside the
    # exact board stem and allow-list above.
    removed = []
    for role, target in sorted(allowed.items()):
        if role not in roles and target.is_file():
            target.unlink()
            removed.append(role)
    return {
        "schema": 1, "ok": True, "board": str(board),
        "roles": sorted(roles), "removed_stale_roles": removed,
    }


def _placement_position_signature(board):
    """Hash only component poses, so serialization cannot mimic progress."""
    import pcbnew

    loaded = pcbnew.LoadBoard(str(Path(board).resolve()))
    if loaded is None:
        raise ValueError("placement board is unreadable")
    rows = []
    for footprint in loaded.GetFootprints():
        position = footprint.GetPosition()
        rows.append((
            str(footprint.GetReference()),
            round(position.x / 1e6, 6),
            round(position.y / 1e6, 6),
            round(float(footprint.GetOrientationDegrees()) % 360.0, 6),
            bool(footprint.GetLayer() == pcbnew.B_Cu),
        ))
    return digest_value(sorted(rows))


def _candidate_position_signature(candidate):
    """Content fingerprint for an in-memory placement candidate.

    Strategy/seed labels are not proof of search diversity: two algorithms
    may converge to the same poses, while candidates with the same coarse
    route key may still be geometrically distinct.  Record the actual pose
    state so an unattended wave can distinguish both cases without retaining
    every temporary PCB.
    """
    back = set(getattr(candidate, "back_refs", ()) or ())
    rows = [(
        str(ref),
        round(float(position[0]), 6),
        round(float(position[1]), 6),
        round(float(position[2]) % 360.0, 6),
        bool(ref in back),
    ) for ref, position in (getattr(candidate, "P", {}) or {}).items()]
    return digest_value(sorted(rows))


def _incremental_outline_repack_variants(
        synth, cfg, base, moved_positions, input_board, follow_report,
        outline_policy, cell_evidence, *, width, height):
    """Evacuate collisions created by a receding mechanical edge.

    Edge-follow is intentionally a rigid mechanical transform.  A smaller
    outline can therefore push that moved band into an otherwise good local
    placement.  Resolve only the *introduced* collision graph, translate
    complete owner/bypass cells, and preserve existing connector body
    overhang without permitting it to grow.  Exact embedded-board courtyards
    generate proposals; later materialized KiCad DRC and electrical craft
    remain the admission authority.
    """
    report = copy.deepcopy(follow_report)
    result = copy.deepcopy(base)
    result.strat = "incremental-edge-band"
    result.seed = -1
    result.P = dict(moved_positions)
    result.W = float(width)
    result.H = float(height)
    result.route_preflight = {}
    if not bool(outline_policy.get("repack_collisions", False)):
        return [(result, report)]

    primary = {
        ref: result.P[ref] for ref in result.P
        if ref in base.P and tuple(result.P[ref]) != tuple(base.P[ref])
    }
    repack_report = {
        "schema": 1, "enabled": True,
        "primary_refs": sorted(primary), "attempted": bool(primary),
    }
    report["repack"] = repack_report
    if not primary:
        repack_report["reason"] = "outline_did_not_move_placements"
        return [(result, report)]

    import pcbnew

    board = pcbnew.LoadBoard(str(input_board))
    if board is None:
        repack_report["reason"] = "source_board_unloadable"
        return [(result, report)]
    snapshot_boxes = {
        str(fp.GetReference()): synth._footprint_courtyard_box(fp)
        for fp in board.GetFootprints()
    }

    def embedded_bbox(ref, position):
        if ref not in snapshot_boxes or ref not in base.P:
            raise KeyError(ref)
        x, y, rotation = map(float, position)
        old_x, old_y, old_rotation = map(float, base.P[ref])
        if abs((rotation - old_rotation) % 360.0) > 1e-6:
            # The compaction legalizer is translation-only. Refuse a future
            # caller that attempts to reuse this authority for rotations.
            raise ValueError("embedded bbox authority does not rotate")
        x0, x1, y0, y1 = snapshot_boxes[ref]
        return (x0 + x - old_x, x1 + x - old_x,
                y0 + y - old_y, y1 + y - old_y)

    try:
        baseline_pairs = synth._placement_bbox_overlap_pairs(
            base.P, embedded_bbox, back_refs=base.back_refs)
        moved_pairs = synth._placement_bbox_overlap_pairs(
            result.P, embedded_bbox, back_refs=base.back_refs)
    except (KeyError, TypeError, ValueError) as exc:
        repack_report.update({
            "reason": "embedded_bbox_authority_error",
            "error": "%s: %s" % (type(exc).__name__, exc),
        })
        return [(result, report)]
    introduced = moved_pairs - baseline_pairs
    repack_report["baseline_pairs"] = [
        list(pair) for pair in sorted(baseline_pairs)]
    repack_report["introduced_pairs"] = [
        list(pair) for pair in sorted(introduced)]
    if not introduced:
        repack_report.update({"reason": "already_legal", "variants": 0})
        return [(result, report)]

    details = list(
        ((cell_evidence or {}).get("decoupler") or {}).get("details") or ())
    owner_by_cap = {
        str(row.get("cap_ref")): str(row.get("owner_ref"))
        for row in details
        if (row.get("cap_ref") in base.P
            and row.get("owner_ref") in base.P)
    }
    caps_by_owner = {}
    for cap, owner in owner_by_cap.items():
        caps_by_owner.setdefault(owner, set()).add(cap)

    fixed = set(cfg.pins or ())
    fixed.update((cfg.params.get("anchor_pins") or {}).keys())
    fixed.update((cfg.params.get("anchor_local_placements") or {}).keys())
    fixed.update(str(ref) for ref in
                 (outline_policy.get("repack_fixed_refs") or ()))
    for group in cfg.params.get("rigid_groups") or ():
        fixed.update((group.get("offsets") or {}).keys())
    fixed.update(ref for ref in base.P
                 if ref.startswith(("H", "FID", "LOGO")))

    search_base = copy.deepcopy(base)
    search_base.W = float(width)
    search_base.H = float(height)
    trace = {}
    comps = synth._extend_footprint_map_from_board(
        {}, str(input_board), refs=base.P)
    variants = synth._placement_bounded_macro_legalizations(
        search_base, primary, baseline_pairs, comps,
        owner_by_cap, caps_by_owner,
        lambda ref: (ref in base.P and ref in comps and ref not in fixed),
        max_steps=int(outline_policy.get("repack_max_steps", 8) or 8),
        beam_width=int(outline_policy.get("repack_beam_width", 32) or 32),
        max_variants=int(outline_policy.get(
            "repack_max_variants", 4) or 4),
        clearance_mm=float(outline_policy.get(
            "repack_clearance_mm", 0.10) or 0.10),
        bbox_fn=embedded_bbox, trace=trace,
        preserve_existing_overhang=True, exact_bbox_overlap=True)
    repack_report.update({
        "reason": trace.get("reason"),
        "variants": len(variants), "trace": trace,
    })
    if not variants:
        return [(result, report)]

    rows = []
    for index, (placements, roots, kind) in enumerate(variants):
        candidate = copy.deepcopy(search_base)
        candidate.strat = "incremental-edge-repack"
        candidate.seed = -1
        candidate.P = dict(base.P)
        candidate.P.update(placements)
        candidate.route_preflight = {}
        candidate_report = copy.deepcopy(report)
        candidate_report["repack"].update({
            "selected_variant": index,
            "kind": kind,
            "displaced_roots": list(roots),
            "moved_refs": {
                ref: {
                    "dx_mm": round(candidate.P[ref][0] - base.P[ref][0], 6),
                    "dy_mm": round(candidate.P[ref][1] - base.P[ref][1], 6),
                }
                for ref in sorted(candidate.P)
                if tuple(candidate.P[ref]) != tuple(base.P[ref])
            },
        })
        rows.append((candidate, candidate_report))
    return rows


def _outline_selection_sort_key(row, *, route_probe=False):
    """Rank outline candidates without trading routability for laminate.

    ``row`` retains the placement-stage tuple layout for compatibility. The
    appended fields are hard-route key, full-route key, and blocking-only
    craft key. With probing enabled, hard physical/craft/route defects are
    removed first, area chooses the smallest equivalent outline, and only then
    do polish/congestion proxies break ties.
    """
    if route_probe:
        return (row[0], row[11], row[9], row[2], row[1], row[10],
                row[3], row[4])
    return (row[0], row[1], row[2], row[3], row[4])


def _continued_edge_follow_policy(input_board, source_outline,
                                  outline_policy):
    """Keep a discovered mechanical edge band stable across continuation.

    Re-evaluating a distance-from-edge selector after every accepted shrink
    makes the band creep inward and eventually claims the very components the
    repacker should evacuate.  A sibling canonical placement report records
    the previously moved membership.  Reuse it only when its target outline
    matches this exact source artifact; explicit refs in current policy remain
    additive.  First-time boards still use geometric discovery unchanged.
    """
    policy = copy.deepcopy(dict(outline_policy or {}))
    released = {str(ref) for ref in
                (policy.get("edge_follow_exclude_refs") or ())}
    board = Path(input_board).resolve()
    report_path = board.with_name(board.stem + ".placement.json")
    provenance = {"schema": 1, "source": "geometric_discovery"}
    if not report_path.is_file():
        return policy, provenance
    try:
        previous = _load_json(report_path)
        previous_compaction = previous.get("outline_compaction") or {}
        previous_target = (previous_compaction.get("target_outline_mm")
                           or previous.get("selected_outline_mm") or ())
        moved = (previous_compaction.get("selected_refs")
                 or previous_compaction.get("moved_refs") or {})
        if (len(previous_target) != 2 or not moved
                or any(abs(float(previous_target[index])
                           - float(source_outline[index])) > 0.05
                       for index in range(2))):
            return policy, provenance
        current_groups = [dict(raw or {}) for raw in
                          (policy.get("edge_follow") or ())]

        def current_options(ref, edge, previous_row):
            for group in current_groups:
                if str(group.get("edge") or "").lower() != edge:
                    continue
                explicit = {str(item) for item in
                            (group.get("refs") or ())}
                excluded = {str(item) for item in
                            (group.get("exclude_refs") or ())}
                if ref in excluded:
                    continue
                if ref in explicit or float(
                        group.get("margin_mm", 0.0) or 0.0) > 0.0:
                    return {
                        "mode": str(group.get("mode") or "rigid"),
                        "clearance_mm": float(
                            group.get("clearance_mm", 0.0) or 0.0),
                    }
            return {
                "mode": str((previous_row or {}).get("mode") or "rigid"),
                "clearance_mm": float(
                    (previous_row or {}).get("clearance_mm", 0.0) or 0.0),
            }

        membership = {}
        for ref, row in moved.items():
            if str(ref) in released:
                continue
            edge = str((row or {}).get("edge") or "").lower()
            if edge in {"left", "right", "top", "bottom"}:
                membership[str(ref)] = {
                    "edge": edge,
                    **current_options(str(ref), edge, row),
                }
        for group in current_groups:
            edge = str(group.get("edge") or "").lower()
            if edge not in {"left", "right", "top", "bottom"}:
                continue
            for ref in group.get("refs") or ():
                ref = str(ref)
                if ref in released:
                    continue
                if ref in {str(item) for item in
                           (group.get("exclude_refs") or ())}:
                    continue
                membership[ref] = {
                    "edge": edge,
                    "mode": str(group.get("mode") or "rigid"),
                    "clearance_mm": float(
                        group.get("clearance_mm", 0.0) or 0.0),
                }
        if not membership:
            return policy, provenance
        grouped = {}
        for ref, row in membership.items():
            key = (row["edge"], row["mode"], row["clearance_mm"])
            grouped.setdefault(key, set()).add(ref)
        policy["edge_follow"] = tuple({
            "edge": edge, "refs": tuple(sorted(refs)), "mode": mode,
            "clearance_mm": clearance,
        } for (edge, mode, clearance), refs in sorted(grouped.items()))
        by_edge = {}
        for ref, row in membership.items():
            by_edge.setdefault(row["edge"], set()).add(ref)
        provenance = {
            "schema": 1, "source": "prior_admitted_membership",
            "report": str(report_path),
            "released_refs": sorted(released),
            "refs_by_edge": {
                edge: sorted(refs) for edge, refs in sorted(by_edge.items())
            },
        }
        return policy, provenance
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return policy, provenance


def _placement_stage(cfg, input_board, output_board, *, replace, strategies,
                     seeds, workers, craft_trials, craft_rounds,
                     craft_epochs, completion_report=None):
    import cec_synth_pipeline as synth
    import cec_search_policy
    import cec_outline_compaction

    output_board = Path(output_board).resolve()
    if replace:
        cec_search_policy.bounded_placement_plan(strategies, seeds)
        source = synth.read_placement(str(input_board))
        outline_policy = dict(
            cfg.params.get("outline_compaction") or {})
        edge_follow_policy, edge_follow_membership = (
            _continued_edge_follow_policy(
                input_board, (source.W, source.H), outline_policy))
        follow_extents = None
        if any(str((group or {}).get("mode") or "rigid").lower()
               == "contain" for group in
               (edge_follow_policy.get("edge_follow") or ())):
            import pcbnew
            follow_board = pcbnew.LoadBoard(str(input_board))
            if follow_board is None:
                raise RuntimeError(
                    "contain edge-follow source board is unloadable")
            follow_extents = {
                str(fp.GetReference()): synth._footprint_courtyard_box(fp)
                for fp in follow_board.GetFootprints()
            }
        outline_variants = []
        outline_sizes = cec_outline_compaction.outline_candidates(
            source.W, source.H, outline_policy)
        for width, height in outline_sizes:
            variant = copy.copy(cfg)
            variant.params = dict(cfg.params)
            # A replacement placement cannot inherit copper authority proved
            # for the source footprint snapshot.  Keeping these keys made any
            # outline change fail against the old dimensions before the new
            # candidate could even be evaluated.  Release only the derived
            # freeze/snapshot fields; the selected materialized placement must
            # earn a fresh exact state at the normal canonical boundary.
            for key in ("pourfirst_state", "pourfirst_outline_mm",
                        "pourfirst_seen_placements",
                        "pourfirst_avoid_boxes"):
                variant.params.pop(key, None)
            if len(outline_sizes) > 1:
                # Size-floor discovery is a screening pass. Running the full
                # iterative route-repair budget independently for every size
                # serializes a large amount of work before the outlines have
                # even been compared. Measure each outline once here; the
                # selected winner receives the canonical exact repair below.
                variant.params["placement_route_repair_trials"] = int(
                    outline_policy.get(
                        "probe_route_repair_trials", 0) or 0)
                if not bool(outline_policy.get(
                        "probe_route_preflight", False)):
                    variant.params["placement_route_preflight_auto"] = False
                    variant.params["placement_route_preflight_topk"] = 0
            variant.pins, follow = (
                cec_outline_compaction.edge_follow_positions(
                    cfg.pins, (source.W, source.H), (width, height),
                    edge_follow_policy, extent_by_ref=follow_extents))
            follow["membership"] = edge_follow_membership
            outline_variants.append((variant, width, height, follow))
        candidates = []
        candidate_context = {}
        repack_evidence = None
        if outline_policy.get("repack_collisions", False):
            repack_evidence = synth.placement_craft_evidence(
                str(input_board), cfg=cfg)
        for variant, width, height, follow in outline_variants:
            rows = []
            if outline_policy.get("include_incremental", True):
                # --replace-placement is the explicit authority boundary that
                # permits discarding incumbent copper.  Rehydration normally
                # refuses routed inputs so an audit cannot erase them by
                # accident; this replacement path must be able to preserve
                # their exact component poses as the incremental baseline.
                base = synth.placement_candidate_from_board(
                    variant, str(input_board), allow_routed=True)
                moved, incremental_follow = (
                    cec_outline_compaction.edge_follow_positions(
                        base.P, (source.W, source.H), (width, height),
                        edge_follow_policy, extent_by_ref=follow_extents))
                incremental_follow["membership"] = edge_follow_membership
                incremental_rows = _incremental_outline_repack_variants(
                    synth, variant, base, moved, input_board,
                    incremental_follow, outline_policy, repack_evidence,
                    width=width, height=height)
                for incremental, repack_follow in incremental_rows:
                    rows.append(incremental)
                    candidate_context[id(incremental)] = (
                        variant, repack_follow)
            if outline_policy.get("include_fresh_placement", True):
                rows.extend(synth.place_candidates(
                    variant, width, height,
                    strategies=tuple(strategies), seeds=tuple(seeds),
                    max_workers=workers))
            candidates.extend(rows)
            for candidate in rows:
                candidate_context.setdefault(
                    id(candidate), (variant, follow))
        if not candidates:
            raise RuntimeError("route-aware placement produced no candidates")
        # A mechanically legal outline can still cross the routing floor.  A
        # post-selection preflight discovers that too late: the smallest
        # candidate has already displaced every larger fallback.  When the
        # board enables the bounded outline probe, measure every surviving
        # candidate with its own outline/pin policy before final ranking.  The
        # hard feasibility prefix is considered ahead of area; soft
        # congestion remains a tie-breaker after area so a marginal proxy win
        # cannot silently bloat an otherwise equally routable board.
        probe_outline_routes = bool(outline_policy.get(
            "probe_route_preflight", False))
        if probe_outline_routes:
            # All outline candidates are independent. Dispatch them through a
            # single bounded process pool instead of serializing one pool per
            # outline size. candidate_cfg retains each candidate's exact
            # outline/pour policy while TemporaryDirectory ownership remains
            # inside rerank_route_preflight, so wider searches do not retain
            # materialized boards on disk.
            with synth._oracle_env(cfg.params), \
                    synth._placement_route_preflight_env():
                synth.rerank_route_preflight(
                    cfg, candidates, topk=len(candidates),
                    grid_mm=float(cfg.params.get(
                        "placement_route_preflight_grid_mm", 1.0) or 1.0),
                    iters=int(cfg.params.get(
                        "placement_route_preflight_iters", 4) or 4),
                    backend=str(cfg.params.get(
                        "placement_route_preflight_backend", "auto")),
                    multiresolution=bool(cfg.params.get(
                        "placement_route_preflight_multiresolution", True)),
                    candidate_cfg=lambda candidate: candidate_context[
                        id(candidate)][0])
        # Cheap HPWL/congestion proxy ranking is a pruning signal, not an
        # electrical placement verdict.  Materialize every surviving candidate
        # and put the hard decoupler/stranded-part craft key ahead of the cheap
        # proxy.  This closes the old seam where the right algorithms ran but a
        # lower-HPWL board with failed bypass cells was selected anyway.
        selection_rows = []
        with tempfile.TemporaryDirectory(
                prefix="cec-full-placement-rank-") as work:
            for index, candidate in enumerate(candidates):
                candidate_path = Path(work) / ("%03d.kicad_pcb" % index)
                variant_cfg, follow = candidate_context[id(candidate)]
                synth.materialize(candidate, variant_cfg,
                                  str(candidate_path))
                evidence = synth.placement_craft_evidence(
                    str(candidate_path), cfg=variant_cfg)
                key = synth.placement_craft_key(evidence)
                pads = synth._oracle_pads_in_bounds(str(candidate_path))
                courtyards = synth._oracle_courtyard_overlaps(
                    str(candidate_path))
                physical_key = (
                    0 if pads.get("ok") else 1,
                    len(courtyards.get("violations") or ()),
                    int(candidate.residual),
                )
                if probe_outline_routes:
                    import cec_route_preflight
                    route_key = tuple(
                        cec_route_preflight.placement_evidence_key(
                            candidate.route_preflight))
                    # Error, declared critical-route/pin/fanout blockers, and
                    # ordinary unroutable connections determine whether this
                    # outline remains a viable routing floor. A missing
                    # straight escape ray (key field 6) is explicitly a
                    # warning, so it stays in the soft tail with forecast
                    # density and overflow instead of growing the board.
                    route_hard_key = route_key[:6] + route_key[7:8]
                else:
                    route_key = ()
                    route_hard_key = ()
                selection_rows.append((
                    physical_key, key,
                    float(candidate.W) * float(candidate.H),
                    synth._candidate_sort_key(candidate),
                    index, candidate, evidence, variant_cfg, follow,
                    route_hard_key, route_key,
                    synth.placement_craft_blocking_key(evidence),
                ))
        # Physical legality is lexicographically prior to every electrical or
        # wirelength preference.  Repair may improve electrical craft, but it
        # is not allowed to carry an already-overlapping board forward.
        if probe_outline_routes:
            selection_rows.sort(key=lambda row: _outline_selection_sort_key(
                row, route_probe=True))
        else:
            selection_rows.sort(key=_outline_selection_sort_key)
        (_physical_key, _craft_key, _area, _proxy_key, _index, best,
         initial_craft, selected_cfg, outline_follow) = selection_rows[0][:9]
        best, repair = synth.repair_placement_craft_epochs(
            selected_cfg, best, max_trials=int(craft_trials),
            rounds=int(craft_rounds), epochs=int(craft_epochs)
        )
        synth.materialize(best, selected_cfg, str(output_board))
        copied = _copy_sidecars(
            output_board, output_board, cfg=selected_cfg)
        # Downstream placement, route-authority, and signoff stages must see
        # the exact selected mechanical anchors rather than the nominal
        # pre-compaction coordinates.
        cfg.pins = dict(selected_cfg.pins)
        cfg.params["selected_outline_mm"] = [best.W, best.H]
        cfg.params["selected_outline_edge_follow"] = outline_follow
        selection_signatures = [
            _candidate_position_signature(row[5])
            for row in selection_rows
        ]
        placement = {
            "mode": "route-aware-replacement",
            "strategy": best.strat,
            "seed": best.seed,
            "placement_signature": _candidate_position_signature(best),
            "placement_diversity": {
                "candidate_count": len(selection_signatures),
                "unique_pose_count": len(set(selection_signatures)),
                "collapsed_count": (
                    len(selection_signatures) - len(set(selection_signatures))
                ),
            },
            "residual": best.residual,
            "proxy": best.proxy,
            "selection_craft_key": list(_craft_key),
            "selection_physical_key": list(_physical_key),
            "selected_outline_mm": [best.W, best.H],
            "selected_outline_area_mm2": round(best.W * best.H, 3),
            "outline_compaction": outline_follow,
            "selection_craft": initial_craft,
            "selection_candidates": [
                {
                    "strategy": row[5].strat, "seed": row[5].seed,
                    "outline_mm": [row[5].W, row[5].H],
                    "outline_area_mm2": round(row[5].W * row[5].H, 3),
                    "physical_key": list(row[0]),
                    "craft_key": list(row[1]),
                    "proxy_key": list(row[3]),
                    "route_hard_key": list(row[9]),
                    "route_key": list(row[10]),
                    "placement_signature": selection_signatures[index],
                }
                for index, row in enumerate(selection_rows)
            ],
            "craft_repair": repair,
        }
    else:
        copied = _copy_sidecars(input_board, output_board, cfg=cfg)
        placement = {"mode": "existing-current-beta-placement"}
        initial_craft = synth.placement_craft_evidence(
            str(output_board), cfg=cfg)
        frozen_before = _frozen_placement_contract(output_board)
        placement["frozen_placement_before"] = frozen_before
        optimize_clean_margin = bool(cfg.params.get(
            "placement_craft_optimize_clean_margin", True))
        import pcbnew
        _placement_board = pcbnew.LoadBoard(str(output_board))
        routed_input = any(True for _item in _placement_board.GetTracks())
        if routed_input:
            # A routed canonical board may be audited here but never converted
            # back into a placement-only Candidate.  Placement rehydration is
            # intentionally destructive to copper and is authorized only by
            # --replace-placement.  Later routing/repair stages retain exact
            # ownership of the existing tracks and zones.
            repair = {
                "schema": 1, "changed": False,
                "skipped": "routed_input_read_only",
                "reason": (
                    "replacement not requested; preserve routed copper"),
            }
            placement.update({
                "mode": "existing-routed-beta-placement-verified",
                "selection_craft": initial_craft,
                "craft_repair": repair,
            })
        elif frozen_before.get("applicable"):
            if frozen_before.get("ok") and not initial_craft.get("ok"):
                # Repair only a current hard craft blocker; clean-margin
                # optimization alone never perturbs a frozen placement.
                candidate = synth.placement_candidate_from_board(
                    cfg, str(output_board))
                candidate, repair = synth.repair_placement_craft_epochs(
                    cfg, candidate, max_trials=int(craft_trials),
                    rounds=int(craft_rounds), epochs=int(craft_epochs))
                if repair.get("changed"):
                    synth.materialize(candidate, cfg, str(output_board))
                    repair["postfreeze_state_sync"] = \
                        _sync_safe_postfreeze_placement_delta(output_board)
                placement.update({
                    "mode": "existing-frozen-placement-bounded-repair",
                    "selection_craft": initial_craft,
                    "craft_repair": repair,
                })
            else:
                # Fail closed on stale authority and preserve a matching,
                # already-valid complete solve exactly. Replacing it requires
                # --replace-placement, which also recomputes power.
                repair = {
                    "schema": 1, "changed": False,
                    "skipped": "complete_frozen_placement_authority",
                    "reason": ("contract_preserved"
                               if frozen_before.get("ok")
                               else "contract_mismatch"),
                }
                placement.update({
                    "mode": "existing-frozen-placement-verified",
                    "selection_craft": initial_craft,
                    "craft_repair": repair,
                })
        elif not initial_craft.get("ok") or optimize_clean_margin:
            candidate = synth.placement_candidate_from_board(
                cfg, str(output_board))
            candidate, repair = synth.repair_placement_craft_epochs(
                cfg, candidate, max_trials=int(craft_trials),
                rounds=int(craft_rounds), epochs=int(craft_epochs))
            # A verified no-op must be byte-preserving.  ``materialize`` is a
            # placement reconstruction tool, not a serializer: invoking it for
            # an unchanged candidate can legitimately rebuild copper/zones and
            # used to turn an already clean board into an unrouted one.  Only a
            # monotonic accepted placement delta owns that destructive rewrite.
            if repair.get("changed"):
                synth.materialize(candidate, cfg, str(output_board))
            placement.update({
                "mode": ("existing-current-beta-bounded-repair"
                         if repair.get("changed") else
                         "existing-current-beta-placement-verified"),
                "selection_craft": initial_craft,
                "craft_repair": repair,
            })

    profile_declaration = None
    profile_name = cfg.params.get("stackup_profile")
    if profile_name:
        # POFV authority must live in the PCB artifact, not only in the wave
        # process environment. This metadata-only admission repairs archived or
        # copied six-layer candidates after proving that their physical stackup
        # already matches the explicit board policy. It refuses mismatches and
        # never migrates layers, zones, tracks, pads, or placements.
        import cec_migrate_6layer
        profile_declaration = cec_migrate_6layer.declare_profile(
            str(output_board), str(profile_name))

    reconsider_fiducials = _placement_fiducials_reconsiderable(
        output_board, replace=replace)
    fiducial_repair = _transactional_fiducial_edge_repair(
        cfg, output_board, reconsider_all=reconsider_fiducials)
    placement["fiducial_edge_repair"] = fiducial_repair
    if not fiducial_repair.get("ok"):
        placement["fiducial_edge_repair_blocked"] = True
    post_fiducial_craft_repair = _bounded_post_fiducial_craft_repair(
        cfg, output_board, fiducial_repair,
        max_trials=int(craft_trials), rounds=int(craft_rounds),
        epochs=int(craft_epochs))
    placement["post_fiducial_craft_repair"] = \
        post_fiducial_craft_repair

    service_clearance_mm = float(cfg.params.get(
        "service_interface_clearance_mm", 0.0) or 0.0)
    if service_clearance_mm > 0.0:
        service_repair = synth.repair_service_connectors_away_from_interfaces(
            str(output_board), clearance_mm=service_clearance_mm,
            edge_detect_mm=float(cfg.params.get(
                "service_interface_edge_detect_mm", 6.0) or 6.0),
            max_shift_mm=float(cfg.params.get(
                "service_interface_max_shift_mm", 8.0) or 8.0))
    else:
        service_repair = {"schema": 1, "ok": True, "changed": False,
                          "skipped": "policy_disabled"}
    placement["service_interface_repair"] = service_repair
    if not service_repair.get("ok"):
        placement["service_interface_repair_blocked"] = True

    import pcbnew

    def measure_physical():
        pads_now = synth._oracle_pads_in_bounds(str(output_board))
        courtyards_now = synth._oracle_courtyard_overlaps(str(output_board))
        craft_now = synth.placement_craft_evidence(
            str(output_board), cfg=cfg)
        loaded_now = pcbnew.LoadBoard(str(output_board))
        routed_now = bool(
            loaded_now is not None
            and any(True for _item in loaded_now.GetTracks()))
        craft_gate_now = _placement_craft_gate(
            craft_now, routed_input=routed_now)
        constraints_now = _placement_constraint_gate(output_board, cfg)
        ok_now = (
            bool(pads_now.get("ok"))
            and bool(courtyards_now.get("ok"))
            and bool(craft_gate_now.get("ok"))
            and bool(constraints_now.get("ok"))
            and bool(fiducial_repair.get("ok"))
            and bool(service_repair.get("ok")))
        return (pads_now, courtyards_now, craft_now, routed_now,
                craft_gate_now, constraints_now, ok_now)

    (pads, courtyards, craft, routed_output, craft_gate,
     placement_constraints, pre_route_physical_ok) = measure_physical()
    authority_artifacts = []

    def ensure_authority():
        try:
            result = _ensure_placement_route_authority(cfg, output_board)
        except Exception as exc:                         # noqa: BLE001
            result = {
                "schema": 1, "ok": False, "applicable": True,
                "reason": "exact_route_authority_exception",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "_artifacts": [],
            }
        authority_artifacts.extend(result.get("_artifacts") or ())
        return result

    route_authority = (ensure_authority()
                       if pre_route_physical_ok else {
                           "schema": 1, "ok": False, "applicable": True,
                           "reason": "placement_not_admitted",
                           "_artifacts": [],
                       })
    if route_authority.get("placement_changed"):
        # The power solver's placement transaction is now the board. Re-run
        # all physical/craft/constraint gates against that exact artifact
        # before letting priority routing consume its authority.
        (pads, courtyards, craft, routed_output, craft_gate,
         placement_constraints,
         pre_route_physical_ok) = measure_physical()
        route_authority["post_move_physical_ok"] = bool(
            pre_route_physical_ok)
    priority_applicable = bool(
        not routed_output
        and (cfg.params.get("critical_route_nets")
             or int(cfg.params.get(
                 "placement_route_preflight_topk", 0) or 0) > 0))
    priority_repair = {
        "schema": 1, "ok": True, "changed": False,
        "applicable": priority_applicable,
        "reason": ("not_run" if priority_applicable else
                   "no_priority_route_placement_policy"),
    }
    priority_evidence = {}
    if (pre_route_physical_ok and route_authority.get("ok")
            and priority_applicable):
        # Placement and exact pours are mutually dependent.  A placement move
        # can clear a declared pair against the old reservations and then lose
        # it when the power authority is regenerated for the new coordinates.
        # Iterate that boundary transactionally: every provisional move earns
        # a fresh exact power freeze and exact critical-route measurement.
        # Keep the best *post-authority* state, and bound/repetition-guard the
        # search so unattended waves cannot oscillate.
        import cec_route_preflight

        coopt_rounds = max(1, int(cfg.params.get(
            "placement_power_route_coopt_rounds", 2) or 2))
        coopt_history = []
        best_key = None
        best_evidence = None
        best_authority = dict(route_authority)
        best_repair = None
        best_fiducial_repair = dict(fiducial_repair)
        best_service_repair = dict(service_repair)
        best_profile_declaration = profile_declaration
        best_round = 0
        selected_snapshot = None
        seen_placements = {_placement_position_signature(output_board)}
        stop_reason = "round_limit"
        repair_error = None
        with tempfile.TemporaryDirectory(
                prefix="cec-placement-power-route-coopt-") as scratch:
            scratch = Path(scratch)
            baseline_snapshot = scratch / "round-00"
            _snapshot_placement_authority(output_board, baseline_snapshot)
            selected_snapshot = baseline_snapshot

            for outer_round in range(1, coopt_rounds + 1):
                current_repair = _repair_placement_priority_routes(
                    cfg, output_board,
                    completion_report=completion_report)
                if (current_repair.get("ok")
                        and not current_repair.get("changed")):
                    ordinary_evidence = dict(
                        current_repair.get("result_evidence") or {})
                    ordinary_gate = _placement_priority_route_gate(
                        ordinary_evidence, applicable=True)
                    if not ordinary_gate.get("ok"):
                        current_repair = \
                            _repair_placement_priority_routes_with_power_replan(
                                cfg, output_board, current_repair)
                row = {
                    "round": outer_round,
                    "repair_changed": bool(current_repair.get("changed")),
                    "repair_ok": bool(current_repair.get("ok")),
                    "repair_baseline_key": list(
                        current_repair.get("baseline_key") or ()),
                    "repair_result_key": list(
                        current_repair.get("result_key") or ()),
                    "repair_stop_reason": current_repair.get("stop_reason"),
                    "repair_rounds_run": current_repair.get("rounds_run"),
                    "repair_accepted_count": current_repair.get(
                        "accepted_count"),
                    "repair_round_summaries":
                        _compact_priority_repair_round_history(
                            current_repair),
                    "power_replan": {
                        key: value for key, value in
                        (current_repair.get("power_replan") or {}).items()
                        if key != "trials"
                    },
                }
                if best_key is None and current_repair.get("baseline_key"):
                    best_key = tuple(current_repair["baseline_key"])
                if not current_repair.get("ok"):
                    repair_error = str(
                        current_repair.get("reason") or "repair_error")
                    row["stop"] = repair_error
                    coopt_history.append(row)
                    stop_reason = repair_error
                    break
                if not current_repair.get("changed"):
                    measured = dict(
                        current_repair.get("result_evidence") or {})
                    if not measured:
                        measured = _measure_placement_priority_routes(
                            cfg, output_board)
                    measured_key = tuple(
                        cec_route_preflight.placement_evidence_key(measured))
                    row.update({
                        "post_authority_key": list(measured_key),
                        "post_authority_gate": _placement_priority_route_gate(
                            measured, applicable=True),
                        "stop": "no_accepted_placement_move",
                    })
                    coopt_history.append(row)
                    if best_evidence is None and (
                            best_key is None or measured_key <= best_key):
                        best_key = measured_key
                        best_evidence = measured
                        best_repair = current_repair
                    stop_reason = "no_accepted_placement_move"
                    break

                # Materialization rebuilds the complete placement. Reassert
                # the stackup and deterministic mechanical finishers before
                # compiling exact power for these coordinates.
                if profile_name:
                    import cec_migrate_6layer
                    profile_declaration = cec_migrate_6layer.declare_profile(
                        str(output_board), str(profile_name))
                fiducial_repair = _transactional_fiducial_edge_repair(
                    cfg, output_board,
                    reconsider_all=_placement_fiducials_reconsiderable(
                        output_board, replace=replace))
                placement["fiducial_edge_repair"] = fiducial_repair
                if service_clearance_mm > 0.0:
                    service_repair = \
                        synth.repair_service_connectors_away_from_interfaces(
                            str(output_board),
                            clearance_mm=service_clearance_mm,
                            edge_detect_mm=float(cfg.params.get(
                                "service_interface_edge_detect_mm", 6.0)
                                or 6.0),
                            max_shift_mm=float(cfg.params.get(
                                "service_interface_max_shift_mm", 8.0)
                                or 8.0))
                    placement["service_interface_repair"] = service_repair
                (pads, courtyards, craft, routed_output, craft_gate,
                 placement_constraints,
                 pre_route_physical_ok) = measure_physical()
                route_authority = (ensure_authority()
                                   if pre_route_physical_ok else {
                                       "schema": 1, "ok": False,
                                       "applicable": True,
                                       "reason": "route_repair_not_admitted",
                                       "_artifacts": [],
                                   })
                row["physical_ok"] = bool(pre_route_physical_ok)
                row["route_authority_ok"] = bool(
                    route_authority.get("ok"))
                row["route_authority_reason"] = route_authority.get(
                    "reason")
                if (not pre_route_physical_ok
                        or not route_authority.get("ok")):
                    row["stop"] = "post_move_authority_refused"
                    coopt_history.append(row)
                    stop_reason = "post_move_authority_refused"
                    break

                measured = _measure_placement_priority_routes(
                    cfg, output_board)
                measured_key = tuple(
                    cec_route_preflight.placement_evidence_key(measured))
                measured_gate = _placement_priority_route_gate(
                    measured, applicable=True)
                signature = _placement_position_signature(output_board)
                repeated = signature in seen_placements
                row.update({
                    "post_authority_key": list(measured_key),
                    "post_authority_gate": measured_gate,
                    "placement_signature": signature,
                    "repeated_placement": repeated,
                })
                coopt_history.append(row)

                # Only a state that improves the exact post-pour authority may
                # displace the current best. A fully admitted state naturally
                # wins because critical-refusal fields lead the evidence key.
                if best_key is None or measured_key < best_key:
                    snapshot = scratch / ("round-%02d" % outer_round)
                    _snapshot_placement_authority(output_board, snapshot)
                    selected_snapshot = snapshot
                    best_key = measured_key
                    best_evidence = measured
                    best_authority = dict(route_authority)
                    best_repair = current_repair
                    best_fiducial_repair = dict(fiducial_repair)
                    best_service_repair = dict(service_repair)
                    best_profile_declaration = profile_declaration
                    best_round = outer_round
                if measured_gate.get("ok"):
                    stop_reason = "important_routes_feasible"
                    break
                if repeated:
                    stop_reason = "repeated_placement"
                    break
                seen_placements.add(signature)
            else:
                stop_reason = "round_limit"

            _restore_placement_authority(output_board, selected_snapshot)

        # The selected snapshot already contains its matching exact authority;
        # remeasure cheap physical gates after rollback/selection and reuse its
        # recorded authority rather than rebuilding the pours a second time.
        fiducial_repair = best_fiducial_repair
        service_repair = best_service_repair
        profile_declaration = best_profile_declaration
        placement["fiducial_edge_repair"] = fiducial_repair
        placement["service_interface_repair"] = service_repair
        (pads, courtyards, craft, routed_output, craft_gate,
         placement_constraints,
         pre_route_physical_ok) = measure_physical()
        route_authority = best_authority
        if best_evidence is None:
            best_evidence = _measure_placement_priority_routes(
                cfg, output_board)
            best_key = tuple(
                cec_route_preflight.placement_evidence_key(best_evidence))
        priority_evidence = best_evidence
        if best_repair is not None:
            priority_repair = dict(best_repair)
        else:
            priority_repair = {
                "schema": 1, "ok": repair_error is None,
                "changed": False, "accepted_count": 0,
                "reason": stop_reason,
            }
        priority_repair.update({
            "schema": 2,
            "ok": bool(priority_repair.get("ok")) and repair_error is None,
            "changed": bool(best_round),
            "result_key": list(best_key or ()),
            "result_evidence": priority_evidence,
            "cooptimization": {
                "schema": 1,
                "rounds_requested": coopt_rounds,
                "rounds_run": len(coopt_history),
                "selected_round": best_round,
                "selected_key": list(best_key or ()),
                "stop_reason": stop_reason,
                "repetition_guard": True,
                "strict_post_authority_selection": True,
                "history": coopt_history,
            },
        })
    # Optical datums own the final placement move, after exact power and the
    # priority-route co-optimizer have selected their board.  The late pass is
    # itself an exact transaction: a mark that would force a pour rebuild or a
    # critical-route regression is rolled back with the entire authority.
    if pre_route_physical_ok and route_authority.get("ok"):
        late_fiducials = _finalize_fiducials_after_route_authority(
            cfg, output_board, priority_applicable=priority_applicable)
        placement["fiducial_late_finalization"] = {
            key: value for key, value in late_fiducials.items()
            if key != "route_authority"}
        if not late_fiducials.get("ok"):
            pre_route_physical_ok = False
        elif late_fiducials.get("accepted"):
            fiducial_repair = dict(
                late_fiducials.get("repair") or fiducial_repair)
            placement["fiducial_edge_repair"] = fiducial_repair
            route_authority = dict(
                late_fiducials.get("route_authority") or route_authority)
            authority_artifacts.extend(
                route_authority.get("_artifacts") or ())
            if priority_applicable:
                priority_evidence = dict(
                    late_fiducials.get("priority_route_evidence") or {})
                if priority_repair.get("ok"):
                    import cec_route_preflight
                    priority_repair["result_evidence"] = priority_evidence
                    priority_repair["result_key"] = list(
                        cec_route_preflight.placement_evidence_key(
                            priority_evidence))
            (pads, courtyards, craft, routed_output, craft_gate,
             placement_constraints,
             pre_route_physical_ok) = measure_physical()
    else:
        placement["fiducial_late_finalization"] = {
            "schema": 1, "ok": True, "applicable": False,
            "reason": "placement_or_route_authority_not_admitted",
        }

    priority_gate = _placement_priority_route_gate(
        priority_evidence, applicable=priority_applicable)
    if not priority_repair.get("ok") and priority_applicable:
        priority_gate = {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "priority_route_repair_error",
            "blockers": [{"term": "repair", "count": 1,
                          "detail": priority_repair.get("reason")}],
        }
    frozen_after = _frozen_placement_contract(output_board)
    physical_ok = (
        bool(pre_route_physical_ok)
        and bool(frozen_after.get("ok"))
        and bool(route_authority.get("ok"))
        and bool(priority_gate.get("ok")))
    placement["priority_route_repair"] = priority_repair
    placement["priority_route_evidence"] = priority_evidence
    placement["priority_route_gate"] = priority_gate
    placement.update({
        "schema": SCHEMA,
        "board": str(output_board),
        "pads_in_bounds": pads,
        "courtyards": courtyards,
        "craft": craft,
        "craft_gate": craft_gate,
        "constraint_gate": placement_constraints,
        "frozen_placement_after": frozen_after,
        "fabrication_profile": profile_declaration,
        "route_authority": {
            key: value for key, value in route_authority.items()
            if key != "_artifacts"},
        "ok": physical_ok,
    })
    report = output_board.with_suffix(".placement.json")
    atomic_json(report, placement)
    placement["_artifacts"] = list(dict.fromkeys(
        copied + authority_artifacts
        + [str(report)]))
    placement["report"] = str(report)
    return placement


def _preflight_stage(board, output_dir, cfg, *, grid_mm, iterations, backend):
    import cec_route_preflight
    import cec_synth_pipeline as synth

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    heatmap = output_dir / "congestion.png"
    report_path = output_dir / "preflight.json"
    # Compile the exact same profile/pour/critical route environment used by
    # detailed routing. A preflight without those reservations is a different
    # board and cannot admit production work.
    with synth._oracle_env(_route_params_for_board(cfg, board)):
        report = cec_route_preflight.analyze_multiresolution(
            str(board), grid_mm=float(grid_mm), iters=int(iterations),
            backend=backend, heatmap_path=str(heatmap),
            board_hint=cfg.board, run_future_congestion=True
        )
    atomic_json(report_path, report)
    compact = cec_route_preflight.compact_placement_evidence(report)
    return {
        "ok": not bool(report.get("error")),
        "admission_gate": bool(report.get("gate")),
        "report": str(report_path),
        "heatmap": str(heatmap) if heatmap.is_file() else None,
        "summary": compact,
        "_artifacts": [str(report_path)] + (
            [str(heatmap)] if heatmap.is_file() else []
        ),
    }


def _route_candidate_worker(payload):
    """Spawn-safe route-oracle worker using only serializable inputs.

    ``--route-candidates`` is a request for route diversity, not duplicate
    CPU work.  The CEC Freerouting fork keeps its real ``-seed`` axis opt-in
    so historical single-route callers remain byte-stable.  Candidate workers
    are the bounded ensemble boundary, therefore enable that axis explicitly
    for the duration of the worker and record the contract in the verdict.
    """
    import cec_synth_pipeline as synth

    route_cfg = synth.Config.load(
        payload["board_name"], params=dict(payload["params"]))
    previous_seed_axis = os.environ.get("CEC_FR_SEED_AXIS")
    os.environ["CEC_FR_SEED_AXIS"] = "1"
    try:
        result = synth.route_oracle_grade(
            payload["board"], cfg=route_cfg,
            passes=int(payload["passes"]), opt=int(payload["opt"]),
            seed=int(payload["seed"]), fr_timeout=int(payload["timeout"]),
            work_dir=payload["work_dir"], keep=True, verbose=True,
            craft_gates=True, thermal=payload["thermal"], precision=True,
            allow_route_access_repair=bool(
                payload.get("allow_route_access_repair")),
        )
        result = dict(result)
        result["route_candidate_diversity"] = {
            "schema": 1,
            "backend": "freerouting-cec-seed-axis",
            "enabled": True,
            "seed": int(payload["seed"]),
        }
        return result
    finally:
        if previous_seed_axis is None:
            os.environ.pop("CEC_FR_SEED_AXIS", None)
        else:
            os.environ["CEC_FR_SEED_AXIS"] = previous_seed_axis


def _route_candidate_summary(row):
    """Compact, durable evidence for one bounded route attempt."""
    import cec_search_policy

    trace = list(row.get("stage_trace") or ())
    failed_stage = row.get("failure_stage")
    if not failed_stage:
        failed_stage = next(
            (event.get("stage") for event in reversed(trace)
             if event.get("status") == "failed"), None)
    return {
        "seed": row.get("seed"), "gate": bool(row.get("gate")),
        "artifact": row.get("routed"),
        "failure_artifact": row.get("failure_artifact"),
        "failure_stage": failed_stage,
        "rank": list(cec_search_policy.candidate_rank(row)),
        "sort_key": row.get("sort_key"), "drc": row.get("drc"),
        "unconnected": row.get("unconnected"),
        "unconn_critical": row.get("unconn_critical"),
        "failed_terms": sorted(
            name for name, passed in (row.get("gate_terms") or {}).items()
            if not passed),
        "blocker_summary": row.get("blocker_summary"),
        "blocker_evidence": row.get("blocker_evidence"),
        "stage_trace": trace,
        "route_s": row.get("route_s"),
        "error": row.get("error"),
        "reasons": list(row.get("reasons") or ()),
        "worker_error": row.get("worker_error"),
    }


def _route_failure_digest(candidate_summary):
    """Bound the exception text while retaining each candidate's root cause."""
    digest = []
    for row in candidate_summary:
        reason = (row.get("worker_error") or row.get("error") or
                  next(iter(row.get("reasons") or ()), None) or
                  "route produced no eligible board")
        digest.append({
            "seed": row.get("seed"),
            "stage": row.get("failure_stage"),
            "reason": str(reason)[:500],
            "artifact": row.get("failure_artifact"),
        })
    return digest


def _route_stage(board, output_dir, cfg, *, passes, opt, seed, timeout,
                 thermal, candidates=1, route_workers=None,
                 allow_route_access_repair=False):
    import cec_synth_pipeline as synth
    import cec_search_policy
    import cec_process_pool

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    route_cfg = cfg
    params = _route_params_for_board(cfg, board)
    # The canonical production coordinator consumes the global preflight's
    # escape tier.  Specialist/ablation callers may leave it disabled, while
    # every start-to-finish run gets the complete professional ordering.
    params.setdefault("automatic_pin_escape_tier", True)
    # A canonical single-candidate run is already the winner-polish context.
    # Waves defer exhaustive whole-board ordinary-net completion until their
    # winner; without this translation the canonical route never ran that
    # stage and stopped with avoidable long control/LED ratlines.
    if params.get("lastmile_final_winner") and not params.get("lastmile_final"):
        params["lastmile_final"] = True
    if params != dict(cfg.params or {}):
        route_cfg = synth.Config.load(cfg.board, params=params)
    seeds = cec_search_policy.bounded_seed_plan(seed, candidates)
    candidate_results = []
    executor_evidence = {
        "schema": 1, "mode": "in_process", "bounded": True,
        "requested": len(seeds), "workers": 1,
        "seed_axis": "freerouting-cec",
    }
    if len(seeds) == 1:
        # The canonical pipeline's explicit route seed is a real reproducible
        # control even when the bounded ensemble contains one candidate.  Keep
        # legacy direct route_once callers byte-stable; opt in only at this
        # coordinator boundary, exactly as the multi-candidate worker does.
        previous_seed_axis = os.environ.get("CEC_FR_SEED_AXIS")
        os.environ["CEC_FR_SEED_AXIS"] = "1"
        try:
            result = synth.route_oracle_grade(
                str(board), cfg=route_cfg, passes=int(passes), opt=int(opt),
                seed=int(seeds[0]), fr_timeout=int(timeout),
                work_dir=str(output_dir), keep=True, verbose=True,
                craft_gates=True, thermal=thermal, precision=True,
                allow_route_access_repair=bool(allow_route_access_repair),
            )
            result = dict(result)
            result["route_candidate_diversity"] = {
                "schema": 1, "backend": "freerouting-cec-seed-axis",
                "enabled": True, "seed": int(seeds[0]),
            }
            candidate_results.append(result)
        finally:
            if previous_seed_axis is None:
                os.environ.pop("CEC_FR_SEED_AXIS", None)
            else:
                os.environ["CEC_FR_SEED_AXIS"] = previous_seed_axis
    else:
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing

        workers = min(
            len(seeds), max(1, int(route_workers or os.cpu_count() or 1)))
        payloads = []
        for candidate_seed in seeds:
            work = output_dir / ("candidate-%06d" % int(candidate_seed))
            work.mkdir(parents=True, exist_ok=True)
            payloads.append({
                "board": str(board), "board_name": cfg.board,
                "params": params, "passes": int(passes), "opt": int(opt),
                "seed": int(candidate_seed), "timeout": int(timeout),
                "thermal": thermal, "work_dir": str(work),
                "allow_route_access_repair": bool(
                    allow_route_access_repair),
            })
        context = multiprocessing.get_context("spawn")
        # A candidate may execute several bounded prefix routers plus the
        # residual router.  Keep that internal effort unchanged, but put a
        # finite outer wall around the worker generation.  The policy knob is
        # generic and optional; its default covers six full FR budgets plus
        # pcbnew import/admission time without allowing an overnight deadlock.
        default_candidate_watchdog = max(
            7200.0, float(timeout) * 6.0 + 1800.0)
        raw_watchdog = (params.get("route_worker_watchdog_s") or
                        os.environ.get("CEC_ROUTE_WORKER_WATCHDOG_S") or
                        default_candidate_watchdog)
        try:
            candidate_watchdog = max(60.0, float(raw_watchdog))
        except (TypeError, ValueError):
            candidate_watchdog = default_candidate_watchdog
        generation_watchdog = cec_process_pool.pool_wall_budget(
            candidate_watchdog, len(payloads), workers,
            cleanup_s=300.0, multiplier=1.0,
            minimum_s=candidate_watchdog)
        executor_evidence = {
            "schema": 1, "mode": "spawn_process_pool", "bounded": True,
            "requested": len(seeds), "workers": workers,
            "candidate_watchdog_s": round(candidate_watchdog, 3),
            "generation_watchdog_s": round(generation_watchdog, 3),
        }
        pool = ProcessPoolExecutor(
            max_workers=workers, mp_context=context)
        forced_shutdown = False
        future_payload = {}
        try:
            future_payload = {
                pool.submit(_route_candidate_worker, payload): payload
                for payload in payloads
            }
            for future in cec_process_pool.watched_as_completed(
                    pool, future_payload,
                    wall_timeout_s=generation_watchdog, poll_s=5.0):
                payload = future_payload[future]
                try:
                    candidate_results.append(future.result())
                except Exception as exc:                  # noqa: BLE001
                    candidate_results.append({
                        "seed": payload["seed"], "gate": False,
                        "routed": None, "drc": None, "unconnected": None,
                        "sort_key": [1, 99, 99, 99],
                        "worker_error": "%s: %s" % (
                            type(exc).__name__, exc),
                    })
        except cec_process_pool.WorkerPoolStalled as exc:
            forced_shutdown = True
            executor_evidence.update({
                "status": "stalled", "error": str(exc),
                "completed": len(candidate_results),
            })
            for future, payload in future_payload.items():
                if future.done():
                    continue
                candidate_results.append({
                    "seed": payload["seed"], "gate": False,
                    "routed": None, "drc": None, "unconnected": None,
                    "sort_key": [1, 99, 99, 99],
                    "worker_error": "WorkerPoolStalled: %s" % exc,
                })
        finally:
            shutdown = cec_process_pool.shutdown_process_pool(
                pool, force=forced_shutdown, grace_s=5.0)
            executor_evidence.setdefault("status", "complete")
            executor_evidence["shutdown"] = shutdown
            print("[route] executor watchdog: %s" %
                  json.dumps(executor_evidence, sort_keys=True), flush=True)
        candidate_results.sort(key=lambda row: int(row.get("seed") or 0))

    candidate_summary = [
        _route_candidate_summary(row) for row in candidate_results]
    batch_report = output_dir / "candidate-summary.json"
    result = cec_search_policy.select_candidate(candidate_results)
    if result is None:
        atomic_json(batch_report, {
            "schema": 1, "bounded": True,
            "hard_cap": cec_search_policy.MAX_ROUTE_CANDIDATES,
            "requested": len(seeds), "seeds": list(seeds),
            "winner_seed": None,
            "executor": executor_evidence,
            "candidates": candidate_summary,
        })
        raise PipelineBlocked(
            "bounded route ensemble produced no eligible board; "
            "candidate fail stack: %s" %
            _route_failure_digest(candidate_summary))

    # Multi-candidate execution retains compact evidence but only one board.
    # Loser work trees can be hundreds of MB and carry no release authority.
    if len(seeds) > 1:
        winner_source = Path(result["routed"]).resolve()
        winner_board = output_dir / "winner.kicad_pcb"
        copied = _copy_sidecars(winner_source, winner_board, cfg=cfg)
        result = dict(result)
        result["routed"] = str(winner_board.resolve())
        for candidate_seed in seeds:
            shutil.rmtree(
                output_dir / ("candidate-%06d" % int(candidate_seed)),
                ignore_errors=True)
    else:
        copied = []

    # Production parity with fresh-wave publication: run the deterministic
    # fabrication polish on the exact selected artifact, not merely as part of
    # the code signature.  The actuator evaluates isolated variants and only
    # adopts a monotonic winner.  Its admission also covers foreign-pour
    # ownership, so a cosmetic/DFM improvement cannot create a hidden power
    # corridor incursion.  Signoff below independently re-scores the resulting
    # bytes; a repair exception is retained as evidence without destroying an
    # otherwise valid routed artifact.
    fab_repair = {"schema": 1, "skipped": "route_artifact_missing"}
    _has_routed_artifact = bool(
        result.get("routed") and os.path.isfile(result["routed"]))
    if (_has_routed_artifact
            and os.environ.get("CEC_FAB_REPAIR", "1") == "1"):
        try:
            import cec_fab_repair
            fab_repair = cec_fab_repair.repair_admitted(result["routed"])
            after = dict(fab_repair.get("after") or {})
            for key in ("drc", "unconnected", "kelvin_ok", "diffpair_ok"):
                if key in after:
                    result[key] = after[key]
        except Exception as exc:                         # noqa: BLE001
            fab_repair = {
                "schema": 1, "skipped": "repair_error",
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
    elif _has_routed_artifact:
        fab_repair = {"schema": 1, "skipped": "policy_disabled"}
    result["fab_repair"] = fab_repair

    report = output_dir / "oracle.json"
    atomic_json(report, result)
    atomic_json(batch_report, {
        "schema": 1, "bounded": True,
        "hard_cap": cec_search_policy.MAX_ROUTE_CANDIDATES,
        "requested": len(seeds), "seeds": list(seeds),
        "winner_seed": result.get("seed"),
        "executor": executor_evidence,
        "candidates": candidate_summary,
    })
    routed = result.get("routed")
    artifacts = [str(report), str(batch_report)] + copied
    if routed and os.path.isfile(routed):
        artifacts += _copy_sidecars(routed, routed, cfg=cfg)
    return {
        "ok": bool(result.get("gate")),
        "artifact_produced": bool(routed and os.path.isfile(routed)),
        "winner_completion_enabled": bool(params.get("lastmile_final")),
        "candidate_budget": len(seeds),
        "winner_seed": result.get("seed"),
        "candidate_summary": str(batch_report),
        "fab_repair": fab_repair,
        "gate": bool(result.get("gate")),
        "board": str(Path(routed).resolve()) if routed else None,
        "report": str(report),
        "drc": result.get("drc"),
        "unconnected": result.get("unconnected"),
        "failed_terms": sorted(
            name for name, passed in (result.get("gate_terms") or {}).items()
            if not passed
        ),
        "blocker_summary": result.get("blocker_summary"),
        "_artifacts": artifacts,
    }


def _load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _independent_signoff(board, cfg, route_report, output_path):
    import cec_constraints
    import cec_fab_check
    import cec_fab_profile
    import cec_route_quality
    import cec_score
    import cec_synth_pipeline as synth
    import pcbnew

    oracle = _load_json(route_report)
    _hints, _pours, rules = synth._oracle_hints_pours(str(board))
    metrics = cec_score.score(str(board), rules)
    constraint_gate = cec_constraints.release_gate(
        str(board), {"sch": str(cfg.sch)}, phase="post_route"
    )
    board_db = pcbnew.LoadBoard(str(board))
    route_geometry = cec_route_quality.analyze_board(board_db)
    profile_name = cec_fab_profile.active_profile_name(
        board_db, hint=cfg.board
    )
    if profile_name:
        copper_oz = cec_fab_profile.stackup_oz(profile_name)["F.Cu"]
        fab = cec_fab_check.check(str(board), "jlcpcb", copper_oz, True)
    else:
        fab = {"error": "board has no declared fabrication profile"}

    fab_blockers = (
        int(fab.get("drc_total", 0) or 0)
        + len(fab.get("slivers") or ())
        + len(fab.get("islands") or ())
        + len(fab.get("drill_aspect") or ())
        + (1 if fab.get("error") or fab.get("artifact_error") else 0)
    )
    terms = {
        "route_oracle": oracle.get("gate") is True,
        "independent_score": bool(metrics.gates_pass),
        "drc_zero": int(metrics.drc) == 0,
        "connectivity_zero": int(metrics.unconnected) == 0,
        # Intermediate routing may carry inherited advisory geometry while it
        # monotonically improves connectivity.  Release may not: require the
        # whole-board craft verdict so ordinary-net covered overlaps and acute
        # backtracks are just as withholding as arbitrary headings or arcs.
        "route_geometry": bool(route_geometry.get("craft_ok", False)),
        "constraint_release": constraint_gate.get("ok") is True,
        "fabrication": fab_blockers == 0,
        "source_not_draft": not cfg.is_draft,
    }
    report = {
        "schema": SCHEMA,
        "board": str(Path(board).resolve()),
        "ok": all(terms.values()),
        "terms": terms,
        "failed_terms": sorted(name for name, value in terms.items() if not value),
        "metrics": {
            "gates_pass": bool(metrics.gates_pass),
            "drc": int(metrics.drc),
            "drc_types": dict(metrics.drc_types),
            "unconnected": int(metrics.unconnected),
            "kelvin_ok": bool(metrics.kelvin_ok),
            "diffpair_ok": bool(metrics.diffpair_ok),
            "tracks": int(metrics.tracks),
            "vias": int(metrics.vias),
            "length_mm": round(float(metrics.length), 3),
        },
        "constraint_gate": constraint_gate,
        "route_geometry": route_geometry,
        "fabrication": fab,
        "fab_blocker_count": fab_blockers,
        "oracle_report": str(Path(route_report).resolve()),
    }
    atomic_json(output_path, report)
    return report


def _tool_versions():
    versions = {"python": sys.version.split()[0]}
    for name, command in (
        ("kicad_cli", ["kicad-cli", "--version"]),
        ("git", ["git", "rev-parse", "HEAD"]),
    ):
        try:
            versions[name] = _run(command, timeout=30).stdout.strip()
        except Exception as exc:  # version evidence must be visible, not fatal
            versions[name] = "unavailable: %s" % exc
    return versions


def _manifest_payload(directory, *, board, source_signature, signoff,
                      extra=None):
    directory = Path(directory).resolve()
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name in (
            "manifest.json", "release-index.json"
        ):
            continue
        files.append({
            "path": path.relative_to(directory).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    payload = {
        "schema": SCHEMA,
        "board": board,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source_signature": source_signature,
        "signoff": signoff,
        "tool_versions": _tool_versions(),
        "files": files,
    }
    if extra:
        payload.update(extra)
    return payload


def write_content_manifest(directory, *, board, source_signature, signoff,
                           extra=None):
    directory = Path(directory).resolve()
    payload = _manifest_payload(
        directory, board=board, source_signature=source_signature,
        signoff=signoff, extra=extra
    )
    payload["content_signature"] = {
        "algorithm": "sha256",
        "canonical_json_sha256": digest_value(payload),
        "scope": "manifest payload excluding content_signature",
    }
    path = directory / "manifest.json"
    atomic_json(path, payload)
    return str(path)


def verify_content_manifest(path):
    path = Path(path).resolve()
    payload = _load_json(path)
    signature = payload.pop("content_signature", {})
    if signature.get("algorithm") != "sha256":
        return False, "missing sha256 content signature"
    if digest_value(payload) != signature.get("canonical_json_sha256"):
        return False, "manifest content signature mismatch"
    for row in payload.get("files") or ():
        artifact = path.parent / row["path"]
        if (
            not artifact.is_file()
            or artifact.stat().st_size != int(row["size"])
            or sha256_file(artifact) != row["sha256"]
        ):
            return False, "artifact mismatch: %s" % row["path"]
    return True, "verified"


def _deterministic_zip(directory, zip_path):
    directory = Path(directory).resolve()
    zip_path = Path(zip_path).resolve()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return str(zip_path)


def _copper_gerber_count(gerber_dir):
    count = 0
    for path in Path(gerber_dir).glob("*"):
        if not path.is_file():
            continue
        try:
            header = path.read_text(errors="ignore")[:4096]
        except OSError:
            continue
        if "TF.FileFunction,Copper," in header:
            count += 1
    return count


def _manufacturing_package(board, cfg, out_dir, source_signature,
                           signoff_report, route_report):
    import cec_fab_profile
    import pcbnew

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    package = out_dir / "package"
    if package.exists():
        backup = out_dir / ("package.previous.%d" % int(time.time()))
        os.replace(package, backup)
    package.mkdir(parents=True)
    gerbers = package / "gerbers"
    gerbers.mkdir()
    release_board = package / (cfg.board + ".kicad_pcb")
    copied = _copy_sidecars(board, release_board, cfg=cfg)
    _run([
        "kicad-cli", "pcb", "export", "gerbers", "--check-zones",
        "--board-plot-params", "-o", str(gerbers) + "/", str(release_board),
    ])
    _run([
        "kicad-cli", "pcb", "export", "drill", "--generate-map",
        "--map-format", "gerberx2", "--generate-report",
        "--report-path", str(package / "drill-report.txt"),
        "-o", str(gerbers) + "/", str(release_board),
    ])
    position = package / (cfg.board + "-pos.csv")
    _run([
        "kicad-cli", "pcb", "export", "pos", "--format", "csv",
        "--units", "mm", "--side", "both", "--exclude-dnp",
        "-o", str(position), str(release_board),
    ])
    bom_dir = package / "bom"
    bom_dir.mkdir()
    for source in sorted((Path(cfg.dir) / "bom").glob("*.csv")):
        shutil.copy2(source, bom_dir / source.name)
    shutil.copy2(signoff_report, package / "signoff.json")
    shutil.copy2(route_report, package / "oracle.json")

    enabled = cec_fab_profile.enabled_copper_layers(
        pcbnew.LoadBoard(str(release_board))
    )
    copper_gerbers = _copper_gerber_count(gerbers)
    drill_files = sorted(gerbers.glob("*.drl"))
    if copper_gerbers != len(enabled):
        raise RuntimeError(
            "fabrication export has %d copper Gerber(s), expected %d (%s)" % (
                copper_gerbers, len(enabled), ", ".join(enabled)
            )
        )
    if not drill_files:
        raise RuntimeError("fabrication export produced no Excellon drill file")
    if not position.is_file() or not list(bom_dir.glob("*.csv")):
        raise RuntimeError("assembly export is missing position or BOM data")

    manifest = write_content_manifest(
        package, board=cfg.board, source_signature=source_signature,
        signoff=_load_json(signoff_report), extra={
            "release_class": "FABRICATION_RELEASE",
            "enabled_copper_layers": list(enabled),
            "copper_gerber_count": copper_gerbers,
            "drill_file_count": len(drill_files),
        }
    )
    verified, reason = verify_content_manifest(manifest)
    if not verified:
        raise RuntimeError("release manifest verification failed: %s" % reason)
    zip_path = out_dir / (cfg.board + "-fabrication.zip")
    _deterministic_zip(package, zip_path)
    index = out_dir / "release-index.json"
    atomic_json(index, {
        "schema": SCHEMA,
        "board": cfg.board,
        "package": str(package),
        "manifest": manifest,
        "manifest_sha256": sha256_file(manifest),
        "zip": str(zip_path),
        "zip_sha256": sha256_file(zip_path),
        "verified": True,
    })
    return {
        "ok": True,
        "released": True,
        "package": str(package),
        "manifest": manifest,
        "zip": str(zip_path),
        "index": str(index),
        "_artifacts": copied + [
            str(path) for path in package.rglob("*") if path.is_file()
        ] + [str(zip_path), str(index)],
    }


def _withheld_evidence(board, cfg, out_dir, source_signature,
                       signoff_report, route_report):
    out_dir = Path(out_dir).resolve()
    evidence = out_dir / "withheld"
    evidence.mkdir(parents=True, exist_ok=True)
    review_board = evidence / (cfg.board + "-withheld.kicad_pcb")
    copied = _copy_sidecars(board, review_board, cfg=cfg)
    shutil.copy2(signoff_report, evidence / "signoff.json")
    shutil.copy2(route_report, evidence / "oracle.json")
    manifest = write_content_manifest(
        evidence, board=cfg.board, source_signature=source_signature,
        signoff=_load_json(signoff_report), extra={
            "release_class": "WITHHELD_REVIEW_ONLY",
            "manufacturing_outputs_emitted": False,
        }
    )
    verified, reason = verify_content_manifest(manifest)
    if not verified:
        raise RuntimeError("withheld manifest verification failed: %s" % reason)
    return {
        "ok": True,
        "released": False,
        "board": str(review_board),
        "manifest": manifest,
        "reason": "release gates failed; Gerbers deliberately not generated",
        "_artifacts": copied + [str(evidence / "signoff.json"),
                                str(evidence / "oracle.json"), manifest],
    }


def _dashboard_stage(board, cfg, route_report):
    import cec_dashboard

    summary = cec_dashboard.archive_board(
        str(board), "%s-full-pipeline" % cfg.board,
        provenance_path=str(route_report), archive_role="pipeline"
    )
    summary_path = Path(cec_dashboard.ARCHIVE_ROOT) / summary["id"] / "summary.json"
    return {
        "ok": summary.get("verdict") in ("CLEAN", "FAILED"),
        "archive_id": summary.get("id"),
        "verdict": summary.get("verdict"),
        "viewer_url": "http://localhost:8090/?id=%s" % summary.get("id"),
        "panel_urls": summary.get("panel_urls") or {},
        "_artifacts": [str(summary_path)],
    }


def run_full_pipeline(
    *, board_name, input_board, out_dir, replace_placement=False,
    strategies=("plain", "dataflow", "thermal", "hybrid"),
    placement_seeds=(0, 1), workers=None, grid_mm=0.5,
    preflight_iters=40, backend="auto", passes=16, opt=30, route_seed=0,
    route_candidates=1, route_workers=None, route_timeout=1800,
    thermal="lazy", craft_trials=128,
    craft_rounds=12, craft_epochs=3, resume=True, dashboard=True,
    allow_derived_input=False, completion_report=None,
    fresh_placement_only=False,
):
    import cec_synth_pipeline as synth

    cfg = synth.Config.load(board_name)
    if fresh_placement_only:
        outline_policy = dict(cfg.params.get("outline_compaction") or {})
        outline_policy.update({
            "include_fresh_placement": True,
            "include_incremental": False,
        })
        cfg.params["outline_compaction"] = outline_policy
    # The canonical production entry point always earns routing admission on a
    # bounded exact shortlist. Board policies may raise/lower these budgets,
    # but omitting the keys must not silently revert to proxy-only placement.
    cfg.params.setdefault("placement_route_preflight_topk", 4)
    cfg.params.setdefault("placement_route_preflight_grid_mm", 1.0)
    cfg.params.setdefault("placement_route_preflight_iters", 4)
    cfg.params.setdefault("placement_route_preflight_backend", backend)
    cfg.params.setdefault("placement_route_preflight_multiresolution", True)
    # Exact candidate probes are independent CPU workloads. Use a bounded
    # half-machine pool (capped for memory headroom) unless board policy has a
    # measured override; GPU adjudication remains serialized by the worker
    # selector because concurrent contexts would only contend for one device.
    cfg.params.setdefault("placement_route_preflight_workers", min(
        8, max(1, (os.cpu_count() or 1) // 2)))
    cfg.params.setdefault("placement_route_repair_trials", 16)
    cfg.params.setdefault("placement_route_repair_rounds", 2)
    cfg.params.setdefault("placement_route_repair_full_evals", 4)
    # One repair pass can invalidate its own exact power reservation geometry.
    # Permit one bounded follow-up against the regenerated authority; the
    # placement-stage transaction keeps only strict post-authority progress.
    cfg.params.setdefault("placement_power_route_coopt_rounds", 2)
    cfg.params.setdefault("placement_power_replan_candidates", 2)
    input_board = Path(input_board or cfg.pcb).resolve()
    if not input_board.is_file():
        raise FileNotFoundError(
            "no current placement board; pass --input-board explicitly"
        )
    cfg, route_authority = synth.config_with_board_route_authority(
        cfg, str(input_board))
    if route_authority.get("applicable") and not route_authority.get("ok"):
        raise PipelineBlocked(
            "input route authority refused: %s" %
            route_authority.get("reason", "unknown"))
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    board_identity = _board_identity(cfg)
    journal = StageJournal(out_dir / "pipeline-state.json", board_identity,
                           resume=resume)
    source_signature = _files_signature(_source_files(cfg, input_board))
    common = {
        "source": source_signature["sha256"],
        "board": board_identity,
        "policy": cfg.params,
        "route_authority": route_authority,
        "completion_evidence": (
            digest_value(completion_report)
            if completion_report is not None else None),
    }

    intake_path = out_dir / "01-source-intake.json"
    intake = journal.run(
        "source_intake",
        digest_value({**common, "code": _code_signature(
            "cec_constraints.py", "cec_beta_manifest.py",
            "cec_generalization_gate.py", "cec_beta_electrical_audit.py",
            "cec_sch_gates.py"
        ), "coordinator": _callable_signature(_source_intake)}),
        lambda: {
            **_source_intake(
                cfg, input_board, intake_path,
                allow_derived_input=allow_derived_input),
            "route_authority": route_authority,
            "report": str(intake_path), "_artifacts": [str(intake_path)],
        },
    )
    if not intake.get("ok"):
        raise PipelineBlocked(
            "source intake refused: %s" % (
                (intake.get("manifest_errors") or [])
                + ([((intake.get("project_rule_authority") or {}).get(
                    "reason") or "project rule authority failed")]
                   if not (intake.get("project_rule_authority") or {}).get(
                       "ok", True) else [])
                + ((intake.get("intake") or {}).get("reasons") or [])
                + ((intake.get("electrical_source_audit") or {}).get(
                    "reasons") or [])
            )
        )

    placed_board = out_dir / "02-placement" / "board.kicad_pcb"
    placement = journal.run(
        "placement",
        digest_value({
            **common, "input_board": sha256_file(input_board),
            "replace": replace_placement, "strategies": strategies,
            "seeds": placement_seeds, "craft_trials": craft_trials,
            "craft_rounds": craft_rounds, "craft_epochs": craft_epochs,
            "completion_evidence": common["completion_evidence"],
            "code": _code_closure_signature(
                "cec_synth_pipeline.py", "cec_boarddb.py",
                "cec_future_congestion.py", "cec_precision_route.py"
            ), "coordinator": _callable_signature(_placement_stage),
        }),
        lambda: _placement_stage(
            cfg, input_board, placed_board, replace=replace_placement,
            strategies=strategies, seeds=placement_seeds, workers=workers,
            craft_trials=craft_trials, craft_rounds=craft_rounds,
            craft_epochs=craft_epochs,
            completion_report=completion_report,
        ),
    )
    if not placement.get("ok"):
        raise PipelineBlocked(
            "placement admission refused; see %s" % placement.get("report")
        )

    preflight = journal.run(
        "route_preflight",
        digest_value({
            **common, "placement": sha256_file(placed_board),
            "grid_mm": grid_mm, "iters": preflight_iters,
            "backend": backend,
            "code": _code_signature(
                "cec_route_preflight.py", "cec_coord_router.py",
                "cec_route_awareness_service.py", "cec_pair_return.py"
            ), "coordinator": _callable_signature(_preflight_stage),
        }),
        lambda: _preflight_stage(
            placed_board, out_dir / "03-preflight", cfg,
            grid_mm=grid_mm, iterations=preflight_iters, backend=backend
        ),
    )
    if not preflight.get("ok"):
        raise PipelineBlocked(
            "routing preflight could not produce trustworthy evidence"
        )
    if not preflight.get("admission_gate"):
        raise PipelineBlocked(
            "routing preflight admission refused; see %s" %
            preflight.get("report")
        )

    route_access_repair = _route_access_repair_allowed(
        intake, placement)
    route = journal.run(
        "precision_detailed_route",
        digest_value({
            **common, "placement": sha256_file(placed_board),
            "preflight": sha256_file(preflight["report"]),
            "passes": passes, "opt": opt, "seed": route_seed,
            "route_candidates": route_candidates,
            "route_workers": route_workers,
            "timeout": route_timeout, "thermal": thermal,
            "allow_route_access_repair": route_access_repair,
            "code": _code_closure_signature(
                "cec_synth_pipeline.py", "cec_precision_route.py",
                "cec_staged_fr.py", "cec_pair_return.py",
                "cec_decoupler_cell.py", "cec_ground_plane.py",
                "cec_completion_evidence.py", "cec_fab_repair.py",
                "cec_search_policy.py", "cec_pour_clearance.py",
                "cec_constraints.py"
            ), "coordinator": _callable_signature(_route_stage),
        }),
        lambda: _route_stage(
            placed_board, out_dir / "04-route", cfg, passes=passes,
            opt=opt, seed=route_seed, timeout=route_timeout, thermal=thermal,
            candidates=route_candidates, route_workers=route_workers,
            allow_route_access_repair=route_access_repair,
        ),
    )
    routed_board = Path(route.get("board") or placed_board).resolve()
    signoff_path = out_dir / "05-signoff.json"
    signoff = journal.run(
        "independent_signoff",
        digest_value({
            **common, "routed": sha256_file(routed_board),
            "oracle": sha256_file(route["report"]),
            "code": _code_signature(
                "cec_constraints.py", "cec_score.py", "cec_fab_check.py",
                "cec_fab_profile.py", "cec_route_quality.py",
                "cec_impedance.py", "cec_thermal2d.py"
            ), "coordinator": _callable_signature(_independent_signoff),
        }),
        lambda: {
            **_independent_signoff(
                routed_board, cfg, route["report"], signoff_path
            ),
            "report": str(signoff_path), "_artifacts": [str(signoff_path)],
        },
    )

    if signoff.get("ok"):
        package = journal.run(
            "manufacturing_release",
            digest_value({
                **common, "routed": sha256_file(routed_board),
                "signoff": sha256_file(signoff_path),
                "code": _code_signature("cec_fab_profile.py"),
            }),
            lambda: _manufacturing_package(
                routed_board, cfg, out_dir / "06-release",
                source_signature, signoff_path, route["report"]
            ),
        )
    else:
        package = journal.run(
            "withheld_evidence",
            digest_value({
                **common, "routed": sha256_file(routed_board),
                "signoff": sha256_file(signoff_path),
            }),
            lambda: _withheld_evidence(
                routed_board, cfg, out_dir / "06-release",
                source_signature, signoff_path, route["report"]
            ),
        )

    dash = None
    if dashboard:
        dash = journal.run(
            "dashboard_archive",
            digest_value({
                "routed": sha256_file(routed_board),
                "oracle": sha256_file(route["report"]),
                "code": _code_signature("cec_dashboard.py"),
            }),
            lambda: _dashboard_stage(routed_board, cfg, route["report"]),
        )

    result = {
        "schema": SCHEMA,
        "status": "RELEASED" if signoff.get("ok") else "WITHHELD",
        "board": board_identity,
        "routed_board": str(routed_board),
        "source_signature": source_signature,
        "preflight": preflight,
        "route": route,
        "signoff": signoff,
        "package": package,
        "dashboard": dash,
        "journal": str(journal.path),
    }
    result_path = out_dir / "pipeline-result.json"
    atomic_json(result_path, result)
    journal.data["result"] = {
        "status": result["status"], "path": str(result_path),
        "sha256": sha256_file(result_path),
    }
    journal._write()
    return result


def run_route_probe(*, board_name, placement_board, out_dir, passes=16,
                    opt=30, route_seed=0, route_candidates=1,
                    route_workers=None, route_timeout=1800,
                    thermal="lazy", allow_route_access_repair=False):
    """Run only detailed routing on an already admitted placement artifact.

    This is a bounded diagnostic/resume entry point, not a fabrication bypass.
    It requires the canonical placement report and frozen route authority next
    to the PCB, runs the exact same route ensemble as the full pipeline, and
    deliberately emits neither independent signoff nor manufacturing files.
    A file-backed CLI also gives multiprocessing workers a real ``__main__``;
    ad-hoc stdin wrappers cannot safely exercise the repair workers.
    """
    import cec_synth_pipeline as synth

    placement_board = Path(placement_board).resolve()
    if not placement_board.is_file():
        raise FileNotFoundError(
            "route probe placement does not exist: %s" % placement_board)
    placement_report = placement_board.with_name(
        placement_board.stem + ".placement.json")
    if not placement_report.is_file():
        raise PipelineBlocked(
            "route-only probe requires sibling canonical placement report: "
            "%s" % placement_report)
    placement = _load_json(placement_report)
    if not placement.get("ok"):
        raise PipelineBlocked(
            "route-only probe refused non-admitted placement: %s" %
            placement_report)

    cfg = synth.Config.load(board_name)
    cfg, authority = synth.config_with_board_route_authority(
        cfg, str(placement_board))
    if (not authority.get("ok") or
            (authority.get("applicable") and not authority.get("bound"))):
        raise PipelineBlocked(
            "route-only probe requires matching frozen route authority: %s" %
            (authority.get("reason") or "not bound"))

    # A sibling placement report is a record of the code and policy that
    # produced it, not permanent admission authority.  New generic gates can
    # legitimately prove that an older open placement cannot construct a
    # mandatory local cell (for example, no legal decoupler return via).  A
    # route-only probe must re-evaluate that exact board before spending the
    # detailed-router budget; otherwise a stale ``ok`` report can be shown as
    # the current candidate and fail only after several routing tiers.
    #
    # Deferral is legal only for a board that actually contains copper.  The
    # CLI's ``--allow-derived-input`` is intake provenance, not evidence that
    # a clean placement has old routes which the repair transaction may rip
    # up.  Conflating the two hid placement-owned local-PI failures behind a
    # route-owned label.
    import pcbnew
    loaded = pcbnew.LoadBoard(str(placement_board))
    if loaded is None:
        raise PipelineBlocked(
            "route-only probe could not load placement: %s" %
            placement_board)
    routed_input = any(True for _item in loaded.GetTracks())
    current_craft = synth.placement_craft_evidence(
        str(placement_board), cfg=cfg, relief_diagnostics=False)
    current_gate = _placement_craft_gate(
        current_craft,
        routed_input=bool(routed_input and allow_route_access_repair))
    if not current_gate.get("ok"):
        decoupler = current_craft.get("decoupler") or {}
        raise PipelineBlocked(
            "route-only probe refused stale/non-admitted placement under "
            "current rules: %s" % (
                (decoupler.get("violations") or
                 current_gate.get("blockers") or
                 current_craft.get("errors") or
                 ["placement craft gate failed"])[:6],
            ))

    out_dir = Path(out_dir).resolve()
    return _route_stage(
        placement_board, out_dir / "04-route", cfg,
        passes=passes, opt=opt, seed=route_seed, timeout=route_timeout,
        thermal=thermal, candidates=route_candidates,
        route_workers=route_workers,
        allow_route_access_repair=bool(
            routed_input and allow_route_access_repair))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True,
                        help="current-BETA board key")
    parser.add_argument("--input-board", default=None,
                        help="authoritative current placement .kicad_pcb")
    parser.add_argument(
        "--allow-derived-input", action="store_true",
        help=("explicitly permit a non-manifest probe/derived PCB; production "
              "runs default to the current manifest placement"))
    parser.add_argument("--out", default=None,
                        help="run directory (default build/full-pipeline/BOARD)")
    parser.add_argument("--replace-placement", action="store_true",
                        help="replace placements inside the existing outline")
    parser.add_argument(
        "--fresh-placement-only", action="store_true",
        help=("with --replace-placement, explicitly bypass an incumbent-only "
              "outline policy and evaluate the requested fresh strategies "
              "and seeds"))
    parser.add_argument(
        "--route-only-probe", action="store_true",
        help=("run the canonical bounded route ensemble on a sibling-report "
              "admitted placement; no signoff or manufacturing output"))
    parser.add_argument("--strategies", default="plain,dataflow,thermal,hybrid")
    parser.add_argument("--placement-seeds", default="0,1")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--craft-trials", type=int, default=128,
                        help="bounded proposals per electrical craft round")
    parser.add_argument("--craft-rounds", type=int, default=12,
                        help="monotonic repair rounds per bounded epoch")
    parser.add_argument("--craft-epochs", type=int, default=3,
                        help="bounded incumbent-continuation epochs (max 4)")
    parser.add_argument("--grid-mm", type=float, default=0.5)
    parser.add_argument("--preflight-iters", type=int, default=40)
    parser.add_argument("--backend", choices=("auto", "cpu", "gpu"),
                        default="auto")
    parser.add_argument("--passes", type=int, default=16)
    parser.add_argument("--opt", type=int, default=30)
    parser.add_argument("--route-seed", type=int, default=0)
    parser.add_argument(
        "--route-candidates", type=int, default=1,
        help="bounded independent route candidates (hard-capped at 8)")
    parser.add_argument(
        "--route-workers", type=int, default=0,
        help="parallel route workers (default: candidate count / CPU cap)")
    parser.add_argument("--route-timeout", type=int, default=1800)
    parser.add_argument("--thermal", choices=("always", "lazy"),
                        default="lazy")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument(
        "--completion-report", default=None,
        help=("prior detailed-route oracle whose refusal certificates guide "
              "the bounded placement repair; all moves still require exact "
              "placement, power, and route admission"))
    args = parser.parse_args(argv)
    if args.fresh_placement_only and not args.replace_placement:
        parser.error("--fresh-placement-only requires --replace-placement")
    completion_report = None
    if args.completion_report:
        completion_path = Path(args.completion_report).resolve()
        if completion_path.stat().st_size > 32 * 1024 * 1024:
            parser.error("--completion-report exceeds 32 MiB")
        try:
            completion_report = json.loads(
                completion_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error("cannot read --completion-report: %s" % exc)
        if not isinstance(completion_report, dict):
            parser.error("--completion-report must contain a JSON object")
    out = Path(args.out).resolve() if args.out else (
        ROOT / "build" / "full-pipeline" / args.board
    )
    if args.route_only_probe:
        if not args.input_board:
            parser.error("--route-only-probe requires --input-board")
        route = run_route_probe(
            board_name=args.board, placement_board=args.input_board,
            out_dir=out, passes=args.passes, opt=args.opt,
            route_seed=args.route_seed,
            route_candidates=args.route_candidates,
            route_workers=(args.route_workers or None),
            route_timeout=args.route_timeout, thermal=args.thermal,
            allow_route_access_repair=args.allow_derived_input)
        print("\n%s" % json.dumps({
            "status": "ROUTE_PROBE_COMPLETE",
            "board": route.get("board"),
            "drc": route.get("drc"),
            "unconnected": route.get("unconnected"),
            "failed_terms": route.get("failed_terms"),
            "report": route.get("report"),
        }, indent=2))
        return 0
    result = run_full_pipeline(
        board_name=args.board, input_board=args.input_board, out_dir=out,
        replace_placement=args.replace_placement,
        strategies=tuple(x for x in args.strategies.split(",") if x),
        placement_seeds=tuple(
            int(x) for x in args.placement_seeds.split(",") if x != ""
        ),
        workers=(args.workers or None), grid_mm=args.grid_mm,
        craft_trials=args.craft_trials, craft_rounds=args.craft_rounds,
        craft_epochs=args.craft_epochs,
        preflight_iters=args.preflight_iters, backend=args.backend,
        passes=args.passes, opt=args.opt, route_seed=args.route_seed,
        route_candidates=args.route_candidates,
        route_workers=(args.route_workers or None),
        route_timeout=args.route_timeout, thermal=args.thermal,
        resume=not args.no_resume, dashboard=not args.no_dashboard,
        allow_derived_input=args.allow_derived_input,
        completion_report=completion_report,
        fresh_placement_only=args.fresh_placement_only,
    )
    print("\n%s" % json.dumps({
        "status": result["status"],
        "routed_board": result["routed_board"],
        "failed_terms": result["signoff"].get("failed_terms"),
        "dashboard": result.get("dashboard"),
        "journal": result["journal"],
    }, indent=2))
    return 0 if result["status"] == "RELEASED" else 2


def _reexec_workspace_python():
    """Run the production CLI in the repository's single managed runtime.

    CUDA packages are intentionally installed only in ``.venv`` to avoid a
    second multi-hundred-megabyte wheel in the system/user site.  A plain
    ``python3 scripts/cec_full_pipeline.py`` previously bypassed that runtime
    and made explicit GPU preflight fail despite a healthy device and CuPy
    install.  Imported/library use is unaffected; this is only called by the
    executable entry point.  Set CEC_KEEP_CALLER_PYTHON=1 for controlled
    interpreter-ablation tests.
    """
    if os.environ.get("CEC_KEEP_CALLER_PYTHON") == "1":
        return
    candidate = ROOT / ".venv" / "bin" / "python"
    # Venv launchers are commonly symlinks to /usr/bin/python3. Comparing
    # resolved executable paths therefore says system Python and venv Python
    # are identical even though only the latter initializes the venv prefix
    # and site-packages. ``sys.prefix`` is the environment identity.
    same = Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()
    if candidate.is_file() and os.access(candidate, os.X_OK) and not same:
        os.execv(str(candidate), [
            str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]])


if __name__ == "__main__":
    _reexec_workspace_python()
    try:
        sys.exit(main())
    except PipelineBlocked as exc:
        print("PIPELINE BLOCKED: %s" % exc, file=sys.stderr)
        sys.exit(2)
