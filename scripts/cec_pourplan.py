#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
PourPlan -- the first-class, mutable owner of copper-pour state in the place->route->check loop
(pour lever, docs/pour-lever-scoping-2026-07-08.md).

Copper pours were derived STATELESSLY from board/placement geometry at five independent call
sites (the "one geometry, five stateless consumers" of the scoping doc §1.1): the placement
settle/evac, the pre-route keepouts, the post-route copper, the bodies-in-pours gate, and the
thermal solve. Re-deriving at each site is the box-model duality debt (a re-stamped cap kept
landing in a gate box the settle never saw). This module introduces ONE object -- a `PourPlan`
of `PourSpec` primitives -- that all the derivation consumers compile from, so the settle boxes,
the gate boxes, the keepout reservations, and the post-route copper are geometrically identical
BY CONSTRUCTION, and the lever has a STATE to mutate.

Stage 1 (this module + the re-points) is a PURE REFACTOR: `cec_fr._pour_boxes_core` stays the
geometry kernel, and the three compile views (`pour_polygons` / `keepout_hints` / `evac_boxes`)
reproduce today's `derive_power_pours` / `corridor_keepouts` / `_pour_boxes_unified` output
byte-for-byte when `asks=()` (the golden guarantee -- teeth in build/pourwt/pour_lever_probe.py).

Stage 2 adds the placer ASK channel (`PlacementSession.pour(...)` -> `cfg.params["pour_asks"]`),
folded here via `asks=` (inert when unused). Stage 3 serializes a plan to/from a
`<board>.pourplan.json` sidecar. The router REBUILD verb (stage 4) and the eval harness
(stage 5) await owner rulings and are NOT implemented here.

Pure-data + picklable/JSON-serializable core (`specs` / `board_sig` / `recipe`); the live pcbnew
board handle needed for the non-lane keepout derivation is a private, non-serialized attribute so
a sidecar-loaded plan re-derives keepouts off the board being routed. Imports of cec_fr / cec_pcb
/ cec_score / cec_synth_pipeline are LAZY (inside methods) so this module has no import cycle with
either cec_fr or cec_synth_pipeline (the scoping doc's placement rationale, §2)."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field, asdict


# add_power_pours' own defaults (cec_fr.add_power_pours); a derived spec carries these, so
# pour_polygons() emits them only when a spec OVERRIDES one -> a derived plan is byte-identical
# to today's derive_power_pours output ({net, layer, polygon} exactly).
_PRIORITY_DEFAULT = 2
_MIN_THICKNESS_DEFAULT = 0.25
_ISLAND_REMOVAL_DEFAULT = 0

# --- stage-4 rebuild-verb constants (docs/pour-lever-scoping-2026-07-08.md §4 + §8 rulings) ---
_OZ_MM = 0.0348                                   # 1oz finished copper thickness (mm)
_OUTER_THICKNESS_MM = 2 * _OZ_MM                  # 2oz outer pours (the cable/rail boards' outers)
# HARD cross-section floor for a rebuilt pour when the caller supplies no explicit need (ruling 2).
# 0.06 mm^2 = the 24-pin worst rail (~6A on the 6A/circuit ATX bar) at the checker's j_max=100 A/mm^2.
_DEFAULT_MIN_CROSS_MM2 = float(os.environ.get("CEC_POUR_MIN_CROSS_MM2", "0.06"))


class EscalateToHuman(Exception):
    """A pour edit crossed the ratified autonomy line (docs/pour-lever-scoping §8 ruling 1). In-loop
    autonomy is a geometry-only reshape (notch / shrink / relocate / drop_layer) of an EXISTING
    auto-derived pour, SAME net. ADDING a pour on a net the plan would not derive, DROPPING a
    required pour, CHANGING a pour's net, or touching a FROZEN (human-ratified) spec is a DESIGN
    change -> escalate. Carries a named, human-readable reason (never a silent proceed)."""


class PourCrossSectionRefused(Exception):
    """A reshape would neck a REBUILT pour below the min-pour-cross-section requirement (ruling 2:
    min-pour-cross-section is a HARD gate on rebuilt pours). Refused so a reshape can never thin the
    copper to dodge the foreign-on-pour gate. Carries the got/need cross-section in its message."""


class PourUniformityRefused(Exception):
    """DERIVE-ONCE-STAMP-N could not make a per-cable OUTPUT family uniform WITHOUT necking the
    master below the min-pour-cross-section HARD gate (owner ruling 2026-07-09: the per-cable output
    field must be IDENTICAL across positions/SKUs). Uniformity constrains DOWN -- a replica that
    would collide foreign copper at some position shrinks the MASTER (so ALL positions stay
    identical); if that shrink crosses the cross-section floor, we REFUSE rather than ship a
    non-uniform fallback silently. Carries a named reason (role + got/need cross-section)."""


# --- per-cable family recognition (owner ruling 2026-07-09, per-cable output uniformity) ----------
# A per-cable sense net is '<prefix><index><_HI|_LO>' with the INTEGER index sitting IMMEDIATELY
# before the _HI/_LO suffix -- /SENSEC1_LO -> ('/SENSEC', 1, '_LO'). A rail name like /SENSE5VSB_LO
# (no trailing digit) never matches, and /SENSE3V3_HI matches as ('/SENSE3V', 3, '_HI') -- a
# SINGLE-index role that the >=2-positions family test rejects. So shared-bus / per-rail boards
# (24-pin, 12VHPWR, Hub) yield NO family and are byte-identical (teeth (f)).
_CABLE_NET_RE = re.compile(r"^(?P<pre>.*?)(?P<idx>\d+)(?P<suf>_(?:HI|LO))$")


def _parse_cable_net(net):
    """Parse a per-cable sense net -> (prefix, idx:int, suffix) or None (not a cable-family net)."""
    if not net:
        return None
    m = _CABLE_NET_RE.match(net)
    if not m:
        return None
    return (m.group("pre"), int(m.group("idx")), m.group("suf"))


@dataclass
class PourSpec:
    """One requested/derived pour primitive. `polygon` is the concrete compiled geometry (the
    kernel's rectangle corners, or an ask's resolved box); the higher-level fields (shape/region/
    notch/exempt_nets) describe the INTENT the lever mutates. `frozen` marks human-ratified
    geometry the loop may not mutate (enforced by the stage-4 rebuild verb)."""
    net: str
    layers: tuple = ("F.Cu",)
    shape: str = "rect"                # "lane" | "corridor" | "rect" | "notched"
    region: tuple | None = None        # (x0,y0,x1,y1) mm hint; None = auto-derived from pads
    priority: int = _PRIORITY_DEFAULT  # zone priority above GND(0)
    notch: dict | None = None          # {"at":(x,y),"gap_mm":..,"vertical":bool} -- the shunt window
    exempt_nets: tuple = ()            # nets allowed to live inside (own-rail eviction exemption)
    min_thickness: float = _MIN_THICKNESS_DEFAULT
    island_removal: int = _ISLAND_REMOVAL_DEFAULT
    provenance: str = "derived"        # "derived" | "placer_ask" | "router_ask" | "human"
    frozen: bool = False               # human-ratified geometry the loop may not mutate
    polygon: tuple = ()                # ((x,y),...) compiled geometry (rect corners today)

    def rect(self):
        """(x0,x1,y0,y1) of the polygon's extent (the evac/gate box format)."""
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        return (min(xs), max(xs), min(ys), max(ys)) if self.polygon else None


@dataclass
class PourPlan:
    """The plan = an ordered list of PourSpec + the placement signature it is valid for + the
    compile recipe (env knobs) it was derived under. `specs` order is load-bearing (the lane-mode
    keepout names index into it), matching `_pour_boxes_core`'s emission order."""
    specs: list
    board_sig: str = ""
    recipe: dict = field(default_factory=dict)

    # ---- private, NON-serialized derivation context (set by from_board; used by keepout_hints) ----
    _board_path: str | None = field(default=None, repr=False, compare=False)
    _board: object = field(default=None, repr=False, compare=False)
    _kelvin_pairs: object = field(default=None, repr=False, compare=False)
    _nets_12v: object = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ recipe / signature helpers
    @staticmethod
    def recipe_from_env():
        """The geometry-relevant compile knobs the pour derivations read live from os.environ.
        Recorded on the plan so a serialized (stage-3) plan carries the recipe it was built under."""
        return {
            "pour_lanes": os.environ.get("CEC_POUR_LANES", "0") == "1",
            "shunt_gap": os.environ.get("CEC_SHUNT_GAP", "0") == "1",
            "shunt_gap_mm": float(os.environ.get("CEC_SHUNT_GAP_MM", "6.5")),
            "corridor_fcu_only": os.environ.get("CEC_CORRIDOR_FCU_ONLY", "0") == "1",
            "inner_pours": os.environ.get("CEC_INNER_POURS", "0") == "1",
            "lane_w_json": os.environ.get("CEC_LANE_W_JSON", ""),
            # PER-CABLE OUTPUT UNIFORMITY (owner ruling 2026-07-09): when set, a per-cable family's
            # pours are DERIVED ONCE (the most-constrained position) and STAMPED to every position
            # by the cable-pitch translation, so the output field is IDENTICAL across positions/SKUs.
            # OFF by default -> byte-identical derivation (SB-08 / 24-pin teeth). The oracle recipe
            # turns it ON (fresh boards get the uniformity guarantee).
            "uniform": os.environ.get("CEC_POUR_UNIFORM", "0") == "1",
        }

    @staticmethod
    def _sig_from_prepared(prepared):
        """A cheap deterministic signature over the pad geometry the plan was derived from
        (net -> ref/x/y/tht). Two placements with the same pad geometry share a signature."""
        h = hashlib.sha1()
        for net in sorted(prepared):
            for ref, x, y, tht in sorted(prepared[net]):
                h.update(("%s|%s|%.4f|%.4f|%d;" % (net, ref, x, y, int(bool(tht)))).encode())
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------ constructors
    @classmethod
    def from_prepared(cls, names, kelvin_pairs, prepared, padcount, flipped, bbox, inner_layer,
                      *, asks=(), margin=1.0, layer="F.Cu", recipe=None, board_sig=None):
        """The low-level constructor over the SAME inputs `cec_fr._pour_boxes_core` takes
        (`prepared` = {net: [(ref, x_mm, y_mm, is_tht)]}). Derives the Kelvin-pair pours through
        the kernel (unchanged geometry), then appends any `asks` as extra specs. Extra asked-net
        entries in `prepared` are ignored by the kernel (it only reads kelvin-pair nets), so a
        board with `asks=()` compiles byte-identically to `derive_power_pours` today."""
        import cec_fr
        pourdicts = cec_fr._pour_boxes_core(names, kelvin_pairs, prepared, padcount, flipped,
                                            bbox, inner_layer, margin=margin, layer=layer)
        specs = [PourSpec(net=p["net"], layers=(p["layer"],), shape="rect",
                          polygon=tuple(tuple(pt) for pt in p["polygon"]))
                 for p in pourdicts]
        plan = cls(specs=specs,
                   board_sig=board_sig if board_sig is not None else cls._sig_from_prepared(prepared),
                   recipe=recipe if recipe is not None else cls.recipe_from_env())
        for a in (asks or ()):
            sp = _ask_spec(a, prepared, bbox, margin)
            if sp is not None:
                specs.append(sp)
        # DERIVE-ONCE-STAMP-N (owner ruling 2026-07-09): when the uniformity lever is on AND the
        # board carries a per-cable family, replace each position's INDEPENDENTLY-derived pours with
        # the most-constrained position's geometry STAMPED across the UNIFORM cable-pitch grid. Inert
        # (byte-identical) when the lever is off or there is no family -- the golden/24-pin guarantee.
        if plan.recipe.get("uniform"):
            plan.enforce_uniformity()
        return plan

    @classmethod
    def from_board(cls, board_path, *, board=None, kelvin_pairs=None, nets_12v=None, asks=(),
                   margin=1.0, edge_clear=0.4, layer="F.Cu", recipe=None):
        """DEFAULT plan == today's `derive_power_pours` geometry (auto-derived from the §6.4 rail
        pads), then apply placer/router `asks`. `asks=()` -> byte-identical to `derive_power_pours`.

        Replicates `derive_power_pours`' board-read verbatim (the pcbnew BOARD is cached per path,
        so pass an already-loaded `board=` when a caller also mutates it -- the same contract).
        Stashes the board + resolved kelvin pairs + nets_12v privately so `keepout_hints` can
        re-derive the non-lane force-corridor off the board without a second load."""
        import cec_fr
        import pcbnew
        from collections import defaultdict
        MM = cec_fr.MM
        board = board if board is not None else pcbnew.LoadBoard(board_path)
        names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values()
                 if n.GetNetname()}
        if kelvin_pairs is None:
            kelvin_pairs = cec_fr._board_kelvin_pairs(board)
        bb = board.GetBoardEdgesBoundingBox()
        bx0, by0 = bb.GetLeft() / MM + edge_clear, bb.GetTop() / MM + edge_clear
        bx1, by1 = bb.GetRight() / MM - edge_clear, bb.GetBottom() / MM - edge_clear
        # INNER-POUR mode (experimental, OFF by default -- CEC_INNER_POURS): mirror derive_power_pours.
        inner_layer = None
        if os.environ.get("CEC_INNER_POURS", "0") == "1":
            for lid in range(pcbnew.PCB_LAYER_ID_COUNT):
                try:
                    if (board.GetLayerName(lid) == "PWR_RT"
                            and board.GetLayerType(lid) == pcbnew.LT_SIGNAL):
                        inner_layer = "In2.Cu"
                        break
                except Exception:                                # noqa: BLE001 -- foreign layer guard
                    pass
        pads_by_net = defaultdict(list)
        padcount = defaultdict(int)
        flipped = {}
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            flipped[ref] = fp.IsFlipped()
            for p in fp.Pads():
                padcount[ref] += 1
                nn = p.GetNetname()
                if nn:
                    pads_by_net[nn].append((ref, p))
        prepared = defaultdict(list)
        for net, entries in pads_by_net.items():
            for ref, p in entries:
                pos = p.GetPosition()
                prepared[net].append((ref, pos.x / MM, pos.y / MM,
                                      p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
        plan = cls.from_prepared(names, kelvin_pairs, prepared, dict(padcount), dict(flipped),
                                 (bx0, by0, bx1, by1), inner_layer, asks=asks, margin=margin,
                                 layer=layer, recipe=recipe)
        plan._board_path = board_path
        plan._board = board
        plan._kelvin_pairs = kelvin_pairs
        plan._nets_12v = nets_12v
        return plan

    @classmethod
    def from_placement(cls, P, nl, comps, W, H, *, asks=(), margin=1.0, edge_clear=0.4):
        """The PLACEMENT-side constructor (settle/evac, C1). Reads pad geometry off the placement
        dict P (via cec_pcb.pad_global) exactly as `_pour_boxes_unified` did -- flipped={},
        inner_layer=None, bbox=(edge_clear, edge_clear, W-edge_clear, H-edge_clear). Builds
        `prepared` for the kelvin-pair nets UNIONed with the asked nets (so an ask on a no-shunt
        rail can auto-derive its box from that net's pads). `asks=()` -> byte-identical to the old
        `_pour_boxes_unified`."""
        import cec_pcb
        import cec_synth_pipeline as csp
        pairs = csp._kelvin_pairs(nl)
        if not pairs and not asks:
            return cls(specs=[], board_sig="", recipe=cls.recipe_from_env())
        pair_nets = {n for pr in pairs for n in pr}
        want = pair_nets | {a["net"] for a in (asks or ())}
        names = set(nl.nets)
        prepared = {}
        for net in want:
            entries = []
            for ref, padnum in nl.nets.get(net, []):
                if ref not in P or ref not in comps:
                    continue
                try:
                    g = cec_pcb.pad_global(ref, padnum, P, comps)
                except Exception:                                # noqa: BLE001 -- pad absent (NPTH etc.)
                    continue
                entries.append((ref, g[0], g[1], csp._pad_is_tht(comps[ref]).get(padnum, False)))
            prepared[net] = entries
        padcount = {r: csp._ref_padcount(nl, r) for r in nl.comps}
        bbox = (edge_clear, edge_clear, W - edge_clear, H - edge_clear)
        return cls.from_prepared(names, pairs, prepared, padcount, {}, bbox, None,
                                 asks=asks, margin=margin)

    # ------------------------------------------------------------------ the three compile views
    def pour_polygons(self):
        """POST-ROUTE view: `add_power_pours` / `Spec.power_pours`-ready dicts. Emits the minimal
        {net, layer, polygon} of `_pour_boxes_core` (byte-identical to `derive_power_pours`), plus
        priority/min_thickness/island_removal ONLY when a spec overrides the add_power_pours
        default -- so a derived plan is byte-identical and an asked/mutated spec still carries its
        override to the copper."""
        out = []
        for s in self.specs:
            if not s.polygon:
                continue
            d = {"net": s.net, "layer": (s.layers[0] if s.layers else "F.Cu"),
                 "polygon": [tuple(pt) for pt in s.polygon]}
            if s.priority != _PRIORITY_DEFAULT:
                d["priority"] = s.priority
            if s.min_thickness != _MIN_THICKNESS_DEFAULT:
                d["min_thickness"] = s.min_thickness
            if s.island_removal != _ISLAND_REMOVAL_DEFAULT:
                d["island_removal"] = s.island_removal
            out.append(d)
        return out

    def evac_boxes(self):
        """PLACEMENT view: (net, x0, x1, y0, y1) tuples for `_evacuate_pours` / the bodies gate
        (byte-identical to the old `_pour_boxes_unified` output)."""
        out = []
        for s in self.specs:
            r = s.rect()
            if r is not None:
                out.append((s.net, r[0], r[1], r[2], r[3]))
        return out

    def keepout_hints(self, *, layers=("F.Cu", "B.Cu")):
        """PRE-ROUTE view: `bake_hints`-ready keepout dicts (byte-identical to `corridor_keepouts`).

        LANE mode (CEC_POUR_LANES=1): the keepouts ARE the lane pour shapes (commit 006bdb6 --
        one geometry source for pours, settle, gate, AND route-time keepouts), so rebox this
        plan's own `pour_polygons()`.
        Non-lane: delegate to the extracted force-corridor derivation `cec_fr._force_corridor_hints`
        (the connector->shunt corridor clipped at the shunt notch) off the board this plan wraps."""
        if os.environ.get("CEC_POUR_LANES", "0") == "1":
            hints = []
            lsel = tuple(layers)
            for i, p in enumerate(self.pour_polygons()):
                xs = [q[0] for q in p["polygon"]]
                ys = [q[1] for q in p["polygon"]]
                lay = (("B.Cu",) if (p["layer"] == "B.Cu" and lsel == ("F.Cu",))
                       else ((p["layer"],) if lsel == ("F.Cu",) else lsel))
                hints.append({"name": f"corr_{p['net'].strip('/')}_{i}",
                              "x0": round(min(xs), 2), "y0": round(min(ys), 2),
                              "x1": round(max(xs), 2), "y1": round(max(ys), 2),
                              "layers": lay, "allow_vias": True, "block_fills": False})
            return hints
        import cec_fr
        import pcbnew
        board = self._board if self._board is not None else pcbnew.LoadBoard(self._board_path)
        return cec_fr._force_corridor_hints(board, self._board_path,
                                            kelvin_pairs=self._kelvin_pairs,
                                            nets_12v=self._nets_12v, layers=layers)

    # ------------------------------------------------------------------ mutation (the ask surface)
    def add(self, spec: PourSpec):
        """Append a pour geometry the derivation would not produce -- the sanctioned PLACER-ASK /
        sidecar path (a declarative ask resolved through `_ask_spec`, or a deserialized spec). This
        is NOT the router rebuild verb: the router reaches a NEW pour only through `rebuild('add')`,
        which ESCALATES (that add is a design change, ruling 1). Placer asks are additive by design."""
        self.specs.append(spec)
        return self

    # ------------------------------------------------------------------ per-cable uniformity
    # DERIVE-ONCE-STAMP-N (owner ruling 2026-07-09, per-cable output-field uniformity). The pipeline
    # controls the per-cable output pinout WITHIN ampacity, but the resulting pours must be IDENTICAL
    # across cable positions on a board (and across the PCIe 2-/3-port SKUs -- one output spec per
    # family). The stateless per-net derivation produced congestion-shaped, position-dependent pours
    # (the owner saw them differ between cable positions). Here we DERIVE ONCE (the tightest position)
    # and STAMP that geometry to every position by the cable-pitch translation.
    def _cable_families(self):
        """Group the plan's specs into per-cable roles: {(prefix, suffix): {idx: [spec, ...]}},
        keeping only roles with >= 2 positions (a genuine multi-cable family)."""
        roles = {}
        for s in self.specs:
            p = _parse_cable_net(s.net)
            if p is None:
                continue
            pre, idx, suf = p
            roles.setdefault((pre, suf), {}).setdefault(idx, []).append(s)
        return {k: v for k, v in roles.items() if len(v) >= 2}

    def has_cable_family(self):
        """True iff the plan carries a per-cable family (>=2 positions on some role)."""
        return bool(self._cable_families())

    @staticmethod
    def _union_min(specs):
        """(x0, y0) = the min-corner of the union bbox of a position's pours. The pour is derived
        from that cable's OUTPUT TAB THT pads (+ its shunt), so this min-corner TRACKS the real
        output tabs -- it is the per-tab-block anchor derive-once-stamp-N stamps AT (never a
        regularized pitch: a blade tab's ONLY connection is the pour that laps it, since the
        force-pour-only DSN policy EXCLUDES the connector force pins from Freerouting, so a pour
        moved off its tab leaves an OPEN 18A joint -- owner correction 2026-07-09)."""
        rects = [s.rect() for s in specs if s.rect() is not None]
        if not rects:
            return None
        return (min(r[0] for r in rects), min(r[2] for r in rects))

    @staticmethod
    def _min_cross_of(specs, shrink, *, thickness_mm=_OUTER_THICKNESS_MM):
        """Geometry proxy for the DC-field bottleneck of a spec SET at a symmetric `shrink`: each
        box carries current along its longer side, so its cross is (shorter side - 2*shrink)*thickness;
        the set's bottleneck is the MIN. Shorter side clamped at 0 (an over-shrunk box necks, not grows)."""
        widths = []
        for s in specs:
            r = s.rect()
            if r is None:
                continue
            widths.append(max(0.0, min((r[1] - r[0]) - 2 * shrink, (r[3] - r[2]) - 2 * shrink)))
        return (min(widths) * thickness_mm) if widths else None

    def _stamp_role_at_tabs(self, pre, suf, by_idx, master_specs, m_ref, shrink):
        """Stamp the MASTER's SHAPE (each master box taken RELATIVE to the master's own min-corner
        `m_ref`) at EVERY position's OWN min-corner (its tab-block anchor), symmetrically shrunk by
        `shrink`. This makes the pour SHAPE identical across positions while each pour stays laid
        over ITS OWN output tabs (position anchored to the tab, never regularized off it). Returns
        the stamped specs, or None when a position has no derivable anchor (caller leaves the role)."""
        out = []
        for idx in sorted(by_idx):
            ref = self._union_min(by_idx[idx])
            if ref is None:
                return None
            net = pre + str(idx) + suf
            for ms in master_specs:
                r = ms.rect()
                if r is None:
                    continue
                rx0, rx1 = r[0] - m_ref[0], r[1] - m_ref[0]     # master box RELATIVE to its min-corner
                ry0, ry1 = r[2] - m_ref[1], r[3] - m_ref[1]
                x0 = ref[0] + rx0 + shrink
                x1 = ref[0] + rx1 - shrink
                y0 = ref[1] + ry0 + shrink
                y1 = ref[1] + ry1 - shrink
                out.append(PourSpec(net=net, layers=ms.layers, shape=ms.shape,
                                    priority=ms.priority, min_thickness=ms.min_thickness,
                                    island_removal=ms.island_removal,
                                    provenance="uniform_stamp",
                                    polygon=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                                    region=(x0, y0, x1, y1)))
        return out

    @staticmethod
    def _role_master(by_idx):
        """The MOST-CONSTRAINED position = the one whose independently-derived pour has the SMALLEST
        total area (the tightest, congestion-squeezed pour). Replicating it constrains uniformity
        DOWN, never up (a wide position never forces a narrow one to grow). Ties break on lower idx."""
        def area(specs):
            tot = 0.0
            for s in specs:
                r = s.rect()
                if r:
                    tot += (r[1] - r[0]) * (r[3] - r[2])
            return tot
        return min(sorted(by_idx), key=lambda i: (area(by_idx[i]), i))

    def enforce_uniformity(self, *, foreign_by_pos=None, min_cross_mm2=None,
                           shrink_step=0.5, max_iters=200):
        """DERIVE-ONCE-STAMP-N (owner ruling 2026-07-09 + correction). For each per-cable role, pick
        the most-constrained (tightest) position as the MASTER, then replace every position's pours
        with the master's SHAPE stamped AT that position's OWN tab-block anchor (net-mapped). The
        SHAPE becomes identical across positions; each pour stays laid over its OWN output tabs (the
        pour position is NEVER regularized off its tab -- a moved pour leaves an OPEN force joint).
        Uniformity constrains DOWN:

          * `foreign_by_pos` = {idx: [(x0,x1,y0,y1), ...]} of FIXED foreign copper per position. When a
            stamped replica would overlap foreign copper at SOME position, the master shrinks
            symmetrically (so ALL positions keep the SAME shape) until every replica is clear.
          * if shrinking necks the master below the min-pour-cross-section HARD gate floor, REFUSE
            (PourUniformityRefused) -- never ship a non-uniform fallback silently (owner ruling).

        No-op (byte-identical) when there is no per-cable family. Mutates the plan IN PLACE."""
        fams = self._cable_families()
        if not fams:
            return self
        floor = _DEFAULT_MIN_CROSS_MM2 if min_cross_mm2 is None else float(min_cross_mm2)
        fam_ids = {id(s) for by_idx in fams.values() for specs in by_idx.values() for s in specs}
        kept = [s for s in self.specs if id(s) not in fam_ids]
        stamped_all = []
        for (pre, suf), by_idx in fams.items():
            master_idx = self._role_master(by_idx)
            master_specs = by_idx[master_idx]
            m_ref = self._union_min(master_specs)
            if m_ref is None:                                 # degenerate master -> leave role
                stamped_all.extend(s for i in sorted(by_idx) for s in by_idx[i])
                continue
            shrink = 0.0
            for _ in range(max_iters):
                stamped = self._stamp_role_at_tabs(pre, suf, by_idx, master_specs, m_ref, shrink)
                if stamped is None:                           # missing anchor -> leave role UNCHANGED
                    stamped = [s for i in sorted(by_idx) for s in by_idx[i]]
                    break
                collided = False
                if foreign_by_pos:
                    for sp in stamped:
                        idx = _parse_cable_net(sp.net)[1]
                        r = sp.rect()
                        for (fx0, fx1, fy0, fy1) in foreign_by_pos.get(idx, []):
                            if not (r[1] <= fx0 or r[0] >= fx1 or r[3] <= fy0 or r[2] >= fy1):
                                collided = True
                                break
                        if collided:
                            break
                if not collided:
                    break
                shrink += shrink_step
                mc = self._min_cross_of(master_specs, shrink)
                if mc is not None and mc < floor - 1e-9:
                    raise PourUniformityRefused(
                        "derive-once-stamp-N on role %s%s: shrinking the master to clear foreign "
                        "copper at some cable position necks it to %.4f mm^2 < required %.4f mm^2 "
                        "(min-pour-cross-section HARD gate) -- refusing rather than shipping a "
                        "non-uniform fallback (owner ruling 2026-07-09)" % (pre, suf, mc, floor))
            stamped_all.extend(stamped)
        self.specs = kept + stamped_all
        return self

    # ------------------------------------------------------------------ stage-4 REBUILD verb
    # The router-rebuild actuation surface (docs/pour-lever-scoping-2026-07-08.md §3.2/§4, owner
    # RATIFIED 2026-07-09). `rebuild(op, net=..., ...)` is the ONE entry the router-repair emits
    # through: it enforces the autonomy line (ruling 1) BEFORE any geometry change and the
    # min-pour-cross-section HARD gate (ruling 2) AFTER, so the loop can reshape a derived pour but
    # never add/drop/re-net one, and never neck copper to cheat the foreign gate.
    def _specs_for(self, net):
        return [s for s in self.specs if s.net == net]

    def _min_cross_mm2(self, net, *, thickness_mm=_OUTER_THICKNESS_MM):
        """Geometry proxy for the checker's DC-field bottleneck: for each of the net's lane boxes the
        current flows along the LONGER side, so the box cross-section is (shorter side)*thickness; the
        net's bottleneck is the MIN over its boxes. Returns None if the net has no polygon box."""
        widths = []
        for s in self._specs_for(net):
            r = s.rect()
            if r is None:
                continue
            widths.append(min(r[1] - r[0], r[3] - r[2]))   # (x1-x0, y1-y0) shorter side
        return (min(widths) * thickness_mm) if widths else None

    def _set_rect(self, spec, x0, x1, y0, y1):
        spec.polygon = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        spec.region = (x0, y0, x1, y1)

    def _op_shrink(self, specs, edge, mm):
        """Pull one edge of each of the net's boxes inward by `mm` (off a congested region). edge in
        {x0,x1,y0,y1}; x0/y0 move up (grow the value), x1/y1 move down (shrink the value)."""
        if edge not in ("x0", "x1", "y0", "y1"):
            raise ValueError("shrink: edge must be one of x0/x1/y0/y1, got %r" % edge)
        _EPS = 0.01                                     # a moved edge never CROSSES the opposite one
        for s in specs:
            r = s.rect()
            if r is None:
                continue
            x0, x1, y0, y1 = r
            # CLAMP to a sliver instead of letting the edge cross (a crossed edge would flip the
            # rect and read as WIDER via min/max -- an over-shrink must NECK, not grow, so the
            # min-pour-cross-section HARD gate can catch it).
            if edge == "x0":
                x0 = min(x0 + mm, x1 - _EPS)
            elif edge == "x1":
                x1 = max(x1 - mm, x0 + _EPS)
            elif edge == "y0":
                y0 = min(y0 + mm, y1 - _EPS)
            else:
                y1 = max(y1 - mm, y0 + _EPS)
            self._set_rect(s, x0, x1, y0, y1)

    def _op_relocate(self, specs, dxy=None, region=None):
        """Translate the net's boxes by (dx,dy), or (if `region` given) move the whole box set so its
        bounding box is centred on `region`'s centre (a lane moved off a foreign trace)."""
        if dxy is None and region is None:
            raise ValueError("relocate: pass dxy=(dx,dy) or region=(x0,y0,x1,y1)")
        if region is not None:
            rects = [s.rect() for s in specs if s.rect() is not None]
            if rects:
                bx0 = min(r[0] for r in rects); bx1 = max(r[1] for r in rects)
                by0 = min(r[2] for r in rects); by1 = max(r[3] for r in rects)
                tcx = (region[0] + region[2]) / 2.0; tcy = (region[1] + region[3]) / 2.0
                dxy = (tcx - (bx0 + bx1) / 2.0, tcy - (by0 + by1) / 2.0)
        dx, dy = dxy
        for s in specs:
            r = s.rect()
            if r is None:
                continue
            self._set_rect(s, r[0] + dx, r[1] + dx, r[2] + dy, r[3] + dy)

    def _op_notch(self, specs, at, gap_mm, vertical=None):
        """Open/widen the un-poured window centred on `at`=(x,y): pull each box's shunt-side edge back
        so the gap is >= gap_mm (reuses cec_fr._open_shunt_notch, the derive-time notch geometry)."""
        import cec_fr
        vert = vertical
        if vert is None:
            # default axis = the taller box set (EPS/PCIe top->bottom cables run vertical)
            rects = [s.rect() for s in specs if s.rect() is not None]
            vert = (max(r[3] for r in rects) - min(r[2] for r in rects)) >= \
                   (max(r[1] for r in rects) - min(r[0] for r in rects)) if rects else True
        for s in specs:
            r = s.rect()
            if r is None:
                continue
            nx0, nx1, ny0, ny1 = cec_fr._open_shunt_notch((r[0], r[1], r[2], r[3]), at, gap_mm,
                                                          vertical=vert)
            self._set_rect(s, nx0, nx1, ny0, ny1)

    def _op_drop_layer(self, net, layer):
        """Remove the net's pour on `layer` (F.Cu+B.Cu -> the other layer only, so foreign escapes
        under the remaining pour). ESCALATES if it would leave the net with NO pour (that is dropping
        a required pour, ruling 1)."""
        keep, drop = [], []
        for s in self.specs:
            if s.net == net and (layer in s.layers or (s.layers and s.layers[0] == layer)):
                drop.append(s)
            else:
                keep.append(s)
        if drop and not any(s.net == net for s in keep):
            raise EscalateToHuman(
                "drop_layer(%r, %r): removing that layer leaves net %r with NO pour -- dropping a "
                "required pour is a DESIGN change (ruling 1), escalate to human" % (net, layer, net))
        self.specs = keep

    def rebuild(self, op, *, net, min_cross_mm2=None, **kw):
        """THE router-rebuild verb. `op` in {notch, shrink, relocate, drop_layer} is an in-loop,
        SAME-net, geometry-only reshape of an EXISTING derived pour (ruling 1 autonomy). `op` in
        {add, drop} -- or any op naming a net with no derived pour -- raises EscalateToHuman (a
        design change). A frozen (human-ratified) spec is never mutated. AFTER the reshape the
        rebuilt pour's cross-section is checked as a HARD gate (ruling 2): a neck below the required
        cross-section raises PourCrossSectionRefused so a reshape can never thin copper to dodge the
        foreign-on-pour gate. Mutates the plan IN PLACE (state, not the board) and returns self.

        UNIFORMITY-PRESERVING (fix 3, owner ruling 2026-07-09): when `net` is a member of a per-cable
        family (>=2 positions), the reshape composes with the autonomy line by applying IDENTICALLY to
        ALL positions of the family -- otherwise it would break the per-cable output-field uniformity
        the derive-once-stamp-N guarantee established. The relative ops (shrink / drop_layer / relocate
        by dxy) replicate to every position; an op carrying an ABSOLUTE positional argument (notch at=,
        relocate region=) cannot be replicated identically and raises PourUniformityRefused (a named,
        non-silent refusal) -- it stays inside the autonomy line (it never adds/drops/re-nets a pour),
        it is refused only because it cannot hold the uniformity invariant."""
        # ---- AUTONOMY LINE (ruling 1): guard BEFORE touching geometry -----------------------------
        if op == "add":
            raise EscalateToHuman(
                "add-pour on net %r: the auto-derivation would not produce this pour -- ADDING a pour "
                "is a DESIGN change (ruling 1), escalate to human" % net)
        if op in ("drop", "remove"):
            raise EscalateToHuman(
                "drop-pour on net %r: DROPPING a required pour is a DESIGN change (ruling 1), "
                "escalate to human" % net)
        if op not in ("notch", "shrink", "relocate", "drop_layer"):
            raise EscalateToHuman(
                "pour op %r is not an in-loop reshape (notch/shrink/relocate/drop_layer) -- escalate "
                "to human" % op)
        _rename = kw.get("new_net") or kw.get("rename")
        if _rename is not None:
            raise EscalateToHuman(
                "reshape may not CHANGE a pour's net (%r -> %r) -- a net change is a DESIGN change "
                "(ruling 1), escalate to human" % (net, _rename))
        specs = self._specs_for(net)
        if not specs:
            raise EscalateToHuman(
                "reshape %r on net %r: no auto-derived pour exists on that net -- a reshape only "
                "reshapes an EXISTING derived pour; requesting a pour where none is derived is an "
                "ADD (design change, ruling 1), escalate to human" % (op, net))
        # ---- UNIFORMITY-PRESERVING (fix 3): a family-member reshape applies to ALL positions ------
        _fam_role = _parse_cable_net(net)
        fam_by_idx = fam_pre = fam_suf = None
        if _fam_role is not None:
            fam_pre, _fi, fam_suf = _fam_role
            fam_by_idx = self._cable_families().get((fam_pre, fam_suf))
        if fam_by_idx is not None:
            if op == "notch" or (op == "relocate" and kw.get("region") is not None):
                raise PourUniformityRefused(
                    "reshape %r on family net %r carries an ABSOLUTE positional argument (%s) that "
                    "cannot be replicated identically across the %d cable positions -- it would break "
                    "the per-cable output-field uniformity (owner ruling 2026-07-09); refusing"
                    % (op, net, "notch at=" if op == "notch" else "relocate region=", len(fam_by_idx)))
            specs = [s for i in sorted(fam_by_idx) for s in fam_by_idx[i]]   # reshape EVERY position
        if any(s.frozen for s in specs):
            raise EscalateToHuman(
                "reshape %r on net %r: a spec is FROZEN (human-ratified geometry the loop may not "
                "mutate, ruling 1), escalate to human" % (op, net))
        # ATOMIC: snapshot so a cross-section REFUSAL leaves the plan UNCHANGED (a refused reshape
        # must not leave the pour half-necked -- the loop moves on with the original geometry).
        snap_specs = list(self.specs)
        snap = [(s, s.polygon, s.region, s.provenance) for s in self.specs]
        try:
            # ---- the geometry op (same net, geometry only) ---------------------------------------
            if op == "notch":
                self._op_notch(specs, kw["at"], kw.get("gap_mm", 6.5), kw.get("vertical"))
            elif op == "shrink":
                self._op_shrink(specs, kw["edge"], kw["mm"])
            elif op == "relocate":
                self._op_relocate(specs, kw.get("dxy"), kw.get("region"))
            elif op == "drop_layer":
                if fam_by_idx is not None:               # drop the layer on EVERY position's net
                    for i in sorted(fam_by_idx):
                        self._op_drop_layer(fam_pre + str(i) + fam_suf, kw["layer"])
                    specs = [s for i in sorted(fam_by_idx)
                             for s in self._specs_for(fam_pre + str(i) + fam_suf)]
                else:
                    self._op_drop_layer(net, kw["layer"])
                    specs = self._specs_for(net)         # refresh after the removal
            for s in specs:
                if s.provenance == "derived":
                    s.provenance = "router_ask"
            # ---- HARD cross-section gate on the rebuilt pour (ruling 2) ---------------------------
            floor = _DEFAULT_MIN_CROSS_MM2 if min_cross_mm2 is None else float(min_cross_mm2)
            after = self._min_cross_mm2(net)
            if after is not None and after < floor - 1e-9:
                raise PourCrossSectionRefused(
                    "reshape %r on net %r necks the rebuilt pour to %.4f mm^2 < required %.4f mm^2 "
                    "(min-pour-cross-section HARD gate, ruling 2) -- a reshape must never neck copper "
                    "to dodge the foreign-on-pour gate" % (op, net, after, floor))
        except PourCrossSectionRefused:
            self.specs = snap_specs                      # roll back the drop_layer removal
            for s, poly, region, prov in snap:
                s.polygon, s.region, s.provenance = poly, region, prov
            raise
        return self

    # ------------------------------------------------------------------ serialization (stage 3)
    def to_dict(self):
        """JSON-serializable form (specs + sig + recipe). The private board handles are dropped --
        a loaded plan re-attaches the board being routed for the non-lane keepout derivation."""
        return {"version": 1, "board_sig": self.board_sig, "recipe": self.recipe,
                "specs": [_spec_to_dict(s) for s in self.specs]}

    @classmethod
    def from_dict(cls, d, *, board_path=None, board=None, kelvin_pairs=None, nets_12v=None):
        plan = cls(specs=[_spec_from_dict(s) for s in d.get("specs", [])],
                   board_sig=d.get("board_sig", ""), recipe=d.get("recipe", {}))
        plan._board_path = board_path
        plan._board = board
        plan._kelvin_pairs = kelvin_pairs
        plan._nets_12v = nets_12v
        return plan


# --------------------------------------------------------------------------- module helpers
def _ask_spec(ask, prepared, bbox, margin):
    """Resolve a placer/router ask -> a PourSpec, or None if it can't derive a box. region_hint
    given -> that box; else auto-derive from the net's pads (default). Clamped to `bbox`."""
    net = ask["net"]
    region = ask.get("region_hint")
    bx0, by0, bx1, by1 = bbox
    if region:
        x0, y0, x1, y1 = region
    else:
        pts = [(x, y) for (_ref, x, y, _t) in prepared.get(net, [])]
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
    x0 = max(bx0, x0); y0 = max(by0, y0)
    x1 = min(bx1, x1); y1 = min(by1, y1)
    if x1 - x0 < 0.8 or y1 - y0 < 0.6:
        return None
    return PourSpec(net=net, layers=tuple(ask.get("layers", ("F.Cu",))),
                    shape=ask.get("shape", "lane"), region=(x0, y0, x1, y1),
                    priority=int(ask.get("priority", _PRIORITY_DEFAULT)),
                    provenance=ask.get("provenance", "placer_ask"),
                    polygon=((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


def _spec_to_dict(s: PourSpec):
    d = asdict(s)
    d["layers"] = list(s.layers)
    d["exempt_nets"] = list(s.exempt_nets)
    d["region"] = list(s.region) if s.region is not None else None
    d["polygon"] = [list(pt) for pt in s.polygon]
    return d


def _spec_from_dict(d):
    return PourSpec(net=d["net"], layers=tuple(d.get("layers", ("F.Cu",))),
                    shape=d.get("shape", "rect"),
                    region=tuple(d["region"]) if d.get("region") is not None else None,
                    priority=int(d.get("priority", _PRIORITY_DEFAULT)),
                    notch=d.get("notch"),
                    exempt_nets=tuple(d.get("exempt_nets", ())),
                    min_thickness=float(d.get("min_thickness", _MIN_THICKNESS_DEFAULT)),
                    island_removal=int(d.get("island_removal", _ISLAND_REMOVAL_DEFAULT)),
                    provenance=d.get("provenance", "derived"),
                    frozen=bool(d.get("frozen", False)),
                    polygon=tuple(tuple(pt) for pt in d.get("polygon", ())))
