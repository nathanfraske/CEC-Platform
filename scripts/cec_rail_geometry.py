"""Shared electrical-terminal geometry for rail reservation and copper planning.

All identities arrive as topology or role data. Physical pad records are lists:
several lands bearing the same electrical number must never collapse into one.
"""
from __future__ import annotations

import math
from collections import defaultdict
from functools import lru_cache
from collections import namedtuple


_LockedSegment = namedtuple("LockedSegment", "net x1 y1 x2 y2 width_mm")


def locked_segment(net, x1, y1, x2, y2, *, width_mm):
    """One validated record for imported and newly committed copper alike."""
    values = tuple(float(v) for v in (x1, y1, x2, y2, width_mm))
    if not all(math.isfinite(v) for v in values) or values[-1] <= 0:
        raise ValueError("locked copper needs finite geometry and a positive width")
    return _LockedSegment(str(net), *values)


class RailGeometryError(ValueError):
    """A claimed rail cannot be represented from its actual physical pads."""


def discover_topology(pads, *, roles=None):
    """Find series elements between source connectors and output terminals.

    Explicit roles override conventional reference classes. Ambiguous source
    direction is refused; reference ordering cannot choose electrical intent.
    """
    roles = roles or {}
    invalid_roles = {ref: value for ref, value in roles.items()
                     if value not in {"source", "sink", "series", "ignore"}}
    if invalid_roles:
        raise RailGeometryError("invalid terminal roles: %r" % invalid_roles)
    by_ref = defaultdict(list)
    for pad in pads:
        if pad.get("net"):
            by_ref[str(pad["ref"])].append(pad)

    def role(ref):
        if ref in roles:
            return roles[ref]
        if ref.startswith("RS"):
            return "series"
        if ref.startswith("TB"):
            return "sink"
        if ref.startswith("J"):
            return "source"
        return ""

    sources, sinks = defaultdict(set), defaultdict(set)
    for ref, rows in by_ref.items():
        target = sources if role(ref) == "source" else (
            sinks if role(ref) == "sink" else None)
        if target is not None:
            for row in rows:
                target[row["net"]].add(ref)
    out = []
    for ref, rows in sorted(by_ref.items()):
        if role(ref) != "series":
            continue
        nets = sorted({row["net"] for row in rows})
        if len(nets) != 2:
            continue
        directions = [(src, snk) for src, snk in (nets, nets[::-1])
                      if sources[src] and sinks[snk]]
        if len(directions) > 1:
            raise RailGeometryError("ambiguous source direction for %s" % ref)
        if not directions:
            continue
        src, snk = directions[0]
        out.append({"shunt": ref, "hi": src, "lo": snk,
                    "source_refs": sorted(sources[src]),
                    "sink_refs": sorted(sinks[snk])})
    return out


def topology_refs(row):
    """Normalize existing corridor schemas without inventing missing parts."""
    source = row.get("source_refs") or ([row["j_in"]] if row.get("j_in") else [])
    sink = row.get("sink_refs") or row.get("j_out_blades") or (
        [row["j_out"]] if row.get("j_out") else [])
    return tuple(source), tuple(sink)


def compile_rails(topology, pads, courtyard_y, current_for_nets, *,
                  terminal_clearance_mm=0.75):
    """Compile the same rail records for placement and live-board consumers."""
    by_ref_net = defaultdict(list)
    by_ref = defaultdict(list)
    for row in pads:
        by_ref_net[(row["ref"], row["net"])].append(row)
        by_ref[row["ref"]].append(row)
    rails = []
    for item in topology:
        ref, src, snk = item["shunt"], item["hi"], item["lo"]
        source_refs, sink_refs = topology_refs(item)
        source = [p for r in source_refs for p in by_ref_net[(r, src)]]
        sink = [p for r in sink_refs for p in by_ref_net[(r, snk)]]
        hi, lo = by_ref_net[(ref, src)], by_ref_net[(ref, snk)]
        missing = [r for r in source_refs if not by_ref_net[(r, src)]]
        missing += [r for r in sink_refs if not by_ref_net[(r, snk)]]
        if missing or not source or not sink or len(hi) != 1 or len(lo) != 1:
            raise RailGeometryError(
                "%s: incomplete physical rail terminals (missing=%s, "
                "source=%d sink=%d series contacts=%d/%d)" %
                (ref, missing, len(source), len(sink), len(hi), len(lo)))
        hi, lo = hi[0], lo[0]
        for pad in source + sink + [hi, lo]:
            if (any(not math.isfinite(float(pad[k]))
                    for k in ("x", "y", "width", "height"))
                    or min(pad["width"], pad["height"]) <= 0):
                raise RailGeometryError("invalid physical land on %s.%s" %
                                        (pad["ref"], pad["number"]))
        current = current_for_nets((src, snk))
        amps = float(current["amps"] if isinstance(current, dict) else current)
        if not math.isfinite(amps) or amps <= 0:
            raise RailGeometryError("%s: missing positive current authority" % ref)
        boxes = [courtyard_y[r] for r in sink_refs if r in courtyard_y]
        if not boxes:
            boxes = [(p["y"] - p["height"] / 2,
                      p["y"] + p["height"] / 2) for p in sink]
        mean_y = sum(p["y"] for p in sink) / len(sink)
        escape_y = (max(b[1] for b in boxes) + terminal_clearance_mm
                    if mean_y < lo["y"] else
                    min(b[0] for b in boxes) - terminal_clearance_mm)

        def contact(p):
            return (p["number"], p["x"], p["y"],
                    max(p["width"], p["height"]) / 2, bool(p["tht"]))

        rails.append({
            "rs": ref, "src_net": src, "snk_net": snk, "amps": amps,
            "current_authority": current if isinstance(current, dict) else
                {"amps": amps, "source": "caller"},
            "face": hi.get("face", "F.Cu"),
            "hi": (hi["x"], hi["y"]), "lo": (lo["x"], lo["y"]),
            "pad_w": max(hi["width"], hi["height"]),
            "tb_escape_y": escape_y,
            "source_refs": list(source_refs), "sink_refs": list(sink_refs),
            # Legacy planner field names retained at this adapter boundary.
            "j3": sorted((contact(p) for p in source), key=lambda p: p[1:3]),
            "tb": sorted(((p["ref"], *contact(p)) for p in sink),
                         key=lambda p: p[2:4]),
        })
    return sorted(rails, key=lambda row: (row["hi"][0], row["rs"]))


def board_facts(board):
    """Read every physical copper land, including repeated electrical pins."""
    import pcbnew
    from cec_footprint_fields import footprint_properties
    pads, courtyard_y, roles = [], {}, {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        face = "B.Cu" if fp.IsFlipped() else "F.Cu"
        declared_role = footprint_properties(fp).get("PowerRole", "")
        if declared_role:
            roles[ref] = declared_role.strip().lower()
        fp_pads = []
        for pad in fp.Pads():
            if not pad.GetNumber() or not list(pad.GetLayerSet().CuStack()):
                continue
            pos, size = pad.GetPosition(), pad.GetSize()
            fp_pads.append({"ref": ref, "number": pad.GetNumber(),
                            "net": pad.GetNetname(),
                            "x": pos.x / 1e6, "y": pos.y / 1e6,
                            "width": size.x / 1e6, "height": size.y / 1e6,
                            "tht": pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                            "face": face})
        pads.extend(fp_pads)
        if fp_pads:
            courtyard_y[ref] = _physical_envelope_y(fp)
    return pads, courtyard_y, roles


def _physical_envelope_y(fp):
    """Union real courtyard and all copper lands, including protruding pads."""
    import pcbnew
    boxes = [p.GetBoundingBox() for p in fp.Pads() if p.GetNumber()
             and list(p.GetLayerSet().CuStack())]
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
    if cy is not None and not cy.IsEmpty():
        boxes.append(cy.BBox())
    if not boxes:
        raise RailGeometryError("no physical envelope for %s" % fp.GetReference())
    return (min(box.GetTop() for box in boxes) / 1e6,
            max(box.GetBottom() for box in boxes) / 1e6)


@lru_cache(maxsize=1024)
def _library_envelope_y(libid, angle, flipped):
    """Cache native geometry by pose class, not a guessed courtyard rectangle."""
    import os
    import pcbnew
    import cec_pcb
    nick, name = libid.split(":")
    fp = pcbnew.FootprintLoad(os.path.dirname(cec_pcb.fp_path(nick, name)), name)
    if fp is None:
        raise RailGeometryError("cannot load footprint geometry for %s" % libid)
    # Flip consults the parent board's layer stack; an orphan footprint can
    # crash the SWIG binding rather than raising an exception.
    owner = pcbnew.CreateEmptyBoard()
    owner.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    fp.SetOrientationDegrees(angle)
    if flipped:
        fp.Flip(fp.GetPosition(), False)
    return _physical_envelope_y(fp)


def placement_facts(nl, comps, pos_of, topology, *, back_refs=()):
    """Read library lands at proposed poses; never substitute origins for pads."""
    import cec_pcb
    refs = {row["shunt"] for row in topology}
    for row in topology:
        refs.update(ref for group in topology_refs(row) for ref in group)
    net_at = {}
    for net, members in nl.nets.items():
        for ref, number in members:
            key = (ref, str(number))
            if key in net_at and net_at[key] != net:
                raise RailGeometryError("multiple nets for physical pin %s.%s" % key)
            net_at[key] = net
    pads, courtyard_y = [], {}
    for ref in sorted(refs):
        pose = pos_of(ref)
        if pose is None or ref not in comps:
            raise RailGeometryError("missing placement/footprint for %s" % ref)
        x, y, angle = pose
        flipped = ref in back_refs
        for pad in cec_pcb.local_physical_pads(comps[ref]):
            lx, ly = pad["x"], pad["y"]
            # Match native Flip(): rotate first, then mirror global X.
            dx, dy = cec_pcb._rot(lx, ly, angle)
            if flipped:
                dx = -dx
            pads.append({**pad, "ref": ref,
                         "net": net_at.get((ref, pad["number"]), ""),
                         "x": x + dx, "y": y + dy,
                         "face": "B.Cu" if flipped else "F.Cu"})
        lo, hi = _library_envelope_y(comps[ref], angle % 360, flipped)
        courtyard_y[ref] = (y + lo, y + hi)
    return pads, courtyard_y
