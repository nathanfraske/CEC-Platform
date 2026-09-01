#!/usr/bin/env python3
"""Guarded certificate-driven local routing repair.

The global router and the bounded last-mile completer deliberately refuse when
they cannot prove a clear path.  Their refusal certificates retain exact KiCad
UUIDs for the copper that blocked the search.  This module turns that evidence
into a deterministic, bounded repair ladder:

* only a track named by a refusal certificate is eligible;
* DRC-conflicting tracks rank before merely congesting tracks;
* locked, coupled, Kelvin/sense, plane and high-current copper is immutable;
* one segment is removed and reconnected between its original endpoints using
  the same exact collision/edge guards as the last-mile completer;
* progressively larger local mazes and, lastly, a through-via bridge are tried;
* a candidate is adopted only when full-board DRC/connectivity improves without
  regressing either hard pair gate.

This is intentionally local copper surgery, not a second global autorouter.  A
certificate is evidence for where to spend bounded search, never permission to
force a route or weaken a rule.
"""

from __future__ import annotations

import argparse
import contextvars
import copy
import itertools
import json
import math
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pcbnew

import cec_fab_profile as _fab
import cec_fr
import cec_process_pool
import cec_score
import cec_stage_admission
import cec_toolchain as _tc


MM = 1_000_000
SCHEMA = 1
REPAIR_ALGORITHM_REVISION = \
    "2026-08-31-laid-pour-aware-diverse-endpoints-v43"
_WORKER_DEADLINE = contextvars.ContextVar(
    "cec_certificate_worker_deadline", default=None)


def _is_gnd_net(net: str) -> bool:
    return str(net).rsplit("/", 1)[-1].upper() in {
        "GND", "AGND", "PGND", "GNDA", "GNDD", "DGND"}


@dataclass
class RepairEffortBudget:
    """Bound candidate enumeration without weakening any admission gate.

    The certificate ladder contains several independently bounded searches.
    Their Cartesian product can still become large on a board with many live
    DRC identities.  This coordinator gives the *whole* repair transaction a
    deterministic trial and wall-clock envelope while retaining small,
    stage-specific reserves for later connectivity negotiation.
    """

    max_attempts: int = 64
    wall_budget_s: float = 240.0
    started: float = field(default_factory=time.monotonic)
    attempts_started: int = 0
    stage_attempts: dict[str, int] = field(default_factory=dict)
    stage_stops: dict[str, str] = field(default_factory=dict)
    stop_reason: str | None = None
    stop_stage: str | None = None

    def _global_stop(self, stage: str) -> str | None:
        if self.stop_reason:
            return self.stop_reason
        if self.attempts_started >= max(0, int(self.max_attempts)):
            self.stop_reason = "global_attempt_budget"
        elif time.monotonic() - self.started >= max(
                0.0, float(self.wall_budget_s)):
            self.stop_reason = "wall_budget"
        if self.stop_reason:
            self.stop_stage = stage
        return self.stop_reason

    def claim(self, stage: str, *, stage_limit: int | None = None) -> bool:
        """Reserve one candidate trial before copying or mutating a board."""

        if self._global_stop(stage):
            return False
        used = int(self.stage_attempts.get(stage, 0))
        if stage_limit is not None and used >= max(0, int(stage_limit)):
            self.stage_stops.setdefault(stage, "stage_attempt_budget")
            return False
        self.attempts_started += 1
        self.stage_attempts[stage] = used + 1
        return True

    def remaining_wall_s(self) -> float:
        """Return the transaction time that has not yet been consumed."""

        return max(0.0, float(self.wall_budget_s) -
                   (time.monotonic() - self.started))

    def remaining_attempts(self) -> int:
        """Return candidate slots that have not yet been claimed."""

        return max(0, int(self.max_attempts) - self.attempts_started)

    def claim_before_reserve(self, stage: str, *,
                             stage_limit: int | None = None,
                             reserve_wall_s: float = 0.0,
                             reserve_attempts: int = 0,
                             trial_wall_s: float = 0.0) -> bool:
        """Claim work only when it cannot consume a later-stage reserve.

        A global wall clock prevents runaway waves, but by itself lets an
        early exhaustive search starve cheaper topology negotiation.  This
        admission check leaves both time and trial slots for later stages.  A
        reserve stop is local to ``stage``; it does not poison the transaction
        or prevent the reserved stage from running.
        """

        if self._global_stop(stage):
            return False
        if self.remaining_attempts() <= max(0, int(reserve_attempts)):
            self.stage_stops.setdefault(stage, "later_stage_attempt_reserve")
            return False
        needed_wall_s = (max(0.0, float(reserve_wall_s)) +
                         max(0.0, float(trial_wall_s)))
        if self.remaining_wall_s() <= needed_wall_s:
            self.stage_stops.setdefault(stage, "later_stage_wall_reserve")
            return False
        return self.claim(stage, stage_limit=stage_limit)

    def available(self, stage: str) -> bool:
        """Return whether non-trial stage work remains inside the wall budget."""

        return self._global_stop(stage) is None

    def stage_stop(self, stage: str, fallback: str) -> str:
        return self.stage_stops.get(stage) or self.stop_reason or fallback

    def report(self) -> dict:
        return {
            "schema": 1,
            "max_attempts": max(0, int(self.max_attempts)),
            "wall_budget_s": max(0.0, float(self.wall_budget_s)),
            "attempts_started": int(self.attempts_started),
            "stage_attempts": dict(sorted(self.stage_attempts.items())),
            "stage_stops": dict(sorted(self.stage_stops.items())),
            "stop_reason": self.stop_reason,
            "stop_stage": self.stop_stage,
            "wall_s": round(time.monotonic() - self.started, 3),
        }


@dataclass(frozen=True)
class RepairTarget:
    """One evidence-backed, policy-qualified movable track."""

    uuid: str
    net: str
    layer: str
    hit_count: int
    blocked_nets: tuple[str, ...]
    reservations: tuple[dict, ...]
    drc_types: tuple[str, ...]
    drc_conflict: bool
    priority: tuple
    sensitive_repair: bool = False


@dataclass(frozen=True)
class ViaRepairTarget:
    """One unlocked via named by a live structural DRC violation.

    Locked priority copper remains immutable.  When the other side of an
    exact clearance identity is an unlocked via, relocating the lower-
    authority barrel and rebuilding its incident stubs is strictly safer than
    weakening or unlocking the already-proved route.
    """

    uuid: str
    net: str
    x_nm: int
    y_nm: int
    diameter_nm: int
    drill_nm: int
    counterpart_uuids: tuple[str, ...]
    drc_types: tuple[str, ...]
    away_dx: int
    away_dy: int
    priority: tuple


@dataclass(frozen=True)
class NegotiationWindow:
    """One refused connection plus the movable blockers in its local window."""

    net: str
    distance_mm: float
    width_mm: float
    clearance_mm: float
    blocker_uuids: tuple[str, ...]
    blocker_nets: tuple[str, ...]
    blocker_hits: int
    omitted_movable_blockers: int
    fixed_blocker_hits: int
    trapped_endpoints: int
    endpoints: tuple[dict, ...]
    priority: tuple
    unlock_uuids: tuple[str, ...] = ()
    local_pin_escape: bool = False
    vertical_pofv_escape: bool = False
    vertical_blocker_layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FootprintRepairTarget:
    """A movable support footprint certified as sealing a routed pin.

    This is deliberately narrower than ordinary placement optimization.  The
    router must have reported a trapped endpoint and named one foreign SMD
    footprint's pads in the failed escape rays.  Only a small, unlocked,
    two-terminal support cell is eligible for the transactional re-seat.
    """

    ref: str
    target_net: str
    endpoint_ref: str
    endpoint_pad: str
    endpoint_x_mm: float
    endpoint_y_mm: float
    hit_count: int
    distance_mm: float
    priority: tuple
    motion: str = "away_from_endpoint"
    companion_refs: tuple[str, ...] = ()


def _uuid(item) -> str:
    try:
        return item.m_Uuid.AsString()
    except Exception:  # noqa: BLE001 - old pcbnew bindings
        return ""


def _copy_board_family(source: str, destination: str) -> None:
    """Copy a board and every executable route-ownership sidecar.

    Certificate repair is an intermediate producer, not a new design source.
    Dropping the pour-plan/frozen-state sidecars here makes downstream routing
    and dashboard analysis reconstruct a different current-copper contract
    for the repaired board.  Use the shared family copier so project rules,
    pour authority, and ranking provenance all survive every trial/adoption.
    """

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)


def _repair_attempt_completion_payload(row: dict) -> dict:
    """Reduce a prior repair report to its latest live refusal evidence.

    Certificate repair is intentionally wave-bounded.  Its report therefore
    must be a valid input to the next wave, not merely human telemetry.  Walk
    attempts in execution order, replace older evidence for the same endpoint
    pair, and remove a net's certificates when a later accepted completion
    closed it.  This makes blocker discovery cumulative without carrying
    already-resolved or pre-negotiation geometry forward.
    """

    latest = {}

    def endpoint_key(detail):
        certificate = detail.get("certificate") or {}
        net = str(certificate.get("net") or detail.get("net") or "")
        endpoints = certificate.get("endpoints") or ()
        endpoint_rows = []
        for endpoint in endpoints:
            endpoint_rows.append((
                str(endpoint.get("ref") or ""),
                str(endpoint.get("pad") or ""),
                round(float(endpoint.get("x_mm") or 0.0), 6),
                round(float(endpoint.get("y_mm") or 0.0), 6),
            ))
        return net, tuple(sorted(endpoint_rows))

    def absorb_report(report, *, committed=False):
        if committed:
            closed_nets = {
                str(detail.get("net") or "")
                for detail in report.get("closed_details") or ()
                if str(detail.get("net") or "")}
            for key in list(latest):
                if key[0] in closed_nets:
                    latest.pop(key, None)
        for detail in report.get("refused_details") or ():
            key = endpoint_key(detail)
            if key[0]:
                latest[key] = copy.deepcopy(detail)

    # A bounded placement-only wave may consume all of its wall clock before
    # producing a route attempt.  Its fresh probe is still the current refusal
    # authority and must seed the next wave; otherwise valid trapped-support
    # targets disappear simply because placement was tried once.
    planning_evidence = ((row.get("plan") or {}).get(
        "planning_refusal_evidence"))
    if isinstance(planning_evidence, dict):
        absorb_report(planning_evidence)
    live_probe = ((row.get("plan") or {}).get("live_refusal_probe"))
    if isinstance(live_probe, dict):
        absorb_report(live_probe)

    for attempt in row.get("attempts") or ():
        candidates = []
        if isinstance(attempt.get("completion"), dict):
            candidates.append(attempt["completion"])
        close = ((attempt.get("phases") or {}).get("close") or {})
        if isinstance(close.get("completion"), dict):
            candidates.append(close["completion"])
        # The exact-pair worker returns its best current certificate beside
        # the coarse completion wrapper.  On a bounded timeout that wrapper
        # intentionally contains no ``refused_details``; dropping the sibling
        # certificate made the next wave and the placement fallback blind to
        # the very pin field that exhausted route search.  Normalize it into
        # the ordinary completion schema while the window still provides the
        # certified net/distance identity.
        exact = close.get("exact_pair_refusal") or {}
        certificate = exact.get("certificate") or {}
        window = attempt.get("window") or {}
        if certificate:
            candidates.append({
                "schema": 1,
                "closed": 0,
                "refused": 1,
                "refused_details": [{
                    "net": str(certificate.get("net") or
                               window.get("net") or ""),
                    "distance_mm": float(window.get("distance_mm") or 0.0),
                    "certificate": copy.deepcopy(certificate),
                    "source": "atomic_exact_pair_refusal",
                }],
            })
        for report in candidates:
            # A target-only scratch route is not current board state when its
            # composite transaction later fails restoration or DRC.  Only an
            # admitted attempt may erase the prior live refusal certificate.
            absorb_report(report, committed=bool(attempt.get("accepted")))
    live = set(((row.get("final") or {}).get("unconn_nets") or ()))
    refused = [detail for key, detail in sorted(latest.items())
               if not live or key[0] in live]
    return {
        "schema": 1,
        "unconn_nets": sorted(live),
        "refused": len(refused),
        "refused_details": refused,
        "source": "certificate_repair_attempt_ledger",
    }


def _completion_payload(data: dict | None) -> dict:
    """Accept an oracle row, an import report, or a bare completion report."""

    row = data or {}
    if isinstance(row.get("completion_report"), dict):
        row = row["completion_report"]
    if isinstance(row.get("import_report"), dict):
        row = row["import_report"]
    # Short-lived exact-completion workers publish their route result under
    # ``completion`` alongside generated-UUID evidence.  Treat that as the
    # same refusal-certificate schema; otherwise a perfectly current trapped
    # endpoint report appears certificate-free and the repair ladder falls
    # through to an unrelated whole-board closure search.
    if isinstance(row.get("completion"), dict):
        row = row["completion"]
    if isinstance(row.get("attempts"), list) and isinstance(
            row.get("final"), dict):
        row = _repair_attempt_completion_payload(row)
    return row


def refusal_certificates(data: dict | None) -> list[dict]:
    """Return unique refusal rows from every completion stage in *data*."""

    payload = _completion_payload(data)
    reports = []
    for name in ("final_completion", "lastmile"):
        if isinstance(payload.get(name), dict):
            reports.append(payload[name])
    if isinstance(payload.get("refused_details"), list):
        reports.append(payload)
    rows, seen = [], set()
    for report in reports:
        for detail in report.get("refused_details") or ():
            cert = detail.get("certificate") or {}
            if not cert:
                continue
            key = json.dumps(cert, sort_keys=True, separators=(",", ":"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"detail": detail, "certificate": cert})
    rows.sort(key=lambda row: (
        float(row["detail"].get("distance_mm") or 1e9),
        str(row["certificate"].get("net") or "")))
    return rows


def _planning_completion_with_live_report(completion, live_unconnected,
                                          live_report):
    """Replace inherited refusal geometry with a current-board probe.

    Router oracles often wrap completion data under ``completion_report``.
    Merely assigning a top-level ``unconn_nets`` list filters stale nets but
    leaves every nested certificate, coordinate and blocker UUID untouched.
    Build the planning payload from the unwrapped completion row and make the
    isolated current-board probe the sole refusal source.
    """

    payload = copy.deepcopy(_completion_payload(completion))
    payload["unconn_nets"] = list(live_unconnected or ())
    if isinstance(live_report, dict):
        payload["final_completion"] = copy.deepcopy(live_report)
        payload.pop("lastmile", None)
        payload.pop("refused_details", None)
    return payload


def _run_drc(board_path: str, destination: str) -> dict:
    cli = _tc.require_kicad_cli("certificate repair DRC")
    subprocess.run(
        [cli, "pcb", "drc", "--exit-code-violations", "--format", "json",
         "-o", destination, board_path],
        capture_output=True, check=False,
    )
    with open(destination, encoding="utf-8") as source:
        return json.load(source)


def _drc_track_index(drc_data: dict | None) -> dict[str, set[str]]:
    """Map exact track UUIDs to structural DRC types that name them."""

    out: dict[str, set[str]] = {}
    for violation in (drc_data or {}).get("violations") or ():
        kind = str(violation.get("type") or "")
        if kind in cec_score.COSMETIC_DRC_TYPES:
            continue
        for item in violation.get("items") or ():
            desc = str(item.get("description") or "")
            if not desc.startswith(("Track ", "Arc ")):
                continue
            uid = str(item.get("uuid") or "")
            if uid:
                out.setdefault(uid, set()).add(kind)
    return out


def _closest_point_on_track(point, track):
    """Return the closest integer-nanometre point on a straight track."""

    start, end = track.GetStart(), track.GetEnd()
    vx, vy = end.x - start.x, end.y - start.y
    wx, wy = point.x - start.x, point.y - start.y
    length2 = vx * vx + vy * vy
    if length2 <= 0:
        return start
    scale = max(0.0, min(1.0, (wx * vx + wy * vy) / float(length2)))
    return pcbnew.VECTOR2I(
        int(round(start.x + scale * vx)),
        int(round(start.y + scale * vy)),
    )


def _octant_away(dx: int, dy: int, *, fallback=(1, 0)) -> tuple[int, int]:
    """Snap an obstacle-away vector to a canonical 0/45/90 direction."""

    ax, ay = abs(int(dx)), abs(int(dy))
    if ax == 0 and ay == 0:
        return tuple(int(value) for value in fallback)
    sx = 0 if dx == 0 else (1 if dx > 0 else -1)
    sy = 0 if dy == 0 else (1 if dy > 0 else -1)
    if ax >= 2 * max(1, ay):
        return sx, 0
    if ay >= 2 * max(1, ax):
        return 0, sy
    return sx, sy


def plan_via_repairs(board_path: str, drc_data: dict | None, *,
                     limit: int = 8) -> dict:
    """Plan relocations for unlocked vias in exact live DRC identities.

    This does not infer candidates from proximity.  A via is eligible only
    when KiCad names its UUID in a structural route-fault violation, and an
    in-pad/via-on-pad barrel is never moved.  The counterpart geometry is used
    only to rank an initial canonical direction away from the conflict; full
    DRC and connectivity remain the admission authority.
    """

    board = pcbnew.LoadBoard(board_path)
    route_items = {_uuid(item): item for item in board.GetTracks() if _uuid(item)}
    pad_hits = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            pad_hits.append(pad)
    aggregate = {}
    route_fault_types = set(cec_score.SENSE_FAULT_DRC_TYPES)
    for violation in (drc_data or {}).get("violations") or ():
        kind = str(violation.get("type") or "")
        if kind not in route_fault_types:
            continue
        items = violation.get("items") or ()
        uuids = tuple(sorted(str(row.get("uuid") or "") for row in items
                             if row.get("uuid")))
        for row in items:
            uid = str(row.get("uuid") or "")
            via = route_items.get(uid)
            if via is None or via.GetClass() != "PCB_VIA" or via.IsLocked():
                continue
            pos = via.GetPosition()
            # A POFV or ordinary via-on-pad is package/pad infrastructure.  It
            # may be resized only by the qualified footprint/process flow, not
            # translated by a route cleanup pass.
            on_pad = any(
                pad.GetNetCode() == via.GetNetCode()
                and pad.GetBoundingBox().Contains(pos)
                for pad in pad_hits)
            if on_pad:
                continue
            entry = aggregate.setdefault(uid, {
                "via": via, "types": set(), "counterparts": set(),
                "vectors": [],
            })
            entry["types"].add(kind)
            for other_uid in uuids:
                if not other_uid or other_uid == uid:
                    continue
                entry["counterparts"].add(other_uid)
                other = route_items.get(other_uid)
                if other is None:
                    continue
                if other.GetClass() in {"PCB_TRACK", "PCB_ARC"}:
                    closest = _closest_point_on_track(pos, other)
                    dx, dy = pos.x - closest.x, pos.y - closest.y
                    if dx == 0 and dy == 0:
                        start, end = other.GetStart(), other.GetEnd()
                        dx, dy = -(end.y - start.y), end.x - start.x
                elif other.GetClass() == "PCB_VIA":
                    other_pos = other.GetPosition()
                    dx, dy = pos.x - other_pos.x, pos.y - other_pos.y
                else:
                    continue
                entry["vectors"].append((dx, dy))

    targets = []
    for uid, entry in aggregate.items():
        via = entry["via"]
        vectors = entry["vectors"]
        if vectors:
            # The largest separation deficit normally dominates a multi-item
            # identity.  Summing sign-normalized vectors also avoids an
            # arbitrary UUID-dependent direction when two obstacles agree.
            dx = sum(_octant_away(x, y)[0] for x, y in vectors)
            dy = sum(_octant_away(x, y)[1] for x, y in vectors)
            away = _octant_away(dx, dy)
        else:
            away = (1, 0)
        pos = via.GetPosition()
        targets.append(ViaRepairTarget(
            uuid=uid, net=str(via.GetNetname() or ""),
            x_nm=int(pos.x), y_nm=int(pos.y),
            diameter_nm=int(via.GetWidth(via.TopLayer())),
            drill_nm=int(via.GetDrillValue()),
            counterpart_uuids=tuple(sorted(entry["counterparts"])),
            drc_types=tuple(sorted(entry["types"])),
            away_dx=int(away[0]), away_dy=int(away[1]),
            priority=(0, -len(entry["types"]), uid),
        ))
    targets.sort(key=lambda target: target.priority)
    return {
        "schema": 1,
        "board": os.path.abspath(board_path),
        "targets": [asdict(target) for target in targets[:max(0, int(limit))]],
        "eligible": len(targets),
    }


def _structural_drc_identities(drc_data: dict | None) -> list[str]:
    """Stable identities for non-cosmetic KiCad DRC violations.

    A repair is not monotonic merely because the total DRC count did not rise:
    it may remove one clearance fault while creating a new short elsewhere.
    UUID-backed identities let the admission gate reject that debt swap.  The
    compact JSON encoding also survives multiprocessing without tuple/list
    ambiguity.
    """

    # Match the electrical route-fault class used by pair/Kelvin signoff.
    # Footprint-internal/profile-qualified hole findings are filtered by
    # cec_score and are not movable track-route debt.
    route_fault_types = set(cec_score.SENSE_FAULT_DRC_TYPES)
    identities = set()
    for violation in (drc_data or {}).get("violations") or ():
        kind = str(violation.get("type") or "")
        if kind not in route_fault_types:
            continue
        uuids = sorted(
            str(item.get("uuid") or "")
            for item in (violation.get("items") or ())
            if item.get("uuid"))
        if uuids:
            identity = [kind, "uuid", uuids]
        else:
            fallback = sorted([
                str(item.get("description") or ""),
                round(float((item.get("pos") or {}).get("x") or 0.0), 4),
                round(float((item.get("pos") or {}).get("y") or 0.0), 4),
            ] for item in (violation.get("items") or ()))
            identity = [kind, "fallback",
                        str(violation.get("description") or ""), fallback]
        identities.add(json.dumps(
            identity, sort_keys=True, separators=(",", ":")))
    return sorted(identities)


_COUPLED_RE = re.compile(
    r"(?:^|[/_])(CAN_[HL]|USB_D_[PN]|USB_[PN]|D[PN]|CLK_[PN]|TX_[PN]|RX_[PN])$",
    re.IGNORECASE,
)


def protected_net_reason(net: str, *, width_mm: float = 0.0,
                         layer: str = "", locked: bool = False) -> str | None:
    """Return why automatic single-segment surgery must not touch *net*.

    The policy is deliberately name-light: locked/wide geometry is the primary
    signal.  Names only cover electrical structures whose phase/skew or
    measurement topology a local single-net repair cannot independently prove.
    """

    upper = (net or "").upper()
    if locked:
        return "locked_copper"
    # Ordinary 1.0 mm local supply branches remain eligible: the replacement
    # keeps the exact width and is independently DRC-scored.  Copper wider than
    # that is a lane/trunk/pour pickup whose impedance and thermal intent cannot
    # be certified by a local topological repair alone.
    if width_mm > 1.0 + 1e-9:
        return "wide_or_high_current"
    if upper.endswith(("_HI", "_LO")) or "KELVIN" in upper:
        return "kelvin_or_sense"
    if _COUPLED_RE.search(upper) or "CAN_H" in upper or "CAN_L" in upper:
        return "coupled_pair"
    # A track *on* a plane-role layer is not itself the plane.  Narrow,
    # unlocked local branches may be rerouted there with exact zone/copper
    # collision checks, or bridged onto a non-plane signal layer by
    # _layer_candidates().  Treating the layer name alone as authorship made
    # ordinary +3V3/VCC crossings impossible to repair.  Actual plane zones,
    # locked prefixes, and wide current trunks never enter this track-only
    # surgery path.
    return None


def plan_repairs(board_path: str, completion: dict | None, *,
                 drc_data: dict | None = None, limit: int = 12) -> dict:
    """Build a deterministic repair plan from certificates and real board state."""

    board = pcbnew.LoadBoard(board_path)
    tracks = {_uuid(item): item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK" and _uuid(item)}
    drc_index = _drc_track_index(drc_data)
    aggregate: dict[str, dict] = {}
    immutable = []
    for row in refusal_certificates(completion):
        cert = row["certificate"]
        blocked = str(cert.get("net") or row["detail"].get("net") or "")
        for blocker in cert.get("dominant_blockers") or ():
            if blocker.get("kind") != "track" or not blocker.get("uuid"):
                continue
            uid = str(blocker["uuid"])
            item = tracks.get(uid)
            if item is None:
                continue
            entry = aggregate.setdefault(uid, {
                "item": item, "hit_count": 0, "blocked_nets": set(),
                "certificate_layers": set(), "reservations": {},
            })
            entry["hit_count"] += int(blocker.get("hit_count") or 1)
            if blocked:
                entry["blocked_nets"].add(blocked)
                ends = cert.get("endpoints") or ()
                if len(ends) >= 2:
                    reservation = {
                        "net": blocked,
                        "a": [float(ends[0]["x_mm"]),
                              float(ends[0]["y_mm"])],
                        "b": [float(ends[1]["x_mm"]),
                              float(ends[1]["y_mm"])],
                        "a_owner": {key: ends[0].get(key)
                                    for key in ("kind", "ref", "pad")
                                    if ends[0].get(key) is not None},
                        "b_owner": {key: ends[1].get(key)
                                    for key in ("kind", "ref", "pad")
                                    if ends[1].get(key) is not None},
                        "width_mm": float(cert.get("width_mm") or 0.25),
                        "clearance_mm": float(
                            cert.get("clearance_mm") or 0.25),
                    }
                    rkey = json.dumps(reservation, sort_keys=True,
                                      separators=(",", ":"))
                    entry["reservations"][rkey] = reservation
            if blocker.get("layer"):
                entry["certificate_layers"].add(str(blocker["layer"]))

    # Structural DRC is independent repair evidence.  Previously an unlocked
    # offending track became selectable only when a completion-refusal
    # certificate also happened to name it as a congestion blocker.  That
    # left legal local reroutes unused on boards whose residual router created
    # a clearance or short but whose open nets were elsewhere.  Seed those
    # exact UUIDs directly; the normal protected-net policy and transactional
    # full-board admission below still decide whether they may move.
    for uid, drc_types in drc_index.items():
        item = tracks.get(uid)
        if item is None:
            continue
        entry = aggregate.setdefault(uid, {
            "item": item, "hit_count": 0, "blocked_nets": set(),
            "certificate_layers": set(), "reservations": {},
        })
        entry["hit_count"] = max(
            int(entry["hit_count"]), max(1, len(drc_types)))
        entry["certificate_layers"].add(
            board.GetLayerName(item.GetLayer()))

    targets = []
    for uid, entry in aggregate.items():
        item = entry["item"]
        net = item.GetNetname() or ""
        layer = board.GetLayerName(item.GetLayer())
        width_mm = item.GetWidth() / MM
        reason = protected_net_reason(
            net, width_mm=width_mm, layer=layer, locked=item.IsLocked())
        if reason:
            immutable.append({
                "uuid": uid, "net": net, "layer": layer,
                "width_mm": round(width_mm, 6), "reason": reason,
                "hit_count": entry["hit_count"],
                "blocked_nets": sorted(entry["blocked_nets"]),
            })
            continue
        drc_types = tuple(sorted(drc_index.get(uid, ())))
        # Prefer a real DRC offender, then blockers shared by more refused
        # connections, then frequency and UUID for deterministic ties.
        priority = (
            0 if drc_types else 1,
            -len(entry["blocked_nets"]),
            -int(entry["hit_count"]),
            uid,
        )
        targets.append(RepairTarget(
            uuid=uid, net=net, layer=layer,
            hit_count=int(entry["hit_count"]),
            blocked_nets=tuple(sorted(entry["blocked_nets"])),
            reservations=tuple(entry["reservations"][key]
                               for key in sorted(entry["reservations"])),
            drc_types=drc_types, drc_conflict=bool(drc_types),
            priority=priority,
        ))
    targets.sort(key=lambda row: row.priority)
    immutable.sort(key=lambda row: (-row["hit_count"], row["uuid"]))
    return {
        "schema": SCHEMA,
        "board": os.path.abspath(board_path),
        "certificates": len(refusal_certificates(completion)),
        "targets": [asdict(row) for row in targets[:max(0, int(limit))]],
        "immutable": immutable,
        "drc_named_track_count": len(drc_index),
    }


def plan_sensitive_drc_repairs(board_path: str, drc_data: dict | None, *,
                               limit: int = 4) -> dict:
    """Select narrowly recoverable locked measurement copper.

    Priority routing deliberately locks copper after it has passed its
    electrical checks.  Older staged-router releases could nevertheless lock
    a newly-created clearance defect because their promotion gate tolerated a
    bounded DRC increase.  Treating every locked track as movable would erase
    the meaning of that ownership boundary, so recovery is intentionally
    limited to an exact live clearance UUID on an ungrouped Kelvin/sense net.

    Coupled pairs, wide current copper, and explicitly grouped geometry remain
    immutable.  The caller must still prove the replacement with the shared
    full-board admission contract and must reject any new measurement or route
    topology fault.
    """

    board = pcbnew.LoadBoard(board_path)
    tracks = {_uuid(item): item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK" and _uuid(item)}
    drc_index = _drc_track_index(drc_data)
    grouped = {
        _uuid(item)
        for group in board.Groups()
        for item in tracks.values()
        if group.ContainsItem(item)
    }
    targets = []
    immutable = []
    for uid, drc_types_raw in sorted(drc_index.items()):
        item = tracks.get(uid)
        if item is None or not item.IsLocked():
            continue
        net = item.GetNetname() or ""
        layer = board.GetLayerName(item.GetLayer())
        width_mm = item.GetWidth() / MM
        drc_types = tuple(sorted(drc_types_raw))
        reason = protected_net_reason(
            net, width_mm=width_mm, layer=layer, locked=False)
        refusal = None
        if set(drc_types) - {"clearance"}:
            refusal = "unsupported_drc_type"
        elif uid in grouped:
            refusal = "explicit_group_ownership"
        elif reason != "kelvin_or_sense":
            refusal = reason or "authored_locked_copper"
        if refusal:
            immutable.append({
                "uuid": uid, "net": net, "layer": layer,
                "width_mm": round(width_mm, 6),
                "drc_types": list(drc_types), "reason": refusal,
            })
            continue
        targets.append(RepairTarget(
            uuid=uid, net=net, layer=layer,
            hit_count=max(1, len(drc_types)), blocked_nets=(),
            reservations=(), drc_types=drc_types, drc_conflict=True,
            priority=(-len(drc_types), uid), sensitive_repair=True,
        ))
    targets.sort(key=lambda row: row.priority)
    return {
        "schema": SCHEMA,
        "board": os.path.abspath(board_path),
        "targets": [asdict(row) for row in targets[:max(0, int(limit))]],
        "immutable": immutable,
        "drc_named_track_count": len(drc_index),
    }


def _escape_corridor_blocker_rows(certificate: dict,
                                  surface_layers: dict[str, set[str]],
                                  trapped_labels: set[str]) -> list[dict]:
    """Return track blockers on each trapped land's cheapest surface ray.

    ``dominant_blockers`` is a board-wide hit histogram.  It can spend a
    bounded negotiation cap on several remote branches while omitting a short,
    low-hit stub that seals the only useful pad escape.  Per-ray certificate
    evidence has the missing topology.  Select the surface ray with the fewest
    fixed obstructions and then the fewest distinct track blockers; the caller
    still applies provenance, electrical policy, and full-board admission.
    """

    selected = []
    seen = set()
    for layer_row in certificate.get("layers") or ():
        layer_name = str(layer_row.get("layer") or "")
        for endpoint_row in layer_row.get("endpoint_escape") or ():
            label = str(endpoint_row.get("endpoint") or "")
            if (label not in trapped_labels
                    or layer_name not in surface_layers.get(label, set())):
                continue
            ray_candidates = []
            for ray in endpoint_row.get("ray_details") or ():
                track_rows = []
                track_ids = set()
                fixed_count = 0
                for blocker in ray.get("blockers") or ():
                    uid = str(blocker.get("uuid") or "")
                    if blocker.get("kind") == "track" and uid:
                        if uid not in track_ids:
                            track_ids.add(uid)
                            track_rows.append(blocker)
                    else:
                        fixed_count += 1
                if not track_rows:
                    continue
                ray_candidates.append((
                    fixed_count, len(track_rows),
                    str(ray.get("direction") or ""), track_rows))
            if not ray_candidates:
                continue
            _fixed, _tracks, _direction, rows = min(
                ray_candidates, key=lambda value: value[:3])
            for blocker in rows:
                uid = str(blocker.get("uuid") or "")
                if uid in seen:
                    continue
                seen.add(uid)
                selected.append({**blocker, "escape_corridor": True})
    return selected


def _fair_negotiation_window_schedule(windows, limit: int):
    """Round-robin ranked windows so one residual net cannot starve peers."""

    by_net = {}
    for window in sorted(windows, key=lambda row: row.priority):
        by_net.setdefault(window.net, []).append(window)
    net_order = sorted(by_net, key=lambda net: (
        by_net[net][0].priority, net))
    scheduled = []
    round_index = 0
    cap = max(0, int(limit))
    while len(scheduled) < cap:
        added = False
        for net in net_order:
            rows = by_net[net]
            if round_index >= len(rows):
                continue
            scheduled.append(rows[round_index])
            added = True
            if len(scheduled) >= cap:
                break
        if not added:
            break
        round_index += 1
    return scheduled


def _pofv_endpoint_blocker_rows(board, certificate: dict) -> list[dict]:
    """Certify exact all-layer blockers of a legal endpoint POFV escape.

    Surface escape rays describe traces leaving a land on one copper layer.
    A through via at that land is a different three-dimensional candidate: its
    barrel occupies every enabled copper layer.  This probe uses the same
    preferred filled-and-capped geometry, pad-containment authority, foreign
    copper indexes, and one-database-unit centreline as the real last-mile via
    guard.  It therefore names only objects whose removal can actually change
    that POFV verdict; it is not a broad congestion sample.
    """

    profile_name = cec_fr._fab.board_profile_name(board)
    profile = cec_fr._fab.PROFILES.get(profile_name)
    geometry = cec_fr._fab.preferred_pofv_geometry(profile)
    if not geometry:
        return []
    diameter_mm, drill_mm = geometry
    diameter_nm = int(round(diameter_mm * MM))
    drill_nm = int(round(drill_mm * MM))
    clearance_nm = int(round(max(
        0.0, float(certificate.get("clearance_mm") or 0.2)) * MM))
    target_net = str(certificate.get("net") or "")
    rows = []
    for endpoint in certificate.get("endpoints") or ():
        if endpoint.get("kind") != "pad":
            continue
        ref = str(endpoint.get("ref") or "")
        number = str(endpoint.get("pad") or "")
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            continue
        pad = next((item for item in footprint.Pads()
                    if str(item.GetNumber()) == number), None)
        if (pad is None or pad.HasHole() or not pad.GetNetCode()
                or (target_net and str(pad.GetNetname() or "") != target_net)):
            continue
        at = pad.GetCenter()
        blocking_pad, allowed_lands = cec_fr._fab.via_at_pad_conflicts(
            board, at, diameter_nm, drill_nm, int(pad.GetNetCode()))
        owner_qualified = any(
            str(row.get("ref") or "") == ref
            and str(row.get("pad") or "") == number
            for row in allowed_lands)
        if blocking_pad is not None or not owner_qualified:
            continue

        probe = pcbnew.VECTOR2I(int(at.x) + 1, int(at.y))
        blockers = []
        seen = set()
        for layer_id in board.GetEnabledLayers().CuStack():
            zones, copper = cec_fr._identified_foreign_shape_indexes(
                board, layer_id, {int(pad.GetNetCode())})
            for blocker in cec_fr._snapshot_foreign_blockers(
                    at, probe, diameter_nm, clearance_nm, zones, copper,
                    limit=64):
                key = json.dumps(blocker, sort_keys=True,
                                 separators=(",", ":"))
                if key in seen:
                    continue
                seen.add(key)
                blockers.append(blocker)
        if not blockers:
            continue
        rows.append({
            "endpoint": {key: endpoint.get(key) for key in
                         ("endpoint", "kind", "ref", "pad", "uuid",
                          "x_mm", "y_mm")
                         if endpoint.get(key) is not None},
            "diameter_mm": round(diameter_mm, 6),
            "drill_mm": round(drill_mm, 6),
            "profile": profile_name,
            "qualified_lands": allowed_lands,
            "blockers": blockers,
        })
    return rows


def plan_negotiations(board_path: str, completion: dict | None, *,
                      limit: int = 8,
                      max_blockers_per_window: int = 2,
                      generated_locked_uuids=()) -> dict:
    """Rank atomic blocked-net/rip-up windows from exact certificates.

    Moving a blocker and requiring that move alone to improve the whole board
    rejects the useful neutral state in negotiated routing.  A negotiation
    window instead identifies a refused connection and a *small* set of
    certificate-named, policy-movable tracks.  The worker later removes those
    branches, closes the refused connection, restores every displaced net, and
    scores that composite transaction.  No geometry outside the certificate is
    eligible for removal.
    """

    board = pcbnew.LoadBoard(board_path)
    tracks = {_uuid(item): item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK" and _uuid(item)}
    max_blockers = max(1, int(max_blockers_per_window))
    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}
    group_names_by_uuid = {}
    for group in board.Groups():
        for uid, item in tracks.items():
            if group.ContainsItem(item):
                group_names_by_uuid.setdefault(uid, set()).add(
                    str(group.GetName() or ""))
    windows = []
    immutable = []
    seen = set()
    pofv_vertical_candidates = 0
    live_unconnected = set((completion or {}).get("unconn_nets") or ())
    for row in refusal_certificates(completion):
        cert = row["certificate"]
        net = str(cert.get("net") or row["detail"].get("net") or "")
        # Completion reports contain intermediate last-mile refusals as well
        # as later successful closures.  When the oracle supplies its final
        # unconnected-net set, drop those stale certificates before spending a
        # negotiation window on a net that is already complete.
        if live_unconnected and net not in live_unconnected:
            continue
        width_mm = float(cert.get("width_mm") or 0.25)
        target_reason = protected_net_reason(net, width_mm=width_mm)
        if not net or target_reason:
            immutable.append({"net": net, "reason": target_reason or
                              "missing_target_net", "role": "target"})
            continue
        surface_layers = _surface_endpoint_layers(board, cert)
        surface_trapped = _surface_trapped_endpoint_labels(board, cert)
        endpoints = tuple({key2: endpoint.get(key2)
                           for key2 in ("endpoint", "kind", "ref", "pad", "uuid",
                                        "x_mm", "y_mm")
                           if endpoint.get(key2) is not None}
                          for endpoint in (cert.get("endpoints") or ()))
        distance = float(row["detail"].get("distance_mm") or 1e9)

        # Before broad planar rip-up, ask the distinct three-dimensional
        # question: does an explicitly qualified POFV at a refused SMD land
        # fail only because exact, policy-movable tracks occupy its barrel?
        # Every named blocker must fit in the bounded transaction; removing a
        # subset cannot change an all-layer via verdict and is therefore never
        # scheduled.
        for pofv_row in _pofv_endpoint_blocker_rows(board, cert):
            pofv_vertical_candidates += 1
            vertical_movable = []
            vertical_fixed = []
            vertical_immutable = []
            for blocker in pofv_row["blockers"]:
                uid = str(blocker.get("uuid") or "")
                if blocker.get("kind") != "track" or not uid:
                    vertical_fixed.append(dict(blocker))
                    continue
                item = tracks.get(uid)
                if item is None or item.GetNetname() == net:
                    if item is None:
                        vertical_fixed.append(dict(blocker))
                    continue
                layer = board.GetLayerName(item.GetLayer())
                reason = protected_net_reason(
                    item.GetNetname() or "", width_mm=item.GetWidth() / MM,
                    layer=layer, locked=item.IsLocked())
                generated_unlock = False
                item_groups = group_names_by_uuid.get(uid, set())
                generated_group_authority = (
                    not item_groups
                    or item_groups <= {cec_fr.ENDPOINT_NECKDOWN_GROUP})
                if (item.IsLocked() and uid in generated_locked
                        and generated_group_authority):
                    intrinsic_reason = protected_net_reason(
                        item.GetNetname() or "",
                        width_mm=item.GetWidth() / MM,
                        layer=layer, locked=False)
                    reason = intrinsic_reason
                    if intrinsic_reason is None:
                        generated_unlock = True
                entry = {
                    "uuid": uid, "net": item.GetNetname() or "",
                    "layer": layer, "hit_count": 1,
                    "generated_unlock": generated_unlock,
                    "vertical_pofv_blocker": True,
                }
                if reason:
                    entry["reason"] = reason
                    vertical_immutable.append(entry)
                elif not any(existing["uuid"] == uid
                             for existing in vertical_movable):
                    vertical_movable.append(entry)
            immutable.extend(
                {**entry, "blocked_net": net,
                 "role": "vertical_pofv_blocker"}
                for entry in vertical_immutable)
            immutable.extend({
                "blocked_net": net, "role": "vertical_pofv_blocker",
                "reason": "fixed_vertical_obstruction", "blocker": blocker,
            } for blocker in vertical_fixed)
            if (vertical_fixed or vertical_immutable
                    or not vertical_movable):
                continue
            vertical_movable.sort(key=lambda entry: (
                entry["layer"], entry["net"], entry["uuid"]))
            if len(vertical_movable) > max_blockers:
                immutable.append({
                    "blocked_net": net, "role": "vertical_pofv_window",
                    "reason": "vertical_blocker_cap",
                    "required_blockers": len(vertical_movable),
                    "max_blockers_per_window": max_blockers,
                    "endpoint": pofv_row["endpoint"],
                })
                continue
            chosen_ids = tuple(entry["uuid"]
                               for entry in vertical_movable)
            key = (net, chosen_ids)
            if key in seen:
                continue
            seen.add(key)
            vertical_layers = tuple(sorted({entry["layer"]
                                            for entry in vertical_movable}))
            unlock_uuids = tuple(
                entry["uuid"] for entry in vertical_movable
                if entry.get("generated_unlock"))
            # Keep the tuple shape compatible with ordinary window priorities.
            # A vertical escape is an exact local proof, but it is not proof
            # that the entire endpoint pair is local: globally sorting every
            # POFV window ahead of every planar window made a 44 mm control
            # path consume two timeout variants while a certified 3.7 mm
            # trapped-pad repair waited behind it. Rank the endpoint escape in
            # the same trapped/locality domain as ordinary windows, retaining
            # the exact vertical preference only within comparable geometry.
            vertical_upper = net.upper()
            if (vertical_upper in {"GND", "AGND", "DGND", "PGND"}
                    or vertical_upper.endswith("_GND")):
                vertical_role_priority = 0
            elif (net.startswith("+") or any(
                    token in vertical_upper for token in
                    ("VBUS", "VCC", "VDD", "VIN", "VOUT"))):
                vertical_role_priority = 1
            else:
                vertical_role_priority = 2
            escape_probe_mm = float(
                (cert.get("search") or {}).get("escape_probe_mm") or 1.25)
            vertical_local = distance <= max(2.0, 4.0 * escape_probe_mm)
            priority = (
                0, -1, 0 if unlock_uuids else 1,
                vertical_role_priority,
                0 if vertical_local else 1,
                distance if vertical_local else 0.0,
                0, 0, len(vertical_movable), vertical_role_priority,
                distance, -len(vertical_movable), net, chosen_ids)
            windows.append(NegotiationWindow(
                net=net, distance_mm=distance, width_mm=width_mm,
                clearance_mm=float(cert.get("clearance_mm") or 0.25),
                blocker_uuids=chosen_ids,
                blocker_nets=tuple(entry["net"]
                                   for entry in vertical_movable),
                blocker_hits=len(vertical_movable),
                omitted_movable_blockers=0, fixed_blocker_hits=0,
                trapped_endpoints=1, endpoints=endpoints,
                priority=priority, unlock_uuids=unlock_uuids,
                local_pin_escape=True, vertical_pofv_escape=True,
                vertical_blocker_layers=vertical_layers))

        escape_rows = _escape_corridor_blocker_rows(
            cert, surface_layers, surface_trapped)
        escape_uuids = {
            str(blocker.get("uuid") or "") for blocker in escape_rows}
        trapped_endpoint_uuids = {
            str(blocker.get("uuid") or "")
            for layer_row in (cert.get("layers") or ())
            for endpoint_row in (layer_row.get("endpoint_escape") or ())
            if str(endpoint_row.get("endpoint") or "") in surface_trapped
            for ray in (endpoint_row.get("ray_details") or ())
            for blocker in (ray.get("blockers") or ())
            if blocker.get("kind") == "track" and blocker.get("uuid")
        }
        blocker_rows = list(cert.get("dominant_blockers") or ())
        dominant_uuids = {
            str(blocker.get("uuid") or "") for blocker in blocker_rows}
        blocker_rows.extend(
            blocker for blocker in escape_rows
            if str(blocker.get("uuid") or "") not in dominant_uuids)
        movable = []
        local_immutable = []
        fixed_blocker_hits = 0
        used = set()
        for blocker in blocker_rows:
            blocker_hits = int(blocker.get("hit_count") or 1)
            if blocker.get("kind") != "track" or not blocker.get("uuid"):
                fixed_blocker_hits += blocker_hits
                continue
            uid = str(blocker["uuid"])
            if uid in used:
                continue
            used.add(uid)
            item = tracks.get(uid)
            if item is None or item.GetNetname() == net:
                continue
            layer = board.GetLayerName(item.GetLayer())
            reason = protected_net_reason(
                item.GetNetname() or "", width_mm=item.GetWidth() / MM,
                layer=layer, locked=item.IsLocked())
            generated_unlock = False
            item_groups = group_names_by_uuid.get(uid, set())
            generated_group_authority = (
                not item_groups
                or item_groups <= {cec_fr.ENDPOINT_NECKDOWN_GROUP})
            if (item.IsLocked() and uid in generated_locked
                    and generated_group_authority):
                intrinsic_reason = protected_net_reason(
                    item.GetNetname() or "", width_mm=item.GetWidth() / MM,
                    layer=layer, locked=False)
                # Once provenance proves the lock came from this pipeline,
                # report the underlying electrical policy—not the incidental
                # lock bit—as the remaining refusal authority.
                reason = intrinsic_reason
                if intrinsic_reason is None:
                    # The caller proved this UUID did not exist in the
                    # authored baseline.  It is still eligible only as an
                    # exact certificate blocker on ordinary narrow signal
                    # copper; every electrical/topology invariant is checked
                    # again after the composite transaction.
                    generated_unlock = True
            entry = {
                "uuid": uid, "net": item.GetNetname() or "",
                "layer": layer, "hit_count": int(
                    blocker.get("hit_count") or 1),
                "generated_unlock": generated_unlock,
                "escape_corridor": uid in escape_uuids,
                "trapped_endpoint_blocker": uid in trapped_endpoint_uuids,
            }
            if reason:
                entry["reason"] = reason
                local_immutable.append(entry)
                fixed_blocker_hits += blocker_hits
            else:
                movable.append(entry)
        immutable.extend({**entry, "blocked_net": net, "role": "blocker"}
                         for entry in local_immutable)
        if not movable:
            continue
        movable.sort(key=lambda entry: (
            0 if entry["escape_corridor"] else 1,
            0 if entry["trapped_endpoint_blocker"] else 1,
            -entry["hit_count"], entry["uuid"]))
        # When a physical pad surface is sealed, remote-end blockers do not
        # contribute to opening that land and only enlarge the restoration
        # transaction.  Keep the window local whenever the certificate names
        # at least one policy-movable blocker around the trapped endpoint.
        local_movable = [entry for entry in movable
                         if entry["trapped_endpoint_blocker"]]
        chosen = (local_movable or movable)[:max_blockers]
        key = (net, tuple(entry["uuid"] for entry in chosen))
        if key in seen:
            continue
        seen.add(key)
        hit_total = sum(entry["hit_count"] for entry in chosen)
        escape_rays = {}
        for layer_row in cert.get("layers") or ():
            for endpoint_row in layer_row.get("endpoint_escape") or ():
                label = str(endpoint_row.get("endpoint") or "")
                if label:
                    escape_rays.setdefault(label, set()).update(
                        endpoint_row.get("clear_rays") or ())
        trapped = sum(not rays for rays in escape_rays.values())
        # Canonical and maze closure have already failed before negotiation.
        # Prefer the windows with a genuinely trapped endpoint here: those are
        # the cases for which certificate-driven rip-up is necessary.  An
        # untrapped endpoint can still be attempted after the scarce escape
        # pockets.  Within that class, close reference and supply continuity
        # before ordinary controls.
        omitted = max(0, len(movable) - len(chosen))
        unlock_uuids = tuple(entry["uuid"] for entry in chosen
                             if entry.get("generated_unlock"))
        # Critical/power ordering has already run before certificate repair.
        # At this residual stage, a short pad-to-pad gap blocked by exact
        # pipeline-owned copper is the highest-confidence negotiated move.
        # Scale the local window from the certificate's own escape probe rather
        # than a board-specific dimension.
        escape_probe_mm = float(
            (cert.get("search") or {}).get("escape_probe_mm") or 1.25)
        endpoint_kinds = {str(row.get("kind") or "") for row in endpoints}
        local_pin_escape = bool(
            endpoint_kinds <= {"pad", "via", "track", "trk"}
            and (distance <= max(2.0, 4.0 * escape_probe_mm)
                 or surface_trapped))
        upper_net = net.upper()
        if (upper_net in {"GND", "AGND", "DGND", "PGND"}
                or upper_net.endswith("_GND")):
            role_priority = 0
        elif (net.startswith("+") or any(
                token in upper_net for token in
                ("VBUS", "VCC", "VDD", "VIN", "VOUT"))):
            role_priority = 1
        else:
            role_priority = 2
        priority = (0 if trapped else 1, -trapped,
                    0 if unlock_uuids else 1,
                    # Once reversibility/provenance is equal, restore ground
                    # reference and supply continuity before ordinary control
                    # nets.  Locality follows electrical role: a short GPIO
                    # window must not starve a longer broken reference path.
                    role_priority,
                    0 if local_pin_escape else 1,
                    distance if local_pin_escape else 0.0,
                    # For residual non-local windows, irreducible geometry is
                    # more predictive than the net's electrical role.  Route
                    # power early in the global schedule, but do not spend a
                    # repair wave on a long power corridor with many fixed
                    # blockers while a nearly feasible control window waits.
                    fixed_blocker_hits, omitted, len(chosen), role_priority,
                    distance, -hit_total, net, key[1])
        windows.append(NegotiationWindow(
            net=net, distance_mm=distance, width_mm=width_mm,
            clearance_mm=float(cert.get("clearance_mm") or 0.25),
            blocker_uuids=tuple(entry["uuid"] for entry in chosen),
            blocker_nets=tuple(entry["net"] for entry in chosen),
            blocker_hits=hit_total,
            omitted_movable_blockers=omitted,
            fixed_blocker_hits=fixed_blocker_hits,
            trapped_endpoints=trapped,
            endpoints=endpoints, priority=priority,
            unlock_uuids=unlock_uuids,
            local_pin_escape=local_pin_escape))
    windows.sort(key=lambda window: window.priority)
    scheduled = _fair_negotiation_window_schedule(windows, limit)
    immutable.sort(key=lambda entry: (
        str(entry.get("blocked_net") or entry.get("net") or ""),
        str(entry.get("uuid") or "")))
    return {
        "schema": SCHEMA,
        "board": os.path.abspath(board_path),
        "certificates": len(refusal_certificates(completion)),
        "windows": [asdict(window) for window in scheduled],
        "immutable": immutable,
        "max_blockers_per_window": max_blockers,
        "window_schedule": "ranked_net_round_robin",
        "generated_locked_authority_count": len(generated_locked),
        "pofv_vertical_candidates": pofv_vertical_candidates,
    }


def _surface_endpoint_layers(board, certificate: dict) -> dict[str, set[str]]:
    """Map certificate pad labels to the physical copper surface they own."""

    surfaces = {}
    for endpoint in certificate.get("endpoints") or ():
        if endpoint.get("kind") != "pad":
            continue
        label = str(endpoint.get("endpoint") or "")
        ref = str(endpoint.get("ref") or "")
        number = str(endpoint.get("pad") or "")
        if not label or not ref or not number:
            continue
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            continue
        pad = next((item for item in footprint.Pads()
                    if str(item.GetNumber()) == number), None)
        if pad is None or pad.HasHole():
            continue
        owned = set()
        if pad.IsOnLayer(pcbnew.F_Cu):
            owned.add("F.Cu")
        if pad.IsOnLayer(pcbnew.B_Cu):
            owned.add("B.Cu")
        if owned:
            surfaces[label] = owned
    return surfaces


def _surface_trapped_endpoint_labels(board, certificate: dict) -> set[str]:
    """Return SMD endpoint labels sealed on their own component surface.

    A fine-pitch pad may have clear rays on an inner signal layer while every
    ray on the copper surface that actually owns the land is blocked.  That is
    still a pin-escape problem: the closure transaction should try a qualified
    via/bridge launch before another board-scale surface maze.  Resolve the
    physical pad side from the board rather than assuming every SMD is top.
    """

    surfaces = _surface_endpoint_layers(board, certificate)

    layer_rays = {}
    for layer in certificate.get("layers") or ():
        layer_name = str(layer.get("layer") or "")
        for escape in layer.get("endpoint_escape") or ():
            label = str(escape.get("endpoint") or "")
            if label:
                layer_rays.setdefault((label, layer_name), set()).update(
                    str(ray) for ray in (escape.get("clear_rays") or ()))
    return {
        label for label, owned_layers in surfaces.items()
        if any((label, layer) in layer_rays
               and not layer_rays[(label, layer)]
               for layer in owned_layers)
    }


def _trapped_foreign_pad_blockers(completion: dict | None) -> list[dict]:
    """Extract foreign footprint pads that seal a certified endpoint escape.

    The evidence is intentionally taken from per-ray refusal rows rather than
    broad ``dominant_blockers``.  A pad that merely intersects one rejected
    board-scale path is not placement authority; a foreign pad repeated on an
    endpoint with no clear surface ray is.
    """

    rows = []
    for refusal in refusal_certificates(completion):
        cert = refusal["certificate"]
        net = str(cert.get("net") or refusal["detail"].get("net") or "")
        endpoints = {
            str(row.get("endpoint") or ""): row
            for row in (cert.get("endpoints") or ())
            if row.get("endpoint") is not None
        }
        # A support cell has placement authority only when the endpoint is
        # sealed across every routable layer represented by the certificate.
        # Treating one blocked layer as globally trapped wastes placement
        # search when another layer already has a legal launch ray.
        clear_by_endpoint = {}
        counts = {}
        blocker_layers = {}
        for layer in cert.get("layers") or ():
            layer_name = str(layer.get("layer") or "")
            for escape in layer.get("endpoint_escape") or ():
                label = str(escape.get("endpoint") or "")
                clear_by_endpoint.setdefault(label, set()).update(
                    str(ray) for ray in (escape.get("clear_rays") or ()))
                if escape.get("clear_rays"):
                    continue
                endpoint = endpoints.get(label) or {}
                endpoint_ref = str(endpoint.get("ref") or "")
                for ray in escape.get("ray_details") or ():
                    if ray.get("status") != "foreign_copper_blocked":
                        continue
                    for blocker in ray.get("blockers") or ():
                        if blocker.get("kind") != "pad":
                            continue
                        ref = str(blocker.get("ref") or "")
                        if not ref or ref == endpoint_ref:
                            continue
                        key = (net, label, ref)
                        counts[key] = counts.get(key, 0) + int(
                            blocker.get("hit_count") or 1)
                        blocker_layers.setdefault(key, set()).add(layer_name)
        for (target_net, label, ref), hit_count in counts.items():
            if clear_by_endpoint.get(label):
                continue
            endpoint = endpoints.get(label) or {}
            if endpoint.get("x_mm") is None or endpoint.get("y_mm") is None:
                continue
            rows.append({
                "ref": ref,
                "target_net": target_net,
                "endpoint_ref": str(endpoint.get("ref") or ""),
                "endpoint_pad": str(endpoint.get("pad") or ""),
                "endpoint_x_mm": float(endpoint["x_mm"]),
                "endpoint_y_mm": float(endpoint["y_mm"]),
                "layers": sorted(blocker_layers.get(
                    (target_net, label, ref), ())),
                "hit_count": int(hit_count),
                "distance_mm": float(
                    refusal["detail"].get("distance_mm") or 1e9),
            })
    rows.sort(key=lambda row: (
        -row["hit_count"], row["distance_mm"], row["target_net"],
        row["ref"]))
    return rows


def plan_footprint_repairs(board_path: str, completion: dict | None, *,
                           limit: int = 4) -> dict:
    """Plan bounded support-cell re-seats from trapped-pin certificates.

    Only unlocked, all-SMD, two-terminal footprints are admitted.  This keeps
    connector mechanics, IC pinouts, THT geometry, fiducials, and authored
    anchors outside automatic movement while covering bypass capacitors,
    filters, pull parts, and other small support cells on any board.
    """

    board = pcbnew.LoadBoard(board_path)
    if board is None:
        return {"schema": SCHEMA, "board": os.path.abspath(board_path),
                "targets": [], "immutable": [{"reason": "board_unloadable"}]}
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    live_unconnected = set((completion or {}).get("unconn_nets") or ())
    targets = []
    immutable = []
    seen = set()
    candidate_rows = [
        {**row, "motion": "away_from_endpoint"}
        for row in _trapped_foreign_pad_blockers(completion)]

    # A refusal can also prove that the movable object is one of the two
    # endpoints itself: a small resistor/capacitor inherited too far from its
    # owning IC, or with its signal land facing away from that IC.  Treat that
    # as the inverse of a foreign blocker move.  The certificate supplies the
    # peer coordinate; eligibility remains limited to an unlocked two-pin SMD
    # support, and the complete transaction must reconnect every affected net
    # and improve the whole-board score.
    endpoint_support_rows = 0
    for refusal in refusal_certificates(completion):
        cert = refusal["certificate"]
        target_net = str(
            cert.get("net") or refusal["detail"].get("net") or "")
        endpoints = [
            endpoint for endpoint in cert.get("endpoints") or ()
            if endpoint.get("x_mm") is not None
            and endpoint.get("y_mm") is not None]
        trapped_labels = (_surface_trapped_endpoint_labels(board, cert)
                          if cert.get("layers") else set())
        hit_count = sum(int(row.get("hit_count") or 1)
                        for row in cert.get("dominant_blockers") or ())
        distance = float(refusal["detail"].get("distance_mm") or 1e9)
        for endpoint in endpoints:
            ref = str(endpoint.get("ref") or "")
            if endpoint.get("kind") != "pad" or not ref:
                continue
            peers = [row for row in endpoints if row is not endpoint]
            if not peers:
                continue
            peer = min(peers, key=lambda row: (
                math.hypot(float(row["x_mm"]) - float(endpoint["x_mm"]),
                           float(row["y_mm"]) - float(endpoint["y_mm"])),
                str(row.get("ref") or ""), str(row.get("pad") or "")))
            endpoint_label = str(endpoint.get("endpoint") or "")
            peer_label = str(peer.get("endpoint") or "")
            if (peer_label in trapped_labels
                    and endpoint_label not in trapped_labels):
                # A clear two-pin endpoint on an exclusive point-to-point net
                # is normally a local support component (soft-start/timing
                # capacitor, bootstrap part, threshold resistor, and so on).
                # Seating that support immediately beside the trapped owner
                # can shrink the required escape to a direct pad connection;
                # moving the much larger owner and its whole fanout is the
                # wrong first degree of freedom.  Do not generalize this to a
                # shared rail: a random same-net passive on a multi-drop net is
                # not placement authority for the trapped pin.
                target_code = board.GetNetcodeFromNetname(target_net)
                target_pads = [
                    (footprint.GetReference(), str(pad.GetNumber()))
                    for footprint in board.GetFootprints()
                    for pad in footprint.Pads()
                    if pad.IsOnCopperLayer()
                    and pad.GetNetCode() == target_code]
                expected_endpoints = {
                    (ref, str(endpoint.get("pad") or "")),
                    (str(peer.get("ref") or ""),
                     str(peer.get("pad") or "")),
                }
                if (len(target_pads) != 2
                        or set(target_pads) != expected_endpoints):
                    continue
            candidate_rows.append({
                "ref": ref, "target_net": target_net,
                "endpoint_ref": str(peer.get("ref") or ""),
                "endpoint_pad": str(peer.get("pad") or ""),
                "endpoint_x_mm": float(peer["x_mm"]),
                "endpoint_y_mm": float(peer["y_mm"]),
                "layers": [], "hit_count": max(1, hit_count),
                "distance_mm": distance,
                "motion": "toward_endpoint",
            })
            endpoint_support_rows += 1

    for row in candidate_rows:
        if live_unconnected and row["target_net"] not in live_unconnected:
            continue
        key = (row["target_net"], row["ref"], row["endpoint_ref"],
               row["endpoint_pad"], row.get("motion"))
        if key in seen:
            continue
        seen.add(key)
        fp = footprints.get(row["ref"])
        reason = None
        pads = list(fp.Pads()) if fp is not None else []
        copper_pads = [pad for pad in pads if pad.IsOnCopperLayer()]
        if fp is None:
            reason = "missing_footprint"
        elif fp.IsLocked():
            reason = "locked_footprint"
        elif row["ref"].upper().startswith(("J", "H", "FID", "LOGO", "MK")):
            reason = "mechanical_or_access_anchor"
        elif not copper_pads or len(copper_pads) > 2:
            reason = "not_two_terminal_support"
        elif any(pad.HasHole() for pad in copper_pads):
            reason = "through_hole_geometry"
        elif len({pad.GetNetCode() for pad in copper_pads
                  if pad.GetNetCode() > 0}) > 2:
            reason = "multi_net_support"
        if reason:
            immutable.append({**row, "reason": reason})
            continue
        priority = (-int(row["hit_count"]), float(row["distance_mm"]),
                    row["target_net"], row["ref"], row.get("motion"))
        companions = ()
        if str(row.get("motion") or "") == "toward_endpoint":
            target_pos = fp.GetPosition()
            target_code = board.GetNetcodeFromNetname(row["target_net"])
            adjacent = []
            for other_ref, other in footprints.items():
                if other_ref == row["ref"] or other.IsLocked():
                    continue
                if other_ref.upper().startswith(
                        ("J", "H", "FID", "LOGO", "MK")):
                    continue
                other_pads = [pad for pad in other.Pads()
                              if pad.IsOnCopperLayer()]
                if (len(other_pads) != 2
                        or any(pad.HasHole() for pad in other_pads)
                        or not any(pad.GetNetCode() == target_code
                                   for pad in other_pads)):
                    continue
                distance = math.hypot(
                    other.GetPosition().x - target_pos.x,
                    other.GetPosition().y - target_pos.y) / MM
                if distance <= 3.0 + 1e-9:
                    adjacent.append((distance, other_ref))
            # A local divider/filter cell may contain one or two companion
            # passives.  Keep the transaction bounded and deterministic; the
            # whole-board scorer rejects a merely coincident same-net part.
            companions = tuple(ref for _distance, ref in sorted(adjacent)[:2])
        targets.append(FootprintRepairTarget(
            ref=row["ref"], target_net=row["target_net"],
            endpoint_ref=row["endpoint_ref"],
            endpoint_pad=row["endpoint_pad"],
            endpoint_x_mm=row["endpoint_x_mm"],
            endpoint_y_mm=row["endpoint_y_mm"],
            hit_count=row["hit_count"], distance_mm=row["distance_mm"],
            priority=priority,
            motion=str(row.get("motion") or "away_from_endpoint"),
            companion_refs=companions))
    targets.sort(key=lambda row: row.priority)
    immutable.sort(key=lambda row: (
        row.get("target_net", ""), row.get("ref", "")))
    return {
        "schema": SCHEMA,
        "board": os.path.abspath(board_path),
        "targets": [asdict(row) for row in targets[:max(0, int(limit))]],
        "immutable": immutable,
        "certificate_blockers": len(
            _trapped_foreign_pad_blockers(completion)),
        "certificate_support_endpoints": endpoint_support_rows,
    }


def plan_endpoint_owner_repairs(board_path: str, completion: dict | None, *,
                                limit: int = 4) -> dict:
    """Plan re-seats for small SMD ICs whose own pin cannot escape.

    This is intentionally not a general placement optimizer.  Authority comes
    from a refusal certificate proving that a pad is sealed on the component's
    physical copper surface.  Connectors, THT parts, two-terminal supports,
    large controllers/BGAs, locked footprints, and mechanical references are
    excluded.
    """

    board = pcbnew.LoadBoard(board_path)
    live_unconnected = set((completion or {}).get("unconn_nets") or ())
    targets, immutable, seen = [], [], set()
    for refusal in refusal_certificates(completion):
        cert = refusal["certificate"]
        target_net = str(cert.get("net") or refusal["detail"].get("net") or "")
        if live_unconnected and target_net not in live_unconnected:
            continue
        trapped = _surface_trapped_endpoint_labels(board, cert)
        for endpoint in cert.get("endpoints") or ():
            label = str(endpoint.get("endpoint") or "")
            if label not in trapped or endpoint.get("kind") != "pad":
                continue
            ref = str(endpoint.get("ref") or "")
            key = (target_net, ref, str(endpoint.get("pad") or ""))
            if not ref or key in seen:
                continue
            seen.add(key)
            footprint = board.FindFootprintByReference(ref)
            copper_pads = (list(footprint.Pads())
                           if footprint is not None else [])
            reason = None
            if footprint is None:
                reason = "missing_footprint"
            elif footprint.IsLocked():
                reason = "locked_footprint"
            elif ref.upper().startswith(("J", "H", "FID", "LOGO", "MK")):
                reason = "mechanical_or_access_anchor"
            elif any(pad.HasHole() for pad in copper_pads):
                reason = "through_hole_geometry"
            elif not (3 <= len(copper_pads) <= 16):
                reason = "outside_small_smd_owner_scope"
            if reason:
                immutable.append({"target_net": target_net, "ref": ref,
                                  "reason": reason})
                continue
            peers = [
                row for row in cert.get("endpoints") or ()
                if row is not endpoint
                and row.get("x_mm") is not None
                and row.get("y_mm") is not None]
            if not peers:
                immutable.append({"target_net": target_net, "ref": ref,
                                  "reason": "peer_endpoint_missing"})
                continue
            peer = min(peers, key=lambda row: (
                math.hypot(float(row["x_mm"]) - float(endpoint["x_mm"]),
                           float(row["y_mm"]) - float(endpoint["y_mm"])),
                str(row.get("ref") or ""), str(row.get("pad") or "")))
            hits = sum(int(row.get("hit_count") or 1)
                       for row in cert.get("dominant_blockers") or ())
            distance = float(refusal["detail"].get("distance_mm") or 1e9)
            owner_position = footprint.GetPosition()
            owner_nets = {pad.GetNetCode() for pad in copper_pads
                          if pad.GetNetCode() > 0}
            local_supports = []
            for other in board.GetFootprints():
                other_ref = other.GetReference()
                if (other is footprint or other.IsLocked()
                        or other_ref.upper().startswith(
                            ("J", "H", "FID", "LOGO", "MK"))):
                    continue
                other_pads = [pad for pad in other.Pads()
                              if pad.IsOnCopperLayer()]
                if (len(other_pads) != 2
                        or any(pad.HasHole() for pad in other_pads)
                        or not owner_nets.intersection(
                            pad.GetNetCode() for pad in other_pads)):
                    continue
                local_distance = math.hypot(
                    other.GetPosition().x - owner_position.x,
                    other.GetPosition().y - owner_position.y) / MM
                if local_distance <= 4.0 + 1e-9:
                    local_supports.append((local_distance, other_ref))
            # Carry the closest bounded support cell with the endpoint owner.
            # Four members cover the immediate decoupling/filter ring without
            # turning local legalization into a board-scale placement move.
            companions = tuple(ref for _distance, ref in
                               sorted(local_supports)[:4])
            targets.append(FootprintRepairTarget(
                ref=ref, target_net=target_net,
                endpoint_ref=str(peer.get("ref") or ""),
                endpoint_pad=str(peer.get("pad") or ""),
                endpoint_x_mm=float(peer["x_mm"]),
                endpoint_y_mm=float(peer["y_mm"]),
                hit_count=hits, distance_mm=distance,
                priority=(distance, -hits, target_net, ref),
                motion="toward_endpoint", companion_refs=companions))
    targets.sort(key=lambda row: row.priority)
    return {
        "schema": SCHEMA, "board": os.path.abspath(board_path),
        "targets": [asdict(row) for row in targets[:max(0, int(limit))]],
        "immutable": immutable,
    }


def plan_congestion_via_repairs(board_path: str, completion: dict | None, *,
                                generated_locked_uuids=(),
                                limit: int = 4) -> dict:
    """Plan moves for exact refusal-named ordinary through vias.

    Unlike DRC via repair, this degree of freedom is justified by a route
    refusal certificate.  A locked barrel is eligible only when the authored
    baseline proves it was generated by this pipeline, and a via on any
    same-net pad is never moved.  Pair/sense/high-current policy remains the
    same as track negotiation.
    """

    board = pcbnew.LoadBoard(board_path)
    route_items = {_uuid(item): item for item in board.GetTracks() if _uuid(item)}
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    pads = [pad for footprint in board.GetFootprints() for pad in footprint.Pads()]
    live_unconnected = set((completion or {}).get("unconn_nets") or ())
    targets, immutable, seen = [], [], set()
    for refusal in refusal_certificates(completion):
        cert = refusal["certificate"]
        target_net = str(cert.get("net") or refusal["detail"].get("net") or "")
        if live_unconnected and target_net not in live_unconnected:
            continue
        endpoints = [row for row in cert.get("endpoints") or ()
                     if row.get("x_mm") is not None and row.get("y_mm") is not None]
        for blocker in cert.get("dominant_blockers") or ():
            if blocker.get("kind") != "via" or not blocker.get("uuid"):
                continue
            uid = str(blocker["uuid"])
            key = (target_net, uid)
            if key in seen:
                continue
            seen.add(key)
            via = route_items.get(uid)
            reason = None
            if via is None or via.GetClass() != "PCB_VIA":
                reason = "via_missing"
            elif via.GetNetname() == target_net:
                reason = "same_net_via"
            elif via.IsLocked() and uid not in generated:
                reason = "authored_locked_via"
            elif protected_net_reason(
                    via.GetNetname() or "",
                    width_mm=via.GetWidth(pcbnew.F_Cu) / MM):
                reason = protected_net_reason(
                    via.GetNetname() or "",
                    width_mm=via.GetWidth(pcbnew.F_Cu) / MM)
            elif any(pad.GetNetCode() == via.GetNetCode()
                     and pad.GetBoundingBox().Contains(via.GetPosition())
                     for pad in pads):
                reason = "via_on_pad"
            if reason:
                immutable.append({"target_net": target_net, "uuid": uid,
                                  "reason": reason})
                continue
            pos = via.GetPosition()
            nearest = min(endpoints, key=lambda row: math.hypot(
                pos.x / MM - float(row["x_mm"]),
                pos.y / MM - float(row["y_mm"])), default=None)
            if nearest is None:
                immutable.append({"target_net": target_net, "uuid": uid,
                                  "reason": "missing_target_endpoint"})
                continue
            target = ViaRepairTarget(
                uuid=uid, net=via.GetNetname() or "",
                x_nm=int(pos.x), y_nm=int(pos.y),
                diameter_nm=int(via.GetWidth(pcbnew.F_Cu)),
                drill_nm=int(via.GetDrillValue()),
                counterpart_uuids=(), drc_types=(),
                away_dx=int(round(pos.x - float(nearest["x_mm"]) * MM)),
                away_dy=int(round(pos.y - float(nearest["y_mm"]) * MM)),
                priority=(-int(blocker.get("hit_count") or 1),
                          float(refusal["detail"].get("distance_mm") or 1e9),
                          target_net, uid))
            owner_directions = []
            tolerance_nm = 5_000
            for item in board.GetTracks():
                if (item is via or item.GetNetCode() != via.GetNetCode()
                        or item.GetClass() not in {"PCB_TRACK", "PCB_ARC"}):
                    continue
                start, end = item.GetStart(), item.GetEnd()
                if math.hypot(start.x - pos.x, start.y - pos.y) <= tolerance_nm:
                    other = end
                elif math.hypot(end.x - pos.x, end.y - pos.y) <= tolerance_nm:
                    other = start
                else:
                    continue
                direction = _octant_away(other.x - pos.x, other.y - pos.y)
                if direction not in owner_directions:
                    owner_directions.append(direction)
            targets.append({
                "target_net": target_net,
                "distance_mm": float(
                    refusal["detail"].get("distance_mm") or 1e9),
                "hit_count": int(blocker.get("hit_count") or 1),
                "via": asdict(target),
                "owner_directions": [list(direction)
                                     for direction in owner_directions],
            })
    targets.sort(key=lambda row: tuple(row["via"]["priority"]))
    return {
        "schema": SCHEMA, "board": os.path.abspath(board_path),
        "targets": targets[:max(0, int(limit))], "immutable": immutable,
    }


def _find_track(board, uid: str):
    return next((item for item in board.GetTracks()
                 if item.GetClass() == "PCB_TRACK" and _uuid(item) == uid), None)


def _layer_candidates(board, source_layer: int, *, net_name="",
                      spec=None) -> list[int]:
    """Return the same profile-authorized bridge pool as global last-mile."""

    return [
        layer for layer in cec_fr._lastmile_route_layers(
            board, net_name=net_name, spec=spec, exclude_front=False)
        if int(layer) != int(source_layer)
    ]


def _other_end(track, point):
    if track.GetStart() == point:
        return track.GetEnd()
    if track.GetEnd() == point:
        return track.GetStart()
    return None


def _expanded_branch(board, target, *, max_hops: int = 2):
    """Expand a blocker through bounded degree-2 neck segments on both ends.

    Freerouting commonly emits ``fine stub -> class-width trunk -> fine stub``.
    Moving only the middle trunk can be impossible because its endpoints were
    chosen for the old corridor.  This walker includes at most *max_hops*
    unlocked, same-layer, same-net neighbours per side and stops at a pad,
    via, junction, width increase, lock, or topology ambiguity.  The returned
    fine-width/budget tuples preserve legitimate pin neck-downs.
    """

    net_code, layer = target.GetNetCode(), target.GetLayer()
    source_width = target.GetWidth()
    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"
              and item.GetNetCode() == net_code and item.GetLayer() == layer]
    selected = [target]
    selected_ids = {_uuid(target)}

    def walk(point):
        current = point
        local_width = source_width
        budget_nm = 0.0
        added = []
        for _ in range(max(0, int(max_hops))):
            incident = [item for item in tracks
                        if _uuid(item) not in selected_ids
                        and _other_end(item, current) is not None]
            # A real junction is ownership evidence; never rip through it.
            if len(incident) != 1:
                break
            item = incident[0]
            if item.IsLocked() or item.GetWidth() > source_width:
                break
            other = _other_end(item, current)
            if other is None:
                break
            # Stop after reaching a pad/via anchor, but include the neck that
            # lands there so the reroute owns a usable boundary point.
            added.append(item)
            selected_ids.add(_uuid(item))
            local_width = min(local_width, item.GetWidth())
            budget_nm += math.hypot(other.x - current.x, other.y - current.y)
            current = other
            on_pad = any(pad.GetNetCode() == net_code and pad.HitTest(current)
                         for fp in board.GetFootprints() for pad in fp.Pads())
            on_via = any(item2.GetClass() == "PCB_VIA"
                         and item2.GetNetCode() == net_code
                         and item2.GetPosition() == current
                         for item2 in board.GetTracks())
            if on_pad or on_via:
                break
        return current, local_width, int(round(budget_nm)), added

    start, sw, sb, left = walk(target.GetStart())
    selected.extend(left)
    # The second walk must see the first side as already owned so it cannot
    # circle back through a tiny loop.
    end, ew, eb, right = walk(target.GetEnd())
    selected.extend(right)
    start_escape = (sw, sb) if sb > 0 and sw < source_width else None
    end_escape = (ew, eb) if eb > 0 and ew < source_width else None
    return {
        "start": start, "end": end, "tracks": selected,
        "start_escape": start_escape, "end_escape": end_escape,
        "source_length_nm": sum(math.hypot(
            item.GetEnd().x - item.GetStart().x,
            item.GetEnd().y - item.GetStart().y) for item in selected),
    }


def _lay_ops(board, operations, net_code: int, *, lock: bool = False) -> dict:
    tracks = vias = 0
    uuids = []
    for op in operations:
        if op[0] == "via":
            _, at, drill, diameter = op
            item = pcbnew.PCB_VIA(board)
            item.SetPosition(at)
            item.SetDrill(int(round(float(drill) * MM)))
            item.SetWidth(int(round(float(diameter) * MM)))
            item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            item.SetNetCode(net_code)
            item.SetLocked(bool(lock))
            board.Add(item)
            uuids.append(_uuid(item))
            vias += 1
        else:
            _, start, end, width, layer = op
            if start == end:
                continue
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(start)
            item.SetEnd(end)
            item.SetWidth(int(width))
            item.SetLayer(int(layer))
            item.SetNetCode(net_code)
            item.SetLocked(bool(lock))
            board.Add(item)
            uuids.append(_uuid(item))
            tracks += 1
    board.BuildConnectivity()
    return {"tracks": tracks, "vias": vias, "uuids": uuids,
            "locked": bool(lock)}


def _candidate_ops(board, target: RepairTarget, *, board_path: str, mode: str,
                   maze_margin_mm: float) -> tuple[list | None, dict]:
    requested_mode = mode
    item = _find_track(board, target.uuid)
    if item is None:
        return None, {"refusal": "target_track_missing"}
    if item.IsLocked() and not target.sensitive_repair:
        return None, {"refusal": "target_became_locked"}
    if target.sensitive_repair and not item.IsLocked():
        return None, {"refusal": "sensitive_target_lost_lock"}
    if target.sensitive_repair:
        intrinsic_reason = protected_net_reason(
            item.GetNetname() or "", width_mm=item.GetWidth() / MM,
            layer=board.GetLayerName(item.GetLayer()), locked=False)
        if (not target.drc_conflict
                or set(target.drc_types) != {"clearance"}
                or intrinsic_reason != "kelvin_or_sense"):
            return None, {"refusal": "sensitive_target_policy_mismatch"}
        if mode.startswith("branch_"):
            return None, {"refusal": "sensitive_branch_expansion_forbidden"}
        if any(group.ContainsItem(item) for group in board.Groups()):
            return None, {"refusal": "sensitive_target_grouped"}
    branch = (_expanded_branch(board, item)
              if mode.startswith("branch_") else None)
    start = branch["start"] if branch else item.GetStart()
    end = branch["end"] if branch else item.GetEnd()
    width, layer, net_code = item.GetWidth(), item.GetLayer(), item.GetNetCode()
    net = item.GetNetname() or ""
    resolver = cec_fr._project_netclass_resolver(board_path)
    spec = dict(resolver(net) or {})
    clearance_mm = max(0.2, float(spec.get("clearance") or 0.0))
    clearance_nm = int(round(clearance_mm * MM))

    # Future-route reservation: when a certificate says this track blocked a
    # still-open connection, the replacement must not simply occupy the same
    # corridor under a fresh UUID.  Treat each certified endpoint corridor as
    # virtual foreign copper during blocker reroute.  This is steering only;
    # the reservation never reaches the saved board or relaxes DRC.
    use_reservations = not mode.endswith("_unreserved")
    if not use_reservations:
        mode = mode[:-len("_unreserved")]
    reservations = []
    edge_box = board.GetBoardEdgesBoundingBox()
    board_center = pcbnew.VECTOR2I(
        int(edge_box.GetLeft() + edge_box.GetWidth() // 2),
        int(edge_box.GetTop() + edge_box.GetHeight() // 2))
    for row in (target.reservations if use_reservations else ()):
        try:
            a = pcbnew.VECTOR2I(int(round(row["a"][0] * MM)),
                                int(round(row["a"][1] * MM)))
            b = pcbnew.VECTOR2I(int(round(row["b"][0] * MM)),
                                int(round(row["b"][1] * MM)))
            virtual_width = int(round(
                float(row.get("width_mm") or 0.25) * MM))
            virtual_clearance = int(round(
                float(row.get("clearance_mm") or 0.25) * MM))
            owner_a = row.get("a_owner") or {}
            owner_b = row.get("b_owner") or {}
            connector_is_a = str(owner_a.get("ref") or "").upper().startswith("J")
            connector_is_b = str(owner_b.get("ref") or "").upper().startswith("J")
            path = [a, b]
            if connector_is_a != connector_is_b:
                connector, other = ((a, b) if connector_is_a else (b, a))
                dx = board_center.x - connector.x
                dy = board_center.y - connector.y
                # Standard edge-connector breakout: leave perpendicular to
                # the edge-facing pin row before turning toward the load.  If
                # the load is already within 3 mm on that axis, align the turn
                # with it; otherwise reserve a bounded 2 mm interior escape.
                if abs(dx) >= abs(dy):
                    ex = (other.x if abs(other.x - connector.x) <= 3 * MM
                          else connector.x + (2 * MM if dx >= 0 else -2 * MM))
                    elbow = pcbnew.VECTOR2I(int(ex), connector.y)
                else:
                    ey = (other.y if abs(other.y - connector.y) <= 3 * MM
                          else connector.y + (2 * MM if dy >= 0 else -2 * MM))
                    elbow = pcbnew.VECTOR2I(connector.x, int(ey))
                path = ([connector, elbow, other] if connector_is_a
                        else [other, elbow, connector])
            for left, right in zip(path, path[1:]):
                if left == right:
                    continue
                reservations.append((
                    pcbnew.SHAPE_SEGMENT(left, right, virtual_width),
                    virtual_clearance, str(row.get("net") or ""),
                ))
        except Exception:                               # noqa: BLE001
            continue

    # The source segment must be absent from the collision snapshot; its other
    # same-net copper remains and is correctly exempt.
    removed = branch["tracks"] if branch else [item]
    if target.sensitive_repair:
        # Release only the exact DRC-named object selected by the narrow
        # planner.  Replacement copper is re-locked below before it can leave
        # this transaction.
        item.SetLocked(False)
    for old in removed:
        board.Remove(old)
    board.BuildConnectivity()

    def edge_ok(a, b, half_width):
        if not cec_fr._edge_leg_clear(board, a, b, half_width):
            return False
        candidate = pcbnew.SHAPE_SEGMENT(a, b, int(2 * half_width))
        return not any(shape.Collide(candidate, extra)
                       for shape, extra, _net in reservations)

    operations = None
    route_mode = mode.removeprefix("branch_")
    start_escape = branch["start_escape"] if branch else None
    end_escape = branch["end_escape"] if branch else None
    if route_mode == "same_layer":
        legs = cec_fr._guarded_profiled_lastmile_legs(
            board, start, end, width, layer, clearance_nm, net_code, edge_ok,
            start_escape=start_escape, end_escape=end_escape,
            allow_maze=True, maze_margin_mm=maze_margin_mm,
            foreign_cache={})
        if legs:
            operations = [("trk", a, b, leg_width, layer)
                          for a, b, leg_width in legs]
    elif route_mode == "bridge":
        via_diameter = float(spec.get("via_diameter") or 0.6)
        via_drill = float(spec.get("via_drill") or 0.3)
        operations = cec_fr._lastmile_bridge(
            board, (start.x, start.y), {layer}, (end.x, end.y), {layer},
            width, net_code,
            _layer_candidates(
                board, layer, net_name=net, spec=spec), clearance_nm,
            drill=via_drill, dia=via_diameter, leg_ok=edge_ok,
            start_escape=start_escape, end_escape=end_escape,
            seat_limit=8, allow_maze=True, maze_margin_mm=maze_margin_mm,
            foreign_cache={})
    else:
        raise ValueError("unknown certificate repair mode %r" % mode)
    evidence = {
        "mode": requested_mode, "maze_margin_mm": float(maze_margin_mm),
        "net": net, "layer": board.GetLayerName(layer),
        "width_mm": round(width / MM, 6),
        "clearance_mm": round(clearance_mm, 6),
        "source_length_mm": round(
            (branch["source_length_nm"] if branch else
             math.hypot(end.x - start.x, end.y - start.y)) / MM, 6),
        "removed_tracks": [_uuid(old) for old in removed],
        "start_escape": ([round(start_escape[0] / MM, 6),
                           round(start_escape[1] / MM, 6)]
                          if start_escape else None),
        "end_escape": ([round(end_escape[0] / MM, 6),
                         round(end_escape[1] / MM, 6)]
                        if end_escape else None),
        "future_route_reservations": [net for _shape, _extra, net
                                      in reservations],
        "sensitive_repair": bool(target.sensitive_repair),
    }
    if not operations:
        evidence["refusal"] = "no_exact_clear_local_path"
        return None, evidence
    evidence["new_geometry"] = _lay_ops(
        board, operations, net_code, lock=target.sensitive_repair)
    evidence["new_length_mm"] = round(sum(
        math.hypot(op[2].x - op[1].x, op[2].y - op[1].y) / MM
        for op in operations if op[0] != "via"), 6)
    return operations, evidence


def _snapshot_displaced_branch(board, uid: str, *, max_hops: int = 2,
                               allow_generated_locked: bool = False):
    """Describe one certificate-named local branch before any mutation."""

    item = _find_track(board, uid)
    if item is None:
        return None, "target_track_missing_or_coalesced"
    net = item.GetNetname() or ""
    layer = board.GetLayerName(item.GetLayer())
    was_locked = bool(item.IsLocked())
    reason = protected_net_reason(
        net, width_mm=item.GetWidth() / MM, layer=layer,
        locked=(was_locked and not allow_generated_locked))
    group_names = tuple(sorted(
        str(group.GetName() or "") for group in board.Groups()
        if group.ContainsItem(item)))
    if allow_generated_locked:
        if not was_locked:
            return None, "generated_locked_authority_mismatch"
        if (group_names
                and set(group_names) != {cec_fr.ENDPOINT_NECKDOWN_GROUP}):
            return None, "explicit_group_ownership"
    if reason:
        return None, reason
    # Baseline provenance applies to the exact certificate UUID.  Do not let
    # degree-2 expansion silently absorb neighbouring authored segments.
    branch = _expanded_branch(
        board, item, max_hops=(0 if allow_generated_locked else max_hops))
    snapshot = {
        "requested_uuid": uid,
        "net": net,
        "net_code": item.GetNetCode(),
        "layer": item.GetLayer(),
        "width": item.GetWidth(),
        "start": pcbnew.VECTOR2I(branch["start"].x, branch["start"].y),
        "end": pcbnew.VECTOR2I(branch["end"].x, branch["end"].y),
        "start_escape": branch["start_escape"],
        "end_escape": branch["end_escape"],
        "source_length_nm": float(branch["source_length_nm"]),
        "removed_uuids": tuple(_uuid(old) for old in branch["tracks"]),
        "relock": was_locked,
        "endpoint_neckdown_group": (
            cec_fr.ENDPOINT_NECKDOWN_GROUP in group_names),
        "_track_objects": tuple(branch["tracks"]),
    }
    return snapshot, None


def _merge_overlapping_snapshots(snapshots, *, board=None):
    """Coalesce overlapping/adjacent degree-2 snapshots into restorable paths.

    Exact generated-copper authority deliberately snapshots one UUID at a
    time.  Several certificate blockers can nevertheless be consecutive
    segments of one branch; restoring those tiny fragments independently is
    impossible once the refused net claims their shared corridor.  Merge a
    contiguous same-net/same-layer/equal-width chain only when its interior has
    no pad, via, or unselected track attachment.  Junctions remain separate.
    """

    def row_nodes(snapshot):
        return {
            (point.x, point.y)
            for item in snapshot["_track_objects"]
            for point in (item.GetStart(), item.GetEnd())
        }

    def compatible(snapshot, group):
        first = group["rows"][0]
        return (snapshot["net_code"] == first["net_code"]
                and snapshot["layer"] == first["layer"]
                and snapshot["width"] == first["width"])

    groups = []
    for snapshot in snapshots:
        ids = set(snapshot["removed_uuids"])
        nodes = row_nodes(snapshot)
        touching = [
            group for group in groups
            if ids & group["ids"]
            or (compatible(snapshot, group) and nodes & group["nodes"])
        ]
        if not touching:
            groups.append({"ids": set(ids), "nodes": set(nodes),
                           "rows": [snapshot]})
            continue
        primary = touching[0]
        primary["ids"].update(ids)
        primary["nodes"].update(nodes)
        primary["rows"].append(snapshot)
        for other in touching[1:]:
            primary["ids"].update(other["ids"])
            primary["nodes"].update(other["nodes"])
            primary["rows"].extend(other["rows"])
            groups.remove(other)

    merged = []
    for group in groups:
        rows = group["rows"]
        if len(rows) == 1:
            merged.append(rows[0])
            continue
        nets = {row["net_code"] for row in rows}
        layers = {row["layer"] for row in rows}
        if len(nets) != 1 or len(layers) != 1:
            return None, "overlap_crossed_net_or_layer"
        objects = {}
        for row in rows:
            for item in row["_track_objects"]:
                objects[_uuid(item)] = item
        degree = {}
        incident = {}
        for item in objects.values():
            for point in (item.GetStart(), item.GetEnd()):
                key = (point.x, point.y)
                degree[key] = degree.get(key, 0) + 1
                incident.setdefault(key, []).append(item)
        boundary = sorted(key for key, count in degree.items() if count == 1)
        if len(boundary) != 2:
            # Overlapping snapshots would delete the same object twice and
            # must fail closed.  Merely adjacent junctions retain the previous
            # independent-branch behavior.
            raw_id_count = sum(len(row["removed_uuids"]) for row in rows)
            if raw_id_count != len(objects):
                return None, "overlap_is_not_degree2_path"
            merged.extend(rows)
            continue
        start_key, end_key = boundary
        width = max(item.GetWidth() for item in objects.values())

        if board is not None:
            interior = set(degree) - {start_key, end_key}
            external_anchor = False
            for item in board.GetTracks():
                uid = _uuid(item)
                if uid in objects or item.GetNetCode() != rows[0]["net_code"]:
                    continue
                if item.GetClass() == "PCB_VIA":
                    pos = item.GetPosition()
                    if (pos.x, pos.y) in interior:
                        external_anchor = True
                        break
                elif item.GetClass() in {"PCB_TRACK", "PCB_ARC"}:
                    if item.GetLayer() != rows[0]["layer"]:
                        continue
                    if any((point.x, point.y) in interior
                           for point in (item.GetStart(), item.GetEnd())):
                        external_anchor = True
                        break
            if not external_anchor:
                for footprint in board.GetFootprints():
                    for pad in footprint.Pads():
                        if pad.GetNetCode() != rows[0]["net_code"]:
                            continue
                        if any(pad.GetBoundingBox().Contains(
                                pcbnew.VECTOR2I(*point))
                               for point in interior):
                            external_anchor = True
                            break
                    if external_anchor:
                        break
            if external_anchor:
                merged.extend(rows)
                continue

        def escape(key):
            item = incident[key][0]
            if item.GetWidth() >= width:
                return None
            length = int(round(math.hypot(
                item.GetEnd().x - item.GetStart().x,
                item.GetEnd().y - item.GetStart().y)))
            return (item.GetWidth(), length)

        merged.append({
            "requested_uuid": ",".join(sorted(
                {row["requested_uuid"] for row in rows})),
            "net": rows[0]["net"], "net_code": rows[0]["net_code"],
            "layer": rows[0]["layer"], "width": width,
            "start": pcbnew.VECTOR2I(*start_key),
            "end": pcbnew.VECTOR2I(*end_key),
            "start_escape": escape(start_key),
            "end_escape": escape(end_key),
            "source_length_nm": sum(math.hypot(
                item.GetEnd().x - item.GetStart().x,
                item.GetEnd().y - item.GetStart().y)
                for item in objects.values()),
            "removed_uuids": tuple(sorted(objects)),
            "relock": any(bool(row.get("relock")) for row in rows),
            "endpoint_neckdown_group": any(
                bool(row.get("endpoint_neckdown_group")) for row in rows),
            "_track_objects": tuple(objects[key] for key in sorted(objects)),
        })
    merged.sort(key=lambda row: (row["net"], row["layer"],
                                 row["requested_uuid"]))
    return merged, None


def _restore_displaced_branch(board, snapshot, *, board_path: str,
                              maze_margin_mm: float,
                              max_detour_ratio: float = 2.0,
                              deadline_monotonic: float | None = None):
    """Reconnect a displaced branch around the newly claimed target route."""

    start, end = snapshot["start"], snapshot["end"]
    width = int(snapshot["width"])
    layer = int(snapshot["layer"])
    net_code = int(snapshot["net_code"])
    resolver = cec_fr._project_netclass_resolver(board_path)
    spec = dict(resolver(snapshot["net"]) or {})
    clearance_mm = max(0.2, float(spec.get("clearance") or 0.0))
    clearance_nm = int(round(clearance_mm * MM))

    # Track fragments wholly embedded in one same-net pad are not electrical
    # edges.  Requiring them to be redrawn can make a valid negotiated route
    # appear unrestorable when the new copper passes near that land.  Use the
    # exact rotated/custom pad hit test—not its bounding box—and let the final
    # connectivity/DRC scorer prove that omitting the redundant fragment is
    # harmless.  This also handles THT pads naturally on every copper layer
    # they own.
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if (pad.GetNetCode() == net_code and pad.IsOnLayer(layer)
                    and pad.HitTest(start) and pad.HitTest(end)):
                return True, {
                    "net": snapshot["net"],
                    "mode": "same_pad_redundant",
                    "requested_uuid": snapshot["requested_uuid"],
                    "removed_uuids": list(snapshot["removed_uuids"]),
                    "anchor": {
                        "ref": footprint.GetReference(),
                        "pad": str(pad.GetNumber()),
                        "layer": board.GetLayerName(layer),
                    },
                    "source_length_mm": round(
                        float(snapshot["source_length_nm"]) / MM, 6),
                    "new_length_mm": 0.0,
                    "geometry": {"tracks": 0, "vias": 0,
                                 "uuids": [], "locked": False},
                }

    def edge_ok(a, b, half_width):
        return cec_fr._edge_leg_clear(board, a, b, half_width)

    operations = None
    mode = "same_layer"
    legs = cec_fr._guarded_profiled_lastmile_legs(
        board, start, end, width, layer, clearance_nm, net_code, edge_ok,
        start_escape=snapshot.get("start_escape"),
        end_escape=snapshot.get("end_escape"), allow_maze=True,
        maze_margin_mm=float(maze_margin_mm), foreign_cache={},
        deadline_monotonic=deadline_monotonic)
    precision_grid_mm = None
    if (not legs and math.hypot(end.x - start.x, end.y - start.y)
            <= 5.0 * MM):
        # The ordinary 0.5 mm maze is deliberately cheap, but a restored
        # fine-pitch support branch can have one legal channel only an eighth
        # millimetre wide.  Spend two finite local retries after the coarse
        # search fails; exact collision and edge guards remain unchanged.
        for grid_mm in (0.25, 0.125):
            legs = cec_fr._maze_lastmile_legs(
                board, start, end, width, layer, clearance_nm, net_code,
                edge_ok, start_escape=snapshot.get("start_escape"),
                end_escape=snapshot.get("end_escape"), grid_mm=grid_mm,
                margin_mm=float(maze_margin_mm), foreign_cache={},
                deadline_monotonic=deadline_monotonic)
            if legs:
                precision_grid_mm = grid_mm
                break
    if legs:
        operations = [("trk", a, b, leg_width, layer)
                      for a, b, leg_width in legs]
        if precision_grid_mm is not None:
            mode = "same_layer_precision_%.3fmm" % precision_grid_mm
    else:
        mode = "bridge"
        operations = cec_fr._lastmile_bridge(
            board, (start.x, start.y), {layer}, (end.x, end.y), {layer},
            width, net_code,
            _layer_candidates(
                board, layer, net_name=snapshot["net"], spec=spec),
            clearance_nm,
            drill=float(spec.get("via_drill") or 0.3),
            dia=float(spec.get("via_diameter") or 0.6), leg_ok=edge_ok,
            start_escape=snapshot.get("start_escape"),
            end_escape=snapshot.get("end_escape"), seat_limit=8,
            allow_maze=True, maze_margin_mm=float(maze_margin_mm),
            foreign_cache={}, deadline_monotonic=deadline_monotonic)
    if not operations:
        return False, {
            "net": snapshot["net"], "mode": mode,
            "requested_uuid": snapshot["requested_uuid"],
            "removed_uuids": list(snapshot["removed_uuids"]),
            "start_mm": [round(start.x / MM, 6), round(start.y / MM, 6)],
            "end_mm": [round(end.x / MM, 6), round(end.y / MM, 6)],
            "width_mm": round(width / MM, 6),
            "source_length_mm": round(
                float(snapshot["source_length_nm"]) / MM, 6),
            "refusal": ("displaced_branch_restore_timeout"
                        if deadline_monotonic is not None
                        and time.monotonic() >= deadline_monotonic else
                        "displaced_branch_unrestorable"),
        }
    new_length_nm = sum(math.hypot(
        op[2].x - op[1].x, op[2].y - op[1].y)
        for op in operations if op[0] != "via")
    source_length_nm = max(1.0, float(snapshot["source_length_nm"]))
    allowed_nm = source_length_nm * max(1.0, float(max_detour_ratio)) + 2 * MM
    if new_length_nm > allowed_nm + 1:
        return False, {
            "net": snapshot["net"], "mode": mode,
            "refusal": "displaced_detour_budget_exceeded",
            "source_length_mm": round(source_length_nm / MM, 6),
            "new_length_mm": round(new_length_nm / MM, 6),
            "max_detour_ratio": float(max_detour_ratio),
        }
    before_ids = {_uuid(item) for item in board.GetTracks() if _uuid(item)}
    geometry = _lay_ops(
        board, operations, net_code, lock=bool(snapshot.get("relock")))
    generated_vias = [
        item for item in board.GetTracks()
        if item.GetClass() == "PCB_VIA" and _uuid(item)
        and _uuid(item) not in before_ids and item.GetNetCode() == net_code
    ]
    local_pofv_signal_vias = cec_fr.group_local_pofv_signal_vias(
        board, generated_vias)
    if snapshot.get("endpoint_neckdown_group"):
        generated = [item for item in board.GetTracks()
                     if _uuid(item) and _uuid(item) not in before_ids
                     and item.GetNetCode() == net_code]
        full_width = int(round(float(spec.get("track_width") or
                                   width / MM) * MM))
        cec_fr.group_endpoint_neckdowns(board, generated, full_width)
    return True, {
        "net": snapshot["net"], "mode": mode,
        "requested_uuid": snapshot["requested_uuid"],
        "removed_uuids": list(snapshot["removed_uuids"]),
        "source_length_mm": round(source_length_nm / MM, 6),
        "new_length_mm": round(new_length_nm / MM, 6),
        "geometry": geometry,
        "local_pofv_signal_vias": local_pofv_signal_vias,
    }


def _restore_displaced_net(board, snapshot, *, board_path: str,
                           maze_margin_mm: float,
                           deadline_monotonic: float | None = None):
    """Fallback from an exact branch path to bounded whole-net completion.

    Once the refused route claims a corridor, an old internal waypoint may no
    longer be reachable even though the displaced net has another legal
    topology.  Reconnect the current live clusters for that one net instead of
    forcing the obsolete waypoint.  The caller still subjects the composite
    board to strict identity-aware connectivity, DRC, pair, and Kelvin gates.
    """

    net = snapshot["net"]
    before_ids = {_uuid(item) for item in board.GetTracks() if _uuid(item)}
    resolver = cec_fr._project_netclass_resolver(board_path)
    spec = dict(resolver(net) or {})
    width_mm = max(0.15, float(snapshot["width"]) / MM)
    clearance_mm = max(0.2, float(spec.get("clearance") or 0.0))
    max_mm = max(25.0, min(
        80.0, float(snapshot["source_length_nm"]) / MM + 8.0))
    remaining_s = (None if deadline_monotonic is None else
                   max(0.0, deadline_monotonic - time.monotonic()))
    if remaining_s is not None and remaining_s <= 0.0:
        return False, {
            "net": net, "mode": "network_lastmile",
            "requested_uuid": snapshot["requested_uuid"],
            "removed_uuids": list(snapshot["removed_uuids"]),
            "refusal": "displaced_net_restore_timeout",
        }
    # Restore breadth before depth.  A displaced power tree commonly has
    # several easy islands plus one genuinely trapped branch.  Sending that
    # whole frontier directly into the deep lattice/maze search lets the
    # nearest hard pair consume the transaction deadline and discards every
    # already-proven target closure.  The bounded canonical pass fairly joins
    # the easy islands first; only a still-disconnected net receives the
    # remaining deep-search budget.
    reports = []
    breadth_s = (None if remaining_s is None else min(
        30.0, max(4.0, remaining_s * 0.60)))
    breadth = cec_fr.synthesize_lastmile(
        board, max_mm=max(80.0, max_mm), min_w=width_mm,
        clearance=clearance_mm, cap=64,
        netclass_resolver=resolver, include_nets={net},
        attempts_per_pair=8, maze_max_mm=0.0,
        maze_margin_mm=2.0, bridge_fast=True,
        wall_timeout_s=breadth_s, per_net_timeout_s=breadth_s)
    reports.append({"stage": "canonical_breadth", "report": breadth})
    board.BuildConnectivity()
    net_code = board.GetNetcodeFromNetname(net)
    live_components = cec_fr.net_connectivity_component_count(
        board, net_code) if net_code > 0 else 0
    if live_components > 1:
        deep_remaining_s = (None if deadline_monotonic is None else max(
            0.0, deadline_monotonic - time.monotonic()))
        if deep_remaining_s is None or deep_remaining_s > 0.0:
            deep = cec_fr.synthesize_lastmile(
                board, max_mm=max_mm, min_w=width_mm,
                clearance=clearance_mm, cap=8,
                netclass_resolver=resolver, include_nets={net},
                attempts_per_pair=24, maze_max_mm=max_mm,
                maze_margin_mm=float(maze_margin_mm),
                wall_timeout_s=deep_remaining_s,
                per_net_timeout_s=deep_remaining_s)
            reports.append({"stage": "deep_remaining", "report": deep})
            board.BuildConnectivity()
            live_components = cec_fr.net_connectivity_component_count(
                board, net_code) if net_code > 0 else 0
    report = {
        "schema": 1,
        "net": net,
        "stages": reports,
        "closed": sum(int(row["report"].get("closed") or 0)
                      for row in reports),
        "refused": sum(int(row["report"].get("refused") or 0)
                       for row in reports),
        "live_components_after": int(live_components),
    }
    if live_components > 1:
        return False, {
            "net": net, "mode": "network_lastmile",
            "requested_uuid": snapshot["requested_uuid"],
            "removed_uuids": list(snapshot["removed_uuids"]),
            "start_mm": [round(snapshot["start"].x / MM, 6),
                         round(snapshot["start"].y / MM, 6)],
            "end_mm": [round(snapshot["end"].x / MM, 6),
                       round(snapshot["end"].y / MM, 6)],
            "width_mm": round(float(snapshot["width"]) / MM, 6),
            "source_length_mm": round(
                float(snapshot["source_length_nm"]) / MM, 6),
            "refusal": "displaced_net_unrestorable",
            "completion": report,
        }
    generated = [
        item for item in board.GetTracks()
        if _uuid(item) and _uuid(item) not in before_ids
        and item.GetNetname() == net
    ]
    if snapshot.get("relock"):
        for item in generated:
            item.SetLocked(True)
    if snapshot.get("endpoint_neckdown_group"):
        full_width = int(round(float(spec.get("track_width") or
                                   width_mm) * MM))
        cec_fr.group_endpoint_neckdowns(board, generated, full_width)
    board.BuildConnectivity()
    return True, {
        "net": net, "mode": "network_lastmile",
        "requested_uuid": snapshot["requested_uuid"],
        "removed_uuids": list(snapshot["removed_uuids"]),
        "generated_uuids": [_uuid(item) for item in generated],
        "relocked": bool(snapshot.get("relock")),
        "completion": report,
    }


def _snapshot_row(snapshot) -> dict:
    """Convert a removed-branch boundary to a process-safe JSON row."""

    row = {
        key: snapshot[key]
        for key in ("requested_uuid", "net", "net_code", "layer", "width",
                    "start_escape", "end_escape", "source_length_nm",
                    "removed_uuids")
    } | {
        "start_xy": [snapshot["start"].x, snapshot["start"].y],
        "end_xy": [snapshot["end"].x, snapshot["end"].y],
    }
    row["relock"] = bool(snapshot.get("relock"))
    row["endpoint_neckdown_group"] = bool(
        snapshot.get("endpoint_neckdown_group"))
    return row


def _snapshot_from_row(row) -> dict:
    return dict(row) | {
        "start": pcbnew.VECTOR2I(int(row["start_xy"][0]),
                                 int(row["start_xy"][1])),
        "end": pcbnew.VECTOR2I(int(row["end_xy"][0]),
                               int(row["end_xy"][1])),
    }


def _remove_negotiation_blockers(board, window: NegotiationWindow, *,
                                 branch_hops: int = 2):
    """Phase 1: remove a complete bounded blocker set and save boundaries."""

    snapshots = []
    unlock_uuids = set(window.unlock_uuids)
    requested_uuids = set(window.blocker_uuids)
    consumed_uuids = set()

    def geometry_key(item):
        ends = sorted(((item.GetStart().x, item.GetStart().y),
                       (item.GetEnd().x, item.GetEnd().y)))
        return (item.GetNetCode(), item.GetLayer(), item.GetWidth(),
                tuple(ends))

    tracks_by_geometry = {}
    for item in board.GetTracks():
        if item.GetClass() != "PCB_TRACK" or not _uuid(item):
            continue
        tracks_by_geometry.setdefault(geometry_key(item), []).append(item)
    for uid in window.blocker_uuids:
        if uid in consumed_uuids:
            continue
        item = _find_track(board, uid)
        coincident = (tracks_by_geometry.get(geometry_key(item), [])
                      if item is not None else [])
        coincident_ids = {_uuid(row) for row in coincident}
        # Same-net, same-layer tracks with identical centreline and width are
        # one electrical edge even when an earlier generator accidentally
        # emitted multiple UUIDs.  When the certificate names every copy,
        # snapshot one edge, remove all copies, and restore at most one.  This
        # avoids manufacturing a zero-length loop/false junction while never
        # broadening rip-up authority to an unlisted authored object.
        duplicate_group = (len(coincident_ids) > 1
                           and coincident_ids <= requested_uuids)
        snapshot_hops = 0 if duplicate_group else branch_hops
        snapshot, refusal = _snapshot_displaced_branch(
            board, uid, max_hops=snapshot_hops,
            allow_generated_locked=(uid in unlock_uuids))
        if snapshot is None:
            return False, {"stage": "remove_blockers", "refusal": refusal,
                           "blocked_net": window.net, "blocker_uuid": uid}, []
        if duplicate_group:
            locked_without_authority = [
                row_id for row_id, row in ((_uuid(row), row)
                                            for row in coincident)
                if row.IsLocked() and row_id not in unlock_uuids]
            if locked_without_authority:
                return False, {
                    "stage": "remove_blockers",
                    "refusal": "coincident_locked_authority_mismatch",
                    "blocked_net": window.net,
                    "blocker_uuid": uid,
                    "coincident_uuids": sorted(coincident_ids),
                }, []
            snapshot["requested_uuid"] = ",".join(sorted(coincident_ids))
            snapshot["removed_uuids"] = tuple(sorted(coincident_ids))
            snapshot["relock"] = any(row.IsLocked() for row in coincident)
            snapshot["_track_objects"] = tuple(sorted(
                coincident, key=lambda row: _uuid(row)))
            consumed_uuids.update(coincident_ids)
        snapshots.append(snapshot)
    if not snapshots:
        return False, {"stage": "remove_blockers",
                       "refusal": "no_movable_blocker_branch",
                       "blocked_net": window.net}, []
    raw_count = len(snapshots)
    snapshots, merge_refusal = _merge_overlapping_snapshots(
        snapshots, board=board)
    if snapshots is None:
        return False, {"stage": "remove_blockers",
                       "refusal": merge_refusal,
                       "blocked_net": window.net}, []
    removed = set()
    for snapshot in snapshots:
        for old in snapshot.pop("_track_objects"):
            uid = _uuid(old)
            if uid and uid not in removed:
                board.Remove(old)
                removed.add(uid)
    board.BuildConnectivity()
    return True, {
        "stage": "remove_blockers", "blocked_net": window.net,
        "removed_branches": len(snapshots),
        "coalesced_branches": raw_count - len(snapshots),
        "removed_tracks": len(removed),
    }, [_snapshot_row(snapshot) for snapshot in snapshots]


def _certificate_endpoint_anchor(board, endpoint, net_code, class_width,
                                 clearance_nm, min_width_nm):
    """Resolve one current certificate endpoint to exact live board layers."""

    kind = str(endpoint.get("kind") or "")
    target = None
    if kind == "pad":
        for footprint in board.GetFootprints():
            if footprint.GetReference() != str(endpoint.get("ref") or ""):
                continue
            target = next((pad for pad in footprint.Pads()
                           if str(pad.GetNumber()) ==
                           str(endpoint.get("pad") or "")
                           and pad.GetNetCode() == net_code), None)
            break
    elif kind == "node":
        # Component relocation deliberately removes the old pad-attached
        # segment, so its preserved far boundary no longer has a useful UUID.
        # Resolve that exact live electrical node instead of falling back to a
        # whole-net island search.  Only an existing same-net track endpoint
        # or via centre is authority; proximity is never sufficient.
        requested = pcbnew.VECTOR2I(
            int(round(float(endpoint.get("x_mm") or 0.0) * MM)),
            int(round(float(endpoint.get("y_mm") or 0.0) * MM)))
        key = (int(requested.x), int(requested.y))
        # A last-mile certificate can call a point a generic node because it
        # first encountered the attached track endpoint.  If that point is
        # exactly a same-net pad centre, retain the pad identity: treating a
        # 0.30 mm controller land as a class-width track node discards its
        # qualified neck-down and falsely reports every escape as blocked.
        exact_pads = [
            pad for footprint in board.GetFootprints() for pad in footprint.Pads()
            if pad.GetNetCode() == net_code
            and (int(pad.GetCenter().x), int(pad.GetCenter().y)) == key]
        if len(exact_pads) == 1:
            target = exact_pads[0]
            kind = "pad"
        else:
            for item in board.GetTracks():
                if item.GetNetCode() != net_code:
                    continue
                if isinstance(item, pcbnew.PCB_VIA):
                    live = item.GetPosition()
                    matches = (int(live.x), int(live.y)) == key
                else:
                    a, b = item.GetStart(), item.GetEnd()
                    matches = key in {
                        (int(a.x), int(a.y)), (int(b.x), int(b.y))}
                if matches:
                    target = item
                    break
    else:
        uid = str(endpoint.get("uuid") or "")
        target = next((item for item in board.GetTracks()
                       if _uuid(item) == uid
                       and item.GetNetCode() == net_code), None)
    if target is None:
        return None
    all_cu = set(board.GetEnabledLayers().CuStack())
    escape = None
    if kind == "pad":
        point = target.GetPosition()
        layers = frozenset(layer for layer in target.GetLayerSet().CuStack()
                           if layer in all_cu)
        try:
            is_smd = (int(target.GetAttribute()) ==
                      int(pcbnew.PAD_ATTRIB_SMD))
        except Exception:                               # noqa: BLE001
            is_smd = False
        minor = min(target.GetSize().x, target.GetSize().y)
        major = max(target.GetSize().x, target.GetSize().y)
        if is_smd and minor < class_width:
            local_width = min(
                class_width, max(int(min_width_nm), minor // 2))
            land_budget = major / 2.0 + clearance_nm + class_width / 2.0
            budget = int(round(max(
                0.6 * MM, min(1.5 * MM,
                              max(1.5 * class_width, land_budget)))))
            escape = (local_width, budget)
    elif target.GetClass() == "PCB_VIA":
        point = target.GetPosition()
        layers = frozenset(all_cu)
    else:
        requested = pcbnew.VECTOR2I(
            int(round(float(endpoint.get("x_mm") or 0.0) * MM)),
            int(round(float(endpoint.get("y_mm") or 0.0) * MM)))
        choices = (target.GetStart(), target.GetEnd())
        point = min(choices, key=lambda value: math.hypot(
            value.x - requested.x, value.y - requested.y))
        layers = frozenset((target.GetLayer(),))
    if not layers:
        return None
    return point, layers, escape, target


def _target_endpoint_retreat_candidates_worker(
        board_path, target_row, certificate, generated_locked_uuids=(),
        max_hops=4, max_length_mm=6.0):
    """Plan bounded replacements for a genuinely dangling target-net leaf.

    A relocation may preserve the far end of a direct pad stub at a point
    whose only route access is back through that same stub.  Retrying against
    the sealed tip cannot work.  This walker may shorten only a proven leaf:
    the original point must have one same-net incident track and no pad/via,
    and the walk stops at the first pad, via, junction, policy boundary, or
    finite hop/length cap.  Each returned prefix is independently retryable;
    whole-board admission later proves that superseding it did not disconnect
    any load.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    net_info = board.GetNetInfo().GetNetItem(str(target.target_net))
    if net_info is None:
        return {"candidates": [], "refusal": "retreat_net_missing"}
    net_code = int(net_info.GetNetCode())
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    endpoints = list((certificate or {}).get("endpoints") or ())
    remote = next((row for row in endpoints
                   if row.get("kind") == "node"
                   and abs(float(row.get("x_mm") or 0.0)
                           - float(target.endpoint_x_mm)) <= 1e-6
                   and abs(float(row.get("y_mm") or 0.0)
                           - float(target.endpoint_y_mm)) <= 1e-6), None)
    if remote is None:
        return {"candidates": [],
                "refusal": "retreat_endpoint_not_certified_node"}

    def key(point):
        return int(point.x), int(point.y)

    origin = (int(round(float(remote["x_mm"]) * MM)),
              int(round(float(remote["y_mm"]) * MM)))
    pads_by_node = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() != net_code:
                continue
            pads_by_node.setdefault(key(pad.GetCenter()), []).append(
                (footprint.GetReference(), str(pad.GetNumber())))
    vias_by_node = {}
    tracks_by_node = {}
    track_by_uuid = {}
    for item in board.GetTracks():
        if item.GetNetCode() != net_code:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            vias_by_node.setdefault(key(item.GetPosition()), []).append(item)
            continue
        if item.GetClass() != "PCB_TRACK":
            continue
        uid = _uuid(item)
        if not uid:
            continue
        track_by_uuid[uid] = item
        tracks_by_node.setdefault(key(item.GetStart()), []).append(item)
        tracks_by_node.setdefault(key(item.GetEnd()), []).append(item)

    if pads_by_node.get(origin):
        return {"candidates": [], "refusal": "retreat_origin_is_pad"}
    if vias_by_node.get(origin):
        return {"candidates": [], "refusal": "retreat_origin_is_via"}
    incident = tracks_by_node.get(origin) or ()
    if len(incident) != 1:
        return {"candidates": [],
                "refusal": "retreat_origin_not_single_track_leaf",
                "incident_tracks": len(incident)}

    group_names_by_uuid = {}
    for group in board.Groups():
        name = str(group.GetName() or "")
        for uid, item in track_by_uuid.items():
            if group.ContainsItem(item):
                group_names_by_uuid.setdefault(uid, set()).add(name)

    current = origin
    previous_uid = None
    removed = []
    walked_nm = 0.0
    candidates = []
    stop_reason = "retreat_hop_cap"
    for _hop in range(max(0, int(max_hops))):
        choices = [item for item in tracks_by_node.get(current, ())
                   if _uuid(item) != previous_uid]
        if len(choices) != 1:
            stop_reason = ("retreat_reached_junction" if len(choices) > 1
                           else "retreat_reached_dead_end")
            break
        item = choices[0]
        uid = _uuid(item)
        layer = board.GetLayerName(item.GetLayer())
        groups = group_names_by_uuid.get(uid, set())
        if groups and groups != {cec_fr.ENDPOINT_NECKDOWN_GROUP}:
            stop_reason = "retreat_explicit_group_ownership"
            break
        if item.IsLocked() and uid not in generated:
            stop_reason = "retreat_authored_locked_track"
            break
        reason = protected_net_reason(
            item.GetNetname() or "", width_mm=item.GetWidth() / MM,
            layer=layer, locked=False)
        if reason:
            stop_reason = "retreat_%s" % reason
            break
        other = (_other_end(item, pcbnew.VECTOR2I(*current)))
        if other is None:
            stop_reason = "retreat_topology_mismatch"
            break
        segment_nm = math.hypot(other.x - current[0], other.y - current[1])
        if walked_nm + segment_nm > max(0.0, float(max_length_mm)) * MM:
            stop_reason = "retreat_length_cap"
            break
        walked_nm += segment_nm
        removed.append(uid)
        current = key(other)
        previous_uid = uid

        pad_rows = pads_by_node.get(current) or ()
        via_rows = vias_by_node.get(current) or ()
        remaining = [row for row in tracks_by_node.get(current, ())
                     if _uuid(row) not in set(removed)]
        endpoint = {"kind": "node", "x_mm": current[0] / MM,
                    "y_mm": current[1] / MM}
        if len(pad_rows) == 1:
            endpoint.update({"kind": "pad", "ref": pad_rows[0][0],
                             "pad": pad_rows[0][1]})
        # The newly exposed boundary must remain a live electrical anchor once
        # the prefix is removed.  A second bare dead end is not an improvement.
        if pad_rows or via_rows or remaining:
            candidates.append({
                "original_endpoint": dict(remote),
                "endpoint": endpoint,
                "removed_uuids": list(removed),
                "hops": len(removed),
                "removed_length_mm": round(walked_nm / MM, 6),
                "boundary": ("pad" if pad_rows else
                             "via" if via_rows else
                             "junction" if len(remaining) > 1 else "track"),
            })
        if pad_rows:
            stop_reason = "retreat_reached_pad"
            break
        if via_rows:
            stop_reason = "retreat_reached_via"
            break
        if len(remaining) != 1:
            stop_reason = ("retreat_reached_junction"
                           if len(remaining) > 1
                           else "retreat_reached_dead_end")
            break
    return {
        "schema": 1, "net": str(target.target_net),
        "origin": {"x_mm": origin[0] / MM, "y_mm": origin[1] / MM},
        "candidates": candidates, "stop_reason": stop_reason,
    }


def _target_endpoint_access_candidates_worker(
        board_path, target_row, certificate, max_hops=6,
        max_length_mm=8.0, limit=8):
    """Enumerate live access nodes on the endpoint's same-net component.

    Exact pair identity is valuable, but the physical pad centre is not the
    only legal attachment point once an existing branch already connects that
    pad to the routed component.  Walk only exact track endpoints (and stop at
    foreign pads) so a moved support can tee into the nearest exposed point
    without deleting, moving, or reinterpreting any existing copper.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    net_info = board.GetNetInfo().GetNetItem(str(target.target_net))
    if net_info is None:
        return {"candidates": [], "refusal": "access_net_missing"}
    net_code = int(net_info.GetNetCode())
    endpoints = list((certificate or {}).get("endpoints") or ())
    remote = next((row for row in endpoints
                   if abs(float(row.get("x_mm") or 0.0)
                          - float(target.endpoint_x_mm)) <= 1e-6
                   and abs(float(row.get("y_mm") or 0.0)
                          - float(target.endpoint_y_mm)) <= 1e-6), None)
    if remote is None:
        return {"candidates": [],
                "refusal": "access_endpoint_not_certified"}

    def key(point):
        return int(point.x), int(point.y)

    origin = (int(round(float(remote["x_mm"]) * MM)),
              int(round(float(remote["y_mm"]) * MM)))
    pads_by_node = {}
    vias_by_node = {}
    tracks_by_node = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() == net_code:
                pads_by_node.setdefault(key(pad.GetCenter()), []).append(
                    (footprint.GetReference(), str(pad.GetNumber())))
    for item in board.GetTracks():
        if item.GetNetCode() != net_code:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            vias_by_node.setdefault(key(item.GetPosition()), []).append(item)
        elif item.GetClass() == "PCB_TRACK" and _uuid(item):
            tracks_by_node.setdefault(key(item.GetStart()), []).append(item)
            tracks_by_node.setdefault(key(item.GetEnd()), []).append(item)
    if not (pads_by_node.get(origin) or vias_by_node.get(origin)
            or tracks_by_node.get(origin)):
        return {"candidates": [], "refusal": "access_origin_not_live"}

    target_fp = board.FindFootprintByReference(target.ref)
    target_points = ([] if target_fp is None else [
        pad.GetCenter() for pad in target_fp.Pads()
        if str(pad.GetNetname() or "") == str(target.target_net)])
    queue = [(origin, 0, 0.0, ())]
    best = {origin: (0, 0.0)}
    candidates = []
    while queue:
        current, hops, walked_nm, path = queue.pop(0)
        if hops >= max(0, int(max_hops)):
            continue
        incident = sorted(tracks_by_node.get(current, ()), key=_uuid)
        for item in incident:
            uid = _uuid(item)
            if uid in path:
                continue
            other = _other_end(item, pcbnew.VECTOR2I(*current))
            if other is None:
                continue
            other_key = key(other)
            segment_nm = math.hypot(
                other.x - current[0], other.y - current[1])
            next_length = walked_nm + segment_nm
            if next_length > max(0.0, float(max_length_mm)) * MM:
                continue
            next_hops = hops + 1
            previous = best.get(other_key)
            if previous is not None and previous <= (next_hops, next_length):
                continue
            best[other_key] = (next_hops, next_length)
            next_path = path + (uid,)
            pad_rows = pads_by_node.get(other_key) or ()
            endpoint = {"kind": "node", "x_mm": other_key[0] / MM,
                        "y_mm": other_key[1] / MM}
            if len(pad_rows) == 1:
                endpoint.update({"kind": "pad", "ref": pad_rows[0][0],
                                 "pad": pad_rows[0][1]})
            target_distance = min((math.hypot(
                point.x - other_key[0], point.y - other_key[1]) / MM
                for point in target_points), default=1e9)
            candidates.append({
                "endpoint": endpoint, "access_path_uuids": list(next_path),
                "hops": next_hops,
                "access_length_mm": round(next_length / MM, 6),
                "target_distance_mm": round(target_distance, 6),
                "boundary": ("pad" if pad_rows else
                             "via" if vias_by_node.get(other_key) else
                             "junction" if len(
                                 tracks_by_node.get(other_key, ())) > 2
                             else "track"),
            })
            # A different pad is already a complete electrical anchor.  Do
            # not walk through its land into another local branch.
            if not pad_rows:
                queue.append((other_key, next_hops, next_length, next_path))
    candidates.sort(key=lambda row: (
        row["hops"], row["target_distance_mm"], row["access_length_mm"],
        tuple(row["access_path_uuids"])))
    return {
        "schema": 1, "net": str(target.target_net),
        "origin": {"x_mm": origin[0] / MM, "y_mm": origin[1] / MM},
        "candidates": candidates[:max(0, int(limit))],
    }


def _apply_target_endpoint_retreat_worker(
        board_path, target_net, candidate, generated_locked_uuids=()):
    """Remove one pre-certified target leaf prefix on a scratch board."""

    board = pcbnew.LoadBoard(board_path)
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    requested = tuple(str(uid) for uid in candidate.get("removed_uuids") or ())
    items = []
    for uid in requested:
        item = _find_track(board, uid)
        if item is None or str(item.GetNetname() or "") != str(target_net):
            return False, {"refusal": "retreat_track_not_live", "uuid": uid}
        groups = {str(group.GetName() or "") for group in board.Groups()
                  if group.ContainsItem(item)}
        if groups and groups != {cec_fr.ENDPOINT_NECKDOWN_GROUP}:
            return False, {"refusal": "retreat_explicit_group_ownership",
                           "uuid": uid}
        if item.IsLocked() and uid not in generated:
            return False, {"refusal": "retreat_authored_locked_track",
                           "uuid": uid}
        reason = protected_net_reason(
            item.GetNetname() or "", width_mm=item.GetWidth() / MM,
            layer=board.GetLayerName(item.GetLayer()), locked=False)
        if reason:
            return False, {"refusal": "retreat_%s" % reason, "uuid": uid}
        items.append(item)
    for item in items:
        board.Remove(item)
    board.BuildConnectivity()
    pcbnew.SaveBoard(board_path, board)
    return True, {
        "net": str(target_net), "removed_uuids": list(requested),
        "removed_tracks": len(items),
        "removed_length_mm": float(candidate.get("removed_length_mm") or 0.0),
        "target_endpoint_override": dict(candidate.get("endpoint") or {}),
    }


def _close_certificate_pair(board, window: NegotiationWindow, *,
                            board_path: str, prefer_bridge: bool,
                            wall_timeout_s: float | None = None):
    """Route the exact live refusal pair before searching every net island."""

    if len(window.endpoints) != 2:
        return False, {"refusal": "certificate_pair_not_binary"}
    net_info = board.GetNetInfo().GetNetItem(window.net)
    if net_info is None:
        return False, {"refusal": "certificate_net_missing"}
    net_code = int(net_info.GetNetCode())
    resolver = cec_fr._project_netclass_resolver(board_path)
    spec = dict(resolver(window.net) or {})
    base_width_mm = max(0.15, float(window.width_mm),
                        float(spec.get("track_width") or 0.0))
    base_width = int(round(base_width_mm * MM))
    clearance_nm = int(round(max(
        0.0, float(window.clearance_mm),
        float(spec.get("clearance") or 0.0)) * MM))
    try:
        min_width_nm = max(
            1, int(board.GetDesignSettings().m_TrackMinWidth))
    except Exception:                                  # noqa: BLE001
        min_width_nm = int(round(min(0.20, base_width_mm) * MM))
    anchors = [
        _certificate_endpoint_anchor(
            board, endpoint, net_code, base_width, clearance_nm,
            min_width_nm)
        for endpoint in window.endpoints]
    if any(anchor is None for anchor in anchors):
        return False, {"refusal": "certificate_endpoint_not_live"}
    (start, start_layers, start_escape, _start_item), \
        (end, end_layers, end_escape, _end_item) = anchors
    deadline = (None if wall_timeout_s is None else
                time.monotonic() + max(0.0, float(wall_timeout_s)))
    bridge_layers = cec_fr._lastmile_route_layers(
        board, net_name=window.net, spec=spec, exclude_front=True)
    same_layer_authority = set(cec_fr._lastmile_route_layers(
        board, net_name=window.net, spec=spec, exclude_front=False))
    # Use actual zone authority, not a stale/global name.  A refactor moved
    # layer selection into cec_fr but left the old local ``plane`` identifier
    # behind, so every atomic negotiation failed before evaluating geometry.
    plane = {
        int(layer_id)
        for layer_name in cec_fr.plane_layers(board)
        for layer_id in (board.GetLayerID(layer_name),)
        if int(layer_id) >= 0
    }

    def width_for_layer(layer):
        by_layer = spec.get("track_width_by_layer_mm") or {}
        return int(round(max(
            base_width_mm,
            float(by_layer.get(board.GetLayerName(layer)) or 0.0)) * MM))

    def edge_ok(a, b, half_width):
        return cec_fr._edge_leg_clear(board, a, b, half_width)

    def bridge_ops(phase_deadline=None):
        return cec_fr._lastmile_bridge(
            board, (start.x, start.y), start_layers,
            (end.x, end.y), end_layers, base_width, net_code,
            bridge_layers, clearance_nm,
            drill=float(spec.get("via_drill") or 0.3),
            dia=float(spec.get("via_diameter") or 0.6),
            leg_ok=edge_ok, start_escape=start_escape,
            end_escape=end_escape, seat_limit=8, allow_maze=True,
            maze_margin_mm=max(4.0, float(window.distance_mm) * 0.25),
            foreign_cache={}, width_for_layer=width_for_layer,
            seat_offsets_mm=(0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0),
            seat_angles_deg=(0, 90, 180, 270), allow_lattice=False,
            deadline_monotonic=phase_deadline)

    # A finite exact-pair attempt is a portfolio of route families, not a
    # winner-takes-all call to whichever family happens to run first.  Dense
    # multilayer boards used to let the preferred bridge (or the first common
    # layer) consume the entire deadline, so the report said ``search_timeout``
    # without ever evaluating the other legal escape.  Reserve milestones for
    # bridge-first, same-layer, and final bridge search while rolling any time
    # saved by an early refusal into the later phases.
    phase_started = time.monotonic()
    total_timeout_s = (None if deadline is None else
                       max(0.0, deadline - phase_started))

    def phase_milestone(fraction):
        if deadline is None or total_timeout_s is None:
            return None
        return min(deadline, phase_started + total_timeout_s * fraction)

    initial_bridge_deadline = phase_milestone(0.40)
    same_layer_phase_deadline = phase_milestone(
        0.75 if prefer_bridge else 0.65)
    operations = (bridge_ops(initial_bridge_deadline)
                  if prefer_bridge else None)
    if operations is None:
        common = sorted(
            ((start_layers & end_layers) & same_layer_authority) - plane,
                        key=lambda layer: (
                            0 if "SIG" in board.GetLayerName(layer).upper()
                            else 1, layer))
        for layer_index, layer in enumerate(common):
            width = width_for_layer(layer)
            if same_layer_phase_deadline is None:
                layer_deadline = None
            else:
                remaining_s = max(
                    0.0, same_layer_phase_deadline - time.monotonic())
                remaining_layers = max(1, len(common) - layer_index)
                if remaining_s <= 0.0:
                    break
                # One difficult layer must not consume the whole exact-pair
                # budget and silently prevent every other authorized copper
                # layer from being evaluated.  The outer transaction remains
                # finite; this simply shares its remaining slice fairly.
                layer_deadline = min(
                    same_layer_phase_deadline,
                    time.monotonic() + remaining_s / remaining_layers)
            legs = cec_fr._guarded_profiled_lastmile_legs(
                board, start, end, width, layer, clearance_nm, net_code,
                edge_ok, start_escape=start_escape, end_escape=end_escape,
                allow_maze=True,
                maze_margin_mm=max(4.0, float(window.distance_mm) * 0.25),
                foreign_cache={}, deadline_monotonic=layer_deadline)
            if legs:
                operations = [("trk", a, b, leg_width, layer)
                              for a, b, leg_width in legs]
                break
    if operations is None:
        # This is the only phase allowed to use the final deadline.  For a
        # same-layer-first net it is the first bridge attempt; for a
        # bridge-first net it is a broader retry after every common layer had
        # a bounded chance.
        operations = bridge_ops(deadline)
    if operations is None:
        endpoint_owned = set(cec_fr._endpoint_bridge_layers(
            board, start_layers, end_layers, bridge_layers))
        diagnostic_layers = sorted(
            (same_layer_authority | set(bridge_layers) | endpoint_owned)
            - set(plane))
        certificate = cec_fr._lastmile_refusal_certificate(
            board, start, end, base_width, clearance_nm, net_code,
            diagnostic_layers,
            endpoint_a=dict(window.endpoints[0]),
            endpoint_b=dict(window.endpoints[1]),
            maze_searched=True,
            maze_margin_mm=max(
                4.0, float(window.distance_mm) * 0.25),
            attempts_per_pair=8,
            start_escape=start_escape, end_escape=end_escape)
        return False, {
            "refusal": ("certificate_pair_search_timeout"
                        if deadline is not None
                        and time.monotonic() >= deadline else
                        "certificate_pair_no_exact_clear_path"),
            "certificate": certificate,
        }
    before_ids = {_uuid(item) for item in board.GetTracks() if _uuid(item)}
    geometry = _lay_ops(board, operations, net_code, lock=False)
    new_items = [item for item in board.GetTracks()
                 if _uuid(item) and _uuid(item) not in before_ids]
    pofv = cec_fr.group_local_pofv_signal_vias(
        board, [item for item in new_items
                if item.GetClass() == "PCB_VIA"])
    return True, {
        "schema": 1, "closed": 1, "legs": geometry["tracks"],
        "vias": geometry["vias"], "refused": 0, "far": 0,
        "cross_layer": 0, "timed_out": False,
        "elapsed_s": None, "refused_details": [], "far_details": [],
        "closed_details": [{
            "net": window.net, "distance_mm": float(window.distance_mm),
            "mode": "certificate_exact_pair", "legs": geometry["tracks"],
            "vias": geometry["vias"],
        }],
        "local_pofv_signal_vias": pofv,
        "exact_pair_geometry": geometry,
    }


def _close_negotiation_target(board, window: NegotiationWindow, *,
                              board_path: str, attempt_budget: int,
                              maze_margin_mm: float,
                              prefer_bridge: bool | None = None,
                              wall_timeout_s: float | None = None):
    """Phase 2: let the refused net claim the newly vacated corridor."""

    resolver = cec_fr._project_netclass_resolver(board_path)
    target_started = time.monotonic()
    exact_changed, exact_completion = _close_certificate_pair(
        board, window, board_path=board_path,
        prefer_bridge=(bool(window.local_pin_escape)
                       if prefer_bridge is None else bool(prefer_bridge)),
        wall_timeout_s=wall_timeout_s)
    if exact_changed:
        return True, {
            "stage": "close_blocked_net", "blocked_net": window.net,
            "completion": exact_completion,
        }
    if exact_completion.get("refusal") == \
            "certificate_pair_search_timeout":
        return False, {
            "stage": "close_blocked_net", "blocked_net": window.net,
            "refusal": "blocked_net_still_refused",
            "exact_pair_refusal": exact_completion,
            "completion": {
                "closed": 0, "refused": 1, "far": 0,
                "cross_layer": 0, "timed_out": True,
                "elapsed_s": round(time.monotonic() - target_started, 3),
                "timeout_detail": {
                    "stage": "certificate_exact_pair",
                    "net": window.net,
                    "reason": "pair_wall_clock_budget_exhausted",
                },
                "refused_details": [], "far_details": [],
            },
        }
    remaining_wall_s = (None if wall_timeout_s is None else max(
        0.0, float(wall_timeout_s) -
        (time.monotonic() - target_started)))
    if remaining_wall_s is not None and remaining_wall_s <= 0.0:
        return False, {
            "stage": "close_blocked_net", "blocked_net": window.net,
            "refusal": "blocked_net_still_refused",
            "exact_pair_refusal": exact_completion,
            "completion": {"closed": 0, "refused": 1,
                           "timed_out": True, "elapsed_s": 0.0,
                           "refused_details": [], "far_details": []},
        }
    max_mm = max(25.0, min(80.0, float(window.distance_mm) + 8.0))
    completion = cec_fr.synthesize_lastmile(
        board, max_mm=max_mm,
        # ``min_w`` is the fabrication-qualified local neck-down floor, not
        # the target net's trunk width.  Feeding a 0.50 mm power width back as
        # the minimum disabled fine-pitch pad escapes during negotiation.
        min_w=min(0.25, max(0.15, window.width_mm)),
        # The collision index retains every foreign object's project
        # clearance.  A zero caller floor therefore selects the exact
        # pairwise max(net clearance, object clearance) instead of carrying a
        # stale refusal certificate's historical 0.25 mm search margin into
        # a board whose authoritative classes are 0.20 mm.
        clearance=0.0, cap=12,
        netclass_resolver=resolver, include_nets={window.net},
        attempts_per_pair=int(attempt_budget), maze_max_mm=max_mm,
        maze_margin_mm=float(maze_margin_mm),
        prefer_bridge=(bool(window.local_pin_escape)
                       if prefer_bridge is None else bool(prefer_bridge)),
        wall_timeout_s=remaining_wall_s,
        per_net_timeout_s=remaining_wall_s)
    if not completion.get("closed"):
        return False, {
            "stage": "close_blocked_net", "blocked_net": window.net,
            "refusal": "blocked_net_still_refused",
            "exact_pair_refusal": exact_completion,
            "completion": completion,
        }
    return True, {"stage": "close_blocked_net",
                  "blocked_net": window.net, "completion": completion}


def _restore_negotiation_blockers(board, snapshot_rows, *, board_path: str,
                                  maze_margin_mm: float,
                                  max_detour_ratio: float,
                                  order_mode: str = "hardest_first",
                                  wall_timeout_s: float | None = None):
    """Phase 3: restore every displaced branch around the new target route."""

    restored = []
    deadline_monotonic = (
        None if wall_timeout_s is None else
        time.monotonic() + max(0.0, float(wall_timeout_s)))
    # Restore the geometrically hardest branch first while all of its original
    # alternatives are still available; later branches see both the newly
    # claimed target route and every earlier restoration as real obstacles.
    snapshots = [_snapshot_from_row(row) for row in snapshot_rows]
    if order_mode == "hardest_first":
        snapshots.sort(key=lambda row: (-row["width"],
                                        -row["source_length_nm"], row["net"]))
    elif order_mode == "easiest_first":
        snapshots.sort(key=lambda row: (row["width"],
                                        row["source_length_nm"], row["net"]))
    else:
        raise ValueError("unknown restoration order %r" % order_mode)
    # Several certificate UUIDs from one net are one restoration problem, but
    # their saved branch boundaries remain much tighter authority than a
    # board-scale whole-net search.  Try every bounded boundary first; same-net
    # copper cannot block its siblings.  Only a boundary that cannot be
    # recovered triggers one grouped live-topology fallback.  This avoids
    # turning a local rip-up into a long reconstruction of an otherwise routed
    # 40+ mm control network.
    grouped = {}
    net_order = []
    for snapshot in snapshots:
        net = str(snapshot.get("net") or "")
        if net not in grouped:
            grouped[net] = []
            net_order.append(net)
        grouped[net].append(snapshot)
    restoration_groups = [grouped[net] for net in net_order]

    for snapshot_group in restoration_groups:
        if len(snapshot_group) > 1:
            # Escape a real package land before replaying remote trunks.  A
            # long branch is often geometrically easy, while a short
            # fine-pitch neckdown has only one viable first millimetre.  The
            # global hardest/easiest order remains authoritative between nets;
            # inside one same-net group, pin access owns route-order priority.
            snapshot_group = sorted(
                snapshot_group,
                key=lambda row: (
                    0 if (row.get("start_escape") is not None
                          or row.get("end_escape") is not None) else 1,
                    float(row.get("source_length_nm") or 0.0),
                    str(row.get("requested_uuid") or "")))
            snapshot = dict(snapshot_group[0])
            snapshot.update({
                "requested_uuid": ",".join(sorted(
                    {str(row.get("requested_uuid") or "")
                     for row in snapshot_group
                     if row.get("requested_uuid")})),
                "removed_uuids": tuple(sorted({
                    str(uid) for row in snapshot_group
                    for uid in row.get("removed_uuids") or () if uid})),
                "source_length_nm": sum(float(
                    row.get("source_length_nm") or 0.0)
                    for row in snapshot_group),
                "width": min(int(row["width"])
                             for row in snapshot_group),
                "relock": any(bool(row.get("relock"))
                              for row in snapshot_group),
                "endpoint_neckdown_group": any(bool(
                    row.get("endpoint_neckdown_group"))
                    for row in snapshot_group),
            })
            branch_attempts = []
            exact_ok = True
            exact_phase_deadline = deadline_monotonic
            if deadline_monotonic is not None:
                now = time.monotonic()
                exact_phase_deadline = now + max(
                    0.0, deadline_monotonic - now) * 0.60
            branch_weights = [
                4.0 if (branch.get("start_escape") is not None
                        or branch.get("end_escape") is not None) else 1.0
                for branch in snapshot_group]
            for branch_index, branch in enumerate(snapshot_group):
                branch_deadline = exact_phase_deadline
                if exact_phase_deadline is not None:
                    now = time.monotonic()
                    remaining = max(0.0, exact_phase_deadline - now)
                    remaining_weight = max(
                        1.0, sum(branch_weights[branch_index:]))
                    branch_deadline = min(
                        exact_phase_deadline,
                        now + remaining *
                        branch_weights[branch_index] / remaining_weight)
                branch_ok, branch_evidence = _restore_displaced_branch(
                    board, branch, board_path=board_path,
                    maze_margin_mm=maze_margin_mm,
                    max_detour_ratio=max_detour_ratio,
                    deadline_monotonic=branch_deadline)
                branch_attempts.append(branch_evidence)
                exact_ok = exact_ok and branch_ok
            if exact_ok:
                ok = True
                evidence = {
                    "net": snapshot["net"],
                    "mode": "boundary_group_lastmile",
                    "requested_uuid": snapshot["requested_uuid"],
                    "removed_uuids": list(snapshot["removed_uuids"]),
                    "branch_attempts": branch_attempts,
                }
            else:
                ok, evidence = _restore_displaced_net(
                    board, snapshot, board_path=board_path,
                    maze_margin_mm=maze_margin_mm,
                    deadline_monotonic=deadline_monotonic)
                evidence["branch_attempts"] = branch_attempts
                if ok:
                    evidence["mode"] = "network_group_lastmile"
            evidence["snapshot_count"] = len(snapshot_group)
            restored.append(evidence)
            if not ok:
                return False, {
                    "stage": "restore_blockers",
                    "refusal": evidence.get("refusal"),
                    "restored": restored, "order_mode": order_mode,
                }
            continue

        snapshot = snapshot_group[0]
        ok, evidence = _restore_displaced_branch(
            board, snapshot, board_path=board_path,
            maze_margin_mm=maze_margin_mm,
            max_detour_ratio=max_detour_ratio,
            deadline_monotonic=deadline_monotonic)
        if not ok:
            branch_refusal = evidence
            ok, evidence = _restore_displaced_net(
                board, snapshot, board_path=board_path,
                maze_margin_mm=maze_margin_mm,
                deadline_monotonic=deadline_monotonic)
            evidence["branch_refusal"] = branch_refusal
        restored.append(evidence)
        if not ok:
            return False, {
                "stage": "restore_blockers",
                "refusal": evidence.get("refusal"),
                "restored": restored, "order_mode": order_mode,
            }
    board.BuildConnectivity()
    return True, {
        "stage": "restore_blockers", "restored": restored,
        "order_mode": order_mode,
        "snapshot_groups": len(restoration_groups),
    }


def _metric_row(metrics, drc_data=None) -> dict:
    row = cec_stage_admission.snapshot(metrics)
    row.update({
        "vias": int(metrics.vias),
        "tracks": int(metrics.tracks),
        "length_mm": round(float(metrics.length), 3),
        "drc_types": dict(metrics.drc_types),
    })
    # Legacy/mocked Metrics may not carry scorer-authoritative violation rows.
    # Retain the exact raw-DCR fallback for those callers only.
    if drc_data is not None and not row["structural_drc_identities"]:
        row["structural_drc_identities"] = _structural_drc_identities(
            drc_data)
    return row


def _accepts(before, after) -> tuple[bool, str]:
    return cec_stage_admission.accepts(
        before, after, require_strict=True)


def _placement_preflight_accepts(before, after) -> tuple[bool, str, list[str]]:
    """Reject new physical collisions before expensive route reconstruction.

    A footprint transaction intentionally removes its incident branches, so
    connectivity, dangling-item, pair, Kelvin, and route-topology gates may
    regress temporarily.  Direct shorts, clearance faults, hole collisions,
    mask bridges, and courtyard overlaps cannot be healed by reconnecting the
    removed branches.  Letting such a pose into the expensive reconstruction
    stage wastes the wave budget and lets the router obscure the actual
    placement defect.

    Compare identity sets rather than aggregate DRC counts so a move cannot
    trade an existing violation for a different short or clearance fault.
    """

    physical_types = {
        "clearance", "courtyards_overlap", "hole_clearance",
        "hole_to_hole", "shorting_items", "solder_mask_bridge",
    }

    def physical_identities(row):
        result = set()
        for identity in row.get("structural_drc_identities") or ():
            try:
                kind = str(json.loads(identity)[0])
            except (IndexError, TypeError, ValueError, json.JSONDecodeError):
                # Unknown legacy identities are intentionally left to the
                # ordinary final admission gate; they cannot be classified as
                # pose-intrinsic physical faults here.
                continue
            if kind in physical_types:
                result.add(identity)
        return result

    old_identities = physical_identities(before)
    new_identities = sorted(
        physical_identities(after) - old_identities)
    if new_identities:
        return False, "placement_preflight_drc_regressed", new_identities
    return True, "placement_preflight_clear", []


def _classify_placement_conflicts_worker(
        board_path, drc_data, target_row, move, generated_locked_uuids=()):
    """Attribute pose-intrinsic DRC faults to exact movable/fixed objects.

    The classifier is board-agnostic: moved ownership comes from the proposed
    placement transaction, route provenance comes from the authored baseline,
    and every cause is attached to KiCad's exact violation UUIDs.  This makes
    a rejection actionable by a later resolver instead of merely recording
    that one named component was "too close" to something.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    moved_refs = {target.ref, *map(str, target.companion_refs)}
    moved_route_uuids = set(move.get("moved_pad_via_uuids") or ())
    moved_route_uuids.update(move.get("moved_internal_track_uuids") or ())
    moved_route_uuids.update(
        move.get("placement_relocated_via_uuids") or ())
    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}
    generated_locked.update(
        str(uid) for uid in
        (move.get("placement_generated_locked_uuids") or ()) if uid)
    items = {}

    def put(uid, **metadata):
        if uid:
            items[str(uid)] = metadata

    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference() or "")
        footprint_position = footprint.GetPosition()
        put(_uuid(footprint), kind="footprint", ref=ref, net="",
            locked=bool(footprint.IsLocked()), moved=ref in moved_refs,
            x_nm=int(footprint_position.x), y_nm=int(footprint_position.y))
        for pad in footprint.Pads():
            pad_position = pad.GetCenter()
            put(_uuid(pad), kind="pad", ref=ref,
                net=str(pad.GetNetname() or ""),
                locked=bool(footprint.IsLocked()), moved=ref in moved_refs,
                x_nm=int(pad_position.x), y_nm=int(pad_position.y))
    for item in board.GetTracks():
        uid = _uuid(item)
        if item.GetClass() == "PCB_VIA":
            position = item.GetPosition()
            x_nm, y_nm = int(position.x), int(position.y)
            # KiCad 10 requires a layer for via width; the no-argument SWIG
            # overload logs one assertion per call and can flood unattended
            # wave logs even though it returns the same through-via diameter.
            diameter_nm = int(item.GetWidth(pcbnew.F_Cu))
            drill_nm = int(item.GetDrill())
        else:
            start, end = item.GetStart(), item.GetEnd()
            x_nm = int(round((start.x + end.x) / 2.0))
            y_nm = int(round((start.y + end.y) / 2.0))
            diameter_nm = drill_nm = 0
        put(uid, kind=("via" if item.GetClass() == "PCB_VIA" else "track"),
            ref="", net=str(item.GetNetname() or ""),
            locked=bool(item.IsLocked()), moved=uid in moved_route_uuids,
            pipeline_movable=(not item.IsLocked()
                              or uid in generated_locked),
            x_nm=x_nm, y_nm=y_nm, diameter_nm=diameter_nm,
            drill_nm=drill_nm)
    for zone in board.Zones():
        put(_uuid(zone), kind="zone", ref="",
            net=str(zone.GetNetname() or ""),
            locked=bool(zone.IsLocked()), moved=False,
            pipeline_movable=False)

    physical_types = {
        "clearance", "courtyards_overlap", "hole_clearance",
        "hole_to_hole", "shorting_items", "solder_mask_bridge",
    }
    rows, causes, movable_copper, movable_tracks, movable_vias, fixed = \
        [], {}, set(), set(), set(), []
    movable_via_evidence = {}
    for violation in (drc_data or {}).get("violations") or ():
        violation_type = str(violation.get("type") or "")
        if violation_type not in physical_types:
            continue
        violation_items = []
        for item in violation.get("items") or ():
            uid = str(item.get("uuid") or "")
            metadata = dict(items.get(uid) or {})
            metadata.update({
                "uuid": uid,
                "description": str(item.get("description") or ""),
            })
            violation_items.append(metadata)
        if not any(item.get("moved") for item in violation_items):
            continue
        stationary = [item for item in violation_items
                      if not item.get("moved")]
        row_causes = set()
        if not stationary:
            row_causes.add("cell_self_collision")
        for item in stationary:
            kind = item.get("kind")
            if kind in {"footprint", "pad"}:
                row_causes.add("stationary_component_collision")
            elif kind in {"track", "via"}:
                if item.get("pipeline_movable"):
                    row_causes.add("pipeline_copper_collision")
                    if item.get("uuid"):
                        movable_copper.add(str(item["uuid"]))
                        if kind == "track":
                            movable_tracks.add(str(item["uuid"]))
                        elif kind == "via":
                            via_uid = str(item["uuid"])
                            movable_vias.add(via_uid)
                            evidence = movable_via_evidence.setdefault(
                                via_uid, {
                                    "uuid": via_uid,
                                    "net": str(item.get("net") or ""),
                                    "x_nm": int(item.get("x_nm") or 0),
                                    "y_nm": int(item.get("y_nm") or 0),
                                    "diameter_nm": int(
                                        item.get("diameter_nm") or 0),
                                    "drill_nm": int(
                                        item.get("drill_nm") or 0),
                                    "counterpart_uuids": set(),
                                    "drc_types": set(),
                                    "away_dx": 0,
                                    "away_dy": 0,
                                    "direction_samples": 0,
                                    "priority": (),
                                })
                            evidence["drc_types"].add(violation_type)
                            for moved_item in violation_items:
                                if not moved_item.get("moved"):
                                    continue
                                counterpart = str(
                                    moved_item.get("uuid") or "")
                                if counterpart:
                                    evidence["counterpart_uuids"].add(
                                        counterpart)
                                if (moved_item.get("x_nm") is not None
                                        and moved_item.get("y_nm") is not None):
                                    evidence["away_dx"] += int(
                                        item.get("x_nm") or 0) - int(
                                            moved_item.get("x_nm") or 0)
                                    evidence["away_dy"] += int(
                                        item.get("y_nm") or 0) - int(
                                            moved_item.get("y_nm") or 0)
                                    evidence["direction_samples"] += 1
                else:
                    row_causes.add("authored_copper_collision")
            elif kind == "zone":
                row_causes.add("zone_rule_collision")
            else:
                row_causes.add("unclassified_physical_collision")
        for cause in row_causes:
            causes[cause] = causes.get(cause, 0) + 1
        row = {
            "type": violation_type,
            "causes": sorted(row_causes),
            "items": violation_items,
        }
        rows.append(row)
        if row_causes - {"pipeline_copper_collision"}:
            fixed.append(row)
    via_targets = []
    for uid in sorted(movable_via_evidence):
        evidence = movable_via_evidence[uid]
        samples = max(1, int(evidence.pop("direction_samples") or 0))
        evidence["away_dx"] = int(round(evidence["away_dx"] / samples))
        evidence["away_dy"] = int(round(evidence["away_dy"] / samples))
        evidence["counterpart_uuids"] = tuple(sorted(
            evidence["counterpart_uuids"]))
        evidence["drc_types"] = tuple(sorted(evidence["drc_types"]))
        via_targets.append(asdict(ViaRepairTarget(**evidence)))
    return {
        "schema": 1,
        "moved_refs": sorted(moved_refs),
        "root_causes": dict(sorted(causes.items())),
        "movable_copper_uuids": sorted(movable_copper),
        "movable_track_uuids": sorted(movable_tracks),
        "movable_via_uuids": sorted(movable_vias),
        "movable_via_targets": via_targets,
        "fixed_conflict_count": len(fixed),
        "fixed_conflicts": fixed,
        "violations": rows,
    }


def _evacuate_placement_copper_worker(
        board_path, track_uuids, generated_locked_uuids=()):
    """Rip up exact policy-movable tracks occupying a proposed component seat.

    This is the placement analogue of route negotiation.  Exact UUIDs come
    from KiCad DRC, every removed branch retains its original endpoints, and
    protected/authored copper remains immutable.  Vias are intentionally not
    handled here because their vertical connectivity requires a separate via
    relocation transaction rather than track-branch replay.
    """

    requested = tuple(sorted({str(uid) for uid in track_uuids if uid}))
    if not requested:
        return False, {"refusal": "no_movable_track_conflicts"}, []
    board = pcbnew.LoadBoard(board_path)
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    missing_or_via = []
    blocker_nets = []
    for uid in requested:
        item = _find_track(board, uid)
        if item is None or item.GetClass() != "PCB_TRACK":
            missing_or_via.append(uid)
            continue
        blocker_nets.append(str(item.GetNetname() or ""))
    if missing_or_via:
        return False, {
            "refusal": "placement_conflict_not_track_branch",
            "uuids": missing_or_via,
        }, []
    window = NegotiationWindow(
        net="__PLACEMENT_SEAT__", distance_mm=0.0, width_mm=0.0,
        clearance_mm=0.0, blocker_uuids=requested,
        blocker_nets=tuple(blocker_nets), blocker_hits=len(requested),
        omitted_movable_blockers=0, fixed_blocker_hits=0,
        trapped_endpoints=0, endpoints=(), priority=(),
        unlock_uuids=tuple(uid for uid in requested if uid in generated))
    changed, evidence, snapshots = _remove_negotiation_blockers(
        board, window, branch_hops=0)
    if not changed:
        return False, evidence, []
    pcbnew.SaveBoard(board_path, board)
    return True, {
        **evidence,
        "mode": "placement_generated_copper_evacuation",
        "requested_track_uuids": list(requested),
        "affected_nets": sorted(set(blocker_nets)),
    }, snapshots


def _spawn_apply(func, args, *, timeout_s=None):
    """Run one pcbnew operation in a bounded fresh interpreter.

    KiCad's Python proxies can become invalid after a board is saved/reloaded in
    the same process.  The production staged router already uses this boundary;
    certificate repair follows the same rule so long unattended waves do not
    accumulate stale SWIG state.  A raw ``multiprocessing.Pool`` context can
    wait forever during ``__exit__`` after the result has been delivered (the
    parent waits on a futex while the idle child waits on its task pipe).  Use
    the pipeline's finite coordinator and shutdown guard for this one-shot
    worker as well.
    """

    raw_timeout = (timeout_s if timeout_s is not None else
                   os.environ.get("CEC_CERTIFICATE_WORKER_TIMEOUT_S", "300"))
    try:
        wall_timeout_s = max(1.0, float(raw_timeout))
    except (TypeError, ValueError):
        wall_timeout_s = 300.0
    deadline = _WORKER_DEADLINE.get()
    if deadline is not None:
        remaining_s = float(deadline) - time.monotonic()
        if remaining_s <= 0.0:
            raise cec_process_pool.WorkerPoolStalled(
                "certificate repair wall budget exhausted before worker")
        # The transaction budget is an actual deadline, not merely a check
        # between candidates.  Cap every in-flight KiCad child to the time
        # remaining so one difficult maze cannot overrun an unattended wave.
        wall_timeout_s = max(0.05, min(wall_timeout_s, remaining_s))
    pool = ProcessPoolExecutor(
        max_workers=1, mp_context=mp.get_context("spawn"))
    forced_shutdown = False
    future = None
    try:
        future = pool.submit(func, *args)
        completed = cec_process_pool.watched_as_completed(
            pool, {future: None}, wall_timeout_s=wall_timeout_s,
            poll_s=min(1.0, wall_timeout_s))
        for done in completed:
            return done.result()
        raise cec_process_pool.WorkerPoolStalled(
            "certificate worker returned no completion")
    except BaseException:
        forced_shutdown = True
        if future is not None:
            future.cancel()
        raise
    finally:
        cec_process_pool.shutdown_process_pool(
            pool, force=forced_shutdown, grace_s=2.0)


def _spawn_dangling_cleanup(board_path, max_iterations=8, *, attempts=2):
    """Run idempotent DRC cleanup with one fresh-worker recovery attempt.

    KiCad's deprecated SWIG binding can occasionally return a raw
    ``SwigPyObject`` instead of its BOARD proxy in an otherwise healthy fresh
    process.  Exact UUID cleanup is restart-safe: every successful iteration is
    saved, and a new worker simply re-runs DRC on the remaining cascade.  Keep
    the retry finite and publish its error history for forensic reports.
    """

    errors = []
    limit = max(1, int(attempts))
    for attempt in range(limit):
        try:
            changed, evidence = _spawn_apply(
                _drc_dangling_cleanup_worker,
                (board_path, max_iterations))
            evidence = dict(evidence)
            evidence["worker_attempts"] = attempt + 1
            if errors:
                evidence["worker_retry_errors"] = errors
            return changed, evidence
        except Exception as exc:                         # noqa: BLE001
            errors.append({
                "attempt": attempt + 1,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:400]),
            })
    raise RuntimeError(
        "dangling cleanup failed after %d fresh workers: %s" %
        (limit, errors[-1]["error"]))


def _plan_worker(board_path, completion, drc_data, limit):
    return plan_repairs(board_path, completion, drc_data=drc_data, limit=limit)


def _sensitive_plan_worker(board_path, drc_data, limit):
    return plan_sensitive_drc_repairs(
        board_path, drc_data, limit=limit)


def _negotiation_plan_worker(board_path, completion, limit, max_blockers,
                             generated_locked_uuids=()):
    return plan_negotiations(
        board_path, completion, limit=limit,
        max_blockers_per_window=max_blockers,
        generated_locked_uuids=generated_locked_uuids)


def _footprint_plan_worker(board_path, completion, limit):
    return plan_footprint_repairs(board_path, completion, limit=limit)


def _endpoint_owner_plan_worker(board_path, completion, limit):
    return plan_endpoint_owner_repairs(board_path, completion, limit=limit)


def _congestion_via_plan_worker(board_path, completion,
                                generated_locked_uuids, limit):
    return plan_congestion_via_repairs(
        board_path, completion,
        generated_locked_uuids=generated_locked_uuids, limit=limit)


def _generated_locked_route_uuids(board_path: str,
                                  authored_baseline: str | None) -> tuple[str, ...]:
    """Return locked copper UUIDs absent from an explicit authored baseline.

    Provenance applies to both segments and vias.  Restricting this set to
    ``PCB_TRACK`` made a generated barrel look authored even when the placed
    baseline contained no route copper at all.
    """

    if not authored_baseline or not os.path.isfile(authored_baseline):
        return ()
    current = pcbnew.LoadBoard(board_path)
    baseline = pcbnew.LoadBoard(authored_baseline)
    authored = {_uuid(item) for item in baseline.GetTracks() if _uuid(item)}
    return tuple(sorted(
        _uuid(item) for item in current.GetTracks()
        if item.IsLocked() and _uuid(item) and _uuid(item) not in authored))


def _score_worker(board_path, drc_json):
    with open(drc_json, encoding="utf-8") as source:
        drc_data = json.load(source)
    row = _metric_row(
        cec_score.score(board_path, drc_json=drc_json), drc_data=drc_data)
    import cec_pour_clearance
    laid = dict((cec_pour_clearance.inspect_file(board_path).get("laid")
                 or {}))
    items = list(laid.get("items") or ())
    row["foreign_on_laid_pour"] = sum(
        int(laid.get(key) or 0)
        for key in ("n_parts", "n_tracks", "n_vias"))
    row["foreign_on_laid_pour_identities"] = sorted({
        json.dumps([
            str(item.get("kind") or "unknown"),
            str(item.get("uuid") or item.get("ref") or ""),
            str(item.get("net") or ""),
            str(item.get("pour_net") or item.get("pour") or ""),
            str(item.get("layer") or ""),
        ], separators=(",", ":"))
        for item in items
    })
    return row


def _open_coupled_pairs(pairs, unconnected_nets):
    """Return only pairs whose two members still require physical closure.

    Coupled copper is never eligible for the single-net surgery below.  The
    corresponding repair unit is the complete declared pair: both members are
    routed and admitted together, or the board remains byte-for-byte at its
    previous accepted state.
    """

    open_nets = {str(net) for net in unconnected_nets or () if net}
    return [dict(pair) for pair in pairs
            if {str(pair.get("p") or ""), str(pair.get("n") or "")}
            <= open_nets]


def _open_coupled_pairs_worker(board_path, unconnected_nets):
    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    return _open_coupled_pairs(
        cec_precision_route.derive_coupled_pairs(
            board_path, board=board),
        unconnected_nets)


def _partial_open_coupled_pairs(pairs, unconnected_nets):
    """Pairs with exactly one open member, requiring atomic pair replacement."""

    open_nets = {str(net) for net in unconnected_nets or () if net}
    rows = []
    for pair in pairs:
        members = {str(pair.get("p") or ""), str(pair.get("n") or "")}
        if len(members & open_nets) == 1:
            rows.append(dict(pair))
    return rows


def _partial_open_coupled_pairs_worker(board_path, unconnected_nets):
    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    return _partial_open_coupled_pairs(
        cec_precision_route.derive_coupled_pairs(
            board_path, board=board),
        unconnected_nets)


def _coupled_pairs_within_nets_worker(board_path, nets):
    """Return declared pairs wholly owned by a displaced-net transaction."""
    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    scope = {str(net) for net in nets if net}
    return [dict(pair) for pair in cec_precision_route.derive_coupled_pairs(
        board_path, board=board)
        if {str(pair.get("p") or ""), str(pair.get("n") or "")} <= scope]


def _swap_reversible_split_pair_station(
        board, pair, *, generated_locked_uuids=()):
    """Correct a reversed P/N order using interchangeable split support cells.

    This is placement repair, not logical net swapping.  It applies only to an
    adjacent split-member station made from two movable, ungrouped, identical
    two-pin footprints of the same value.  The swap must change mismatched
    endpoint lane polarity into a consistent ordering; otherwise the board is
    restored immediately.  Neighbor nets displaced by the move are returned
    for ordinary guarded closure inside the same outer transaction.
    """
    import cec_precision_route

    stations = cec_precision_route._pair_endpoint_stations(board, pair)
    if len(stations) != 2:
        return False, {"refusal": "pair_station_count_not_two",
                       "station_count": len(stations)}

    def plan(rows):
        return cec_precision_route._paired_portal_candidates(
            tuple(rows[0]["p_center"]), tuple(rows[0]["n_center"]),
            tuple(rows[1]["p_center"]), tuple(rows[1]["n_center"]),
            width=float(pair["width"]), gap=float(pair["gap"]))

    before_plan = plan(stations)
    preferred_before = dict(before_plan.get("preferred_signs") or {})
    if preferred_before.get("start") == preferred_before.get("end"):
        return False, {"refusal": "pair_lane_order_already_consistent",
                       "preferred_signs": preferred_before}
    groups = list(board.Groups())
    pair_nets = {str(pair["p"]), str(pair["n"])}
    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}
    candidates = []
    for station in stations:
        if station.get("kind") != "split-member-footprints":
            continue
        p_refs = {str(row.get("ref"))
                  for row in station.get("p_contacts") or ()}
        n_refs = {str(row.get("ref"))
                  for row in station.get("n_contacts") or ()}
        if len(p_refs) != 1 or len(n_refs) != 1 or p_refs == n_refs:
            continue
        p_ref, n_ref = next(iter(p_refs)), next(iter(n_refs))
        first = board.FindFootprintByReference(p_ref)
        second = board.FindFootprintByReference(n_ref)
        if first is None or second is None:
            continue
        first_pads, second_pads = list(first.Pads()), list(second.Pads())
        first_lib = str(first.GetFPID().GetLibItemName())
        second_lib = str(second.GetFPID().GetLibItemName())
        if (first.IsLocked() or second.IsLocked()
                or any(group.ContainsItem(first) or group.ContainsItem(second)
                       for group in groups)
                or len(first_pads) != 2 or len(second_pads) != 2
                or first_lib != second_lib
                or first.GetValue() != second.GetValue()
                or first.GetLayer() != second.GetLayer()):
            continue
        candidates.append((station, first, second))
    if not candidates:
        return False, {"refusal": "no_interchangeable_split_pair_support"}

    for station, first, second in candidates:
        first_state = (first.GetPosition(), first.GetOrientation())
        second_state = (second.GetPosition(), second.GetOrientation())
        pad_rows = [(footprint.GetReference(), str(pad.GetNumber()),
                     str(pad.GetNetname()), int(pad.GetNetCode()),
                     (int(pad.GetCenter().x), int(pad.GetCenter().y)))
                    for footprint in (first, second)
                    for pad in footprint.Pads()]
        displaced_nets = sorted({
            str(pad.GetNetname())
            for footprint in (first, second) for pad in footprint.Pads()
            if pad.GetNetname() and str(pad.GetNetname()) not in pair_nets})
        first.SetPosition(second_state[0])
        first.SetOrientation(second_state[1])
        second.SetPosition(first_state[0])
        second.SetOrientation(first_state[1])
        after_stations = cec_precision_route._pair_endpoint_stations(
            board, pair)
        after_plan = plan(after_stations) if len(after_stations) == 2 else {}
        preferred_after = dict(after_plan.get("preferred_signs") or {})
        if (preferred_after.get("start") is not None
                and preferred_after.get("start")
                == preferred_after.get("end")):
            # Prove the placement change first, then return to the old
            # geometry to snapshot the exact stable copper boundary.  Direct
            # pad-attached stubs move with neither the physical site nor the
            # logical component and would otherwise sit under the opposite
            # net after the swap.
            first.SetPosition(first_state[0])
            first.SetOrientation(first_state[1])
            second.SetPosition(second_state[0])
            second.SetOrientation(second_state[1])
            tracks_by_node = {}
            for item in board.GetTracks():
                if isinstance(item, pcbnew.PCB_VIA):
                    continue
                for point in (item.GetStart(), item.GetEnd()):
                    tracks_by_node.setdefault(
                        (int(item.GetNetCode()),
                         (int(point.x), int(point.y))), []).append(item)
            removed = {}
            anchors = []
            pad_vias = []
            for ref, pad_number, net_name, net_code, node in pad_rows:
                for item in tracks_by_node.get((net_code, node), ()):
                    uid = _uuid(item)
                    if (item.GetClass() != "PCB_TRACK" or not uid
                            or (item.IsLocked()
                                and uid not in generated_locked)):
                        return False, {
                            "refusal": "immutable_split_support_incident_copper",
                            "uuid": uid, "ref": ref, "pad": pad_number}
                    if uid in removed:
                        continue
                    a = (int(item.GetStart().x), int(item.GetStart().y))
                    b = (int(item.GetEnd().x), int(item.GetEnd().y))
                    far = b if a == node else a
                    removed[uid] = item
                    anchors.append({
                        "ref": ref, "pad": pad_number, "net": net_name,
                        "x_mm": round(far[0] / MM, 6),
                        "y_mm": round(far[1] / MM, 6),
                        "track_uuid": uid,
                    })
                for item in board.GetTracks():
                    if (not isinstance(item, pcbnew.PCB_VIA)
                            or int(item.GetNetCode()) != net_code
                            or (int(item.GetPosition().x),
                                int(item.GetPosition().y)) != node):
                        continue
                    uid = _uuid(item)
                    if item.IsLocked() and uid not in generated_locked:
                        return False, {
                            "refusal": "authored_locked_split_support_pad_via",
                            "uuid": uid, "ref": ref, "pad": pad_number}
                    pad_vias.append((ref, pad_number, item))
            first.SetPosition(second_state[0])
            first.SetOrientation(second_state[1])
            second.SetPosition(first_state[0])
            second.SetOrientation(first_state[1])
            footprints = {first.GetReference(): first,
                          second.GetReference(): second}
            new_centers = {
                (ref, str(pad.GetNumber())): pad.GetCenter()
                for ref, footprint in footprints.items()
                for pad in footprint.Pads()}
            for ref, pad_number, via in pad_vias:
                via.SetPosition(new_centers[(ref, pad_number)])
            for item in removed.values():
                board.Remove(item)
            board.BuildConnectivity()
            return True, {
                "station": station.get("id"),
                "refs": [first.GetReference(), second.GetReference()],
                "preferred_signs_before": preferred_before,
                "preferred_signs_after": preferred_after,
                "displaced_nets": displaced_nets,
                "removed_incident_tracks": len(removed),
                "preserved_anchors": anchors,
                "moved_pad_vias": sorted(
                    _uuid(via) for _ref, _pad, via in pad_vias if _uuid(via)),
            }
        first.SetPosition(first_state[0])
        first.SetOrientation(first_state[1])
        second.SetPosition(second_state[0])
        second.SetOrientation(second_state[1])
    board.BuildConnectivity()
    return False, {"refusal": "split_support_swap_did_not_align_pair"}


def _swap_reversible_split_pair_station_worker(
        board_path, pair_name, generated_locked_uuids=()):
    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    pairs = [row for row in cec_precision_route.derive_coupled_pairs(
        board_path, board=board) if str(row.get("name")) == str(pair_name)]
    if len(pairs) != 1:
        return False, {"refusal": "pair_identity_not_unique",
                       "matches": len(pairs)}
    changed, evidence = _swap_reversible_split_pair_station(
        board, pairs[0], generated_locked_uuids=generated_locked_uuids)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return changed, evidence


def _coupled_pair_closure_worker(board_path, pair_name, pair_grid=True,
                                 pair_timeout_s=None):
    """Route one named pair as a precision-router atomic transaction."""

    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    old_timeout = os.environ.get("CEC_PRECISION_PAIR_TIMEOUT")
    try:
        if pair_timeout_s is not None:
            os.environ["CEC_PRECISION_PAIR_TIMEOUT"] = str(
                max(5.0, float(pair_timeout_s)))
        report = cec_precision_route.precision_route_board(
            board, board_path=board_path, do_kelvin=False, do_pairs=True,
            include_pair_names={str(pair_name)}, pair_grid=bool(pair_grid),
            verbose=False)
    finally:
        if pair_timeout_s is not None:
            if old_timeout is None:
                os.environ.pop("CEC_PRECISION_PAIR_TIMEOUT", None)
            else:
                os.environ["CEC_PRECISION_PAIR_TIMEOUT"] = old_timeout
    routed = [row for row in report.get("pairs", {}).get("routed", ())
              if str(row.get("name")) == str(pair_name)]
    changed = bool(routed and report.get("pairs_ok")
                   and report.get("critical_routes_ok"))
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return changed, report


def _remove_partial_pair_copper_worker(board_path, pair_name,
                                       generated_locked_uuids=()):
    """Rip up only unlocked copper of one declared partially open pair."""

    import cec_precision_route

    board = pcbnew.LoadBoard(board_path)
    pairs = [pair for pair in cec_precision_route.derive_coupled_pairs(
        board_path, board=board) if str(pair.get("name")) == str(pair_name)]
    if len(pairs) != 1:
        return False, {"refusal": "pair_identity_not_unique",
                       "matches": len(pairs)}
    pair = pairs[0]
    members = {pair["p"], pair["n"]}
    groups = list(board.Groups())
    pair_copper = [item for item in board.GetTracks()
                   if item.GetNetname() in members]
    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}
    immutable = [
        {"uuid": _uuid(item), "net": item.GetNetname(),
         "locked": bool(item.IsLocked()),
         "grouped": any(group.ContainsItem(item) for group in groups)}
        for item in pair_copper
        if (item.IsLocked() and _uuid(item) not in generated_locked)
        or any(group.ContainsItem(item) for group in groups)
    ]
    if immutable:
        return False, {"refusal": "authored_or_grouped_pair_copper",
                       "immutable": immutable}
    removed = [{"uuid": _uuid(item), "net": item.GetNetname(),
                "kind": item.GetClass()} for item in pair_copper]
    for item in pair_copper:
        board.Remove(item)
    board.BuildConnectivity()
    pcbnew.SaveBoard(board_path, board)
    return True, {"removed": removed, "removed_count": len(removed),
                  "pair": pair,
                  "generated_locked_authority_count": len(generated_locked)}


def _coupled_pair_bundle_closure_worker(board_path, pair_names,
                                        pair_grid=True,
                                        pair_timeout_s=60.0):
    """Route a related set of declared pairs in one precision schedule."""

    import cec_precision_route

    names = {str(name) for name in pair_names if name}
    board = pcbnew.LoadBoard(board_path)
    old_timeout = os.environ.get("CEC_PRECISION_PAIR_TIMEOUT")
    try:
        os.environ["CEC_PRECISION_PAIR_TIMEOUT"] = str(
            max(5.0, float(pair_timeout_s)))
        report = cec_precision_route.precision_route_board(
            board, board_path=board_path, do_kelvin=False, do_pairs=True,
            include_pair_names=names, pair_grid=bool(pair_grid),
            verbose=False)
    finally:
        if old_timeout is None:
            os.environ.pop("CEC_PRECISION_PAIR_TIMEOUT", None)
        else:
            os.environ["CEC_PRECISION_PAIR_TIMEOUT"] = old_timeout
    routed_names = {str(row.get("name"))
                    for row in report.get("pairs", {}).get("routed", ())}
    changed = bool(names <= routed_names and report.get("pairs_ok")
                   and report.get("critical_routes_ok"))
    report["requested_pair_names"] = sorted(names)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return changed, report


def _mutate_worker(board_path, target_row, mode, margin):
    board = pcbnew.LoadBoard(board_path)
    target = RepairTarget(**target_row)
    operations, evidence = _candidate_ops(
        board, target, board_path=board_path, mode=mode,
        maze_margin_mm=margin)
    if operations:
        pcbnew.SaveBoard(board_path, board)
    return bool(operations), evidence


def _via_offset_candidates(target: ViaRepairTarget):
    """Deterministic canonical displacement ladder, conflict-away first.

    The candidate budget is normally much smaller than the Cartesian product
    of directions and radii.  Radius-major enumeration spent that whole budget
    rotating around 0.20 mm and rarely reached the distance actually required
    to clear a pad, mask expansion, or drill keepout.  Exhaust the bounded
    radius ladder along the measured conflict-away vector first, then rotate
    to alternate octants.  This gives every finite prefix useful radial
    diversity while retaining deterministic angular fallbacks.
    """

    ax, ay = _octant_away(target.away_dx, target.away_dy)
    directions = [
        (ax, ay),
        _octant_away(ax - ay, ax + ay),
        _octant_away(ax + ay, ay - ax),
        (-ay, ax),
        (ay, -ax),
        (-ax, -ay),
    ]
    unique = []
    for direction in directions:
        direction = _octant_away(*direction)
        if direction not in unique:
            unique.append(direction)
    for dx, dy in unique:
        for step_mm in (0.20, 0.30, 0.45, 0.60, 0.80, 1.00, 1.40):
            step_nm = int(round(step_mm * MM))
            yield dx * step_nm, dy * step_nm, step_mm, (dx, dy)


def _placement_via_offset_candidates(target: ViaRepairTarget,
                                     owner_directions=()):
    """Interleave owner access and collision escape for placement vias.

    The general via repair ladder is direction-major so a small attempt budget
    still reaches the displacement needed to clear a broad obstacle.  A via
    moved specifically to seat a component has a second constraint: when that
    barrel is the preserved boundary of one of the component's own nets,
    moving it far along the collision vector can strand the owning pad across
    an unrelated route fence.  Sample the same-net owner direction and the
    measured collision-away direction at four radially diverse distances
    before falling back to the ordinary deterministic ladder.
    """

    directions = []
    for raw in (*owner_directions,
                _octant_away(target.away_dx, target.away_dy)):
        direction = _octant_away(*raw)
        if direction not in directions:
            directions.append(direction)
    emitted = set()
    for step_mm in (0.20, 0.45, 0.80, 1.40):
        step_nm = int(round(step_mm * MM))
        for dx, dy in directions[:2]:
            key = dx * step_nm, dy * step_nm
            if key in emitted:
                continue
            emitted.add(key)
            yield key[0], key[1], step_mm, (dx, dy)
    for dx_nm, dy_nm, step_mm, direction in _via_offset_candidates(target):
        key = dx_nm, dy_nm
        if key in emitted:
            continue
        emitted.add(key)
        yield dx_nm, dy_nm, step_mm, direction


def _congestion_via_offset_candidates(target: ViaRepairTarget,
                                      owner_directions=()):
    """Interleave reachable radial and rectangular relocation candidates.

    A via can need the horizontal clearance of a larger diagonal move while a
    transverse inner-layer trunk limits its vertical displacement.  Via
    coordinates need not lie on a 45-degree ray; only the rebuilt copper legs
    do.  Sample two finite 0.80/0.45 mm rectangular blends after the first
    three owner-aware radii, then retain the ordinary fallback ladder.
    """

    base = list(_placement_via_offset_candidates(
        target, owner_directions=owner_directions))
    emitted = set()
    for row in base[:6]:
        key = int(row[0]), int(row[1])
        if key in emitted:
            continue
        emitted.add(key)
        yield row
    directions = []
    for raw in (*owner_directions,
                _octant_away(target.away_dx, target.away_dy)):
        direction = _octant_away(*raw)
        if direction not in directions:
            directions.append(direction)
    for dx, dy in directions:
        if dx == 0 or dy == 0:
            continue
        for x_step, y_step in ((0.80, 0.45), (0.45, 0.80)):
            key = (dx * int(round(x_step * MM)),
                   dy * int(round(y_step * MM)))
            if key in emitted:
                continue
            emitted.add(key)
            yield key[0], key[1], max(x_step, y_step), (dx, dy)
    for row in base[6:]:
        key = int(row[0]), int(row[1])
        if key in emitted:
            continue
        emitted.add(key)
        yield row


def _relocate_via_worker(board_path, target_row, dx_nm, dy_nm,
                         generated_locked_uuids=(),
                         allow_unattached_stitch=False):
    """Move one DRC-named via and canonically rebuild every incident stub."""

    board = pcbnew.LoadBoard(board_path)
    target = ViaRepairTarget(**target_row)
    route_items = {_uuid(item): item for item in board.GetTracks() if _uuid(item)}
    via = route_items.get(target.uuid)
    if via is None or via.GetClass() != "PCB_VIA":
        return False, {"refusal": "target_via_missing"}
    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}
    if via.IsLocked() and target.uuid not in generated_locked:
        return False, {"refusal": "target_via_became_locked"}
    old = via.GetPosition()
    if (old.x, old.y) != (target.x_nm, target.y_nm):
        return False, {"refusal": "target_via_moved_since_plan"}

    branches = []
    unsupported = []
    tolerance_nm = 5_000
    for item in list(board.GetTracks()):
        if item is via or item.GetNetCode() != via.GetNetCode():
            continue
        if item.GetClass() not in {"PCB_TRACK", "PCB_ARC"}:
            continue
        start, end = item.GetStart(), item.GetEnd()
        at_start = math.hypot(start.x - old.x, start.y - old.y) <= tolerance_nm
        at_end = math.hypot(end.x - old.x, end.y - old.y) <= tolerance_nm
        if not (at_start or at_end):
            continue
        uid = _uuid(item)
        if (item.GetClass() != "PCB_TRACK"
                or (item.IsLocked() and uid not in generated_locked)):
            unsupported.append(_uuid(item))
            continue
        other = end if at_start else start
        branches.append({
            "other": pcbnew.VECTOR2I(int(other.x), int(other.y)),
            "width": int(item.GetWidth()), "layer": int(item.GetLayer()),
            "locked": bool(item.IsLocked()), "uuid": _uuid(item),
            "endpoint_neckdown_group": any(
                group.ContainsItem(item)
                and group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP
                for group in board.Groups()),
        })
        board.Remove(item)
    if unsupported:
        return False, {"refusal": "locked_or_arc_incident_stub",
                       "incident_uuids": sorted(unsupported)}
    new = pcbnew.VECTOR2I(int(old.x + dx_nm), int(old.y + dy_nm))
    if not branches:
        if not allow_unattached_stitch:
            return False, {"refusal": "no_incident_route_stub"}
        # This mode is requested only by the refusal-certificate via planner,
        # which has already proved that the barrel is not pad-owned, not an
        # authored locked object, and not protected signal/power topology.
        # With no incident track, preserving a fictitious stub is impossible;
        # translate the stitching barrel and let zone refill, exact closure,
        # DRC, connectivity, and final admission prove the composite result.
        via.SetPosition(new)
        pcbnew.SaveBoard(board_path, board)
        return True, {
            "mode": "unattached_stitch_via",
            "old_mm": [round(old.x / MM, 6), round(old.y / MM, 6)],
            "new_mm": [round(new.x / MM, 6), round(new.y / MM, 6)],
            "incident_stubs": 0,
            "generated_track_uuids": [],
            "generated_locked_track_uuids": [],
            "generated_tracks": [],
        }
    via.SetPosition(new)
    board.BuildConnectivity()
    resolver = cec_fr._project_netclass_resolver(board_path)
    spec = dict(resolver(target.net) or {})
    clearance_nm = int(round(max(
        0.2, float(spec.get("clearance") or 0.0)) * MM))
    net_code = int(via.GetNetCode())
    generated = []
    generated_items = []
    for branch in branches:
        layer, width = branch["layer"], branch["width"]

        def edge_ok(a, b, half_width):
            return cec_fr._edge_leg_clear(board, a, b, half_width)

        legs = cec_fr._guarded_profiled_lastmile_legs(
            board, branch["other"], new, width, layer, clearance_nm,
            net_code, edge_ok, allow_maze=True, maze_margin_mm=2.0,
            foreign_cache={})
        if not legs:
            return False, {
                "refusal": "incident_stub_cannot_reach_candidate",
                "incident_uuid": branch["uuid"],
            }
        for start, end, leg_width in legs:
            if start == end:
                continue
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(start)
            track.SetEnd(end)
            track.SetWidth(int(leg_width))
            track.SetLayer(layer)
            track.SetNetCode(net_code)
            track.SetLocked(branch["locked"])
            board.Add(track)
            generated_items.append(track)
            generated.append({
                "layer": board.GetLayerName(layer),
                "width_mm": round(leg_width / MM, 6),
                "start": [round(start.x / MM, 6), round(start.y / MM, 6)],
                "end": [round(end.x / MM, 6), round(end.y / MM, 6)],
            })
        board.BuildConnectivity()
    if any(branch.get("endpoint_neckdown_group") for branch in branches):
        full_width = int(round(float(spec.get("track_width") or
                                   target.diameter_nm / MM) * MM))
        cec_fr.group_endpoint_neckdowns(board, generated_items, full_width)
    pcbnew.SaveBoard(board_path, board)
    return True, {
        "old_mm": [round(old.x / MM, 6), round(old.y / MM, 6)],
        "new_mm": [round(new.x / MM, 6), round(new.y / MM, 6)],
        "incident_stubs": len(branches),
        "generated_track_uuids": sorted(
            _uuid(item) for item in generated_items if _uuid(item)),
        "generated_locked_track_uuids": sorted(
            _uuid(item) for item in generated_items
            if _uuid(item) and item.IsLocked()),
        "generated_tracks": generated,
    }


def _remove_negotiation_worker(board_path, window_row, branch_hops):
    board = pcbnew.LoadBoard(board_path)
    window = NegotiationWindow(**window_row)
    changed, evidence, snapshots = _remove_negotiation_blockers(
        board, window, branch_hops=branch_hops)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return bool(changed), evidence, snapshots


def _close_negotiation_worker(board_path, window_row, attempt_budget, margin,
                              prefer_bridge=None, wall_timeout_s=None):
    board = pcbnew.LoadBoard(board_path)
    window = NegotiationWindow(**window_row)
    changed, evidence = _close_negotiation_target(
        board, window, board_path=board_path,
        attempt_budget=attempt_budget, maze_margin_mm=margin,
        prefer_bridge=prefer_bridge, wall_timeout_s=wall_timeout_s)
    if changed:
        completion = evidence.get("completion") or {}
        _save_with_reconciled_endpoint_neckdowns(
            board_path, board, completion)
    return bool(changed), evidence


def _restore_negotiation_worker(board_path, snapshots, margin,
                                max_detour_ratio,
                                order_mode="hardest_first",
                                wall_timeout_s=None):
    board = pcbnew.LoadBoard(board_path)
    changed, evidence = _restore_negotiation_blockers(
        board, snapshots, board_path=board_path,
        maze_margin_mm=margin, max_detour_ratio=max_detour_ratio,
        order_mode=order_mode, wall_timeout_s=wall_timeout_s)
    if changed:
        # A narrow pad escape may be restored before its downstream full-width
        # branch.  Qualifying/grouping that fragment immediately sees no throat
        # and rejects it; after the complete transaction is restored the same
        # copper is a valid bounded endpoint taper.  Reconcile once against the
        # finished topology and persist its exact object-scoped rule evidence.
        _save_with_reconciled_endpoint_neckdowns(
            board_path, board, evidence)
    return bool(changed), evidence


def _footprint_relocation_candidates(board_path, target_row):
    """Return a bounded route-aware seat ladder away from the trapped pad."""

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    fp = board.FindFootprintByReference(target.ref) if board is not None else None
    if fp is None:
        return []
    pos = fp.GetPosition()
    if target.motion == "toward_endpoint":
        vx = target.endpoint_x_mm - pos.x / MM
        vy = target.endpoint_y_mm - pos.y / MM
        norm = math.hypot(vx, vy)
        if norm <= 1e-9:
            ux = uy = 0.0
        else:
            ux, uy = vx / norm, vy / norm
        # Try the pin-swap at the legal current seat first, then walk toward
        # the owning endpoint in finite half-millimetre steps.  Paired 0/180
        # trials cover polarized pad numbering without assuming a refdes or a
        # footprint library convention.
        preferred = round(min(3.0, max(
            0.5, float(target.distance_mm) - 3.0)), 6)
        px, py = -uy, ux
        straight_dx, straight_dy = ux * preferred, uy * preferred
        lateral = min(0.75, max(0.5, preferred / 3.0))
        if target.companion_refs:
            # Preserve the relative geometry of an already coherent passive
            # divider/filter cell.  The relocation worker rotates every member
            # around the owner origin as one rigid body, so a 180-degree lane
            # reversal remains a valid cell operation rather than rotating
            # each support in place and scrambling the internal geometry.
            rows = []
            for fraction, side in (
                    (1.0, 0.0), (1.0, 1.0), (1.0, -1.0),
                    (0.75, 0.0), (0.75, 1.0), (0.75, -1.0),
                    (0.5, 0.0), (1.25, 0.0)):
                for rotation in (0.0, 180.0):
                    rows.append({
                        "rotation_delta_deg": rotation,
                        "dx_mm": round(
                            straight_dx * fraction + side * px * lateral, 6),
                        "dy_mm": round(
                            straight_dy * fraction + side * py * lateral, 6),
                    })
            return rows
        rows = [{"rotation_delta_deg": 180.0,
                 "dx_mm": 0.0, "dy_mm": 0.0}]
        for rotation in (0.0, 90.0, 180.0, -90.0):
            rows.append({
                "rotation_delta_deg": rotation,
                "dx_mm": round(straight_dx, 6),
                "dy_mm": round(straight_dy, 6),
            })
        for side in (1.0, -1.0):
            rows.append({
                "rotation_delta_deg": 0.0,
                "dx_mm": round(straight_dx + side * px * lateral, 6),
                "dy_mm": round(straight_dy + side * py * lateral, 6),
            })
        rows.append({
            "rotation_delta_deg": 0.0,
            "dx_mm": round(straight_dx * 0.5, 6),
            "dy_mm": round(straight_dy * 0.5, 6),
        })
        return rows
    dx = pos.x / MM - target.endpoint_x_mm
    dy = pos.y / MM - target.endpoint_y_mm
    sx = -1.0 if dx < 0.0 else 1.0
    sy = -1.0 if dy < 0.0 else 1.0
    # A quarter-turn changes which land faces the pin row; small translations
    # then clear the support courtyard and via field.  Keep one 180-degree
    # trial first for swapped-land cases whose body already has a legal seat.
    patterns = [
        (180.0, 0.0, 0.0),
        (180.0, 0.5, 0.5),
        (90.0, 0.0, 0.0),
        (90.0, 0.25, 0.25),
        (90.0, 0.5, 0.5),
        (90.0, 0.75, 0.75),
        (90.0, 0.5, 0.75),
        (90.0, 0.75, 0.5),
        (-90.0, 0.0, 0.0),
        (-90.0, 0.5, 0.5),
        (0.0, 0.5, 0.75),
        (0.0, 0.75, 0.5),
    ]
    return [{"rotation_delta_deg": rotation,
             "dx_mm": round(sx * x, 6),
             "dy_mm": round(sy * y, 6)}
            for rotation, x, y in patterns]


def _rotate_board_vector(x, y, degrees):
    """Rotate a board-space vector using KiCad's clockwise-positive angle.

    KiCad board coordinates grow downward on Y, so increasing a footprint's
    orientation maps +X toward -Y.  Using the conventional Cartesian matrix
    here made predicted pads/boxes rotate opposite to the saved footprint and
    could rank a support whose target land actually faced behind its sibling.
    """

    radians = math.radians(float(degrees))
    cosine, sine = math.cos(radians), math.sin(radians)
    return cosine * x + sine * y, -sine * x + cosine * y


def _occupancy_relocation_candidates(board_path, target_row, *, limit=32):
    """Generate component seats from live geometry instead of fixed offsets.

    The refusal certificate supplies the electrical objective (the endpoint
    that must become reachable).  The current board supplies the placement
    objective: actual footprint extents, board outline, and copper occupancy.
    Candidate pads are seated on a finite ring around the peer endpoint and
    the whole support cluster is transformed as a rigid body.  The returned
    order is deterministic and prefers board-contained, courtyard-clear,
    low-copper seats before route distance or movement magnitude.

    This is deliberately a cheap proposal stage.  Exact KiCad DRC and the
    transactional reconnect/admission gate remain authoritative.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    owner = (board.FindFootprintByReference(target.ref)
             if board is not None else None)
    if owner is None:
        return []
    members = [owner]
    for ref in target.companion_refs:
        companion = board.FindFootprintByReference(str(ref))
        if companion is None:
            return []
        members.append(companion)
    member_refs = {member.GetReference() for member in members}
    owner_origin = owner.GetPosition()

    def rect_from_box(box):
        return (float(box.GetLeft()) / MM, float(box.GetTop()) / MM,
                float(box.GetRight()) / MM, float(box.GetBottom()) / MM)

    def transform_point(x_mm, y_mm, dx_mm, dy_mm, rotation_deg):
        ox, oy = owner_origin.x / MM, owner_origin.y / MM
        rx, ry = x_mm - ox, y_mm - oy
        tx, ty = _rotate_board_vector(rx, ry, rotation_deg)
        return ox + dx_mm + tx, oy + dy_mm + ty

    def transformed_rect(rect, candidate):
        left, top, right, bottom = rect
        points = [transform_point(
            x, y, float(candidate["dx_mm"]), float(candidate["dy_mm"]),
            float(candidate["rotation_delta_deg"]))
                  for x, y in ((left, top), (right, top),
                               (right, bottom), (left, bottom))]
        xs, ys = zip(*points)
        return min(xs), min(ys), max(xs), max(ys)

    def inflated(rect, amount):
        return (rect[0] - amount, rect[1] - amount,
                rect[2] + amount, rect[3] + amount)

    def overlap_area(first, second):
        width = min(first[2], second[2]) - max(first[0], second[0])
        height = min(first[3], second[3]) - max(first[1], second[1])
        return max(0.0, width) * max(0.0, height)

    member_rects = {
        member.GetReference(): rect_from_box(
            member.GetBoundingBox(False, False))
        for member in members}
    stationary_rects = [
        (footprint.GetReference(), inflated(rect_from_box(
            footprint.GetBoundingBox(False, False)), 0.15))
        for footprint in board.GetFootprints()
        if footprint.GetReference() not in member_refs]
    edge = board.GetBoardEdgesBoundingBox()
    board_rect = inflated(rect_from_box(edge), -0.25)

    target_code = board.GetNetcodeFromNetname(target.target_net)
    target_pads = [pad for pad in owner.Pads()
                   if pad.IsOnCopperLayer()
                   and pad.GetNetCode() == target_code]
    if not target_pads:
        return []
    endpoint = (float(target.endpoint_x_mm), float(target.endpoint_y_mm))
    target_pad = min(target_pads, key=lambda pad: math.hypot(
        pad.GetCenter().x / MM - endpoint[0],
        pad.GetCenter().y / MM - endpoint[1]))
    pad_position = target_pad.GetCenter()
    pad_x, pad_y = pad_position.x / MM, pad_position.y / MM

    # Copper attached directly to the moving cell is either removed or moved
    # by the relocation transaction and therefore is not stationary
    # occupancy.  Every other item remains a real congestion cost.
    pad_nodes = {
        (pad.GetNetCode(), int(pad.GetCenter().x), int(pad.GetCenter().y))
        for member in members for pad in member.Pads()
        if pad.IsOnCopperLayer()}
    member_surface_layers = {
        layer for member in members for pad in member.Pads()
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu)
        if pad.IsOnLayer(layer)}
    incident_uuids = set()
    for item in board.GetTracks():
        uid = _uuid(item)
        if not uid:
            continue
        if item.GetClass() == "PCB_VIA":
            node = (item.GetNetCode(), int(item.GetPosition().x),
                    int(item.GetPosition().y))
            if node in pad_nodes:
                incident_uuids.add(uid)
            continue
        if any((item.GetNetCode(), int(point.x), int(point.y)) in pad_nodes
               for point in (item.GetStart(), item.GetEnd())):
            incident_uuids.add(uid)
    copper_rects = [
        (_uuid(item), bool(item.IsLocked()),
         inflated(rect_from_box(item.GetBoundingBox()), 0.10))
        for item in board.GetTracks()
        if (_uuid(item) and _uuid(item) not in incident_uuids
            and (item.GetClass() == "PCB_VIA"
                 or item.GetLayer() in member_surface_layers))]

    vector_x, vector_y = endpoint[0] - pad_x, endpoint[1] - pad_y
    norm = math.hypot(vector_x, vector_y)
    if norm <= 1e-9:
        unit_x, unit_y = 1.0, 0.0
    else:
        unit_x, unit_y = vector_x / norm, vector_y / norm
    perp_x, perp_y = -unit_y, unit_x
    rotations = ((0.0, 180.0) if target.companion_refs else
                 (0.0, 90.0, 180.0, -90.0))
    raw = []
    if target.motion == "toward_endpoint":
        for rotation in rotations:
            rotated_pad_x, rotated_pad_y = transform_point(
                pad_x, pad_y, 0.0, 0.0, rotation)
            for seat_gap in (0.50, 0.75, 1.00, 1.25, 1.50, 2.00,
                             2.50, 3.00, 3.50):
                for lateral in (0.0, 0.5, -0.5, 1.0, -1.0,
                                1.5, -1.5, 2.0, -2.0, 2.5, -2.5,
                                3.0, -3.0):
                    desired_x = (endpoint[0] - unit_x * seat_gap
                                 + perp_x * lateral)
                    desired_y = (endpoint[1] - unit_y * seat_gap
                                 + perp_y * lateral)
                    raw.append({
                        "rotation_delta_deg": rotation,
                        "dx_mm": round(desired_x - rotated_pad_x, 6),
                        "dy_mm": round(desired_y - rotated_pad_y, 6),
                        "generator": "occupancy_endpoint_ring",
                        "seat_gap_mm": seat_gap,
                        "lateral_mm": lateral,
                    })
    else:
        # A foreign support blocking a trapped land has no destination pad.
        # Explore a finite polar neighborhood away from the certified
        # endpoint while the same occupancy score chooses an actual free seat.
        away_x, away_y = -unit_x, -unit_y
        for rotation in rotations:
            for radius in (0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0):
                for lateral in (0.0, 0.5, -0.5, 1.0, -1.0):
                    raw.append({
                        "rotation_delta_deg": rotation,
                        "dx_mm": round(away_x * radius
                                       + perp_x * lateral, 6),
                        "dy_mm": round(away_y * radius
                                       + perp_y * lateral, 6),
                        "generator": "occupancy_away_field",
                        "seat_gap_mm": radius,
                        "lateral_mm": lateral,
                    })

    scored, seen = [], set()
    for candidate in raw:
        key = _footprint_candidate_key(target.ref, candidate)[1:]
        if key in seen:
            continue
        seen.add(key)
        transformed = [transformed_rect(
            member_rects[member.GetReference()], candidate)
                       for member in members]
        outside_mm2 = sum(
            max(0.0, board_rect[0] - rect[0]) * max(0.0, rect[3] - rect[1])
            + max(0.0, rect[2] - board_rect[2]) * max(0.0, rect[3] - rect[1])
            + max(0.0, board_rect[1] - rect[1]) * max(0.0, rect[2] - rect[0])
            + max(0.0, rect[3] - board_rect[3]) * max(0.0, rect[2] - rect[0])
            for rect in transformed)
        footprint_areas = [
            overlap_area(rect, stationary)
            for rect in transformed
            for _ref, stationary in stationary_rects]
        footprint_overlap_refs = sorted({
            ref for rect in transformed for ref, stationary in stationary_rects
            if overlap_area(rect, stationary) > 1e-9})
        footprint_overlap_count = sum(area > 1e-9
                                      for area in footprint_areas)
        footprint_overlap_mm2 = sum(footprint_areas)
        copper_hit_uuids = sorted({
            uid for rect in transformed for uid, _locked, copper in copper_rects
            if overlap_area(rect, copper) > 1e-9})
        locked_copper_hit_uuids = sorted({
            uid for rect in transformed
            for uid, locked, copper in copper_rects
            if locked and overlap_area(rect, copper) > 1e-9})
        copper_hits = len(copper_hit_uuids)
        locked_copper_hits = len(locked_copper_hit_uuids)
        moved_pad_x, moved_pad_y = transform_point(
            pad_x, pad_y, float(candidate["dx_mm"]),
            float(candidate["dy_mm"]),
            float(candidate["rotation_delta_deg"]))
        endpoint_distance = math.hypot(
            moved_pad_x - endpoint[0], moved_pad_y - endpoint[1])
        movement = math.hypot(float(candidate["dx_mm"]),
                              float(candidate["dy_mm"]))
        score = (round(outside_mm2, 6), footprint_overlap_count,
                 round(footprint_overlap_mm2, 6), locked_copper_hits,
                 copper_hits,
                 round(endpoint_distance, 6), round(movement, 6),
                 abs(float(candidate["rotation_delta_deg"])), key)
        candidate["occupancy_score"] = {
            "outside_mm2": round(outside_mm2, 6),
            "footprint_overlap_count": footprint_overlap_count,
            "footprint_overlap_mm2": round(footprint_overlap_mm2, 6),
            "footprint_overlap_refs": footprint_overlap_refs,
            "copper_hits": copper_hits,
            "copper_hit_uuids": copper_hit_uuids[:32],
            "locked_copper_hits": locked_copper_hits,
            "locked_copper_hit_uuids": locked_copper_hit_uuids[:32],
            "endpoint_distance_mm": round(endpoint_distance, 6),
            "movement_mm": round(movement, 6),
        }
        scored.append((score, candidate))
    scored.sort(key=lambda row: row[0])
    return [candidate for _score, candidate in
            scored[:max(0, int(limit))]]


def _combined_footprint_relocation_candidates(board_path, target_row):
    """Prefer measured seats and bounded soft-obstacle cell expansion.

    If the target's best occupancy-derived seats repeatedly intersect small,
    unlocked two-pin supports, those parts form a local mobility graph.  Try
    the target with one or two of the highest-pressure supports as a rigid
    cell.  This is a generic detailed-placement operation: connectors,
    multi-pin owners, grouped/mechanical references, THT parts, and locked
    footprints never enter the graph.
    """

    board = pcbnew.LoadBoard(board_path)
    if board is None:
        return _footprint_relocation_candidates(board_path, target_row)
    target = FootprintRepairTarget(**target_row)
    base_rows = _occupancy_relocation_candidates(
        board_path, target_row, limit=64)
    # A routed endpoint may already own a narrow egress through a dense pin
    # field.  Generate seats around a few exact nodes on that live component,
    # not only around the inaccessible pad centre.  The metadata follows the
    # pose so exact reconnection uses the same certified access point; ordinary
    # occupancy, DRC, and whole-board admission still rank and prove the move.
    access_certificate = {"endpoints": [
        {"kind": ("pad" if target.endpoint_ref and target.endpoint_pad
                  else "node"),
         "ref": target.endpoint_ref, "pad": target.endpoint_pad,
         "x_mm": target.endpoint_x_mm, "y_mm": target.endpoint_y_mm},
    ]}
    access_plan = _target_endpoint_access_candidates_worker(
        board_path, target_row, access_certificate,
        max_hops=8, max_length_mm=8.0, limit=4)
    access_rows = []
    for access in access_plan.get("candidates") or ():
        endpoint = dict(access.get("endpoint") or {})
        access_target = dict(target_row)
        access_target["endpoint_x_mm"] = float(endpoint["x_mm"])
        access_target["endpoint_y_mm"] = float(endpoint["y_mm"])
        for row in _occupancy_relocation_candidates(
                board_path, access_target, limit=16):
            row = dict(row)
            row["generator"] = "occupancy_connected_endpoint"
            row["route_access_endpoint"] = endpoint
            row["route_access_path_uuids"] = list(
                access.get("access_path_uuids") or ())
            row["route_access_hops"] = int(access.get("hops") or 0)
            access_rows.append(row)
    owner = board.FindFootprintByReference(target.ref)
    owner_position = owner.GetPosition() if owner is not None else None
    existing = {str(ref) for ref in target.companion_refs}
    excluded = {target.ref, target.endpoint_ref, *existing}
    grouped = {
        footprint.GetReference()
        for group in board.Groups() for footprint in board.GetFootprints()
        if group.ContainsItem(footprint)}
    pressure = {}
    for row in base_rows:
        score = row.get("occupancy_score") or {}
        overlap_area = float(score.get("footprint_overlap_mm2") or 0.0)
        for ref in score.get("footprint_overlap_refs") or ():
            pressure.setdefault(str(ref), [0, 0.0])
            pressure[str(ref)][0] += 1
            pressure[str(ref)][1] += overlap_area

    eligible = []
    for ref, (hits, area) in pressure.items():
        footprint = board.FindFootprintByReference(ref)
        pads = (list(footprint.Pads()) if footprint is not None else [])
        copper_pads = [pad for pad in pads if pad.IsOnCopperLayer()]
        distance = (math.hypot(
            footprint.GetPosition().x - owner_position.x,
            footprint.GetPosition().y - owner_position.y) / MM
                    if footprint is not None and owner_position is not None
                    else 1e9)
        if (not ref or ref in excluded or ref in grouped
                or footprint is None or footprint.IsLocked()
                or ref.upper().startswith(("J", "H", "FID", "LOGO", "MK"))
                or len(copper_pads) != 2
                or any(pad.HasHole() for pad in copper_pads)
                or distance > 6.0 + 1e-9):
            continue
        eligible.append((-hits, -area, distance, ref))
    eligible.sort()
    soft_refs = [row[3] for row in eligible[:3]]

    expanded_rows = []
    available_members = max(0, 4 - len(existing))
    subsets = ([(ref,) for ref in soft_refs]
               if available_members >= 1 else [])
    if available_members >= 2:
        subsets.extend(itertools.combinations(soft_refs, 2))
    for subset in subsets[:6]:
        expanded_target = dict(target_row)
        cluster = tuple(sorted(existing | set(subset)))
        expanded_target["companion_refs"] = list(cluster)
        for row in _occupancy_relocation_candidates(
                board_path, expanded_target, limit=12):
            row = dict(row)
            row["mobility_companion_refs"] = list(cluster)
            row["generator"] = "occupancy_mobility_graph"
            expanded_rows.append(row)

    def measured_key(row):
        score = row.get("occupancy_score") or {}
        return (
            float(score.get("outside_mm2") or 0.0),
            int(score.get("footprint_overlap_count") or 0),
            float(score.get("footprint_overlap_mm2") or 0.0),
            int(score.get("locked_copper_hits") or 0),
            int(score.get("copper_hits") or 0),
            float(score.get("endpoint_distance_mm") or 1e9),
            len(row.get("mobility_companion_refs") or ()),
            _footprint_candidate_key(target.ref, row),
        )

    measured = access_rows + base_rows + expanded_rows
    measured.sort(key=measured_key)
    rows = measured + _footprint_relocation_candidates(
        board_path, target_row)
    unique, seen = [], set()
    ref = target_row.get("ref")
    for row in rows:
        key = _footprint_candidate_key(ref, row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _relocate_footprint_worker(board_path, target_row, candidate,
                               max_branch_tracks=12, max_copper_pads=2,
                               generated_locked_uuids=()):
    """Move one certified support cell/cluster and its pad-attached stubs.

    A component re-seat changes the location of its pads, not the topology of
    every net that happens to leave them.  Walking degree-two copper until a
    foreign pad is reached turns a local pin-access repair into a whole-net
    rip-up (and needlessly makes unrelated fanout a routing dependency).  The
    stable boundary for this transaction is therefore the far endpoint of each
    item directly attached to an old pad centre.  The ordinary completion
    engine reconnects the moved pad to those preserved anchors, and the final
    full-board score still rejects any clearance or connectivity regression.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    fp = board.FindFootprintByReference(target.ref) if board is not None else None
    if fp is None or fp.IsLocked():
        return False, {"refusal": "missing_or_locked_footprint"}
    footprints = [fp]
    for ref in target.companion_refs:
        companion = board.FindFootprintByReference(str(ref))
        if companion is None or companion.IsLocked():
            return False, {"refusal": "missing_or_locked_companion",
                           "ref": str(ref)}
        footprints.append(companion)
    copper_by_ref = {}
    for member in footprints:
        member_pads = [pad for pad in member.Pads()
                       if pad.IsOnCopperLayer()]
        if (not member_pads
                or len(member_pads) > max(2, int(max_copper_pads))
                or any(pad.HasHole() for pad in member_pads)):
            return False, {"refusal": "footprint_outside_relocation_scope",
                           "ref": member.GetReference()}
        copper_by_ref[member.GetReference()] = member_pads
    copper_pads = [pad for pads in copper_by_ref.values() for pad in pads]

    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}

    def point_key(point):
        return int(point.x), int(point.y)

    pad_rows = [
        (ref, str(pad.GetNumber()), pad.GetNetname(), pad.GetNetCode(),
         point_key(pad.GetCenter()))
        for ref, pads in copper_by_ref.items() for pad in pads]
    all_copper = list(board.GetTracks())
    pad_vias = {}
    for item in all_copper:
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        for ref, pad_number, _net_name, net_code, node in pad_rows:
            if item.GetNetCode() == net_code and point_key(
                    item.GetPosition()) == node:
                pad_vias[(ref, pad_number)] = item
    # A locked authored via at an SMD pad is an immutable route boundary, not
    # an immutable component pose.  Earlier versions refused the entire
    # re-seat because the via could not follow the pad.  Preserve such a via
    # at its authored coordinate and reconnect the moved pad to it inside the
    # same transaction; only unlocked or explicitly generated pad vias may
    # move with the footprint.  Whole-board DRC/connectivity admission still
    # rejects any illegal reconstruction.
    anchored_pad_vias = {
        identity: via for identity, via in pad_vias.items()
        if via.IsLocked() and _uuid(via) not in generated_locked
    }

    tracks_by_node = {}
    for item in all_copper:
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        net_code = item.GetNetCode()
        for point in (item.GetStart(), item.GetEnd()):
            tracks_by_node.setdefault(
                (net_code, point_key(point)), []).append(item)

    cluster_pad_nodes = {
        (net_code, node)
        for _ref, _pad, _name, net_code, node in pad_rows}
    internal_tracks = {}
    for item in all_copper:
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        net_code = item.GetNetCode()
        a = (net_code, point_key(item.GetStart()))
        b = (net_code, point_key(item.GetEnd()))
        if a not in cluster_pad_nodes or b not in cluster_pad_nodes:
            continue
        uid = _uuid(item)
        if not uid:
            continue
        if item.IsLocked() and uid not in generated_locked:
            return False, {
                "refusal": "authored_locked_internal_cluster_track",
                "track_uuid": uid,
            }
        internal_tracks[uid] = item

    removed = {}
    pad_row_by_identity = {
        (ref, pad_number): (net_name, net_code, node)
        for ref, pad_number, net_name, net_code, node in pad_rows
    }
    anchors = []
    anchor_keys = set()

    def preserve_anchor(row):
        key = (
            str(row.get("ref") or ""), str(row.get("pad") or ""),
            str(row.get("net") or ""),
            round(float(row.get("x_mm") or 0.0), 6),
            round(float(row.get("y_mm") or 0.0), 6),
        )
        if key not in anchor_keys:
            anchor_keys.add(key)
            anchors.append(row)

    for (ref, pad_number), via in anchored_pad_vias.items():
        net_name, _net_code, node = pad_row_by_identity[(ref, pad_number)]
        preserve_anchor({
            "ref": ref,
            "pad": pad_number,
            "net": net_name,
            "x_mm": round(node[0] / MM, 6),
            "y_mm": round(node[1] / MM, 6),
            "track_uuid": _uuid(via),
            "kind": "authored_locked_pad_via",
        })
    for ref, pad_number, net_name, net_code, start in pad_rows:
        for item in tracks_by_node.get((net_code, start), ()):
            uid = _uuid(item)
            if not uid or uid in removed or uid in internal_tracks:
                continue
            if item.IsLocked() and uid not in generated_locked:
                # Like a locked pad via, authored incident copper is a fixed
                # route boundary.  Keep the trace untouched and reconnect the
                # moved pad to its old contact point.  This preserves manual
                # copper exactly while allowing a transactional component
                # re-seat to repair pin access.
                preserve_anchor({
                    "ref": ref,
                    "pad": pad_number,
                    "net": net_name,
                    "x_mm": round(start[0] / MM, 6),
                    "y_mm": round(start[1] / MM, 6),
                    "track_uuid": uid,
                    "kind": "authored_locked_incident_branch",
                })
                continue
            removed[uid] = item
            if len(removed) > max(1, int(max_branch_tracks)):
                return False, {"refusal": "incident_branch_too_broad",
                               "track_count": len(removed)}
            a, b = point_key(item.GetStart()), point_key(item.GetEnd())
            far = b if a == start else a
            preserve_anchor({
                "ref": ref,
                "pad": pad_number,
                "net": net_name,
                "x_mm": round(far[0] / MM, 6),
                "y_mm": round(far[1] / MM, 6),
                "track_uuid": uid,
                "kind": "removed_incident_branch_far_endpoint",
            })

    old_poses = {
        member.GetReference(): {
            "position": member.GetPosition(),
            "rotation": member.GetOrientationDegrees(),
        } for member in footprints}
    delta = pcbnew.VECTOR2I_MM(
        float(candidate["dx_mm"]), float(candidate["dy_mm"]))
    rotation_delta = float(candidate["rotation_delta_deg"])
    owner_origin = old_poses[target.ref]["position"]
    destination_origin = owner_origin + delta
    def transform(point):
        dx = point.x - owner_origin.x
        dy = point.y - owner_origin.y
        tx, ty = _rotate_board_vector(dx, dy, rotation_delta)
        return pcbnew.VECTOR2I(
            int(round(destination_origin.x + tx)),
            int(round(destination_origin.y + ty)))

    for member in footprints:
        pose = old_poses[member.GetReference()]
        member.SetPosition(transform(pose["position"]))
        member.SetOrientationDegrees(pose["rotation"] + rotation_delta)
    for item in internal_tracks.values():
        item.SetStart(transform(item.GetStart()))
        item.SetEnd(transform(item.GetEnd()))
    new_pad_centers = {
        (member.GetReference(), str(pad.GetNumber())): pad.GetCenter()
        for member in footprints for pad in member.Pads()}
    moved_vias = []
    for identity, via in pad_vias.items():
        if identity in anchored_pad_vias:
            continue
        via.SetPosition(new_pad_centers[identity])
        moved_vias.append(_uuid(via))
    for item in removed.values():
        board.Remove(item)
    board.BuildConnectivity()
    pcbnew.SaveBoard(board_path, board)
    old_position = old_poses[target.ref]["position"]
    old_rotation = old_poses[target.ref]["rotation"]
    return True, {
        "ref": target.ref,
        "companion_refs": list(target.companion_refs),
        "old_position_mm": [round(old_position.x / MM, 6),
                            round(old_position.y / MM, 6)],
        "new_position_mm": [round(fp.GetPosition().x / MM, 6),
                            round(fp.GetPosition().y / MM, 6)],
        "old_rotation_deg": float(old_rotation),
        "new_rotation_deg": float(fp.GetOrientationDegrees()),
        "moved_internal_tracks": len(internal_tracks),
        "moved_internal_track_uuids": sorted(internal_tracks),
        "removed_tracks": len(removed),
        "preserved_anchors": anchors,
        "preserved_locked_pad_via_uuids": sorted(
            _uuid(via) for via in anchored_pad_vias.values() if _uuid(via)),
        "moved_pad_via_uuids": sorted(uid for uid in moved_vias if uid),
        "affected_nets": sorted({name for _ref, _pad, name, _code, _node in pad_rows
                                 if name}),
    }


def _prune_relocated_dangling_vias_worker(board_path, eligible_uuids,
                                           drc_data):
    """Remove only moved pad vias named by KiCad as newly dangling."""

    eligible = {str(uid) for uid in eligible_uuids if uid}
    named = {
        str(item.get("uuid"))
        for violation in (drc_data or {}).get("violations") or ()
        if violation.get("type") == "via_dangling"
        for item in violation.get("items") or ()
        if item.get("uuid")
    }
    remove = eligible & named
    if not remove:
        return False, {"removed": [], "reason": "no_eligible_dangling_via"}
    board = pcbnew.LoadBoard(board_path)
    removed = []
    for item in list(board.GetTracks()):
        uid = _uuid(item)
        if isinstance(item, pcbnew.PCB_VIA) and uid in remove:
            board.Remove(item)
            removed.append(uid)
    board.BuildConnectivity()
    pcbnew.SaveBoard(board_path, board)
    return bool(removed), {"removed": sorted(removed)}


def _refill_worker(board_path):
    cec_fr.refill_zones(board_path)
    return True


def _save_with_reconciled_endpoint_neckdowns(board_path, board, report):
    """Persist generated copper with an exact object-scoped width contract.

    A composite negotiation can retain older guarded neckdowns while adding a
    narrower, pad-limited taper.  Updating the PCB_GROUP without re-deriving
    the sidecar rule leaves the new geometry governed by the historical group
    minimum and makes a valid whole-board completion fail its own DRC.  Always
    rebuild membership evidence from the final in-memory board, then write the
    rule from the minimum width of the exact group that will be saved.
    """

    # Every through-via or track added after the prior fill changes the legal
    # shape of every intersected zone.  Saving the stale fill makes KiCad DRC
    # report zero-clearance copper where the next refill would correctly void
    # the plane, and can also leave a plane pickup electrically open.  Refill
    # the exact candidate before deriving groups or publishing it; a failure
    # is fatal to the speculative worker so the unchanged parent remains the
    # transaction authority.
    zones = list(board.Zones())
    if zones:
        for zone in zones:
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
    report["zone_refill"] = {
        "performed": bool(zones),
        "zone_count": len(zones),
    }

    resolver = cec_fr._project_netclass_resolver(board_path)
    reconciliation = cec_fr.reconcile_endpoint_neckdown_groups(
        board, netclass_resolver=resolver)
    report["endpoint_neckdown_reconciliation"] = reconciliation
    if (reconciliation.get("applicable")
            and reconciliation.get("tracks")
            and reconciliation.get("min_width_mm") is not None):
        report["endpoint_neckdown"] = {
            "group": reconciliation["group"],
            "tracks": int(reconciliation["tracks"]),
            "min_width_mm": float(reconciliation["min_width_mm"]),
        }
    # A composite transaction may emit POFV barrels in more than one phase
    # (target closure plus displaced-branch restoration).  Phase-local reports
    # name only their own vias, so writing rule authority from the outer report
    # can omit the restored set and turn a geometrically valid improvement into
    # via-diameter/drill DRC debt.  Re-derive the exact eligible group from the
    # finished board just as the standalone transactional finisher does.
    pofv = cec_fr.group_local_pofv_signal_vias(
        board, list(board.GetTracks()))
    if pofv:
        report["local_pofv_signal_vias"] = pofv
    pcbnew.SaveBoard(board_path, board)
    report["endpoint_neckdown_rule"] = \
        cec_fr.ensure_endpoint_neckdown_rule(board_path, report)
    report["local_pofv_signal_via_rule"] = \
        cec_fr.ensure_local_pofv_signal_via_rule(board_path, report)
    return report


def _lastmile_worker(board_path, target_nets, attempt_budget, margin,
                     prefer_bridge=False, wall_timeout_s=None):
    board = pcbnew.LoadBoard(board_path)
    resolver = cec_fr._project_netclass_resolver(board_path)
    nets = tuple(target_nets)
    # Divide the caller's complete allowance fairly across the requested
    # nets.  Do not cap a one-net worker at 35 s: placement repair commonly
    # exposes a second, longer island pair after its exact local certificate
    # closes, and the old cap silently discarded most of the caller's budget.
    per_net_timeout_s = (None if wall_timeout_s is None else max(
        5.0, float(wall_timeout_s) / max(1, len(nets))))
    if prefer_bridge:
        # A completion set is not a single search problem: one dense net must
        # not monopolize the worker and starve the others.  Give every net its
        # own canonical breadth slice, persist all monotonic closures in the
        # same in-memory board, then spend remaining time only on unresolved
        # nets.  The caller still owns whole-board DRC/admission.
        effective_wall_s = (75.0 if wall_timeout_s is None else
                            max(1.0, float(wall_timeout_s)))
        started = time.monotonic()
        stage_rows = []
        per_net_breadth_s = max(
            4.0, min(30.0, effective_wall_s * 0.65 / max(1, len(nets))))
        unresolved = []
        for net in nets:
            remaining = effective_wall_s - (time.monotonic() - started)
            if remaining <= 0.0:
                unresolved.append(net)
                continue
            allowance = min(per_net_breadth_s, remaining)
            stage = cec_fr.synthesize_lastmile(
                board, max_mm=80.0, min_w=0.2, clearance=0.0, cap=64,
                netclass_resolver=resolver, include_nets={net},
                attempts_per_pair=8, maze_max_mm=0.0,
                maze_margin_mm=2.0, bridge_fast=True,
                wall_timeout_s=allowance, per_net_timeout_s=allowance)
            board.BuildConnectivity()
            net_code = board.GetNetcodeFromNetname(net)
            components = cec_fr.net_connectivity_component_count(
                board, net_code) if net_code > 0 else 0
            stage_rows.append({"stage": "canonical_breadth", "net": net,
                               "components_after": components,
                               "report": stage})
            if components > 1:
                unresolved.append(net)
        remaining = effective_wall_s - (time.monotonic() - started)
        deep = None
        if unresolved and remaining > 0.0:
            deep = cec_fr.synthesize_lastmile(
                board, max_mm=25.0, min_w=0.2, clearance=0.0, cap=8,
                netclass_resolver=resolver, include_nets=set(unresolved),
                attempts_per_pair=int(attempt_budget), maze_max_mm=25.0,
                maze_margin_mm=float(margin), prefer_bridge=True,
                wall_timeout_s=remaining,
                per_net_timeout_s=max(
                    4.0, remaining / max(1, len(unresolved))))
            stage_rows.append({"stage": "deep_remaining",
                               "nets": list(unresolved), "report": deep})
        reports = [row["report"] for row in stage_rows]
        report = {
            "schema": 1, "staged": True, "stages": stage_rows,
            "closed": sum(int(item.get("closed") or 0)
                          for item in reports),
            "refused": sum(int(item.get("refused") or 0)
                           for item in reports),
            "elapsed_s": round(time.monotonic() - started, 3),
        }
    else:
        report = cec_fr.synthesize_lastmile(
            board, max_mm=25.0, min_w=0.2, clearance=0.0, cap=8,
            netclass_resolver=resolver, include_nets=set(nets),
            attempts_per_pair=int(attempt_budget), maze_max_mm=25.0,
            maze_margin_mm=float(margin), prefer_bridge=False,
            wall_timeout_s=wall_timeout_s,
            per_net_timeout_s=per_net_timeout_s)
    if report.get("closed"):
        _save_with_reconciled_endpoint_neckdowns(board_path, board, report)
    return report


def _exact_relocated_connections_worker(board_path, target_row, move,
                                        wall_timeout_s=30.0):
    """Reconnect a moved support cell to its certified live boundaries.

    Relocation already records the exact far end of every removed incident
    segment, and its refusal certificate records the target net's live remote
    endpoint.  Searching every disconnected island on either net discards
    that information and can spend a minute proving the wrong pair.  Route
    only those pad-to-node pairs first, with the ordinary layer, clearance,
    edge, POFV, and endpoint-neckdown guards.  The caller still performs a
    whole-board connectivity and DRC admission after the composite move.
    """

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    fp = board.FindFootprintByReference(target.ref)
    if fp is None:
        return {"schema": 1, "closed": 0, "target_closed": False,
                "refused": [{"role": "target",
                              "refusal": "moved_footprint_missing"}]}

    pairs = []
    target_pads = [pad for pad in fp.Pads()
                   if str(pad.GetNetname()) == str(target.target_net)]
    endpoint_override = dict(move.get("target_endpoint_override") or {})
    target_x_mm = float(endpoint_override.get(
        "x_mm", target.endpoint_x_mm))
    target_y_mm = float(endpoint_override.get(
        "y_mm", target.endpoint_y_mm))
    if target_pads:
        remote = pcbnew.VECTOR2I(
            int(round(target_x_mm * MM)), int(round(target_y_mm * MM)))
        pad = min(target_pads, key=lambda item: math.hypot(
            item.GetCenter().x - remote.x, item.GetCenter().y - remote.y))
        pairs.append({
            "role": "target", "net": str(target.target_net),
            "ref": target.ref, "pad": str(pad.GetNumber()),
            "x_mm": target_x_mm, "y_mm": target_y_mm,
            "endpoint_override": endpoint_override or None,
        })
    else:
        pairs.append({"role": "target", "net": str(target.target_net),
                      "refusal": "target_pad_missing_after_move"})

    for anchor in move.get("preserved_anchors") or ():
        pairs.append({
            "role": "support", "net": str(anchor.get("net") or ""),
            "ref": str(anchor.get("ref") or ""),
            "pad": str(anchor.get("pad") or ""),
            "x_mm": float(anchor.get("x_mm") or 0.0),
            "y_mm": float(anchor.get("y_mm") or 0.0),
            "track_uuid": str(anchor.get("track_uuid") or ""),
        })

    started = time.monotonic()
    closed = []
    refused = []
    target_closed = False
    for index, pair in enumerate(pairs):
        if pair.get("refusal"):
            refused.append(pair)
            continue
        remaining = max(
            0.0, float(wall_timeout_s) - (time.monotonic() - started))
        if remaining <= 0.0:
            refused.append({**pair,
                            "refusal": "relocated_pair_budget_exhausted"})
            continue
        footprint = board.FindFootprintByReference(pair["ref"])
        pad = (None if footprint is None else next(
            (item for item in footprint.Pads()
             if str(item.GetNumber()) == pair["pad"]
             and str(item.GetNetname()) == pair["net"]), None))
        if pad is None:
            refused.append({**pair,
                            "refusal": "relocated_pair_pad_not_live"})
            continue
        distance_mm = math.hypot(
            pad.GetCenter().x / MM - pair["x_mm"],
            pad.GetCenter().y / MM - pair["y_mm"])
        resolver = cec_fr._project_netclass_resolver(board_path)
        spec = dict(resolver(pair["net"]) or {})
        if pair["role"] == "target" and endpoint_override:
            remote_endpoint = {
                key: endpoint_override[key]
                for key in ("kind", "ref", "pad", "uuid", "x_mm", "y_mm")
                if endpoint_override.get(key) is not None}
            remote_endpoint.setdefault("kind", "node")
            remote_endpoint.setdefault("x_mm", pair["x_mm"])
            remote_endpoint.setdefault("y_mm", pair["y_mm"])
        elif (pair["role"] == "target" and target.endpoint_ref
              and target.endpoint_pad):
            remote_endpoint = {
                "kind": "pad", "ref": target.endpoint_ref,
                "pad": target.endpoint_pad,
                "x_mm": pair["x_mm"], "y_mm": pair["y_mm"]}
        else:
            remote_endpoint = {"kind": "node", "x_mm": pair["x_mm"],
                               "y_mm": pair["y_mm"]}
        window = NegotiationWindow(
            net=pair["net"], distance_mm=float(distance_mm),
            width_mm=max(0.15, float(spec.get("track_width") or 0.0)),
            clearance_mm=max(0.0, float(spec.get("clearance") or 0.0)),
            blocker_uuids=(), blocker_nets=(), blocker_hits=0,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0,
            endpoints=(
                remote_endpoint,
                {"kind": "pad", "ref": pair["ref"],
                 "pad": pair["pad"]}),
            priority=(index,), local_pin_escape=True)
        # Share the finite wall clock fairly across the remaining exact pairs.
        allowance = max(1.0, min(20.0, remaining / max(
            1, len(pairs) - index)))
        changed, detail = _close_certificate_pair(
            board, window, board_path=board_path, prefer_bridge=False,
            wall_timeout_s=allowance)
        row = {**pair, "distance_mm": round(distance_mm, 6),
               "completion": detail}
        if not changed:
            row["refusal"] = str(detail.get("refusal") or
                                  "relocated_pair_not_closed")
            refused.append(row)
            continue
        board.BuildConnectivity()
        closed.append(row)
        if pair["role"] == "target":
            target_closed = True

    report = {
        "schema": 1, "closed": len(closed),
        "target_closed": bool(target_closed),
        "support_closed": sum(row["role"] == "support" for row in closed),
        "support_closed_nets": sorted({
            row["net"] for row in closed if row["role"] == "support"}),
        "support_expected": sum(row.get("role") == "support"
                                and not row.get("refusal") for row in pairs),
        "closed_details": closed, "refused": refused,
        "elapsed_s": round(time.monotonic() - started, 3),
    }
    if closed:
        _save_with_reconciled_endpoint_neckdowns(board_path, board, report)
    return report


def _live_refusal_probe_worker(board_path, target_nets, attempt_budget=24,
                               margin=8.0):
    """Measure blockers and persist any exact legal closures on a scratch board.

    The caller always supplies a disposable candidate family and admits it
    transactionally.  Throwing away a probe that already proved and emitted a
    legal route forced a later, differently configured finisher to rediscover
    the same topology; on dense boards that turned a solved I2C connection
    back into an end-of-run ratline.
    """

    board = pcbnew.LoadBoard(board_path)
    resolver = cec_fr._project_netclass_resolver(board_path)
    report = cec_fr.synthesize_lastmile(
        board, max_mm=25.0, min_w=0.25, clearance=0.0, cap=8,
        netclass_resolver=resolver, include_nets=set(target_nets),
        attempts_per_pair=int(attempt_budget), maze_max_mm=25.0,
        maze_margin_mm=float(margin), prefer_bridge=True)
    if report.get("closed"):
        _save_with_reconciled_endpoint_neckdowns(board_path, board, report)
    return report


def _broad_canonical_worker(board_path, target_nets):
    """Try long canonical/bridge closures without a board-scale maze.

    The residual router can leave electrically simple component islands tens
    of millimetres apart.  The historical 25 mm finishing ceiling classified
    those as someone else's problem, while enabling an 80 mm maze made one
    cleanup pass take minutes per net.  Canonical 0/45/90 and guarded bridge
    attempts scale acceptably at 80 mm; maze search remains disabled here and
    certificate negotiation owns the genuinely obstructed cases.
    """

    board = pcbnew.LoadBoard(board_path)
    resolver = cec_fr._project_netclass_resolver(board_path)
    try:
        outer_timeout_s = max(1.0, float(os.environ.get(
            "CEC_CERTIFICATE_CANONICAL_NET_TIMEOUT_S", "8")))
    except (TypeError, ValueError):
        outer_timeout_s = 8.0
    # Yield before the supervising worker deadline so monotonic partial
    # closures can be saved and adjudicated.  Previously the parent killed a
    # dense-net worker at eight seconds and discarded every legal connection
    # it had already found.  This inner deadline is a search bound only; the
    # unchanged full-board DRC/connectivity gate decides whether to adopt it.
    inner_timeout_s = max(0.25, outer_timeout_s - 2.0)
    report = cec_fr.synthesize_lastmile(
        board, max_mm=80.0, min_w=0.2, clearance=0.0, cap=64,
        netclass_resolver=resolver, include_nets=set(target_nets),
        attempts_per_pair=8, maze_max_mm=0.0, maze_margin_mm=2.0,
        # This is the breadth pass: sample the bounded cardinal dogbone set
        # and move on.  The former full lattice made the nearest obstructed
        # island consume the entire per-net allowance, starving seven easy
        # +3V3 islands on the six-layer PCIe board.  Deep lattice/maze work is
        # still available later under an exact refusal certificate.
        bridge_fast=True,
        wall_timeout_s=inner_timeout_s,
        per_net_timeout_s=inner_timeout_s)
    if report.get("closed"):
        _save_with_reconciled_endpoint_neckdowns(board_path, board, report)
    return report


def _completion_net(detail: dict) -> str:
    """Return the net named by one last-mile detail/certificate row."""

    certificate = detail.get("certificate") or {}
    return str(certificate.get("net") or detail.get("net") or "")


def _rank_single_net_closure_targets(open_nets, completion) -> list[str]:
    """Schedule certified/local residuals before unknown long connections.

    A multi-net last-mile call is sequential inside one KiCad process.  One
    pathological residual therefore used to consume the whole worker deadline
    and prevent every later net -- including already-certified congestion
    windows -- from reaching negotiation.  Rank each live net independently:
    known refusal distance first, then deterministic name order.  Unknown nets
    remain eligible but cannot starve evidence-backed local work.
    """

    distances = {}
    for row in refusal_certificates(completion):
        detail = row.get("detail") or {}
        net = _completion_net(detail)
        if not net:
            continue
        try:
            distance = float(detail.get("distance_mm"))
        except (TypeError, ValueError):
            distance = float("inf")
        distances[net] = min(distance, distances.get(net, float("inf")))
    return sorted(
        {str(net) for net in (open_nets or ()) if str(net)},
        key=lambda net: (
            0 if net in distances else 1,
            distances.get(net, float("inf")),
            net,
        ))


def _merge_single_net_completion_reports(open_nets, reports,
                                         fallback_completion=None) -> dict:
    """Build one current refusal ledger from isolated per-net reports.

    Preserve a caller-supplied live-net certificate when its cheap canonical
    probe timed out.  Replace it as soon as that net returns a newer refusal,
    and remove it when the net closes.  The result deliberately exposes the
    ordinary ``refused_details`` schema consumed by every negotiation planner.
    """

    live = {str(net) for net in (open_nets or ()) if str(net)}
    by_net = {}
    for row in refusal_certificates(fallback_completion):
        detail = copy.deepcopy(row.get("detail") or {})
        net = _completion_net(detail)
        if net in live:
            by_net.setdefault(net, []).append(detail)
    timeouts = []
    for item in reports or ():
        net = str(item.get("net") or "")
        report = item.get("completion")
        if isinstance(report, dict):
            fresh = [copy.deepcopy(row.get("detail") or {})
                     for row in refusal_certificates(report)]
            if fresh:
                by_net[net] = fresh
            elif int(report.get("closed") or 0) > 0:
                by_net.pop(net, None)
        if item.get("timeout"):
            timeouts.append({
                "net": net,
                "error": str(item.get("error") or "")[:400],
            })
    refused = [detail for net in sorted(by_net)
               for detail in by_net[net] if net in live]
    return {
        "schema": 1,
        "closed": 0,
        "refused": len(refused),
        "refused_details": refused,
        "isolated_timeouts": timeouts,
    }


def _defer_support_relocation(footprint_plan, negotiation_plan,
                              prior_report=None) -> bool:
    """Prefer bounded copper negotiation over moving a placed component.

    A refusal can name both a nearby support part and exact movable route
    blockers.  Component relocation is the larger degree of freedom: it
    invalidates every incident branch and may require several expensive
    completion searches.  If an atomic route window exists, consume that
    smaller transaction first.  A later freshly measured wave may still move
    the support when copper negotiation proves no window remains.
    """

    targets = (footprint_plan or {}).get("targets") or ()
    windows = (negotiation_plan or {}).get("windows") or ()
    if not (targets and windows):
        return False
    if (isinstance(prior_report, dict)
            and str(prior_report.get("algorithm_revision") or "") ==
                REPAIR_ALGORITHM_REVISION
            and not bool(prior_report.get("changed"))
            and _prior_has_footprint_attempts(prior_report)):
        # The unchanged predecessor already crossed the route-fixed-point
        # gate and spent its bounded slice on placement.  Continue that finite
        # candidate frontier; do not bounce back to the same route windows
        # merely because the predecessor ended before writing a later-stage
        # schedule row.
        return False
    _ordered, prior = _prioritize_windows_by_proven_close(
        windows, prior_report)
    current_nets = {str(row.get("net") or "") for row in windows
                    if row.get("net")}
    prior_timeouts = set(prior.get("timed_out_nets") or ())
    prior_exhausted = set(prior.get("exhausted_nets") or ())
    # Once every current, freshly certified route window has already consumed
    # its bounded target search without a close, repeating those windows before
    # placement is a loop.  This changes only stage order: footprint motion is
    # still independently transactional and whole-board gated.
    return not bool(
        current_nets
        and current_nets <= (prior_timeouts | prior_exhausted))


def _drc_dangling_targets(drc_data):
    """Return exact route UUIDs identified by KiCad as dangling copper."""
    rows = {}
    for violation in (drc_data or {}).get("violations") or ():
        kind = str(violation.get("type") or "")
        if kind not in {"track_dangling", "via_dangling"}:
            continue
        for item in violation.get("items") or ():
            description = str(item.get("description") or "")
            if not description.startswith(("Track ", "Arc ", "Via ")):
                continue
            uid = str(item.get("uuid") or "")
            if uid:
                rows[uid] = kind
    return rows


def _drc_dangling_cleanup_worker(board_path, max_iterations=8):
    """Delete only KiCad-proven dangling route items until the cascade settles.

    Locked router output is not authorship here: an item enters this pass only
    when the current KiCad DRC names its exact UUID as dangling.  The caller
    still evaluates the complete candidate transactionally and rejects any
    connectivity, pair, or DRC regression.
    """
    removed = []
    stop = "iteration_budget"
    with tempfile.TemporaryDirectory(prefix="cec_dangling_probe_") as work:
        for iteration in range(max(1, int(max_iterations))):
            raw = _run_drc(
                board_path, os.path.join(work, "drc-%02d.json" % iteration))
            targets = _drc_dangling_targets(raw)
            if not targets:
                stop = "settled"
                break
            board = pcbnew.LoadBoard(board_path)
            items = {_uuid(item): item for item in board.GetTracks()
                     if _uuid(item)}
            selected = [(uid, targets[uid], items[uid])
                        for uid in sorted(targets) if uid in items]
            if not selected:
                stop = "drc_uuid_not_found"
                break
            for uid, kind, item in selected:
                removed.append({
                    "iteration": iteration,
                    "uuid": uid,
                    "type": kind,
                    "item": item.GetClass(),
                    "net": item.GetNetname() or "",
                    "locked": bool(item.IsLocked()),
                })
                # Transfer ownership to KiCad immediately.  ``Remove`` leaves
                # the Python SWIG proxy live after the board is saved; the
                # next cascade iteration can then receive that stale proxy in
                # place of a BOARD and fail before the monotonic scorer sees a
                # valid pruned candidate.
                board.Delete(item)
            pcbnew.SaveBoard(board_path, board)
            selected.clear()
            items.clear()
            del board
    return bool(removed), {
        "schema": 1,
        "removed": removed,
        "removed_count": len(removed),
        "iterations": (max((row["iteration"] for row in removed), default=-1)
                       + 1),
        "stop": stop,
    }


def _footprint_candidate_key(ref, candidate):
    """Stable identity for one deterministic support-placement pose."""

    companions = tuple(sorted(
        str(item) for item in
        (candidate.get("mobility_companion_refs") or ()) if item))
    identity_ref = str(ref or "")
    if companions:
        identity_ref += "|" + ",".join(companions)

    return (
        identity_ref,
        round(float(candidate.get("rotation_delta_deg") or 0.0), 6),
        round(float(candidate.get("dx_mm") or 0.0), 6),
        round(float(candidate.get("dy_mm") or 0.0), 6),
    )


def _prior_footprint_candidate_keys(report):
    """Collect already-scored or bounded-out placement poses recursively."""

    if (report or {}).get("algorithm_revision") != \
            REPAIR_ALGORITHM_REVISION:
        # A geometry/search change can make an old rejected pose legal.  Pose
        # memory is valid only within the exact algorithm revision that
        # produced the refusal.
        return set()
    keys = set()
    retry_keys = set()
    for row in (((report or {}).get("plan") or {}).get(
            "placement_candidate_history") or ()):
        if isinstance(row, (list, tuple)) and len(row) == 4 and row[0]:
            keys.add((str(row[0]), round(float(row[1]), 6),
                      round(float(row[2]), 6), round(float(row[3]), 6)))

    def visit(value):
        if isinstance(value, dict):
            if (value.get("stage") in {
                    "footprint_relocation", "endpoint_owner_relocation"}
                    and isinstance(value.get("candidate"), dict)):
                timed_out = (
                    value.get("decision") ==
                    "component_transaction_worker_error"
                    and "WorkerPoolStalled" in str(value.get("error") or "")
                    and value.get(
                        "placement_copper_restoration_budget_s") is None)
                target = value.get("target") or {}
                key = _footprint_candidate_key(
                    target.get("ref"), value["candidate"])
                if key[0] and timed_out:
                    retry_keys.add(key)
                    keys.discard(key)
                elif key[0] and key not in retry_keys:
                        keys.add(key)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(report or {})
    return keys - retry_keys


def _prior_has_footprint_attempts(report):
    """Return whether an unchanged predecessor reached placement work."""

    found = False

    def visit(value):
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            if (value.get("stage") in {
                    "footprint_relocation", "endpoint_owner_relocation"}
                    and isinstance(value.get("candidate"), dict)):
                found = True
                return
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(report or {})
    return found


def _placement_frontier_advanced(*sweeps) -> bool:
    """Return whether this wave accepted a placement transaction.

    A current refusal may continue to name a support or endpoint owner after
    every deterministic pose for that object has already been measured.  The
    presence of a target is therefore not proof that the placement frontier
    advanced.  A rejected pose leaves placement and every route certificate
    byte-for-byte valid, so ending the slice there only manufactures another
    identical wave.  Only an accepted move invalidates the current route graph
    and justifies a placement-only slice; all refusals fall through to the next
    route/via degree of freedom in the same bounded transaction.
    """

    return any(
        bool((sweep or {}).get("accepted"))
        for sweep in sweeps)


def _retarget_preserved_anchors_for_via_move(
        anchors, *, net, via_uuid, old_mm, new_mm, tolerance_mm=1e-6):
    """Move relocation-certificate anchors carried by a displaced via.

    A footprint move preserves the live boundary beyond each removed pad
    stub.  If detailed placement subsequently moves a via exactly at that
    boundary, the electrical boundary moves with the barrel and its rebuilt
    incident stubs.  Keeping the old coordinate turns a valid support route
    into ``certificate_endpoint_not_live`` and sends a short exact connection
    into an expensive whole-net fallback.  Retarget only same-net anchors at
    the exact old via centre; every unrelated certificate remains immutable.
    """

    try:
        old_x, old_y = map(float, old_mm)
        new_x, new_y = map(float, new_mm)
    except (TypeError, ValueError):
        return [dict(row) for row in anchors or ()], []
    updated = []
    evidence = []
    for anchor in anchors or ():
        row = dict(anchor)
        if (str(row.get("net") or "") == str(net or "")
                and abs(float(row.get("x_mm") or 0.0) - old_x)
                <= float(tolerance_mm)
                and abs(float(row.get("y_mm") or 0.0) - old_y)
                <= float(tolerance_mm)):
            evidence.append({
                "ref": str(row.get("ref") or ""),
                "pad": str(row.get("pad") or ""),
                "net": str(row.get("net") or ""),
                "via_uuid": str(via_uuid or ""),
                "old_mm": [old_x, old_y],
                "new_mm": [new_x, new_y],
            })
            row["x_mm"] = round(new_x, 6)
            row["y_mm"] = round(new_y, 6)
            row["anchor_via_uuid"] = str(via_uuid or "")
        updated.append(row)
    return updated, evidence


def _persist_placement_candidate_history(plan, prior_candidates=()):
    """Persist deterministic pose memory on normal and bounded-stop exits."""

    placement_history = set(prior_candidates or ())
    placement_history.update(_prior_footprint_candidate_keys({
        "algorithm_revision": REPAIR_ALGORITHM_REVISION,
        "plan": plan,
    }))
    plan["placement_candidate_history"] = [
        list(key) for key in sorted(placement_history)
    ]
    return plan["placement_candidate_history"]


def _attempt_placement_via_clearance(
        board_path, before, target_row, move, conflicts, *, work_dir, token,
        generated_locked_uuids=(), max_candidates=8):
    """Displace exact pipeline vias that occupy a proposed component seat.

    Every offset is evaluated on a fresh child of the current staged board.
    A via pose is retained only when the named barrel no longer participates
    in the placement collision, no fixed component/authored/zone collision is
    introduced, and the classified physical-debt count does not increase.
    The ordinary footprint transaction still has to reconnect the target and
    pass full-board admission, so this is a bounded detailed-placement degree
    of freedom rather than permission to weaken DRC.
    """

    via_targets = [dict(row) for row in
                   (conflicts.get("movable_via_targets") or ())]
    if not via_targets:
        return False, {"refusal": "no_movable_via_targets"}, conflicts, {}
    staged = os.path.join(work_dir, "placement-via-%s-stage.kicad_pcb" % token)
    _copy_board_family(board_path, staged)
    current_conflicts = dict(conflicts)
    moved_vias = []
    generated_tracks = []
    generated_locked_tracks = []
    current_anchors = [dict(row) for row in
                       (move.get("preserved_anchors") or ())]
    anchor_updates = []
    attempts = []
    per_via_limit = max(1, int(max_candidates))

    for via_index, via_row in enumerate(via_targets):
        via_uid = str(via_row.get("uuid") or "")
        if via_uid not in set(
                current_conflicts.get("movable_via_uuids") or ()):
            continue
        target = ViaRepairTarget(**via_row)
        owner_directions = []
        staged_board = pcbnew.LoadBoard(staged)
        for anchor in current_anchors:
            if (str(anchor.get("net") or "") != str(target.net or "")
                    or abs(float(anchor.get("x_mm") or 0.0)
                           - target.x_nm / MM) > 1e-6
                    or abs(float(anchor.get("y_mm") or 0.0)
                           - target.y_nm / MM) > 1e-6):
                continue
            footprint = staged_board.FindFootprintByReference(
                str(anchor.get("ref") or ""))
            pad = (None if footprint is None else next((
                item for item in footprint.Pads()
                if str(item.GetNumber()) == str(anchor.get("pad") or "")
                and str(item.GetNetname() or "") == str(target.net or "")),
                None))
            if pad is None:
                continue
            owner_directions.append(_octant_away(
                int(pad.GetCenter().x) - int(target.x_nm),
                int(pad.GetCenter().y) - int(target.y_nm)))
        owner_directions = tuple(dict.fromkeys(owner_directions))
        del staged_board
        adopted = False
        for offset_index, (dx_nm, dy_nm, step_mm, direction) in enumerate(
                itertools.islice(_placement_via_offset_candidates(
                    target, owner_directions),
                                  per_via_limit)):
            trial = os.path.join(
                work_dir, "placement-via-%s-%02d-%02d.kicad_pcb" %
                (token, via_index, offset_index))
            _copy_board_family(staged, trial)
            row = {
                "uuid": via_uid, "net": target.net,
                "step_mm": float(step_mm), "direction": list(direction),
                "owner_directions": [list(value)
                                     for value in owner_directions],
            }
            changed, evidence = _spawn_apply(
                _relocate_via_worker,
                (trial, via_row, dx_nm, dy_nm,
                 tuple(generated_locked_uuids)), timeout_s=20.0)
            row["move"] = evidence
            if not changed:
                row.update({"accepted": False,
                            "decision": evidence.get("refusal")})
                attempts.append(row)
                continue

            candidate_move = dict(move)
            candidate_move["placement_relocated_via_uuids"] = sorted({
                *map(str, moved_vias), via_uid,
            })
            candidate_generated = sorted({
                *map(str, generated_tracks),
                *map(str, evidence.get("generated_track_uuids") or ()),
            })
            candidate_generated_locked = sorted({
                *map(str, generated_locked_tracks),
                *map(str, evidence.get(
                    "generated_locked_track_uuids") or ()),
            })
            candidate_move["moved_internal_track_uuids"] = sorted({
                *map(str, move.get("moved_internal_track_uuids") or ()),
                *candidate_generated,
            })
            candidate_move["placement_generated_locked_uuids"] = \
                candidate_generated_locked
            _spawn_apply(_refill_worker, (trial,))
            drc_path = os.path.join(
                work_dir, "placement-via-%s-%02d-%02d-drc.json" %
                (token, via_index, offset_index))
            _run_drc(trial, drc_path)
            with open(drc_path, encoding="utf-8") as source:
                drc_data = json.load(source)
            post_conflicts = _spawn_apply(
                _classify_placement_conflicts_worker,
                (trial, drc_data, target_row, candidate_move,
                 tuple(generated_locked_uuids)), timeout_s=15.0)
            score = _spawn_apply(_score_worker, (trial, drc_path))
            preflight_ok, preflight_decision, preflight_faults = \
                _placement_preflight_accepts(before, score)
            old_vias = set(current_conflicts.get("movable_via_uuids") or ())
            new_vias = set(post_conflicts.get("movable_via_uuids") or ())
            old_count = len(current_conflicts.get("violations") or ())
            new_count = len(post_conflicts.get("violations") or ())
            accepted = (
                via_uid not in new_vias
                and not (new_vias - (old_vias - {via_uid}))
                and not post_conflicts.get("fixed_conflict_count")
                and new_count <= old_count)
            row.update({
                "after_conflicts": post_conflicts,
                "placement_preflight": {
                    "accepted": preflight_ok,
                    "decision": preflight_decision,
                    "new_faults": preflight_faults,
                },
                "accepted": accepted,
                "decision": ("via_conflict_reduced" if accepted else
                             "via_conflict_not_reduced"),
            })
            attempts.append(row)
            if not accepted:
                continue
            current_anchors, via_anchor_updates = \
                _retarget_preserved_anchors_for_via_move(
                    current_anchors, net=target.net, via_uuid=via_uid,
                    old_mm=evidence.get("old_mm") or (),
                    new_mm=evidence.get("new_mm") or ())
            anchor_updates.extend(via_anchor_updates)
            _copy_board_family(trial, staged)
            current_conflicts = post_conflicts
            moved_vias.append(via_uid)
            generated_tracks = candidate_generated
            generated_locked_tracks = candidate_generated_locked
            adopted = True
            break
        if not adopted:
            return False, {
                "refusal": "placement_via_candidate_exhausted",
                "via_uuid": via_uid, "attempts": attempts,
            }, conflicts, {}

    if not moved_vias:
        return False, {"refusal": "no_placement_via_moved",
                       "attempts": attempts}, conflicts, {}
    _copy_board_family(staged, board_path)
    return True, {
        "mode": "placement_via_clearance",
        "moved_via_uuids": sorted(moved_vias),
        "generated_track_uuids": sorted(generated_tracks),
        "generated_locked_track_uuids": sorted(generated_locked_tracks),
        "preserved_anchor_updates": anchor_updates,
        "attempts": attempts,
    }, current_conflicts, {
        "placement_relocated_via_uuids": sorted(moved_vias),
        "placement_generated_locked_uuids": sorted(
            generated_locked_tracks),
        "moved_internal_track_uuids": sorted({
            *map(str, move.get("moved_internal_track_uuids") or ()),
            *map(str, generated_tracks),
        }),
        "preserved_anchors": current_anchors,
    }


def _route_certificate_soft_obstacle_refs(
        board_path, certificate, target_row, *, limit=2):
    """Return eligible support parts sealing either exact endpoint's rays.

    This is the feedback edge between routing and detailed placement.  Only
    exact foreign-pad identities repeated in blocked endpoint rays may extend
    the cell, and the same mobility policy used by occupancy placement keeps
    connectors, THT, grouped/locked/mechanical, and multi-pin parts fixed.
    """

    target = FootprintRepairTarget(**target_row)
    existing = {target.ref, target.endpoint_ref,
                *map(str, target.companion_refs)}
    counts = {}
    blocker_pads = {}
    for layer in (certificate or {}).get("layers") or ():
        for escape in layer.get("endpoint_escape") or ():
            # Either side can be the true cut.  Moving a support whose own pad
            # already has a legal ray cannot repair a sealed peer pin; inspect
            # every endpoint with no escape on the layer and let the mobility
            # policy below decide whether any named blocker may move.
            if escape.get("clear_rays"):
                continue
            for ray in escape.get("ray_details") or ():
                if ray.get("status") != "foreign_copper_blocked":
                    continue
                for blocker in ray.get("blockers") or ():
                    if blocker.get("kind") != "pad":
                        continue
                    ref = str(blocker.get("ref") or "")
                    if not ref or ref in existing:
                        continue
                    counts[ref] = counts.get(ref, 0) + 1
                    blocker_pads.setdefault(ref, set()).add(str(
                        blocker.get("pad") or ""))
    if not counts:
        return []

    board = pcbnew.LoadBoard(board_path)
    owner = board.FindFootprintByReference(target.ref)
    if owner is None:
        return []
    owner_position = owner.GetPosition()
    grouped = {
        footprint.GetReference()
        for group in board.Groups() for footprint in board.GetFootprints()
        if group.ContainsItem(footprint)}
    eligible = []
    for ref, hits in counts.items():
        footprint = board.FindFootprintByReference(ref)
        pads = (list(footprint.Pads()) if footprint is not None else [])
        copper_pads = [pad for pad in pads if pad.IsOnCopperLayer()]
        distance = (math.hypot(
            footprint.GetPosition().x - owner_position.x,
            footprint.GetPosition().y - owner_position.y) / MM
                    if footprint is not None else 1e9)
        if (footprint is None or footprint.IsLocked() or ref in grouped
                or ref.upper().startswith(("J", "H", "FID", "LOGO", "MK"))
                or len(copper_pads) != 2
                or any(pad.HasHole() for pad in copper_pads)
                or distance > 6.0 + 1e-9):
            continue
        eligible.append((-hits, distance, ref, sorted(blocker_pads[ref])))
    eligible.sort()
    return [{"ref": ref, "hit_count": -neg_hits,
             "distance_mm": round(distance, 6), "pads": pads}
            for neg_hits, distance, ref, pads in
            eligible[:max(0, int(limit))]]


def _route_certificate_movable_track_uuids(
        board_path, certificate, *, generated_locked_uuids=(), limit=4):
    """Rank exact policy-movable tracks sealing either route endpoint.

    Only UUIDs named in blocked rays at an endpoint with no clear ray enter
    the result.  Existing protected-net policy and authored-baseline
    provenance remain authoritative; the evacuation worker rechecks both
    immediately before mutation.
    """

    counts = {}
    for layer in (certificate or {}).get("layers") or ():
        for escape in layer.get("endpoint_escape") or ():
            if escape.get("clear_rays"):
                continue
            for ray in escape.get("ray_details") or ():
                if ray.get("status") != "foreign_copper_blocked":
                    continue
                for blocker in ray.get("blockers") or ():
                    if blocker.get("kind") != "track":
                        continue
                    uid = str(blocker.get("uuid") or "")
                    if uid:
                        counts[uid] = counts.get(uid, 0) + 1
    if not counts:
        return []
    board = pcbnew.LoadBoard(board_path)
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    eligible = []
    for uid, hits in counts.items():
        item = _find_track(board, uid)
        if item is None or item.GetClass() != "PCB_TRACK":
            continue
        net = str(item.GetNetname() or "")
        layer = board.GetLayerName(item.GetLayer())
        locked = bool(item.IsLocked())
        if locked and uid not in generated:
            continue
        reason = protected_net_reason(
            net, width_mm=item.GetWidth() / MM, layer=layer,
            locked=(locked and uid not in generated))
        if reason:
            continue
        eligible.append((-hits, uid))
    eligible.sort()
    return [uid for _neg_hits, uid in
            eligible[:max(0, int(limit))]]


def _normalize_pad_owned_via_to_profile_worker(
        board_path, via_uuid, ownership_snapshot_rows=()):
    """Shrink an oversized local through via to qualified POFV geometry.

    This is not a generic via-size waiver.  The board must explicitly declare
    a filled/capped profile.  A via may either be fully contained by a same-net
    SMD pad or terminate a short, same-net SMD dogbone; true via-in-pad still
    requires full-land containment.  The smallest valid profile geometry is
    used so an adjacent fine-pitch pin is not sealed by an ordinary 0.9/0.5 mm
    barrel.  Centre and net stay unchanged, preserving the immediate return.
    """

    board = pcbnew.LoadBoard(board_path)
    via = next((item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"
                and _uuid(item) == str(via_uuid)), None)
    if via is None:
        return False, {"refusal": "pad_owned_via_not_live"}
    profile_name = _fab.board_profile_name(board)
    profile = _fab.get_profile(profile_name) if profile_name else None
    if not profile or not profile.get("pofv"):
        return False, {"refusal": "board_has_no_pofv_profile"}
    position = via.GetPosition()
    net_code = int(via.GetNetCode())
    owners = [
        (footprint.GetReference(), str(pad.GetNumber()), pad, "via_in_pad")
        for footprint in board.GetFootprints()
        for pad in footprint.Pads()
        if pad.IsOnCopperLayer() and int(pad.GetNetCode()) == net_code
        and pad.HitTest(position)]
    if not owners:
        # Filled/capped process geometry also applies to a local dogbone via
        # just outside its land.  Prove ownership from an exact incident track
        # endpoint and a short opposite endpoint seated on a same-net SMD pad;
        # do not normalize arbitrary remote or stitching vias.
        for item in board.GetTracks():
            if (item.GetClass() != "PCB_TRACK"
                    or int(item.GetNetCode()) != net_code):
                continue
            start = item.GetStart()
            end = item.GetEnd()
            if start == position:
                pad_point = end
            elif end == position:
                pad_point = start
            else:
                continue
            if math.hypot(pad_point.x - position.x,
                          pad_point.y - position.y) > 1.5 * MM:
                continue
            for footprint in board.GetFootprints():
                for pad in footprint.Pads():
                    if (not pad.IsOnCopperLayer()
                            or int(pad.GetNetCode()) != net_code
                            or not pad.HitTest(pad_point)):
                        continue
                    try:
                        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                            continue
                    except Exception:                 # noqa: BLE001
                        continue
                    owner = (footprint.GetReference(),
                             str(pad.GetNumber()), pad, "local_dogbone")
                    if not any((row[0], row[1], row[3]) ==
                               (owner[0], owner[1], owner[3])
                               for row in owners):
                        owners.append(owner)
    if not owners:
        # A placement transaction may have already evacuated the dogbone that
        # established this ownership.  Its immutable branch snapshot retains
        # exact endpoints and net identity, so use that proof rather than
        # guessing from proximity after the track has disappeared.
        for row in ownership_snapshot_rows or ():
            if str(row.get("net") or "") != str(via.GetNetname() or ""):
                continue
            start_xy = row.get("start_xy") or ()
            end_xy = row.get("end_xy") or ()
            if len(start_xy) != 2 or len(end_xy) != 2:
                continue
            start = pcbnew.VECTOR2I(int(start_xy[0]), int(start_xy[1]))
            end = pcbnew.VECTOR2I(int(end_xy[0]), int(end_xy[1]))
            if start == position:
                pad_point = end
            elif end == position:
                pad_point = start
            else:
                continue
            if math.hypot(pad_point.x - position.x,
                          pad_point.y - position.y) > 1.5 * MM:
                continue
            for footprint in board.GetFootprints():
                for pad in footprint.Pads():
                    if (not pad.IsOnCopperLayer()
                            or int(pad.GetNetCode()) != net_code
                            or not pad.HitTest(pad_point)):
                        continue
                    try:
                        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                            continue
                    except Exception:                 # noqa: BLE001
                        continue
                    owner = (footprint.GetReference(),
                             str(pad.GetNumber()), pad,
                             "evacuated_local_dogbone")
                    if not any((existing[0], existing[1], existing[3]) ==
                               (owner[0], owner[1], owner[3])
                               for existing in owners):
                        owners.append(owner)
    if not owners:
        return False, {"refusal": "via_has_no_local_smd_owner"}

    annular = float(profile["pofv_annular_min_mm"])
    drills = sorted({
        float(profile["pofv_drill_min_mm"]),
        *map(float, profile.get("pofv_drill_preferred_mm") or ()),
    })
    old_diameter = via.GetWidth(via.TopLayer()) / MM
    old_drill = via.GetDrillValue() / MM
    for drill_mm in drills:
        diameter_mm = drill_mm + 2.0 * annular
        if diameter_mm >= old_diameter - 1e-9:
            continue
        diameter_nm = int(round(diameter_mm * MM))
        drill_nm = int(round(drill_mm * MM))
        for ref, pad_number, pad, ownership_mode in owners:
            if ownership_mode == "via_in_pad":
                allowed, reason = _fab.via_pad_decision(
                    board, pad, position, diameter_nm, drill_nm, net_code)
            else:
                allowed, reason = _fab.pofv_dimensions(
                    profile, diameter_mm, drill_mm)
            if not allowed:
                continue
            via.SetWidth(diameter_nm)
            via.SetDrill(drill_nm)
            evidence = cec_fr.group_local_pofv_signal_vias(board, [via])
            if not evidence:
                return False, {"refusal": "pofv_group_qualification_failed"}
            pcbnew.SaveBoard(board_path, board)
            rule = cec_fr.ensure_local_pofv_signal_via_rule(
                board_path, {"local_pofv_signal_vias": evidence})
            return True, {
                "mode": "pad_owned_pofv_normalization",
                "uuid": str(via_uuid), "net": str(via.GetNetname() or ""),
                "owner_ref": ref, "owner_pad": pad_number,
                "ownership_mode": ownership_mode,
                "old_diameter_mm": round(old_diameter, 3),
                "old_drill_mm": round(old_drill, 3),
                "diameter_mm": round(diameter_mm, 3),
                "drill_mm": round(drill_mm, 3),
                "qualification": reason, "group": evidence,
                "rule": rule,
            }
    return False, {
        "refusal": "no_contained_smaller_pofv_geometry",
        "owners": [{"ref": ref, "pad": pad_number, "mode": mode}
                   for ref, pad_number, _pad, mode in owners],
    }


def _refresh_transaction_pofv_rule_worker(board_path, via_uuids):
    """Reassert exact normalized-via ownership before final admission."""

    wanted = {str(uid) for uid in via_uuids if uid}
    if not wanted:
        return False, {"refusal": "no_transaction_pofv_uuids"}
    board = pcbnew.LoadBoard(board_path)
    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA" and _uuid(item) in wanted]
    if {str(_uuid(via)) for via in vias} != wanted:
        return False, {"refusal": "transaction_pofv_via_not_live",
                       "requested": sorted(wanted),
                       "live": sorted(_uuid(via) for via in vias)}
    evidence = cec_fr.group_local_pofv_signal_vias(board, vias)
    if not evidence:
        return False, {"refusal": "transaction_pofv_requalification_failed"}
    pcbnew.SaveBoard(board_path, board)
    rule = cec_fr.ensure_local_pofv_signal_via_rule(
        board_path, {"local_pofv_signal_vias": evidence})
    return bool(rule.get("applicable")), {
        "mode": "transaction_pofv_rule_refresh",
        "group": evidence, "rule": rule,
    }


def _attempt_route_certificate_via_clearance(
        board_path, before, target_row, move, certificate, *, work_dir,
        token, generated_locked_uuids=(), ownership_snapshot_rows=(),
        max_vias=2, max_offsets=4):
    """Move one refusal-named ordinary via and retry the exact target pair.

    The existing congestion-via planner supplies pad ownership, protected-net,
    authored-lock, and direction checks.  Each offset is isolated; a moved
    barrel is retained only when physical preflight is clear *and* the exact
    target pair closes.  Displaced incident stubs remain part of the enclosing
    footprint transaction and final whole-board admission.
    """

    target = FootprintRepairTarget(**target_row)
    completion = {
        "unconn_nets": [target.target_net],
        "refused_details": [{
            "net": target.target_net,
            "distance_mm": float(target.distance_mm),
            "certificate": certificate,
        }],
    }
    via_plan = plan_congestion_via_repairs(
        board_path, completion,
        generated_locked_uuids=generated_locked_uuids,
        limit=max_vias)
    attempts = []
    for via_index, plan_row in enumerate(via_plan.get("targets") or ()):
        via_row = dict(plan_row["via"])
        via_target = ViaRepairTarget(**via_row)
        # Before moving a pad-owned return barrel away from its land, try the
        # profile-qualified geometry at the same centre.  This preserves the
        # shortest possible return and often frees the adjacent fine-pitch
        # escape without manufacturing another disconnected dogbone.
        normalized_trial = os.path.join(
            work_dir, "route-via-%s-%02d-pofv.kicad_pcb" %
            (token, via_index))
        _copy_board_family(board_path, normalized_trial)
        normalized, normalization = _spawn_apply(
            _normalize_pad_owned_via_to_profile_worker,
            (normalized_trial, via_target.uuid,
             tuple(ownership_snapshot_rows)), timeout_s=20.0)
        normalization_row = {
            "uuid": via_target.uuid, "net": via_target.net,
            "mode": "pad_owned_pofv_normalization",
            "normalization": normalization,
        }
        if normalized:
            _spawn_apply(_refill_worker, (normalized_trial,))
            drc_path = os.path.join(
                work_dir, "route-via-%s-%02d-pofv-drc.json" %
                (token, via_index))
            _run_drc(normalized_trial, drc_path)
            score = _spawn_apply(_score_worker, (normalized_trial, drc_path))
            preflight_ok, preflight_decision, preflight_faults = \
                _placement_preflight_accepts(before, score)
            normalization_row["placement_preflight"] = {
                "accepted": preflight_ok,
                "decision": preflight_decision,
                "new_faults": preflight_faults,
            }
            if preflight_ok:
                candidate_move = dict(move)
                candidate_move["placement_pofv_normalized_via_uuids"] = \
                    sorted({
                        *map(str, move.get(
                            "placement_pofv_normalized_via_uuids") or ()),
                        via_target.uuid,
                    })
                target_route_baseline = os.path.join(
                    work_dir,
                    "route-via-%s-%02d-pofv-pre-target.kicad_pcb" %
                    (token, via_index))
                _copy_board_family(normalized_trial, target_route_baseline)
                exact = _spawn_apply(
                    _exact_relocated_connections_worker,
                    (normalized_trial, target_row, candidate_move, 35.0),
                    timeout_s=40.0)
                normalization_row["exact_reconnect"] = exact
                if exact.get("target_closed"):
                    normalization_row.update({
                        "accepted": True,
                        "decision": "pad_owned_pofv_target_closed",
                    })
                    attempts.append(normalization_row)
                    _copy_board_family(normalized_trial, board_path)
                    return True, {
                        "mode": "pad_owned_pofv_normalization",
                        "plan": via_plan, "attempts": attempts,
                        "accepted_uuid": via_target.uuid,
                    }, exact, {
                        "placement_pofv_normalized_via_uuids":
                            candidate_move[
                                "placement_pofv_normalized_via_uuids"],
                        "target_route_baseline_path":
                            target_route_baseline,
                    }
                normalization_row.update({
                    "accepted": False,
                    "decision": "normalized_target_still_refused",
                })
            else:
                normalization_row.update({
                    "accepted": False, "decision": preflight_decision,
                })
        else:
            normalization_row.update({
                "accepted": False,
                "decision": normalization.get("refusal"),
            })
        attempts.append(normalization_row)
        for offset_index, (dx_nm, dy_nm, step_mm, direction) in enumerate(
                itertools.islice(_via_offset_candidates(via_target),
                                  max(1, int(max_offsets)))):
            trial = os.path.join(
                work_dir, "route-via-%s-%02d-%02d.kicad_pcb" %
                (token, via_index, offset_index))
            _copy_board_family(board_path, trial)
            row = {
                "uuid": via_target.uuid, "net": via_target.net,
                "step_mm": float(step_mm), "direction": list(direction),
            }
            changed, evidence = _spawn_apply(
                _relocate_via_worker,
                (trial, via_row, dx_nm, dy_nm,
                 tuple(generated_locked_uuids), True), timeout_s=20.0)
            row["move"] = evidence
            if not changed:
                row.update({"accepted": False,
                            "decision": evidence.get("refusal")})
                attempts.append(row)
                continue
            candidate_move = dict(move)
            candidate_move["placement_relocated_via_uuids"] = sorted({
                *map(str, move.get(
                    "placement_relocated_via_uuids") or ()),
                via_target.uuid,
            })
            generated_tracks = sorted({
                *map(str, move.get("moved_internal_track_uuids") or ()),
                *map(str, evidence.get("generated_track_uuids") or ()),
            })
            generated_locked_tracks = sorted({
                *map(str, move.get(
                    "placement_generated_locked_uuids") or ()),
                *map(str, evidence.get(
                    "generated_locked_track_uuids") or ()),
            })
            candidate_move["moved_internal_track_uuids"] = generated_tracks
            candidate_move["placement_generated_locked_uuids"] = \
                generated_locked_tracks
            _spawn_apply(_refill_worker, (trial,))
            drc_path = os.path.join(
                work_dir, "route-via-%s-%02d-%02d-drc.json" %
                (token, via_index, offset_index))
            _run_drc(trial, drc_path)
            score = _spawn_apply(_score_worker, (trial, drc_path))
            preflight_ok, preflight_decision, preflight_faults = \
                _placement_preflight_accepts(before, score)
            row["placement_preflight"] = {
                "accepted": preflight_ok,
                "decision": preflight_decision,
                "new_faults": preflight_faults,
            }
            if not preflight_ok:
                row.update({"accepted": False,
                            "decision": preflight_decision})
                attempts.append(row)
                continue
            target_route_baseline = os.path.join(
                work_dir,
                "route-via-%s-%02d-%02d-pre-target.kicad_pcb" %
                (token, via_index, offset_index))
            _copy_board_family(trial, target_route_baseline)
            exact = _spawn_apply(
                _exact_relocated_connections_worker,
                (trial, target_row, candidate_move, 35.0),
                timeout_s=40.0)
            row["exact_reconnect"] = exact
            if not exact.get("target_closed"):
                row.update({"accepted": False,
                            "decision": "target_still_refused"})
                attempts.append(row)
                continue
            row.update({"accepted": True,
                        "decision": "route_via_target_closed"})
            attempts.append(row)
            _copy_board_family(trial, board_path)
            return True, {
                "mode": "route_certificate_via_clearance",
                "plan": via_plan, "attempts": attempts,
                "accepted_uuid": via_target.uuid,
            }, exact, {
                "placement_relocated_via_uuids":
                    candidate_move["placement_relocated_via_uuids"],
                "placement_generated_locked_uuids":
                    generated_locked_tracks,
                "moved_internal_track_uuids": generated_tracks,
                "target_route_baseline_path": target_route_baseline,
            }
    return False, {
        "refusal": "route_certificate_via_candidate_exhausted",
        "plan": via_plan, "attempts": attempts,
    }, None, {}


def _attempt_target_endpoint_retreat(
        board_path, target_row, move, certificate, *, work_dir, token,
        generated_locked_uuids=(), max_candidates=4):
    """Shorten a certified dead-end leaf and retry the exact moved-pad pair."""

    plan = _spawn_apply(
        _target_endpoint_retreat_candidates_worker,
        (board_path, target_row, certificate,
         tuple(generated_locked_uuids), max_candidates, 6.0),
        timeout_s=20.0)
    attempts = []
    for index, candidate in enumerate(
            (plan.get("candidates") or ())[:max(0, int(max_candidates))]):
        trial = os.path.join(
            work_dir, "endpoint-retreat-%s-%02d.kicad_pcb" % (token, index))
        _copy_board_family(board_path, trial)
        changed, application = _spawn_apply(
            _apply_target_endpoint_retreat_worker,
            (trial, target_row.get("target_net"), candidate,
             tuple(generated_locked_uuids)), timeout_s=20.0)
        row = {"candidate": candidate, "application": application}
        if not changed:
            row.update({"accepted": False,
                        "decision": application.get("refusal")})
            attempts.append(row)
            continue
        candidate_move = dict(move)
        candidate_move["target_endpoint_override"] = dict(
            candidate.get("endpoint") or {})
        target_route_baseline = os.path.join(
            work_dir, "endpoint-retreat-%s-%02d-pre-target.kicad_pcb" %
            (token, index))
        _copy_board_family(trial, target_route_baseline)
        exact = _spawn_apply(
            _exact_relocated_connections_worker,
            (trial, target_row, candidate_move, 35.0), timeout_s=40.0)
        row["exact_reconnect"] = exact
        if not exact.get("target_closed"):
            row.update({"accepted": False,
                        "decision": "retreated_target_still_refused"})
            attempts.append(row)
            continue
        row.update({"accepted": True,
                    "decision": "retreated_target_closed"})
        attempts.append(row)
        _copy_board_family(trial, board_path)
        return True, {"plan": plan, "attempts": attempts,
                      "accepted_candidate": candidate}, exact, {
            "target_endpoint_override": dict(candidate.get("endpoint") or {}),
            "retreated_target_track_uuids": list(
                candidate.get("removed_uuids") or ()),
            "target_route_baseline_path": target_route_baseline,
        }
    return False, {"plan": plan, "attempts": attempts,
                   "refusal": "endpoint_retreat_candidate_exhausted"}, \
        None, {}


def _attempt_target_endpoint_access(
        board_path, target_row, move, certificate, *, work_dir, token,
        max_candidates=6):
    """Retry a moved target against bounded nodes on its live net component."""

    plan = _spawn_apply(
        _target_endpoint_access_candidates_worker,
        (board_path, target_row, certificate, max_candidates, 8.0,
         max_candidates), timeout_s=20.0)
    attempts = []
    for index, candidate in enumerate(
            (plan.get("candidates") or ())[:max(0, int(max_candidates))]):
        trial = os.path.join(
            work_dir, "endpoint-access-%s-%02d.kicad_pcb" % (token, index))
        _copy_board_family(board_path, trial)
        candidate_move = dict(move)
        candidate_move["target_endpoint_override"] = dict(
            candidate.get("endpoint") or {})
        target_route_baseline = os.path.join(
            work_dir, "endpoint-access-%s-%02d-pre-target.kicad_pcb" %
            (token, index))
        _copy_board_family(trial, target_route_baseline)
        exact = _spawn_apply(
            _exact_relocated_connections_worker,
            (trial, target_row, candidate_move, 30.0), timeout_s=35.0)
        row = {"candidate": candidate, "exact_reconnect": exact}
        if not exact.get("target_closed"):
            row.update({"accepted": False,
                        "decision": "access_target_still_refused"})
            attempts.append(row)
            continue
        row.update({"accepted": True, "decision": "access_target_closed"})
        attempts.append(row)
        _copy_board_family(trial, board_path)
        return True, {"plan": plan, "attempts": attempts,
                      "accepted_candidate": candidate}, exact, {
            "target_endpoint_override": dict(candidate.get("endpoint") or {}),
            "target_access_path_uuids": list(
                candidate.get("access_path_uuids") or ()),
            "target_route_baseline_path": target_route_baseline,
        }
    return False, {"plan": plan, "attempts": attempts,
                   "refusal": "endpoint_access_candidate_exhausted"}, \
        None, {}


def _attempt_alternate_placement_route_order(
        baseline_path, trial_path, snapshot_rows, target_row, move, *,
        work_dir, token, restoration_timeout_s):
    """Retry a moved cell with displaced copper scheduled before its target.

    A legal component seat can require one generated branch to move.  Routing
    the moved pad first and replaying that branch second gives the first net an
    accidental, order-dependent monopoly on the corridor.  Preserve the exact
    pre-target board, restore every displaced net there, and then reconnect the
    moved cell.  Only the composite board is published, and only when both
    phases close; the caller still applies whole-board DRC/connectivity gates.

    This is deliberately a two-order bounded transaction rather than an
    unbounded retry loop.  It generalizes negotiated routing to placement
    evacuation without granting authority over authored copper or weakening
    any final admission criterion.
    """

    alternate = os.path.join(
        work_dir, "footprint-%s-displaced-first.kicad_pcb" % token)
    _copy_board_family(baseline_path, alternate)
    evidence = {
        "schema": 1,
        "policy": "target_first_then_displaced_first",
        "alternate_board": os.path.basename(alternate),
    }
    try:
        restored, restoration = _spawn_apply(
            _restore_negotiation_worker,
            (alternate, snapshot_rows, 8.0, 2.0,
             "hardest_first", restoration_timeout_s),
            timeout_s=restoration_timeout_s + 3.0)
    except cec_process_pool.WorkerPoolStalled as exc:
        evidence.update({
            "accepted": False,
            "decision": "alternate_restoration_budget_exhausted",
            "restoration": {
                "refusal": "placement_restoration_budget_exhausted",
                "budget_s": restoration_timeout_s,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:400]),
            },
        })
        return False, evidence, None
    evidence["restoration"] = restoration
    if not restored:
        evidence.update({
            "accepted": False,
            "decision": "alternate_displaced_copper_unrestorable",
        })
        return False, evidence, None

    exact = _spawn_apply(
        _exact_relocated_connections_worker,
        (alternate, target_row, move, 35.0), timeout_s=40.0)
    evidence["exact_reconnect"] = exact
    if not exact.get("target_closed"):
        evidence.update({
            "accepted": False,
            "decision": "alternate_target_still_refused",
        })
        return False, evidence, exact

    _copy_board_family(alternate, trial_path)
    evidence.update({
        "accepted": True,
        "decision": "alternate_order_composite_closed",
    })
    return True, evidence, exact


def _attempt_footprint_relocation(board_path, before, target_row, *,
                                  work_dir, token, effort=None,
                                  max_candidates=8,
                                  skip_candidate_keys=(),
                                  stage_name="footprint_relocation",
                                  max_copper_pads=2,
                                  max_branch_tracks=12,
                                  generated_locked_uuids=(),
                                  candidate_override=None,
                                  allow_route_expansion=True):
    """Try one trapped-pin support-cell re-seat as an atomic transaction."""

    target = FootprintRepairTarget(**target_row)
    skipped = set(skip_candidate_keys or ())
    proposed_candidates = (
        list(candidate_override) if candidate_override is not None else
        _combined_footprint_relocation_candidates(board_path, target_row))
    candidates = [
        candidate for candidate in proposed_candidates
        if _footprint_candidate_key(target.ref, candidate) not in skipped
    ]
    rows = []
    target_closed_seen = False
    # ``max_candidates`` is a per-certified-target bound.  Sharing one effort
    # stage key across the outer target loop let the first difficult passive
    # consume the entire placement allowance and silently skipped every later
    # support cell.  The global attempt/wall budget still caps the full wave;
    # this key only keeps each target's finite ladder independent.
    effort_stage = "%s:%s" % (stage_name, token)
    for index, candidate in enumerate(candidates[:max(0, int(max_candidates))]):
        if effort is not None and not effort.claim(
                effort_stage, stage_limit=max_candidates):
            break
        trial = os.path.join(
            work_dir, "footprint-%s-%02d.kicad_pcb" % (token, index))
        _copy_board_family(board_path, trial)
        effective_target_row = dict(target_row)
        if candidate.get("mobility_companion_refs") is not None:
            effective_target_row["companion_refs"] = list(
                candidate.get("mobility_companion_refs") or ())
        effective_target = FootprintRepairTarget(**effective_target_row)
        candidate_started = time.monotonic()
        row = {"stage": stage_name, "target": effective_target_row,
               "candidate": candidate}

        def record_row():
            """Publish one pose with its complete transaction wall cost."""

            row["elapsed_s"] = round(
                max(0.0, time.monotonic() - candidate_started), 3)
            rows.append(row)

        try:
            changed, move = _spawn_apply(
                _relocate_footprint_worker,
                (trial, effective_target_row, candidate, max_branch_tracks,
                 max_copper_pads, tuple(generated_locked_uuids)),
                timeout_s=25.0)
            row["move"] = move
            if not changed:
                row.update({"accepted": False,
                            "decision": move.get("refusal")})
                record_row()
                continue
            if candidate.get("route_access_endpoint"):
                move["target_endpoint_override"] = dict(
                    candidate["route_access_endpoint"])
                move["target_access_path_uuids"] = list(
                    candidate.get("route_access_path_uuids") or ())

            # Reject a physically illegal pose before spending the majority
            # of the wave on target/support reconstruction.  Refill first so
            # adaptive zones get their normal chance to clear moved pads and
            # vias; what remains is a real placement/copper invariant, not a
            # stale fill artifact.  Connectivity is deliberately ignored by
            # this preflight because the transaction has just removed the
            # incident branches it is about to rebuild.
            _spawn_apply(_refill_worker, (trial,))
            preflight_drc_path = os.path.join(
                work_dir, "footprint-%s-%02d-preflight-drc.json" %
                (token, index))
            _run_drc(trial, preflight_drc_path)
            with open(preflight_drc_path, encoding="utf-8") as source:
                preflight_drc_data = json.load(source)
            row["placement_conflicts"] = _spawn_apply(
                _classify_placement_conflicts_worker,
                (trial, preflight_drc_data, effective_target_row, move,
                 tuple(generated_locked_uuids)), timeout_s=15.0)
            preflight_after = _spawn_apply(
                _score_worker, (trial, preflight_drc_path))
            preflight_ok, preflight_decision, preflight_faults = \
                _placement_preflight_accepts(before, preflight_after)
            row["placement_preflight"] = {
                "accepted": preflight_ok,
                "decision": preflight_decision,
                "new_faults": preflight_faults,
                "drc": preflight_after.get("drc"),
                "drc_types": preflight_after.get("drc_types"),
                "diffpair_ok": preflight_after.get("diffpair_ok"),
                "kelvin_ok": preflight_after.get("kelvin_ok"),
                "route_topology_fault_nets": preflight_after.get(
                    "route_topology_fault_nets"),
            }
            evacuation_snapshots = []
            if not preflight_ok:
                conflicts = row["placement_conflicts"]
                movable_tracks = tuple(
                    conflicts.get("movable_track_uuids") or ())
                # Exact policy-movable track branches are the cheapest local
                # degree of freedom and can be evacuated even when a via is
                # also named.  The via remains for the independent bounded
                # displacement stage below; stationary components, authored
                # copper, and zones still fail closed.
                if (not conflicts.get("fixed_conflict_count")
                        and movable_tracks):
                    evacuated, evacuation, evacuation_snapshots = \
                        _spawn_apply(
                            _evacuate_placement_copper_worker,
                            (trial, movable_tracks,
                             tuple(generated_locked_uuids)),
                            timeout_s=25.0)
                    row["placement_copper_evacuation"] = evacuation
                    if evacuated:
                        _spawn_apply(_refill_worker, (trial,))
                        post_drc_path = os.path.join(
                            work_dir,
                            "footprint-%s-%02d-post-evacuation-drc.json" %
                            (token, index))
                        _run_drc(trial, post_drc_path)
                        with open(post_drc_path, encoding="utf-8") as source:
                            post_drc_data = json.load(source)
                        post_conflicts = _spawn_apply(
                            _classify_placement_conflicts_worker,
                            (trial, post_drc_data, effective_target_row, move,
                             tuple(generated_locked_uuids)), timeout_s=15.0)
                        post_after = _spawn_apply(
                            _score_worker, (trial, post_drc_path))
                        preflight_ok, post_decision, post_faults = \
                            _placement_preflight_accepts(before, post_after)
                        row["placement_conflicts_after_evacuation"] = \
                            post_conflicts
                        conflicts = post_conflicts
                        row["placement_preflight_after_evacuation"] = {
                            "accepted": preflight_ok,
                            "decision": post_decision,
                            "new_faults": post_faults,
                            "drc": post_after.get("drc"),
                            "drc_types": post_after.get("drc_types"),
                        }
                        if not preflight_ok:
                            preflight_decision = post_decision
                if (not preflight_ok
                        and not conflicts.get("fixed_conflict_count")
                        and conflicts.get("movable_via_targets")):
                    via_changed, via_evidence, via_conflicts, move_patch = \
                        _attempt_placement_via_clearance(
                            trial, before, effective_target_row, move,
                            conflicts, work_dir=work_dir,
                            token="%s-%02d" % (token, index),
                            generated_locked_uuids=generated_locked_uuids,
                            max_candidates=8)
                    row["placement_via_clearance"] = via_evidence
                    if via_changed:
                        move.update(move_patch)
                        conflicts = via_conflicts
                        _spawn_apply(_refill_worker, (trial,))
                        post_via_drc_path = os.path.join(
                            work_dir,
                            "footprint-%s-%02d-post-via-drc.json" %
                            (token, index))
                        _run_drc(trial, post_via_drc_path)
                        post_via_after = _spawn_apply(
                            _score_worker, (trial, post_via_drc_path))
                        preflight_ok, post_via_decision, post_via_faults = \
                            _placement_preflight_accepts(
                                before, post_via_after)
                        row["placement_conflicts_after_via"] = conflicts
                        row["placement_preflight_after_via"] = {
                            "accepted": preflight_ok,
                            "decision": post_via_decision,
                            "new_faults": post_via_faults,
                            "drc": post_via_after.get("drc"),
                            "drc_types": post_via_after.get("drc_types"),
                        }
                        if not preflight_ok:
                            preflight_decision = post_via_decision
                if not preflight_ok:
                    row.update({"accepted": False,
                                "decision": preflight_decision})
                    record_row()
                    continue

            # The move certificate already owns the exact target endpoint and
            # every removed incident branch boundary.  Reconnect those pairs
            # before asking a whole-net island search to rediscover them.
            target_route_baseline = os.path.join(
                work_dir, "footprint-%s-%02d-pre-target.kicad_pcb" %
                (token, index))
            _copy_board_family(trial, target_route_baseline)
            exact_reconnect = _spawn_apply(
                _exact_relocated_connections_worker,
                (trial, effective_target_row, move, 35.0), timeout_s=40.0)
            row["exact_reconnect"] = exact_reconnect
            if not exact_reconnect.get("target_closed"):
                target_route_baseline = None
            target_report = exact_reconnect
            fallback_target_closed = False
            target_refusals = [
                item for item in exact_reconnect.get("refused") or ()
                if item.get("role") == "target"]
            if (not exact_reconnect.get("target_closed")
                    and any(item.get("refusal") in {
                        "certificate_endpoint_not_live",
                        "relocated_pair_pad_not_live",
                    } for item in target_refusals)):
                # Retain one bounded generic fallback only when the exact
                # endpoint identity could not be resolved.  If a current
                # binary pair was resolved and proved no clear path, a
                # whole-net search cannot repair that authoritative gap and
                # merely repeats unrelated island work.
                target_report = _spawn_apply(
                    _lastmile_worker,
                    (trial, (effective_target.target_net,), 12, 6.0),
                    timeout_s=25.0)
                fallback_target_closed = bool(target_report.get("closed"))
            if not (exact_reconnect.get("target_closed")
                    or fallback_target_closed):
                target_certificate = next((
                    (item.get("completion") or {}).get("certificate")
                    for item in target_refusals
                    if isinstance(
                        (item.get("completion") or {}).get(
                            "certificate"), dict)), None)
                route_authority = tuple(sorted({
                    *map(str, generated_locked_uuids),
                    *map(str, move.get(
                        "placement_generated_locked_uuids") or ()),
                }))
                route_blockers = _route_certificate_movable_track_uuids(
                    trial, target_certificate or {},
                    generated_locked_uuids=route_authority, limit=4)
                if route_blockers:
                    route_evacuated, route_evidence, route_snapshots = \
                        _spawn_apply(
                            _evacuate_placement_copper_worker,
                            (trial, tuple(route_blockers), route_authority),
                            timeout_s=25.0)
                    row["route_certificate_copper_evacuation"] = {
                        **route_evidence,
                        "certificate_blocker_uuids": route_blockers,
                    }
                    if route_evacuated:
                        evacuation_snapshots.extend(route_snapshots)
                        _spawn_apply(_refill_worker, (trial,))
                        target_route_baseline = os.path.join(
                            work_dir,
                            "footprint-%s-%02d-pre-target-route-evac.kicad_pcb" %
                            (token, index))
                        _copy_board_family(trial, target_route_baseline)
                        retry = _spawn_apply(
                            _exact_relocated_connections_worker,
                            (trial, effective_target_row, move, 35.0),
                            timeout_s=40.0)
                        row["exact_reconnect_after_route_evacuation"] = retry
                        exact_reconnect = retry
                        target_report = retry
                        if not retry.get("target_closed"):
                            target_route_baseline = None
                        target_refusals = [
                            item for item in retry.get("refused") or ()
                            if item.get("role") == "target"]
                if not exact_reconnect.get("target_closed"):
                    via_certificate = next((
                        (item.get("completion") or {}).get("certificate")
                        for item in target_refusals
                        if isinstance(
                            (item.get("completion") or {}).get(
                                "certificate"), dict)), None)
                    if via_certificate:
                        via_changed, via_evidence, via_retry, via_move = \
                            _attempt_route_certificate_via_clearance(
                                trial, before, effective_target_row, move,
                                via_certificate, work_dir=work_dir,
                                token="%s-%02d" % (token, index),
                                generated_locked_uuids=route_authority,
                                ownership_snapshot_rows=
                                    tuple(evacuation_snapshots),
                                max_vias=2, max_offsets=4)
                        row["route_certificate_via_clearance"] = \
                            via_evidence
                        if via_changed:
                            target_route_baseline = via_move.pop(
                                "target_route_baseline_path",
                                target_route_baseline)
                            move.update(via_move)
                            exact_reconnect = via_retry
                            target_report = via_retry
                            target_refusals = [
                                item for item in
                                via_retry.get("refused") or ()
                                if item.get("role") == "target"]
                if not exact_reconnect.get("target_closed"):
                    access_certificate = next((
                        (item.get("completion") or {}).get("certificate")
                        for item in target_refusals
                        if isinstance(
                            (item.get("completion") or {}).get(
                                "certificate"), dict)), None)
                    if access_certificate:
                        access_changed, access_evidence, access_retry, \
                            access_move = _attempt_target_endpoint_access(
                                trial, effective_target_row, move,
                                access_certificate, work_dir=work_dir,
                                token="%s-%02d" % (token, index),
                                max_candidates=6)
                        row["target_endpoint_access"] = access_evidence
                        if access_changed:
                            target_route_baseline = access_move.pop(
                                "target_route_baseline_path",
                                target_route_baseline)
                            move.update(access_move)
                            exact_reconnect = access_retry
                            target_report = access_retry
                            target_refusals = [
                                item for item in
                                access_retry.get("refused") or ()
                                if item.get("role") == "target"]
                if not exact_reconnect.get("target_closed"):
                    retreat_certificate = next((
                        (item.get("completion") or {}).get("certificate")
                        for item in target_refusals
                        if isinstance(
                            (item.get("completion") or {}).get(
                                "certificate"), dict)), None)
                    if retreat_certificate:
                        retreat_changed, retreat_evidence, retreat_retry, \
                            retreat_move = _attempt_target_endpoint_retreat(
                                trial, effective_target_row, move,
                                retreat_certificate, work_dir=work_dir,
                                token="%s-%02d" % (token, index),
                                generated_locked_uuids=route_authority,
                                max_candidates=4)
                        row["target_endpoint_retreat"] = retreat_evidence
                        if retreat_changed:
                            target_route_baseline = retreat_move.pop(
                                "target_route_baseline_path",
                                target_route_baseline)
                            move.update(retreat_move)
                            exact_reconnect = retreat_retry
                            target_report = retreat_retry
                            target_refusals = [
                                item for item in
                                retreat_retry.get("refused") or ()
                                if item.get("role") == "target"]
            row["target_completion"] = target_report
            if not (exact_reconnect.get("target_closed")
                    or fallback_target_closed):
                if allow_route_expansion:
                    target_certificate = next((
                        (item.get("completion") or {}).get("certificate")
                        for item in target_refusals
                        if isinstance(
                            (item.get("completion") or {}).get(
                                "certificate"), dict)), None)
                    route_blockers = _route_certificate_soft_obstacle_refs(
                        trial, target_certificate or {},
                        effective_target_row, limit=2)
                    available = max(
                        0, 4 - len(effective_target.companion_refs))
                    additions = [item["ref"] for item in route_blockers
                                 ][:available]
                    if additions:
                        expanded_target_row = dict(effective_target_row)
                        expanded_companions = tuple(sorted({
                            *map(str, effective_target.companion_refs),
                            *map(str, additions),
                        }))
                        expanded_target_row["companion_refs"] = list(
                            expanded_companions)
                        expanded_candidate = dict(candidate)
                        expanded_candidate["mobility_companion_refs"] = list(
                            expanded_companions)
                        expanded_candidate["generator"] = \
                            "route_certificate_mobility_graph"
                        expanded_candidate["route_blockers"] = route_blockers
                        expansion = _attempt_footprint_relocation(
                            board_path, before, expanded_target_row,
                            work_dir=work_dir,
                            token="%s-route-%02d" % (token, index),
                            effort=effort, max_candidates=1,
                            skip_candidate_keys=(),
                            stage_name=stage_name,
                            max_copper_pads=max_copper_pads,
                            max_branch_tracks=max_branch_tracks,
                            generated_locked_uuids=generated_locked_uuids,
                            candidate_override=(expanded_candidate,),
                            allow_route_expansion=False)
                        row["route_aware_expansion"] = expansion
                        if expansion.get("adopted"):
                            row.update({
                                "accepted": False,
                                "decision":
                                    "superseded_by_route_aware_expansion",
                            })
                            record_row()
                            return {
                                "adopted": True,
                                "after": expansion["after"],
                                "accepted": expansion["accepted"],
                                "attempts": rows + list(
                                    expansion.get("attempts") or ()),
                            }
                row.update({"accepted": False,
                            "decision": "target_still_refused"})
                record_row()
                if index >= 5 and not target_closed_seen:
                    break
                continue
            target_closed_seen = True

            if evacuation_snapshots:
                # Placement copper replay is speculative: the target seat has
                # closed, but the displaced branches may prove mutually
                # exclusive with it.  Do not let one such branch consume the
                # whole repair wave.  Atomic route negotiation already uses a
                # bounded replay allowance; apply the same breadth-first
                # discipline here and retain the exact timeout/refusal in the
                # candidate evidence.
                restoration_timeout_s = \
                    _placement_restoration_timeout_s(
                        len(evacuation_snapshots))
                row["placement_copper_restoration_budget_s"] = \
                    restoration_timeout_s
                try:
                    restored, restoration = _spawn_apply(
                        _restore_negotiation_worker,
                        (trial, evacuation_snapshots, 8.0, 2.0,
                         "hardest_first", restoration_timeout_s),
                        timeout_s=restoration_timeout_s + 3.0)
                except cec_process_pool.WorkerPoolStalled as exc:
                    # The child used its complete pose-local replay slice.
                    # Record that as topology/search evidence for this pose,
                    # rather than a generic transaction crash that the next
                    # wave would retry forever.  A worker timeout before this
                    # bounded stage is still handled by the outer exception
                    # and remains retryable after a global wall stop.
                    restoration = {
                        "schema": 1,
                        "refusal":
                            "placement_restoration_budget_exhausted",
                        "budget_s": restoration_timeout_s,
                        "error": "%s: %s" % (
                            type(exc).__name__, str(exc)[:400]),
                    }
                    row["placement_copper_restoration"] = restoration
                    row.update({
                        "accepted": False,
                        "decision":
                            "placement_copper_restoration_timeout",
                    })
                    record_row()
                    continue
                row["placement_copper_restoration"] = restoration
                if not restored:
                    if target_route_baseline:
                        alternate_restored, alternate_evidence, \
                            alternate_exact = \
                            _attempt_alternate_placement_route_order(
                                target_route_baseline, trial,
                                evacuation_snapshots,
                                effective_target_row, move,
                                work_dir=work_dir,
                                token="%s-%02d" % (token, index),
                                restoration_timeout_s=
                                restoration_timeout_s)
                        row["placement_route_order_negotiation"] = \
                            alternate_evidence
                        if alternate_restored:
                            restored = True
                            restoration = alternate_evidence.get(
                                "restoration") or restoration
                            exact_reconnect = alternate_exact
                            target_report = alternate_exact
                            row["placement_copper_restoration"] = \
                                restoration
                            row["target_completion"] = target_report
                    if not restored:
                        row.update({
                            "accepted": False,
                            "decision": "placement_copper_unrestorable",
                        })
                        record_row()
                        continue

            affected = _relocation_support_nets(
                move, effective_target.target_net)
            support_closed_nets = set(
                exact_reconnect.get("support_closed_nets") or ())
            if affected and not set(affected) <= support_closed_nets:
                # A moved bypass/filter/threshold part must re-establish its
                # ground return just as rigorously as its signal pin.  Skipping
                # GND merely traded the certified target open for a fresh
                # ground open; the whole-board scorer correctly rejected it.
                # The same exact last-mile/via guards and DRC admission apply
                # here, so this is not permission for an arbitrary ground
                # stitch.
                support_timeout_s = _support_completion_timeout_s(
                    len(affected), 24, 8.0)
                row["support_completion"] = _spawn_apply(
                    _lastmile_worker,
                    (trial, affected, 24, 8.0, False,
                     support_timeout_s),
                    timeout_s=min(300.0, support_timeout_s + 5.0))
            # One certificate identifies one missing component edge, not
            # necessarily the last island on that net.  After the exact moved
            # pad pair closes, finish the target net against the live board so
            # a multi-island rail is not rejected as "no improvement" merely
            # because a second gap remained outside the certificate window.
            target_finish_timeout_s = _support_completion_timeout_s(
                1, 24, 8.0)
            row["target_net_completion"] = _spawn_apply(
                _lastmile_worker,
                (trial, (effective_target.target_net,), 24, 8.0, True,
                 target_finish_timeout_s),
                timeout_s=min(300.0, target_finish_timeout_s + 5.0))
            normalized_pofv_uuids = tuple(move.get(
                "placement_pofv_normalized_via_uuids") or ())
            if normalized_pofv_uuids:
                pofv_refreshed, pofv_refresh = _spawn_apply(
                    _refresh_transaction_pofv_rule_worker,
                    (trial, normalized_pofv_uuids), timeout_s=20.0)
                row["transaction_pofv_rule_refresh"] = pofv_refresh
                if not pofv_refreshed:
                    row.update({
                        "accepted": False,
                        "decision": "transaction_pofv_rule_unavailable",
                    })
                    record_row()
                    continue
            _spawn_apply(_refill_worker, (trial,))

            drc_path = os.path.join(
                work_dir, "footprint-%s-%02d-drc.json" % (token, index))
            drc_data = _run_drc(trial, drc_path)
            pruned, prune = _spawn_apply(
                _prune_relocated_dangling_vias_worker,
                (trial, tuple(move.get("moved_pad_via_uuids") or ()),
                 drc_data))
            row["moved_via_prune"] = prune
            if pruned:
                _spawn_apply(_refill_worker, (trial,))
                drc_data = _run_drc(trial, drc_path)
            # Exact/support completion can leave superseded generated stubs
            # after the moved cell has been fully reconnected.  Do not reject
            # an otherwise improving composite for copper KiCad itself proves
            # is dangling; remove only those exact DRC UUIDs, refill, and
            # independently remeasure before admission.
            cleaned, cleanup = _spawn_dangling_cleanup(trial, 8)
            row["post_placement_dangling_cleanup"] = cleanup
            if cleaned:
                _spawn_apply(_refill_worker, (trial,))
                drc_data = _run_drc(trial, drc_path)
            after = _spawn_apply(_score_worker, (trial, drc_path))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            record_row()
            if not ok:
                continue
            _copy_board_family(trial, board_path)
            return {"adopted": True, "after": after,
                    "accepted": row, "attempts": rows}
        except Exception as exc:                         # noqa: BLE001
            row.update({"accepted": False,
                        "decision": "component_transaction_worker_error",
                        "error": "%s: %s" % (
                            type(exc).__name__, str(exc)[:600])})
            record_row()
    return {"adopted": False, "attempts": rows,
            "prior_candidates_skipped": len(skipped),
            "stop": (effort.stage_stop(
                effort_stage, "candidate_exhausted")
                if effort is not None else "candidate_exhausted")}


def _relocation_support_nets(move, target_net):
    """Return every non-target net a moved support cell must reconnect."""

    return tuple(sorted({
        str(net) for net in (move.get("affected_nets") or ())
        if net and str(net) != str(target_net)
    }))


def _new_generated_track_conflicts_worker(
        board_path, before, after, generated_locked_uuids=(),
        protected_nets=()):
    """Name generated locked tracks in newly introduced route DRCs.

    A useful via relocation can close a blocked net while touching one older
    pipeline-generated trunk.  Rejecting that intermediate state discards the
    only viable composite move; blindly accepting it merely swaps an open net
    for a clearance fault.  Extract only exact UUID identities which are new
    relative to the transaction baseline, then authorize only locked tracks
    proven absent from the authored board.  Vias, authored copper, protected
    target nets, mask faults, and identity-free diagnostics remain immutable.
    """

    old_identities = set(before.get("structural_drc_identities") or ())
    new_identities = sorted(
        set(after.get("structural_drc_identities") or ()) - old_identities)
    generated = {str(uid) for uid in generated_locked_uuids if uid}
    protected = {str(net) for net in protected_nets if net}
    board = pcbnew.LoadBoard(board_path)
    tracks = {
        _uuid(item): item for item in board.GetTracks()
        if item.GetClass() == "PCB_TRACK" and _uuid(item)
    }
    repairable_types = {"clearance", "shorting_items", "tracks_crossing"}
    selected = set()
    parsed = []
    for identity in new_identities:
        try:
            row = json.loads(identity) if isinstance(identity, str) else identity
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if (not isinstance(row, (list, tuple)) or len(row) < 3
                or str(row[0]) not in repairable_types
                or str(row[1]) != "uuid"
                or not isinstance(row[2], (list, tuple))):
            continue
        ids = tuple(sorted(str(uid) for uid in row[2] if uid))
        candidates = []
        for uid in ids:
            item = tracks.get(uid)
            if (item is None or uid not in generated or not item.IsLocked()
                    or str(item.GetNetname() or "") in protected):
                continue
            selected.add(uid)
            candidates.append(uid)
        parsed.append({"identity": identity, "type": str(row[0]),
                       "uuids": list(ids),
                       "generated_track_uuids": candidates})
    return {
        "schema": 1,
        "new_structural_drc_identities": new_identities,
        "repairable_identities": parsed,
        "generated_track_uuids": sorted(selected),
    }


def _attempt_congestion_via_relocation(
        board_path, before, target_row, *, work_dir, token,
        generated_locked_uuids=(), effort=None, max_candidates=8):
    """Move one refusal-named via, then close and score the blocked net."""

    via_row = dict(target_row["via"])
    target = ViaRepairTarget(**via_row)
    rows = []
    # A refusal vector says where congestion wants the barrel to move; its
    # incident stubs say which motions remain electrically cheap.  Interleave
    # both constraints so a small candidate budget samples reachable angular
    # alternatives instead of exhausting seven radii in one direction that no
    # owning branch can follow.
    owner_directions = tuple(
        tuple(int(value) for value in row)
        for row in target_row.get("owner_directions") or ())
    offsets = list(_congestion_via_offset_candidates(
        target, owner_directions=owner_directions))[
            :max(0, int(max_candidates))]
    for index, (dx_nm, dy_nm, step_mm, direction) in enumerate(offsets):
        if effort is not None and not effort.claim(
                "congestion_via_relocation", stage_limit=max_candidates):
            break
        trial = os.path.join(
            work_dir, "congestion-via-%s-%02d.kicad_pcb" % (token, index))
        _copy_board_family(board_path, trial)
        row = {
            "stage": "congestion_via_relocation", "target": target_row,
            "step_mm": step_mm, "direction": list(direction),
        }
        try:
            changed, move = _spawn_apply(
                _relocate_via_worker,
                (trial, via_row, dx_nm, dy_nm,
                 tuple(generated_locked_uuids)), timeout_s=20.0)
            row["move"] = move
            if not changed:
                row.update({"accepted": False,
                            "decision": move.get("refusal")})
                rows.append(row)
                continue
            completion = _spawn_apply(
                _lastmile_worker,
                (trial, (target_row["target_net"],), 24, 8.0, True),
                timeout_s=25.0)
            row["target_completion"] = completion
            if not completion.get("closed"):
                row.update({"accepted": False,
                            "decision": "target_still_refused"})
                rows.append(row)
                continue
            _spawn_apply(_refill_worker, (trial,))
            drc_path = os.path.join(
                work_dir, "congestion-via-%s-%02d-drc.json" %
                (token, index))
            _run_drc(trial, drc_path)
            after = _spawn_apply(_score_worker, (trial, drc_path))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            if (not ok and int(after.get("unconnected") or 0)
                    < int(before.get("unconnected") or 0)):
                collateral = _spawn_apply(
                    _new_generated_track_conflicts_worker,
                    (trial, before, after, tuple(generated_locked_uuids),
                     (target_row["target_net"],)))
                recovery = {"classification": collateral,
                            "attempted": False}
                row["generated_track_recovery"] = recovery
                conflict_uuids = tuple(
                    collateral.get("generated_track_uuids") or ())
                if conflict_uuids:
                    recovery["attempted"] = True
                    removed, removal, snapshots = _spawn_apply(
                        _evacuate_placement_copper_worker,
                        (trial, conflict_uuids,
                         tuple(generated_locked_uuids)), timeout_s=20.0)
                    recovery["removal"] = removal
                    recovery["removed"] = bool(removed)
                    if removed:
                        restored, restoration = _spawn_apply(
                            _restore_negotiation_worker,
                            (trial, snapshots, 2.0, 5.0,
                             "hardest_first", 45.0), timeout_s=50.0)
                        recovery["restoration"] = restoration
                        recovery["restored"] = bool(restored)
                        if restored:
                            _spawn_apply(_refill_worker, (trial,))
                            composite_drc_path = os.path.join(
                                work_dir,
                                "congestion-via-%s-%02d-composite-drc.json" %
                                (token, index))
                            _run_drc(trial, composite_drc_path)
                            composite_after = _spawn_apply(
                                _score_worker, (trial, composite_drc_path))
                            composite_ok, composite_decision = _accepts(
                                before, composite_after)
                            recovery.update({
                                "after": composite_after,
                                "accepted": composite_ok,
                                "decision": composite_decision,
                            })
                            row.update({
                                "after": composite_after,
                                "accepted": composite_ok,
                                "decision": (
                                    "composite_" + composite_decision),
                            })
                            after = composite_after
                            ok = composite_ok
            rows.append(row)
            if not ok:
                continue
            _copy_board_family(trial, board_path)
            return {"adopted": True, "after": after,
                    "accepted": row, "attempts": rows}
        except Exception as exc:                         # noqa: BLE001
            row.update({
                "accepted": False,
                "decision": "via_transaction_worker_error",
                "error": "%s: %s" % (
                    type(exc).__name__, str(exc)[:600]),
            })
            rows.append(row)
    return {
        "adopted": False, "attempts": rows,
        "stop": (effort.stage_stop(
            "congestion_via_relocation", "candidate_exhausted")
            if effort is not None else "candidate_exhausted"),
    }


def _atomic_negotiation_timeout_s(attempt_budget, margin):
    """Return the bounded child allowance for one atomic close search.

    The coordinator supplies ``CEC_CERTIFICATE_WORKER_TIMEOUT_S`` from the
    transaction wall budget.  Do not silently replace that allowance with the
    historical 25/45-second constants: dense but legal mazes routinely need
    longer, and killing them early only makes the outer wave spin through
    equivalent candidates.  A dedicated override remains available for
    profiling, while the parent deadline in :func:`_spawn_apply` is always the
    final cap.
    """

    legacy_floor = 45.0 if (attempt_budget > 12 or margin >= 12.0) else 25.0
    raw = os.environ.get(
        "CEC_CERTIFICATE_NEGOTIATION_TIMEOUT_S",
        os.environ.get("CEC_CERTIFICATE_WORKER_TIMEOUT_S", "90"))
    try:
        configured = float(raw)
    except (TypeError, ValueError):
        configured = 90.0
    return max(legacy_floor, min(300.0, max(1.0, configured)))


def _atomic_close_timeout_s(attempt_budget, margin):
    """Bound one target search so a window cannot starve its siblings.

    Atomic negotiation contains several independently useful windows.  Its
    outer transaction allowance is intentionally generous enough for close,
    restoration, DRC, and scoring, but using that entire allowance for the
    first target maze prevents every later certificate from being tried.  A
    local close gets a smaller deterministic allowance; broad/deep variants
    retain a larger floor.  Timeout remains a refusal with exact evidence.
    """

    raw = os.environ.get("CEC_CERTIFICATE_NEGOTIATION_CLOSE_TIMEOUT_S", "25")
    try:
        configured = max(1.0, float(raw))
    except (TypeError, ValueError):
        configured = 25.0
    floor = 45.0 if (attempt_budget > 12 or margin >= 12.0) else 25.0
    return min(_atomic_negotiation_timeout_s(attempt_budget, margin),
               max(floor, configured))


def _live_probe_budget_s(wall_budget_s, configured_timeout_s,
                         negotiation_timeout_s):
    """Reserve the majority of a repair wave for actual transactions.

    The live probe is freshness evidence, not the repair itself. Giving it
    the historical 60-second default inside a 60-second certificate wave let
    one difficult but already-certified net consume the whole transaction at
    attempt zero. Bound the probe to one fifth of the caller's finite wall
    budget (with a useful 4-second floor), while still honoring both explicit
    probe and worker ceilings. A timeout is safe: the coordinator already
    filters and falls back to caller-supplied certificates for currently open
    nets.
    """

    wall = max(1.0, float(wall_budget_s))
    reserve_bound = max(4.0, wall * 0.20)
    return max(1.0, min(float(configured_timeout_s),
                        float(negotiation_timeout_s), reserve_bound))


def _support_completion_timeout_s(net_count, attempt_budget, margin):
    """Scale a moved-cell support repair to the number of incident nets.

    Endpoint-owner motion is intentionally the broadest fallback in this
    pipeline.  Once the certified target pin closes, every other net touched
    by the moved footprint is repaired in one transaction.  The historical
    60-second cap treated that multi-net sweep like a single target search and
    killed otherwise valid controller re-seats before KiCad could return a
    score.  Preserve the configured worker ceiling, scale the allowance only
    with the finite incident-net count, and leave the coordinator's global
    deadline as the final bound.
    """

    configured = _atomic_negotiation_timeout_s(attempt_budget, margin)
    scaled = 30.0 + 25.0 * max(1, int(net_count))
    return min(300.0, max(configured, scaled))


def _placement_restoration_timeout_s(snapshot_count):
    """Bound replay for one speculative component seat.

    A placement candidate can close its named target while making one of the
    copper branches evacuated from that seat impossible to restore.  Those
    failures are common topology evidence, not a reason to spend the entire
    wave proving one pose.  Scale modestly for a larger displaced branch set,
    but cap the default slice so later certified components are still tried.
    The override is intentionally separate from atomic route negotiation: a
    user may profile broad route windows without turning every placement pose
    into another full-wave search.
    """

    raw = os.environ.get(
        "CEC_CERTIFICATE_PLACEMENT_RESTORE_TIMEOUT_S", "25")
    try:
        configured = max(1.0, float(raw))
    except (TypeError, ValueError):
        configured = 25.0
    complexity_floor = min(
        45.0, 15.0 + 2.0 * max(1, int(snapshot_count)))
    return min(90.0, max(configured, complexity_floor))


def _atomic_negotiation_variants(window: NegotiationWindow, deep_retry: bool):
    """Return a bounded least-invasive-first topology portfolio."""

    bridge_candidate = bool(window.local_pin_escape)
    variants = [(12, 4.0, 2, False)]
    if bridge_candidate:
        variants.append((12, 4.0, 2, True))
    if deep_retry:
        breadth_margin = min(
            20.0, max(8.0, round(float(window.distance_mm) * 0.55, 1)))
        variants.append((1, breadth_margin, 4, bridge_candidate))
        board_scale_margin = min(
            25.0, max(12.0, round(float(window.distance_mm) + 8.0, 1)))
        variants.append((4, board_scale_margin, 4, bridge_candidate))
    return variants


def _attempt_atomic_negotiation(board_path, before, window_row, *,
                                work_dir, token, deep_retry,
                                max_detour_ratio, effort=None,
                                effort_stage="negotiation_cycle",
                                effort_stage_limit=12):
    """Try one certificate window as an all-or-nothing transaction.

    This helper deliberately owns no outer retry policy.  It either publishes
    one strictly admissible board back to ``board_path`` or returns the exact
    refusal rows for the caller's bounded negotiation sweep.
    """

    window = NegotiationWindow(**window_row)
    # Claim the least-invasive topology first.  A local pin-escape certificate
    # says that a bridge is worth enumerating; it does not prove that a new
    # through-via is preferable.  In particular, once certified blockers have
    # been removed, an existing multilayer anchor may expose a trivial route on
    # the endpoint's own copper layer.  Trying a bridge first can spend the
    # whole bounded slice looking for a legal barrel through unrelated inner
    # layers and prevent that surface route from ever running.
    # Preserve the inverse topology as a separate finite transaction.  This is
    # useful when the surface route would occupy the only restoration corridor
    # available to a displaced neighbour.  Deep variants retain the existing
    # bounded breadth escalation without creating an unbounded retry loop.
    variants = _atomic_negotiation_variants(window, deep_retry)
    rows = []
    base_topology_count = 2 if window.local_pin_escape else 1
    target_closed_but_unrestorable = False
    for variant, (attempt_budget, margin, branch_hops,
                  prefer_bridge) in enumerate(variants):
        # Once the bounded surface and inverse-bridge topologies can both close
        # the target but cannot restore their displaced nets, a wider target
        # maze is the wrong degree of freedom.  Preserve the refusal evidence
        # and escalate to the independently bounded via/owner stages.
        if (variant >= base_topology_count
                and target_closed_but_unrestorable):
            break
        if (effort is not None and not effort.claim(
                effort_stage, stage_limit=effort_stage_limit)):
            break
        trial = os.path.join(
            work_dir, "negotiate-%s-%02d.kicad_pcb" % (token, variant))
        _copy_board_family(board_path, trial)
        row = {
            "stage": "atomic_negotiation",
            "window": asdict(window),
            "variant": variant,
            "attempts_per_pair": attempt_budget,
            "maze_margin_mm": margin,
            "branch_hops": branch_hops,
            "target_topology": ("bridge_first" if prefer_bridge
                                else "surface_first"),
            "phases": {},
        }
        try:
            removed, remove_evidence, snapshots = _spawn_apply(
                _remove_negotiation_worker,
                (trial, window_row, branch_hops))
            row["phases"]["remove"] = remove_evidence
            if not removed:
                row.update({"accepted": False,
                            "decision": remove_evidence.get("refusal")})
                rows.append(row)
                continue
            close_timeout_s = _atomic_close_timeout_s(
                attempt_budget, margin)
            closed, close_evidence = _spawn_apply(
                _close_negotiation_worker,
                (trial, window_row, attempt_budget, margin,
                 prefer_bridge, max(1.0, close_timeout_s - 2.0)),
                timeout_s=close_timeout_s)
            row["phases"]["close"] = close_evidence
            if not closed:
                close_timed_out = bool(
                    (close_evidence.get("completion") or {}).get(
                        "timed_out"))
                row.update({
                    "accepted": False,
                    "decision": ("blocked_net_search_timeout"
                                 if close_timed_out else
                                 close_evidence.get("refusal")),
                })
                rows.append(row)
                # A timeout says this search domain exhausted its compute
                # slice, not that a still broader version should immediately
                # monopolize the same wave.  Move to the next independently
                # certified window; deep variants remain available when a
                # finite search returns an actual geometric refusal.
                inverse_topology_pending = any(
                    later[:3] == (attempt_budget, margin, branch_hops)
                    and bool(later[3]) != bool(prefer_bridge)
                    for later in variants[variant + 1:])
                if close_timed_out and not inverse_topology_pending:
                    break
                continue

            # A displaced branch can be geometrically unrestorable while
            # already being electrically redundant through zones or alternate
            # same-net copper.  The old transaction required geometric
            # restoration unconditionally and therefore threw away proven
            # target closures before the connectivity scorer could decide
            # whether the removed branch still mattered.  Score an isolated
            # copy first.  It may be published only when the ordinary strict
            # contract proves fewer opens/DRCs, no new debt identities, and no
            # topology regression; otherwise the original trial continues to
            # mandatory blocker restoration below.
            pruned_trial = os.path.join(
                work_dir,
                "negotiate-%s-%02d-pruned.kicad_pcb" % (token, variant))
            _copy_board_family(trial, pruned_trial)
            prune_evidence = {"attempted": True, "accepted": False}
            prune_stage = "refill"
            try:
                try:
                    _spawn_apply(_refill_worker, (pruned_trial,))
                except Exception as exc:             # noqa: BLE001
                    prune_evidence["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                prune_stage = "dangling_cleanup"
                cleaned, cleanup_evidence = _spawn_dangling_cleanup(
                    pruned_trial, 8)
                prune_evidence["dangling_cleanup"] = cleanup_evidence
                if cleaned:
                    try:
                        _spawn_apply(_refill_worker, (pruned_trial,))
                    except Exception as exc:         # noqa: BLE001
                        prune_evidence["cleanup_refill_warning"] = \
                            "%s: %s" % (type(exc).__name__, exc)
                prune_stage = "independent_drc"
                prune_drc = os.path.join(
                    work_dir,
                    "negotiate-%s-%02d-pruned-drc.json" %
                    (token, variant))
                _run_drc(pruned_trial, prune_drc)
                prune_stage = "full_board_score"
                pruned_after = _spawn_apply(
                    _score_worker, (pruned_trial, prune_drc))
                prune_stage = "strict_admission"
                prune_ok, prune_decision = _accepts(before, pruned_after)
                prune_evidence.update({
                    "after": pruned_after,
                    "accepted": prune_ok,
                    "decision": prune_decision,
                })
            except Exception as exc:                 # noqa: BLE001
                prune_ok = False
                prune_evidence.update({
                    "decision": "pruned_candidate_worker_error",
                    "failure_stage": prune_stage,
                    "error": "%s: %s" %
                             (type(exc).__name__, str(exc)[:400]),
                })
            row["phases"]["redundant_blocker_prune"] = prune_evidence
            if prune_ok:
                row.update({"after": pruned_after, "accepted": True,
                            "decision": prune_decision})
                rows.append(row)
                _copy_board_family(pruned_trial, board_path)
                return {
                    "adopted": True,
                    "after": pruned_after,
                    "accepted": row,
                    "attempts": rows,
                }

            # Restoration order is a real routing variable: the first branch
            # claims copper that every later branch must avoid.  Preserve the
            # target-only state and try one deterministic alternate ordering
            # when the historical widest/longest-first order fails.  The
            # search remains bounded at two orders; each result is reported,
            # and neither can bypass the full-board admission below.
            restore_seed = os.path.join(
                work_dir,
                "negotiate-%s-%02d-restore-seed.kicad_pcb" %
                (token, variant))
            _copy_board_family(trial, restore_seed)
            restore_attempts = []
            restored = False
            restore_evidence = {}
            try:
                restore_timeout_s = max(1.0, float(os.environ.get(
                    "CEC_CERTIFICATE_RESTORE_TIMEOUT_S", "20")))
            except (TypeError, ValueError):
                restore_timeout_s = 20.0
            # A replay transaction may coalesce several removed fragments into
            # one live net.  Scale the bounded allowance with that actual
            # branch frontier; the former fixed 20 seconds repeatedly closed
            # three of four branches and discarded the complete target route.
            restore_timeout_s = min(
                90.0, max(restore_timeout_s,
                          15.0 + 6.0 * max(1, len(snapshots))))
            for restore_index, order_mode in enumerate(
                    ("hardest_first", "easiest_first")):
                if restore_index:
                    _copy_board_family(restore_seed, trial)
                restored, restore_evidence = _spawn_apply(
                    _restore_negotiation_worker,
                    (trial, snapshots, margin, max_detour_ratio,
                     order_mode, restore_timeout_s),
                    timeout_s=restore_timeout_s + 2.0)
                restore_attempts.append(dict(restore_evidence))
                if restored:
                    break
            row["phases"]["restore_attempts"] = restore_attempts
            row["phases"]["restore"] = restore_evidence
            if not restored:
                # Exact branch replay can fail even though the displaced nets
                # remain ordinary routable islands.  Give those nets one
                # target-first completion pass from the partially restored
                # transaction, then let the whole-board monotonic scorer—not
                # branch-shape identity—decide whether the composite is valid.
                network_exhausted_nets = {
                    str(item.get("net") or "")
                    for item in restore_evidence.get("restored") or ()
                    if item.get("refusal") in {
                        "displaced_net_unrestorable",
                        "displaced_net_restore_timeout",
                    }
                }
                displaced_nets = tuple(sorted({
                    str(snapshot.get("net") or "")
                    for snapshot in snapshots
                    if snapshot.get("net")
                    and str(snapshot.get("net")) != window.net
                    and str(snapshot.get("net"))
                    not in network_exhausted_nets
                }))
                fallback = {
                    "attempted": bool(displaced_nets),
                    "nets": list(displaced_nets),
                    "network_exhausted_nets": sorted(
                        network_exhausted_nets),
                    "accepted": False,
                }
                if displaced_nets:
                    fallback_stage = "completion"
                    try:
                        fallback_margin = max(12.0, float(margin))
                        fallback_report = _spawn_apply(
                            _lastmile_worker,
                            (trial, displaced_nets, 32,
                             fallback_margin, True),
                            timeout_s=_atomic_negotiation_timeout_s(
                                32, fallback_margin))
                        fallback["completion"] = fallback_report
                        fallback_stage = "refill"
                        try:
                            _spawn_apply(_refill_worker, (trial,))
                        except Exception as exc:     # noqa: BLE001
                            fallback["refill_warning"] = "%s: %s" % (
                                type(exc).__name__, exc)
                        fallback_stage = "dangling_cleanup"
                        cleaned, cleanup_evidence = \
                            _spawn_dangling_cleanup(trial, 8)
                        fallback["dangling_cleanup"] = cleanup_evidence
                        if cleaned:
                            try:
                                _spawn_apply(_refill_worker, (trial,))
                            except Exception as exc: # noqa: BLE001
                                fallback["cleanup_refill_warning"] = \
                                    "%s: %s" % (type(exc).__name__, exc)
                        fallback_stage = "independent_drc"
                        fallback_drc = os.path.join(
                            work_dir,
                            "negotiate-%s-%02d-displaced-drc.json" %
                            (token, variant))
                        _run_drc(trial, fallback_drc)
                        fallback_stage = "full_board_score"
                        fallback_after = _spawn_apply(
                            _score_worker, (trial, fallback_drc))
                        fallback_stage = "strict_admission"
                        fallback_ok, fallback_decision = _accepts(
                            before, fallback_after)
                        fallback.update({
                            "after": fallback_after,
                            "accepted": fallback_ok,
                            "decision": fallback_decision,
                        })
                    except Exception as exc:         # noqa: BLE001
                        fallback_ok = False
                        fallback.update({
                            "decision": "displaced_completion_worker_error",
                            "failure_stage": fallback_stage,
                            "error": "%s: %s" %
                                     (type(exc).__name__, str(exc)[:400]),
                        })
                else:
                    fallback_ok = False
                    fallback["decision"] = "no_displaced_nets"
                row["phases"]["displaced_net_completion"] = fallback
                if fallback_ok:
                    row.update({
                        "after": fallback_after,
                        "accepted": True,
                        "decision": fallback_decision,
                    })
                    rows.append(row)
                    _copy_board_family(trial, board_path)
                    return {
                        "adopted": True,
                        "after": fallback_after,
                        "accepted": row,
                        "attempts": rows,
                    }
                row.update({"accepted": False,
                            "decision": restore_evidence.get("refusal")})
                rows.append(row)
                target_closed_but_unrestorable = True
                continue
            try:
                _spawn_apply(_refill_worker, (trial,))
            except Exception as exc:                 # noqa: BLE001
                row["refill_warning"] = "%s: %s" % (
                    type(exc).__name__, exc)
            cleaned, cleanup_evidence = _spawn_dangling_cleanup(trial, 8)
            row["phases"]["dangling_cleanup"] = cleanup_evidence
            if cleaned:
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:             # noqa: BLE001
                    row["cleanup_refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
        except Exception as exc:                     # noqa: BLE001
            row.update({
                "accepted": False,
                "decision": "worker_error",
                "error": "%s: %s" %
                         (type(exc).__name__, str(exc)[:400]),
            })
            rows.append(row)
            continue

        trial_drc = os.path.join(
            work_dir, "negotiate-%s-%02d-drc.json" % (token, variant))
        _run_drc(trial, trial_drc)
        after = _spawn_apply(_score_worker, (trial, trial_drc))
        ok, decision = _accepts(before, after)
        row.update({"after": after, "accepted": ok,
                    "decision": decision})
        rows.append(row)
        if ok:
            _copy_board_family(trial, board_path)
            return {
                "adopted": True,
                "after": after,
                "accepted": row,
                "attempts": rows,
            }
        # Once a complete transaction was scored, a broader geometric retry
        # must not churn on the same debt swap or hard-gate regression.
        break
    return {"adopted": False, "attempts": rows}


def _prioritize_windows_by_proven_close(windows, prior_report):
    """Order current certificates using only prior search-cost evidence.

    Geometry and authority always come from the freshly measured windows.
    Prior attempts may influence scheduling, never eligibility: a net whose
    target closure previously succeeded is cheap/high-value, while a target
    that exhausted its bounded search moves behind untried work.  This keeps
    unattended waves from repeating expensive first-net timeouts and lets a
    later full-board transaction reach restoration and scoring.
    """

    proven = set()
    timed_out = set()
    exhausted = set()

    def absorb_schedule(value):
        if isinstance(value, dict):
            if value.get("policy") == \
                    "proven_close_then_untried_then_prior_timeout":
                proven.update(str(net) for net in
                              value.get("proven_close_nets") or () if net)
                timed_out.update(str(net) for net in
                                 value.get("timed_out_nets") or () if net)
                exhausted.update(str(net) for net in
                                 value.get("exhausted_nets") or () if net)
            for child in value.values():
                absorb_schedule(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                absorb_schedule(child)

    prior_revision = str(
        (prior_report or {}).get("algorithm_revision") or "")
    if prior_revision == REPAIR_ALGORITHM_REVISION:
        # Carry search-cost evidence only across the exact same algorithm.
        # A new route-family scheduler or layer policy invalidates an older
        # ``timed_out`` plateau: treating it as current skipped routing and
        # sent an unchanged board straight back into placement.  Likewise,
        # inherited evidence must identify the revision that measured it;
        # merely being nested in a newer placement-only report is not proof.
        carried = ((((prior_report or {}).get("plan") or {}).get(
            "negotiation") or {}).get("prior_schedule_evidence") or {})
        if str(carried.get("algorithm_revision") or "") == \
                REPAIR_ALGORITHM_REVISION:
            absorb_schedule(carried)
        terminal_variants = {}
        retryable_nets = set()
        for row in (prior_report or {}).get("attempts") or ():
            if row.get("stage") != "atomic_negotiation":
                continue
            net = str((row.get("window") or {}).get("net") or "")
            if not net:
                continue
            completion = ((row.get("phases") or {}).get("close") or {}).get(
                "completion") or {}
            if int(completion.get("closed") or 0) > 0:
                proven.add(net)
            if (row.get("decision") == "blocked_net_search_timeout"
                    or completion.get("timed_out")):
                timed_out.add(net)
                retryable_nets.add(net)
            elif row.get("decision") == "worker_error":
                retryable_nets.add(net)
            elif (int(completion.get("closed") or 0) == 0
                  and row.get("decision") in {
                      "blocked_net_still_refused",
                      "blocked_net_unroutable",
                      "blocked_net_search_exhausted",
                  }):
                terminal_variants.setdefault(net, set()).add(
                    int(row.get("variant") or 0))
        negotiation_stop = ((((prior_report or {}).get("plan") or {}).get(
            "negotiation_sweep") or {}).get("stop"))
        if negotiation_stop == "no_admissible_negotiation":
            # Two or more distinct finite topologies that all return an exact
            # geometric refusal constitute a route plateau for this algorithm
            # revision. A timeout/worker error remains retryable and therefore
            # cannot authorize placement escalation.
            exhausted.update(
                net for net, variants in terminal_variants.items()
                if len(variants) >= 2 and net not in retryable_nets)
    rows = list(windows or ())
    rows.sort(key=lambda row: (
        0 if str(row.get("net") or "") in proven else
        2 if str(row.get("net") or "") in (timed_out | exhausted) else 1,
        tuple(row.get("priority") or ()),
        str(row.get("net") or ""),
    ))
    return rows, {
        "algorithm_revision": REPAIR_ALGORITHM_REVISION,
        "proven_close_nets": sorted(proven),
        "timed_out_nets": sorted(timed_out - proven),
        "exhausted_nets": sorted(exhausted - proven),
        "policy": "proven_close_then_untried_then_prior_timeout",
    }


def repair_board(board_path: str, out_path: str, completion: dict | None, *,
                 max_targets: int = 4, close_blocked_nets: bool = True,
                 negotiate: bool = True, max_windows: int = 8,
                 max_blockers_per_window: int = 2,
                 max_detour_ratio: float = 2.0,
                 deep_retry: bool = True,
                 max_attempts: int = 64,
                 wall_budget_s: float = 240.0,
                 lastmile_attempts: tuple[int, ...] = (8, 16),
                 lastmile_margins: tuple[float, ...] = (4.0, 8.0),
                 authored_baseline: str | None = None,
                 verbose: bool = False) -> dict:
    """Run the guarded repair ladder and write the best accepted artifact."""

    started = time.monotonic()
    work = tempfile.mkdtemp(prefix="cec_cert_repair_")
    attempts = []
    effort = RepairEffortBudget(
        max_attempts=max_attempts, wall_budget_s=wall_budget_s,
        started=started)
    deadline_token = _WORKER_DEADLINE.set(
        started + max(0.0, float(wall_budget_s)))
    try:
        current = os.path.join(work, "current.kicad_pcb")
        _copy_board_family(board_path, current)
        drc_path = os.path.join(work, "baseline-drc.json")
        drc_data = _run_drc(current, drc_path)
        generated_locked_uuids = _spawn_apply(
            _generated_locked_route_uuids,
            (current, authored_baseline))
        before = _spawn_apply(_score_worker, (current, drc_path))
        baseline = dict(before)
        accepted = []
        # Both the open-net list and the blocker geometry must come from the
        # exact current board.  A historical oracle is useful provenance, but
        # its nested certificates become stale after the first accepted move.
        # Probe in an isolated worker: any plausible copper it draws dies with
        # that process, while its exact refusal coordinates feed the planners.
        live_open_nets = tuple(before.get("unconn_nets") or ())
        certified_nets = {
            str((row.get("certificate") or {}).get("net") or
                (row.get("detail") or {}).get("net") or "")
            for row in refusal_certificates(completion)}
        certified_nets.discard("")
        live_probe_nets = tuple(
            net for net in live_open_nets if net in certified_nets)
        if not live_probe_nets:
            live_probe_nets = live_open_nets
        try:
            live_probe_timeout_s = max(1.0, float(os.environ.get(
                "CEC_CERTIFICATE_LIVE_PROBE_TIMEOUT_S", "60")))
        except (TypeError, ValueError):
            live_probe_timeout_s = 60.0
        live_probe_failed = False
        live_probe_trial = os.path.join(work, "live-probe.kicad_pcb")
        _copy_board_family(current, live_probe_trial)
        prior_planning_evidence = ((completion or {}).get("plan") or {}).get(
            "planning_refusal_evidence") or {}
        prior_output = str((completion or {}).get("output") or "")
        reuse_prior_evidence = bool(
            isinstance(completion, dict)
            and not completion.get("changed")
            and prior_output
            and os.path.abspath(prior_output) == os.path.abspath(board_path)
            and prior_planning_evidence.get("refused_details"))
        if reuse_prior_evidence:
            # An unchanged predecessor's output is byte-for-byte the board now
            # supplied as input.  Its live-filtered planning evidence is
            # therefore current; replaying the all-open-net probe only burns
            # the next bounded slice on the same timeout.
            live_probe_failed = True
            live_probe = {
                "schema": 1, "reused_prior_evidence": True,
                "fallback": "unchanged_predecessor_planning_evidence",
                "refused_details": [],
            }
        else:
            try:
                live_probe_budget_s = _live_probe_budget_s(
                    wall_budget_s, live_probe_timeout_s,
                    _atomic_negotiation_timeout_s(24, 8.0))
                live_probe = _spawn_apply(
                    _live_refusal_probe_worker,
                    (live_probe_trial, live_probe_nets, 24, 8.0),
                    timeout_s=live_probe_budget_s)
            except Exception as exc:                     # noqa: BLE001
                # A live all-open-net probe is freshness evidence, not the only
                # source of repair authority.  Dense boards can exhaust this
                # bounded diagnostic before planning starts; aborting the
                # entire transaction at attempt zero discards a caller-supplied
                # refusal certificate that may still name live component UUIDs.
                live_probe_failed = True
                live_probe = {
                    "schema": 1,
                    "error": "%s: %s" % (
                        type(exc).__name__, str(exc)[:800]),
                    "fallback": "supplied_certificate_filtered_by_live_opens",
                    "refused_details": [],
                }
        if not live_probe_failed and int(live_probe.get("closed") or 0) > 0:
            row = {
                "stage": "live_probe_promotion",
                "completion": live_probe,
            }
            try:
                _spawn_apply(_refill_worker, (live_probe_trial,))
            except Exception as exc:                     # noqa: BLE001
                row["refill_warning"] = "%s: %s" % (
                    type(exc).__name__, str(exc))
            live_probe_drc_path = os.path.join(
                work, "live-probe-drc.json")
            live_probe_drc = _run_drc(
                live_probe_trial, live_probe_drc_path)
            after = _spawn_apply(
                _score_worker, (live_probe_trial, live_probe_drc_path))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            attempts.append(row)
            live_probe["promotion"] = {
                "accepted": bool(ok), "decision": decision,
                "after_drc": after.get("drc"),
                "after_unconnected": after.get("unconnected"),
            }
            if ok:
                _copy_board_family(live_probe_trial, current)
                before = after
                drc_data = live_probe_drc
                accepted.append(row)
        planning_completion = _planning_completion_with_live_report(
            completion, before.get("unconn_nets") or (),
            None if live_probe_failed else live_probe)
        plan = _spawn_apply(
            _plan_worker,
            (current, planning_completion, drc_data, max_targets))
        negotiation_plan = _spawn_apply(
            _negotiation_plan_worker,
            (current, planning_completion, max_windows,
             max_blockers_per_window, generated_locked_uuids))
        # The worker planned against an isolated scratch copy.  Publish the
        # stable caller-visible identity, not a path removed in ``finally``.
        plan["board"] = os.path.abspath(board_path)
        negotiation_plan["board"] = os.path.abspath(board_path)
        _scheduled_windows, prior_schedule_evidence = \
            _prioritize_windows_by_proven_close(
                negotiation_plan.get("windows") or (), completion)
        negotiation_plan["prior_schedule_evidence"] = \
            prior_schedule_evidence
        plan["negotiation"] = negotiation_plan
        plan["live_refusal_probe"] = live_probe
        # Persist the exact live-filtered evidence used by both planners.  A
        # later bounded wave must not lose trapped-support authority merely
        # because its optional fresh probe times out before emitting another
        # certificate.
        plan["planning_refusal_evidence"] = {
            "schema": 1,
            "unconn_nets": list(before.get("unconn_nets") or ()),
            "refused_details": [
                copy.deepcopy(row["detail"])
                for row in refusal_certificates(planning_completion)
            ],
        }

        # Route refusal can prove that the copper search is not the remaining
        # degree of freedom: a small support footprint inherited from an older
        # or authored placement may physically seal every surface escape from
        # a fine-pitch pad.  Consume that evidence before repeatedly ripping
        # up unrelated tracks.  The entire footprint/pad-via/incident-branch
        # move is transactional and must restore its support nets, improve the
        # full-board score, and preserve every pair/topology gate.
        footprint_plan = _spawn_apply(
            _footprint_plan_worker, (current, planning_completion, 4))
        footprint_plan["board"] = os.path.abspath(board_path)
        footprint_sweep = {"schema": 1, "targets": footprint_plan["targets"],
                           "attempts": [], "accepted": [],
                           "stop": "no_eligible_trapped_support"}
        footprint_targets = list(footprint_plan["targets"])
        support_relocation_deferred = _defer_support_relocation(
            footprint_plan, negotiation_plan, completion)
        if support_relocation_deferred:
            footprint_targets = []
            footprint_sweep["stop"] = \
                "deferred_until_movable_route_windows_exhausted"
        prior_footprint_candidates = _prior_footprint_candidate_keys(
            completion)
        for footprint_index, target_row in enumerate(footprint_targets):
            result = _attempt_footprint_relocation(
                current, before, target_row, work_dir=work,
                token="%02d" % footprint_index, effort=effort,
                # Breadth first: no difficult passive may consume the wave
                # before another certified support receives a trial.  Later
                # waves skip these exact deterministic poses and continue the
                # finite ladder rather than restarting it.
                max_candidates=2,
                skip_candidate_keys=prior_footprint_candidates,
                generated_locked_uuids=generated_locked_uuids)
            footprint_sweep["attempts"].extend(result["attempts"])
            if not result["adopted"]:
                footprint_sweep["stop"] = result.get(
                    "stop", "candidate_exhausted")
                if effort.stop_reason:
                    break
                continue
            before = result["after"]
            accepted.append(result["accepted"])
            footprint_sweep["accepted"].append(result["accepted"])
            footprint_sweep["stop"] = "accepted_one_remeasure_required"
            break
        footprint_plan["sweep"] = footprint_sweep
        plan["footprint_relocation"] = footprint_plan

        # A refusal-named generated via is a smaller degree of freedom than
        # moving the endpoint owner or replaying a whole-net maze.  Earlier
        # scheduling placed it after both, so a bounded wave could spend its
        # entire wall clock re-proving the same route plateau without reaching
        # the exact movable barrel named by that proof.  Try the finite via
        # ladder here, after any tiny support-cell repair but before owner
        # placement.  Authored/on-pad/priority vias never enter this plan, and
        # the composite transaction still has to close the target, restore any
        # newly displaced generated track, and pass full-board admission.
        early_congestion_via_attempted = False
        early_congestion_via_plan = None
        if (not footprint_sweep["accepted"]
                and effort.available("congestion_via_relocation_early")):
            early_congestion_via_plan = _spawn_apply(
                _congestion_via_plan_worker,
                (current, planning_completion,
                 generated_locked_uuids, 4))
            early_congestion_via_plan["board"] = os.path.abspath(board_path)
            early_via_sweep = {
                "schema": 1,
                "targets": early_congestion_via_plan["targets"],
                "attempts": [], "accepted": [],
                "stop": "no_eligible_via",
                "schedule": "before_endpoint_owner_and_route_replay",
            }
            if early_congestion_via_plan["targets"]:
                early_congestion_via_attempted = True
            for via_index, target_row in enumerate(
                    early_congestion_via_plan["targets"]):
                result = _attempt_congestion_via_relocation(
                    current, before, target_row, work_dir=work,
                    token="early-%02d" % via_index,
                    generated_locked_uuids=generated_locked_uuids,
                    effort=effort, max_candidates=8)
                early_via_sweep["attempts"].extend(result["attempts"])
                if not result["adopted"]:
                    early_via_sweep["stop"] = result.get(
                        "stop", "candidate_exhausted")
                    if effort.stop_reason:
                        break
                    continue
                before = result["after"]
                accepted.append(result["accepted"])
                early_via_sweep["accepted"].append(result["accepted"])
                early_via_sweep["stop"] = \
                    "accepted_one_remeasure_required"
                effort.stop_reason = "via_slice_complete"
                effort.stop_stage = "congestion_via_relocation_early"
                break
            early_congestion_via_plan["sweep"] = early_via_sweep
            plan["congestion_via_relocation"] = \
                early_congestion_via_plan

        # Once both exact route windows and small support motion have reached
        # their measured fixed point, spend the next bounded slice on the
        # trapped endpoint owner before replaying lower-value route/via
        # variants.  This is the placement equivalent of routing critical
        # nets first: a sealed IC pad cannot be repaired by moving only its
        # clear peer or by repeating the same whole-net maze.
        early_owner_attempted = False
        early_owner_plan = None
        if (not support_relocation_deferred
                and not footprint_sweep["accepted"]
                and not effort.stop_reason
                and effort.available("endpoint_owner_relocation_early")):
            early_owner_plan = _spawn_apply(
                _endpoint_owner_plan_worker,
                (current, planning_completion, 4))
            early_owner_plan["board"] = os.path.abspath(board_path)
            early_owner_sweep = {
                "schema": 1, "targets": early_owner_plan["targets"],
                "attempts": [], "accepted": [],
                "stop": "no_eligible_owner",
                "schedule": "after_route_and_support_fixed_point",
            }
            for owner_index, target_row in enumerate(
                    early_owner_plan["targets"]):
                result = _attempt_footprint_relocation(
                    current, before, target_row, work_dir=work,
                    token="owner-early-%02d" % owner_index,
                    effort=effort, max_candidates=1,
                    skip_candidate_keys=prior_footprint_candidates,
                    stage_name="endpoint_owner_relocation",
                    max_copper_pads=16, max_branch_tracks=64,
                    generated_locked_uuids=generated_locked_uuids)
                early_owner_sweep["attempts"].extend(result["attempts"])
                if not result["adopted"]:
                    early_owner_sweep["stop"] = result.get(
                        "stop", "candidate_exhausted")
                    if effort.stop_reason:
                        break
                    continue
                before = result["after"]
                accepted.append(result["accepted"])
                early_owner_sweep["accepted"].append(result["accepted"])
                early_owner_sweep["stop"] = \
                    "accepted_one_remeasure_required"
                break
            early_owner_plan["sweep"] = early_owner_sweep
            plan["endpoint_owner_relocation"] = early_owner_plan
            early_owner_attempted = True
            placement_frontier_advanced = _placement_frontier_advanced(
                footprint_sweep, early_owner_sweep)
            early_owner_sweep["frontier_advanced"] = \
                placement_frontier_advanced
            # This wave entered placement only because current route windows
            # had already reached a measured fixed point.  End the logical
            # slice after its finite support/owner frontier; replaying route
            # and via searches in the same wave wastes the remaining wall
            # clock and delays the next remembered placement poses.  Normal
            # report/final-board publication still runs below, and an accepted
            # move is freshly remeasured by the next wave.  When every current
            # pose was already present in history, however, do not manufacture
            # another placement-only slice: continue into route/via work.
            if placement_frontier_advanced:
                effort.stop_reason = "placement_slice_complete"
                effort.stop_stage = "endpoint_owner_relocation_early"
            else:
                early_owner_sweep["stop"] = \
                    "placement_candidate_frontier_exhausted"

        variants = [("same_layer", margin) for margin in (2.0, 4.0, 8.0)]
        variants.append(("bridge", 8.0))
        variants.extend(("branch_same_layer", margin)
                        for margin in (2.0, 4.0, 8.0))
        variants.append(("branch_bridge", 8.0))
        # If preserving the certified future corridor makes the blocker itself
        # unroutable, retain the DRC-fixing fallback but label it explicitly as
        # a plateau.  The next placement wave then sees the refreshed
        # certificate instead of silently carrying a structural violation.
        variants.append(("branch_same_layer_unreserved", 2.0))
        variants.append(("branch_bridge_unreserved", 8.0))
        # Standalone blocker relocation is useful only for an exact DRC
        # offender.  A neutral congestion move cannot improve connectivity by
        # itself and was formerly rejected before the blocked connection could
        # claim the freed corridor.  Non-DRC blockers go directly to the atomic
        # negotiation below.
        individual_targets = [row for row in plan["targets"]
                              if row.get("drc_conflict")]
        accepted_blocker_target = None
        for target_row in individual_targets[:max(0, int(max_targets))]:
            target = RepairTarget(**target_row)
            adopted_target = False
            for mode, margin in variants:
                if not effort.claim("blocker_reroute", stage_limit=10):
                    break
                trial = os.path.join(work, "trial-%03d.kicad_pcb" % len(attempts))
                _copy_board_family(current, trial)
                has_operations, evidence = _spawn_apply(
                    _mutate_worker, (trial, target_row, mode, margin))
                row = {"target": asdict(target), **evidence}
                if not has_operations:
                    row.update({"accepted": False,
                                "decision": evidence.get("refusal")})
                    attempts.append(row)
                    continue
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:                 # noqa: BLE001
                    row["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                trial_drc = os.path.join(work, "trial-%03d-drc.json" % len(attempts))
                trial_drc_data = _run_drc(trial, trial_drc)
                after = _spawn_apply(_score_worker, (trial, trial_drc))
                ok, decision = _accepts(before, after)
                row.update({"after": after, "accepted": ok,
                            "decision": decision})
                attempts.append(row)
                if not ok:
                    continue
                _copy_board_family(trial, current)
                before = after
                accepted.append({"stage": "blocker_reroute", **row})
                accepted_blocker_target = target_row
                adopted_target = True
                if verbose:
                    print("[certificate-repair] accepted %s %s: %s" %
                          (target.net, target.uuid, row["after"]),
                          file=sys.stderr, flush=True)
                break
            if adopted_target:
                # Certificates describe the original graph.  Do not apply a
                # second stale removal in the same local neighborhood; refresh
                # in a future wave from the newly generated certificates.
                break
            if ("blocker_reroute" in effort.stage_stops
                    or effort.stop_reason):
                break

        # Once a proven blocker moves, retry only the connections whose
        # certificates named it.  The ladder increases search breadth without
        # ever changing clearance, width, or collision rules.
        if close_blocked_nets and accepted_blocker_target is not None:
            target_nets = set(
                accepted_blocker_target.get("blocked_nets") or ())
            for attempt_budget, margin in zip(lastmile_attempts, lastmile_margins):
                if not target_nets:
                    break
                if not effort.claim(
                        "blocked_net_completion", stage_limit=2):
                    break
                trial = os.path.join(work, "close-%03d.kicad_pcb" % len(attempts))
                _copy_board_family(current, trial)
                report = _spawn_apply(
                    _lastmile_worker,
                    (trial, tuple(sorted(target_nets)), attempt_budget, margin))
                row = {"stage": "blocked_net_completion",
                       "nets": sorted(target_nets),
                       "attempts_per_pair": int(attempt_budget),
                       "maze_margin_mm": float(margin), "completion": report}
                if not report.get("closed"):
                    row.update({"accepted": False,
                                "decision": "completion_still_refused"})
                    attempts.append(row)
                    continue
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:                 # noqa: BLE001
                    row["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                trial_drc = os.path.join(work, "close-%03d-drc.json" % len(attempts))
                trial_drc_data = _run_drc(trial, trial_drc)
                after = _spawn_apply(_score_worker, (trial, trial_drc))
                ok, decision = _accepts(before, after)
                row.update({"after": after, "accepted": ok,
                            "decision": decision})
                attempts.append(row)
                if not ok:
                    continue
                _copy_board_family(trial, current)
                before = after
                accepted.append(row)
                break

        # Refresh KiCad's exact DRC UUID set after every accepted move and
        # continue a bounded identity-driven cleanup.  Completion
        # certificates become stale after copper moves, but DRC evidence does
        # not: each fresh report names the live offending objects.  Planning
        # with an empty completion payload therefore permits only the new
        # direct-DRC targets added by plan_repairs(), never stale congestion
        # blockers.  One accepted target per round keeps the transaction and
        # its proof small while allowing a single production invocation to
        # remove more than one independent residual-router defect.
        drc_sweep = {"schema": 1, "rounds": [], "stop": "round_budget"}
        for sweep_round in range(max(0, int(max_targets))):
            live_drc_path = os.path.join(
                work, "sweep-%02d-baseline-drc.json" % sweep_round)
            live_drc = _run_drc(current, live_drc_path)
            live_plan = _spawn_apply(
                _plan_worker, (current, {}, live_drc, max_targets))
            live_targets = [row for row in live_plan.get("targets") or ()
                            if row.get("drc_conflict")]
            round_row = {
                "round": sweep_round,
                "candidate_uuids": [row["uuid"] for row in live_targets],
                "accepted": False,
            }
            drc_sweep["rounds"].append(round_row)
            if not live_targets:
                drc_sweep["stop"] = "no_movable_drc_tracks"
                break
            for target_row in live_targets:
                target = RepairTarget(**target_row)
                for mode, margin in variants:
                    if not effort.claim(
                            "drc_identity_reroute", stage_limit=16):
                        break
                    trial = os.path.join(
                        work, "sweep-%02d-%03d.kicad_pcb" %
                        (sweep_round, len(attempts)))
                    _copy_board_family(current, trial)
                    has_operations, evidence = _spawn_apply(
                        _mutate_worker, (trial, target_row, mode, margin))
                    row = {"stage": "drc_identity_reroute",
                           "round": sweep_round,
                           "target": asdict(target), **evidence}
                    if not has_operations:
                        row.update({"accepted": False,
                                    "decision": evidence.get("refusal")})
                        attempts.append(row)
                        continue
                    try:
                        _spawn_apply(_refill_worker, (trial,))
                    except Exception as exc:             # noqa: BLE001
                        row["refill_warning"] = "%s: %s" % (
                            type(exc).__name__, exc)
                    trial_drc = os.path.join(
                        work, "sweep-%02d-%03d-drc.json" %
                        (sweep_round, len(attempts)))
                    _run_drc(trial, trial_drc)
                    after = _spawn_apply(
                        _score_worker, (trial, trial_drc))
                    ok, decision = _accepts(before, after)
                    row.update({"after": after, "accepted": ok,
                                "decision": decision})
                    attempts.append(row)
                    if not ok:
                        continue
                    _copy_board_family(trial, current)
                    before = after
                    accepted.append(row)
                    round_row.update({
                        "accepted": True, "uuid": target.uuid,
                        "net": target.net, "decision": decision,
                        "after_drc": after["drc"],
                        "after_unconnected": after["unconnected"],
                    })
                    if verbose:
                        print("[certificate-repair] DRC sweep accepted "
                              "%s %s: drc=%s unconnected=%s" %
                              (target.net, target.uuid, after["drc"],
                               after["unconnected"]),
                              file=sys.stderr, flush=True)
                    break
                if round_row["accepted"]:
                    break
            if not round_row["accepted"]:
                drc_sweep["stop"] = effort.stage_stop(
                    "drc_identity_reroute",
                    "no_admissible_drc_reroute")
                break

        # Recover only legacy locked measurement copper that is itself named
        # by a live clearance identity.  This is intentionally separate from
        # ordinary blocker repair: the lock is an authorship boundary and may
        # be crossed only for an exact, ungrouped Kelvin/sense offender.  Each
        # replacement is re-locked before save and must pass the same strict
        # identity-aware admission contract as every other stage.
        sensitive_drc_sweep = {
            "schema": 1, "rounds": [], "stop": "round_budget"}
        baseline_topology_clean = not (
            before.get("kelvin_topology_faults")
            or before.get("route_topology_fault_nets"))
        if not baseline_topology_clean:
            sensitive_drc_sweep["stop"] = "baseline_topology_not_clean"
        else:
            sensitive_variants = [
                ("same_layer", 2.0), ("same_layer", 4.0),
                ("same_layer", 8.0), ("bridge", 8.0),
            ]
            for sensitive_round in range(max(0, int(max_targets))):
                live_drc_path = os.path.join(
                    work, "sensitive-%02d-baseline-drc.json" %
                    sensitive_round)
                live_drc = _run_drc(current, live_drc_path)
                sensitive_plan = _spawn_apply(
                    _sensitive_plan_worker,
                    (current, live_drc, max_targets))
                sensitive_targets = list(
                    sensitive_plan.get("targets") or ())
                round_row = {
                    "round": sensitive_round,
                    "candidate_uuids": [row["uuid"]
                                        for row in sensitive_targets],
                    "immutable": sensitive_plan.get("immutable") or [],
                    "accepted": False,
                }
                sensitive_drc_sweep["rounds"].append(round_row)
                if not sensitive_targets:
                    sensitive_drc_sweep["stop"] = (
                        "no_eligible_locked_sensitive_tracks")
                    break
                for target_row in sensitive_targets:
                    target = RepairTarget(**target_row)
                    for mode, margin in sensitive_variants:
                        if not effort.claim(
                                "sensitive_drc_reroute", stage_limit=8):
                            break
                        trial = os.path.join(
                            work, "sensitive-%02d-%03d.kicad_pcb" %
                            (sensitive_round, len(attempts)))
                        _copy_board_family(current, trial)
                        has_operations, evidence = _spawn_apply(
                            _mutate_worker,
                            (trial, target_row, mode, margin))
                        row = {
                            "stage": "sensitive_drc_reroute",
                            "round": sensitive_round,
                            "target": asdict(target), **evidence,
                        }
                        if not has_operations:
                            row.update({
                                "accepted": False,
                                "decision": evidence.get("refusal"),
                            })
                            attempts.append(row)
                            continue
                        try:
                            _spawn_apply(_refill_worker, (trial,))
                        except Exception as exc:         # noqa: BLE001
                            row["refill_warning"] = "%s: %s" % (
                                type(exc).__name__, exc)
                        trial_drc = os.path.join(
                            work, "sensitive-%02d-%03d-drc.json" %
                            (sensitive_round, len(attempts)))
                        _run_drc(trial, trial_drc)
                        after = _spawn_apply(
                            _score_worker, (trial, trial_drc))
                        ok, decision = _accepts(before, after)
                        # The central contract rejects newly introduced
                        # topology faults.  This stronger local requirement
                        # also refuses to carry any such ambiguity out of a
                        # sensitive-recovery transaction.
                        if (after.get("kelvin_topology_faults")
                                or after.get("route_topology_fault_nets")):
                            ok = False
                            decision = "sensitive_topology_not_clean"
                        row.update({"after": after, "accepted": ok,
                                    "decision": decision})
                        attempts.append(row)
                        if not ok:
                            continue
                        _copy_board_family(trial, current)
                        before = after
                        accepted.append(row)
                        round_row.update({
                            "accepted": True, "uuid": target.uuid,
                            "net": target.net, "decision": decision,
                            "after_drc": after["drc"],
                            "after_unconnected": after["unconnected"],
                        })
                        if verbose:
                            print(
                                "[certificate-repair] sensitive DRC sweep "
                                "accepted %s %s: drc=%s unconnected=%s" %
                                (target.net, target.uuid, after["drc"],
                                 after["unconnected"]),
                                file=sys.stderr, flush=True)
                        break
                    if round_row["accepted"]:
                        break
                if not round_row["accepted"]:
                    sensitive_drc_sweep["stop"] = effort.stage_stop(
                        "sensitive_drc_reroute",
                        "no_admissible_sensitive_drc_reroute")
                    break

        # Track-only surgery cannot resolve a live identity whose routed side
        # is a locked priority segment and whose other side is a lower-
        # authority unlocked via.  Replan from the current DRC, move only the
        # named barrel, and rebuild its incident same-net stubs through the
        # ordinary guarded 0/45/90 path generator.  Each move is a separate
        # full-board transaction; UUID-set admission prevents a clearance debt
        # swap even when the raw DRC count happens to remain constant.
        via_sweep = {"schema": 1, "rounds": [], "stop": "round_budget"}
        for via_round in range(max(0, int(max_targets))):
            live_drc_path = os.path.join(
                work, "via-%02d-baseline-drc.json" % via_round)
            live_drc = _run_drc(current, live_drc_path)
            via_plan = plan_via_repairs(
                current, live_drc, limit=max_targets)
            targets = list(via_plan.get("targets") or ())
            round_row = {
                "round": via_round,
                "candidate_uuids": [row["uuid"] for row in targets],
                "accepted": False,
            }
            via_sweep["rounds"].append(round_row)
            if not targets:
                via_sweep["stop"] = "no_movable_drc_vias"
                break
            for target_row in targets:
                target = ViaRepairTarget(**target_row)
                # The conflict-away vectors are tried at all useful local
                # radii before broadening sideways; eighteen exact candidates
                # bound runtime without turning this into unconstrained via
                # spreading.
                offsets = list(_via_offset_candidates(target))[:18]
                for dx_nm, dy_nm, step_mm, direction in offsets:
                    if not effort.claim(
                            "drc_via_relocation", stage_limit=12):
                        break
                    trial = os.path.join(
                        work, "via-%02d-%03d.kicad_pcb" %
                        (via_round, len(attempts)))
                    _copy_board_family(current, trial)
                    changed, evidence = _spawn_apply(
                        _relocate_via_worker,
                        (trial, target_row, dx_nm, dy_nm))
                    row = {
                        "stage": "drc_via_relocation",
                        "round": via_round,
                        "target": asdict(target),
                        "step_mm": step_mm,
                        "direction": list(direction),
                        **evidence,
                    }
                    if not changed:
                        row.update({"accepted": False,
                                    "decision": evidence.get("refusal")})
                        attempts.append(row)
                        continue
                    try:
                        _spawn_apply(_refill_worker, (trial,))
                    except Exception as exc:             # noqa: BLE001
                        row["refill_warning"] = "%s: %s" % (
                            type(exc).__name__, exc)
                    trial_drc = os.path.join(
                        work, "via-%02d-%03d-drc.json" %
                        (via_round, len(attempts)))
                    _run_drc(trial, trial_drc)
                    after = _spawn_apply(
                        _score_worker, (trial, trial_drc))
                    ok, decision = _accepts(before, after)
                    row.update({"after": after, "accepted": ok,
                                "decision": decision})
                    attempts.append(row)
                    if not ok:
                        continue
                    _copy_board_family(trial, current)
                    before = after
                    accepted.append(row)
                    round_row.update({
                        "accepted": True, "uuid": target.uuid,
                        "net": target.net, "decision": decision,
                        "after_drc": after["drc"],
                        "after_unconnected": after["unconnected"],
                        "new_mm": evidence.get("new_mm"),
                    })
                    if verbose:
                        print("[certificate-repair] via relocation accepted "
                              "%s %s -> %s: drc=%s unconnected=%s" %
                              (target.net, target.uuid,
                               evidence.get("new_mm"), after["drc"],
                               after["unconnected"]),
                              file=sys.stderr, flush=True)
                    break
                if round_row["accepted"]:
                    break
            if not round_row["accepted"]:
                via_sweep["stop"] = effort.stage_stop(
                    "drc_via_relocation",
                    "no_admissible_via_relocation")
                break

        # Restore protected pairs before ordinary residual closure.  The
        # single-net repair path correctly treats pair copper as immutable,
        # but that used to leave an important gap: when *both* members were
        # still open, no later stage owned the legal atomic repair.  Delegate
        # the complete pair to the precision router, then admit its result only
        # after a fresh fill, KiCad DRC, connectivity score, pair gate, Kelvin
        # gate, and route-topology gate.  Running this before broad closure also
        # ensures the following refusal certificates see the newly reserved
        # pair corridor rather than planning against stale free space.
        pair_sweep = {
            "schema": 1, "candidates": [], "attempts": [],
            "partial_candidates": [], "partial_attempts": [],
            "partial_accepted": [], "accepted": [],
            "stop": "no_open_coupled_pair",
        }
        if before["unconnected"] > 0 and effort.available(
                "coupled_pair_closure"):
            # Exactly one open member is not a single-net repair problem.  Its
            # already-connected mate owns the matched topology and must be
            # replaced with it.  Rip up only unlocked or explicitly
            # pipeline-generated copper for the complete declared pair, route
            # both members as one precision transaction, then use the same
            # strict whole-board admission contract as every other stage.
            partial_pairs = _spawn_apply(
                _partial_open_coupled_pairs_worker,
                (current, tuple(before.get("unconn_nets") or ())))
            pair_sweep["partial_candidates"] = [
                {key: pair.get(key) for key in
                 ("name", "kind", "p", "n", "width", "gap", "clearance")}
                for pair in partial_pairs]
            if partial_pairs:
                pair_sweep["stop"] = "candidate_exhausted"
            for pair_index, pair in enumerate(partial_pairs):
                if not effort.claim(
                        "partial_coupled_pair_replacement", stage_limit=2):
                    pair_sweep["stop"] = effort.stage_stop(
                        "partial_coupled_pair_replacement", "effort_budget")
                    break
                trial = os.path.join(
                    work, "partial-pair-%02d-%03d.kicad_pcb" %
                    (pair_index, len(attempts)))
                _copy_board_family(current, trial)
                removed, removal = _spawn_apply(
                    _remove_partial_pair_copper_worker,
                    (trial, pair["name"], tuple(generated_locked_uuids)))
                row = {
                    "stage": "partial_coupled_pair_replacement",
                    "pair": {key: pair.get(key) for key in
                             ("name", "kind", "p", "n", "width", "gap",
                              "clearance")},
                    "removal": removal,
                }
                if not removed:
                    row.update({"accepted": False,
                                "decision": removal.get("refusal")})
                    pair_sweep["partial_attempts"].append(row)
                    attempts.append(row)
                    continue
                changed, precision_report = _spawn_apply(
                    _coupled_pair_closure_worker,
                    (trial, pair["name"], True, 120.0), timeout_s=140.0)
                row["precision"] = precision_report
                if not changed:
                    swapped, swap_evidence = _spawn_apply(
                        _swap_reversible_split_pair_station_worker,
                        (trial, pair["name"],
                         tuple(generated_locked_uuids)))
                    row["support_orientation"] = swap_evidence
                    if swapped:
                        related_pairs = _spawn_apply(
                            _coupled_pairs_within_nets_worker,
                            (trial, tuple(
                                swap_evidence.get("displaced_nets") or ())))
                        row["related_displaced_pairs"] = [
                            {key: related.get(key) for key in
                             ("name", "p", "n", "kind")}
                            for related in related_pairs]
                        related_removals = []
                        related_ready = True
                        for related in related_pairs:
                            related_removed, related_evidence = _spawn_apply(
                                _remove_partial_pair_copper_worker,
                                (trial, related["name"],
                                 tuple(generated_locked_uuids)))
                            related_removals.append({
                                "name": related["name"],
                                "removed": related_removed,
                                "evidence": related_evidence})
                            related_ready = related_ready and related_removed
                        row["related_pair_removals"] = related_removals
                        bundle_names = [pair["name"]] + [
                            related["name"] for related in related_pairs]
                        if related_ready:
                            changed, swapped_precision = _spawn_apply(
                                _coupled_pair_bundle_closure_worker,
                                (trial, tuple(bundle_names), True, 120.0),
                                timeout_s=280.0)
                        else:
                            changed, swapped_precision = False, {
                                "refusal": "related_pair_copper_immutable"}
                        row["precision_after_support_orientation"] = \
                            swapped_precision
                        paired_nets = {
                            str(related.get(member) or "")
                            for related in related_pairs
                            for member in ("p", "n")}
                        ordinary_nets = sorted(
                            set(swap_evidence.get("displaced_nets") or ())
                            - paired_nets)
                        if changed and ordinary_nets:
                            row["support_net_cleanup"] = _spawn_apply(
                                _lastmile_worker,
                                (trial, tuple(ordinary_nets),
                                 24, 4.0, True), timeout_s=90.0)
                if not changed:
                    row.update({"accepted": False,
                                "decision": "precision_pair_refused"})
                    pair_sweep["partial_attempts"].append(row)
                    attempts.append(row)
                    continue
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:             # noqa: BLE001
                    row["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                trial_drc = os.path.join(
                    work, "partial-pair-%02d-%03d-drc.json" %
                    (pair_index, len(attempts)))
                _run_drc(trial, trial_drc)
                after = _spawn_apply(_score_worker, (trial, trial_drc))
                ok, decision = _accepts(before, after)
                row.update({"after": after, "accepted": ok,
                            "decision": decision})
                pair_sweep["partial_attempts"].append(row)
                attempts.append(row)
                if not ok:
                    continue
                _copy_board_family(trial, current)
                before = after
                accepted.append(row)
                pair_sweep["partial_accepted"].append({
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "after_drc": after["drc"],
                    "after_unconnected": after["unconnected"],
                    "diffpair_ok": after["diffpair_ok"],
                    "decision": decision,
                })
                pair_sweep["stop"] = "accepted_partial_pair"
                if verbose:
                    print("[certificate-repair] partial coupled pair %s "
                          "accepted: drc=%s unconnected=%s diffpair=%s" %
                          (pair["name"], after["drc"],
                           after["unconnected"], after["diffpair_ok"]),
                          file=sys.stderr, flush=True)

            open_pairs = _spawn_apply(
                _open_coupled_pairs_worker,
                (current, tuple(before.get("unconn_nets") or ())))
            pair_sweep["candidates"] = [
                {key: pair.get(key) for key in
                 ("name", "kind", "p", "n", "width", "gap", "clearance")}
                for pair in open_pairs]
            if open_pairs:
                pair_sweep["stop"] = "candidate_exhausted"
            for pair_index, pair in enumerate(open_pairs):
                if not effort.claim(
                        "coupled_pair_closure", stage_limit=4):
                    pair_sweep["stop"] = effort.stage_stop(
                        "coupled_pair_closure", "effort_budget")
                    break
                trial = os.path.join(
                    work, "pair-%02d-%03d.kicad_pcb" %
                    (pair_index, len(attempts)))
                _copy_board_family(current, trial)
                changed, precision_report = _spawn_apply(
                    _coupled_pair_closure_worker,
                    (trial, pair["name"], True, 120.0), timeout_s=140.0)
                row = {
                    "stage": "coupled_pair_closure",
                    "pair": {key: pair.get(key) for key in
                             ("name", "kind", "p", "n", "width", "gap",
                              "clearance")},
                    "precision": precision_report,
                }
                if not changed:
                    swapped, swap_evidence = _spawn_apply(
                        _swap_reversible_split_pair_station_worker,
                        (trial, pair["name"],
                         tuple(generated_locked_uuids)))
                    row["support_orientation"] = swap_evidence
                    if swapped:
                        related_pairs = _spawn_apply(
                            _coupled_pairs_within_nets_worker,
                            (trial, tuple(
                                swap_evidence.get("displaced_nets") or ())))
                        row["related_displaced_pairs"] = [
                            {key: related.get(key) for key in
                             ("name", "p", "n", "kind")}
                            for related in related_pairs]
                        related_removals = []
                        related_ready = True
                        for related in related_pairs:
                            related_removed, related_evidence = _spawn_apply(
                                _remove_partial_pair_copper_worker,
                                (trial, related["name"],
                                 tuple(generated_locked_uuids)))
                            related_removals.append({
                                "name": related["name"],
                                "removed": related_removed,
                                "evidence": related_evidence})
                            related_ready = related_ready and related_removed
                        row["related_pair_removals"] = related_removals
                        bundle_names = [pair["name"]] + [
                            related["name"] for related in related_pairs]
                        if related_ready:
                            changed, swapped_precision = _spawn_apply(
                                _coupled_pair_bundle_closure_worker,
                                (trial, tuple(bundle_names), True, 120.0),
                                timeout_s=280.0)
                        else:
                            changed, swapped_precision = False, {
                                "refusal": "related_pair_copper_immutable"}
                        row["precision_after_support_orientation"] = \
                            swapped_precision
                        paired_nets = {
                            str(related.get(member) or "")
                            for related in related_pairs
                            for member in ("p", "n")}
                        ordinary_nets = sorted(
                            set(swap_evidence.get("displaced_nets") or ())
                            - paired_nets)
                        if changed and ordinary_nets:
                            row["support_net_cleanup"] = _spawn_apply(
                                _lastmile_worker,
                                (trial, tuple(ordinary_nets),
                                 24, 4.0, True), timeout_s=90.0)
                if not changed:
                    row.update({"accepted": False,
                                "decision": "precision_pair_refused"})
                    pair_sweep["attempts"].append(row)
                    attempts.append(row)
                    continue
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:             # noqa: BLE001
                    row["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                trial_drc = os.path.join(
                    work, "pair-%02d-%03d-drc.json" %
                    (pair_index, len(attempts)))
                _run_drc(trial, trial_drc)
                after = _spawn_apply(_score_worker, (trial, trial_drc))
                ok, decision = _accepts(before, after)
                row.update({"after": after, "accepted": ok,
                            "decision": decision})
                pair_sweep["attempts"].append(row)
                attempts.append(row)
                if not ok:
                    continue
                _copy_board_family(trial, current)
                before = after
                accepted.append(row)
                pair_sweep["accepted"].append({
                    "name": pair["name"], "p": pair["p"], "n": pair["n"],
                    "after_drc": after["drc"],
                    "after_unconnected": after["unconnected"],
                    "diffpair_ok": after["diffpair_ok"],
                    "decision": decision,
                })
                pair_sweep["stop"] = "accepted_all_candidates"
                if verbose:
                    print("[certificate-repair] coupled pair %s accepted: "
                          "drc=%s unconnected=%s diffpair=%s" %
                          (pair["name"], after["drc"],
                           after["unconnected"], after["diffpair_ok"]),
                          file=sys.stderr, flush=True)
        plan["coupled_pair_closure"] = pair_sweep

        # Re-run a cheap, board-generic finishing pass after structural
        # repair.  The ordinary router can leave legal component islands more
        # than 25 mm apart, while running a board-scale maze for every one of
        # those pairs is prohibitively slow.  Canonical 0/45/90 and guarded
        # bridge attempts are inexpensive at 80 mm, so iterate them only while
        # they strictly improve the certified graph.  The final (including
        # zero-closure) report is retained because its exact blocker UUIDs are
        # the only valid authority for the negotiation stage below.
        closure_sweep = {
            "schema": 1, "rounds": [], "stop": "round_budget",
            "schedule": "isolated_certified_distance_then_name",
        }
        closure_reports = []
        try:
            canonical_timeout_s = max(1.0, float(os.environ.get(
                "CEC_CERTIFICATE_CANONICAL_NET_TIMEOUT_S", "8")))
        except (TypeError, ValueError):
            canonical_timeout_s = 8.0
        try:
            canonical_net_cap = max(1, int(os.environ.get(
                "CEC_CERTIFICATE_CANONICAL_NET_CAP", "8")))
        except (TypeError, ValueError):
            canonical_net_cap = 8
        fresh_completion = {
            "unconn_nets": list(before.get("unconn_nets") or ()),
            "final_completion": _merge_single_net_completion_reports(
                before.get("unconn_nets") or (), (), planning_completion),
        }
        # Canonical closure only adds copper.  Therefore an accepted route can
        # change the component graph of that same net, but it cannot open a
        # corridor for a different net that just proved a fixed point.  Retry
        # only the improved-net frontier in later rounds instead of replaying
        # every refusal and burning the negotiation reserve.
        closure_frontier = None
        negotiation_reserve_s = min(
            90.0, max(0.0, float(wall_budget_s)) * 0.40)
        negotiation_reserve_attempts = min(
            16, max(0, int(max_attempts)) // 4)
        for closure_round in range(3):
            target_nets = _rank_single_net_closure_targets(
                before.get("unconn_nets") or (), fresh_completion)
            if closure_frontier is not None:
                target_nets = [
                    net for net in target_nets if net in closure_frontier]
            target_nets = target_nets[:canonical_net_cap]
            if not target_nets:
                closure_sweep["stop"] = "connectivity_closed"
                break
            round_row = {
                "round": closure_round,
                "nets": list(target_nets),
                "attempts": [],
                "closed": 0,
                "accepted": False,
            }
            closure_sweep["rounds"].append(round_row)
            round_improved = False
            improved_nets = set()
            for net_index, net in enumerate(target_nets):
                if not effort.claim_before_reserve(
                        "broad_canonical_closure",
                        stage_limit=3 * canonical_net_cap,
                        reserve_wall_s=negotiation_reserve_s,
                        reserve_attempts=negotiation_reserve_attempts,
                        trial_wall_s=canonical_timeout_s):
                    closure_sweep["stop"] = effort.stage_stop(
                        "broad_canonical_closure", "round_budget")
                    break
                trial = os.path.join(
                    work, "closure-%02d-%02d-%03d.kicad_pcb" %
                    (closure_round, net_index, len(attempts)))
                _copy_board_family(current, trial)
                row = {
                    "stage": "broad_canonical_closure",
                    "round": closure_round,
                    "net": net,
                    "timeout_s": canonical_timeout_s,
                }
                try:
                    completion_report = _spawn_apply(
                        _broad_canonical_worker, (trial, (net,)),
                        timeout_s=canonical_timeout_s)
                except cec_process_pool.WorkerPoolStalled as exc:
                    row.update({
                        "accepted": False,
                        "decision": "isolated_net_timeout",
                        "timeout": True,
                        "error": "%s: %s" % (
                            type(exc).__name__, str(exc)[:400]),
                    })
                    closure_reports.append(row)
                    round_row["attempts"].append(row)
                    attempts.append(row)
                    continue
                row["completion"] = completion_report
                if not completion_report.get("closed"):
                    row.update({
                        "accepted": False,
                        "decision": "isolated_fixed_point_no_closure",
                    })
                    closure_reports.append(row)
                    round_row["attempts"].append(row)
                    attempts.append(row)
                    continue
                try:
                    _spawn_apply(_refill_worker, (trial,))
                except Exception as exc:             # noqa: BLE001
                    row["refill_warning"] = "%s: %s" % (
                        type(exc).__name__, exc)
                trial_drc = os.path.join(
                    work, "closure-%02d-%02d-%03d-drc.json" %
                    (closure_round, net_index, len(attempts)))
                _run_drc(trial, trial_drc)
                after = _spawn_apply(_score_worker, (trial, trial_drc))
                ok, decision = _accepts(before, after)
                row.update({"after": after, "accepted": ok,
                            "decision": decision})
                round_row["attempts"].append(row)
                attempts.append(row)
                if not ok:
                    continue
                _copy_board_family(trial, current)
                before = after
                accepted.append(row)
                closure_reports.append(row)
                round_row["closed"] += int(
                    completion_report.get("closed") or 0)
                round_row.update({
                    "accepted": True, "decision": decision,
                    "after_drc": after["drc"],
                    "after_unconnected": after["unconnected"],
                })
                round_improved = True
                improved_nets.add(net)
                if verbose:
                    print("[certificate-repair] canonical closure %s: "
                          "drc=%s unconnected=%s" %
                          (net, after["drc"], after["unconnected"]),
                          file=sys.stderr, flush=True)
            fresh_completion = {
                "unconn_nets": list(before.get("unconn_nets") or ()),
                "final_completion": _merge_single_net_completion_reports(
                    before.get("unconn_nets") or (), closure_reports,
                    planning_completion),
            }
            if effort.stop_reason or "broad_canonical_closure" in \
                    effort.stage_stops:
                break
            if not round_improved:
                closure_sweep["stop"] = "isolated_fixed_point"
                break
            closure_frontier = improved_nets

        # The cheap breadth probe intentionally omits lattice and maze work,
        # but blocker negotiation is destructive and must not run merely
        # because that probe reached a fixed point.  Give each remaining net
        # one bounded, isolated bridge-first/deep portfolio first.  Existing
        # vias/THT anchors are now represented explicitly in that portfolio,
        # so a six-layer board can use its available routing fabric before the
        # pipeline considers rip-up or placement.  Each candidate still needs
        # independent whole-board connectivity and DRC admission.
        deep_route_sweep = {
            "schema": 1, "attempts": [], "accepted": [],
            "stop": "candidate_exhausted",
            "schedule": "additive_route_before_destructive_negotiation",
        }
        try:
            deep_route_timeout_s = max(8.0, float(os.environ.get(
                "CEC_CERTIFICATE_DEEP_NET_TIMEOUT_S", "30")))
        except (TypeError, ValueError):
            deep_route_timeout_s = 30.0
        deep_route_inner_s = max(5.0, deep_route_timeout_s - 3.0)
        deep_targets = _rank_single_net_closure_targets(
            before.get("unconn_nets") or (), fresh_completion)
        deep_targets = deep_targets[:min(4, canonical_net_cap)]
        for net_index, net in enumerate(deep_targets):
            if not effort.claim_before_reserve(
                    "deep_route_portfolio", stage_limit=4,
                    reserve_wall_s=negotiation_reserve_s,
                    reserve_attempts=negotiation_reserve_attempts,
                    trial_wall_s=deep_route_timeout_s):
                deep_route_sweep["stop"] = effort.stage_stop(
                    "deep_route_portfolio", "effort_budget")
                break
            trial = os.path.join(
                work, "deep-route-%02d-%03d.kicad_pcb" %
                (net_index, len(attempts)))
            _copy_board_family(current, trial)
            row = {
                "stage": "deep_route_portfolio",
                "net": net,
                "timeout_s": deep_route_timeout_s,
            }
            try:
                completion_report = _spawn_apply(
                    _lastmile_worker,
                    (trial, (net,), 24, 8.0, True,
                     deep_route_inner_s),
                    timeout_s=deep_route_timeout_s)
            except cec_process_pool.WorkerPoolStalled as exc:
                row.update({
                    "accepted": False,
                    "decision": "isolated_deep_route_timeout",
                    "timeout": True,
                    "error": "%s: %s" % (
                        type(exc).__name__, str(exc)[:400]),
                })
                deep_route_sweep["attempts"].append(row)
                closure_reports.append(row)
                attempts.append(row)
                continue
            row["completion"] = completion_report
            if not completion_report.get("closed"):
                row.update({
                    "accepted": False,
                    "decision": "isolated_deep_route_no_closure",
                })
                deep_route_sweep["attempts"].append(row)
                closure_reports.append(row)
                attempts.append(row)
                continue
            try:
                _spawn_apply(_refill_worker, (trial,))
            except Exception as exc:                 # noqa: BLE001
                row["refill_warning"] = "%s: %s" % (
                    type(exc).__name__, exc)
            trial_drc = os.path.join(
                work, "deep-route-%02d-%03d-drc.json" %
                (net_index, len(attempts)))
            _run_drc(trial, trial_drc)
            after = _spawn_apply(_score_worker, (trial, trial_drc))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            deep_route_sweep["attempts"].append(row)
            closure_reports.append(row)
            attempts.append(row)
            if not ok:
                continue
            _copy_board_family(trial, current)
            before = after
            accepted.append(row)
            deep_route_sweep["accepted"].append({
                "net": net, "decision": decision,
                "after_drc": after["drc"],
                "after_unconnected": after["unconnected"],
            })
            if verbose:
                print("[certificate-repair] deep route %s: "
                      "drc=%s unconnected=%s" %
                      (net, after["drc"], after["unconnected"]),
                      file=sys.stderr, flush=True)
        fresh_completion = {
            "unconn_nets": list(before.get("unconn_nets") or ()),
            "final_completion": _merge_single_net_completion_reports(
                before.get("unconn_nets") or (), closure_reports,
                planning_completion),
        }
        plan["deep_route_portfolio"] = deep_route_sweep

        # Always negotiate from the latest refusal certificates.  Previously
        # this stage was disabled by *any* earlier adoption and retained the
        # pre-repair certificates, so a successful DRC repair accidentally
        # prevented the connectivity repair it was meant to enable.
        if effort.available("fresh_negotiation_plan"):
            generated_locked_uuids = _spawn_apply(
                _generated_locked_route_uuids,
                (current, authored_baseline))
            fresh_negotiation_plan = _spawn_apply(
                _negotiation_plan_worker,
                (current, fresh_completion, max_windows,
                 max_blockers_per_window, generated_locked_uuids))
            ordered_windows, prior_schedule = \
                _prioritize_windows_by_proven_close(
                    fresh_negotiation_plan.get("windows") or (), completion)
            fresh_negotiation_plan["windows"] = ordered_windows
            fresh_negotiation_plan["prior_outcome_schedule"] = prior_schedule
        else:
            fresh_negotiation_plan = {
                "schema": 1, "board": os.path.abspath(board_path),
                "windows": [], "skipped": effort.stop_reason,
            }
        fresh_negotiation_plan["board"] = os.path.abspath(board_path)
        plan["fresh_negotiation"] = fresh_negotiation_plan

        # Atomic negotiated rip-up: remove a bounded certificate-named blocker
        # set, route the refused net first, restore every displaced branch, and
        # admit only the composite full-board improvement.  The original
        # certificate set is stale after one adoption, so stop and let the next
        # wave remeasure rather than chaining speculative surgery.
        if negotiate and before["unconnected"] > 0:
            adopted_window = False
            for window_index, window_row in enumerate(
                    fresh_negotiation_plan["windows"]):
                result = _attempt_atomic_negotiation(
                    current, before, window_row,
                    work_dir=work,
                    token="00-%02d-%03d" % (window_index, len(attempts)),
                    deep_retry=deep_retry,
                    max_detour_ratio=max_detour_ratio,
                    effort=effort,
                    effort_stage="atomic_negotiation",
                    effort_stage_limit=12)
                attempts.extend(result["attempts"])
                if result["adopted"]:
                    before = result["after"]
                    accepted.append(result["accepted"])
                    adopted_window = True
                    if verbose:
                        window = NegotiationWindow(**window_row)
                        print("[certificate-repair] negotiated %s around %s: %s" %
                              (window.net, list(window.blocker_nets), before),
                              file=sys.stderr, flush=True)
                    break
                if ("atomic_negotiation" in effort.stage_stops
                        or effort.stop_reason):
                    break

            # A successful displacement changes which ordinary islands can
            # now see each other.  Re-run the same cheap finisher to a bounded
            # fixed point instead of carrying those newly opened corridors to
            # a later pipeline wave.
            post_negotiation_closure = {
                "schema": 1, "rounds": [], "stop": "not_adopted",
            }
            if adopted_window:
                post_negotiation_closure["stop"] = "round_budget"
                post_reports = []
                post_frontier = None
                cycle_reserve_s = min(
                    45.0, max(0.0, float(wall_budget_s)) * 0.20)
                cycle_reserve_attempts = min(
                    8, max(0, int(max_attempts)) // 8)
                for closure_round in range(2):
                    target_nets = _rank_single_net_closure_targets(
                        before.get("unconn_nets") or (), fresh_completion)
                    if post_frontier is not None:
                        target_nets = [
                            net for net in target_nets
                            if net in post_frontier]
                    target_nets = target_nets[:canonical_net_cap]
                    if not target_nets:
                        post_negotiation_closure["stop"] = \
                            "connectivity_closed"
                        break
                    round_row = {
                        "round": closure_round,
                        "nets": list(target_nets),
                        "attempts": [], "closed": 0, "accepted": False,
                    }
                    post_negotiation_closure["rounds"].append(round_row)
                    round_improved = False
                    improved_nets = set()
                    for net_index, net in enumerate(target_nets):
                        if not effort.claim_before_reserve(
                                "post_negotiation_closure",
                                stage_limit=2 * canonical_net_cap,
                                reserve_wall_s=cycle_reserve_s,
                                reserve_attempts=cycle_reserve_attempts,
                                trial_wall_s=canonical_timeout_s):
                            post_negotiation_closure["stop"] = \
                                effort.stage_stop(
                                    "post_negotiation_closure",
                                    "round_budget")
                            break
                        trial = os.path.join(
                            work,
                            "post-negotiate-%02d-%02d-%03d.kicad_pcb" %
                            (closure_round, net_index, len(attempts)))
                        _copy_board_family(current, trial)
                        row = {
                            "stage": "post_negotiation_closure",
                            "round": closure_round, "net": net,
                            "timeout_s": canonical_timeout_s,
                        }
                        try:
                            completion_report = _spawn_apply(
                                _broad_canonical_worker, (trial, (net,)),
                                timeout_s=canonical_timeout_s)
                        except cec_process_pool.WorkerPoolStalled as exc:
                            row.update({
                                "accepted": False,
                                "decision": "isolated_net_timeout",
                                "timeout": True,
                                "error": "%s: %s" % (
                                    type(exc).__name__, str(exc)[:400]),
                            })
                            post_reports.append(row)
                            round_row["attempts"].append(row)
                            attempts.append(row)
                            continue
                        row["completion"] = completion_report
                        if not completion_report.get("closed"):
                            row.update({
                                "accepted": False,
                                "decision":
                                    "isolated_fixed_point_no_closure",
                            })
                            post_reports.append(row)
                            round_row["attempts"].append(row)
                            attempts.append(row)
                            continue
                        try:
                            _spawn_apply(_refill_worker, (trial,))
                        except Exception as exc:     # noqa: BLE001
                            row["refill_warning"] = "%s: %s" % (
                                type(exc).__name__, exc)
                        trial_drc = os.path.join(
                            work,
                            "post-negotiate-%02d-%02d-%03d-drc.json" %
                            (closure_round, net_index, len(attempts)))
                        _run_drc(trial, trial_drc)
                        after = _spawn_apply(
                            _score_worker, (trial, trial_drc))
                        ok, decision = _accepts(before, after)
                        row.update({"after": after, "accepted": ok,
                                    "decision": decision})
                        round_row["attempts"].append(row)
                        attempts.append(row)
                        if not ok:
                            continue
                        _copy_board_family(trial, current)
                        before = after
                        accepted.append(row)
                        post_reports.append(row)
                        round_row["closed"] += int(
                            completion_report.get("closed") or 0)
                        round_row.update({
                            "accepted": True, "decision": decision,
                            "after_drc": after["drc"],
                            "after_unconnected": after["unconnected"],
                        })
                        round_improved = True
                        improved_nets.add(net)
                    fresh_completion = {
                        "unconn_nets": list(
                            before.get("unconn_nets") or ()),
                        "final_completion":
                            _merge_single_net_completion_reports(
                                before.get("unconn_nets") or (),
                                post_reports, fresh_completion),
                    }
                    if effort.stop_reason or \
                            "post_negotiation_closure" in \
                            effort.stage_stops:
                        break
                    if not round_improved:
                        post_negotiation_closure["stop"] = \
                            "isolated_fixed_point"
                        break
                    post_frontier = improved_nets
            plan["post_negotiation_closure"] = \
                post_negotiation_closure

            # Continue at most two more freshly certified negotiations.  This
            # is intentionally a small monotonic sweep, not an autorouter
            # loop: every cycle must adopt one full-board improvement, then
            # remeasure blockers and return to a canonical closure fixed point
            # before another displacement is even eligible.
            negotiation_sweep = {
                "schema": 1,
                "rounds": [{
                    "round": 0,
                    "accepted": bool(adopted_window),
                    "after_unconnected": before["unconnected"],
                    "after_drc": before["drc"],
                }],
                "stop": "round_budget" if adopted_window else
                        "no_admissible_negotiation",
            }
            for negotiation_round in range(1, 3):
                if not effort.available("negotiation_cycle"):
                    negotiation_sweep["stop"] = effort.stop_reason
                    break
                if not adopted_window or before["unconnected"] <= 0:
                    if before["unconnected"] <= 0:
                        negotiation_sweep["stop"] = "connectivity_closed"
                    break
                generated_locked_uuids = _spawn_apply(
                    _generated_locked_route_uuids,
                    (current, authored_baseline))
                cycle_plan = _spawn_apply(
                    _negotiation_plan_worker,
                    (current, fresh_completion, max_windows,
                     max_blockers_per_window, generated_locked_uuids))
                cycle_windows_ordered, cycle_prior_schedule = \
                    _prioritize_windows_by_proven_close(
                        cycle_plan.get("windows") or (), completion)
                cycle_plan["windows"] = cycle_windows_ordered
                cycle_plan["prior_outcome_schedule"] = \
                    cycle_prior_schedule
                # Later cycles operate on progressively harder residuals.
                # Cap their fresh candidate breadth so a no-improvement tail
                # cannot dominate an unattended wave after useful work has
                # already been published by earlier cycles.
                cycle_windows = list(cycle_plan["windows"])[
                    :min(4, max(0, int(max_windows)))]
                cycle_row = {
                    "round": negotiation_round,
                    "candidate_nets": [row["net"]
                                       for row in cycle_windows],
                    "window_cap": 4,
                    "prior_outcome_schedule": cycle_prior_schedule,
                    "accepted": False,
                }
                negotiation_sweep["rounds"].append(cycle_row)
                if not cycle_windows:
                    negotiation_sweep["stop"] = \
                        "no_certificate_movable_windows"
                    break
                adopted_window = False
                for window_index, window_row in enumerate(
                        cycle_windows):
                    result = _attempt_atomic_negotiation(
                        current, before, window_row,
                        work_dir=work,
                        token="%02d-%02d-%03d" %
                              (negotiation_round, window_index,
                               len(attempts)),
                        deep_retry=deep_retry,
                        max_detour_ratio=max_detour_ratio,
                        effort=effort,
                        effort_stage="negotiation_cycle",
                        effort_stage_limit=12)
                    attempts.extend(result["attempts"])
                    if not result["adopted"]:
                        continue
                    before = result["after"]
                    accepted.append(result["accepted"])
                    adopted_window = True
                    cycle_row.update({
                        "accepted": True,
                        "net": window_row["net"],
                        "after_unconnected": before["unconnected"],
                        "after_drc": before["drc"],
                    })
                    if verbose:
                        print("[certificate-repair] negotiation cycle %s "
                              "accepted %s: drc=%s unconnected=%s" %
                              (negotiation_round, window_row["net"],
                               before["drc"], before["unconnected"]),
                              file=sys.stderr, flush=True)
                    break
                if not adopted_window:
                    negotiation_sweep["stop"] = \
                        "no_admissible_negotiation"
                    break

                # Re-certify after this adoption.  Two rounds are sufficient:
                # the first can claim newly opened corridors; the second must
                # either improve again or prove the fresh fixed point.
                cycle_reports = []
                for closure_round in range(2):
                    target_nets = _rank_single_net_closure_targets(
                        before.get("unconn_nets") or (), fresh_completion)
                    target_nets = target_nets[:canonical_net_cap]
                    if not target_nets:
                        fresh_completion = {
                            "unconn_nets": [], "final_completion": {},
                        }
                        break
                    round_improved = False
                    for net_index, net in enumerate(target_nets):
                        if not effort.claim(
                                "negotiation_cycle_closure",
                                stage_limit=4 * canonical_net_cap):
                            negotiation_sweep["stop"] = effort.stage_stop(
                                "negotiation_cycle_closure",
                                "round_budget")
                            break
                        trial = os.path.join(
                            work,
                            "cycle-%02d-close-%02d-%02d-%03d.kicad_pcb" %
                            (negotiation_round, closure_round, net_index,
                             len(attempts)))
                        _copy_board_family(current, trial)
                        row = {
                            "stage": "negotiation_cycle_closure",
                            "negotiation_round": negotiation_round,
                            "round": closure_round, "net": net,
                            "timeout_s": canonical_timeout_s,
                        }
                        try:
                            completion_report = _spawn_apply(
                                _broad_canonical_worker, (trial, (net,)),
                                timeout_s=canonical_timeout_s)
                        except cec_process_pool.WorkerPoolStalled as exc:
                            row.update({
                                "accepted": False,
                                "decision": "isolated_net_timeout",
                                "timeout": True,
                                "error": "%s: %s" % (
                                    type(exc).__name__, str(exc)[:400]),
                            })
                            cycle_reports.append(row)
                            attempts.append(row)
                            continue
                        row["completion"] = completion_report
                        if not completion_report.get("closed"):
                            row.update({
                                "accepted": False,
                                "decision":
                                    "isolated_fixed_point_no_closure",
                            })
                            cycle_reports.append(row)
                            attempts.append(row)
                            continue
                        try:
                            _spawn_apply(_refill_worker, (trial,))
                        except Exception as exc:     # noqa: BLE001
                            row["refill_warning"] = "%s: %s" % (
                                type(exc).__name__, exc)
                        trial_drc = os.path.join(
                            work,
                            "cycle-%02d-close-%02d-%02d-%03d-drc.json" %
                            (negotiation_round, closure_round, net_index,
                             len(attempts)))
                        _run_drc(trial, trial_drc)
                        after = _spawn_apply(
                            _score_worker, (trial, trial_drc))
                        ok, decision = _accepts(before, after)
                        row.update({"after": after, "accepted": ok,
                                    "decision": decision})
                        attempts.append(row)
                        if not ok:
                            continue
                        _copy_board_family(trial, current)
                        before = after
                        accepted.append(row)
                        cycle_reports.append(row)
                        round_improved = True
                    fresh_completion = {
                        "unconn_nets": list(
                            before.get("unconn_nets") or ()),
                        "final_completion":
                            _merge_single_net_completion_reports(
                                before.get("unconn_nets") or (),
                                cycle_reports, fresh_completion),
                    }
                    if effort.stop_reason or \
                            "negotiation_cycle_closure" in \
                            effort.stage_stops:
                        break
                    if not round_improved:
                        break
            plan["negotiation_sweep"] = negotiation_sweep

        # Make the exact route fixed point the authority for every broader
        # degree of freedom in this same run.  Previously the via and endpoint
        # owner planners consumed ``fresh_completion`` from the cheap
        # pre-negotiation probe, while the much better exact-pair certificates
        # remained buried in telemetry until a later wave (and timed-out
        # certificates were lost even there).  The ledger is live-net
        # filtered and replacement ordered, so accepted closures cannot leave
        # stale placement authority behind.
        post_route_refusal_evidence = _repair_attempt_completion_payload({
            "attempts": attempts,
            "final": before,
            "plan": plan,
        })
        plan["post_route_refusal_evidence"] = \
            copy.deepcopy(post_route_refusal_evidence)
        fresh_completion = {
            "unconn_nets": list(before.get("unconn_nets") or ()),
            "final_completion": post_route_refusal_evidence,
        }

        # If exact live evidence did not expose a generated via before route
        # replay, re-plan once from the richer post-route certificates.  Never
        # replay the same finite via ladder twice in one wave.
        if not early_congestion_via_attempted:
            generated_locked_uuids = _spawn_apply(
                _generated_locked_route_uuids, (current, authored_baseline))
            congestion_via_plan = _spawn_apply(
                _congestion_via_plan_worker,
                (current, fresh_completion, generated_locked_uuids, 4))
            congestion_via_plan["board"] = os.path.abspath(board_path)
            congestion_via_sweep = {
                "schema": 1, "targets": congestion_via_plan["targets"],
                "attempts": [], "accepted": [], "stop": "no_eligible_via",
                "schedule": "after_route_refusal_refresh",
            }
            for via_index, target_row in enumerate(
                    congestion_via_plan["targets"]):
                result = _attempt_congestion_via_relocation(
                    current, before, target_row, work_dir=work,
                    token="%02d" % via_index,
                    generated_locked_uuids=generated_locked_uuids,
                    effort=effort, max_candidates=8)
                congestion_via_sweep["attempts"].extend(result["attempts"])
                if not result["adopted"]:
                    congestion_via_sweep["stop"] = result.get(
                        "stop", "candidate_exhausted")
                    if effort.stop_reason:
                        break
                    continue
                before = result["after"]
                accepted.append(result["accepted"])
                congestion_via_sweep["accepted"].append(result["accepted"])
                congestion_via_sweep["stop"] = \
                    "accepted_one_remeasure_required"
                break
            congestion_via_plan["sweep"] = congestion_via_sweep
            plan["congestion_via_relocation"] = congestion_via_plan

        # Endpoint-owner motion has the broadest blast radius of every repair
        # degree available here.  It therefore runs only after local closure,
        # bounded track/via negotiation, and blocker restoration have all
        # reached a measured fixed point.  This ordering prevents a routable
        # fine-pitch escape from moving an otherwise valid controller and
        # invalidating every incident branch merely because its first dogbone
        # seat was occupied.  The move remains transactional and can still
        # recover genuinely sealed pin rings on a later-authority fallback.
        if early_owner_attempted:
            owner_plan = early_owner_plan
            owner_sweep = owner_plan["sweep"]
            owner_targets = []
        else:
            generated_locked_uuids = _spawn_apply(
                _generated_locked_route_uuids, (current, authored_baseline))
            owner_plan = _spawn_apply(
                _endpoint_owner_plan_worker, (current, fresh_completion, 4))
            owner_plan["board"] = os.path.abspath(board_path)
            owner_sweep = {
                "schema": 1, "targets": owner_plan["targets"],
                "attempts": [], "accepted": [],
                "stop": "no_eligible_owner",
            }
            owner_targets = owner_plan["targets"]
        for owner_index, target_row in enumerate(owner_targets):
            result = _attempt_footprint_relocation(
                current, before, target_row, work_dir=work,
                token="owner-%02d" % owner_index, effort=effort,
                max_candidates=6, stage_name="endpoint_owner_relocation",
                max_copper_pads=16, max_branch_tracks=64,
                generated_locked_uuids=generated_locked_uuids)
            owner_sweep["attempts"].extend(result["attempts"])
            if not result["adopted"]:
                owner_sweep["stop"] = result.get(
                    "stop", "candidate_exhausted")
                if effort.stop_reason:
                    break
                continue
            before = result["after"]
            accepted.append(result["accepted"])
            owner_sweep["accepted"].append(result["accepted"])
            owner_sweep["stop"] = "accepted_one_remeasure_required"
            break
        owner_plan["sweep"] = owner_sweep
        plan["endpoint_owner_relocation"] = owner_plan

        # KiCad occasionally leaves a locked tail/via that no longer belongs
        # to the final connectivity graph.  Prune only exact UUIDs from the
        # current DRC, follow the resulting cascade to a fixed point, and then
        # apply the same full-board monotonic admission used by every repair.
        dangling_trial = os.path.join(
            work, "dangling-%03d.kicad_pcb" % len(attempts))
        _copy_board_family(current, dangling_trial)
        if effort.claim("drc_dangling_cascade", stage_limit=1):
            changed, evidence = _spawn_dangling_cleanup(dangling_trial, 8)
            dangling_row = {"stage": "drc_dangling_cascade", **evidence}
            if changed:
                dangling_drc = os.path.join(
                    work, "dangling-%03d-drc.json" % len(attempts))
                _run_drc(dangling_trial, dangling_drc)
                after = _spawn_apply(
                    _score_worker, (dangling_trial, dangling_drc))
                ok, decision = _accepts(before, after)
                dangling_row.update({"after": after, "accepted": ok,
                                     "decision": decision})
                if ok:
                    _copy_board_family(dangling_trial, current)
                    before = after
                    accepted.append(dangling_row)
            else:
                dangling_row.update({"accepted": False,
                                     "decision": evidence.get("stop")})
        else:
            dangling_row = {
                "stage": "drc_dangling_cascade", "accepted": False,
                "decision": effort.stage_stop(
                    "drc_dangling_cascade", "effort_budget"),
            }
        attempts.append(dangling_row)

        _persist_placement_candidate_history(
            plan, locals().get("prior_footprint_candidates") or ())

        _copy_board_family(current, out_path)
        # Closure is followed by one bounded, provenance-aware route polish.
        # This is deliberately after the last certificate repair: otherwise a
        # successful final bridge can reintroduce Manhattan elbows after an
        # earlier cosmetic pass.  Authored locked copper is immutable; only
        # UUIDs proven absent from the authored baseline may be chamfered.
        route_polish = {
            "schema": 1, "adopted": False,
            "chosen": "baseline", "skipped": "effort_budget",
        }
        if effort.claim("route_polish", stage_limit=1):
            try:
                import cec_fab_repair
                route_polish = cec_fab_repair.repair_admitted(
                    out_path,
                    allow_locked_track_uuids=generated_locked_uuids)
                polish_row = {
                    "stage": "route_polish",
                    "accepted": bool(route_polish.get("adopted")),
                    "decision": route_polish.get("chosen"),
                    "after": route_polish.get("after"),
                }
                attempts.append(polish_row)
                if route_polish.get("adopted"):
                    before = dict(route_polish.get("after") or before)
                    accepted.append(polish_row)
            except Exception as exc:                     # noqa: BLE001
                route_polish = {
                    "schema": 1, "adopted": False,
                    "chosen": "baseline", "skipped": "repair_error",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
                attempts.append({
                    "stage": "route_polish", "accepted": False,
                    "decision": "repair_error",
                    "error": route_polish["error"],
                })
        final = dict(before)
        return {
            "schema": SCHEMA,
            "algorithm_revision": REPAIR_ALGORITHM_REVISION,
            "input": os.path.abspath(board_path),
            "output": os.path.abspath(out_path),
            "baseline": baseline,
            "final": final,
            "improvement": {
                "unconnected": baseline["unconnected"] - final["unconnected"],
                "drc": baseline["drc"] - final["drc"],
            },
            "plan": plan,
            "generated_locked_authority": {
                "authored_baseline": (os.path.abspath(authored_baseline)
                                       if authored_baseline else None),
                "eligible_uuid_count": len(generated_locked_uuids),
            },
            "attempts": attempts,
            "accepted": accepted,
            "drc_sweep": drc_sweep,
            "sensitive_drc_sweep": sensitive_drc_sweep,
            "via_sweep": via_sweep,
            "closure_sweep": closure_sweep,
            "route_polish": route_polish,
            "effort_budget": effort.report(),
            "changed": bool(accepted),
            "wall_s": round(time.monotonic() - started, 3),
        }
    except cec_process_pool.WorkerPoolStalled as exc:
        # A child capped by the transaction deadline is an expected bounded
        # stop, not grounds to discard earlier accepted work or its forensic
        # report.  Publish the last admitted ``current`` board and a compact
        # partial result.  Programming/data errors still propagate normally.
        elapsed = time.monotonic() - started
        if effort.stop_reason is None:
            effort.stop_reason = (
                "wall_budget" if elapsed >= max(0.0, float(wall_budget_s))
                else "worker_stalled")
            effort.stop_stage = "inflight_worker"
        if os.path.isfile(current):
            _copy_board_family(current, out_path)
        baseline_row = dict(locals().get("baseline") or {})
        final_row = dict(locals().get("before") or baseline_row)
        improvement = {}
        if baseline_row and final_row:
            improvement = {
                "unconnected": (baseline_row["unconnected"]
                                - final_row["unconnected"]),
                "drc": baseline_row["drc"] - final_row["drc"],
            }
        partial_plan = locals().get("plan") or {}
        _persist_placement_candidate_history(
            partial_plan,
            locals().get("prior_footprint_candidates") or ())
        return {
            "schema": SCHEMA,
            "algorithm_revision": REPAIR_ALGORITHM_REVISION,
            "input": os.path.abspath(board_path),
            "output": os.path.abspath(out_path),
            "baseline": baseline_row or None,
            "final": final_row or None,
            "improvement": improvement,
            "plan": partial_plan,
            "generated_locked_authority": {
                "authored_baseline": (os.path.abspath(authored_baseline)
                                       if authored_baseline else None),
                "eligible_uuid_count": len(
                    locals().get("generated_locked_uuids") or ()),
            },
            "attempts": attempts,
            "accepted": locals().get("accepted") or [],
            "effort_budget": effort.report(),
            "changed": bool(locals().get("accepted") or ()),
            "bounded_stop": {
                "stage": effort.stop_stage,
                "error": "%s: %s" % (
                    type(exc).__name__, str(exc)[:400]),
            },
            "wall_s": round(time.monotonic() - started, 3),
        }
    finally:
        _WORKER_DEADLINE.reset(deadline_token)
        shutil.rmtree(work, ignore_errors=True)


def _load_json(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", help="routed .kicad_pcb")
    parser.add_argument("out", help="accepted output .kicad_pcb")
    parser.add_argument("--completion", help="oracle/import completion JSON")
    parser.add_argument(
        "--authored-baseline",
        help=("pre-routing authored board; only locked route UUIDs absent "
              "from this baseline may enter generated-copper negotiation"))
    parser.add_argument("--report", help="write machine-readable repair report")
    parser.add_argument("--max-targets", type=int, default=4)
    parser.add_argument("--max-windows", type=int, default=8)
    parser.add_argument("--max-blockers-per-window", type=int, default=2)
    parser.add_argument("--max-detour-ratio", type=float, default=2.0)
    parser.add_argument("--max-attempts", type=int, default=64)
    parser.add_argument("--wall-budget-s", type=float, default=240.0)
    parser.add_argument("--no-deep-retry", action="store_true",
                        help="try one precise window geometry instead of two")
    parser.add_argument("--no-negotiate", action="store_true",
                        help="disable atomic blocked-net/rip-up transactions")
    parser.add_argument("--no-close", action="store_true",
                        help="repair blocker only; do not retry refused nets")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress stdout; useful for pipeline integration")
    args = parser.parse_args(argv)
    result = repair_board(
        os.path.abspath(args.board), os.path.abspath(args.out),
        _load_json(args.completion), max_targets=args.max_targets,
        close_blocked_nets=not args.no_close,
        negotiate=not args.no_negotiate, max_windows=args.max_windows,
        max_blockers_per_window=args.max_blockers_per_window,
        max_detour_ratio=args.max_detour_ratio,
        deep_retry=not args.no_deep_retry,
        max_attempts=args.max_attempts,
        wall_budget_s=args.wall_budget_s,
        authored_baseline=(os.path.abspath(args.authored_baseline)
                           if args.authored_baseline else None),
        verbose=args.verbose)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        Path(args.report).write_text(payload + "\n", encoding="utf-8")
    if not args.quiet:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
