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

import cec_fr
import cec_process_pool
import cec_score
import cec_stage_admission
import cec_toolchain as _tc


MM = 1_000_000
SCHEMA = 1
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


def _completion_payload(data: dict | None) -> dict:
    """Accept an oracle row, an import report, or a bare completion report."""

    row = data or {}
    if isinstance(row.get("completion_report"), dict):
        row = row["completion_report"]
    if isinstance(row.get("import_report"), dict):
        row = row["import_report"]
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
            # Keep the tuple shape compatible with ordinary window priorities;
            # the leading -1 makes this exact local proof precede broader
            # planar congestion surgery for the same refused net.
            priority = (-1, -len(vertical_movable), 0, 0, distance,
                        0, 0, len(vertical_movable), 2, distance,
                        -len(vertical_movable), net, chosen_ids)
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
    for row in _trapped_foreign_pad_blockers(completion):
        if live_unconnected and row["target_net"] not in live_unconnected:
            continue
        key = (row["target_net"], row["ref"], row["endpoint_ref"],
               row["endpoint_pad"])
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
                    row["target_net"], row["ref"])
        targets.append(FootprintRepairTarget(
            ref=row["ref"], target_net=row["target_net"],
            endpoint_ref=row["endpoint_ref"],
            endpoint_pad=row["endpoint_pad"],
            endpoint_x_mm=row["endpoint_x_mm"],
            endpoint_y_mm=row["endpoint_y_mm"],
            hit_count=row["hit_count"], distance_mm=row["distance_mm"],
            priority=priority))
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
            hits = sum(int(row.get("hit_count") or 1)
                       for row in cert.get("dominant_blockers") or ())
            distance = float(refusal["detail"].get("distance_mm") or 1e9)
            targets.append(FootprintRepairTarget(
                ref=ref, target_net=target_net, endpoint_ref=ref,
                endpoint_pad=str(endpoint.get("pad") or ""),
                endpoint_x_mm=float(endpoint["x_mm"]),
                endpoint_y_mm=float(endpoint["y_mm"]),
                hit_count=hits, distance_mm=distance,
                priority=(distance, -hits, target_net, ref)))
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
            targets.append({
                "target_net": target_net,
                "distance_mm": float(
                    refusal["detail"].get("distance_mm") or 1e9),
                "hit_count": int(blocker.get("hit_count") or 1),
                "via": asdict(target),
            })
    targets.sort(key=lambda row: tuple(row["via"]["priority"]))
    return {
        "schema": SCHEMA, "board": os.path.abspath(board_path),
        "targets": targets[:max(0, int(limit))], "immutable": immutable,
    }


def _find_track(board, uid: str):
    return next((item for item in board.GetTracks()
                 if item.GetClass() == "PCB_TRACK" and _uuid(item) == uid), None)


def _layer_candidates(board, source_layer: int) -> list[int]:
    plane = {board.GetLayerID(name) for name in cec_fr.plane_layers(board)}
    plane.discard(-1)
    all_cu = set(board.GetEnabledLayers().CuStack())
    return sorted((layer for layer in all_cu
                   if layer != source_layer and layer not in plane
                   and not any(role in board.GetLayerName(layer).upper()
                               for role in ("GND", "PWR"))),
                  key=lambda layer: (
                      0 if "SIG" in board.GetLayerName(layer).upper() else
                      1 if layer == pcbnew.B_Cu else 2,
                      layer))


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
            width, net_code, _layer_candidates(board, layer), clearance_nm,
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
                              max_detour_ratio: float = 2.0):
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
        maze_margin_mm=float(maze_margin_mm), foreign_cache={})
    if legs:
        operations = [("trk", a, b, leg_width, layer)
                      for a, b, leg_width in legs]
    else:
        mode = "bridge"
        operations = cec_fr._lastmile_bridge(
            board, (start.x, start.y), {layer}, (end.x, end.y), {layer},
            width, net_code, _layer_candidates(board, layer), clearance_nm,
            drill=float(spec.get("via_drill") or 0.3),
            dia=float(spec.get("via_diameter") or 0.6), leg_ok=edge_ok,
            start_escape=snapshot.get("start_escape"),
            end_escape=snapshot.get("end_escape"), seat_limit=8,
            allow_maze=True, maze_margin_mm=float(maze_margin_mm),
            foreign_cache={})
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
            "refusal": "displaced_branch_unrestorable",
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
    }


def _restore_displaced_net(board, snapshot, *, board_path: str,
                           maze_margin_mm: float):
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
    report = cec_fr.synthesize_lastmile(
        board, max_mm=max_mm, min_w=width_mm,
        clearance=clearance_mm, cap=8,
        netclass_resolver=resolver, include_nets={net},
        attempts_per_pair=24, maze_max_mm=max_mm,
        maze_margin_mm=float(maze_margin_mm))
    if not report.get("closed") or report.get("refused"):
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


def _close_negotiation_target(board, window: NegotiationWindow, *,
                              board_path: str, attempt_budget: int,
                              maze_margin_mm: float,
                              prefer_bridge: bool | None = None):
    """Phase 2: let the refused net claim the newly vacated corridor."""

    resolver = cec_fr._project_netclass_resolver(board_path)
    max_mm = max(25.0, min(80.0, float(window.distance_mm) + 8.0))
    completion = cec_fr.synthesize_lastmile(
        board, max_mm=max_mm,
        # ``min_w`` is the fabrication-qualified local neck-down floor, not
        # the target net's trunk width.  Feeding a 0.50 mm power width back as
        # the minimum disabled fine-pitch pad escapes during negotiation.
        min_w=min(0.25, max(0.15, window.width_mm)),
        clearance=max(0.2, window.clearance_mm), cap=12,
        netclass_resolver=resolver, include_nets={window.net},
        attempts_per_pair=int(attempt_budget), maze_max_mm=max_mm,
        maze_margin_mm=float(maze_margin_mm),
        prefer_bridge=(bool(window.local_pin_escape)
                       if prefer_bridge is None else bool(prefer_bridge)))
    if not completion.get("closed"):
        return False, {
            "stage": "close_blocked_net", "blocked_net": window.net,
            "refusal": "blocked_net_still_refused",
            "completion": completion,
        }
    return True, {"stage": "close_blocked_net",
                  "blocked_net": window.net, "completion": completion}


def _restore_negotiation_blockers(board, snapshot_rows, *, board_path: str,
                                  maze_margin_mm: float,
                                  max_detour_ratio: float,
                                  order_mode: str = "hardest_first"):
    """Phase 3: restore every displaced branch around the new target route."""

    restored = []
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
    for snapshot in snapshots:
        ok, evidence = _restore_displaced_branch(
            board, snapshot, board_path=board_path,
            maze_margin_mm=maze_margin_mm,
            max_detour_ratio=max_detour_ratio)
        if not ok:
            branch_refusal = evidence
            ok, evidence = _restore_displaced_net(
                board, snapshot, board_path=board_path,
                maze_margin_mm=maze_margin_mm)
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
    return _metric_row(
        cec_score.score(board_path, drc_json=drc_json), drc_data=drc_data)


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
    """Deterministic canonical displacement ladder, conflict-away first."""

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
    for step_mm in (0.20, 0.30, 0.45, 0.60, 0.80, 1.00, 1.40):
        step_nm = int(round(step_mm * MM))
        for dx, dy in unique:
            yield dx * step_nm, dy * step_nm, step_mm, (dx, dy)


def _relocate_via_worker(board_path, target_row, dx_nm, dy_nm,
                         generated_locked_uuids=()):
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
    if not branches:
        return False, {"refusal": "no_incident_route_stub"}

    new = pcbnew.VECTOR2I(int(old.x + dx_nm), int(old.y + dy_nm))
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
                              prefer_bridge=None):
    board = pcbnew.LoadBoard(board_path)
    window = NegotiationWindow(**window_row)
    changed, evidence = _close_negotiation_target(
        board, window, board_path=board_path,
        attempt_budget=attempt_budget, maze_margin_mm=margin,
        prefer_bridge=prefer_bridge)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return bool(changed), evidence


def _restore_negotiation_worker(board_path, snapshots, margin,
                                max_detour_ratio,
                                order_mode="hardest_first"):
    board = pcbnew.LoadBoard(board_path)
    changed, evidence = _restore_negotiation_blockers(
        board, snapshots, board_path=board_path,
        maze_margin_mm=margin, max_detour_ratio=max_detour_ratio,
        order_mode=order_mode)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return bool(changed), evidence


def _footprint_relocation_candidates(board_path, target_row):
    """Return a bounded route-aware seat ladder away from the trapped pad."""

    board = pcbnew.LoadBoard(board_path)
    target = FootprintRepairTarget(**target_row)
    fp = board.FindFootprintByReference(target.ref) if board is not None else None
    if fp is None:
        return []
    pos = fp.GetPosition()
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


def _relocate_footprint_worker(board_path, target_row, candidate,
                               max_branch_tracks=12, max_copper_pads=2,
                               generated_locked_uuids=()):
    """Move one certified support cell and vacate only its pad-attached stubs.

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
    pads = list(fp.Pads())
    copper_pads = [pad for pad in pads if pad.IsOnCopperLayer()]
    if (not copper_pads or len(copper_pads) > max(2, int(max_copper_pads))
            or any(pad.HasHole() for pad in copper_pads)):
        return False, {"refusal": "footprint_outside_relocation_scope"}

    generated_locked = {str(uid) for uid in generated_locked_uuids if uid}

    def point_key(point):
        return int(point.x), int(point.y)

    pad_rows = [(str(pad.GetNumber()), pad.GetNetname(), pad.GetNetCode(),
                 point_key(pad.GetCenter())) for pad in copper_pads]
    all_copper = list(board.GetTracks())
    pad_vias = {}
    for item in all_copper:
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        for pad_number, _net_name, net_code, node in pad_rows:
            if item.GetNetCode() == net_code and point_key(
                    item.GetPosition()) == node:
                pad_vias[pad_number] = item
    if any(via.IsLocked() and _uuid(via) not in generated_locked
           for via in pad_vias.values()):
        return False, {"refusal": "authored_locked_pad_via"}

    tracks_by_node = {}
    for item in all_copper:
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        net_code = item.GetNetCode()
        for point in (item.GetStart(), item.GetEnd()):
            tracks_by_node.setdefault(
                (net_code, point_key(point)), []).append(item)

    removed = {}
    anchors = []
    for pad_number, net_name, net_code, start in pad_rows:
        for item in tracks_by_node.get((net_code, start), ()):
            uid = _uuid(item)
            if not uid or uid in removed:
                continue
            if item.IsLocked() and uid not in generated_locked:
                return False, {
                    "refusal": "authored_locked_incident_branch",
                    "track_uuid": uid,
                }
            removed[uid] = item
            if len(removed) > max(1, int(max_branch_tracks)):
                return False, {"refusal": "incident_branch_too_broad",
                               "track_count": len(removed)}
            a, b = point_key(item.GetStart()), point_key(item.GetEnd())
            far = b if a == start else a
            anchors.append({
                "pad": pad_number,
                "net": net_name,
                "x_mm": round(far[0] / MM, 6),
                "y_mm": round(far[1] / MM, 6),
                "track_uuid": uid,
            })

    old_position = fp.GetPosition()
    old_rotation = fp.GetOrientationDegrees()
    fp.SetPosition(old_position + pcbnew.VECTOR2I_MM(
        float(candidate["dx_mm"]), float(candidate["dy_mm"])))
    fp.SetOrientationDegrees(
        old_rotation + float(candidate["rotation_delta_deg"]))
    new_pad_centers = {str(pad.GetNumber()): pad.GetCenter()
                       for pad in fp.Pads()}
    moved_vias = []
    for pad_number, via in pad_vias.items():
        via.SetPosition(new_pad_centers[pad_number])
        moved_vias.append(_uuid(via))
    for item in removed.values():
        board.Remove(item)
    board.BuildConnectivity()
    pcbnew.SaveBoard(board_path, board)
    return True, {
        "ref": target.ref,
        "old_position_mm": [round(old_position.x / MM, 6),
                            round(old_position.y / MM, 6)],
        "new_position_mm": [round(fp.GetPosition().x / MM, 6),
                            round(fp.GetPosition().y / MM, 6)],
        "old_rotation_deg": float(old_rotation),
        "new_rotation_deg": float(fp.GetOrientationDegrees()),
        "removed_tracks": len(removed),
        "preserved_anchors": anchors,
        "moved_pad_via_uuids": sorted(uid for uid in moved_vias if uid),
        "affected_nets": sorted({name for _pad, name, _code, _node in pad_rows
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


def _lastmile_worker(board_path, target_nets, attempt_budget, margin,
                     prefer_bridge=False):
    board = pcbnew.LoadBoard(board_path)
    resolver = cec_fr._project_netclass_resolver(board_path)
    report = cec_fr.synthesize_lastmile(
        board, max_mm=25.0, min_w=0.25, clearance=0.25, cap=8,
        netclass_resolver=resolver, include_nets=set(target_nets),
        attempts_per_pair=int(attempt_budget), maze_max_mm=25.0,
        maze_margin_mm=float(margin), prefer_bridge=bool(prefer_bridge))
    if report.get("closed"):
        pcbnew.SaveBoard(board_path, board)
        report["endpoint_neckdown_rule"] = \
            cec_fr.ensure_endpoint_neckdown_rule(board_path, report)
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
    report = cec_fr.synthesize_lastmile(
        board, max_mm=80.0, min_w=0.2, clearance=0.2, cap=64,
        netclass_resolver=resolver, include_nets=set(target_nets),
        attempts_per_pair=8, maze_max_mm=0.0, maze_margin_mm=2.0)
    if report.get("closed"):
        pcbnew.SaveBoard(board_path, board)
        report["endpoint_neckdown_rule"] = \
            cec_fr.ensure_endpoint_neckdown_rule(board_path, report)
    return report


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
                board.Remove(item)
            pcbnew.SaveBoard(board_path, board)
    return bool(removed), {
        "schema": 1,
        "removed": removed,
        "removed_count": len(removed),
        "iterations": (max((row["iteration"] for row in removed), default=-1)
                       + 1),
        "stop": stop,
    }


def _attempt_footprint_relocation(board_path, before, target_row, *,
                                  work_dir, token, effort=None,
                                  max_candidates=8,
                                  stage_name="footprint_relocation",
                                  max_copper_pads=2,
                                  max_branch_tracks=12,
                                  generated_locked_uuids=()):
    """Try one trapped-pin support-cell re-seat as an atomic transaction."""

    target = FootprintRepairTarget(**target_row)
    candidates = _footprint_relocation_candidates(board_path, target_row)
    rows = []
    target_closed_seen = False
    for index, candidate in enumerate(candidates[:max(0, int(max_candidates))]):
        if effort is not None and not effort.claim(
                stage_name, stage_limit=max_candidates):
            break
        trial = os.path.join(
            work_dir, "footprint-%s-%02d.kicad_pcb" % (token, index))
        _copy_board_family(board_path, trial)
        row = {"stage": stage_name, "target": target_row,
               "candidate": candidate}
        try:
            changed, move = _spawn_apply(
                _relocate_footprint_worker,
                (trial, target_row, candidate, max_branch_tracks,
                 max_copper_pads, tuple(generated_locked_uuids)),
                timeout_s=25.0)
            row["move"] = move
            if not changed:
                row.update({"accepted": False,
                            "decision": move.get("refusal")})
                rows.append(row)
                continue

            target_report = _spawn_apply(
                _lastmile_worker,
                (trial, (target.target_net,), 24, 8.0), timeout_s=20.0)
            row["target_completion"] = target_report
            if not target_report.get("closed"):
                row.update({"accepted": False,
                            "decision": "target_still_refused"})
                rows.append(row)
                if index >= 5 and not target_closed_seen:
                    break
                continue
            target_closed_seen = True

            affected = tuple(sorted(
                net for net in (move.get("affected_nets") or ())
                if net and net != target.target_net
                and not _is_gnd_net(net)))
            if affected:
                row["support_completion"] = _spawn_apply(
                    _lastmile_worker, (trial, affected, 24, 8.0),
                    timeout_s=30.0)
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
            after = _spawn_apply(_score_worker, (trial, drc_path))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            rows.append(row)
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
            rows.append(row)
    return {"adopted": False, "attempts": rows,
            "stop": (effort.stage_stop(
                stage_name, "candidate_exhausted")
                if effort is not None else "candidate_exhausted")}


def _attempt_congestion_via_relocation(
        board_path, before, target_row, *, work_dir, token,
        generated_locked_uuids=(), effort=None, max_candidates=8):
    """Move one refusal-named via, then close and score the blocked net."""

    via_row = dict(target_row["via"])
    target = ViaRepairTarget(**via_row)
    rows = []
    offsets = list(_via_offset_candidates(target))[:max(0, int(max_candidates))]
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
    bridge_first = bool(window.local_pin_escape)
    variants = [(12, 4.0, 2, bridge_first)]
    # A via-first local escape can legally close the target while occupying
    # the only corridor available to a displaced neighbour.  Enumerate the
    # inverse topology once before spending effort on a larger maze.  This is
    # a generic route-order/topology search, not permission to relax geometry.
    if bridge_first:
        variants.append((12, 4.0, 2, False))
    if deep_retry:
        # Board-scale residuals often fail because the shortest-path bounding
        # box is physically partitioned by fixed pours or connector fields.
        # Spending the retry on more endpoint-anchor combinations inside that
        # same box is both slow and ineffective.  Escalate corridor breadth
        # first, using one deterministic nearest-anchor attempt.  The cap is
        # deliberately finite and the full transaction still has to restore
        # every displaced branch and pass exact whole-board admission.
        breadth_margin = min(
            20.0, max(8.0, round(float(window.distance_mm) * 0.55, 1)))
        variants.append((1, breadth_margin, 4, bridge_first))
        # If one nearest-anchor attempt proves the broader search domain is
        # still insufficient, search a board-scale corridor with a small
        # anchor set.  This remains far cheaper than the old 24-anchor retry,
        # while preserving enough endpoint diversity for dense pin fields.
        board_scale_margin = min(
            25.0, max(12.0, round(float(window.distance_mm) + 8.0, 1)))
        variants.append((4, board_scale_margin, 4, bridge_first))
    rows = []
    for variant, (attempt_budget, margin, branch_hops,
                  prefer_bridge) in enumerate(variants):
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
            closed, close_evidence = _spawn_apply(
                _close_negotiation_worker,
                (trial, window_row, attempt_budget, margin,
                 prefer_bridge),
                # A single difficult residual must not monopolize an entire
                # unattended wave.  Initial certificate windows get the same
                # bounded effort as the ordinary last-mile stage; an explicit
                # deep retry earns one larger slice.  Timeout is a refusal for
                # this candidate, never permission to weaken geometry.
                timeout_s=(45.0 if (attempt_budget > 12 or margin >= 12.0)
                           else 25.0))
            row["phases"]["close"] = close_evidence
            if not closed:
                row.update({"accepted": False,
                            "decision": close_evidence.get("refusal")})
                rows.append(row)
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
            for restore_index, order_mode in enumerate(
                    ("hardest_first", "easiest_first")):
                if restore_index:
                    _copy_board_family(restore_seed, trial)
                restored, restore_evidence = _spawn_apply(
                    _restore_negotiation_worker,
                    (trial, snapshots, margin, max_detour_ratio,
                     order_mode))
                restore_attempts.append(dict(restore_evidence))
                if restored:
                    break
            row["phases"]["restore_attempts"] = restore_attempts
            row["phases"]["restore"] = restore_evidence
            if not restored:
                row.update({"accepted": False,
                            "decision": restore_evidence.get("refusal")})
                rows.append(row)
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
        plan = _spawn_apply(
            _plan_worker, (current, completion, drc_data, max_targets))
        negotiation_plan = _spawn_apply(
            _negotiation_plan_worker,
            (current, completion, max_windows,
             max_blockers_per_window, generated_locked_uuids))
        # The worker planned against an isolated scratch copy.  Publish the
        # stable caller-visible identity, not a path removed in ``finally``.
        plan["board"] = os.path.abspath(board_path)
        negotiation_plan["board"] = os.path.abspath(board_path)
        plan["negotiation"] = negotiation_plan
        before = _spawn_apply(_score_worker, (current, drc_path))
        baseline = dict(before)
        accepted = []

        # Route refusal can prove that the copper search is not the remaining
        # degree of freedom: a small support footprint inherited from an older
        # or authored placement may physically seal every surface escape from
        # a fine-pitch pad.  Consume that evidence before repeatedly ripping
        # up unrelated tracks.  The entire footprint/pad-via/incident-branch
        # move is transactional and must restore its support nets, improve the
        # full-board score, and preserve every pair/topology gate.
        footprint_plan = _spawn_apply(
            _footprint_plan_worker, (current, completion, 4))
        footprint_plan["board"] = os.path.abspath(board_path)
        footprint_sweep = {"schema": 1, "targets": footprint_plan["targets"],
                           "attempts": [], "accepted": [],
                           "stop": "no_eligible_trapped_support"}
        for footprint_index, target_row in enumerate(
                footprint_plan["targets"]):
            result = _attempt_footprint_relocation(
                current, before, target_row, work_dir=work,
                token="%02d" % footprint_index, effort=effort,
                max_candidates=8,
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
        if close_blocked_nets and accepted:
            target_nets = set(accepted[-1]["target"].get("blocked_nets") or ())
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
        }
        fresh_completion = {
            "unconn_nets": list(before.get("unconn_nets") or ()),
            "final_completion": {},
        }
        for closure_round in range(3):
            if not effort.claim("broad_canonical_closure", stage_limit=3):
                closure_sweep["stop"] = effort.stage_stop(
                    "broad_canonical_closure", "round_budget")
                break
            target_nets = tuple(sorted(before.get("unconn_nets") or ()))
            if not target_nets:
                closure_sweep["stop"] = "connectivity_closed"
                break
            trial = os.path.join(
                work, "closure-%02d-%03d.kicad_pcb" %
                (closure_round, len(attempts)))
            _copy_board_family(current, trial)
            completion_report = _spawn_apply(
                _broad_canonical_worker, (trial, target_nets))
            fresh_completion = {
                "unconn_nets": list(before.get("unconn_nets") or ()),
                "final_completion": completion_report,
            }
            row = {
                "stage": "broad_canonical_closure",
                "round": closure_round,
                "nets": list(target_nets),
                "completion": completion_report,
            }
            round_row = {
                "round": closure_round,
                "closed": int(completion_report.get("closed") or 0),
                "accepted": False,
            }
            closure_sweep["rounds"].append(round_row)
            if not completion_report.get("closed"):
                row.update({"accepted": False,
                            "decision": "fixed_point_no_closure"})
                attempts.append(row)
                closure_sweep["stop"] = "fixed_point_no_closure"
                break
            try:
                _spawn_apply(_refill_worker, (trial,))
            except Exception as exc:                 # noqa: BLE001
                row["refill_warning"] = "%s: %s" % (
                    type(exc).__name__, exc)
            trial_drc = os.path.join(
                work, "closure-%02d-%03d-drc.json" %
                (closure_round, len(attempts)))
            _run_drc(trial, trial_drc)
            after = _spawn_apply(_score_worker, (trial, trial_drc))
            ok, decision = _accepts(before, after)
            row.update({"after": after, "accepted": ok,
                        "decision": decision})
            attempts.append(row)
            if not ok:
                closure_sweep["stop"] = "candidate_rejected"
                break
            _copy_board_family(trial, current)
            before = after
            accepted.append(row)
            round_row.update({
                "accepted": True, "decision": decision,
                "after_drc": after["drc"],
                "after_unconnected": after["unconnected"],
            })
            fresh_completion["unconn_nets"] = list(
                before.get("unconn_nets") or ())
            if verbose:
                print("[certificate-repair] broad closure round %s: "
                      "drc=%s unconnected=%s" %
                      (closure_round, after["drc"], after["unconnected"]),
                      file=sys.stderr, flush=True)

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
                for closure_round in range(2):
                    if not effort.claim(
                            "post_negotiation_closure", stage_limit=2):
                        post_negotiation_closure["stop"] = effort.stage_stop(
                            "post_negotiation_closure", "round_budget")
                        break
                    target_nets = tuple(sorted(
                        before.get("unconn_nets") or ()))
                    if not target_nets:
                        post_negotiation_closure["stop"] = \
                            "connectivity_closed"
                        break
                    trial = os.path.join(
                        work, "post-negotiate-%02d-%03d.kicad_pcb" %
                        (closure_round, len(attempts)))
                    _copy_board_family(current, trial)
                    completion_report = _spawn_apply(
                        _broad_canonical_worker, (trial, target_nets))
                    fresh_completion = {
                        "unconn_nets": list(
                            before.get("unconn_nets") or ()),
                        "final_completion": completion_report,
                    }
                    row = {
                        "stage": "post_negotiation_closure",
                        "round": closure_round,
                        "nets": list(target_nets),
                        "completion": completion_report,
                    }
                    round_row = {
                        "round": closure_round,
                        "closed": int(
                            completion_report.get("closed") or 0),
                        "accepted": False,
                    }
                    post_negotiation_closure["rounds"].append(round_row)
                    if not completion_report.get("closed"):
                        row.update({"accepted": False,
                                    "decision": "fixed_point_no_closure"})
                        attempts.append(row)
                        post_negotiation_closure["stop"] = \
                            "fixed_point_no_closure"
                        break
                    try:
                        _spawn_apply(_refill_worker, (trial,))
                    except Exception as exc:         # noqa: BLE001
                        row["refill_warning"] = "%s: %s" % (
                            type(exc).__name__, exc)
                    trial_drc = os.path.join(
                        work, "post-negotiate-%02d-%03d-drc.json" %
                        (closure_round, len(attempts)))
                    _run_drc(trial, trial_drc)
                    after = _spawn_apply(
                        _score_worker, (trial, trial_drc))
                    ok, decision = _accepts(before, after)
                    row.update({"after": after, "accepted": ok,
                                "decision": decision})
                    attempts.append(row)
                    if not ok:
                        post_negotiation_closure["stop"] = \
                            "candidate_rejected"
                        break
                    _copy_board_family(trial, current)
                    before = after
                    accepted.append(row)
                    fresh_completion["unconn_nets"] = list(
                        before.get("unconn_nets") or ())
                    round_row.update({
                        "accepted": True, "decision": decision,
                        "after_drc": after["drc"],
                        "after_unconnected": after["unconnected"],
                    })
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
                for closure_round in range(2):
                    if not effort.claim(
                            "negotiation_cycle_closure", stage_limit=4):
                        negotiation_sweep["stop"] = effort.stage_stop(
                            "negotiation_cycle_closure", "round_budget")
                        break
                    target_nets = tuple(sorted(
                        before.get("unconn_nets") or ()))
                    if not target_nets:
                        fresh_completion = {
                            "unconn_nets": [], "final_completion": {},
                        }
                        break
                    trial = os.path.join(
                        work, "cycle-%02d-close-%02d-%03d.kicad_pcb" %
                        (negotiation_round, closure_round, len(attempts)))
                    _copy_board_family(current, trial)
                    completion_report = _spawn_apply(
                        _broad_canonical_worker, (trial, target_nets))
                    fresh_completion = {
                        "unconn_nets": list(
                            before.get("unconn_nets") or ()),
                        "final_completion": completion_report,
                    }
                    row = {
                        "stage": "negotiation_cycle_closure",
                        "negotiation_round": negotiation_round,
                        "round": closure_round,
                        "nets": list(target_nets),
                        "completion": completion_report,
                    }
                    if not completion_report.get("closed"):
                        row.update({"accepted": False,
                                    "decision": "fixed_point_no_closure"})
                        attempts.append(row)
                        break
                    try:
                        _spawn_apply(_refill_worker, (trial,))
                    except Exception as exc:         # noqa: BLE001
                        row["refill_warning"] = "%s: %s" % (
                            type(exc).__name__, exc)
                    trial_drc = os.path.join(
                        work, "cycle-%02d-close-%02d-%03d-drc.json" %
                        (negotiation_round, closure_round, len(attempts)))
                    _run_drc(trial, trial_drc)
                    after = _spawn_apply(
                        _score_worker, (trial, trial_drc))
                    ok, decision = _accepts(before, after)
                    row.update({"after": after, "accepted": ok,
                                "decision": decision})
                    attempts.append(row)
                    if not ok:
                        break
                    _copy_board_family(trial, current)
                    before = after
                    accepted.append(row)
                    fresh_completion["unconn_nets"] = list(
                        before.get("unconn_nets") or ())
            plan["negotiation_sweep"] = negotiation_sweep

        # A via is a broader degree of freedom than negotiating the exact
        # certificate-named track branches.  Try it only after the atomic
        # route transaction reaches a fixed point.  The barrel must still be
        # refusal-named, off-pad, electrically ordinary, and generated by this
        # pipeline before its stubs can move as one scored transaction.
        generated_locked_uuids = _spawn_apply(
            _generated_locked_route_uuids, (current, authored_baseline))
        congestion_via_plan = _spawn_apply(
            _congestion_via_plan_worker,
            (current, fresh_completion, generated_locked_uuids, 4))
        congestion_via_plan["board"] = os.path.abspath(board_path)
        congestion_via_sweep = {
            "schema": 1, "targets": congestion_via_plan["targets"],
            "attempts": [], "accepted": [], "stop": "no_eligible_via",
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
        generated_locked_uuids = _spawn_apply(
            _generated_locked_route_uuids, (current, authored_baseline))
        owner_plan = _spawn_apply(
            _endpoint_owner_plan_worker, (current, fresh_completion, 4))
        owner_plan["board"] = os.path.abspath(board_path)
        owner_sweep = {
            "schema": 1, "targets": owner_plan["targets"],
            "attempts": [], "accepted": [], "stop": "no_eligible_owner",
        }
        for owner_index, target_row in enumerate(owner_plan["targets"]):
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

        _copy_board_family(current, out_path)
        final = dict(before)
        return {
            "schema": SCHEMA,
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
        return {
            "schema": SCHEMA,
            "input": os.path.abspath(board_path),
            "output": os.path.abspath(out_path),
            "baseline": baseline_row or None,
            "final": final_row or None,
            "improvement": improvement,
            "plan": locals().get("plan") or {},
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
