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
from dataclasses import dataclass, field, asdict


# add_power_pours' own defaults (cec_fr.add_power_pours); a derived spec carries these, so
# pour_polygons() emits them only when a spec OVERRIDES one -> a derived plan is byte-identical
# to today's derive_power_pours output ({net, layer, polygon} exactly).
_PRIORITY_DEFAULT = 2
_MIN_THICKNESS_DEFAULT = 0.25
_ISLAND_REMOVAL_DEFAULT = 0


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
        """Append a pour geometry the derivation would not produce (a placer/router ask). The
        reshape verbs (notch/shrink/relocate/drop_layer) are the router-rebuild actuation surface
        and land with the stage-4 rebuild verb (owner-gated); stages 1-3 only need `add`."""
        self.specs.append(spec)
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
