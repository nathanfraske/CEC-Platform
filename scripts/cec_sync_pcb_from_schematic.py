#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synchronize an existing PCB's footprint pads with its live schematic.

This is intentionally narrower than KiCad's interactive Update PCB command:
it preserves placement and board mechanics, can remove explicitly retired
references, and can discard all copper when a connectivity change makes the
old route unsafe. It never guesses which obsolete footprint is mechanical.
"""

import argparse
import math
import os
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cec_pcb_reconcile  # noqa: E402
import cec_pcb  # noqa: E402
import cec_sch_gates  # noqa: E402
import cec_footprint_fields  # noqa: E402
import cec_component_jumper_metadata as jumper_metadata  # noqa: E402


def _schematic_pad_nets(schematic):
    pad_nets = {}
    refs = set()
    for members, net_name in cec_pcb_reconcile.netlist_groups(schematic).items():
        for ref, pin in members:
            pad_nets[(ref, pin)] = net_name
            refs.add(ref)
    return pad_nets, refs


def _box_mm(item):
    box = item.GetBoundingBox(False, False)
    return tuple(value / 1e6 for value in (
        box.GetX(), box.GetY(), box.GetX() + box.GetWidth(),
        box.GetY() + box.GetHeight()))


def _overlap(a, b, clearance=0.25):
    return not (a[2] + clearance <= b[0] or b[2] + clearance <= a[0] or
                a[3] + clearance <= b[1] or b[3] + clearance <= a[1])


def _placement_candidates(target, bounds, step=1.0):
    """Deterministic local spiral followed by a complete board raster."""
    tx, ty = target
    yield tx, ty
    for radius in range(1, 25):
        r = radius * step
        points = max(8, radius * 8)
        for index in range(points):
            angle = 2.0 * math.pi * index / points
            yield tx + r * math.cos(angle), ty + r * math.sin(angle)
    x0, y0, x1, y1 = bounds
    y = y0 + step
    while y <= y1 - step:
        x = x0 + step
        while x <= x1 - step:
            yield x, y
            x += step
        y += step


def _place_new_footprint(board, footprint, pad_nets, already_missing):
    """Place one newly materialized part near its rarest connected live net.

    This is a conservative source-sync placement, not a replacement for the
    optimization placer.  It guarantees an on-board, non-overlapping starting
    point and uses connectivity to keep a late-added bypass/strap near its
    owner instead of parking all new parts in an arbitrary edge row.
    """
    ref = footprint.GetReference()
    by_net = {}
    for pad in footprint.Pads():
        net = pad_nets.get((ref, pad.GetNumber()))
        if not net or net.rsplit("/", 1)[-1] == "GND" or net.startswith("unconnected-"):
            continue
        peers = []
        for other in board.GetFootprints():
            if other.GetReference() == ref or other.GetReference() in already_missing:
                continue
            for other_pad in other.Pads():
                if other_pad.GetNetname() == net:
                    pos = other_pad.GetPosition()
                    peers.append((pos.x / 1e6, pos.y / 1e6))
        if peers:
            by_net[net] = peers

    edge = board.GetBoardEdgesBoundingBox()
    bounds = tuple(value / 1e6 for value in (
        edge.GetX(), edge.GetY(), edge.GetX() + edge.GetWidth(),
        edge.GetY() + edge.GetHeight()))
    bounded_by_outline = (
        bounds[2] - bounds[0] > 1e-6
        and bounds[3] - bounds[1] > 1e-6
    )
    if not bounded_by_outline:
        # A schematic-first staging PCB may intentionally have no Edge.Cuts.
        # Its existing footprint cloud is placement provenance only, not a
        # mechanical outline.  Give newly materialized parts a deterministic
        # non-overlapping staging canvas around that cloud; the replacement
        # placer must later bind an explicit outline policy before manufacture.
        staging_boxes = [
            _box_mm(other) for other in board.GetFootprints()
            if other.GetReference() != ref
        ]
        if staging_boxes:
            bounds = (
                min(box[0] for box in staging_boxes) - 10.0,
                min(box[1] for box in staging_boxes) - 10.0,
                max(box[2] for box in staging_boxes) + 10.0,
                max(box[3] for box in staging_boxes) + 10.0,
            )
        else:
            bounds = (0.0, 0.0, 100.0, 100.0)
    if by_net:
        # The least-populated signal/rail is the most local owner hint.
        peers = min(by_net.values(), key=lambda rows: (len(rows), rows))
        target = (sum(x for x, _y in peers) / len(peers),
                  sum(y for _x, y in peers) / len(peers))
    else:
        target = ((bounds[0] + bounds[2]) / 2.0,
                  (bounds[1] + bounds[3]) / 2.0)

    others = [other for other in board.GetFootprints()
              if other.GetReference() != ref]
    for x, y in _placement_candidates(target, bounds):
        footprint.SetPosition(pcbnew.VECTOR2I(int(round(x * 1e6)),
                                              int(round(y * 1e6))))
        box = _box_mm(footprint)
        if (bounded_by_outline and
                (box[0] < bounds[0] + 0.25 or
                 box[1] < bounds[1] + 0.25 or
                 box[2] > bounds[2] - 0.25 or
                 box[3] > bounds[3] - 0.25)):
            continue
        if any(_overlap(box, _box_mm(other)) for other in others):
            continue
        return (round(x, 4), round(y, 4), 0.0)
    raise RuntimeError(f"no legal staging placement found for added footprint {ref}")


def _load_missing_footprint(board, ref, part):
    lib_id = str(part.get("footprint") or "").strip()
    if ":" not in lib_id:
        raise ValueError(f"{ref} has no loadable schematic footprint: {lib_id!r}")
    nick, name = lib_id.split(":", 1)
    path = cec_pcb.fp_path(nick, name)
    footprint = pcbnew.FootprintLoad(
        os.path.dirname(path), os.path.splitext(os.path.basename(path))[0])
    if footprint is None:
        raise RuntimeError(f"pcbnew could not load {lib_id} for {ref}")
    footprint.SetFPID(pcbnew.LIB_ID(nick, name))
    footprint.SetReference(ref)
    footprint.SetValue(str(part.get("value") or ""))
    footprint.SetDNP(bool(part.get("dnp", False)))
    footprint.SetExcludedFromBOM(not bool(part.get("in_bom", True)))
    footprint.SetExcludedFromPosFiles(
        not bool(part.get("on_board", True)) or bool(part.get("dnp", False)))
    board.Add(footprint)
    return footprint


def synchronize(schematic, pcb_path, remove_refs=(), rip_all_copper=False,
                extra_pad_nets=None, add_missing=False,
                replace_mismatched_footprints=False, preserve_locked_nets=(),
                preserve_locked_uuids=()):
    """Apply the schematic netlist plus explicit board-only electrical lands.

    ``extra_pad_nets`` maps ``(reference, pad_number)`` to a net name.  This is
    intentionally explicit: mechanical footprints are not present in the
    schematic, but a fitted plated mounting land may still have an electrical
    contract (for example, the Hub/24-pin inter-board ground lug).  Guessing a
    net for every mechanical hole would be unsafe; clearing an explicitly
    declared electrical lug is equally unsafe.
    """
    pad_nets, schematic_refs = _schematic_pad_nets(schematic)
    inventory = cec_sch_gates.inventory(schematic)
    # Explicit actual component metadata, not generic footprint-library data.
    # Empty hierarchies have no schematic-owned PCB metadata to synchronize.
    jumper_contracts, jumper_observation = (
        jumper_metadata.observe(schematic, timeout_s=10.) if inventory else ({}, None))
    schematic_paths = (
        cec_pcb_reconcile.symbol_paths(schematic) if add_missing else {})
    # KiCad's exported netlist may include PWR_FLAG and power-symbol records,
    # but they are connectivity annotations rather than PCB footprints.
    schematic_refs = {
        ref for ref in schematic_refs
        if not inventory.get(ref, {}).get("lib_id", "").startswith(
            ("cec-power:", "power:"))
    }
    extra_pad_nets = dict(extra_pad_nets or {})
    overlap = set(pad_nets) & set(extra_pad_nets)
    if overlap:
        raise ValueError(
            "extra pad-net override targets schematic-owned pad(s): "
            + ", ".join(f"{ref}.{pad}" for ref, pad in sorted(overlap)))
    pad_nets.update(extra_pad_nets)
    board = pcbnew.LoadBoard(pcb_path)
    remove_refs = set(remove_refs)
    # Snapshot selections before mutation. Permanent retirement uses native
    # destruction, never borrowed-proxy ownership transfer through Remove().
    footprints = list(board.GetFootprints())
    tracks = list(board.GetTracks())
    zones = list(board.Zones())
    # Rule areas are mechanical/routing constraints, not copper. Replacement
    # may rip pours, but must retain native vent, antenna and assembly guards.
    copper_zones = [zone for zone in zones if not zone.GetIsRuleArea()]
    rule_areas = [zone for zone in zones if zone.GetIsRuleArea()]
    preserved_nets = set(preserve_locked_nets or ())
    preserved_uuids = set(preserve_locked_uuids or ())
    preserving = bool(preserved_nets or preserved_uuids)
    if preserving and not rip_all_copper:
        raise ValueError("locked preservation requires an explicit copper replacement")
    import cec_frozen_copper
    selected_items = cec_frozen_copper.require_items(board, preserved_uuids)
    retained = [item for item in tracks
                if item.IsLocked() and (str(item.GetNetname()) in preserved_nets
                    or str(item.m_Uuid.AsString()) in selected_items)]
    if preserving:
        changes = cec_frozen_copper.topology_changes(
            board, pad_nets, inventory, preserved_nets, remove_refs)
        if changes:
            raise ValueError("frozen copper topology changed: %s" % changes[:12])
        missing_nets = preserved_nets - {str(item.GetNetname()) for item in retained}
        if missing_nets:
            raise ValueError("frozen copper absent on declared net(s): %s" % sorted(missing_nets))
        live_nets = set(pad_nets.values())
        stale_items = {str(item.GetNetname()) for item in retained
                       if not item.GetNetname() or str(item.GetNetname()) not in live_nets}
        if stale_items:
            raise ValueError("frozen item net absent from current hierarchy: %s" % sorted(stale_items))
        stale_zones = {str(zone.GetNetname()) for zone in zones
                       if not zone.GetIsRuleArea() and zone.GetNetname()
                       and str(zone.GetNetname()) not in live_nets}
        if stale_zones:
            raise ValueError("frozen zone net absent from current hierarchy: %s" % sorted(stale_zones))
    retained_ids = {str(item.m_Uuid.AsString()) for item in retained}
    report = {
        "footprints_before": len(footprints),
        "tracks_before": len(tracks),
        "zones_before": len(zones),
        "preserved_rule_areas": len(rule_areas),
        "removed_refs": [],
        "pads_reassigned": 0,
        "pads_cleared": 0,
        "values_updated": 0,
        "fields_updated": 0,
        "assembly_flags_updated": 0,
        "added_refs": [],
        "added_placements_mm": {},
        "replaced_footprints": [],
        "zones_refilled": 0,
        "jumper_metadata_updated_refs": [],
        "preserved_locked_tracks": len(retained),
        "preserved_locked_nets": sorted(preserved_nets),
        "preserved_locked_uuids": sorted(preserved_uuids),
    }

    net_objects = {str(name): net for name, net in
                   board.GetNetInfo().NetsByName().items()}

    def net_object(name):
        if name not in net_objects:
            item = pcbnew.NETINFO_ITEM(board, name)
            board.Add(item)
            net_objects[name] = item
        return net_objects[name]

    board_refs = set()
    retired_footprints = []
    for footprint in footprints:
        ref = footprint.GetReference()
        if ref in remove_refs:
            retired_footprints.append(footprint)
            report["removed_refs"].append(ref)
            continue
        board_refs.add(ref)
        expected_part = inventory.get(ref)
        if expected_part and replace_mismatched_footprints:
            expected_id = str(expected_part.get("footprint") or "").strip()
            actual_id = footprint.GetFPID().GetUniStringLibId()
            if expected_id and expected_id != actual_id:
                # A footprint package change moves pad copper and invalidates
                # any attached route/zone geometry.  Synchronization may make
                # that destructive transition only when the caller has
                # explicitly requested the existing copper be discarded.
                if tracks and not rip_all_copper:
                    raise RuntimeError(
                        f"cannot replace routed footprint {ref}: "
                        f"{actual_id} -> {expected_id}; use --rip-all-copper")
                replacement = _load_missing_footprint(
                    board, ref, expected_part)
                position = footprint.GetPosition()
                replacement.SetPosition(position)
                if footprint.IsFlipped():
                    replacement.Flip(position, False)
                replacement.SetOrientation(footprint.GetOrientation())
                replacement.SetPath(footprint.GetPath())
                replacement.SetLocked(footprint.IsLocked())
                for pad in replacement.Pads():
                    expected = pad_nets.get((ref, pad.GetNumber()))
                    if expected is not None:
                        pad.SetNet(net_object(expected))
                retired_footprints.append(footprint)
                report["replaced_footprints"].append({
                    "ref": ref, "before": actual_id, "after": expected_id,
                })
                footprint = replacement
        if expected_part:
            value = expected_part.get("value", "")
            if footprint.GetValue() != value:
                footprint.SetValue(value)
                report["values_updated"] += 1
            report["fields_updated"] += \
                cec_footprint_fields.apply_schematic_fields(
                    footprint, expected_part)
            expected_dnp = bool(expected_part.get("dnp", False))
            expected_bom_excluded = not bool(expected_part.get("in_bom", True))
            expected_pos_excluded = (
                not bool(expected_part.get("on_board", True)) or expected_dnp
            )
            before = (
                footprint.IsDNP(), footprint.IsExcludedFromBOM(),
                footprint.IsExcludedFromPosFiles(),
            )
            after = (expected_dnp, expected_bom_excluded, expected_pos_excluded)
            if before != after:
                footprint.SetDNP(expected_dnp)
                footprint.SetExcludedFromBOM(expected_bom_excluded)
                footprint.SetExcludedFromPosFiles(expected_pos_excluded)
                report["assembly_flags_updated"] += 1
        for pad in footprint.Pads():
            key = (ref, pad.GetNumber())
            expected = pad_nets.get(key)
            if expected is None:
                if pad.GetNetCode() != 0:
                    pad.SetNetCode(0)
                    report["pads_cleared"] += 1
            elif pad.GetNetname() != expected:
                pad.SetNet(net_object(expected))
                report["pads_reassigned"] += 1

    report["unexpected_board_refs"] = sorted(
        ref for ref in board_refs - schematic_refs
        if not ref.startswith(("H", "FID", "LOGO", "TP")))
    missing = sorted(schematic_refs - board_refs)
    if add_missing and missing:
        # Add complex/high-pin-count devices first so their pads become owner
        # anchors for the associated bypass and strap passives.
        def pin_count(ref):
            return sum(key_ref == ref for key_ref, _pin in pad_nets)

        pending = set(missing)
        for ref in sorted(missing, key=lambda item: (-pin_count(item), item)):
            footprint = _load_missing_footprint(board, ref, inventory[ref])
            report["fields_updated"] += \
                cec_footprint_fields.apply_schematic_fields(
                    footprint, inventory[ref])
            path = schematic_paths.get(ref)
            if not path:
                raise RuntimeError(
                    f"schematic instance path unavailable for added footprint {ref}")
            footprint.SetPath(pcbnew.KIID_PATH(path))
            for pad in footprint.Pads():
                expected = pad_nets.get((ref, pad.GetNumber()))
                if expected is not None:
                    pad.SetNet(net_object(expected))
            pending.remove(ref)
            placement = _place_new_footprint(board, footprint, pad_nets, pending)
            report["added_refs"].append(ref)
            report["added_placements_mm"][ref] = placement
            board_refs.add(ref)
    report["missing_schematic_refs"] = sorted(schematic_refs - board_refs)
    # Removals are deliberately last: no board container or child proxy is
    # dereferenced after this point.
    if rip_all_copper:
        from cec_native_items import discard_items
        discarded_tracks = [item for item in tracks
                            if str(item.m_Uuid.AsString()) not in retained_ids]
        discard_items(board, discarded_tracks + ([] if preserving else copper_zones)
                      + retired_footprints)
    else:
        from cec_native_items import discard_items
        discard_items(board, retired_footprints)

    # Zone polygons are authored routing authority, while their filled copper
    # is a cache derived from pads and clearances.  Preserve the polygons and
    # deterministically refill them after a package swap; unlike fixed tracks,
    # this is the normal safe response to changed pad geometry.
    if report["replaced_footprints"] and zones and not rip_all_copper:
        for zone in zones:
            zone.UnFill()
        import cec_zone_fill
        cec_zone_fill.fill(board)
        report["zones_refilled"] = len(zones)

    report["footprints_after"] = (
        len(footprints)
        - len(retired_footprints)
        + len(report["added_refs"])
        + len(report["replaced_footprints"]))
    report["tracks_after"] = len(retained) if rip_all_copper else len(tracks)
    report["zones_after"] = (len(rule_areas) if rip_all_copper and not preserving else len(zones))
    if rip_all_copper and preserving:
        for zone in zones:
            zone.UnFill()

    target_dir = os.path.dirname(os.path.abspath(pcb_path))
    fd, temporary = tempfile.mkstemp(suffix=".kicad_pcb", dir=target_dir)
    os.close(fd)
    try:
        pcbnew.SaveBoard(temporary, board)
        report["jumper_metadata_updated_refs"] = jumper_metadata.apply_saved(
            temporary, jumper_contracts, timeout_s=10.)
        if jumper_observation is not None:
            jumper_metadata.check_observation(jumper_observation)
        os.replace(temporary, pcb_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schematic", required=True)
    parser.add_argument("--pcb", required=True)
    parser.add_argument("--remove-ref", action="append", default=[])
    parser.add_argument("--rip-all-copper", action="store_true")
    parser.add_argument("--preserve-locked-net", action="append", default=[],
                        help="retain locked conductors on this net during copper replacement")
    parser.add_argument("--preserve-locked-uuid", action="append", default=[],
                        help="retain this locked item, not all conductors on its net")
    parser.add_argument(
        "--add-missing", action="store_true",
        help=("materialize missing schematic footprints at deterministic, "
              "connectivity-aware, non-overlapping staging positions"))
    parser.add_argument(
        "--replace-mismatched-footprints", action="store_true",
        help=("replace an existing PCB footprint whose library ID differs "
              "from the live schematic; fixed-track boards also require "
              "--rip-all-copper, while authored zones are refilled"))
    parser.add_argument(
        "--extra-pad-net", action="append", default=[], metavar="REF.PAD=NET",
        help=("explicit net for a board-only electrical land; repeatable "
              "(example: H1.1=GND)"))
    args = parser.parse_args(argv)
    extra_pad_nets = {}
    for spec in args.extra_pad_net:
        try:
            refpad, net = spec.split("=", 1)
            ref, pad = refpad.rsplit(".", 1)
        except ValueError as exc:
            parser.error(f"invalid --extra-pad-net {spec!r}; expected REF.PAD=NET")
        if not ref or not pad or not net:
            parser.error(f"invalid --extra-pad-net {spec!r}; expected REF.PAD=NET")
        key = (ref, pad)
        if key in extra_pad_nets and extra_pad_nets[key] != net:
            parser.error(f"conflicting --extra-pad-net values for {ref}.{pad}")
        extra_pad_nets[key] = net
    report = synchronize(args.schematic, args.pcb, args.remove_ref,
                         args.rip_all_copper, extra_pad_nets, args.add_missing,
                         args.replace_mismatched_footprints, args.preserve_locked_net,
                         args.preserve_locked_uuid)
    for key, value in report.items():
        print(f"{key}={value}")
    if report["unexpected_board_refs"] or report["missing_schematic_refs"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
