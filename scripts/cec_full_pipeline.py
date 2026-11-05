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
import math
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
        import cec_stage_admission
        old = self.data["stages"].get(name) or {}
        if (
            self.resume
            and old.get("status") == "complete"
            and old.get("input_digest") == input_digest
            and artifacts_match(old.get("artifacts") or ())
        ):
            print("  [%-24s] RESUME-%s %s" % (
                name, cec_stage_admission.label(old.get("result")),
                input_digest[:12]), flush=True)
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
                "admission_ok": cec_stage_admission.admission_ok(raw),
                "input_digest": input_digest,
                "elapsed_s": round(time.monotonic() - started, 3),
                "artifacts": artifacts,
                "result": raw,
            }
            self.data["stages"][name] = record
            self._write()
            print(
                "  [%-24s] %-6s %.1fs" % (
                    name, cec_stage_admission.label(raw),
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
            # Spawned physical stages can attach a structured causal
            # certificate. Preserve it across the stage boundary alongside
            # the traceback, rather than flattening it into one error string.
            evidence = getattr(exc, "failure_evidence", None)
            if isinstance(evidence, dict):
                self.data["stages"][name]["failure_evidence"] = copy.deepcopy(evidence)
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


def _copy_sidecars(source_board, destination_board, cfg=None, *, replacement_seed=False):
    """Copy one executable PCB artifact family without dropping authority.

    A pour plan and frozen pour-first state are inputs to preflight and routing,
    not optional reports.  Every canonical stage boundary must preserve them
    when it renames ``foo.kicad_pcb`` to ``board.kicad_pcb``; otherwise the
    next stage reconstructs legacy geometry and quite correctly fails closed.
    """
    import cec_fr
    import cec_interface_eco
    eco_record = cec_interface_eco.read_status(source_board)
    invalidated = bool(eco_record and eco_record.get('route_authority_invalidated'))
    if invalidated and not replacement_seed:
        cec_interface_eco.require_rebuilt(source_board)

    source_board = Path(source_board).resolve()
    destination_board = Path(destination_board).resolve()
    destination_board.parent.mkdir(parents=True, exist_ok=True)
    if invalidated:
        if source_board == destination_board:
            raise ValueError('replacement normalization must use a disposable copy')
        # An interrupted copy/sync remains explicitly unadmitted. Do not copy
        # old pour plans, frozen authority or route certificates into this seed.
        atomic_json(destination_board.with_suffix('.interface-eco.json'), eco_record)
    if source_board != destination_board:
        shutil.copy2(source_board, destination_board)
    copied = [str(destination_board)]
    if not invalidated:
        copied.extend(cec_fr.copy_project_sidecars(
            str(source_board), str(destination_board)))
        # Search ordering survives a no-change continuation, but is never an
        # executable geometry authority. The reader binds it to exact PCB bytes.
        for extension in ('.placement-search.json', '.route-search.json'):
            search_source = source_board.with_suffix(extension)
            if search_source.is_file():
                search_destination = destination_board.with_suffix(extension)
                if search_source != search_destination:
                    shutil.copy2(search_source, search_destination)
                copied.append(str(search_destination))
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
    refusal = {}
    diagnostic = None
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
                    try:
                        if exact_state.is_file():
                            refusal = json.loads(
                                exact_state.read_text(encoding="utf-8")) or {}
                    except (OSError, TypeError, ValueError,
                            json.JSONDecodeError):
                        refusal = {}
                    if cfg.params.get("power_failure_artifact_dir"):
                        import cec_power_failure
                        diagnostic = cec_power_failure.retain_exact_trial(
                            exact_board, exact_state, cfg.params["power_failure_artifact_dir"],
                            limit=cfg.params.get("power_failure_artifact_limit", 2))
                    raise
    except Exception as exc:                           # noqa: BLE001
        result = {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "exact_filled_power_admission_failed",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "state": str(state_path),
            "protected_nets": list(frozen_nets),
        }
        if diagnostic:
            result["diagnostic"] = diagnostic
        if refusal.get("exact_admission"):
            result["admission"] = refusal["exact_admission"]
            result["generated_zone_canonicalization"] = refusal.get(
                "generated_zone_canonicalization")
            result["floating_zone_cleanup"] = refusal.get(
                "floating_zone_cleanup")
        if refusal.get("local_pin_access"):
            # Preserve the producer's bounded package-local refusal in the
            # placement journal.  Without it, a source/sink proof named the
            # disconnected pads but hid the stage that had already tried to
            # join them, making a route-authority failure look like a generic
            # fill problem.
            result["local_pin_access"] = refusal["local_pin_access"]
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


def _requires_frozen_route_authority(cfg):
    """Return whether routing must consume placement-time power authority.

    Older policies used ``pour_first``/``pour_plan`` as the only signal. A
    current board can instead request the same exact current-corridor contract
    through the route recipe: reserved pours plus over-under, pickup, inner
    power, or explicit pour asks. Treat either spelling as authoritative so a
    route entry point cannot silently re-plan power after important signal
    copper has already been committed.
    """
    params = dict(getattr(cfg, "params", {}) or {})
    if params.get("pour_first") or params.get("pour_plan"):
        return True
    return bool(
        params.get("pour_reserve")
        and (params.get("overunder")
             or params.get("power_pickup")
             or params.get("inner_power_routing")
             or params.get("pour_asks")))


def _ensure_placement_route_authority_in_process(
        cfg, board, *, allow_authored_prefix=False):
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
    if not _requires_frozen_route_authority(cfg):
        return {"schema": 1, "ok": True, "applicable": False,
                "reason": "power_route_authority_not_requested",
                "_artifacts": []}
    loaded = pcbnew.LoadBoard(str(board))
    if loaded is None:
        return {"schema": 1, "ok": False, "applicable": True,
                "reason": "placement_board_unreadable", "_artifacts": []}
    if (any(True for _item in loaded.GetTracks())
            and not allow_authored_prefix):
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
        session.cfg, str(board), allow_routed=allow_authored_prefix)
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
            "existing_authority_binding": existing,
            "replaced_exact_invalid_state": replaced_exact_invalid_state,
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


def _ensure_placement_route_authority(
        cfg, board, *, allow_authored_prefix=False):
    """Freeze exact placement power in a clean process when requested.

    The authority compiler performs the heaviest sequence of legacy KiCad
    load/fill/save calls in placement. Keep that sequence out of the
    coordinator so subsequent mechanical finishers and profile checks cannot
    inherit a dead process-global SWIG board proxy.
    """
    if not (cfg.params or {}).get(
            "route_authority_process_isolation", False):
        return _ensure_placement_route_authority_in_process(
            cfg, board, allow_authored_prefix=allow_authored_prefix)
    result = _run_priority_placement_operation_isolated(
        "ensure-authority", cfg, board,
        allow_authored_prefix=allow_authored_prefix)
    state = str(result.get("state") or "")
    if result.get("ok") and result.get("bound") and state:
        cfg.params["pourfirst_state"] = state
    result["process_isolated"] = True
    return result


def _diagnose_power_construction(cfg, board):
    """One bounded private exact-power probe for a rail-only placement block.

    This does not promote its board/state, mutate the active recipe or turn
    a construction success into placement admission. The ordinary compiler
    owns its actual fill/connectivity proof and retains rejected geometry.
    """
    board = Path(board).resolve()
    work = Path(tempfile.mkdtemp(prefix='power-construction-diagnostic-',
                                 dir=board.parent))
    inputs = _artifact_rows(p for p in _placement_authority_family(board)
                           if p.is_file())
    result = dict(schema=1, applicable=True, release_authority=False,
                  route_admission=False, source_sha256=sha256_file(board),
                  directory=str(work))
    started = time.monotonic()
    try:
        private = work / 'board.kicad_pcb'
        _copy_sidecars(board, private)
        probe_cfg = copy.deepcopy(cfg)
        probe_cfg.params = dict(probe_cfg.params or {})
        probe_cfg.params.update(route_authority_process_isolation=True,
            priority_operation_timeout_s=120,
            power_failure_artifact_dir=str(work / 'exact-failures'))
        authority = _ensure_placement_route_authority(
            probe_cfg, private, allow_authored_prefix=True)
        result.update(exact_power_ok=authority.get('ok') is True,
                      authority=authority,
                      reason='diagnostic_complete_not_placement_admission')
    except Exception as exc:                             # noqa: BLE001
        result.update(exact_power_ok=False, reason='diagnostic_operation_failed',
                      error='%s: %s' % (type(exc).__name__, str(exc)[:1000]),
                      operation_failure=dict(getattr(exc, 'failure_evidence', {}) or {}))
    result.update(wall_s=round(time.monotonic() - started, 3),
                  input_families_unchanged=artifacts_match(inputs))
    if not result['input_families_unchanged']:
        result.update(exact_power_ok=False, reason='diagnostic_input_family_changed')
    atomic_json(work / 'diagnostic.json', result)
    return result


def _source_files(cfg, input_board):
    paths = [Path(input_board).resolve(), Path(cfg.sch).resolve()]
    paths.extend(Path(input_board).resolve().with_suffix(suffix) for suffix in (
        '.kicad_pro', '.kicad_dru', '.pourplan.json', '.railreport.json',
        '.cellreport.json', '.pourfirst-state.json',
        '.interface-eco.json', '.interface-eco.pending.json',
        '.priority-replacements.json', '.placement-search.json',
        '.route-lineage.json'))
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_sch")))
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_pro")))
    paths.extend(sorted(Path(cfg.dir).glob("*.kicad_dru")))
    paths.extend(sorted(Path(cfg.dir).glob("pipeline-policy.json")))
    paths.extend(sorted((Path(cfg.dir) / "bom").glob("*.csv")))
    assembly=(getattr(cfg,'params',{}) or {}).get('assembly_envelope')
    if assembly:
        from cec_assembly_envelope import dependencies
        paths.extend(dependencies(assembly,ROOT))
    # Fresh placement loads library geometry, not only the embedded lands in
    # the staging PCB. A corrected land with unchanged schematic text must
    # invalidate normalized-source and placement checkpoints too.
    import cec_sch_gates
    import cec_pcb
    paths.extend(sorted(Path(cfg.dir).glob("*-lib-table")))
    for part in cec_sch_gates.inventory(str(cfg.sch)).values():
        footprint = str(part.get("footprint") or "")
        if not part.get("on_board", True) or not footprint:
            continue
        if ":" not in footprint:
            raise PipelineBlocked("unqualified schematic footprint: %s" % footprint)
        library, name = footprint.split(":", 1)
        land = Path(cec_pcb.fp_path(library, name)).resolve()
        if not land.is_file():
            raise PipelineBlocked("schematic footprint source is missing: %s" % land)
        paths.append(land)
    for cell in (getattr(cfg, "params", {}) or {}).get("blueprint_cells", ()):
        template = cell.get("template")
        if isinstance(template, str):
            source = Path(template)
            source = source if source.is_absolute() else ROOT / source
            if not source.is_file():
                raise PipelineBlocked("blueprint source is missing: %s" % source)
            paths.append(source)
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


def _source_sync_extra_pad_nets(cfg):
    """Parse explicit board-only electrical lands for source normalization."""
    raw = (getattr(cfg, "params", {}) or {}).get(
        "source_sync_extra_pad_nets", {}) or {}
    if not isinstance(raw, dict):
        raise PipelineBlocked(
            "source_sync_extra_pad_nets must be a REF.PAD-to-net mapping")
    parsed = {}
    for refpad, net in raw.items():
        try:
            ref, pad = str(refpad).rsplit(".", 1)
        except ValueError as exc:
            raise PipelineBlocked(
                "invalid source_sync_extra_pad_nets key %r" % refpad) from exc
        if not ref or not pad or not str(net):
            raise PipelineBlocked(
                "invalid source_sync_extra_pad_nets entry %r" % refpad)
        parsed[(ref, pad)] = str(net)
    return parsed


def _parse_source_sync_stdout(stdout):
    """Parse the small ``key=repr(value)`` contract emitted by sync CLI."""
    report = {}
    for raw in str(stdout or "").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        try:
            report[key] = ast.literal_eval(value.strip())
        except (SyntaxError, ValueError):
            report[key] = value.strip()
    return report


def _run_source_sync_process(cfg, work_board, *, remove_refs=()):
    """Refresh one working PCB in an isolated KiCad Python process.

    KiCad 10's legacy SWIG bindings can leave later board handles invalid after
    a large in-process copper strip or footprint replacement.  Source
    normalization is therefore a process boundary, just like routed-placement
    rehydration.  Exit 2 is a structured first-pass orphan report, not a crash.
    """
    command = [
        sys.executable,
        str(HERE / "cec_sync_pcb_from_schematic.py"),
        "--schematic", str(cfg.sch), "--pcb", str(work_board),
        "--rip-all-copper", "--add-missing",
        "--replace-mismatched-footprints",
    ]
    for ref in sorted(set(remove_refs or ())):
        command.extend(("--remove-ref", str(ref)))
    for (ref, pad), net in sorted(_source_sync_extra_pad_nets(cfg).items()):
        command.extend(("--extra-pad-net", "%s.%s=%s" % (ref, pad, net)))
    process = subprocess.run(command, text=True, capture_output=True)
    report = _parse_source_sync_stdout(process.stdout)
    if process.returncode not in (0, 2):
        raise PipelineBlocked(
            "isolated schematic-first source sync failed (exit %s): %s" %
            (process.returncode,
             (process.stderr or process.stdout or "no diagnostic")[-2000:]))
    if not report:
        raise PipelineBlocked(
            "isolated schematic-first source sync returned no report")
    report["process_exit"] = process.returncode
    return report


def _source_normalization_requested(*, replace_placement, fresh_placement_only,
                                    params, input_board, canonical_board,
                                    allow_derived_input=False):
    """Explicit fresh replacement consumes current hierarchy on every board.

    A current manifest PCB is a geometry seed, not schematic authority. The
    prior board-policy-only switch deadlocked ordinary boards immediately
    after a justified source ECO. Policy-driven canonical normalization must
    not redirect an explicit incremental derived input to an older staging
    PCB. Derived inputs still pass live hierarchy intake and require explicit
    replacement scope before any working-copy copper is regenerated.
    """
    # An explicit replacement may rebuild a hash-bound interface ECO while
    # retaining its latest placements. Requiring the canonical staging PCB
    # here discards already completed work; simply copying the ECO instead
    # would launder its invalidated copper. Only the normal copper-free sync
    # and subsequent live intake may clear that invalidation.
    if replace_placement and allow_derived_input:
        import cec_interface_eco
        try:
            record = cec_interface_eco.read_status(input_board)
        except ValueError as exc:
            raise PipelineBlocked(str(exc)) from exc
        if record and record.get('route_authority_invalidated'):
            return True
    requested = bool(replace_placement and (
        fresh_placement_only or params.get('schematic_first_normalization', False)))
    if requested and Path(input_board).resolve() != Path(canonical_board).resolve():
        if fresh_placement_only and allow_derived_input:
            # Both flags are explicit: this is a fresh copper-free rebuild of
            # the SELECTED input, not permission to redirect it to an older,
            # larger manifest seed. The normalizer uses the live hierarchy,
            # writes only its journal-owned copy and reruns strict intake.
            # Existing interface-ECO status was checked above even in fresh
            # mode, so a stale/pending certificate cannot bypass that guard.
            return True
        if not fresh_placement_only:
            # Do not normalize or strip this input here. The ordinary strict
            # source intake below must prove it current as supplied; a stale
            # schematic/interface ECO still fails. --allow-derived-input is
            # independently required by that gate.
            return False
        raise PipelineBlocked('schematic-first derived replacement requires explicit '
                              '--allow-derived-input with fresh placement scope')
    return requested


def _normalize_schematic_first_source(cfg, canonical_board, out_dir):
    """Create an electrically current, copper-free replacement input.

    This follows explicit fresh replacement or schematic-first board policy. It
    never edits the manifest PCB: the current hierarchy is synchronized into a
    journal-owned working copy, obsolete non-mechanical references are removed,
    and the ordinary intake gate must then prove the normalized copy.
    """
    canonical_board = Path(canonical_board).resolve()
    work_dir = Path(out_dir).resolve() / "00-source-normalized"
    work_board = work_dir / "board.kicad_pcb"
    import cec_interface_eco
    eco_record = cec_interface_eco.read_status(canonical_board)
    if eco_record and eco_record.get('route_authority_invalidated'):
        copied = _copy_sidecars(canonical_board, work_board, cfg=cfg, replacement_seed=True)
    else:
        copied = _copy_sidecars(canonical_board, work_board, cfg=cfg)
    first = _run_source_sync_process(cfg, work_board)
    retired = tuple(first.get("unexpected_board_refs") or ())
    final = first
    if retired:
        final = _run_source_sync_process(
            cfg, work_board, remove_refs=retired)
    ok = not (
        final.get("unexpected_board_refs")
        or final.get("missing_schematic_refs")
    )
    eco_rebuilt = None
    if eco_record and eco_record.get('route_authority_invalidated'):
        import pcbnew
        normalized = pcbnew.LoadBoard(str(work_board))
        copper_count = len(list(normalized.GetTracks())) + sum(
            not z.GetIsRuleArea() for z in normalized.Zones())
        if copper_count or not ok:
            raise PipelineBlocked('interface ECO normalization did not prove a copper-free current source')
        eco_rebuilt = {**eco_record, 'output': str(work_board),
                       'output_sha256': cec_interface_eco.sha(work_board),
                       'route_authority_invalidated': False,
                       'copper_free_replacement_seed': True,
                       'design_rule_hashes': {
                           suffix: cec_interface_eco.rule_digest(work_board.with_suffix(suffix))
                           for suffix in ('.kicad_pro', '.kicad_dru')
                           if work_board.with_suffix(suffix).exists()},
                       'admission_ok': False, 'release_authority': False}
        atomic_json(work_board.with_suffix('.interface-eco.json'), eco_rebuilt)
    report_path = work_dir / "source-normalization.json"
    report = {
        "schema": 1,
        "ok": ok,
        "mode": "schematic_first_working_copy",
        "canonical_board": str(Path(cfg.pcb).resolve()),
        "normalization_input": str(canonical_board),
        "derived_interface_rebuild": bool(
            eco_record and eco_record.get('route_authority_invalidated')
            and canonical_board != Path(cfg.pcb).resolve()),
        "board": str(work_board),
        "schematic": str(Path(cfg.sch).resolve()),
        "copper_disposition": "working_copy_ripped_for_replacement",
        "first_pass": first,
        "retired_refs": list(retired),
        "final": final,
        "interface_eco_copper_free_rebuild": eco_rebuilt,
    }
    atomic_json(report_path, report)
    return {
        "ok": ok,
        "board": str(work_board),
        "report": str(report_path),
        "retired_refs": list(retired),
        "added_refs": list(first.get("added_refs") or ()),
        "replaced_footprints": list(
            first.get("replaced_footprints") or ()),
        "_artifacts": copied + [str(report_path)],
    }


def _source_intake(cfg, input_board, report_path, *, allow_derived_input=False,
                   assembly_instance=None, suite_audit_cache=None):
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
    intake_context = {"sch": str(cfg.sch)}
    selected_assembly = None
    if assembly_instance is not None:
        import cec_assembly_instance
        # An explicit saved pair must reach the EARLY intake checker as well
        # as post-route review. Otherwise a good child board is compared to
        # an obsolete policy peer before its selected pair can be examined.
        # Resolve before calling the gate: invalid explicit context must not
        # fall back to a legacy peer or acquire a different member by name.
        selected_assembly = cec_assembly_instance.resolve(
            input_board, assembly_instance, ROOT)
        intake_context[cec_assembly_instance.CONTEXT_KEY] = copy.deepcopy(assembly_instance)
    # Selected source parts/pins must match declared current endpoints before
    # any routing/current consumer. This is source identity, not current-path
    # cleanliness, and is never deferred for derived input geometry.
    import pcbnew
    import cec_source_current_endpoint_intake
    try:
        endpoint_board = pcbnew.LoadBoard(str(input_board))
        declared_current_endpoints = cec_source_current_endpoint_intake.check(
            endpoint_board, board_key)
    except Exception as exc:
        declared_current_endpoints = {
            "ok": False, "reason": str(exc),
            "error_type": type(exc).__name__,
            "current_path_qualified": False,
            "physical_release": False,
        }
    intake = cec_constraints.intake_gate(
        str(input_board), intake_context,
        defer_route_geometry=route_geometry_deferred,
    )
    if suite_audit_cache is not None:
        from cec_suite_source_audit_cache import SuiteSourceAuditCache
        if (type(suite_audit_cache) is not SuiteSourceAuditCache
                or suite_audit_cache.root != ROOT.resolve()):
            raise ValueError('explicit same-root suite audit session required')
    def source_audit(mode, producer):
        return (producer() if suite_audit_cache is None else
                suite_audit_cache.get(mode, producer))
    generalization = source_audit('generalization',
        lambda: cec_generalization_gate.audit(ROOT))
    try:
        platform_electrical = source_audit('electrical-current-beta',
            lambda: cec_beta_electrical_audit.audit(str(ROOT / "beta")))
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
    if selected_assembly is not None and not all(
            cec_assembly_instance.digest(path) == selected_assembly["hashes"][key]
            for key, path in selected_assembly["paths"].items()):
        manifest_errors.append("explicit selected assembly changed during source intake")
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
        "assembly_instance": copy.deepcopy(assembly_instance),
        "selected_assembly_hashes": (selected_assembly["hashes"]
                                     if selected_assembly is not None else None),
        "project_rule_authority": project_rule_authority,
        "declared_current_endpoints": declared_current_endpoints,
        "intake": intake,
        "electrical_source_audit": electrical,
        "generalization_gate": generalization,
        "generic_release_ok": bool(generalization.get("release_ok")),
        "draft": cfg.is_draft,
        "ok": (not manifest_errors and bool(project_rule_authority.get("ok"))
               and bool(declared_current_endpoints.get("ok"))
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
    """Admit route-bound artifacts whose only defect is repairable local copper.

    The decoupler oracle intentionally checks both component geometry and the
    immediate routed supply/return cell.  On an unrouted placement both are
    placement-owned until the bounded placement repair is exhausted.  Once a
    placement enters this full pipeline, an assigned capacitor with legal
    geometry may fail solely because its mandatory dogbone/via is not yet
    synthesized; that must reach the pre-route repair stage whether the prefix
    came from a routed seed or from authored placement copper.  Missing,
    distant, or bad-return placement remains blocking.
    """
    import cec_synth_pipeline as synth
    return synth.placement_craft_admission(
        evidence, allow_route_access_repair=bool(routed_input))


def _placement_craft_failures(evidence):
    """Retain failed checker payloads without a stale term-name allowlist."""
    return {key:copy.deepcopy(value) for key,value in (evidence or {}).items()
            if (isinstance(value,dict) and value.get('ok') is False)
            or (key in ('error','errors') and value)}


def _measure_placement_physical_in_process(cfg, board_path):
    """Measure every non-routing placement gate from one board lifetime.

    This deliberately owns no mutation.  It is a file-level admission phase,
    so callers can run it in a fresh KiCad process after any preceding
    load/fill/save transaction without inheriting a stale SWIG object graph.
    """
    import cec_synth_pipeline as synth

    board_path = str(Path(board_path).resolve())
    pads = synth._oracle_pads_in_bounds(board_path)
    courtyards = synth._oracle_courtyard_overlaps(board_path)
    craft = synth.placement_craft_evidence(board_path, cfg=cfg)
    craft_gate = _placement_craft_gate(craft, routed_input=True)
    constraints = _placement_constraint_gate(Path(board_path), cfg)
    return {
        "schema": 1,
        "ok": bool(
            pads.get("ok") and courtyards.get("ok")
            and craft_gate.get("ok") and constraints.get("ok")),
        "pads_in_bounds": pads,
        "courtyards": courtyards,
        "craft": craft,
        "craft_gate": craft_gate,
        "constraint_gate": constraints,
    }


def _measure_placement_physical(cfg, board_path):
    """Run placement admission with a deterministic fresh-process default."""
    if not (cfg.params or {}).get(
            "placement_measure_process_isolation", False):
        return _measure_placement_physical_in_process(cfg, board_path)
    result = _run_priority_placement_operation_isolated(
        "placement-measure", cfg, board_path)
    result["process_isolated"] = True
    return result


def _placement_board_snapshot(board_path):
    """Return immutable poses/side/outline with a fresh-process fallback."""
    import pcbnew
    import cec_synth_pipeline as synth

    board_path = str(Path(board_path).resolve())
    try:
        board = pcbnew.LoadBoard(board_path)
        if board is None or not hasattr(board, "GetFootprints"):
            raise RuntimeError("pcbnew returned an invalid board proxy")
        footprints = list(board.GetFootprints())
        tracks = list(board.GetTracks())
        bounds = board.GetBoardEdgesBoundingBox()
        return {
            "schema": 1,
            "track_count": len(tracks),
            "placements": {
                str(fp.GetReference() or ""): [
                    fp.GetPosition().x / 1e6,
                    fp.GetPosition().y / 1e6,
                    float(fp.GetOrientationDegrees()),
                ]
                for fp in footprints if fp.GetReference()
            },
            "back_refs": sorted(
                str(fp.GetReference() or "") for fp in footprints
                if fp.GetReference() and fp.GetLayer() == pcbnew.B_Cu),
            "outline_mm": [
                bounds.GetWidth() / 1e6,
                bounds.GetHeight() / 1e6,
            ],
            "mode": "in_process",
        }
    except Exception as exc:                           # noqa: BLE001
        snapshot = synth._run_priority_power_artifact_phase_isolated(
            "placement-snapshot", board_path)
        snapshot["mode"] = "isolated_swig_recovery"
        snapshot["recovered_from"] = "%s: %s" % (
            type(exc).__name__, exc)
        return snapshot


def _declare_fabrication_profile_isolated(board_path, profile_name):
    """Validate/persist a board profile in one fresh KiCad process.

    Priority placement workers legitimately perform several independent
    load/fill/save transactions. KiCad 10's deprecated SWIG graph can leave
    the coordinator's next ``LoadBoard`` as a bare ``SwigPyObject`` even when
    the serialized board is healthy. Profile declaration is a file-level
    admission boundary, so it must not depend on that process-global lifetime.
    """
    import cec_power_artifact_worker

    with tempfile.TemporaryDirectory(
            prefix="cec-profile-declaration-") as work:
        report_path = Path(work) / "report.json"
        process = subprocess.run([
            sys.executable,
            cec_power_artifact_worker.__file__,
            "declare-profile", str(Path(board_path).resolve()),
            "--profile", str(profile_name),
            "--report", str(report_path),
        ], capture_output=True, text=True, timeout=1800)
        if process.stderr:
            print(process.stderr.rstrip(), file=sys.stderr)
        if process.returncode:
            raise RuntimeError(
                "isolated fabrication profile declaration exited %d: %s" % (
                    process.returncode,
                    (process.stderr or process.stdout or
                     "no diagnostic")[-4000:]))
        if not report_path.is_file():
            raise RuntimeError(
                "isolated fabrication profile declaration produced no report")
        result = json.loads(report_path.read_text(encoding="utf-8"))
        result["process_isolated"] = True
        return result


def _frozen_placement_contract(board_path, *, tolerance_mm=0.01):
    """Validate a complete pour-first placement beside ``board_path``.

    A complete frozen state is a placement authority, not merely a routing
    hint.  Generic clean-margin optimization must not move components after
    the power geometry was solved.  Explicit post-freeze repairs (fiducials,
    service connectors, and their electrically owned followers) update the
    sibling state transactionally and are checked again at stage admission.
    """
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

    snapshot = _placement_board_snapshot(board_path)
    actual_placements = dict(snapshot.get("placements") or {})
    mismatches = []
    for ref, expected in sorted(placements.items()):
        actual = actual_placements.get(str(ref))
        if (actual is None or not isinstance(expected, (list, tuple))
                or len(expected) != 3):
            mismatches.append({"ref": str(ref), "reason": "missing"})
            continue
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
            "mismatches": mismatches[:24],
            "placement_snapshot_mode": snapshot.get("mode")}


def _sync_safe_postfreeze_placement_delta(board_path, *, clearance_mm=0.3,
                                        dry_run=False, loaded_board=None,
                                        state_override=None):
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
        state = (state_override if state_override is not None else
                 json.loads(state_path.read_text(encoding="utf-8"))) or {}
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": 1, "ok": False, "updated": False,
                "reason": "state_unreadable",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    placements = state.get("placements")
    if (state.get("placement_scope") != "complete"
            or not isinstance(placements, dict)):
        return {"schema": 1, "ok": False, "updated": False,
                "reason": "not_complete_placement_authority"}

    board = loaded_board if loaded_board is not None else pcbnew.LoadBoard(str(board_path))
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

    import cec_power_guard_geometry
    avoid = cec_power_guard_geometry.placement_reservations(state)
    token_nets = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            token = '%s-%s' % (footprint.GetReference(), pad.GetPadName())
            token_nets.setdefault(token, set()).add(str(pad.GetNetname()))
    owned_terminals = cec_power_guard_geometry.frozen_terminal_tokens(state, token_nets)
    clearance = max(0.0, float(clearance_mm))
    refused = []
    consumers = []
    for ref, footprint, actual in changed:
        pad_nets = {str(pad.GetNetname()) for pad in footprint.Pads()
                    if str(pad.GetNetname())}
        owned = sorted(pad_nets & frozen_nets)
        pad_tokens = {'%s-%s' % (ref, pad.GetPadName()) for pad in footprint.Pads()}
        if owned and (owned_terminals is None or pad_tokens & owned_terminals):
            refused.append({"ref": ref, "reason": "owns_frozen_net",
                            "nets": owned})
            continue
        x0, x1, y0, y1 = synth._footprint_courtyard_box(footprint)
        if owned:
            # Prove actual pad separation on the actual copper layers. An
            # insulated body above an inner bus is not an electrical tap.
            # All ordinary craft/mechanical gates still apply independently.
            proposed_hits = cec_power_guard_geometry.frozen_pad_contacts(
                board, footprint, state, clearance)
            expected = placements[ref]
            try:
                footprint.SetPosition(pcbnew.VECTOR2I_MM(expected[0], expected[1]))
                footprint.SetOrientationDegrees(expected[2])
                original_hits = cec_power_guard_geometry.frozen_pad_contacts(
                    board, footprint, state, clearance)
            finally:
                footprint.SetPosition(pcbnew.VECTOR2I_MM(actual[0], actual[1]))
                footprint.SetOrientationDegrees(actual[2])
            if original_hits or proposed_hits:
                refused.append({'ref': ref, 'reason': 'consumer_pad_touches_frozen_power',
                    'nets': owned, 'original_contacts': original_hits,
                    'proposed_contacts': proposed_hits})
                continue
            consumers.append({'ref': ref, 'nets': owned,
                'proof': 'declared_unowned_pin_and_both_pad_geometries_clear_frozen_copper'})
            continue
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

    if dry_run:
        return {"schema": 1, "ok": True, "updated": False,
                "reason": "power_independent_delta_proved", "dry_run": True,
                "deferred_consumers": consumers,
                "refs": [ref for ref, _footprint, _actual in changed]}
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
            "deferred_consumers": consumers,
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
    snapshot = _placement_board_snapshot(board)
    return (int(snapshot.get("track_count", 0) or 0) == 0
            or bool(_placement_stage_artifact_provenance(board)))


def _transactional_fiducial_edge_repair_in_process(
        cfg, board, *, reconsider_all=False):
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
            str(board), reconsider_all=bool(reconsider_all),
            allow_existing_copper=bool(reconsider_all))
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


def _transactional_fiducial_edge_repair(
        cfg, board, *, reconsider_all=False, reuse=None):
    """Run the complete craft-guarded fiducial transaction in isolation."""
    if not (getattr(cfg, "params", None) or {}).get(
            "fiducial_process_isolation", False):
        return _transactional_fiducial_edge_repair_in_process(
            cfg, board, reconsider_all=reconsider_all)
    def isolated_repair():
        result = _run_priority_placement_operation_isolated(
            "fiducial-repair", cfg, board,
            reconsider_all=reconsider_all)
        result["process_isolated"] = True
        return result

    if reuse is not None:
        return reuse.run(cfg, board, isolated_repair,
                         reconsider_all=reconsider_all)
    return isolated_repair()


def _placement_search_history(board, scope):
    """Read byte-bound ordering only; stale/malformed hints grant no authority."""
    import cec_placement_probe_coverage as coverage
    board = Path(board)
    if not board.is_file():
        # This optional diagnostic must not replace the native loader's
        # failure reporting or create history for an unavailable artifact.
        return {}, {'schema': 1, 'input_sha256': None, 'scopes': {}}, {
            'reason': 'board_unavailable', 'prior_poses': 0, 'cached_admission': False}
    source_hash = sha256_file(board)
    path = board.with_suffix('.placement-search.json')
    state = {'schema': 1, 'input_sha256': source_hash, 'scopes': {}}
    reason = 'missing'
    try:
        saved = json.loads(path.read_text())
        if (saved.get('schema') != 1 or saved.get('input_sha256') != source_hash
                or not isinstance(saved.get('scopes'), dict)):
            reason = 'stale_or_invalid'
        else:
            # Validate both finite histories before retaining either one.
            for key, data in saved['scopes'].items():
                if key not in ('priority', 'craft'):
                    raise ValueError('unknown placement search scope')
                coverage.import_visits(data)
            state = saved
            reason = 'matched'
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, AttributeError):
        reason = 'unreadable_or_invalid'
    data = state['scopes'].get(scope)
    visits = coverage.import_visits(data) if data is not None else {}
    return visits, state, {'reason': reason, 'prior_poses': len(visits),
                           'cached_admission': False}


def _save_placement_search_history(board, scope, state, report):
    """Keep small work-accounting receipts separate from PCB commit/rollback."""
    import cec_placement_probe_coverage as coverage
    history = report.get('probe_history')
    if history is None or not state.get('input_sha256'):
        return
    coverage.import_visits(history)
    state['scopes'][scope] = history
    # Deliberately retain the PRE-repair hash. If geometry changed these hints
    # are stale; changed surroundings must receive a fresh search.
    path = Path(board).with_suffix('.placement-search.json')
    try:
        atomic_json(path, state)
    except OSError as exc:
        report['search_history_write_error'] = str(exc)


def _repair_craft_with_search_history(cfg, candidate, board, **kwargs):
    import cec_synth_pipeline as synth
    coverage = getattr(candidate, 'rehydration_copper_coverage', None)
    use_noncontact = bool(coverage and not coverage.get('ok') and
                          (getattr(cfg, 'params', {}) or {}).get('placement_noncontact_resume', True))
    if use_noncontact:
        # Craft repair need not reconstruct or acquire unrelated routed
        # copper. A narrower source-bound materializer permits only detached
        # SMD pose deltas and proves the rest of the native board unchanged.
        # Attached terminals and zone-coupled placements still refuse.
        import cec_noncontact_placement
        candidate = copy.copy(candidate)
        candidate.noncontact_placement_contract = cec_noncontact_placement.bind(
            board, candidate, immutable_refs=synth._declared_blueprint_refs(cfg), retain_reports=True)
    visits, state, receipt = _placement_search_history(board, 'craft')
    candidate, report = synth.repair_placement_craft_epochs(
        cfg, candidate, probe_visits=visits, **kwargs)
    report['search_history_resume'] = receipt
    if use_noncontact:
        report['materialization_scope'] = 'noncontact_smd_delta_without_copper_ownership'
        report['original_copper_coverage'] = coverage
    _save_placement_search_history(board, 'craft', state, report)
    return candidate, report


def _commit_craft_reconstruction(cfg, candidate, board, repair):
    """Commit the complete craft delta, including incidental rebuilt copper.

    Search's incoming and rebuilt reports are hints. Re-measure the real
    incumbent and rebuilt artifact, preserve the whole authority family on
    refusal, and keep ordinary routing/release admission separate.
    """
    pose_proposal = bool(repair.get('changed'))
    if not pose_proposal and not (repair.get('reconstruction_proposal') or {}).get('requested'):
        return repair
    import cec_synth_pipeline as synth
    import cec_placement_reconstruction as reconstruction
    import cec_placement_route_prefix
    import cec_fab_repair
    import cec_constraints
    result = copy.deepcopy(repair)
    board = Path(board).resolve()
    before = synth.placement_craft_evidence(str(board), cfg=cfg)
    # Until the commit below succeeds, every top-level result describes the
    # retained incumbent, not the discarded temporary reconstruction.
    result.update(result_key=list(synth.placement_craft_repair_key(before)),
        ok=bool(before.get('ok')), result_scope='retained_incumbent',
        blocker_certificate=synth.placement_craft_blocker_certificate(before))
    fixed_before = reconstruction.fixed_domain(board, include_poses=not pose_proposal)
    candidate = copy.copy(candidate)
    candidate.protected_power_prefix = cec_placement_route_prefix.capture(board)
    frozen = _frozen_placement_contract(board)
    if frozen.get('applicable') and not frozen.get('ok'):
        result['reconstruction_commit'] = dict(accepted=False, reason='invalid_frozen_authority')
        result.update(changed=False, accepted_count=0, proposal_only=True)
        return result
    before_score = cec_fab_repair._score_isolated(str(board))
    before_score.update(cec_fab_repair._foreign_isolated(str(board)))
    with tempfile.TemporaryDirectory(prefix='cec-craft-reconstruction-') as work:
        _snapshot_placement_authority(board, work)
        try:
            state = board.with_suffix('.pourfirst-state.json')
            old_state = state.read_bytes() if state.is_file() else None
            bundle = getattr(candidate, 'reconstruction_artifact', None)
            if bundle is not None and not pose_proposal:
                import cec_materialized_candidate
                result['reconstruction_artifact'] = cec_materialized_candidate.install(
                    bundle, board, candidate, cfg)
            else:
                synth.materialize(candidate, cfg, str(board))
            prefix = synth._admit_materialized_power_prefix(candidate, str(board))
            state_unchanged = (state.read_bytes() if state.is_file() else None) == old_state
            frozen_ok = state_unchanged and (not frozen.get('applicable') or
                bool(_sync_safe_postfreeze_placement_delta(board).get('ok')))
            after = synth.placement_craft_evidence(str(board), cfg=cfg)
            after_score = cec_fab_repair._score_isolated(str(board))
            after_score.update(cec_fab_repair._foreign_isolated(str(board)))
            intake = cec_constraints.intake_gate(
                str(board), {'sch': str(cfg.sch)}, defer_route_geometry=True)
            admission = reconstruction.admit(before, after,
                before_score=before_score, after_score=after_score,
                fixed_domain_unchanged=(fixed_before == reconstruction.fixed_domain(
                    board, include_poses=not pose_proposal) and (not pose_proposal or
                    _placement_position_signature(board) == _candidate_position_signature(candidate))),
                prefix_ok=bool(prefix.get('ok')), source_ok=bool(intake.get('ok')),
                frozen_ok=frozen_ok, require_blocking_progress=not pose_proposal)
            result['reconstruction_commit'] = dict(admission, prefix=prefix, source_intake=intake)
            if not admission['accepted']:
                _restore_placement_authority(board, work)
                result.update(changed=False, reconstruction_rolled_back=True,
                    proposed_accepted_count=result.get('accepted_count', 0),
                    accepted_count=0, proposal_only=True)
            else:
                result.update(changed=True, reconstruction_changed=not pose_proposal,
                    result_scope='committed_native_reconstruction',
                    result_key=list(synth.placement_craft_repair_key(after)),
                    ok=bool(after.get('ok')),
                    blocker_certificate=synth.placement_craft_blocker_certificate(after))
        except Exception:
            _restore_placement_authority(board, work)
            raise
    return result


def _bounded_post_fiducial_craft_repair(
        cfg, board, fiducial_repair, *, max_trials, rounds, epochs,
        allow_authored_prefix=False):
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
    if (any(True for _item in loaded.GetTracks())
            and not allow_authored_prefix):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False,
                "reason": "routed_board_preserved"}

    before = synth.placement_craft_evidence(str(board), cfg=cfg)
    if before.get("ok"):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": True, "reason": "post_fiducial_craft_clean",
                "before_key": list(synth.placement_craft_key(before))}

    signature_before = _placement_position_signature(board)
    candidate = synth.placement_candidate_from_board(
        cfg, str(board), allow_routed=allow_authored_prefix)
    candidate, repair = _repair_craft_with_search_history(
        cfg, candidate, board, max_trials=int(max_trials), rounds=int(rounds),
        epochs=int(epochs), initial_evidence=before)
    repair = _commit_craft_reconstruction(cfg, candidate, board, repair)
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


def _commit_frozen_placement_repair(cfg, candidate, board, repair):
    """Commit any placement proposal with its unchanged frozen-power contract.

    Improving a local craft key does not authorize moving a frozen terminal.
    A refused state synchronization must restore the whole artifact family,
    not leave an improved-looking board with a stale placement authority.
    """
    import cec_synth_pipeline as synth
    if not repair.get('changed'):
        return repair
    result = dict(repair)
    with tempfile.TemporaryDirectory(prefix='cec-frozen-craft-commit-') as scratch:
        _snapshot_placement_authority(board, scratch)
        try:
            state_path = Path(board).with_suffix('.pourfirst-state.json')
            state_before = state_path.read_bytes()
            synth.materialize(candidate, cfg, str(board))
            # A signal/craft move cannot replace its plan with another valid
            # plan. Only the proved placement snapshot may be synchronized.
            sync = (_sync_safe_postfreeze_placement_delta(board)
                    if state_path.is_file() and state_path.read_bytes() == state_before
                    else {'ok': False, 'updated': False,
                          'reason': 'frozen_plan_changed_during_materialize'})
            result['postfreeze_state_sync'] = sync
            if not sync.get('ok'):
                _restore_placement_authority(board, scratch)
                result.update(changed=False, rolled_back=True,
                    accepted=False,
                    reason='frozen_power_dependency_refused',
                    proposed_accepted_count=result.get('accepted_count', 0),
                    accepted_count=0, proposal_only=True, ok=False)
        except Exception:
            _restore_placement_authority(board, scratch)
            raise
    return result


def _commit_frozen_craft_repair(cfg, candidate, board, repair):
    """Compatibility entry point; craft and priority repair share one commit."""
    return _commit_frozen_placement_repair(cfg, candidate, board, repair)


def _placement_authority_physical_boundary(before, ensure_authority, measure_physical):
    """A rebuilt authority invalidates earlier physical placement evidence.

    The PCB bytes can be identical while its frozen reservations change.
    Qualify the complete new composition before priority ranking or snapshots;
    callers retain ownership of rollback and bounded alternate proposals.
    """
    if not before[-1]:
        authority = {"schema": 1, "ok": False, "applicable": True,
                     "reason": "route_repair_not_admitted", "_artifacts": []}
        return authority, before, {"schema": 1, "measured_after_authority": False,
                                  "reason": "physical_precondition_refused"}
    authority = ensure_authority()
    after = measure_physical() if authority.get("ok") else before
    certificate = {
        "schema": 1, "measured_after_authority": bool(authority.get("ok")),
        "physical_before_ok": bool(before[-1]),
        "physical_after_ok": bool(after[-1]) if authority.get("ok") else None,
        "craft_gate": dict(after[4]), "constraint_gate": dict(after[5]),
        "pads_ok": bool(after[0].get("ok")),
        "courtyards_ok": bool(after[1].get("ok")),
        "release_authority": False,
    }
    return authority, after, certificate


def _post_authority_craft_dependencies(craft):
    """Typed placement failures that a fresh frozen power solve can expose."""
    import cec_local_return_feedback
    craft = craft or {}
    dependencies = []
    if (craft.get('power_body_clearance') or {}).get('ok') is False:
        dependencies.append('power_body_clearance')
    if any(cec_local_return_feedback.failed_searches(row)
           for row in ((craft.get('decoupler') or {}).get('details') or ())):
        dependencies.append('ground_return_access')
    return dependencies


def _joint_power_placement_admission(before, after):
    """Judge the composed placement AND rebuilt-power result, not either half."""
    import cec_synth_pipeline as synth
    a,b=before['physical'],after['physical']
    before_key=tuple(synth.placement_craft_blocking_key(a[2]))
    after_key=tuple(synth.placement_craft_blocking_key(b[2]))
    old_nets=set((before['authority'].get('planner') or {}).get('frozen_nets') or ())
    new_nets=set((after['authority'].get('planner') or {}).get('frozen_nets') or ())
    terms=dict(physical_core=bool(b[0].get('ok') and b[1].get('ok') and b[5].get('ok')
                and after['fiducial'].get('ok') and after['service'].get('ok')),
        exact_power=bool(after['authority'].get('ok')),
        protected_domains_retained=old_nets<=new_nets,
        craft_not_worse=after_key<=before_key,
        progress=bool(b[6]) or after_key<before_key)
    return dict(schema=1,accepted=all(terms.values()),terms=terms,
                before_key=list(before_key),after_key=list(after_key),
                lost_domains=sorted(old_nets-new_nets))


def _transactional_power_placement_trial(cfg, board, before, propose, rebuild):
    """Rollback the whole artifact family and bindings on regression/exception."""
    params,pins=copy.deepcopy(cfg.params),copy.deepcopy(cfg.pins)
    accepted=False;proposal={}
    with tempfile.TemporaryDirectory(prefix='cec-joint-power-placement-') as work:
        _snapshot_placement_authority(board,work)
        try:
            proposal=dict(propose())
            if not proposal.get('changed'):
                return proposal,before
            after=rebuild()
            admission=_joint_power_placement_admission(before,after)
            accepted=admission['accepted']
            proposal.update(joint_admission=admission,changed=accepted,
                rolled_back=not accepted,
                reason=proposal.get('reason') if accepted else 'joint_power_placement_regression')
            return proposal,after if accepted else before
        except Exception as exc:
            return dict(proposal,ok=False,changed=False,rolled_back=True,
                        reason='joint_power_placement_exception',
                        error='%s: %s'%(type(exc).__name__,exc)),before
        finally:
            if not accepted:
                _restore_placement_authority(board,work)
                cfg.params,cfg.pins=params,pins


def _bounded_post_authority_craft_repair(
        cfg, board, craft, *, max_trials, rounds, epochs,
        allow_authored_prefix=False):
    """Legalize placement once against newly frozen power territory.

    Some craft rules (notably the no-foreign-body-in-pour contract) cannot be
    evaluated until exact current corridors exist.  Run the ordinary generic
    placement repair once at that dependency boundary.  The caller must then
    rebuild and re-admit the power authority for the accepted coordinates;
    this helper never loops power and placement internally.
    """
    import cec_synth_pipeline as synth

    craft = dict(craft or {})
    if craft.get("ok"):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": True,
                "reason": "post_authority_craft_clean"}
    power_body = craft.get("power_body_clearance") or {}
    dependencies = _post_authority_craft_dependencies(craft)
    if not dependencies:
        return {"schema": 1, "ok": False, "changed": False,
                "applicable": False,
                "reason": "non_authority_craft_failure"}

    signature_before = _placement_position_signature(board)
    candidate = synth.placement_candidate_from_board(
        cfg, str(board), allow_routed=allow_authored_prefix)
    candidate, repair = _repair_craft_with_search_history(
        cfg, candidate, board, max_trials=int(max_trials), rounds=int(rounds),
        epochs=int(epochs), initial_evidence=craft)
    if repair.get("changed"):
        synth.materialize(candidate, cfg, str(board))
    signature_after = _placement_position_signature(board)
    result = dict(repair)
    result.update({
        "schema": 1,
        "applicable": True,
        "one_shot": True,
        "authority_dependency": "frozen_power_territory",
        "dependency_kinds": dependencies,
        "placement_signature_before": signature_before,
        "placement_signature_after": signature_after,
        "repeated_placement": signature_after == signature_before,
        "input_power_body_violations": list(
            power_body.get("violations") or ())[:24],
        "input_power_planner_failures": dict(
            power_body.get("planner_failures") or {}),
    })
    return result


def _finalize_fiducials_after_route_authority(
        cfg, board, *, priority_applicable=False,
        allow_authored_prefix=False, fiducial_reuse=None):
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
            cfg, board, reconsider_all=True, reuse=fiducial_reuse)
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

        authority = _ensure_placement_route_authority(
            cfg, board, allow_authored_prefix=allow_authored_prefix)
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
                cfg, board,
                allow_authored_prefix=allow_authored_prefix)
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


def _budgeted_late_fiducial_finalization(cfg, board, **kwargs):
    """An optional last reseat cannot consume final checks or strand a move."""
    import cec_operation_budget
    import cec_synth_pipeline as synth
    with tempfile.TemporaryDirectory(prefix='cec-late-finalization-') as work:
        _snapshot_placement_authority(board, work)
        try:
            with cec_operation_budget.finalization_reserve(float(cfg.params.get(
                    'placement_fiducial_finish_reserve_s', 60.))) as lease:
                result = _finalize_fiducials_after_route_authority(cfg, board, **kwargs)
            if lease['budget_exhausted']:
                _restore_placement_authority(board, work)
                bound, binding = synth.config_with_board_route_authority(cfg, str(board))
                if binding.get('ok') and binding.get('bound'):
                    cfg.params = dict(bound.params)
                result = dict(schema=1, ok=bool(binding.get('ok')), changed=False,
                    accepted=False, rolled_back=True, applicable=True,
                    reason='late_fiducial_budget_reserved', authority_binding=binding)
            return dict(result, finalization_budget=lease)
        except Exception:
            _restore_placement_authority(board, work)
            raise


def _initial_resume_craft_policy(evidence, params, *, resumed):
    """Use the same deferred-repair contract at resume and final admission."""
    gate = _placement_craft_gate(evidence,routed_input=True) if resumed else None
    return {'needs_repair':not (gate['ok'] if gate is not None else evidence.get('ok')),
            'optimize_clean_margin':bool(params.get(
                'placement_resume_optimize_clean_margin' if resumed else
                'placement_craft_optimize_clean_margin', not resumed)),
            'admission':gate}


def _placement_priority_probe_required(cfg, board, *, preserved_routed=False):
    """Critical-route admission is not an optional placement-ranking feature.

    A zero reranking budget does not mean the board has no differential pairs.
    Use the production router's own discovery when policy has no explicit
    selectors; discovery errors propagate rather than silently skip a gate.
    Already routed inputs retain their read-only stage semantics.
    """
    if preserved_routed:
        return False
    if (cfg.params.get("critical_route_nets")
            or int(cfg.params.get("placement_route_preflight_topk", 0) or 0) > 0):
        return True
    import cec_precision_route
    return bool(cec_precision_route.derive_coupled_pairs(str(board)))


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
    if not evidence:
        return {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "placement_route_evidence_missing",
            "blockers": [{"term": "analysis", "count": 1,
                          "detail": "priority-route evidence was not run"}],
        }
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


def _recover_placement_priority_routes(cfg, board):
    """Exercise critical-only detailed routing before another placement ECO."""
    import cec_priority_recovery
    import cec_operation_budget
    directory = Path(tempfile.mkdtemp(prefix='priority-recovery-',
                                      dir=Path(board).resolve().parent))
    params = directory/'params.json'
    atomic_json(params, dict(cfg.params or {}))
    waves = min(8, max(1, int(cfg.params.get('priority_recovery_waves', 2))))
    route_timeout = max(1, int(cfg.params.get('priority_recovery_route_timeout_s', 300)))
    command = [sys.executable, cec_priority_recovery.__file__,
        '--board', str(cfg.board), '--input', str(Path(board).resolve()),
        '--out', str(directory), '--waves', str(waves),
        '--timeout', str(route_timeout), '--params-file', str(params)]
    print('[priority-recovery] critical-only wave logs: %s' % (directory/'worker.log'),flush=True)
    # Recovery precedes the placement co-optimizer, but it must share that
    # coordinator's final validation reserve. Reserving only inside co-opt
    # is too late if this optional search has already consumed the lease.
    # The worker writes private candidates; only a completed admitted result
    # below may touch the parent. Never read/commit an interrupted receipt.
    with cec_operation_budget.finalization_reserve(float(cfg.params.get(
            'placement_coopt_finish_reserve_s', 120.))) as finalization_budget:
        operation_evidence = cec_operation_budget.run(
            command, directory, operation='priority-recovery',
            timeout=float(cfg.params.get('priority_recovery_process_timeout_s', 900)),
            # 2 means a completed, honestly rejected search, not a worker crash.
            accepted_exit_codes=(0, 2))
    if finalization_budget['budget_exhausted']:
        return {'ok': False, 'changed': False,
                'reason': 'priority_recovery_finalization_budget_reserved',
                'finalization_budget': finalization_budget,
                'operation_evidence': finalization_budget['operation_failure'],
                'log': str(directory/'worker.log')}
    report_path = directory/'recovery.json'
    if not report_path.is_file():
        return {'ok':False,'changed':False,'reason':'priority_recovery_worker_failed',
                'exit_code':operation_evidence['exit_code'],
                'operation_evidence':operation_evidence,'log':str(directory/'worker.log')}
    report = json.loads(report_path.read_text())
    report['report'] = str(report_path)
    report['changed'] = False
    report['operation_evidence'] = operation_evidence
    report['finalization_budget'] = finalization_budget
    if operation_evidence['exit_code'] == 0 and report.get('ok') and report.get('selected'):
        _copy_sidecars(report['selected'], board, cfg)
        report['changed'] = True
    elif (operation_evidence['exit_code'] == 2
          and report.get('source_inputs_unchanged') and report.get('engine_unchanged')
          and report.get('source_unchanged') and report.get('partial_selected')
          and (report.get('partial_proof') or {}).get('ok')):
        candidate = Path(report['partial_selected'])
        proof = report['partial_proof']
        from cec_board_suite import signature_unchanged
        if (candidate.is_file() and sha256_file(candidate) == proof.get('board_sha256')
                and proof.get('artifact_signature')
                and signature_unchanged(proof['artifact_signature'])
                and sha256_file(board) == report.get('source_sha256')):
            _copy_sidecars(candidate, board, cfg)
            report.update(changed=True, partial_retained=True)
    return report


def _preserve_admitted_priority_placement(cfg, gate):
    """Return whether an already admitted placement is a stable boundary."""
    return bool(
        (gate or {}).get("ok")
        and not cfg.params.get("placement_optimize_feasible_routes", False))


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
            "pair_probe_budget": dict(round_report.get("pair_probe_budget") or {}),
            "pair_probe_schedule": dict(round_report.get("pair_probe_schedule") or {}),
            "pair_probe_deferred": list(round_report.get("pair_probe_deferred") or ()),
            "probe_coverage": dict(round_report.get("probe_coverage") or {}),
            "proposal_frontier": dict(round_report.get("proposal_frontier") or {}),
            "full_evaluated": int(
                round_report.get("full_evaluated", 0) or 0),
            "accepted": bool(round_report.get("accepted")),
            "move_space": dict(round_report.get("move_space") or {}),
            "externally_excluded_move_count": int(
                round_report.get(
                    "externally_excluded_move_count", 0) or 0),
            "zero_refusal_candidates": zero_refusal,
            "stale_power_handoffs": list(
                round_report.get("finalist_stale_power_handoff") or ()),
            "best_finalist_comparison": round_report.get("best_finalist_comparison"),
            "finalist_artifacts": [dict(move_index=row.get('move_index'),
                candidate=row.get('candidate'), artifact=row.get('artifact'))
                for row in round_report.get('finalist_comparisons') or ()],
            "craft_rejected": craft_rejected,
            "macro_legalization_rejected_count": len(
                round_report.get("macro_legalization_rejected") or ()),
            "power_replan_candidate_count": len(
                round_report.get("power_replan_candidates") or ()),
            "priority_dependency_candidate_count": len(
                round_report.get("priority_dependency_candidates") or ()),
            "timing_s": dict(round_report.get("timing_s") or {}),
        })
    return summaries


def _run_priority_placement_operation_isolated(
        operation, cfg, board, *, completion_report=None, baseline_evidence=None,
        allow_authored_prefix=False,
        allow_unbound_power_authority=False, reconsider_all=False):
    """Run one priority placement operation in a clean KiCad process."""
    import cec_power_artifact_worker

    from contextlib import nullcontext
    import cec_operation_budget
    import cec_route_evidence
    # Keep bounded causal evidence beside the run, not in a deleted /tmp
    # directory or a capture_output buffer invisible until worker completion.
    with nullcontext(tempfile.mkdtemp(
            prefix="operation-" + operation + "-",
            dir=Path(board).resolve().parent)) as work:
        work = Path(work)
        original_board = Path(board).resolve()
        original_hash = sha256_file(original_board)
        mutating_operation = operation in ('priority-repair', 'power-terminal-repair',
                                          'priority-power-replan')
        original_family = {str(path): sha256_file(path)
                           for path in _placement_authority_family(original_board)
                           if path.is_file()} if mutating_operation else None
        baseline_options = dict(allow_authored_prefix=allow_authored_prefix,
            allow_unbound_power_authority=allow_unbound_power_authority)
        original_context = (cec_route_evidence.baseline_context(
            cfg, original_board, **baseline_options)
            if operation == 'priority-repair' and baseline_evidence else None)
        transfer = cec_route_evidence.verify(baseline_evidence, original_context)
        worker_board = original_board
        if mutating_operation:
            worker_board = work/'candidate'/original_board.name
            _copy_sidecars(original_board, worker_board)
            for suffix in ('.authored-prefix.json', '.power-prefix.json'):
                source = original_board.with_suffix(suffix)
                if source.exists():
                    shutil.copy2(source, worker_board.with_suffix(suffix))
        params_path = work / "params.json"
        config_path = work / "config.json"
        completion_path = work / "completion.json"
        report_path = work / "report.json"
        atomic_json(params_path, dict(cfg.params or {}))
        # Preserve explicit source selection (especially net=None), profile,
        # and pins across worker isolation, not only the params dictionary.
        atomic_json(config_path, {key:getattr(cfg,key) for key in
            ('board_key','profile','pins','dir','sch','net','pcb','bom_csv')
            if hasattr(cfg,key)})
        command = [
            sys.executable,
            cec_power_artifact_worker.__file__,
            str(operation), str(worker_board),
            "--board-name", str(cfg.board),
            "--params-file", str(params_path),
            "--config-file", str(config_path),
            "--report", str(report_path),
        ]
        if completion_report is not None:
            atomic_json(completion_path, completion_report)
            command.extend(["--completion-file", str(completion_path)])
        if operation == 'priority-repair' and baseline_evidence:
            transported = baseline_evidence
            if transfer['used']:
                # The coordinator owns this exact copy/sidecar-rebinding
                # boundary. Only a still-matching source proof may be rebound
                # to the private copy; the child verifies that receipt again.
                if cec_route_evidence.baseline_context(
                        cfg, original_board, **baseline_options) != original_context:
                    raise RuntimeError('priority baseline source changed during staging')
                transported = cec_route_evidence.seal(baseline_evidence,
                    cec_route_evidence.baseline_context(cfg, worker_board, **baseline_options))
            baseline_path = work/'baseline.json'
            atomic_json(baseline_path, transported)
            command.extend(['--baseline-file', str(baseline_path)])
        if allow_authored_prefix:
            command.append("--allow-authored-prefix")
        if allow_unbound_power_authority:
            command.append("--allow-unbound-power-authority")
        if reconsider_all:
            command.append("--reconsider-all")
        timeout = float(cfg.params.get(
            'priority_repair_operation_timeout_s' if operation=='priority-repair'
            else 'priority_operation_timeout_s',
            600 if operation in ('priority-measure', 'priority-repair') else 1800))
        if operation == 'power-terminal-repair':
            import cec_priority_dependency
            allocation = cec_priority_dependency.operation_budget(cfg.params)
            timeout = allocation['requested_s']
            atomic_json(work/'budget-plan.json', allocation)
        if operation == 'priority-power-replan':
            timeout = float(cfg.params.get('priority_power_replan_timeout_s',
                cfg.params.get('priority_repair_operation_timeout_s', 1200)))
        print('[operation] %s: budget %.1fs; evidence %s' %
              (operation, timeout, work), flush=True)
        operation_evidence = cec_operation_budget.run(
            command, work, operation=operation, timeout=timeout)
        if not report_path.is_file():
            raise RuntimeError(
                "isolated %s produced no report" % operation)
        result = json.loads(report_path.read_text(encoding="utf-8"))
        if mutating_operation:
            current_family = {str(path): sha256_file(path)
                              for path in _placement_authority_family(original_board)
                              if path.is_file()}
            if sha256_file(original_board) != original_hash or current_family != original_family:
                raise RuntimeError('priority repair input family changed while isolated worker ran')
        if (operation == 'priority-repair' and original_context is not None
                and cec_route_evidence.baseline_context(
                    cfg, original_board, **baseline_options) != original_context):
            raise RuntimeError('priority repair dependencies changed while isolated worker ran')
        if mutating_operation and result.get('ok') and result.get('changed'):
            _copy_sidecars(worker_board, original_board)
        result['operation_evidence'] = operation_evidence
        if operation == 'priority-power-replan':
            result.setdefault('power_replan', {})['operation_evidence'] = dict(
                operation_evidence, report=str(report_path))
        if operation == 'priority-repair':
            result['baseline_transfer'] = transfer
        return result


def _repair_placement_priority_routes_in_process(
        cfg, board, *, completion_report=None, baseline_evidence=None,
        allow_authored_prefix=False,
        allow_unbound_power_authority=False):
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
    import cec_route_evidence

    board = Path(board).resolve()
    loaded = pcbnew.LoadBoard(str(board))
    if loaded is None:
        return {"schema": 1, "ok": False, "changed": False,
                "reason": "placement_board_unreadable"}
    if (any(True for _item in loaded.GetTracks())
            and not allow_authored_prefix):
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False, "reason": "routed_board_preserved"}
    trials = int(cfg.params.get("placement_route_repair_trials", 0) or 0)
    rounds = int(cfg.params.get("placement_route_repair_rounds", 0) or 0)
    if trials <= 0 or rounds <= 0:
        return {"schema": 1, "ok": True, "changed": False,
                "applicable": False, "reason": "policy_disabled"}

    bound, authority = synth.config_with_board_route_authority(
        cfg, str(board))
    # Search-only policy must not leak into the caller's electrical recipe.
    bound = copy.copy(bound)
    bound.params = dict(bound.params or {})
    requires_power_authority = _requires_frozen_route_authority(cfg)
    authority_bound = bool(
        not allow_unbound_power_authority
        and authority.get("ok")
        and (not requires_power_authority or authority.get("bound")))
    if allow_unbound_power_authority:
        # A sibling state may be structurally complete yet have just failed
        # exact filled-copper admission.  Do not let that rejected geometry
        # masquerade as route authority during recovery.  The placement
        # preflight environment derives conservative future-power
        # reservations from board policy instead.
        bound = copy.copy(cfg)
        bound.params = dict(cfg.params or {})
        for key in ("pourfirst_state", "pourfirst_outline_mm",
                    "pourfirst_seen_placements", "pourfirst_avoid_boxes"):
            bound.params.pop(key, None)
    if not authority_bound and not allow_unbound_power_authority:
        return {
            "schema": 1, "ok": False, "changed": False,
            "applicable": True,
            "reason": "exact_route_authority_not_bound",
            "route_authority": authority,
        }
    import cec_placement_route_prefix
    noncontact_scope = None
    try:
        candidate = synth.placement_candidate_from_board(
            bound, str(board), allow_routed=allow_authored_prefix)
        coverage = getattr(candidate, 'rehydration_copper_coverage', None)
        if coverage and not coverage['ok']:
            if not (allow_authored_prefix and cfg.params.get('placement_priority_noncontact_resume',True)):
                raise cec_placement_route_prefix.UnownedRoutedCopper(coverage)
            # Ordinary sense/signal copper is not a destructive rehydration
            # domain. Reuse the exact native remainder-preserving materializer
            # instead, restricted to source-bound detached SMD pose deltas.
            # Attached packages still need an explicitly owned transaction.
            import cec_noncontact_placement
            candidate = copy.copy(candidate)
            candidate.noncontact_placement_contract = cec_noncontact_placement.bind(
                board,candidate,immutable_refs=synth._declared_blueprint_refs(bound),
                retain_reports=True,freeze_native_dependencies=True)
            domain=candidate.noncontact_placement_contract['native_domain']
            bound.params['placement_immutable_refs']=sorted(
                set(bound.params.get('placement_immutable_refs') or ())
                | set(candidate.noncontact_placement_contract['immutable_refs']))
            noncontact_scope=dict(materialization_scope='noncontact_smd_delta_without_copper_ownership',
                original_copper_coverage=coverage,noncontact_domain=domain,release_authority=False)
    except cec_placement_route_prefix.UnadmittedLocalCopper as exc:
        # The prefix guard correctly rejects local copper from an unqualified
        # power state. Treat that known dependency as a structured blocked
        # result, not an isolated-worker crash or permission to silently drop
        # the copper. Even exact noncontact retention grants no route authority.
        return dict(schema=1,ok=False,changed=False,applicable=True,
            reason='unadmitted_local_copper_requires_owned_recovery',
            blocked_stage='frozen_power_authority',
            retry_requires='owned_local_copper_transaction_and_fresh_power_qualification',
            copper_ownership=exc.evidence,route_authority=authority,
            release_authority=False)
    except cec_placement_route_prefix.UnownedRoutedCopper as exc:
        return dict(schema=1, ok=False, changed=False, applicable=True,
            reason='routed_copper_requires_owned_transaction',
            copper_ownership=exc.evidence, route_authority=authority,
            release_authority=False)
    frozen_bound = bool(authority_bound and authority.get('bound'))
    if frozen_bound:
        import cec_frozen_placement_domain
        candidate.frozen_placement_contract = cec_frozen_placement_domain.bind(board, candidate)
    reuse_context = (cec_route_evidence.baseline_context(cfg, board,
        allow_authored_prefix=allow_authored_prefix,
        allow_unbound_power_authority=allow_unbound_power_authority)
        if baseline_evidence else None)
    reuse = cec_route_evidence.verify(baseline_evidence, reuse_context)
    if reuse['used']:
        candidate.route_preflight = cec_route_evidence.clean(baseline_evidence)
    from cec_operation_budget import progress
    progress('repair_baseline_reuse', **reuse)
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
        if frozen_bound:
            report = _commit_frozen_placement_repair(bound, repaired, board, report)
            if not report.get('changed'):
                repaired = candidate
        else:
            synth.materialize(repaired, bound, str(board))
    evidence = dict(getattr(repaired, "route_preflight", {}) or {})
    return {
        **report,
        "schema": 1,
        "ok": not bool(evidence.get("error")) and not report.get('rolled_back', False),
        "applicable": True,
        "result_evidence": evidence,
        "baseline_reuse": reuse,
        "route_authority": authority,
        "authority_mode": ("exact" if authority_bound else
                           "prospective_power_reservations"),
        **(noncontact_scope or {}),
    }


def _repair_placement_priority_routes(
        cfg, board, *, completion_report=None, baseline_evidence=None,
        allow_authored_prefix=False,
        allow_unbound_power_authority=False):
    kwargs = {
        "completion_report": completion_report,
        "allow_authored_prefix": allow_authored_prefix,
        "allow_unbound_power_authority": allow_unbound_power_authority,
    }
    if baseline_evidence is not None:
        kwargs['baseline_evidence'] = baseline_evidence
    import cec_placement_probe_coverage as coverage
    visits, state, history_receipt = _placement_search_history(board, 'priority')
    # Keep diagnostic scheduling inputs off the caller's electrical recipe.
    cfg = copy.copy(cfg)
    cfg.params = dict(cfg.params or {})
    configured = dict(cfg.params.get('placement_probe_history') or {})
    if visits:
        configured['priority'] = coverage.export_visits(visits)
    cfg.params['placement_probe_history'] = configured
    def finish(report):
        report['search_history_resume'] = history_receipt
        _save_placement_search_history(board, 'priority', state, report)
        return report
    if cfg.params.get("priority_route_process_isolation", False):
        return finish(_run_priority_placement_operation_isolated(
            "priority-repair", cfg, board, **kwargs))
    try:
        return finish(_repair_placement_priority_routes_in_process(
            cfg, board, **kwargs))
    except Exception as exc:                           # noqa: BLE001
        message = "%s: %s" % (type(exc).__name__, exc)
        if ("SwigPyObject" not in message
                and "invalid board proxy" not in message):
            raise
        result = _run_priority_placement_operation_isolated(
            "priority-repair", cfg, board, **kwargs)
        result["repair_process"] = "isolated_swig_recovery"
        result["recovered_from"] = message
        return finish(result)


def _priority_cooptimization_attempt(cfg, repair_cfg, board, *, completion_report,
        baseline_evidence, allow_authored_prefix, allow_unbound_power_authority):
    """Keep an exhausted private solve from discarding the measured incumbent.

    Only the supervisor's explicit budget result becomes a bounded stop.
    Crashes, changed inputs and other integrity failures still propagate.
    The outer coordinator restores its selected complete snapshot afterward.
    """
    import cec_operation_budget
    try:
        result = _repair_placement_priority_routes(
            repair_cfg, board, completion_report=completion_report,
            baseline_evidence=baseline_evidence,
            allow_authored_prefix=allow_authored_prefix,
            allow_unbound_power_authority=allow_unbound_power_authority)
        if result.get('ok') and not result.get('changed'):
            gate = _placement_priority_route_gate(
                dict(result.get('result_evidence') or {}), applicable=True)
            if not gate.get('ok'):
                result = _repair_placement_priority_routes_with_power_replan(
                    cfg, board, result, allow_authored_prefix=allow_authored_prefix)
        return result
    except cec_operation_budget.OperationFailure as exc:
        evidence = dict(exc.failure_evidence)
        if evidence.get('status') != 'operation_budget_exhausted':
            raise
        return {'schema': 1, 'ok': False, 'changed': False,
                'reason': 'cooptimization_operation_budget_exhausted',
                'operation_evidence': evidence, 'release_authority': False}


def _repair_placement_priority_routes_with_power_replan(
        cfg, board, ordinary_report, *, allow_authored_prefix=False,
        repairing_failed_authority=False):
    """Budget and retain the full power-replan handoff like other native work."""
    if cfg.params.get('priority_route_process_isolation', False):
        result = _run_priority_placement_operation_isolated(
            'priority-power-replan', cfg, board,
            completion_report=dict(ordinary_report=ordinary_report,
                repairing_failed_authority=repairing_failed_authority),
            allow_authored_prefix=allow_authored_prefix)
        if result.get('ok') and result.get('changed'):
            for key in ('pourfirst_state', 'pourfirst_outline_mm',
                        'pourfirst_seen_placements', 'pourfirst_avoid_boxes'):
                cfg.params.pop(key, None)
        return result
    return _repair_placement_priority_routes_with_power_replan_in_process(
        cfg, board, ordinary_report, allow_authored_prefix=allow_authored_prefix,
        repairing_failed_authority=repairing_failed_authority)


def _repair_placement_priority_routes_with_power_replan_in_process(
        cfg, board, ordinary_report, *, allow_authored_prefix=False,
        repairing_failed_authority=False):
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
    import cec_frozen_copper
    import cec_priority_dependency
    import cec_finalist_evidence
    import cec_post_authority_recovery

    board = Path(board).resolve()
    original_hash = sha256_file(board)
    original_family = {str(path): sha256_file(path)
                       for path in _placement_authority_family(board) if path.is_file()}
    limit = max(0, int(cfg.params.get(
        "placement_power_replan_candidates", 2) or 2))
    rows = cec_priority_dependency.handoff_candidates(ordinary_report, limit)
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
    dependency_trials = 0
    dependency_screens = 0
    dependency_limit = max(0, int(cfg.params.get("priority_dependency_trials", 2)))
    return_recovery_limit = min(4, max(0, int(cfg.params.get(
        "post_authority_return_recovery_calls", 1))))
    report['post_authority_return_recovery_calls'] = 0
    import cec_operation_budget as operation_budget
    def record_trial(phase, trial):
        operation_budget.progress(phase, trial=trial["index"])
        operation_budget.checkpoint({"kind": "power-placement-replan",
                                    "report": report, "current_trial": trial})
    power_keys = ("pourfirst_state", "pourfirst_outline_mm",
                  "pourfirst_seen_placements", "pourfirst_avoid_boxes")
    with tempfile.TemporaryDirectory(
            prefix="cec-placement-power-replan-") as work:
        work = Path(work)
        for index, row in enumerate(rows):
            started = time.monotonic()
            trial_cfg = copy.deepcopy(cfg)
            trial_cfg.params["power_failure_artifact_dir"] = str(
                board.parent / "power-replan-diagnostics")
            for key in power_keys:
                trial_cfg.params.pop(key, None)
            candidate = synth.placement_candidate_from_board(
                trial_cfg, str(board), allow_routed=allow_authored_prefix)
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
                "placements": dict(row.get("placements") or {}),
            }
            record_trial("power_replan_materialization", trial_report)
            try:
                dependency = None
                original_prefix = copy.deepcopy(getattr(candidate, "protected_power_prefix", {}) or {})
                try:
                    synth.materialize(candidate, trial_cfg, str(trial_board))
                except cec_frozen_copper.FrozenCopperConflict as exc:
                    trial_report["frozen_copper_conflict"] = exc.report
                    if not (repairing_failed_authority or
                            row.get('priority_dependency_replacement') is True):
                        raise
                    if dependency_trials >= dependency_limit:
                        trial_report["reason"] = "priority_dependency_budget_exhausted"
                        continue
                    dependency = cec_priority_dependency.release_plan(
                        original_prefix, exc.report,
                        max_pairs=max(0, int(cfg.params.get("priority_dependency_max_pairs", 1))))
                    trial_report["priority_dependency"] = {k: value for k, value in dependency.items()
                                                            if k != "retained_contract"}
                    if not dependency.get("ok"):
                        trial_report["reason"] = "nonreplaceable_frozen_copper"
                        continue
                    dependency_screens += 1
                    candidate.protected_power_prefix = dependency["retained_contract"]
                    synth.materialize(candidate, trial_cfg, str(trial_board))
                if row.get('priority_dependency_replacement') and not dependency:
                    trial_report['reason'] = 'offered_pair_dependency_not_reproduced'
                    continue
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
                if not courtyards.get("ok"):
                    trial_report["physical"]["courtyard_evidence"] = courtyards
                if not craft_gate.get("ok"):
                    craft_failures = _placement_craft_failures(craft)
                    trial_report["physical"].update({
                        "craft_failed_terms": sorted(craft_failures),
                        "craft_failure_evidence": craft_failures,
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
                # The finite expensive dependency allowance belongs to
                # physically admissible proposals. Failed courtyard screens
                # are already bounded by the outer placement candidate list.
                if dependency:
                    dependency_trials += 1
                record_trial("power_replan_authority", trial_report)
                authority = _ensure_placement_route_authority(
                    trial_cfg, trial_board,
                    allow_authored_prefix=allow_authored_prefix)
                trial_report["route_authority"] = {
                    key: value for key, value in authority.items()
                    if key not in ("_artifacts", "planner")}
                if (authority.get("planner") or {}).get("failure_evidence"):
                    trial_report["route_authority"]["failure_evidence"] = \
                        authority["planner"]["failure_evidence"]
                if not authority.get("ok"):
                    trial_report["reason"] = "power_replan_refused"
                    continue
                # The authority compiler can itself change placement. Its
                # output, not just the pre-power trial, must pass mechanics.
                post_physical = _measure_placement_physical(trial_cfg, trial_board)
                post_ok = all((post_physical.get(term) or {}).get("ok") for term in
                              ("pads_in_bounds", "courtyards", "craft_gate", "constraint_gate"))
                if not post_ok and cec_post_authority_recovery.eligibility(post_physical)['ok']:
                    trial_report['post_authority_before_recovery'] = {
                        key: post_physical.get(key) for key in
                        ('pads_in_bounds', 'courtyards', 'craft_gate', 'constraint_gate')}
                    if report['post_authority_return_recovery_calls'] < return_recovery_limit:
                        report['post_authority_return_recovery_calls'] += 1
                        record_trial('power_replan_local_return_recovery', trial_report)
                        recovered, post_physical = cec_post_authority_recovery.recover(
                            trial_cfg, trial_board, post_physical,
                            max_trials=cfg.params.get('post_authority_return_recovery_trials', 16),
                            allow_authored_prefix=allow_authored_prefix)
                        trial_report['post_authority_return_recovery'] = recovered
                        post_ok = all((post_physical.get(term) or {}).get('ok') for term in
                            ('pads_in_bounds', 'courtyards', 'craft_gate', 'constraint_gate'))
                    else:
                        trial_report['post_authority_return_recovery'] = {
                            'ok': False, 'changed': False, 'reason': 'operation_recovery_budget_exhausted'}
                trial_report["post_authority_physical_ok"] = bool(post_ok)
                if not post_ok:
                    trial_report["reason"] = "post_authority_physical_refused"
                    trial_report['post_authority_physical_failures'] = {
                        key:value for key,value in post_physical.items()
                        if key in ('pads_in_bounds','courtyards','craft_gate','constraint_gate')
                        and isinstance(value,dict) and not value.get('ok')}
                    trial_report['post_authority_craft_failures'] = _placement_craft_failures(post_physical.get('craft'))
                    continue
                if dependency:
                    record_trial("power_replan_pair_dependency", trial_report)
                    rebuilt = cec_priority_dependency.rebuild(
                        trial_cfg, trial_board, dependency, original_prefix,
                        board.parent / ("priority-dependency-%02d" % index),
                        allow_authored_prefix=allow_authored_prefix)
                    trial_report["priority_dependency_rebuild"] = rebuilt
                    if not rebuilt.get("ok"):
                        trial_report["reason"] = "owned_priority_dependency_unpaid"
                        continue
                if repairing_failed_authority and not baseline_key:
                    # Pay for the baseline pair solve only after a proposal
                    # proves that the missing power dependency can be repaired.
                    record_trial("power_replan_baseline_measurement", trial_report)
                    baseline = _measure_placement_priority_routes(
                        cfg, board, allow_authored_prefix=allow_authored_prefix,
                        allow_unbound_power_authority=True)
                    if baseline.get("error"):
                        trial_report["reason"] = "baseline_priority_unproven"
                        break
                    baseline_key = tuple(cec_route_preflight.placement_evidence_key(baseline))
                    report["baseline_key"] = list(baseline_key)
                record_trial("power_replan_candidate_measurement", trial_report)
                measured_identity = cec_finalist_evidence.identity(trial_board)
                evidence = _measure_placement_priority_routes(
                    trial_cfg, trial_board,
                    allow_authored_prefix=allow_authored_prefix)
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
                comparison = cec_finalist_evidence.compare_keys(
                    cec_route_preflight.PLACEMENT_EVIDENCE_FIELDS, baseline_key, key)
                trial_report['comparison'] = comparison
                trial_report['artifact'] = cec_finalist_evidence.retain(
                    dict(path=str(board), sha256=original_hash), measured_identity,
                    dict(index=index, kind=row.get('kind'), placements=row.get('placements'),
                         comparison=comparison, release_authority=False),
                    evidence, board.parent/'power-replan-finalists', limit=2,
                    minimum_free_gib=max(16., float(cfg.params.get('minimum_free_gib', 16))))
                improved = key < baseline_key or (
                    repairing_failed_authority and key == baseline_key)
                if not evidence.get("error") and improved and (
                        best is None or key < best[0]):
                    import cec_priority_replacement_receipt as replacement_receipt
                    receipt=(replacement_receipt.issue(original_prefix,dependency,
                        trial_report['priority_dependency_rebuild'],trial_board,
                        source_board_sha256=original_hash) if dependency else None)
                    trial_report['priority_replacement_receipt']=replacement_receipt.stage(
                        board,trial_board,receipt)
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
                report['trial_summaries'] = [{key: value for key, value in trial.items()
                    if key in ('index', 'kind', 'refs', 'reason', 'error', 'wall_s',
                               'key', 'comparison', 'artifact', 'critical_route_refused_count')}
                    for trial in report['trials']]
                record_trial("power_replan_trial_complete", trial_report)

    if best is None:
        report["priority_dependency_trials"] = dependency_trials
        report["priority_dependency_screens"] = dependency_screens
        report["reason"] = "no_post_power_authority_improvement"
        return {**ordinary_report, "power_replan": report}

    best_key, winning_row, evidence, winning_trial, payload = best
    current_family = {str(path): sha256_file(path)
                      for path in _placement_authority_family(board) if path.is_file()}
    if sha256_file(board) != original_hash or current_family != original_family:
        raise RuntimeError("power-replan source changed before promotion")
    published = _publish_placement_authority_payload(board, payload)
    # The exact admitted PCB and its matching sibling authority are now the
    # canonical artifact family. Clear config projections belonging to the
    # pre-move placement; the normal binder will rediscover the new sibling
    # state without rebuilding it.
    for key in power_keys:
        cfg.params.pop(key, None)
    report.update({
        "accepted": True, "changed": True,
        "priority_dependency_trials": dependency_trials,
        "priority_dependency_screens": dependency_screens,
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


def _repair_failed_power_bridge_placement_in_process(
        cfg, board, authority, *, allow_authored_prefix=False):
    """Feed verified power terminals into the existing power-first transaction."""
    import pcbnew
    import cec_power_failure
    import cec_synth_pipeline as synth

    failure = cec_power_failure.bridge_failure(authority)
    report = {"schema": 1, "ok": True, "changed": False,
              "applicable": bool(failure), "reason": "no_typed_power_bridge_failure"}
    if not failure:
        return report
    limit = max(0, int(cfg.params.get("power_terminal_repair_trials", 12)))
    if limit == 0:
        return {**report, "reason": "policy_disabled"}
    loaded = pcbnew.LoadBoard(str(board))
    pads = {}
    for fp in loaded.GetFootprints():
        for pad in fp.Pads():
            pads.setdefault((fp.GetReference(), pad.GetNumber()), []).append({
                "net": pad.GetNetname(), "x_mm": pad.GetPosition().x / 1e6,
                "y_mm": pad.GetPosition().y / 1e6})
    evidence = cec_power_failure.terminal_evidence(failure, pads)
    report["terminal_evidence"] = evidence
    if not evidence["pin_access_blocked"] or evidence["rejected"]:
        return {**report, "reason": "power_terminal_evidence_unproven"}
    local = copy.deepcopy(cfg)
    for key in ("pourfirst_state", "pourfirst_outline_mm",
                "pourfirst_seen_placements", "pourfirst_avoid_boxes"):
        local.params.pop(key, None)
    candidate = synth.placement_candidate_from_board(
        local, str(board), allow_routed=allow_authored_prefix)
    nl = synth.View(local).nl
    comps = synth._fp_of(nl)
    anchors, ics, shunts, passives = synth._classify(
        nl, role_overrides=local.params.get("anchor_roles"))
    passive_spec, series = synth.derive_passive_spec(
        nl, passives, ics, anchor_refs=set(anchors) | set(shunts))
    groups = synth._route_local_follower_groups(candidate, passive_spec, series, comps)
    fixed = (set(synth._placement_repair_immutable_refs(local))
             | set(anchors) | set(shunts))
    fixed.update(fp.GetReference() for fp in loaded.GetFootprints() if fp.IsLocked())
    local.params["placement_immutable_refs"] = sorted(fixed)
    moves = synth._route_access_move_specs(candidate, evidence, local, groups=groups)
    eligible = []
    for move in moves:
        moved = set((move.get("placements") or {}).keys())
        root = str(move.get("ref") or "")
        complete = set(groups.get(root, (root,)))
        if moved and not moved.intersection(fixed) and complete <= moved:
            eligible.append(move)
    moves = synth._bounded_evidence_move_specs(eligible, limit)
    report.update({"generated": len(eligible), "selected": len(moves),
                   "failure_evidence": failure})
    if not moves:
        return {**report, "reason": "no_movable_power_terminal_cell"}
    local.params["placement_power_replan_candidates"] = len(moves)
    ordinary = {"schema": 1, "ok": True, "changed": False,
                "rounds": [{"power_replan_candidates": moves}]}
    # Already running inside the bounded power-terminal operation.
    result = _repair_placement_priority_routes_with_power_replan_in_process(
        local, board, ordinary, allow_authored_prefix=allow_authored_prefix,
        repairing_failed_authority=True)
    report.update({"changed": bool(result.get("changed")),
                   "reason": ("power_authority_repaired" if result.get("changed")
                              else "no_complete_power_first_improvement"),
                   "power_replan": result.get("power_replan")})
    return report


def _repair_failed_power_bridge_placement(cfg, board, authority, *, allow_authored_prefix=False):
    import cec_power_failure
    if not cec_power_failure.bridge_failure(authority):
        return {"schema": 1, "ok": True, "changed": False, "applicable": False}
    return _run_priority_placement_operation_isolated(
        "power-terminal-repair", cfg, board, completion_report=authority,
        allow_authored_prefix=allow_authored_prefix)


def _measure_placement_priority_routes_in_process(
        cfg, board, *, allow_unbound_power_authority=False,
        allow_authored_prefix=False):
    """Measure placement with the configured critical/power owner order."""
    import cec_synth_pipeline as synth
    import cec_route_evidence

    board = Path(board).resolve()
    context_options = dict(allow_authored_prefix=allow_authored_prefix,
        allow_unbound_power_authority=allow_unbound_power_authority)
    before_context = cec_route_evidence.baseline_context(cfg, board, **context_options)
    bound, authority = synth.config_with_board_route_authority(
        cfg, str(board))
    requires_power_authority = _requires_frozen_route_authority(cfg)
    authority_bound = bool(
        not allow_unbound_power_authority
        and authority.get("ok")
        and (not requires_power_authority or authority.get("bound")))
    if allow_unbound_power_authority:
        bound = copy.copy(cfg)
        bound.params = dict(cfg.params or {})
        for key in ("pourfirst_state", "pourfirst_outline_mm",
                    "pourfirst_seen_placements", "pourfirst_avoid_boxes"):
            bound.params.pop(key, None)
    if not authority_bound and not allow_unbound_power_authority:
        return {"error": "exact route authority is not bound",
                "route_authority": authority}
    # Exact placement authority may legitimately contain copper generated by
    # this stage itself (force rails, blueprint cells, local PI, and current
    # pours).  Rehydration remains fail-closed for arbitrary routed inputs;
    # callers must explicitly attest that this is a pipeline-owned prefix.
    bound.params["placement_route_pair_timeout_s"] = float(cfg.params.get(
        "placement_route_pair_timeout_s", 120.0) or 120.0)
    with synth._oracle_env(bound.params), \
            synth._placement_route_preflight_env():
        options = dict(grid_mm=float(cfg.params.get(
                           'placement_route_preflight_grid_mm', 1.0) or 1.0),
                       iters=int(cfg.params.get('placement_route_preflight_iters', 4) or 4),
                       backend=str(cfg.params.get('placement_route_preflight_backend', 'auto')))
        multiresolution = bool(cfg.params.get('placement_route_preflight_multiresolution', True))
        if allow_authored_prefix:
            # This is measurement of an already materialized, exact admitted
            # boundary, not a placement proposal. Rebuilding it strips useful
            # critical copper before asking the solver to recreate that copper.
            # Explicitly allowed prospective power is separate from artifact
            # identity: missing frozen power must not substitute a regenerated
            # board for this known authored prefix. The scoped prospective
            # compiler and final exact-power admission remain mandatory.
            import cec_route_preflight
            analyze = (cec_route_preflight.analyze_multiresolution if multiresolution
                       else cec_route_preflight.analyze)
            evidence = cec_route_preflight.compact_placement_evidence(analyze(
                str(board), **options, run_future_congestion=True,
                critical_nets=tuple(cfg.params.get('critical_route_nets', ()) or ())))
            evidence['measurement_domain'] = 'exact_saved_artifact'
        else:
            candidate = synth.placement_candidate_from_board(
                bound, str(board), allow_routed=allow_authored_prefix)
            measured = synth.rerank_route_preflight(
                bound, [candidate], topk=1, **options, multiresolution=multiresolution)[0]
            evidence = dict(measured.route_preflight or {})
    evidence["authority_mode"] = (
        "exact" if authority_bound else "prospective_power_reservations")
    if not authority_bound:
        evidence["unbound_route_authority"] = authority
    after_context = cec_route_evidence.baseline_context(cfg, board, **context_options)
    if before_context != after_context:
        evidence['error'] = 'inputs_changed_during_priority_measurement'
        return evidence
    return cec_route_evidence.seal(evidence, after_context)


def _measure_placement_priority_routes(
        cfg, board, *, allow_unbound_power_authority=False,
        allow_authored_prefix=False):
    """Measure priority routes, recovering dead KiCad state in isolation.

    The ordinary fast path remains in-process. If KiCad's legacy bindings
    return a dead proxy after a long exact-power transaction, repeat the exact
    same read-only measurement once in a fresh interpreter and return only its
    JSON evidence. No admission rule is weakened and no board is mutated.
    """
    kwargs = {
        "allow_unbound_power_authority": allow_unbound_power_authority,
        "allow_authored_prefix": allow_authored_prefix,
    }
    if cfg.params.get("priority_route_process_isolation", False):
        result = _run_priority_placement_operation_isolated(
            "priority-measure", cfg, board, **kwargs)
        result["measurement_process"] = "isolated"
        return result
    try:
        return _measure_placement_priority_routes_in_process(
            cfg, board, **kwargs)
    except Exception as exc:                           # noqa: BLE001
        message = "%s: %s" % (type(exc).__name__, exc)
        if ("SwigPyObject" not in message
                and "invalid board proxy" not in message):
            raise
        evidence = _run_priority_placement_operation_isolated(
            "priority-measure", cfg, board, **kwargs)
        evidence["measurement_process"] = "isolated_swig_recovery"
        evidence["recovered_from"] = message
        return evidence


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
            ".railreport.json", ".cellreport.json", ".power-prefix.json",
            ".pourfirst-state.json"))
    paths.append(skeleton)
    paths.append(board.with_suffix('.priority-replacements.json'))
    # Keep deterministic ordering and do not let a malformed board name make
    # the transaction touch anything outside its own sibling artifact family.
    return tuple(sorted(set(paths), key=lambda path: str(path)))


def _placement_native_route_escape(cfg, board, evidence):
    """One additive routing trial before any raster-driven placement ECO.

    Reuse the normal preflight recovery on an immutable parent. Promote only
    after actual output authority and priority measurement pass again. The
    whole placement/power artifact family rolls back on any failed term.
    """
    import cec_preflight_native_recovery as native
    import cec_fr
    if (not cfg.params.get('preflight_native_recovery',True)
            or not native.placement_eligible(evidence)):
        return dict(ok=False,changed=False,applicable=False)
    board=Path(board).resolve()
    identity=digest_value(dict(source=native.authority_signature(board),
        code=_code_closure_signature('cec_preflight_native_recovery.py'),
        policy={key:value for key,value in cfg.params.items()
                if key.startswith('preflight_native_')}))[:16]
    work=board.parent/('native-placement-recovery-'+identity)
    parent=work/'parent'/board.name
    if not parent.is_file():
        parent.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(board,parent)
        cec_fr.copy_project_sidecars(str(board),str(parent))
    if sha256_file(parent)!=sha256_file(board):
        return dict(ok=False,changed=False,reason='native_placement_parent_changed')
    result=dict(ok=False,changed=False,applicable=True,source=str(parent))
    preflight=_preflight_stage(parent,work/'preflight',cfg,
        grid_mm=float(cfg.params.get('placement_route_preflight_grid_mm',1.) or 1.),
        iterations=int(cfg.params.get('placement_route_preflight_iters',4) or 4),
        backend=str(cfg.params.get('placement_route_preflight_backend','auto')),
        constructive_nets=native.targets(evidence))
    result.update(preflight=preflight,_artifacts=preflight.get('_artifacts') or [])
    child=Path(preflight.get('board') or parent).resolve()
    receipt=json.loads(Path(preflight['report']).read_text())
    recovery=receipt.get('native_recovery') or {}
    if (not preflight.get('admission_gate') or child==parent
            or not recovery.get('ok') or not native.admitted(recovery.get('terms') or {})):
        result['reason']='native_escape_not_independently_admitted'
        return result
    saved_params,saved_pins=copy.deepcopy(cfg.params),copy.deepcopy(cfg.pins)
    with tempfile.TemporaryDirectory(prefix='cec-native-placement-commit-') as rollback:
        _snapshot_placement_authority(board,rollback)
        try:
            _copy_sidecars(child,board,cfg=cfg)
            authority=_ensure_placement_route_authority(cfg,board,allow_authored_prefix=True)
            measured=_measure_placement_priority_routes(cfg,board,allow_authored_prefix=True)
            gate=_placement_priority_route_gate(measured)
            import pcbnew
            parent_board=pcbnew.LoadBoard(str(parent))
            copper=cec_fr.check_copper_geometry_prefix(str(board),
                cec_fr.copper_geometry_prefix_contract(str(parent),{
                    item.GetNetname() for item in parent_board.GetTracks()}))
            same_positions=_placement_position_signature(parent)==_placement_position_signature(board)
            accepted=bool(authority.get('ok') and gate.get('ok') and copper.get('ok')
                          and same_positions and sha256_file(board)==sha256_file(child))
            result.update(ok=accepted,changed=accepted,priority_evidence=measured,
                priority_gate=gate,route_authority=authority,parent_copper=copper,
                placement_unchanged=same_positions,reason=(
                    'native_escape_before_placement_search' if accepted else 'native_commit_recheck_refused'))
        except Exception as exc:
            result.update(error=type(exc).__name__+': '+str(exc),reason='native_commit_failed')
        finally:
            if not result.get('changed'):
                _restore_placement_authority(board,rollback)
                cfg.params,cfg.pins=saved_params,saved_pins
    return result


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
    snapshot = _placement_board_snapshot(board)
    back = set(snapshot.get("back_refs") or ())
    rows = [
        (str(ref), round(float(pose[0]), 6),
         round(float(pose[1]), 6),
         round(float(pose[2]) % 360.0, 6), str(ref) in back)
        for ref, pose in (snapshot.get("placements") or {}).items()
        if isinstance(pose, (list, tuple)) and len(pose) == 3
    ]
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
    # The variant's mechanical datums were rebound to its target outline.
    # Apply them to the native placement before collision legalization; a
    # Config-only update leaves the old terminal row in the emitted PCB.
    import cec_outline_compaction
    result.P, report['required_anchors'] = (
        cec_outline_compaction.bind_required_positions(
            result.P, getattr(cfg, 'pins', None)))
    result.W = float(width)
    result.H = float(height)
    # This function is entered only by explicit replacement placement. The
    # trial must resize actual Edge.Cuts and re-earn copper authority, not
    # carry the source's frozen proof into a different physical outline.
    result.outline_replacement_authorized = True
    result.protected_power_prefix = {}
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
    search_base.outline_replacement_authorized = True
    search_base.protected_power_prefix = {}
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


def _replacement_source_outline(cfg, source):
    """Resolve the fixed-outline seed for replacement placement.

    A current schematic-first board can legitimately carry a footprint staging
    PCB before its first layout pass.  Such a file has no Edge.Cuts, so its
    footprint bounding box is not a mechanical authority.  Admit it only when
    the board's current policy explicitly declares ``bootstrap_outline_mm``;
    otherwise fail closed instead of guessing or borrowing an old candidate.
    """
    width = float(getattr(source, "W", 0.0) or 0.0)
    height = float(getattr(source, "H", 0.0) or 0.0)
    if width > 1e-6 and height > 1e-6:
        return source, {
            "mode": "edge_cuts",
            "outline_mm": [width, height],
            "origin_mm": [float(getattr(source, "x0", 0.0) or 0.0),
                          float(getattr(source, "y0", 0.0) or 0.0)],
        }

    declared = (getattr(cfg, "params", {}) or {}).get(
        "bootstrap_outline_mm")
    if (not isinstance(declared, (tuple, list)) or len(declared) != 2):
        raise PipelineBlocked(
            "replacement placement source has no Edge.Cuts and the current "
            "board policy declares no bootstrap_outline_mm")
    try:
        width, height = (float(declared[0]), float(declared[1]))
    except (TypeError, ValueError) as exc:
        raise PipelineBlocked(
            "bootstrap_outline_mm must contain two numeric dimensions") from exc
    if (not math.isfinite(width) or not math.isfinite(height)
            or width <= 0.0 or height <= 0.0):
        raise PipelineBlocked(
            "bootstrap_outline_mm dimensions must be finite and positive")

    origin = (getattr(cfg, "params", {}) or {}).get(
        "bootstrap_outline_origin_mm", (0.0, 0.0))
    if (not isinstance(origin, (tuple, list)) or len(origin) != 2):
        raise PipelineBlocked(
            "bootstrap_outline_origin_mm must contain two numeric coordinates")
    try:
        x0, y0 = (float(origin[0]), float(origin[1]))
    except (TypeError, ValueError) as exc:
        raise PipelineBlocked(
            "bootstrap_outline_origin_mm must contain two numeric coordinates") \
            from exc
    if not math.isfinite(x0) or not math.isfinite(y0):
        raise PipelineBlocked(
            "bootstrap_outline_origin_mm coordinates must be finite")

    resolved = copy.copy(source)
    resolved.W, resolved.H = width, height
    resolved.x0, resolved.y0 = x0, y0
    return resolved, {
        "mode": "declared_bootstrap",
        "outline_mm": [width, height],
        "origin_mm": [x0, y0],
        "policy_key": "bootstrap_outline_mm",
    }


def _bind_outline_variant_interface_anchors(synth, cfg, width, height):
    """Bind every declarative interface pose into an outline candidate.

    ``synth_one`` also resolves these anchors inside its worker-local Config,
    but that Config is intentionally not returned by the multiprocessing
    boundary.  The full-flow coordinator later owns craft repair,
    materialization, and route-authority generation; it therefore needs the
    same constraints in its persistent variant Config.  Without this handoff,
    a derived auxiliary connector can be correctly seated by synthesis and
    then treated as movable by a later generic repair pass.
    """
    anchors = synth._bind_declared_interface_anchors(cfg, width, height)
    missing = sorted(ref for ref in anchors if ref not in (cfg.pins or {}))
    if missing:
        raise RuntimeError(
            "declarative interface anchor binding lost ref(s): %s" %
            ", ".join(missing))
    return anchors


def _bind_placement_worker_budget(cfg, workers):
    # ``--workers`` is the placement stage's host-resource ceiling, not merely
    # the cheap seed-generator width.  Before this binding, nested exact craft
    # and route-aware evaluators silently fell back to their own 16-worker
    # defaults; two ordinary pipeline invocations could exhaust a 27 GiB WSL
    # VM despite both being launched with ``--workers 6``.  Bound every nested
    # placement pool to the same explicit ceiling while preserving a tighter
    # board policy when one is declared.
    if workers is None:
        return {}
    worker_ceiling = max(1, int(workers))
    bound = {}
    for key in (
            "placement_craft_eval_workers",
            "placement_route_preflight_workers",
            "placement_route_repair_probe_workers",
            "route_authority_workers"):
        configured = int(cfg.params.get(key, worker_ceiling) or 1)
        cfg.params[key] = min(worker_ceiling, max(1, configured))
        bound[key] = cfg.params[key]
    return bound


def _placement_stage_artifact_provenance(board_path):
    """Return verified provenance for a pipeline placement-stage artifact.

    Placement materialization legitimately contains locked force rails and
    landing copper, so ``GetTracks()`` alone cannot distinguish it from a
    routed canonical board.  A resumable artifact must instead be named in an
    adjacent pipeline-state ledger and match that ledger's SHA-256 exactly.
    This keeps arbitrary routed inputs read-only while allowing a bounded
    placement repair to continue from the pipeline's own admitted checkpoint.
    """
    board_path = Path(board_path).resolve()
    if board_path.with_suffix('.placement-checkpoint.json').exists():
        import cec_placement_checkpoint
        # An invalid explicit checkpoint must never fall back to a weaker
        # nearby journal or an older authored-prefix certificate.
        record = cec_placement_checkpoint.read_board(board_path)
        return {"kind": "pipeline_placement_work", "sha256": record['sha256'],
                "family": record['family'], "phase": record['phase'],
                "context": record['context'], "routing_admitted": False}
    for ancestor in tuple(board_path.parents)[:4]:
        state_path = ancestor / "pipeline-state.json"
        if not state_path.is_file():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            stage = (state.get("stages") or {}).get("placement") or {}
            for artifact in stage.get("artifacts") or ():
                candidate = Path(str(artifact.get("path") or "")).resolve()
                if candidate != board_path:
                    continue
                expected = str(artifact.get("sha256") or "")
                if not expected or sha256_file(board_path) != expected:
                    return None
                return {
                    "schema": 1,
                    "kind": "pipeline_placement_stage",
                    "state": str(state_path),
                    "stage_status": str(stage.get("status") or ""),
                    "sha256": expected,
                }
        except (OSError, ValueError, TypeError):
            return None
    # A placement stage can fail after it has deliberately materialized
    # force rails or exact power but before StageJournal receives the final
    # result.  Preserve that expensive, deterministic boundary with a narrow
    # digest sidecar.  It authorizes only this exact board file; arbitrary
    # routed inputs still have neither a matching journal artifact nor this
    # pipeline-written certificate and remain read-only.
    checkpoint = board_path.with_suffix(".authored-prefix.json")
    if checkpoint.is_file():
        try:
            row = json.loads(checkpoint.read_text(encoding="utf-8"))
            expected = str(row.get("sha256") or "")
            certified = Path(str(row.get("board") or "")).resolve()
            if (row.get("schema") == 1
                    and row.get("kind") == "pipeline_placement_authored_prefix"
                    and certified == board_path
                    and expected
                    and sha256_file(board_path) == expected):
                return {
                    "schema": 1,
                    "kind": "pipeline_placement_authored_prefix",
                    "checkpoint": str(checkpoint),
                    "sha256": expected,
                }
        except (OSError, ValueError, TypeError):
            return None
    # Review-only placement uses the same materializer, but intentionally
    # returns before the route-admitted checkpoint/journal boundary. Its
    # retained exact artifact has a separate source-checked certificate.
    # Without recognizing it, a continuation mistakes authored lanes for a
    # routed canonical PCB and silently skips all placement repair.
    review = board_path.with_suffix(".placement-review.json")
    if review.is_file():
        try:
            row = json.loads(review.read_text(encoding="utf-8"))
            expected = str(row.get("sha256") or "")
            if (row.get("schema") == 1
                    and row.get("role") == "initial-placement-review"
                    and row.get("routing_admitted") is False
                    and row.get("release_accepted") is False
                    and (row.get("evaluation") or {}).get("ok") is True
                    and (row.get("source_intake") or {}).get("ok") is True
                    and Path(str(row.get("board") or "")).resolve() == board_path
                    and expected and sha256_file(board_path) == expected):
                return {"schema": 1, "kind": "pipeline_placement_review",
                        "checkpoint": str(review), "sha256": expected,
                        "family": row.get("family"),
                        "context": row.get("context"), "sources": row.get("sources"),
                        "routing_admitted": False, "release_accepted": False}
        except (OSError, ValueError, TypeError, AttributeError):
            return None
    return None


def _write_placement_authored_prefix_checkpoint(board_path):
    """Digest-attest an exact pipeline-owned placement copper boundary."""
    board_path = Path(board_path).resolve()
    checkpoint = board_path.with_suffix(".authored-prefix.json")
    atomic_json(checkpoint, {
        "schema": 1,
        "kind": "pipeline_placement_authored_prefix",
        "board": str(board_path),
        "sha256": sha256_file(board_path),
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })
    return str(checkpoint)


def _retain_placement_candidate(source, candidate, result, cfg, destination, *, source_files=()):
    """Preserve the exact evaluated artifact, never rematerialize a preview.

    Initial-placement review is explicitly not routing or release admission.
    The complete physical/craft evidence travels with each candidate, including
    failed findings. Native worker errors cannot become reviewable successes.
    """
    if not result.get("ok"):
        raise PipelineBlocked("placement candidate evaluation failed: %s" %
                              result.get("error", "missing worker evidence"))
    destination = Path(destination).resolve()
    copied = _copy_sidecars(source, destination, cfg=cfg)
    import cec_constraints
    source_intake = cec_constraints.intake_gate(
        str(destination), {"sch": str(cfg.sch)}, defer_route_geometry=True)
    if not source_intake.get("ok"):
        raise PipelineBlocked("materialized candidate source intake failed: %s" %
                              "; ".join(source_intake.get("reasons") or ()))
    record = {
        "schema": 1, "role": "initial-placement-review",
        "board": str(destination), "sha256": sha256_file(destination),
        "family": getattr(cfg, "board", None),
        "context": {"pins": copy.deepcopy(getattr(cfg, "pins", {}) or {}),
                    "outline_mm": [candidate.W, candidate.H]},
        "sources": [{"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
                    for path in source_files],
        "strategy": candidate.strat, "seed": candidate.seed,
        "outline_mm": [candidate.W, candidate.H],
        "placement_signature": _candidate_position_signature(candidate),
        "residual": candidate.residual, "proxy": candidate.proxy,
        "placement_journal": copy.deepcopy(getattr(candidate, "journal", [])),
        "cell_packing": copy.deepcopy(getattr(candidate, "cell_packing", {})),
        "supply_inventory": copy.deepcopy(getattr(candidate, "supply_inventory", {})),
        "joint_supply_groups": copy.deepcopy(getattr(candidate, "joint_supply_groups", [])),
        "orientation_admission": copy.deepcopy(getattr(candidate, "orientation_admission", {})),
        "critical_supply_groups": copy.deepcopy(getattr(candidate, "critical_supply_groups", [])),
        "route_preflight": candidate.route_preflight,
        "evaluation": result, "source_intake": source_intake,
        "routing_admitted": False,
        "release_accepted": False,
    }
    report = destination.with_suffix(".placement-review.json")
    atomic_json(report, record)
    record["report"] = str(report)
    record["_artifacts"] = copied + [str(report)]
    return record


def _require_placement_supply_inventory(candidates):
    """Reject source shortages before production placement repair loops.

    Review-only generation may retain a failed source for inspection. Normal
    routing must not spend a geometric repair budget trying to create absent
    components. Legacy/read-back candidates without inventory retain their
    independent existing source and final craft gates.
    """
    for candidate in candidates:
        report = getattr(candidate, "supply_inventory", {}) or {}
        if report.get("ok") is not False:
            continue
        missing = report.get("missing") or ()
        error = PipelineBlocked("source supply inventory incomplete: " + "; ".join(
            "%s.%s (%s)" % (r.get("ref"), r.get("pin"), r.get("failure"))
            for r in missing))
        error.failure_evidence = {
            "certificate": {"kind": "source_supply_inventory_invalid",
                            "repair_stage": "schematic_component_inventory",
                            "inventory": copy.deepcopy(report)},
            "placement_journal": copy.deepcopy(getattr(candidate, "journal", []))}
        raise error


def _fresh_outline_candidates(synth, variant, width, height, *, strategies, seeds,
                              workers, rejections, checkpoint=None):
    """A geometrically infeasible outline is a rejected trial, not a batch crash.

    Catch only the typed geometric refusal. Invalid policy, missing source
    parts and programming exceptions must still fail loudly.
    """
    from cec_edge_packing import EdgePackingInfeasible
    try:
        extra = {'checkpoint': checkpoint} if checkpoint is not None else {}
        return synth.place_candidates(variant, width, height,
            strategies=tuple(strategies), seeds=tuple(seeds), max_workers=workers, **extra)
    except EdgePackingInfeasible as exc:
        rejections.append({"outline_mm": [width, height], "stage": "edge_bank_packing",
            "reason": str(exc), "exception": type(exc).__name__,
            "routing_admitted": False, "release_accepted": False})
        print("  [placement-outline] rejected %g x %g mm: %s" % (width, height, exc),
              flush=True)
        return []


def _placement_checkpointer(cfg, input_board, output_board):
    """Coordinator-only persistence; never serialized into solver workers."""
    import cec_constraints
    import cec_placement_checkpoint
    store = cec_placement_checkpoint.Store(
        Path(output_board).parent / 'checkpoints', family=cfg.board,
        sources=_source_files(cfg, input_board))

    def checkpoint(candidate, candidate_cfg, path, *, phase, rank, observation=None):
        def copy_family(source, destination):
            # Bound all known input sidecars before the native copy helper.
            # Do not copy logs, meshes, or arbitrary directory contents.
            suffixes = ('.kicad_pro', '.kicad_prl', '.kicad_dru', '.pourplan.json',
                        '.railreport.json', '.cellreport.json', '.pourfirst-state.json')
            possible = [source] + [source.with_suffix(s) for s in suffixes]
            possible += [p for s in ('.kicad_pro', '.kicad_prl', '.kicad_dru')
                         for p in Path(candidate_cfg.dir).glob('*' + s)]
            if sum(p.stat().st_size for p in set(possible) if p.is_file()) > store.max_family_bytes:
                raise ValueError('checkpoint family exceeds bounded storage policy')
            return _copy_sidecars(source, destination, cfg=candidate_cfg)

        result = store.publish(path, phase=phase, rank=rank,
            context={'pins': candidate_cfg.pins, 'outline_mm': [candidate.W, candidate.H]},
            copier=copy_family,
            validate=lambda board: cec_constraints.intake_gate(
                str(board), {'sch': candidate_cfg.sch}, defer_route_geometry=True),
            observation=observation)
        if result['published']:
            print('  [placement-checkpoint] %s retained: %s (unadmitted)' %
                  (phase, result['board']), flush=True)
        return result
    return checkpoint


def _restore_placement_resume_context(synth, cfg, input_board, provenance):
    """Rebind live mechanical policy before ANY resumed placement repair.

    New review records carry the same source-bound geometric context as work
    checkpoints. Legacy reviews must still bind current declared interfaces;
    absence of a context cannot silently make a rigid mating row movable.
    Contradictory geometry needs an explicit ECO/replacement, not pin dropping.
    """
    if not provenance:
        return {}
    context = provenance.get('context')
    if context is not None:
        import cec_placement_checkpoint
        if provenance.get('family') != cfg.board:
            raise ValueError('placement checkpoint belongs to a different family')
        if (provenance.get('kind') == 'pipeline_placement_review'
                and not cec_placement_checkpoint.source_valid(provenance.get('sources') or [])):
            raise ValueError('placement review source authority changed or disappeared')
        if not isinstance(context.get('pins'), dict):
            raise ValueError('invalid checkpoint geometric pins')
        cfg.pins = copy.deepcopy(context['pins'])
    source = synth.read_placement(str(input_board))
    if context is not None:
        outline = context.get('outline_mm') or []
        if (len(outline) != 2 or any(not isinstance(v, (int, float))
                or not math.isfinite(v) or v <= 0 for v in outline)
                or any(abs(a - b) > .01 for a, b in zip(outline, (source.W, source.H)))):
            raise ValueError('placement checkpoint outline disagrees with native geometry')
    cfg.params['selected_outline_mm'] = [source.W, source.H]
    anchors = _bind_outline_variant_interface_anchors(synth, cfg, source.W, source.H)
    from cec_outline_compaction import bind_required_positions
    positions = {ref: tuple(row[:3]) for ref, row in source.pos.items()}
    _positions, change_report = bind_required_positions(positions, cfg.pins)
    # A 360-degree spelling difference is not a changed mechanical pose.
    drift = [{'ref': ref, **row} for ref, row in change_report['changed'].items() if (
        abs(row['before'][0] - row['after'][0]) > 1e-5 or
        abs(row['before'][1] - row['after'][1]) > 1e-5 or
        abs((row['before'][2] - row['after'][2] + 180) % 360 - 180) > 1e-5)]
    if drift:
        error = PipelineBlocked('resumed placement violates required mechanical anchors; '
                                'explicit interface ECO/replacement required')
        error.failure_evidence = {'kind': 'resume_anchor_drift', 'drift': drift}
        raise error
    return {'declared_interface_refs': sorted(anchors), 'required_refs': sorted(cfg.pins),
            'outline_mm': [source.W, source.H], 'ok': True}


def _require_fixed_anchor_copper(cfg, board_path, *, evidence=None):
    """Refuse impossible locked-pad repair loops before spending craft budget."""
    import cec_placement_geometry
    if evidence is None:
        evidence = cec_placement_geometry.evaluate(board_path)
    fixed = cec_placement_geometry.fixed_pad_conflicts(evidence, cfg.pins or {})
    if not fixed['ok']:
        error = PipelineBlocked('fixed pad-copper conflict; footprint or joint interface ECO required')
        error.failure_evidence = {'kind': 'fixed_pad_copper_conflict',
                                  'physical_geometry': evidence, **fixed}
        raise error
    return fixed


def _retire_replaced_power_authority(cfg):
    """Replacement invalidates derived power state in every stage consumer.

    Clearing only candidate-local copies leaves final craft/priority checks
    reading the previous attempt's territory from the coordinator. Keep the
    electrical recipe, exact copper-prefix preservation and source files;
    retire only derived placement/pour bindings and rebuild them normally.
    """
    cfg.params = dict(cfg.params or {})
    keys = ("pourfirst_state", "pourfirst_outline_mm",
            "pourfirst_seen_placements", "pourfirst_avoid_boxes")
    return {key:cfg.params.pop(key) for key in keys if key in cfg.params}


def _placement_stage(cfg, input_board, output_board, *, replace, strategies,
                     seeds, workers, craft_trials, craft_rounds,
                     craft_epochs, completion_report=None,
                     candidate_review_only=False):
    import cec_synth_pipeline as synth
    import cec_search_policy
    import cec_outline_compaction
    from cec_fiducial_reuse import SameRunNoopReuse

    # A stage call belongs to exactly one coordinator invocation. Never keep
    # fiducial no-op evidence on cfg, in a module global, or in resume files.
    fiducial_reuse = SameRunNoopReuse()

    _bind_placement_worker_budget(cfg, workers)
    if candidate_review_only and not replace:
        raise ValueError("initial candidate review requires replacement placement")
    # Tracks on a placement artifact are not sufficient evidence that it is a
    # completed routed board: blueprint cells, force rails, local PI links,
    # and exact pour pickups are deliberately authored before the residual
    # router.  Only an input we explicitly preserved as routed suppresses the
    # placement-owned priority-route loop.  Digest-verified placement-stage
    # resumes may reconstruct placement, but must preserve existing locked
    # power-trunk geometry exactly. Constructor success is not that proof.
    preserved_routed_artifact = False
    power_prefix_owner = None
    retired_power = _retire_replaced_power_authority(cfg) if replace else {}

    output_board = Path(output_board).resolve()
    resume_provenance = None
    if not replace:
        resume_provenance = _placement_stage_artifact_provenance(input_board)
        _restore_placement_resume_context(synth, cfg, input_board, resume_provenance)
        if resume_provenance:
            _require_fixed_anchor_copper(cfg, input_board)
    checkpoint = None if candidate_review_only else _placement_checkpointer(
        cfg, input_board, output_board)
    if replace:
        cec_search_policy.bounded_placement_plan(strategies, seeds)
        source = synth.read_placement(
            str(input_board), allow_missing_outline=True)
        source, source_outline = _replacement_source_outline(cfg, source)
        outline_policy = dict(
            cfg.params.get("outline_compaction") or {})
        if source_outline.get("mode") == "declared_bootstrap":
            # There is no incumbent mechanical placement to preserve.  Trying
            # to rehydrate the outline-less staging cloud would both fail the
            # reader and give arbitrary source-sync coordinates design weight.
            # Fresh strategies still receive the complete current netlist and
            # every declared outline candidate.
            outline_policy["include_incremental"] = False
            outline_policy["include_fresh_placement"] = True
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
        generation_rejections = []
        outline_sizes = cec_outline_compaction.outline_candidates(
            source.W, source.H, outline_policy)
        if source_outline.get("mode") != "declared_bootstrap":
            from cec_outline_geometry import screen_rectangular_proposals
            outline_sizes, generation_rejections = screen_rectangular_proposals(
                input_board, outline_sizes)
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
            # Derived mechanical/interface anchors must live in the
            # coordinator-owned Config as well as the worker-local Config.
            # Bind after ordinary edge-follow transforms so the declaration's
            # target-outline geometry remains authoritative.
            _bind_outline_variant_interface_anchors(
                synth, variant, width, height)
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
                    # Mechanical ECOs can leave one member outside its
                    # declared rigid cell. Offer bounded whole-cell restores
                    # and contact reseats before freezing those members for
                    # local craft. These are extra candidates, not automatic
                    # corrections: the same native, stack and electrical
                    # shortlist gates adjudicate each one below.
                    if (variant.params.get('blueprint_cells')
                            and variant.params.get('placement_blueprint_restore', True)):
                        import cec_blueprint_placement
                        restored, restore_report = cec_blueprint_placement.restoration_candidates(
                            variant, incremental, max_candidates=int(variant.params.get(
                                'placement_blueprint_restore_candidates', 4)))
                        repack_follow['blueprint_restore'] = restore_report
                        for alternative in restored:
                            rows.append(alternative)
                            candidate_context[id(alternative)] = (variant, dict(
                                repack_follow, blueprint_restore=alternative.blueprint_restore))
            if outline_policy.get("include_fresh_placement", True):
                rows.extend(_fresh_outline_candidates(synth,
                    variant, width, height,
                    strategies=tuple(strategies), seeds=tuple(seeds),
                    workers=workers, rejections=generation_rejections,
                    checkpoint=checkpoint))
            candidates.extend(rows)
            for candidate in rows:
                candidate_context.setdefault(
                    id(candidate), (variant, follow))
        rejection_path = output_board.parent / "placement-search-rejections.json"
        atomic_json(rejection_path, {"schema": 1, "rejections": generation_rejections})
        if not candidates:
            raise PipelineBlocked("route-aware placement produced no candidates; see %s" % rejection_path)
        if not candidate_review_only:
            _require_placement_supply_inventory(candidates)
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
                        id(candidate)][0], checkpoint=checkpoint)
        # Cheap HPWL/congestion proxy ranking is a pruning signal, not an
        # electrical placement verdict.  Materialize every surviving candidate
        # and put the hard decoupler/stranded-part craft key ahead of the cheap
        # proxy.  This closes the old seam where the right algorithms ran but a
        # lower-HPWL board with failed bypass cells was selected anyway.
        selection_rows = []
        retained_candidates = {}
        selection_evaluation = None
        with tempfile.TemporaryDirectory(
                prefix="cec-full-placement-rank-") as work:
            jobs = []
            for index, candidate in enumerate(candidates):
                candidate_path = Path(work) / ("%03d.kicad_pcb" % index)
                variant_cfg, follow = candidate_context[id(candidate)]
                jobs.append({
                    "candidate": candidate,
                    "cfg": variant_cfg,
                    "path": str(candidate_path),
                    # Final candidate ranking retains the full diagnostic
                    # evidence used by the former serial implementation.
                    "relief_diagnostics": True,
                    "physical_evidence": True,
                })
            # Exact electrical and physical verdicts are independent by
            # candidate.  Reuse the bounded, recyclable spawn pool used by
            # craft repair so native KiCad allocations cannot accumulate in
            # the coordinator.  Results are returned in input order, keeping
            # deterministic ranking byte-for-byte independent of scheduling.
            evaluation_owner = copy.copy(cfg)
            evaluation_owner.params = dict(cfg.params)
            if workers is not None:
                evaluation_owner.params["placement_craft_eval_workers"] = \
                    max(1, int(workers))
            evaluated, selection_evaluation = \
                synth._evaluate_placement_craft_trials(
                    evaluation_owner, jobs)
            print("  [place] exact finalist evaluation: %d candidates, "
                  "%d workers, %d generations" % (
                      len(evaluated),
                      int(selection_evaluation.get("workers", 0) or 0),
                      int(selection_evaluation.get(
                          "worker_generations", 0) or 0)), flush=True)
            # Persist failed workers before TemporaryDirectory cleanup. A terse
            # exception alone discarded the causal stack on compact outlines.
            atomic_json(output_board.parent / "candidate-evaluation.json", {
                "schema": 1, "candidates": [{"index": index,
                    "outline_mm": [candidate.W, candidate.H],
                    "residual": candidate.residual, "result": result}
                    for index, (candidate, result) in enumerate(zip(candidates, evaluated))]})
            for index, (candidate, result) in enumerate(zip(
                    candidates, evaluated)):
                variant_cfg, follow = candidate_context[id(candidate)]
                if not result.get("ok"):
                    raise RuntimeError(
                        "exact placement candidate %d failed closed: %s" % (
                            index, result.get("error") or
                            "missing worker evidence"))
                evidence = result["evidence"]
                if candidate_review_only:
                    retained_candidates[index] = _retain_placement_candidate(
                        jobs[index]["path"], candidate, result, variant_cfg,
                        output_board.parent / "candidates" /
                        ("%03d" % index) / "board.kicad_pcb",
                        source_files=_source_files(variant_cfg, input_board))
                key = synth.placement_craft_key(evidence)
                pads = result["pads"]
                courtyards = result["courtyards"]
                physical_key = (
                    0 if pads.get("ok") else 1,
                    int(courtyards.get("violation_count", len(courtyards.get("violations") or ())))
                    or int(courtyards.get("ok") is False),
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
        if candidate_review_only:
            ordered = [retained_candidates[row[4]] for row in selection_rows]
            unique_poses = len({row["placement_signature"] for row in ordered})
            report_path = output_board.parent / "placement-candidates.json"
            report = {
                "schema": 1, "ok": True,
                "mode": "initial-placement-review",
                "source_outline": source_outline,
                "candidates": ordered,
                "generation_rejections": generation_rejections,
                "placement_diversity": {
                    "candidate_count": len(ordered),
                    "unique_pose_count": unique_poses,
                    "collapsed_count": len(ordered) - unique_poses,
                },
                "selection_evaluation": selection_evaluation,
                "routing_admitted": False, "release_accepted": False,
                "report": str(report_path),
                "_artifacts": [str(report_path), str(rejection_path)] + [
                    path for row in ordered for path in row["_artifacts"]],
            }
            atomic_json(report_path, report)
            return report
        # Save the actual selected PCB before entering another expensive
        # repair. A killed epoch must not destroy the best completed seed.
        synth.materialize(best, selected_cfg, str(output_board))
        _require_fixed_anchor_copper(selected_cfg, output_board)
        if checkpoint is not None:
            checkpoint(best, selected_cfg, output_board, phase='selected',
                       rank=synth._candidate_sort_key(best))
        best, repair = _repair_craft_with_search_history(
            selected_cfg, best, output_board, max_trials=int(craft_trials),
            rounds=int(craft_rounds), epochs=int(craft_epochs),
            initial_evidence=initial_craft,
            checkpoint=checkpoint,
        )
        synth.materialize(best, selected_cfg, str(output_board))
        copied = _copy_sidecars(
            output_board, output_board, cfg=selected_cfg)
        if checkpoint is not None:
            checkpoint(best, selected_cfg, output_board, phase='placement',
                       rank=synth._candidate_sort_key(best))
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
            "retired_power_authority": retired_power,
            "generation_rejections": generation_rejections,
            "source_outline": source_outline,
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
            "placement_journal": copy.deepcopy(getattr(best, "journal", [])),
            "cell_packing": copy.deepcopy(getattr(best, "cell_packing", {})),
            "supply_inventory": copy.deepcopy(getattr(best, "supply_inventory", {})),
            "joint_supply_groups": copy.deepcopy(getattr(best, "joint_supply_groups", [])),
            "orientation_admission": copy.deepcopy(getattr(best, "orientation_admission", {})),
            "critical_supply_groups": copy.deepcopy(getattr(best, "critical_supply_groups", [])),
            "proxy": best.proxy,
            "selection_craft_key": list(_craft_key),
            "selection_physical_key": list(_physical_key),
            "selected_outline_mm": [best.W, best.H],
            "selected_outline_area_mm2": round(best.W * best.H, 3),
            "outline_compaction": outline_follow,
            "selection_craft": initial_craft,
            "selection_evaluation": selection_evaluation,
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
        if checkpoint is not None and resume_provenance:
            checkpoint(synth.read_placement(str(output_board)), cfg,
                       output_board, phase='seed', rank=(0,),
                       observation={'resumed_from': str(input_board)})
        initial_craft = synth.placement_craft_evidence(
            str(output_board), cfg=cfg)
        frozen_before = _frozen_placement_contract(output_board)
        placement["frozen_placement_before"] = frozen_before
        optimize_clean_margin = bool(cfg.params.get(
            "placement_craft_optimize_clean_margin", True))
        import pcbnew
        _placement_board = pcbnew.LoadBoard(str(output_board))
        import cec_fr
        from types import SimpleNamespace
        import cec_placement_route_prefix
        power_prefix_owner = SimpleNamespace(
            protected_power_prefix=cec_placement_route_prefix.capture(output_board))
        routed_input = any(True for _item in _placement_board.GetTracks())
        resume_craft_policy = _initial_resume_craft_policy(
            initial_craft,cfg.params,resumed=bool(resume_provenance))
        placement['initial_resume_craft_policy'] = resume_craft_policy
        optimize_clean_margin = resume_craft_policy['optimize_clean_margin']
        if routed_input and resume_provenance:
            # Generated rails do not make this digest-verified checkpoint a
            # fully routed canonical board. Rehydration may repair placement,
            # but exact power-prefix guards reject any regenerated detour.
            routed_input = False
            placement["resume_provenance"] = resume_provenance
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
            preserved_routed_artifact = True
        elif frozen_before.get("applicable"):
            if frozen_before.get("ok") and resume_craft_policy['needs_repair']:
                # Repair only a current hard craft blocker; clean-margin
                # optimization alone never perturbs a frozen placement.
                candidate = synth.placement_candidate_from_board(
                    cfg, str(output_board),
                    allow_routed=bool(resume_provenance))
                import cec_frozen_placement_domain
                candidate.frozen_placement_contract = cec_frozen_placement_domain.bind(
                    output_board, candidate)
                candidate, repair = _repair_craft_with_search_history(
                    cfg, candidate, output_board, max_trials=int(craft_trials),
                    rounds=int(craft_rounds), epochs=int(craft_epochs),
                    initial_evidence=initial_craft, checkpoint=checkpoint)
                repair = _commit_craft_reconstruction(cfg, candidate, output_board, repair)
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
        elif resume_craft_policy['needs_repair'] or optimize_clean_margin:
            candidate = synth.placement_candidate_from_board(
                cfg, str(output_board),
                allow_routed=bool(resume_provenance))
            candidate, repair = _repair_craft_with_search_history(
                cfg, candidate, output_board, max_trials=int(craft_trials),
                rounds=int(craft_rounds), epochs=int(craft_epochs),
                initial_evidence=initial_craft, checkpoint=checkpoint)
            # A verified no-op must be byte-preserving.  ``materialize`` is a
            # placement reconstruction tool, not a serializer: invoking it for
            # an unchanged candidate can legitimately rebuild copper/zones and
            # used to turn an already clean board into an unrouted one.  Only a
            # independently admitted composed delta owns that rewrite. A
            # footprint move cannot bypass the rebuilt-copper regression guard.
            repair = _commit_craft_reconstruction(cfg, candidate, output_board, repair)
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
        profile_declaration = _declare_fabrication_profile_isolated(
            output_board, profile_name)

    reconsider_fiducials = _placement_fiducials_reconsiderable(
        output_board, replace=replace or bool(placement.get("resume_provenance")))
    fiducial_repair = _transactional_fiducial_edge_repair(
        cfg, output_board, reconsider_all=reconsider_fiducials,
        reuse=fiducial_reuse)
    placement["fiducial_edge_repair"] = fiducial_repair
    if not fiducial_repair.get("ok"):
        placement["fiducial_edge_repair_blocked"] = True
    post_fiducial_craft_repair = _bounded_post_fiducial_craft_repair(
        cfg, output_board, fiducial_repair,
        max_trials=int(craft_trials), rounds=int(craft_rounds),
        epochs=int(craft_epochs),
        allow_authored_prefix=not preserved_routed_artifact)
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

    def measure_physical():
        measured = _measure_placement_physical(cfg, output_board)
        pads_now = measured["pads_in_bounds"]
        courtyards_now = measured["courtyards"]
        craft_now = measured["craft"]
        routed_now = bool(preserved_routed_artifact)
        # This stage is always followed by the bounded priority/local-route
        # repair transaction.  Allow only the classifier's explicitly named
        # copper-completion deferrals; it continues to reject missing/distant
        # capacitors and every non-route-owned craft failure.
        craft_gate_now = measured["craft_gate"]
        constraints_now = measured["constraint_gate"]
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
    authored_prefix_checkpoint = None

    def checkpoint_authored_prefix():
        nonlocal authored_prefix_checkpoint
        if preserved_routed_artifact:
            return None
        if power_prefix_owner is not None:
            # Never certify a rebuilt/detoured bus as the next resume's new
            # authority, even when an intermediate placement gate failed.
            synth._admit_materialized_power_prefix(
                power_prefix_owner, output_board)
        authored_prefix_checkpoint = \
            _write_placement_authored_prefix_checkpoint(output_board)
        return authored_prefix_checkpoint

    power_terminal_calls = 0

    def ensure_authority():
        nonlocal power_terminal_calls
        import cec_power_failure
        try:
            result = _ensure_placement_route_authority(
                cfg, output_board,
                allow_authored_prefix=not preserved_routed_artifact)
        except Exception as exc:                         # noqa: BLE001
            result = {
                "schema": 1, "ok": False, "applicable": True,
                "reason": "exact_route_authority_exception",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "operation_failure": dict(getattr(exc, 'failure_evidence', {}) or {}),
                "_artifacts": [],
            }
        if (cec_power_failure.bridge_failure(result)
                and power_terminal_calls < max(0, int(cfg.params.get(
                    "power_terminal_repair_calls", 1)))):
            power_terminal_calls += 1
            try:
                repair = _repair_failed_power_bridge_placement(
                    cfg, output_board, result,
                    allow_authored_prefix=not preserved_routed_artifact)
            except Exception as exc:                     # noqa: BLE001
                repair = {"ok": False, "changed": False,
                          "reason": "power_terminal_operation_failed",
                          "error": "%s: %s" % (type(exc).__name__, exc)}
            placement["power_terminal_repair"] = repair
            placement.setdefault("power_terminal_repairs", []).append(repair)
            if repair.get("changed"):
                result = _ensure_placement_route_authority(
                    cfg, output_board,
                    allow_authored_prefix=not preserved_routed_artifact)
        authority_artifacts.extend(result.get("_artifacts") or ())
        return result

    route_authority = (ensure_authority()
                       if pre_route_physical_ok else {
                           "schema": 1, "ok": False, "applicable": True,
                           "reason": "placement_not_admitted",
                           "_artifacts": [],
                       })
    # A failed legacy force-rail constructor must not suppress the exact
    # planner's causal evidence. Probe only a private copy; retain the failed
    # placement and authority gates even when that diagnostic finds a path.
    import cec_power_failure
    if cec_power_failure.construction_probe_eligible(
            craft, craft_gate, requires_authority=_requires_frozen_route_authority(cfg),
            routed=preserved_routed_artifact,
            physical_gates=[pads.get('ok'), courtyards.get('ok'),
                placement_constraints.get('ok'), fiducial_repair.get('ok'),
                service_repair.get('ok')]):
        placement['power_construction_diagnostic'] = _diagnose_power_construction(
            cfg, output_board)
    post_authority_craft_repair = {
        "schema": 1, "ok": True, "changed": False,
        "applicable": False, "reason": "no_frozen_power_authority",
        "bounded_cooptimization": True, "passes": [],
    }
    power_placement_pass_limit = min(4, max(1, int(cfg.params.get(
        "placement_power_cooptimization_passes", 3) or 3)))
    if route_authority.get("state"):
        post_authority_craft_repair['reason'] = 'no_power_dependent_placement_repair'
        # Power-dependent craft (especially body-vs-pour clearance) becomes
        # meaningful only after an exact authority exists. Always remeasure;
        # limiting this to a power-solver placement move let a newly generated
        # state bypass its own placement contract.
        (pads, courtyards, craft, routed_output, craft_gate,
         placement_constraints,
         pre_route_physical_ok) = measure_physical()
        route_authority["post_authority_physical_ok"] = bool(
            pre_route_physical_ok)
        # A fresh exact pour can avoid the first body by exposing a different
        # legal corridor that meets another body.  Treating the repair/replan
        # boundary as one-shot made each individually correct stage hand the
        # next stage a new blocker.  Iterate a *small fixed number* of times,
        # with the existing complete-craft repair remaining monotonic inside
        # every pass.  Clean admission, a no-op/plateau, or the hard pass limit
        # terminates the loop and leaves its full causal certificate.
        power_placement_passes = []
        any_power_placement_change = False
        for pass_index in range(power_placement_pass_limit):
            eligible = bool(
                not pre_route_physical_ok
                and pads.get("ok") and courtyards.get("ok")
                and placement_constraints.get("ok")
                and _post_authority_craft_dependencies(craft))
            if not eligible:
                break
            before_joint = copy.deepcopy(dict(authority=route_authority,
                physical=(pads,courtyards,craft,routed_output,craft_gate,
                          placement_constraints,pre_route_physical_ok),
                profile=profile_declaration,fiducial=fiducial_repair,service=service_repair))

            def rebuild_joint():
                nonlocal profile_declaration,fiducial_repair,service_repair
                if profile_name:
                    profile_declaration = _declare_fabrication_profile_isolated(
                        output_board, profile_name)
                fiducial_repair = _transactional_fiducial_edge_repair(
                    cfg, output_board, reconsider_all=False,
                    reuse=fiducial_reuse)
                if service_clearance_mm > 0.0:
                    service_repair = synth.repair_service_connectors_away_from_interfaces(
                        str(output_board),clearance_mm=service_clearance_mm,
                        edge_detect_mm=float(cfg.params.get('service_interface_edge_detect_mm',6.0) or 6.0),
                        max_shift_mm=float(cfg.params.get('service_interface_max_shift_mm',8.0) or 8.0))
                authority = ensure_authority()
                physical = measure_physical()
                authority['post_authority_physical_ok'] = bool(physical[6])
                return dict(authority=authority,physical=physical,profile=profile_declaration,
                            fiducial=fiducial_repair,service=service_repair)

            one_pass, chosen_joint = _transactional_power_placement_trial(
                cfg, output_board, before_joint,
                lambda: _bounded_post_authority_craft_repair(
                    cfg, output_board, craft,max_trials=int(craft_trials),
                    rounds=int(craft_rounds),epochs=int(craft_epochs),
                    allow_authored_prefix=not preserved_routed_artifact),
                rebuild_joint)
            route_authority = chosen_joint['authority']
            (pads,courtyards,craft,routed_output,craft_gate,
             placement_constraints,pre_route_physical_ok) = chosen_joint['physical']
            profile_declaration=chosen_joint['profile']
            fiducial_repair=chosen_joint['fiducial']
            service_repair=chosen_joint['service']
            placement['fiducial_edge_repair']=fiducial_repair
            placement['service_interface_repair']=service_repair
            one_pass = dict(one_pass)
            one_pass["pass"] = pass_index + 1
            power_placement_passes.append(one_pass)
            if not one_pass.get("changed"):
                break
            any_power_placement_change = True
        if power_placement_passes:
            post_authority_craft_repair = dict(
                power_placement_passes[-1])
            post_authority_craft_repair.update({
                "schema": 1,
                "bounded_cooptimization": True,
                "pass_limit": power_placement_pass_limit,
                "passes_run": len(power_placement_passes),
                "passes": power_placement_passes,
                "changed": any_power_placement_change,
                "ok": bool(pre_route_physical_ok),
                "stop_reason": (
                    "gate_clean" if pre_route_physical_ok else
                    "joint_regression_rejected" if power_placement_passes[-1].get('rolled_back') else
                    "plateau" if not power_placement_passes[-1].get(
                        "changed") else
                    "pass_budget_exhausted"),
            })
    placement["post_authority_craft_repair"] = \
        post_authority_craft_repair
    priority_applicable = _placement_priority_probe_required(
        cfg, output_board, preserved_routed=routed_output)
    priority_repair = {
        "schema": 1, "ok": True, "changed": False,
        "applicable": priority_applicable,
        "reason": ("not_run" if priority_applicable else
                   "no_priority_route_placement_policy"),
    }
    priority_evidence = {}
    priority_baseline_gate = {}
    preserve_admitted_placement = False
    partial_prefix_retained = False
    import cec_power_failure
    unresolved_power_bridge = bool(cec_power_failure.bridge_failure(route_authority))
    if unresolved_power_bridge:
        priority_evidence = {"error": "power_bridge_dependency_unresolved",
                             "power_failure": cec_power_failure.bridge_failure(route_authority)}
        priority_repair.update({"ok": False, "reason": "power_bridge_dependency_unresolved"})
    if pre_route_physical_ok and priority_applicable and not unresolved_power_bridge:
        import cec_route_preflight

        # A certified placement is a stable pipeline boundary.  Re-running
        # placement must not rotate or translate otherwise legal parts merely
        # to improve a secondary congestion score: that invalidates the exact
        # route certificate consumed by the next stage and makes resume
        # nondeterministic.  Boards that explicitly want post-admission
        # optimization can opt in; the generic default is byte-stable reuse.
        checkpoint_authored_prefix()
        priority_evidence = _measure_placement_priority_routes(
            cfg, output_board,
            allow_unbound_power_authority=
                not bool(route_authority.get("ok")),
            allow_authored_prefix=True)
        priority_baseline_gate = _placement_priority_route_gate(
            priority_evidence, applicable=True)
        native_escape = _placement_native_route_escape(cfg,output_board,priority_evidence)
        placement['native_route_recovery'] = native_escape
        authority_artifacts.extend(native_escape.get('_artifacts') or ())
        if native_escape.get('changed'):
            route_authority = native_escape['route_authority']
            priority_evidence = native_escape['priority_evidence']
            priority_baseline_gate = native_escape['priority_gate']
            checkpoint_authored_prefix()
            (pads,courtyards,craft,routed_output,craft_gate,
             placement_constraints,pre_route_physical_ok) = measure_physical()
        import cec_priority_recovery
        if (int(cfg.params.get('priority_recovery_waves', 2)) > 0
                and cec_priority_recovery.recovery_eligible(priority_evidence,
                    physical_ok=pre_route_physical_ok,
                    authority_ok=route_authority.get('ok'))):
            recovery = _recover_placement_priority_routes(cfg, output_board)
            placement['priority_routing_recovery'] = recovery
            if recovery.get('changed'):
                partial_prefix_retained = bool(recovery.get('partial_retained'))
                if partial_prefix_retained:
                    checkpoint_authored_prefix()
                    priority_evidence = _measure_placement_priority_routes(
                        cfg, output_board, allow_authored_prefix=True)
                    priority_baseline_gate = _placement_priority_route_gate(priority_evidence)
                else:
                    admitted = next(row for row in recovery['waves'] if row.get('ok'))
                    priority_evidence = admitted['priority_evidence']
                    priority_baseline_gate = admitted['priority_gate']
                (pads, courtyards, craft, routed_output, craft_gate,
                 placement_constraints, pre_route_physical_ok) = measure_physical()
        preserve_admitted_placement = bool(
            pre_route_physical_ok and route_authority.get("ok")
            and _preserve_admitted_priority_placement(
                cfg, priority_baseline_gate))
    if preserve_admitted_placement:
        stable_key = tuple(
            cec_route_preflight.placement_evidence_key(priority_evidence))
        priority_repair = {
            "schema": 2,
            "ok": True,
            "changed": False,
            "accepted_count": 0,
            "applicable": True,
            "reason": "already_feasible_stable",
            "baseline_key": list(stable_key),
            "result_key": list(stable_key),
            "result_evidence": priority_evidence,
            "cooptimization": {
                "schema": 1,
                "rounds_requested": max(1, int(cfg.params.get(
                    "placement_power_route_coopt_rounds", 3) or 3)),
                "rounds_run": 0,
                "selected_round": 0,
                "selected_key": list(stable_key),
                "stop_reason": "already_feasible_stable",
                "repetition_guard": True,
                "strict_post_authority_selection": True,
            },
        }
    elif partial_prefix_retained:
        # Keep a productive routing boundary. Do not run a placement ECO that
        # would invalidate newly qualified copper in the very same pass.
        # The unchanged full priority gate still blocks residual routing.
        priority_repair = {
            'schema': 2, 'ok': False, 'changed': True, 'accepted_count': 0,
            'reason': 'critical_prefix_retained_pending_remaining_pairs',
            'result_evidence': priority_evidence,
            'result_key': list(cec_route_preflight.placement_evidence_key(priority_evidence)),
            'residual_allowed': False,
        }
    elif pre_route_physical_ok and priority_applicable and not unresolved_power_bridge:
        # Placement and exact pours are mutually dependent.  A placement move
        # can clear a declared pair against the old reservations and then lose
        # it when the power authority is regenerated for the new coordinates.
        # Iterate that boundary transactionally: every provisional move earns
        # a fresh exact power freeze and exact critical-route measurement.
        # Keep the best *post-authority* state, and bound/repetition-guard the
        # search so unattended waves cannot oscillate.
        coopt_rounds = max(1, int(cfg.params.get(
            "placement_power_route_coopt_rounds", 3) or 3))
        coopt_history = []
        best_key = tuple(cec_route_preflight.placement_evidence_key(priority_evidence))
        best_evidence = priority_evidence or None
        best_authority = dict(route_authority)
        best_repair = None
        best_fiducial_repair = dict(fiducial_repair)
        best_service_repair = dict(service_repair)
        best_profile_declaration = profile_declaration
        best_round = 0
        selected_snapshot = None
        seen_placements = {_placement_position_signature(output_board)}
        rejected_route_moves = set()
        stop_reason = "round_limit"
        repair_error = None
        import cec_operation_budget
        coopt_budget_checks = []
        previous_round_start = None
        with tempfile.TemporaryDirectory(
                prefix="cec-placement-power-route-coopt-") as scratch:
            scratch = Path(scratch)
            baseline_snapshot = scratch / "round-00"
            _snapshot_placement_authority(output_board, baseline_snapshot)
            selected_snapshot = baseline_snapshot

            with cec_operation_budget.finalization_reserve(float(cfg.params.get(
                    'placement_coopt_finish_reserve_s', 120.))) as coopt_finalization_budget:
                for outer_round in range(1, coopt_rounds + 1):
                    # The nested repair has its own budget, but this outer loop
                    # also pays for power, physical and full priority admission.
                    # Reserve final selection/publication before another round.
                    budget = cec_operation_budget.round_admission(
                        None if previous_round_start is None else
                        time.monotonic() - previous_round_start,
                        reserve_s=0.)  # Already reserved by the enclosing lease.
                    coopt_budget_checks.append(dict(budget, round=outer_round))
                    if not budget['start']:
                        stop_reason = 'cooptimization_budget_reserved'
                        break
                    previous_round_start = time.monotonic()
                    round_input_snapshot = scratch / (
                        "round-%02d-input" % outer_round)
                    _snapshot_placement_authority(
                        output_board, round_input_snapshot)
                    repair_cfg = copy.deepcopy(cfg)
                    repair_cfg.params[
                        "placement_route_excluded_move_signatures"] = sorted(
                            rejected_route_moves)
                    current_repair = _priority_cooptimization_attempt(
                        cfg, repair_cfg, output_board,
                        completion_report=completion_report,
                        baseline_evidence=priority_evidence,
                        allow_authored_prefix=not preserved_routed_artifact,
                        allow_unbound_power_authority=
                            not bool(route_authority.get("ok")))
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
                        "operation_failure": (current_repair.get('operation_evidence')
                            if not current_repair.get('ok') else None),
                        "baseline_reuse": current_repair.get('baseline_reuse'),
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
                            checkpoint_authored_prefix()
                            measured = _measure_placement_priority_routes(
                                cfg, output_board,
                                allow_authored_prefix=True)
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
                        profile_declaration = \
                            _declare_fabrication_profile_isolated(
                                output_board, profile_name)
                    fiducial_repair = _transactional_fiducial_edge_repair(
                        cfg, output_board,
                        reconsider_all=_placement_fiducials_reconsiderable(
                            output_board, replace=replace), reuse=fiducial_reuse)
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
                    # Craft measured against the old state cannot certify newly
                    # frozen reservations, even when ensure_authority leaves the
                    # PCB bytes unchanged. Include that dependency in the same
                    # rollback/exclusion transaction as a failed power solve.
                    route_authority, physical, boundary = \
                        _placement_authority_physical_boundary(
                            measure_physical(), ensure_authority, measure_physical)
                    (pads, courtyards, craft, routed_output, craft_gate,
                     placement_constraints, pre_route_physical_ok) = physical
                    row["post_authority_physical_certificate"] = boundary
                    row["physical_ok"] = bool(pre_route_physical_ok)
                    row["route_authority_ok"] = bool(
                        route_authority.get("ok"))
                    row["route_authority_reason"] = route_authority.get(
                        "reason")
                    if (not pre_route_physical_ok
                            or not route_authority.get("ok")):
                        # Preserve the actual post-move authority failure, not
                        # merely its wrapper reason.  This is the dependency edge
                        # between placement and exact filled power; without the
                        # admission/local-pin/planner stack an unattended run can
                        # only rediscover the same rejected move on its next wave.
                        row["route_authority_failure"] = {
                            key: route_authority.get(key) for key in (
                                "reason", "placement_changed",
                                "placement_delta", "reused", "planner",
                                "exact_admission", "operation_failure")
                            if route_authority.get(key) is not None
                        }
                        accepted_moves = [
                            round_row.get("move") or {}
                            for round_row in (
                                current_repair.get("rounds") or ())
                            if round_row.get("accepted")
                        ]
                        rejected_signature = None
                        if accepted_moves:
                            rejected_signature = (
                                accepted_moves[0].get("move_signature")
                                or synth.route_repair_move_signature(
                                    accepted_moves[0]))
                        can_retry = bool(
                            rejected_signature
                            and rejected_signature not in rejected_route_moves
                            and outer_round < coopt_rounds
                            and not cec_power_failure.bridge_failure(route_authority))
                        if can_retry:
                            rejected_route_moves.add(rejected_signature)
                            row.update({
                                "stop": "post_move_authority_refused_retry",
                                "rejected_move_signature": rejected_signature,
                                "excluded_move_count_next_round": len(
                                    rejected_route_moves),
                            })
                            coopt_history.append(row)
                            # The rejected placement and its freshly generated
                            # power artifacts are one transaction. Restore the
                            # exact input family before asking the bounded placer
                            # for an alternate first branch.
                            _restore_placement_authority(
                                output_board, round_input_snapshot)
                            stop_reason = (
                                "post_move_authority_refused_retry")
                            continue
                        row.update({
                            "stop": "post_move_authority_refused",
                            "rejected_move_signature": rejected_signature,
                            "excluded_move_count": len(rejected_route_moves),
                        })
                        coopt_history.append(row)
                        stop_reason = "post_move_authority_refused"
                        break

                    checkpoint_authored_prefix()
                    measured = _measure_placement_priority_routes(
                        cfg, output_board,
                        allow_authored_prefix=True)
                    priority_evidence = measured
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
                        if checkpoint is not None:
                            row['durable_checkpoint'] = checkpoint(
                                synth.read_placement(str(output_board)), cfg, output_board,
                                phase='priority', rank=list(measured_key),
                                observation={'round': outer_round,
                                    'physical_ok': bool(pre_route_physical_ok),
                                    'route_authority_ok': bool(route_authority.get('ok')),
                                    'priority_gate': measured_gate,
                                    'release_authority': False})
                    if measured_gate.get("ok"):
                        stop_reason = "important_routes_feasible"
                        break
                    if repeated:
                        stop_reason = "repeated_placement"
                        break
                    seen_placements.add(signature)
                else:
                    stop_reason = "round_limit"
            if coopt_finalization_budget['budget_exhausted']:
                stop_reason = 'cooptimization_finalization_budget_reserved'
                coopt_history.append({'round': outer_round, 'stop': stop_reason,
                    'attempt_complete': False,
                    'operation_failure': coopt_finalization_budget['operation_failure']})
            # Restore the best completely measured composition, never the
            # interrupted power/placement half-transaction.
            _restore_placement_authority(output_board, selected_snapshot)

        # The selected snapshot already contains its matching exact authority;
        # remeasure cheap physical gates after rollback/selection and reuse its
        # recorded authority rather than rebuilding the pours a second time.
        # Discard artifact paths accumulated by losing co-optimization rounds:
        # restoring the selected authority intentionally removes files that
        # those trials generated, and journaling such a dead path would turn a
        # valid bounded rollback into a spurious missing-artifact crash.
        fiducial_repair = best_fiducial_repair
        service_repair = best_service_repair
        profile_declaration = best_profile_declaration
        placement["fiducial_edge_repair"] = fiducial_repair
        placement["service_interface_repair"] = service_repair
        (pads, courtyards, craft, routed_output, craft_gate,
         placement_constraints,
         pre_route_physical_ok) = measure_physical()
        route_authority = best_authority
        authority_artifacts = list(
            route_authority.get("_artifacts") or ())
        if best_evidence is None:
            checkpoint_authored_prefix()
            best_evidence = _measure_placement_priority_routes(
                cfg, output_board,
                allow_authored_prefix=True)
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
                "round_budget_checks": coopt_budget_checks,
                "finalization_budget": coopt_finalization_budget,
                "selected_round": best_round,
                "selected_key": list(best_key or ()),
                "stop_reason": stop_reason,
                "repetition_guard": True,
                "strict_post_authority_selection": True,
                "rejected_route_move_count": len(rejected_route_moves),
                "history": coopt_history,
            },
        })
    # Optical datums own the final placement move, after exact power and the
    # priority-route co-optimizer have selected their board.  The late pass is
    # itself an exact transaction: a mark that would force a pour rebuild or a
    # critical-route regression is rolled back with the entire authority.
    if pre_route_physical_ok and route_authority.get("ok"):
        late_fiducials = _budgeted_late_fiducial_finalization(
            cfg, output_board, priority_applicable=priority_applicable,
            allow_authored_prefix=not preserved_routed_artifact,
            fiducial_reuse=fiducial_reuse)
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
    if not priority_applicable and not routed_output:
        priority_gate["reason"] = "no_derived_or_declared_priority_routes"
    if not priority_repair.get("ok") and priority_applicable:
        priority_gate = {
            "schema": 1, "ok": False, "applicable": True,
            "reason": "priority_route_repair_error",
            "blockers": [{"term": "repair", "count": 1,
                          "detail": priority_repair.get("reason")}],
        }
    frozen_after = _frozen_placement_contract(output_board)
    power_prefix_gate = (synth._admit_materialized_power_prefix(
        power_prefix_owner, output_board) if power_prefix_owner is not None
        else {"schema": 1, "ok": True, "applicable": False})
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
        "protected_power_prefix": power_prefix_gate,
        "fabrication_profile": profile_declaration,
        "route_authority": {
            key: value for key, value in route_authority.items()
            if key != "_artifacts"},
        "ok": physical_ok,
    })
    report = output_board.with_suffix(".placement.json")
    atomic_json(report, placement)
    if not preserved_routed_artifact:
        checkpoint_authored_prefix()
    placement["_artifacts"] = list(dict.fromkeys(
        copied + authority_artifacts
        + [str(report)]
        + ([authored_prefix_checkpoint]
           if authored_prefix_checkpoint else [])))
    placement["report"] = str(report)
    return placement


def _preflight_stage(board, output_dir, cfg, *, grid_mm, iterations, backend,
                     constructive_nets=()):
    import cec_route_preflight
    import cec_synth_pipeline as synth
    import cec_preflight_native_recovery as native
    import cec_operation_budget as operation

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    heatmap = output_dir / "congestion.png"
    report_path = output_dir / "preflight.json"
    incoming_board = Path(board).resolve()
    incoming_sha = sha256_file(incoming_board)
    routing_board = incoming_board
    artifacts = []
    # Compile the exact same profile/pour/critical route environment used by
    # detailed routing. A preflight without those reservations is a different
    # board and cannot admit production work.
    with synth._oracle_env(_route_params_for_board(cfg, board)):
        report = None
        if not constructive_nets:
            report = cec_route_preflight.analyze_multiresolution(
                str(board), grid_mm=float(grid_mm), iters=int(iterations),
                backend=backend, heatmap_path=str(heatmap),
                board_hint=cfg.board, run_future_congestion=True)
        # Earlier placement prediction can already supply explicit failed
        # obligations. They select construction only, never substitute a gate
        # or fabricate a preflight report. Always predict the complete saved
        # workload after this one bounded native attempt.
        names = tuple(constructive_nets) if constructive_nets else native.targets(report)
        if names and cfg.params.get('preflight_native_recovery', True):
            if report is not None:
                atomic_json(output_dir / 'preflight-before-native.json', report)
                artifacts.append(str(output_dir / 'preflight-before-native.json'))
            policy = dict(wall_s=cfg.params.get('preflight_native_wall_s',90.),
                max_span_mm=cfg.params.get('preflight_native_max_span_mm',50.),
                attempts_per_pair=cfg.params.get('preflight_native_attempts_per_pair',8))
            identity = digest_value(dict(source=incoming_sha, policy=policy,nets=sorted(names),
                authority=native.authority_signature(incoming_board)['sha256'],
                board=cfg.board, code=_code_closure_signature(
                    'cec_preflight_native_recovery.py')))[:16]
            directory = output_dir / ('native-recovery-' + identity)
            native_report = directory / 'report.json'
            recovery = None
            if native_report.is_file():
                # An unchanged refused attempt must not be rerun every wave.
                # A successful cached prefix is usable only while all signed
                # PCB, project, rule and copper authorities still match.
                from cec_board_suite import signature_unchanged
                cached = json.loads(native_report.read_text())
                if (cached.get('source_sha256') == incoming_sha
                        and cached.get('nets') == sorted(names)
                        and cached.get('source_unchanged')
                        and cached.get('policy') == policy
                        and cached.get('artifact_signature')
                        and signature_unchanged(cached['artifact_signature'])):
                    recovery = cached
                else:
                    recovery = dict(ok=False,reason='native_recovery_cache_identity_changed')
            else:
                command = [sys.executable, str(HERE/'cec_preflight_native_recovery.py'),
                    '--source',str(incoming_board),'--out',str(directory),
                    '--nets-json',json.dumps(names),'--board-hint',cfg.board,
                    '--wall-s',str(policy['wall_s']),
                    '--max-span-mm',str(policy['max_span_mm']),
                    '--attempts-per-pair',str(policy['attempts_per_pair'])]
                native_operation_failure = None
                try:
                    operation.run(command, output_dir/('native-worker-'+identity),
                        operation='preflight-native-obligation',
                        timeout=min(390.,float(policy['wall_s'])+90.))
                except operation.OperationFailure as exc:
                    native_operation_failure = exc.failure_evidence
                    recovery = dict(ok=False, operation_failure=native_operation_failure)
                if native_report.is_file():
                    recovery = json.loads(native_report.read_text())
                    if native_operation_failure:
                        recovery = dict(recovery, ok=False,
                            operation_failure=native_operation_failure,
                            operation_receipt_refused=True)
            recovery = recovery or dict(ok=False,reason='native_recovery_no_receipt')
            if native_report.is_file():
                artifacts.append(str(native_report))
            signed = recovery.get('artifact_signature') or {}
            artifacts.extend(str((ROOT/row['path']).resolve())
                             for row in signed.get('files') or ())
            if recovery.get('ok') and native.admitted(recovery.get('terms') or {}):
                from cec_board_suite import signature_unchanged
                child = Path(recovery.get('board') or '').resolve()
                if (child.is_relative_to(directory.resolve()) and child.is_file()
                        and sha256_file(child) == recovery.get('proposal_sha256')
                        and signed and signature_unchanged(signed)
                        and sha256_file(incoming_board) == incoming_sha):
                    routing_board = child
                    # Native closure earns another complete global prediction;
                    # it is never a reason to flip or bypass the original gate.
                    report = cec_route_preflight.analyze_multiresolution(
                        str(child), grid_mm=float(grid_mm), iters=int(iterations),
                        backend=backend, heatmap_path=str(heatmap),
                        board_hint=cfg.board, run_future_congestion=True)
                else:
                    recovery = dict(recovery, ok=False,
                        reason='native_prefix_identity_changed_before_preflight')
            if report is None:
                report = cec_route_preflight.analyze_multiresolution(
                    str(routing_board), grid_mm=float(grid_mm), iters=int(iterations),
                    backend=backend, heatmap_path=str(heatmap),
                    board_hint=cfg.board, run_future_congestion=True)
            report['native_recovery'] = dict(recovery, report=str(native_report))
        if report is None:
            report = cec_route_preflight.analyze_multiresolution(
                str(routing_board), grid_mm=float(grid_mm), iters=int(iterations),
                backend=backend, heatmap_path=str(heatmap),
                board_hint=cfg.board, run_future_congestion=True)
    if sha256_file(incoming_board) != incoming_sha:
        report.update(gate=False,error='preflight mutated immutable incoming board')
    report['incoming_board_sha256'] = incoming_sha
    report['routing_board_sha256'] = sha256_file(routing_board)
    atomic_json(report_path, report)
    compact = cec_route_preflight.compact_placement_evidence(report)
    return {
        "ok": not bool(report.get("error")),
        "admission_gate": bool(report.get("gate")),
        "report": str(report_path),
        "heatmap": str(heatmap) if heatmap.is_file() else None,
        "summary": compact,
        "board": str(routing_board),
        "_artifacts": [str(report_path)] + (
            [str(heatmap)] if heatmap.is_file() else []
        ) + [str(routing_board)] + artifacts,
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
    import cec_route_checkpoint

    route_cfg = synth.Config.load(
        payload["board_name"], params=dict(payload["params"]))
    # Source selection is effective configuration, not a Config.load default.
    # Preserve explicit absence (notably net=None) just like native operations.
    for key in ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv'):
        if key in (payload.get('config') or {}):
            setattr(route_cfg, key, payload['config'][key])
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
            checkpoint=(cec_route_checkpoint.publisher(
                payload['checkpoint_dir'], route_cfg, payload['board'], payload['seed'])
                if payload.get('checkpoint_dir') else None),
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
        "candidate_origin": row.get("candidate_origin", "proposal"),
        "artifact": row.get("routed"),
        "failure_artifact": row.get("failure_artifact"),
        "failure_stage": failed_stage,
        "rank": list(cec_search_policy.candidate_rank(row)),
        "sort_key": row.get("sort_key"), "drc": row.get("drc"),
        "unconnected": row.get("unconnected"),
        "unconn_critical": row.get("unconn_critical"),
        "vias": row.get("vias"), "length": row.get("length"),
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
        "route_checkpoint": row.get("route_checkpoint"),
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


def _route_candidate_cohorts(pool, payloads, workers, *, watchdog_s,
                             reserve_s, results, evidence, active):
    """Dispatch only funded route cohorts, keeping completed candidates.

    Queueing every seed up front let a second multi-minute route start after
    the first had consumed almost the whole campaign. The measured cohort cost
    is a scheduling estimate, never a relaxed physical gate or solver proof.
    The existing process watchdog remains the hard backstop.
    """
    import cec_operation_budget
    import cec_process_pool
    observed_s = None
    generation_started = time.monotonic()
    cohorts = evidence.setdefault('cohorts', [])
    for offset in range(0, len(payloads), workers):
        # The watchdog covers the whole generation, not a renewable lease for
        # each cohort, even for standalone callers without a campaign deadline.
        watchdog_remaining = watchdog_s - (time.monotonic()-generation_started)
        if watchdog_remaining <= 0:
            evidence.update(status='budget_deferred',
                deferred_seeds=[p['seed'] for p in payloads[offset:]],
                next_cohort_budget={'start':False,
                                    'reason':'generation_watchdog_exhausted'})
            return
        plan = cec_operation_budget.generation_admission(
            watchdog_remaining, observed_s, reserve_s=reserve_s)
        if not plan['start']:
            evidence.update(status='budget_deferred',
                deferred_seeds=[p['seed'] for p in payloads[offset:]],
                next_cohort_budget=plan)
            return
        batch = payloads[offset:offset+workers]
        active.clear()
        active.update({pool.submit(_route_candidate_worker, payload):payload
                       for payload in batch})
        started = time.monotonic()
        for future in cec_process_pool.watched_as_completed(
                pool, active, wall_timeout_s=plan['timeout_s'], poll_s=5.0):
            payload = active[future]
            try:
                results.append(future.result())
            except Exception as exc:                         # noqa: BLE001
                results.append({
                    'seed':payload['seed'], 'gate':False,
                    'routed':None, 'drc':None, 'unconnected':None,
                    'sort_key':[1,99,99,99],
                    'worker_error':'%s: %s' % (type(exc).__name__, exc),
                })
        elapsed = time.monotonic()-started
        observed_s = max(observed_s or 0., elapsed)
        cohorts.append({'seeds':[p['seed'] for p in batch],
                        'elapsed_s':round(elapsed,6), 'budget':plan})


def _grade_route_incumbent(board, output_dir, cfg, *, seed, thermal):
    """Freshly grade an immutable staged copy under this run's route authority.

    A stored prior oracle is not current evidence. This adds no router trial,
    accepts no placement-only board as a route, and never polishes the input.
    Missing/changed evidence aborts selection rather than silently dropping the
    baseline. The normal independent signoff still owns release authority.
    """
    import cec_synth_pipeline as synth

    source = Path(board).resolve()
    before = sha256_file(source)
    snapshot = _placement_board_snapshot(source)
    if not isinstance(snapshot.get("track_count"), int):
        raise PipelineBlocked("route incumbent copper inventory unavailable")
    if snapshot["track_count"] == 0:
        return None
    work = Path(output_dir).resolve() / "incumbent"
    target = work / "board.kicad_pcb"
    copied = _copy_sidecars(source, target, cfg=cfg)
    family = _artifact_rows(copied)
    if sha256_file(target) != before:
        raise PipelineBlocked("route incumbent changed during staging")
    result = dict(synth.route_oracle_grade(
        str(target), cfg=cfg, route=False, seed=int(seed),
        work_dir=str(work / "grade"), keep=True, verbose=False,
        craft_gates=True, thermal=thermal, precision=True))
    if sha256_file(source) != before or not artifacts_match(family):
        raise PipelineBlocked("read-only route incumbent grading changed its input")
    if (not result.get("routed")
            or Path(result["routed"]).resolve() != target
            or not result.get("sort_key")
            or not isinstance(result.get("gate"), bool)
            or not result.get("gate_terms")
            or result.get("drc") is None
            or result.get("unconnected") is None
            or result.get("error")):
        raise PipelineBlocked("fresh route incumbent grading failed: %s" %
                              (result.get("error") or "incomplete oracle evidence"))
    result.update(candidate_origin="incumbent", incumbent_identity={
        "source": str(source), "sha256": before,
        "artifacts": family, "read_only": True,
        "params_sha256": digest_value(cfg.params), "thermal_policy": thermal,
    })
    import cec_route_debt_resume as debt
    import cec_force_current
    result['repair_debt_receipt']=debt.bind(result,family=family,
        params_sha256=digest_value(cfg.params),code_sha256=debt.digest(cec_force_current._code_identity()))
    atomic_json(work / "oracle.json", result)
    return result


def _admit_incumbent_finish(result, incumbent, before, output_dir, cfg, *, thermal):
    """Allow real finishing gains without letting polish undo incumbent choice."""
    import cec_search_policy

    evidence = {"schema": 1, "changed": not artifacts_match(before)}
    if not evidence["changed"]:
        evidence["reason"] = "incumbent_finish_unchanged"
        return result, evidence
    try:
        import cec_fr
        import cec_placement_route_prefix
        parent = cec_placement_route_prefix.capture(incumbent["routed"])
        copper = cec_fr.check_copper_geometry_prefix(result["routed"], parent)
        pairs = cec_placement_route_prefix.check_qualified_pairs(result["routed"], parent)
        if not copper.get("ok") or not pairs.get("ok"):
            raise PipelineBlocked("incumbent finish changed protected copper or pairs")
        import cec_route_checkpoint
        continuation = cec_route_checkpoint.preservation(
            incumbent['routed'], result['routed'], cfg)
        if not continuation.get('ok'):
            raise PipelineBlocked('finishing changed an independently preserved route prefix')
        evidence['continuation_preservation'] = continuation
        finished = _grade_route_incumbent(
            result["routed"], Path(output_dir) / "finish-comparison", cfg,
            seed=incumbent.get("seed") or 0, thermal=thermal)
        if finished is None:
            raise PipelineBlocked("incumbent finish lost routed copper")
        finished["candidate_origin"] = "incumbent_polish"
        selected = cec_search_policy.select_candidate([incumbent, finished])
        evidence.update(
            protected_copper_ok=True, qualified_pairs_ok=True,
            incumbent_gate_regressions=cec_search_policy.incumbent_gate_regressions(
                finished, incumbent),
            before_rank=list(cec_search_policy.candidate_rank(incumbent)),
            after_rank=list(cec_search_policy.candidate_rank(finished)),
            admitted=selected["candidate_origin"] == "incumbent_polish")
    except Exception as exc:                             # noqa: BLE001
        evidence.update(admitted=False, error="%s: %s" % (type(exc).__name__, exc))
        selected = incumbent
    # Return an exact, independently graded artifact, never an in-place undo
    # with potentially stale sidecars left behind by a refused finisher.
    selected = dict(selected)
    selected["dimension_repair"] = result.get("dimension_repair")
    selected["fab_repair"] = result.get("fab_repair")
    evidence["reason"] = ("incumbent_finish_improved" if evidence.get("admitted")
                          else "incumbent_finish_refused")
    return selected, evidence


def _recover_route_checkpoints(board, output_dir, cfg, *, seeds, thermal):
    """Grade a bounded shortlist of complete worker handoffs after shutdown.

    File presence and a stage's success flag are never admissions. Even a
    crashed worker's best snapshot gets the same fresh full oracle, immutable
    parent checks, and incumbent gate comparison as a normally returned board.
    """
    import cec_route_checkpoint as checkpoints
    import cec_synth_pipeline as synth
    import cec_operation_budget as budget

    output_dir = Path(output_dir).resolve()
    evidence = dict(schema=1, read_errors=[], attempts=[], release_authority=False)
    records = []
    for seed in seeds:
        root = output_dir / 'checkpoints' / ('seed-%06d' % int(seed))
        if not (root / 'current.json').exists():
            continue
        try:
            rows, errors = checkpoints.committed(root,
                context=checkpoints.context(cfg, board, seed))
            records.extend(rows)
            evidence['read_errors'].extend(dict(seed=seed, **e) for e in errors)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            evidence['read_errors'].append(dict(seed=seed, error=str(exc)))
    limit = max(1, min(8, int(cfg.params.get('route_checkpoint_grade_limit', 3))))
    evidence.update(available=len(records), grade_limit=limit)
    results, seen = [], set()
    for record in sorted(records, key=lambda r: (r['rank'], r['context']['seed'], r['stage'])):
        if record['sha256'] in seen:
            continue
        seen.add(record['sha256'])
        if (len(evidence['attempts']) >= limit
                or budget.available_timeout(30, os.environ, reserve_s=30) < 30):
            evidence['deferred'] = 'bounded_checkpoint_admission_budget'
            break
        attempt = dict(seed=record['context']['seed'], stage=record['stage'],
                       board=record['board'], sha256=record['sha256'], ok=False)
        evidence['attempts'].append(attempt)
        work = output_dir / 'checkpoint-admission' / (
            '%06d-%s' % (attempt['seed'], Path(record['board']).parent.name))
        try:
            corrected, pair_repair = checkpoints.normalize_complete_pair_additions(
                board, record['board'], work / 'pair-normalization', cfg)
            attempt['pair_normalization'] = pair_repair
            normalized, assembly = checkpoints.assembly_normalize(corrected, work / 'assembly', cfg)
            attempt['assembly'] = assembly
            bound, _authority = synth.config_with_board_route_authority(cfg, normalized)
            result = _grade_route_incumbent(normalized, work, bound,
                seed=attempt['seed'], thermal=thermal)
            if result is None:
                raise ValueError('checkpoint contains no routed copper')
            proof = checkpoints.preservation(board, result['routed'], bound)
            atomic_json(work / 'preservation.json', proof)
            if not proof.get('ok'):
                raise ValueError('checkpoint failed independent parent/power preservation')
            result = dict(result)
            result.pop('incumbent_identity', None)
            result.update(candidate_origin='route_checkpoint', route_checkpoint=dict(
                schema=1, stage=record['stage'], original_sha256=record['sha256'],
                checkpoint_board=record['board'], preservation=str(work / 'preservation.json'),
                freshly_graded=True, release_authority=False))
            atomic_json(work / 'oracle.json', result)
            attempt.update(ok=True, drc=result['drc'], unconnected=result['unconnected'],
                           report=str(work / 'oracle.json'))
            results.append(result)
        except Exception as exc:                         # noqa: BLE001
            attempt['error'] = '%s: %s' % (type(exc).__name__, exc)
        atomic_json(output_dir / 'checkpoint-recovery.json', evidence)
    if records or evidence['read_errors']:
        atomic_json(output_dir / 'checkpoint-recovery.json', evidence)
    return results, evidence


def _persist_route_search_history(result, evidence, output_dir):
    """Store compact ordering hints on a coordinator-owned selected copy only."""
    history = evidence.get('route_search_history')
    if not history or result.get('candidate_origin') not in (
            'incumbent', 'route_residual_resume', 'incumbent_polish', 'route_residual_resume_polish'):
        return []
    board = Path(result['routed']).resolve()
    if not board.is_relative_to(Path(output_dir).resolve()):
        raise PipelineBlocked('search history cannot modify an external board family')
    import cec_certificate_repair as repair
    history = repair.route_search_history({'route_search_history': history})
    path = board.with_suffix('.route-search.json')
    atomic_json(path, dict(schema=1, board_sha256=sha256_file(board),
        route_search_history=history, release_authority=False))
    return [str(path)]


def _resume_owned_pair_access(incumbent, output_dir, cfg, *, seed, thermal):
    """One upstream topology repair, independently graded like every candidate."""
    import cec_pair_access_repair
    import cec_operation_budget as budget
    import cec_search_policy as policy
    import cec_synth_pipeline as synth
    evidence=dict(schema=1,changed=False,release_authority=False)
    wall=float((cfg.params or {}).get('route_pair_access_wall_s',390.))
    if not math.isfinite(wall) or not 150 <= wall <= 600:
        raise ValueError('pair-access wall budget must be 150..600 seconds')
    reserve=float((cfg.params or {}).get('route_finish_reserve_s',
        os.environ.get('CEC_ROUTE_FINISH_RESERVE_S','120')))
    funded=budget.optional_work_admission(wall+100.,reserve_s=reserve)
    if not funded['start']:
        return None,dict(evidence,reason='pair_access_and_revalidation_unfunded',budget=funded)
    source=incumbent['routed']
    inputs=_artifact_rows(p for p in _placement_authority_family(source) if Path(p).is_file())
    work=Path(output_dir)/'owned-pair-access'
    try:
        repair=cec_pair_access_repair.attempt(source,work,cfg,wall_s=wall)
        evidence['repair']={k:repair.get(k) for k in
            ('ok','changed','reason','board','recovered_nets','wall_s','error')}
        if not artifacts_match(inputs):
            raise PipelineBlocked('pair-access worker changed immutable source family')
        if not repair.get('ok') or not repair.get('changed') or not repair.get('board'):
            return None,dict(evidence,reason='no_admitted_pair_access_proposal')
        bound,_=synth.config_with_board_route_authority(cfg,repair['board'])
        grade=_grade_route_incumbent(repair['board'],work/'fresh-grade',bound,seed=seed,thermal=thermal)
        if grade is None:
            raise ValueError('pair-access proposal lost routed copper')
        grade=dict(grade,candidate_origin='route_pair_access_repair')
        losses=policy.incumbent_gate_regressions(grade,incumbent)
        evidence.update(drc=grade['drc'],unconnected=grade['unconnected'],gate_regressions=losses)
        if (losses or grade['drc']!=0 or grade['unconnected']>=incumbent['unconnected']
                or policy.select_candidate([incumbent,grade])!=grade):
            return None,dict(evidence,reason='fresh_pair_access_grade_refused')
        return grade,dict(evidence,changed=True,reason='owned_pair_access_improved')
    except PipelineBlocked:
        raise
    except Exception as exc:
        return None,dict(evidence,reason='pair_access_repair_error',error='%s: %s'%(type(exc).__name__,exc))


def _placement_slice_frontier(repair, source, prior_history=None):
    """Honor a measured, source-bound placement slice without a global reroute.

    This is a scheduling receipt only. No changed board is accepted here, and
    missing/exhausted/timeout evidence must retain the normal route fallback.
    """
    import cec_certificate_repair as certificate
    import cec_route_pose_history as poses
    if (repair.get('changed') or repair.get('error') or repair.get('bounded_stop')
            or (repair.get('effort_budget') or {}).get('stop_reason') != 'placement_slice_complete'):
        return dict(ok=False, release_authority=False)
    scope = ((repair.get('route_search_history') or {}).get('placement_poses') or {}).get('scope')
    if (not poses.valid_scope(scope) or scope['board_sha256'] != sha256_file(source)
            or scope['algorithm_revision'] != certificate.REPAIR_ALGORITHM_REVISION):
        return dict(ok=False, release_authority=False)
    plan = repair.get('plan') or {}
    sweeps = [(plan.get(name) or {}).get('sweep') for name in (
        'footprint_relocation', 'endpoint_owner_relocation',
        'post_route_support_refresh', 'post_negotiation_support_refresh')]
    if any((sweep or {}).get('accepted') for sweep in sweeps):
        return dict(ok=False, release_authority=False)
    # A receipt must actually persist a NEW measured refusal. An unchanged
    # report or a lost sidecar cannot keep suppressing the global fallback.
    measured, _retry = poses.measured_keys(sweeps)
    saved = poses.read(repair['route_search_history']['placement_poses'], scope)
    previous = poses.read((prior_history or {}).get('placement_poses'), scope)
    new_keys = (measured & saved) - previous
    advanced = (bool(new_keys) and
        certificate._placement_frontier_advanced(*sweeps, pose_scope=scope))
    return dict(ok=advanced, release_authority=False,
                reason='measured_unvisited_placement_frontier' if advanced else 'no_new_placement_frontier',
                newly_remembered_poses=len(new_keys),
                source_sha256=scope['board_sha256'])


def _resume_route_residuals(incumbent, output_dir, cfg, *, seed, thermal):
    """Spend a small routed board's next lease on its unfinished repair stage.

    An earlier route/import can consume the entire campaign before certificate
    repair is funded. Repeating placement and global routing first recreates
    that starvation. Resume the existing repair engine, with fresh residuals
    and independent admission, instead. This is scheduling, not a new router
    or permission to relax any geometry rule. A plateau ends this portfolio;
    ordinary global search remains the fallback when no repair is admitted.
    """
    import cec_final_residual
    import cec_operation_budget as budget
    import cec_route_checkpoint as checkpoints
    import cec_search_policy as policy
    import cec_synth_pipeline as synth

    evidence = dict(schema=1, rounds=[], skip_global=False,
                    release_authority=False, changed=False)
    params = cfg.params or {}
    if params.get('route_residual_resume', True) is False:
        evidence['skipped'] = 'policy_disabled'
        return None, evidence
    import cec_route_debt_resume as debt
    import cec_force_current
    known_debt=bool(incumbent and debt.verified(incumbent,
        params_sha256=digest_value(cfg.params),
        code_sha256=debt.digest(cec_force_current._code_identity()),artifacts_match=artifacts_match))
    if (not incumbent or (incumbent.get('drc') != 0 and not known_debt)
            or incumbent.get('gate_terms', {}).get('final_residual_consistent') is not True
            or not isinstance(incumbent.get('unconnected'), int)):
        evidence['skipped'] = 'no_verified_clean_routed_incumbent'
        return None, evidence
    count = incumbent['unconnected']
    limit = max(0, min(128, int(params.get('route_residual_resume_max_opens', 64 if known_debt else 32))))
    if count < 0 or count > limit:
        evidence['skipped'] = 'outside_residual_portfolio'
        return None, evidence
    if known_debt and count and (incumbent['drc'] or count>32):
        # Existing faults are work, not a release waiver. Use a narrowly owned
        # additive portfolio that preserves all original copper and placements.
        # The later independent full oracle still owns every release gate.
        import cec_residual_breadth
        wall=float(params.get('route_residual_resume_wall_s',240.))
        if not math.isfinite(wall) or not 30 <= wall <= 600:
            raise ValueError('known-debt repair wall budget must be 30..600 seconds')
        reserve=float(params.get('route_finish_reserve_s',120.))
        assembly_allowance = 90. if incumbent['gate_terms'].get('fiducials_ok') is False else 0.
        funded=budget.optional_work_admission(wall+60.+assembly_allowance,reserve_s=reserve)
        if not funded['start']:
            evidence.update(stop='finish_reserve',budget=funded)
            return None,evidence
        current = incumbent
        # Mechanical optical marks are not route obstacles to work around.
        # Use their existing bounded allocator, exact optical-only receiving,
        # and a fresh full oracle before spending residual search on the child.
        if incumbent['gate_terms'].get('fiducials_ok') is False:
            assembly = dict(accepted=False, release_authority=False)
            evidence['optical_assembly'] = assembly
            try:
                normalized, proposal = checkpoints.assembly_normalize(
                    incumbent['routed'], Path(output_dir)/'debt-assembly', cfg)
                assembly['proposal'] = proposal
                if proposal.get('changed'):
                    bound, _ = synth.config_with_board_route_authority(cfg, normalized)
                    checked = _grade_route_incumbent(normalized,
                        Path(output_dir)/'assembly-admission', bound, seed=seed, thermal=thermal)
                    import cec_stage_admission
                    transition = cec_stage_admission.evaluate(
                        incumbent['mutation_snapshot'], checked['mutation_snapshot'], require_strict=True)
                    losses = policy.incumbent_gate_regressions(checked, incumbent)
                    assembly.update(native_admission=transition, gate_regressions=losses)
                    if transition['accepted'] and not losses:
                        current = checked
                        assembly['accepted'] = True
            except Exception as exc:
                assembly['error'] = type(exc).__name__ + ':' + str(exc)[:600]
        def keep_received(stop):
            evidence['stop'] = stop
            if current is not incumbent:
                evidence.update(changed=True,skip_global=True,stop='native_optical_debt_reduced')
            atomic_json(Path(output_dir)/'residual-resume.json',evidence)
            return (dict(current,candidate_origin='route_residual_resume')
                    if current is not incumbent else None),evidence
        try:
            with synth._oracle_env(params):
                trial=cec_residual_breadth.run(current['routed'],
                    Path(output_dir)/'known-debt-breadth',board_hint=getattr(cfg,'board_key',None),
                    wall_s=wall,max_rounds=int(params.get('route_residual_resume_rounds',2)))
        except Exception as exc:
            evidence['additive_error'] = type(exc).__name__ + ':' + str(exc)[:600]
            return keep_received('bounded_breadth_start_failed')
        evidence['additive_breadth']=trial
        if not trial.get('changed'):
            return keep_received(trial.get('stop'))
        # A new source-delta receiving proof is independent of the worker's
        # gate. No complete-power receipt is inferred from retention alone.
        import cec_additive_route_receiving
        proof=cec_additive_route_receiving.receive(current['routed'],trial['candidate'])
        evidence['native_retention']=proof
        if not proof.get('ok') or not proof.get('complete'):
            return keep_received('independent_retention_refused')
        import cec_current_debt
        rated = cec_current_debt.receive(current['routed'], trial['candidate'],
            board_hint=getattr(cfg, 'board_key', None) or str(current['routed']))
        evidence['exact_current_debt'] = {key: value for key, value in rated.items()
                                        if key not in ('before_result', 'after_result')}
        if not rated.get('ok') or not rated.get('complete'):
            return keep_received('independent_current_debt_refused')
        bound,_=synth.config_with_board_route_authority(cfg,trial['candidate'])
        grade=_grade_route_incumbent(trial['candidate'],Path(output_dir)/'breadth-admission',
            bound,seed=seed,thermal=thermal)
        decision=debt.admit(current,grade or {})
        evidence['debt_admission']=decision
        losses=policy.incumbent_gate_regressions(grade or {},current)
        evidence['gate_regressions']=losses
        if grade and decision['accepted'] and not losses:
            evidence.update(changed=True,skip_global=True,stop='native_additive_debt_reduced')
            atomic_json(Path(output_dir)/'residual-resume.json',evidence)
            return dict(grade,candidate_origin='route_residual_resume'),evidence
        return keep_received('independent_admission_refused')
    if count == 0:
        # Closure is not fab approval: independent release/thermal gates and
        # the normal guarded finishing path still run below. Nor does zero
        # airwires establish correct pair/power topology: failed route gates
        # must retain access to the normal routing/repair portfolio.
        route_terms = ('pairs_ok', 'rails_ok', 'kelvin_reach_ok', 'pin_escape_ok',
                       'foreign_ok', 'incursion_ok', 'decoupler_cell_ok', 'decouple_ok',
                       'netclass_geometry_ok')
        failed = [name for name in route_terms
                  if incumbent['gate_terms'].get(name) is False]
        evidence.update(skip_global=not failed, failed_route_terms=failed,
            skipped='closed_but_route_gates_failed' if failed else 'native_connectivity_complete')
        return None, evidence
    # A finished priority route can itself own the access a residual needs.
    # A full native incumbent (not a counts-only hint) may fund one bounded,
    # typed pair replacement before repeating downstream placement searches.
    # Its independent ownership proof is distinct from additive/local repair.
    if (params.get('route_pair_access_repair',True)
            and incumbent.get('pairs_ok') is True and incumbent.get('incumbent_identity')):
        pair_candidate,pair_evidence=_resume_owned_pair_access(
            incumbent,output_dir,cfg,seed=seed,thermal=thermal)
        evidence['owned_pair_access']=pair_evidence
        if pair_candidate is not None:
            evidence.update(changed=True,skip_global=True,stop='owned_pair_access_improved')
            atomic_json(Path(output_dir)/'residual-resume.json',evidence)
            return pair_candidate,evidence
    rounds = max(1, min(4, int(params.get('route_residual_resume_rounds', 2))))
    wall = float(params.get('route_residual_resume_wall_s', 240.0))
    if not math.isfinite(wall) or not 10 <= wall <= 600:
        raise ValueError('residual repair wall budget must be 10..600 seconds')
    reserve = float(params.get('route_finish_reserve_s',
                              os.environ.get('CEC_ROUTE_FINISH_RESERVE_S', '120')))
    original, current = incumbent, incumbent
    prior_history = {}
    history_path = Path(current['routed']).with_suffix('.route-search.json')
    if history_path.is_file() and history_path.stat().st_size <= 65536:
        try:
            saved = _load_json(history_path)
            if isinstance(saved, dict) and saved.get('board_sha256') == sha256_file(current['routed']):
                prior_history = saved.get('route_search_history') or {}
        except (ValueError, OSError, TypeError):
            pass  # Ordering hints cannot block or authorize native work.
    report_path = Path(output_dir) / 'residual-resume.json'
    for index in range(rounds):
        funded = budget.optional_work_admission(wall + 60.0, reserve_s=reserve)
        if not funded['start']:
            evidence.update(stop='finish_reserve', budget=funded)
            break
        work = Path(output_dir) / 'residual-resume' / ('round-%02d' % index)
        work.mkdir(parents=True, exist_ok=True)
        row = dict(round=index, input=current['routed'], accepted=False)
        evidence['rounds'].append(row)
        try:
            source_family = _artifact_rows(p for p in
                _placement_authority_family(current['routed']) if Path(p).is_file())
            completion = {'final_residual': cec_final_residual.measure(
                current['routed'], max_details=128, wall_timeout_s=25)}
            completion['route_search_history'] = prior_history
            import cec_support_motion
            completion['support_placement_limits'] = cec_support_motion.limits(
                immutable_refs=tuple(synth._placement_repair_immutable_refs(cfg)))
            # The worker computes its actual board/rule/effort fingerprint.
            # Bind the remaining declarative policy too, but not its staged
            # frozen-state pathname (the sibling contents are hashed there).
            completion['route_pose_policy'] = dict(params=dict(params),
                profile=getattr(cfg, 'profile', None), pins=getattr(cfg, 'pins', {}))
            residual = completion['final_residual']
            if (not cec_final_residual.valid_snapshot(residual)
                    or residual.get('source_board_sha256') != sha256_file(current['routed'])
                    or residual.get('unconnected_count') != current['unconnected']):
                raise ValueError('fresh residual disagrees with native incumbent grade')
            atomic_json(work / 'input-residual.json', completion)
            with synth._oracle_env(params):
                candidate, repair = synth._route_oracle_certificate_repair(
                    current['routed'], completion, str(work),
                    max_targets=int(params.get('certificate_repair_max_targets', 8)),
                    max_windows=int(params.get('certificate_repair_max_windows', 8)),
                    max_blockers_per_window=int(params.get('certificate_repair_max_blockers_per_window', 4)),
                    max_attempts=int(params.get('certificate_repair_max_attempts', 64)),
                    wall_budget_s=wall, authored_baseline=original['routed'],
                    deep_retry=bool(params.get('certificate_repair_deep_retry', True)),
                    timeout_s=int(math.ceil(wall + 60.0)))
            if not artifacts_match(source_family):
                raise PipelineBlocked('residual worker changed its immutable source family')
            row['repair'] = {key: repair.get(key) for key in
                ('changed', 'improvement', 'wall_s', 'skipped', 'error', 'bounded_stop')}
            previous_history = prior_history
            prior_history = repair.get('route_search_history') or prior_history
            evidence['route_search_history'] = prior_history
            if candidate == current['routed'] or not repair.get('changed'):
                frontier = _placement_slice_frontier(repair, current['routed'], previous_history)
                row['placement_frontier'] = frontier
                if frontier['ok']:
                    evidence.update(stop='placement_frontier_progress', skip_global=True)
                else:
                    evidence['stop'] = 'no_progress'
                break
            bound, _ = synth.config_with_board_route_authority(cfg, candidate)
            proof = checkpoints.preservation(original['routed'], candidate, bound)
            atomic_json(work / 'preservation.json', proof)
            if not proof.get('ok'):
                import cec_route_placement_admission as placement_admission
                if not placement_admission.placement_only_failure(proof):
                    raise ValueError('residual repair failed parent/power/pair preservation')
                placement_funded = budget.optional_work_admission(90.0, reserve_s=reserve)
                if not placement_funded['start']:
                    evidence.update(stop='placement_revalidation_unfunded', budget=placement_funded)
                    break
                transition = placement_admission.prepare(original['routed'], candidate,
                    work / 'placement-revalidation', cfg, timeout_s=90.0)
                row['placement_revalidation'] = {key: transition.get(key) for key in
                    ('ok', 'reason', 'moved_refs', 'board', 'input_families_unchanged')}
                if not transition.get('ok'):
                    evidence['stop'] = 'placement_revalidation_refused'
                    if transition.get('reason') == 'source_refill_drift':
                        # The independent source itself fails zero-edit fill
                        # stability. Retain it without promoting the child or
                        # spending global waves on an invalid authority input.
                        evidence.update(stop='source_refill_drift', skip_global=True,
                                        requires_source_revalidation=True)
                    break
                candidate = transition['board']
                bound, _ = synth.config_with_board_route_authority(cfg, candidate)
                # The additive proof remains false and stored as such. A new
                # complete placement proof, not a changed guard, owns this
                # transition; normal fresh route grading below still decides.
            grade = _grade_route_incumbent(candidate, work / 'admission', bound,
                                           seed=seed, thermal=thermal)
            if grade is None:
                raise ValueError('residual repair lost routed copper')
            grade = dict(grade, candidate_origin='route_residual_resume')
            losses = policy.incumbent_gate_regressions(grade, current)
            row.update(drc=grade['drc'], unconnected=grade['unconnected'],
                       gate_regressions=losses)
            if (losses or grade['drc'] != 0
                    or grade['unconnected'] >= current['unconnected']
                    or policy.select_candidate([current, grade]) != grade):
                evidence['stop'] = 'independent_admission_refused'
                break
            row['accepted'] = True
            current = grade
            evidence.update(changed=True, skip_global=True)
            atomic_json(report_path, evidence)
            if grade['unconnected'] == 0:
                evidence['stop'] = 'native_connectivity_complete'
                break
        except PipelineBlocked:
            # A changed source is an integrity failure, not a reason to try
            # another router against corrupted incumbent bytes.
            raise
        except Exception as exc:                         # noqa: BLE001
            row['error'] = '%s: %s' % (type(exc).__name__, exc)
            evidence['stop'] = 'repair_or_admission_error'
            break
    else:
        evidence['stop'] = 'round_budget'
    atomic_json(report_path, evidence)
    return (current if evidence['changed'] else None), evidence


def _route_stage(board, output_dir, cfg, *, passes, opt, seed, timeout,
                 thermal, candidates=1, route_workers=None,
                 allow_route_access_repair=False):
    import cec_synth_pipeline as synth
    import cec_search_policy
    import cec_process_pool
    import cec_route_checkpoint

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
        for key in ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv'):
            if hasattr(cfg, key):
                setattr(route_cfg, key, getattr(cfg, key))
    route_config = {key: getattr(route_cfg, key) for key in
        ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv')
        if hasattr(route_cfg, key)}
    seeds = cec_search_policy.bounded_seed_plan(seed, candidates)
    incumbent = _grade_route_incumbent(
        board, output_dir, route_cfg, seed=seeds[0], thermal=thermal)
    candidate_results = []
    executor_evidence = {
        "schema": 1, "mode": "in_process", "bounded": True,
        "requested": len(seeds), "workers": 1,
        "seed_axis": "freerouting-cec",
    }
    residual_candidate, residual_evidence = _resume_route_residuals(
        incumbent, output_dir, route_cfg, seed=seeds[0], thermal=thermal)
    executor_evidence['residual_resume'] = residual_evidence
    if residual_candidate is not None:
        candidate_results.append(residual_candidate)

    def candidate_wall_budget():
        # One generic watchdog policy for both serial and ensemble dispatch.
        # Internal FR effort remains unchanged; this bounds the whole prefix
        # portfolio, native admission, and residual-router generation.
        default = max(7200.0, float(timeout) * 6.0 + 1800.0)
        raw = (params.get("route_worker_watchdog_s") or
               os.environ.get("CEC_ROUTE_WORKER_WATCHDOG_S") or default)
        try:
            value = max(60.0, float(raw))
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    if residual_evidence['skip_global']:
        executor_evidence.update(mode='residual_resume', workers=0,
                                 global_route_skipped=True)
    elif len(seeds) == 1:
        import cec_operation_budget as budget
        import cec_route_candidate_worker
        # A standalone coordinator has no campaign deadline. Establish ONE
        # non-renewable lease before dispatch, clamped to any enclosing lease,
        # so every nested current/prune/force operation shares the same wall.
        candidate_watchdog = candidate_wall_budget()
        reserve_s = float(params.get('route_finish_reserve_s',
            os.environ.get('CEC_ROUTE_FINISH_RESERVE_S', '120')))
        environment = dict(os.environ)
        budget.available_timeout(candidate_watchdog, environment, reserve_s=reserve_s)
        enclosing = [float(environment[key]) for key in
                     ('CEC_OPERATION_DEADLINE_EPOCH', 'CEC_JOB_DEADLINE_EPOCH')
                     if key in environment]
        deadline = min([time.time() + candidate_watchdog] + enclosing)
        environment['CEC_OPERATION_DEADLINE_EPOCH'] = str(deadline)
        directory = Path(tempfile.mkdtemp(prefix='operation-route-candidate-', dir=output_dir))
        payload_path, report_path = directory / 'payload.json', directory / 'report.json'
        payload = {
            'board': str(Path(board).resolve()), 'board_name': cfg.board,
            'params': params, 'config': route_config,
            'passes': int(passes), 'opt': int(opt), 'seed': int(seeds[0]),
            'timeout': int(timeout), 'thermal': thermal, 'work_dir': str(output_dir),
            'checkpoint_dir': str(output_dir / 'checkpoints' / ('seed-%06d' % seeds[0])),
            'allow_route_access_repair': bool(allow_route_access_repair),
        }
        atomic_json(payload_path, payload)
        command = [sys.executable, cec_route_candidate_worker.__file__,
                   '--payload', str(payload_path), '--report', str(report_path)]
        executor_evidence.update(mode='isolated_operation',
            candidate_watchdog_s=candidate_watchdog, deadline_epoch=deadline,
            finalization_reserve_s=reserve_s, report=str(report_path))
        operation = dict(operation='route-candidate', directory=str(directory), command=command)
        try:
            with budget.finalization_reserve(reserve_s, env=environment) as reservation:
                operation = budget.run(command, directory, operation='route-candidate',
                                       timeout=candidate_watchdog, env=environment)
            executor_evidence['finalization_budget'] = reservation
            if reservation['budget_exhausted']:
                raise budget.OperationFailure(reservation['operation_failure'])
            result = json.loads(report_path.read_text(encoding='utf-8'))
            if (not isinstance(result, dict) or not isinstance(result.get('gate'), bool)
                    or result.get('seed') != int(seeds[0])):
                raise ValueError('route candidate report lacks matching seed/gate evidence')
            result['operation_evidence'] = operation
            candidate_results.append(result)
            executor_evidence.update(status='complete', operation_evidence=operation)
        except (budget.OperationFailure, OSError, ValueError) as exc:
            failure = dict(getattr(exc, 'failure_evidence', None) or dict(operation,
                status='worker_report_invalid' if operation.get('status') == 'complete'
                else 'worker_start_failed', error=str(exc)))
            try:
                with (directory / 'worker.log').open('rb') as capture:
                    failure['log_tail'] = synth._placement_craft_native_tail(capture)
            except OSError:
                pass
            exhausted = failure.get('status') in (
                'operation_budget_exhausted', 'campaign_budget_exhausted')
            classification = dict(status='deferred_budget' if exhausted else 'worker_failed',
                outcome='inconclusive', search_inconclusive=True, proof_complete=False,
                budget_exhausted=exhausted, retryable=False,
                physical_feasibility='not_assessed', release_authority=False,
                operation_failure=failure)
            failed = dict(seed=seeds[0], gate=False, routed=None, drc=None, unconnected=None,
                sort_key=[1,99,99,99], failure_stage='route_candidate_operation',
                worker_error='%s: %s' % (type(exc).__name__, exc),
                blocker_evidence=classification, **classification)
            atomic_json(directory / 'failure.json', failed)
            candidate_results.append(failed)
            executor_evidence.update(classification)
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
                "params": params, "config": route_config,
                "passes": int(passes), "opt": int(opt),
                "seed": int(candidate_seed), "timeout": int(timeout),
                "thermal": thermal, "work_dir": str(work),
                "checkpoint_dir": str(output_dir / 'checkpoints' /
                                      ('seed-%06d' % int(candidate_seed))),
                "allow_route_access_repair": bool(
                    allow_route_access_repair),
            })
        context = multiprocessing.get_context("spawn")
        candidate_watchdog = candidate_wall_budget()
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
            _route_candidate_cohorts(
                pool, payloads, workers, watchdog_s=generation_watchdog,
                reserve_s=float(params.get('route_finish_reserve_s',
                    os.environ.get('CEC_ROUTE_FINISH_RESERVE_S', '120'))),
                results=candidate_results, evidence=executor_evidence,
                active=future_payload)
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

    executor_evidence['residual_resume'] = residual_evidence
    recovered, checkpoint_evidence = _recover_route_checkpoints(
        board, output_dir, route_cfg, seeds=seeds, thermal=thermal)
    candidate_results.extend(recovered)
    executor_evidence['checkpoints'] = checkpoint_evidence
    # Normal returns and rescued snapshots obey the same parent/pair rules.
    # Missing physics must not become acceptable merely because a worker
    # reached its return statement before its deadline.
    for row in candidate_results:
        if not row.get('routed') or row.get('candidate_origin') == 'route_checkpoint':
            continue
        try:
            proof = cec_route_checkpoint.preservation(board, row['routed'], route_cfg)
            proof_path = output_dir / ('candidate-%06d-preservation.json' % int(row.get('seed') or 0))
            atomic_json(proof_path, proof)
            row['continuation_preservation'] = str(proof_path)
            if not proof.get('ok'):
                import cec_route_placement_admission as placement_admission
                import cec_operation_budget as budget
                if row.get('candidate_origin')=='route_pair_access_repair':
                    import cec_route_pair_admission as pair_admission
                    if not pair_admission.pair_only_failure(proof):
                        raise ValueError('returned pair-access candidate has unrelated preservation failures')
                    funded=budget.optional_work_admission(90.,reserve_s=float(params.get(
                        'route_finish_reserve_s',os.environ.get('CEC_ROUTE_FINISH_RESERVE_S','120'))))
                    if not funded['start']:
                        raise ValueError('outer pair-access revalidation not funded')
                    pair_dir=output_dir/('candidate-%06d-pair-access'%int(row.get('seed') or 0))
                    transition=pair_admission.prepare(board,row['routed'],pair_dir,route_cfg,timeout_s=90.)
                    row['continuation_revalidation']=str(pair_dir/'revalidation.json')
                    if (not transition.get('ok')
                            or sha256_file(transition['board'])!=sha256_file(row['routed'])):
                        raise ValueError('outer pair-access revalidation refused')
                    row['routed']=transition['board']
                    continue
                if (row.get('candidate_origin') != 'route_residual_resume'
                        or not placement_admission.placement_only_failure(proof)):
                    raise ValueError('returned candidate failed parent/pair/power preservation')
                # The residual coordinator can admit a support-placement
                # transaction. The outer selector must validate that same
                # kind of transition, not silently reinterpret it as additive
                # routing and discard it. Recheck against this stage's exact
                # parent, in a new private family; never trust an origin label
                # or an inner success flag as placement authority.
                funded = budget.optional_work_admission(90.0, reserve_s=float(
                    params.get('route_finish_reserve_s',
                               os.environ.get('CEC_ROUTE_FINISH_RESERVE_S', '120'))))
                if not funded['start']:
                    raise ValueError('outer placement revalidation not funded')
                revalidation_dir = output_dir / ('candidate-%06d-placement' % int(row.get('seed') or 0))
                transition = placement_admission.prepare(
                    board, row['routed'], revalidation_dir, route_cfg, timeout_s=90.0)
                row['continuation_revalidation'] = str(revalidation_dir/'revalidation.json')
                if (not transition.get('ok')
                        or sha256_file(transition['board']) != sha256_file(row['routed'])):
                    raise ValueError('outer support-placement revalidation refused')
                # Board bytes and rule policy were independently preserved;
                # the fresh grade stays valid on the revalidated family.
                row['routed'] = transition['board']
        except Exception as exc:                         # noqa: BLE001
            row.update(failure_artifact=row['routed'], routed=None, gate=False,
                failure_stage='continuation_preservation', error='%s: %s' % (type(exc).__name__, exc))
    if incumbent is not None:
        # The baseline does not spend a seed slot or alter the explicit search
        # budget. It is graded once with the same authority and thermal policy.
        identity = incumbent["incumbent_identity"]
        if (sha256_file(board) != identity["sha256"]
                or not artifacts_match(identity["artifacts"])):
            raise PipelineBlocked("route incumbent identity changed during candidate search")
        candidate_results.append(incumbent)
    candidate_summary = [
        _route_candidate_summary(row) for row in candidate_results]
    for summary, row in zip(candidate_summary, candidate_results):
        summary["incumbent_gate_regressions"] = (
            cec_search_policy.incumbent_gate_regressions(row, incumbent)
            if row.get('routed') else None)
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
    retained_incumbent = result.get("candidate_origin") == "incumbent"
    retained_checkpoint = result.get('candidate_origin') in (
        'route_checkpoint', 'route_residual_resume', 'route_pair_access_repair')
    if len(seeds) > 1 or retained_incumbent or retained_checkpoint:
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
    incumbent_finish_before = _artifact_rows(copied) if retained_incumbent else None
    finish_baseline = incumbent if retained_incumbent else None
    if not retained_checkpoint and not retained_incumbent:
        # Optional finishers also need an immutable rollback point. The old
        # protection covered only an incumbent winner, not a new proposal.
        prior = output_dir / 'before-finish' / 'board.kicad_pcb'
        _copy_sidecars(result['routed'], prior, cfg=route_cfg)
        finish_baseline = dict(result, routed=str(prior), candidate_origin='incumbent',
            finish_source_origin=result.get('candidate_origin', 'proposal'))
        incumbent_finish_before = _artifact_rows(_copy_sidecars(result['routed'], result['routed'], cfg=route_cfg))

    if retained_checkpoint and Path(result['routed']).is_file():
        # Full fabrication polish is intentionally deferred for checkpoints,
        # but that used to defer even a tiny safe geometry cleanup indefinitely.
        # Give only the existing unlocked acute-vertex primitive a bounded
        # transaction, with an immutable rollback copy and the same independent
        # parent/pair/power/fresh-grade admission used by every other finisher.
        prior = output_dir / 'before-progress-polish' / 'board.kicad_pcb'
        _copy_sidecars(result['routed'], prior, cfg=route_cfg)
        finish_baseline = dict(result, routed=str(prior), candidate_origin='incumbent',
            finish_source_origin=result.get('candidate_origin'))
        incumbent_finish_before = _artifact_rows(p for p in
            _placement_authority_family(result['routed']) if Path(p).is_file())
        import cec_operation_budget as budget
        funded = budget.optional_work_admission(30.0, reserve_s=float(params.get(
            'route_finish_reserve_s', os.environ.get('CEC_ROUTE_FINISH_RESERVE_S','120'))))
        if funded['start']:
            try:
                import cec_route_progress_polish as progress_polish
                result['progress_polish'] = progress_polish.apply(result['routed'], timeout_s=30.0)
            except Exception as exc:                     # noqa: BLE001
                result['progress_polish'] = dict(changed=False,error='%s: %s' % (type(exc).__name__,exc))
        else:
            result['progress_polish'] = dict(changed=False,skipped='finish_reserve',budget=funded)

    # Dimension refusals are spatial work, not a waiver or another blind size
    # normalization. Rebuild eligible escapes against final dimensions before
    # cosmetic fabrication polish. The actuator is bounded and admits exact
    # fault identities including assembly violations that KiCad DRC can miss.
    dimension_repair = {"schema": 1, "skipped": "route_artifact_missing"}
    if retained_checkpoint:
        dimension_repair = {'schema':1, 'skipped':'retained_checkpoint_resume_pending'}
    elif result.get("routed") and os.path.isfile(result["routed"]):
        if os.environ.get("CEC_DIMENSION_REPAIR", "1") == "1":
            try:
                import cec_dimension_repair
                dimension_repair = cec_dimension_repair.repair_admitted(
                    result["routed"], max_targets=8, max_seats=32,
                    board_hint=cfg.board,
                    wall_budget_s=min(240.0, float(os.environ.get(
                        "CEC_DIMENSION_REPAIR_WALL_S", "120"))))
                after = (dimension_repair.get("after") or {}).get("score") or {}
                if dimension_repair.get("changed"):
                    for key in ("drc", "unconnected", "kelvin_ok", "diffpair_ok"):
                        if key in after:
                            result[key] = after[key]
            except Exception as exc:                     # noqa: BLE001
                dimension_repair = {"schema": 1, "skipped": "repair_error",
                    "error": "%s: %s" % (type(exc).__name__, exc)}
        else:
            dimension_repair = {"schema": 1, "skipped": "policy_disabled"}
    result["dimension_repair"] = dimension_repair

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
    if retained_checkpoint:
        fab_repair = {'schema':1, 'skipped':'retained_checkpoint_resume_pending'}
    elif (_has_routed_artifact
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
    # Field faults are electrical release failures despite ordinary DRC being
    # clean. Repair them through the shared bounded actuator, then subject the
    # result to the SAME protected-prefix/fresh-oracle rollback below.
    import cec_route_field_finish
    field_finish = dict(changed=False, skipped='no_closed_route_field_defects')
    if (not retained_checkpoint and finish_baseline is not None
            and cec_route_field_finish.eligible(result)):
        import cec_operation_budget as budget
        funded = budget.optional_work_admission(90., reserve_s=float(params.get(
            'route_finish_reserve_s', os.environ.get('CEC_ROUTE_FINISH_RESERVE_S','120'))))
        if funded['start']:
            try:
                field_finish = cec_route_field_finish.apply(
                    result, output_dir/'field-finish', timeout_s=90., max_rounds=1)
            except Exception as exc:                     # noqa: BLE001
                field_finish = dict(changed=False, error='%s: %s' % (type(exc).__name__, exc))
        else:
            field_finish = dict(changed=False, skipped='finish_reserve', budget=funded)
    # Source-typed scalar finishing is distinct from acute-only progress polish.
    # A closed route gets one bounded private proposal. No locked-cut opt-in,
    # prefix exception, old-board selector or release shortcut is provided.
    # The same fresh whole-coordinator admission and immutable rollback below
    # decide whether it actually replaces the selected incumbent.
    import cec_route_scalar_finish
    scalar_finish = dict(changed=False, skipped='no_closed_selected_route', release_authority=False)
    if params.get('route_scalar_path_finish', True) is False:
        scalar_finish['skipped'] = 'policy_disabled'
    elif finish_baseline is not None and cec_route_scalar_finish.eligible(result):
        try:
            import cec_operation_budget as budget
            funded = budget.optional_work_admission(120., reserve_s=float(params.get(
                'route_finish_reserve_s', os.environ.get('CEC_ROUTE_FINISH_RESERVE_S','120'))))
            if funded['start']:
                scalar_finish = cec_route_scalar_finish.apply(result, output_dir/'source-scalar-finish',
                    board_hint=cfg.board, timeout_s=120.,
                    native_reporting_build=params.get('route_scalar_finish_reporting_build'))
            else:
                scalar_finish = dict(changed=False, skipped='finish_reserve', budget=funded, release_authority=False)
        except Exception as exc:                         # noqa: BLE001 -- optional private proposal never drops the incumbent
            scalar_finish = dict(changed=False,error='%s: %s' % (type(exc).__name__,exc),release_authority=False)
    if finish_baseline is not None:
        progress_polish_report = result.get('progress_polish')
        result, finish_admission = _admit_incumbent_finish(
            result, finish_baseline, incumbent_finish_before, output_dir,
            route_cfg, thermal=thermal)
        if finish_baseline.get('finish_source_origin'):
            origin = finish_baseline['finish_source_origin']
            result['candidate_origin'] = origin + '_polish' if finish_admission.get('admitted') else origin
            finish_admission['baseline_origin'] = origin
        result["incumbent_finish_admission"] = finish_admission
        if progress_polish_report is not None:
            result['progress_polish'] = progress_polish_report
        scalar_finish['coordinator_admitted'] = bool(scalar_finish.get('changed') and finish_admission.get('admitted'))
    result['source_scalar_finish'] = scalar_finish
    result['field_finish'] = field_finish

    report = output_dir / "oracle.json"
    copied.extend(_persist_route_search_history(result, residual_evidence, output_dir))
    atomic_json(report, result)
    atomic_json(batch_report, {
        "schema": 1, "bounded": True,
        "hard_cap": cec_search_policy.MAX_ROUTE_CANDIDATES,
        "requested": len(seeds), "seeds": list(seeds),
        "winner_seed": result.get("seed"),
        "winner_origin": result.get("candidate_origin", "proposal"),
        "executor": executor_evidence,
        "candidates": candidate_summary,
    })
    routed = result.get("routed")
    artifacts = [str(report), str(batch_report)] + copied
    if scalar_finish.get('report') and Path(scalar_finish['report']).is_file():
        artifacts.append(scalar_finish['report'])
    if incumbent is not None:
        artifacts.append(str(output_dir / "incumbent" / "oracle.json"))
    if routed and os.path.isfile(routed):
        artifacts += _copy_sidecars(routed, routed, cfg=cfg)
    return {
        "ok": bool(result.get("gate")),
        "artifact_produced": bool(routed and os.path.isfile(routed)),
        "winner_completion_enabled": bool(params.get("lastmile_final")),
        "candidate_budget": len(seeds),
        "winner_seed": result.get("seed"),
        "winner_origin": result.get("candidate_origin", "proposal"),
        "candidate_summary": str(batch_report),
        "dimension_repair": dimension_repair,
        "fab_repair": fab_repair,
        "source_scalar_finish": scalar_finish,
        "incumbent_finish_admission": result.get("incumbent_finish_admission"),
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
    import cec_hardware_qualification
    import cec_xfcn_contract
    import cec_mezz_contract
    hardware = cec_hardware_qualification.evaluate(
        [str(fp.GetFPID().GetLibItemName()) for fp in board_db.GetFootprints()],
        cec_xfcn_contract.hardware_release_requirements(board, cfg.sch)
        + cec_mezz_contract.hardware_release_requirements(board, cfg.sch))
    route_geometry = cec_route_quality.analyze_board(board_db)
    profile_name = cec_fab_profile.active_profile_name(
        board_db, hint=cfg.board
    )
    if profile_name:
        copper_oz = cec_fab_profile.stackup_oz(profile_name)["F.Cu"]
        fab = cec_fab_check.check(str(board), "jlcpcb", copper_oz, True)
    else:
        fab = {"error": "board has no declared fabrication profile"}

    # One complete manufacturing contract: hand-maintained subsets previously
    # omitted artifact acid traps, native opens and incomplete factory evidence.
    # The checker also counts unknown/unsupported evidence as blocking.
    fab_blockers = cec_fab_check.blocking_count(fab)
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
        # User-specified contour policy is not ordinary electrical DRC. A
        # canonical centerline can still produce huge native round-cap blobs.
        # An incomplete detector or unresolved owner request cannot silently
        # become a polished final-fab verdict. This never weakens the other
        # electrical, field, hardware or factory qualification gates.
        "power_contour_review": route_geometry.get("power_contour_review_ok") is True,
        "constraint_release": constraint_gate.get("ok") is True,
        "fabrication": fab_blockers == 0,
        "source_not_draft": not cfg.is_draft,
        "hardware_qualification": hardware['ok'],
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
        "hardware_qualification": hardware,
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
    fresh_placement_only=False, candidate_review_only=False,
    review_skip_route_probes=False, priority_repair_timeout=None,
):
    import cec_synth_pipeline as synth

    cfg = synth.Config.load(board_name)
    if priority_repair_timeout is not None:
        import math
        if (isinstance(priority_repair_timeout, bool)
                or not math.isfinite(float(priority_repair_timeout))
                or float(priority_repair_timeout) <= 0):
            raise ValueError('priority repair timeout must be finite and positive')
        cfg.params['priority_repair_operation_timeout_s'] = float(priority_repair_timeout)
    if review_skip_route_probes and not candidate_review_only:
        raise ValueError("skipping route probes is allowed only for candidate review")
    if candidate_review_only and not replace_placement:
        raise ValueError("initial candidate review requires replacement placement")
    if candidate_review_only:
        # Initial review measures the bounded shortlist but does not spend a
        # repair/search loop or perform any detailed-route adjudication.
        cfg.params["placement_route_repair_trials"] = 0
        cfg.params["route_oracle"] = False
        cfg.params["placement_candidates_only"] = True
        if review_skip_route_probes:
            cfg.params["placement_route_preflight_auto"] = False
            cfg.params["placement_route_preflight_topk"] = 0
            cfg.params["outline_compaction"] = dict(
                cfg.params.get("outline_compaction") or {}, probe_route_preflight=False)
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
    cfg.params.setdefault("placement_preflight_require_physical", True)
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
    # Keep expensive priority placement measurements/repairs out of the
    # coordinator's long-lived KiCad process. This prevents legacy SWIG
    # lifetime corruption from turning a valid post-authority board into a
    # nondeterministic attribute error later in the same stage.
    cfg.params.setdefault("priority_route_process_isolation", True)
    cfg.params.setdefault("route_authority_process_isolation", True)
    cfg.params.setdefault("fiducial_process_isolation", True)
    cfg.params.setdefault("placement_measure_process_isolation", True)
    # One repair pass can invalidate its own exact power reservation geometry.
    # Permit one bounded follow-up against the regenerated authority; the
    # placement-stage transaction keeps only strict post-authority progress.
    cfg.params.setdefault("placement_power_route_coopt_rounds", 3)
    cfg.params.setdefault("placement_power_replan_candidates", 2)
    input_board = Path(input_board or cfg.pcb).resolve()
    import cec_interface_eco
    try:
        eco_record = cec_interface_eco.read_status(input_board)
        if eco_record and eco_record.get('route_authority_invalidated') and not replace_placement:
            raise ValueError('interface ECO input requires --replace-placement; retained copper is not route authority')
    except ValueError as exc:
        raise PipelineBlocked(str(exc)) from exc
    if not input_board.is_file():
        raise FileNotFoundError(
            "no current placement board; pass --input-board explicitly"
        )
    canonical_input_board = input_board
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    board_identity = _board_identity(cfg)
    journal = StageJournal(out_dir / "pipeline-state.json", board_identity,
                           resume=resume)
    # Refuse an unsatisfiable shared interface before normalizing the source
    # or spending any placement/routing work. A later pad DRC cannot repair
    # a bad shared datum map, and a new random seed cannot change its span.
    import cec_xfcn_contract
    mating = cec_xfcn_contract.mating_compilation_gate(cfg.sch)
    if mating['applicable']:
        mating = journal.run('interface_compilation', digest_value({
            'input': sha256_file(input_board), 'gate': mating,
            'code': _code_signature('cec_xfcn_contract.py', 'cec_mating_rows.py'),
        }), lambda: mating)
        if mating.get('ok') is not True:
            error = PipelineBlocked('mating geometry conflict; revise the shared interface before retrying')
            error.failure_evidence = mating
            raise error
    cfg, route_authority = synth.config_with_board_route_authority(
        cfg, str(input_board))
    if route_authority.get("applicable") and not route_authority.get("ok"):
        raise PipelineBlocked(
            "input route authority refused: %s" %
            route_authority.get("reason", "unknown"))
    source_normalization = None
    if _source_normalization_requested(
            replace_placement=replace_placement,
            fresh_placement_only=fresh_placement_only, params=cfg.params,
            input_board=canonical_input_board, canonical_board=cfg.pcb,
            allow_derived_input=allow_derived_input):
        canonical_signature = _files_signature(
            _source_files(cfg, canonical_input_board))
        source_normalization = journal.run(
            "source_normalization",
            digest_value({
                "source": canonical_signature["sha256"],
                "board": board_identity,
                "policy": cfg.params,
                "code": _code_closure_signature(
                    "cec_sync_pcb_from_schematic.py"),
                "coordinator": _callable_signature(
                    _normalize_schematic_first_source),
            }),
            lambda: _normalize_schematic_first_source(
                cfg, canonical_input_board, out_dir),
        )
        if not source_normalization.get("ok"):
            raise PipelineBlocked(
                "schematic-first source normalization refused; see %s" %
                source_normalization.get("report"))
        input_board = Path(source_normalization["board"]).resolve()
    source_signature = _files_signature(_source_files(cfg, input_board))
    common = {
        "source": source_signature["sha256"],
        "board": board_identity,
        "policy": cfg.params,
        "route_authority": route_authority,
        "source_normalization": (
            digest_value(source_normalization)
            if source_normalization is not None else None),
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
            "cec_sch_gates.py", "cec_part_semantics.py", "cec_xfcn_contract.py"
        ), "coordinator": _callable_signature(_source_intake)}),
        lambda: {
            **_source_intake(
                cfg, input_board, intake_path,
                allow_derived_input=(
                    allow_derived_input
                    or source_normalization is not None)),
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
            "candidate_review_only": candidate_review_only,
            "review_skip_route_probes": review_skip_route_probes,
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
            candidate_review_only=candidate_review_only,
        ),
    )
    if candidate_review_only:
        return {
            "status": "PLACEMENT_CANDIDATES_REVIEW",
            "placement": placement, "routed_board": None,
            "signoff": {"ok": False, "failed_terms": ["not_run_placement_review"]},
            "source_intake": str(intake_path),
            "journal": str(out_dir / "pipeline-state.json"),
        }
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
            "code": _code_closure_signature(
                "cec_route_preflight.py", "cec_coord_router.py",
                "cec_route_awareness_service.py", "cec_pair_return.py",
                "cec_preflight_native_recovery.py"
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

    routing_input = Path(preflight.get('board') or placed_board).resolve()

    route_access_repair = _route_access_repair_allowed(
        intake, placement)
    route = journal.run(
        "precision_detailed_route",
        digest_value({
            **common, "placement": sha256_file(placed_board),
            "routing_input": sha256_file(routing_input),
            "preflight": sha256_file(preflight["report"]),
            "passes": passes, "opt": opt, "seed": route_seed,
            "route_candidates": route_candidates,
            "route_workers": route_workers,
            "timeout": route_timeout, "thermal": thermal,
            "allow_route_access_repair": route_access_repair,
            "dimension_repair_policy": {
                "enabled": os.environ.get("CEC_DIMENSION_REPAIR", "1"),
                "wall_budget_s": os.environ.get("CEC_DIMENSION_REPAIR_WALL_S", "120"),
            },
            "code": _code_closure_signature(
                "cec_synth_pipeline.py", "cec_precision_route.py",
                "cec_staged_fr.py", "cec_pair_return.py",
                "cec_decoupler_cell.py", "cec_ground_plane.py",
                "cec_completion_evidence.py", "cec_fab_repair.py",
                "cec_dimension_repair.py",
                "cec_search_policy.py", "cec_pour_clearance.py",
                "cec_constraints.py"
            ), "coordinator": _callable_signature(_route_stage),
        }),
        lambda: _route_stage(
            routing_input, out_dir / "04-route", cfg, passes=passes,
            opt=opt, seed=route_seed, timeout=route_timeout, thermal=thermal,
            candidates=route_candidates, route_workers=route_workers,
            allow_route_access_repair=route_access_repair,
        ),
    )
    routed_board = Path(route.get("board") or routing_input).resolve()
    signoff_path = out_dir / "05-signoff.json"
    import cec_xfcn_contract
    qualification_inputs = []
    import cec_mezz_contract
    for requirement in (cec_xfcn_contract.hardware_release_requirements(routed_board, cfg.sch)
                        + cec_mezz_contract.hardware_release_requirements(routed_board, cfg.sch)):
        qualification_inputs.extend([requirement['status_path'],
                                     *requirement.get('candidate_dependencies', ())])
    signoff = journal.run(
        "independent_signoff",
        digest_value({
            **common, "routed": sha256_file(routed_board),
            "oracle": sha256_file(route["report"]),
            "hardware_qualification_inputs": _files_signature(qualification_inputs),
            "hardware_qualification_code": _code_closure_signature(
                "cec_hardware_qualification.py", "cec_xfcn_contract.py",
                "cec_mezz_contract.py", "cec_stack_fit_screen.py", "cec_assembly_access.py"),
            "code": _code_closure_signature(
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
            (_requires_frozen_route_authority(cfg)
             and not authority.get("bound"))):
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
    parser.add_argument(
        "--placement-candidates-only", action="store_true",
        help=("with --replace-placement, retain the exact evaluated initial "
              "shortlist for review and stop before craft repair/routing; "
              "does not grant routing or release admission"))
    parser.add_argument("--strategies", default="plain,dataflow,thermal,hybrid")
    parser.add_argument(
        "--review-skip-route-probes", action="store_true",
        help="candidate review only: measure placement craft without route feasibility probes; never grants routing admission")
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
    parser.add_argument("--priority-repair-timeout", type=float, default=None,
                        help="Explicit critical-placement repair operation budget; campaign deadline still applies")
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
    if args.review_skip_route_probes and not args.placement_candidates_only:
        parser.error("--review-skip-route-probes requires --placement-candidates-only")
    if args.fresh_placement_only and not args.replace_placement:
        parser.error("--fresh-placement-only requires --replace-placement")
    if args.placement_candidates_only and (
            not args.replace_placement or args.route_only_probe):
        parser.error("--placement-candidates-only requires --replace-placement and cannot route")
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
        candidate_review_only=args.placement_candidates_only,
        review_skip_route_probes=args.review_skip_route_probes,
        priority_repair_timeout=args.priority_repair_timeout,
    )
    print("\n%s" % json.dumps({
        "status": result["status"],
        "routed_board": result["routed_board"],
        "failed_terms": result["signoff"].get("failed_terms"),
        "dashboard": result.get("dashboard"),
        "journal": result["journal"],
    }, indent=2))
    return 0 if result["status"] in {"RELEASED", "PLACEMENT_CANDIDATES_REVIEW"} else 2


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
