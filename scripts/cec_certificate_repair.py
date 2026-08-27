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
import cec_toolchain as _tc


MM = 1_000_000
SCHEMA = 1


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


def plan_negotiations(board_path: str, completion: dict | None, *,
                      limit: int = 8,
                      max_blockers_per_window: int = 2) -> dict:
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
    windows = []
    immutable = []
    seen = set()
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
        movable = []
        local_immutable = []
        fixed_blocker_hits = 0
        used = set()
        for blocker in cert.get("dominant_blockers") or ():
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
            entry = {
                "uuid": uid, "net": item.GetNetname() or "",
                "layer": layer, "hit_count": int(
                    blocker.get("hit_count") or 1),
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
        movable.sort(key=lambda entry: (-entry["hit_count"], entry["uuid"]))
        chosen = movable[:max_blockers]
        key = (net, tuple(entry["uuid"] for entry in chosen))
        if key in seen:
            continue
        seen.add(key)
        endpoints = tuple({key2: endpoint.get(key2)
                           for key2 in ("endpoint", "kind", "ref", "pad", "uuid",
                                        "x_mm", "y_mm")
                           if endpoint.get(key2) is not None}
                          for endpoint in (cert.get("endpoints") or ()))
        distance = float(row["detail"].get("distance_mm") or 1e9)
        hit_total = sum(entry["hit_count"] for entry in chosen)
        escape_rays = {}
        for layer_row in cert.get("layers") or ():
            for endpoint_row in layer_row.get("endpoint_escape") or ():
                label = str(endpoint_row.get("endpoint") or "")
                if label:
                    escape_rays.setdefault(label, set()).update(
                        endpoint_row.get("clear_rays") or ())
        trapped = sum(not rays for rays in escape_rays.values())
        # Prefer endpoints with a proven escape ray and no fixed pad/zone/pair
        # obstruction.  Within that feasibility class, close reference and
        # supply continuity before ordinary controls: a professional route
        # plan must not bury a ground or power island behind a shorter GPIO.
        omitted = max(0, len(movable) - len(chosen))
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
        priority = (trapped, role_priority, omitted,
                    fixed_blocker_hits, len(chosen),
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
            endpoints=endpoints, priority=priority))
    windows.sort(key=lambda window: window.priority)
    immutable.sort(key=lambda entry: (
        str(entry.get("blocked_net") or entry.get("net") or ""),
        str(entry.get("uuid") or "")))
    return {
        "schema": SCHEMA,
        "board": os.path.abspath(board_path),
        "certificates": len(refusal_certificates(completion)),
        "windows": [asdict(window)
                    for window in windows[:max(0, int(limit))]],
        "immutable": immutable,
        "max_blockers_per_window": max_blockers,
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
            tracks += 1
    board.BuildConnectivity()
    return {"tracks": tracks, "vias": vias}


def _candidate_ops(board, target: RepairTarget, *, board_path: str, mode: str,
                   maze_margin_mm: float) -> tuple[list | None, dict]:
    requested_mode = mode
    item = _find_track(board, target.uuid)
    if item is None:
        return None, {"refusal": "target_track_missing"}
    if item.IsLocked():
        return None, {"refusal": "target_became_locked"}
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
    }
    if not operations:
        evidence["refusal"] = "no_exact_clear_local_path"
        return None, evidence
    evidence["new_geometry"] = _lay_ops(board, operations, net_code)
    evidence["new_length_mm"] = round(sum(
        math.hypot(op[2].x - op[1].x, op[2].y - op[1].y) / MM
        for op in operations if op[0] != "via"), 6)
    return operations, evidence


def _snapshot_displaced_branch(board, uid: str, *, max_hops: int = 2):
    """Describe one certificate-named local branch before any mutation."""

    item = _find_track(board, uid)
    if item is None:
        return None, "target_track_missing_or_coalesced"
    net = item.GetNetname() or ""
    layer = board.GetLayerName(item.GetLayer())
    reason = protected_net_reason(
        net, width_mm=item.GetWidth() / MM, layer=layer,
        locked=item.IsLocked())
    if reason:
        return None, reason
    branch = _expanded_branch(board, item, max_hops=max_hops)
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
        "_track_objects": tuple(branch["tracks"]),
    }
    return snapshot, None


def _merge_overlapping_snapshots(snapshots):
    """Coalesce overlapping degree-2 branch snapshots into restorable paths."""

    groups = []
    for snapshot in snapshots:
        ids = set(snapshot["removed_uuids"])
        touching = [group for group in groups if ids & group["ids"]]
        if not touching:
            groups.append({"ids": set(ids), "rows": [snapshot]})
            continue
        primary = touching[0]
        primary["ids"].update(ids)
        primary["rows"].append(snapshot)
        for other in touching[1:]:
            primary["ids"].update(other["ids"])
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
            return None, "overlap_is_not_degree2_path"
        start_key, end_key = boundary
        width = max(item.GetWidth() for item in objects.values())

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
        return False, {"net": snapshot["net"], "mode": mode,
                       "refusal": "displaced_branch_unrestorable"}
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
    geometry = _lay_ops(board, operations, net_code)
    return True, {
        "net": snapshot["net"], "mode": mode,
        "requested_uuid": snapshot["requested_uuid"],
        "removed_uuids": list(snapshot["removed_uuids"]),
        "source_length_mm": round(source_length_nm / MM, 6),
        "new_length_mm": round(new_length_nm / MM, 6),
        "geometry": geometry,
    }


def _snapshot_row(snapshot) -> dict:
    """Convert a removed-branch boundary to a process-safe JSON row."""

    return {
        key: snapshot[key]
        for key in ("requested_uuid", "net", "net_code", "layer", "width",
                    "start_escape", "end_escape", "source_length_nm",
                    "removed_uuids")
    } | {
        "start_xy": [snapshot["start"].x, snapshot["start"].y],
        "end_xy": [snapshot["end"].x, snapshot["end"].y],
    }


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
    for uid in window.blocker_uuids:
        snapshot, refusal = _snapshot_displaced_branch(
            board, uid, max_hops=branch_hops)
        if snapshot is None:
            return False, {"stage": "remove_blockers", "refusal": refusal,
                           "blocked_net": window.net, "blocker_uuid": uid}, []
        snapshots.append(snapshot)
    if not snapshots:
        return False, {"stage": "remove_blockers",
                       "refusal": "no_movable_blocker_branch",
                       "blocked_net": window.net}, []
    raw_count = len(snapshots)
    snapshots, merge_refusal = _merge_overlapping_snapshots(snapshots)
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
                              maze_margin_mm: float):
    """Phase 2: let the refused net claim the newly vacated corridor."""

    resolver = cec_fr._project_netclass_resolver(board_path)
    max_mm = max(25.0, min(80.0, float(window.distance_mm) + 8.0))
    completion = cec_fr.synthesize_lastmile(
        board, max_mm=max_mm, min_w=max(0.15, window.width_mm),
        clearance=max(0.2, window.clearance_mm), cap=12,
        netclass_resolver=resolver, include_nets={window.net},
        attempts_per_pair=int(attempt_budget), maze_max_mm=max_mm,
        maze_margin_mm=float(maze_margin_mm))
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
                                  max_detour_ratio: float):
    """Phase 3: restore every displaced branch around the new target route."""

    restored = []
    # Restore the geometrically hardest branch first while all of its original
    # alternatives are still available; later branches see both the newly
    # claimed target route and every earlier restoration as real obstacles.
    snapshots = [_snapshot_from_row(row) for row in snapshot_rows]
    snapshots.sort(key=lambda row: (-row["width"],
                                    -row["source_length_nm"], row["net"]))
    for snapshot in snapshots:
        ok, evidence = _restore_displaced_branch(
            board, snapshot, board_path=board_path,
            maze_margin_mm=maze_margin_mm,
            max_detour_ratio=max_detour_ratio)
        restored.append(evidence)
        if not ok:
            return False, {
                "stage": "restore_blockers",
                "refusal": evidence.get("refusal"),
                "restored": restored,
            }
    board.BuildConnectivity()
    return True, {
        "stage": "restore_blockers", "restored": restored,
    }


def _metric_row(metrics, drc_data=None) -> dict:
    row = {
        "unconnected": int(metrics.unconnected),
        "unconn_nets": sorted(metrics.detail.get("unconn_nets") or ()),
        "drc": int(metrics.drc),
        "kelvin_ok": bool(metrics.kelvin_ok),
        "diffpair_ok": bool(metrics.diffpair_ok),
        "vias": int(metrics.vias),
        "tracks": int(metrics.tracks),
        "length_mm": round(float(metrics.length), 3),
        "drc_types": dict(metrics.drc_types),
    }
    if drc_data is not None:
        row["structural_drc_identities"] = _structural_drc_identities(
            drc_data)
    return row


def _accepts(before, after) -> tuple[bool, str]:
    if before["kelvin_ok"] and not after["kelvin_ok"]:
        return False, "kelvin_gate_regressed"
    if before["diffpair_ok"] and not after["diffpair_ok"]:
        return False, "diffpair_gate_regressed"
    if after["unconnected"] > before["unconnected"]:
        return False, "unconnected_regressed"
    new_unconnected = (set(after.get("unconn_nets") or ())
                       - set(before.get("unconn_nets") or ()))
    if new_unconnected:
        return False, "new_unconnected_nets"
    if after["drc"] > before["drc"]:
        return False, "drc_regressed"
    before_faults = set(before.get("structural_drc_identities") or ())
    after_faults = set(after.get("structural_drc_identities") or ())
    if after_faults - before_faults:
        return False, "new_structural_drc_identity"
    if ((after["unconnected"], after["drc"])
            >= (before["unconnected"], before["drc"])):
        return False, "no_structural_improvement"
    return True, "strict_structural_improvement"


def _spawn_apply(func, args):
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

    raw_timeout = os.environ.get("CEC_CERTIFICATE_WORKER_TIMEOUT_S", "300")
    try:
        wall_timeout_s = max(1.0, float(raw_timeout))
    except (TypeError, ValueError):
        wall_timeout_s = 300.0
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


def _plan_worker(board_path, completion, drc_data, limit):
    return plan_repairs(board_path, completion, drc_data=drc_data, limit=limit)


def _negotiation_plan_worker(board_path, completion, limit, max_blockers):
    return plan_negotiations(
        board_path, completion, limit=limit,
        max_blockers_per_window=max_blockers)


def _score_worker(board_path, drc_json):
    with open(drc_json, encoding="utf-8") as source:
        drc_data = json.load(source)
    return _metric_row(
        cec_score.score(board_path, drc_json=drc_json), drc_data=drc_data)


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


def _relocate_via_worker(board_path, target_row, dx_nm, dy_nm):
    """Move one DRC-named via and canonically rebuild every incident stub."""

    board = pcbnew.LoadBoard(board_path)
    target = ViaRepairTarget(**target_row)
    route_items = {_uuid(item): item for item in board.GetTracks() if _uuid(item)}
    via = route_items.get(target.uuid)
    if via is None or via.GetClass() != "PCB_VIA":
        return False, {"refusal": "target_via_missing"}
    if via.IsLocked():
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
        if item.GetClass() != "PCB_TRACK" or item.IsLocked():
            unsupported.append(_uuid(item))
            continue
        other = end if at_start else start
        branches.append({
            "other": pcbnew.VECTOR2I(int(other.x), int(other.y)),
            "width": int(item.GetWidth()), "layer": int(item.GetLayer()),
            "locked": bool(item.IsLocked()), "uuid": _uuid(item),
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
            generated.append({
                "layer": board.GetLayerName(layer),
                "width_mm": round(leg_width / MM, 6),
                "start": [round(start.x / MM, 6), round(start.y / MM, 6)],
                "end": [round(end.x / MM, 6), round(end.y / MM, 6)],
            })
        board.BuildConnectivity()
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


def _close_negotiation_worker(board_path, window_row, attempt_budget, margin):
    board = pcbnew.LoadBoard(board_path)
    window = NegotiationWindow(**window_row)
    changed, evidence = _close_negotiation_target(
        board, window, board_path=board_path,
        attempt_budget=attempt_budget, maze_margin_mm=margin)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return bool(changed), evidence


def _restore_negotiation_worker(board_path, snapshots, margin,
                                max_detour_ratio):
    board = pcbnew.LoadBoard(board_path)
    changed, evidence = _restore_negotiation_blockers(
        board, snapshots, board_path=board_path,
        maze_margin_mm=margin, max_detour_ratio=max_detour_ratio)
    if changed:
        pcbnew.SaveBoard(board_path, board)
    return bool(changed), evidence


def _refill_worker(board_path):
    cec_fr.refill_zones(board_path)
    return True


def _lastmile_worker(board_path, target_nets, attempt_budget, margin):
    board = pcbnew.LoadBoard(board_path)
    resolver = cec_fr._project_netclass_resolver(board_path)
    report = cec_fr.synthesize_lastmile(
        board, max_mm=25.0, min_w=0.25, clearance=0.25, cap=8,
        netclass_resolver=resolver, include_nets=set(target_nets),
        attempts_per_pair=int(attempt_budget), maze_max_mm=25.0,
        maze_margin_mm=float(margin))
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
    variants = [(12, 4.0, 2)]
    if deep_retry:
        variants.append((24, 8.0, 4))
    rows = []
    for variant, (attempt_budget, margin, branch_hops) in enumerate(variants):
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
                (trial, window_row, attempt_budget, margin))
            row["phases"]["close"] = close_evidence
            if not closed:
                row.update({"accepted": False,
                            "decision": close_evidence.get("refusal")})
                rows.append(row)
                continue
            restored, restore_evidence = _spawn_apply(
                _restore_negotiation_worker,
                (trial, snapshots, margin, max_detour_ratio))
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
            cleaned, cleanup_evidence = _spawn_apply(
                _drc_dangling_cleanup_worker, (trial, 8))
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
                 verbose: bool = False) -> dict:
    """Run the guarded repair ladder and write the best accepted artifact."""

    started = time.monotonic()
    work = tempfile.mkdtemp(prefix="cec_cert_repair_")
    attempts = []
    effort = RepairEffortBudget(
        max_attempts=max_attempts, wall_budget_s=wall_budget_s,
        started=started)
    try:
        current = os.path.join(work, "current.kicad_pcb")
        _copy_board_family(board_path, current)
        drc_path = os.path.join(work, "baseline-drc.json")
        drc_data = _run_drc(current, drc_path)
        plan = _spawn_apply(
            _plan_worker, (current, completion, drc_data, max_targets))
        negotiation_plan = _spawn_apply(
            _negotiation_plan_worker,
            (current, completion, max_windows,
             max_blockers_per_window))
        # The worker planned against an isolated scratch copy.  Publish the
        # stable caller-visible identity, not a path removed in ``finally``.
        plan["board"] = os.path.abspath(board_path)
        negotiation_plan["board"] = os.path.abspath(board_path)
        plan["negotiation"] = negotiation_plan
        before = _spawn_apply(_score_worker, (current, drc_path))
        baseline = dict(before)
        accepted = []

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
            fresh_negotiation_plan = _spawn_apply(
                _negotiation_plan_worker,
                (current, fresh_completion, max_windows,
                 max_blockers_per_window))
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
            negotiation_variants = [(12, 4.0, 2)]
            if deep_retry:
                negotiation_variants.append((24, 8.0, 4))
            adopted_window = False
            for window_row in fresh_negotiation_plan["windows"]:
                window = NegotiationWindow(**window_row)
                for attempt_budget, margin, branch_hops in negotiation_variants:
                    if not effort.claim(
                            "atomic_negotiation", stage_limit=12):
                        break
                    trial = os.path.join(
                        work, "negotiate-%03d.kicad_pcb" % len(attempts))
                    _copy_board_family(current, trial)
                    row = {"stage": "atomic_negotiation",
                           "window": asdict(window), "phases": {}}
                    try:
                        removed, remove_evidence, snapshots = _spawn_apply(
                            _remove_negotiation_worker,
                            (trial, window_row, branch_hops))
                        row["phases"]["remove"] = remove_evidence
                        if not removed:
                            row.update({"accepted": False,
                                        "decision": remove_evidence.get(
                                            "refusal")})
                            attempts.append(row)
                            continue
                        closed, close_evidence = _spawn_apply(
                            _close_negotiation_worker,
                            (trial, window_row, attempt_budget, margin))
                        row["phases"]["close"] = close_evidence
                        if not closed:
                            row.update({"accepted": False,
                                        "decision": close_evidence.get(
                                            "refusal")})
                            attempts.append(row)
                            continue
                        restored, restore_evidence = _spawn_apply(
                            _restore_negotiation_worker,
                            (trial, snapshots, margin, max_detour_ratio))
                        row["phases"]["restore"] = restore_evidence
                        if not restored:
                            row.update({"accepted": False,
                                        "decision": restore_evidence.get(
                                            "refusal")})
                            attempts.append(row)
                            continue
                    except Exception as exc:             # noqa: BLE001
                        row.update({"accepted": False,
                                    "decision": "worker_error",
                                    "error": "%s: %s" %
                                             (type(exc).__name__,
                                              str(exc)[:400])})
                        attempts.append(row)
                        continue
                    try:
                        _spawn_apply(_refill_worker, (trial,))
                    except Exception as exc:             # noqa: BLE001
                        row["refill_warning"] = "%s: %s" % (
                            type(exc).__name__, exc)
                    # A negotiated remove/restore can leave an orphaned tail
                    # or barrel even though the newly claimed connection and
                    # every displaced net are electrically complete.  Do not
                    # reject that otherwise valid composite transaction before
                    # giving the exact live KiCad UUID cascade a chance to
                    # settle.  This worker removes only items KiCad names as
                    # dangling; the full score below still rejects any open-
                    # net, structural-DRC, Kelvin, or pair regression.
                    cleaned, cleanup_evidence = _spawn_apply(
                        _drc_dangling_cleanup_worker, (trial, 8))
                    row["phases"]["dangling_cleanup"] = cleanup_evidence
                    if cleaned:
                        try:
                            _spawn_apply(_refill_worker, (trial,))
                        except Exception as exc:         # noqa: BLE001
                            row["cleanup_refill_warning"] = "%s: %s" % (
                                type(exc).__name__, exc)
                    trial_drc = os.path.join(
                        work, "negotiate-%03d-drc.json" % len(attempts))
                    trial_drc_data = _run_drc(trial, trial_drc)
                    after = _spawn_apply(_score_worker, (trial, trial_drc))
                    ok, decision = _accepts(before, after)
                    row.update({"after": after, "accepted": ok,
                                "decision": decision})
                    attempts.append(row)
                    if not ok:
                        # Once a complete transaction was scored, a broader
                        # geometric retry must not churn on the same debt swap
                        # or hard-gate regression. Deep effort is reserved for
                        # target-search and restoration refusals.
                        break
                    _copy_board_family(trial, current)
                    before = after
                    accepted.append(row)
                    adopted_window = True
                    if verbose:
                        print("[certificate-repair] negotiated %s around %s: %s" %
                              (window.net, list(window.blocker_nets), after),
                              file=sys.stderr, flush=True)
                    break
                if adopted_window:
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
                cycle_plan = _spawn_apply(
                    _negotiation_plan_worker,
                    (current, fresh_completion, max_windows,
                     max_blockers_per_window))
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

        # KiCad occasionally leaves a locked tail/via that no longer belongs
        # to the final connectivity graph.  Prune only exact UUIDs from the
        # current DRC, follow the resulting cascade to a fixed point, and then
        # apply the same full-board monotonic admission used by every repair.
        dangling_trial = os.path.join(
            work, "dangling-%03d.kicad_pcb" % len(attempts))
        _copy_board_family(current, dangling_trial)
        if effort.claim("drc_dangling_cascade", stage_limit=1):
            changed, evidence = _spawn_apply(
                _drc_dangling_cleanup_worker, (dangling_trial, 8))
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
            "attempts": attempts,
            "accepted": accepted,
            "drc_sweep": drc_sweep,
            "via_sweep": via_sweep,
            "closure_sweep": closure_sweep,
            "effort_budget": effort.report(),
            "changed": bool(accepted),
            "wall_s": round(time.monotonic() - started, 3),
        }
    finally:
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
        verbose=args.verbose)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        Path(args.report).write_text(payload + "\n", encoding="utf-8")
    if not args.quiet:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
