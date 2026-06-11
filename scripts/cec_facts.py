#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_facts -- board facts + the ONE shared scope resolver (CL-23 seed).
# ============================================================================
# Seeded by CL-03 Ruling 6: scope resolution against board facts happens in
# exactly one place, owned by the facts module, so every tier argues over
# identical facts. Wave-3 CL-23 (board-facts serialization for swarm/panel/
# intent-compiler) absorbs and extends this module; until then it carries:
#
#   * BOARD CATALOG     -- the repo's boards + their FAMILY memberships
#                          (entry scope "families" binds per-board compilation)
#   * board_facts()     -- pcbnew-FREE text extraction (net names, refs,
#                          lib_ids) so the host compile leg stays
#                          dependency-free; pcbnew-grade reading lands wave 3
#   * resolve_scope()   -- SCHEMA-shape scope -> per-dimension object matches
#                          on one board; unscoped/inexpressible => ZERO
#                          coverage (RB-01)
#   * compiled_param()  -- promoted-only binding for compiled params
#                          (CL-03 Ruling 7 resolution order: compiled-promoted
#                          value if present, else the caller's hand value)
# ============================================================================
import fnmatch, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPILED_ROOT = os.path.join(ROOT, "build", "corpus-compiled")

# ---------------------------------------------------------------- catalog --
# Family vocabulary (SCHEMA.md scope.families): the side of the link a board
# sits on ("hub" / "module") plus the board's own name, so an entry may scope
# platform-wide, side-wide, or board-specific.


def board_catalog():
    """[{name, dir, pcb, sch, families:[...]}] for every board dir with a design file.
    Sorted by name (compiler determinism depends on stable iteration)."""
    out = []
    for side, fam in (("hubs", "hub"), ("modules", "module")):
        base = os.path.join(ROOT, side)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            bdir = os.path.join(base, name)
            if not os.path.isdir(bdir):
                continue
            pcbs = sorted(f for f in os.listdir(bdir) if f.endswith(".kicad_pcb"))
            schs = sorted(f for f in os.listdir(bdir) if f.endswith(".kicad_sch"))
            if not pcbs and not schs:
                continue
            out.append({
                "name": name, "dir": bdir,
                "pcb": os.path.join(bdir, pcbs[0]) if pcbs else None,
                "sch": os.path.join(bdir, schs[0]) if schs else None,
                "families": [fam, name],
            })
    return out


def find_board(name):
    for b in board_catalog():
        if b["name"] == name:
            return b
    return None


def families_match(entry_families, board_families):
    """Does an entry's declared family scope cover this board? Empty/absent
    declaration matches NOTHING (unscoped = zero coverage, RB-01)."""
    return bool(set(entry_families or []) & set(board_families or []))


# ------------------------------------------------------------------ facts --
# KiCad 10 dropped the numbered net table -- objects reference nets by NAME:
# (net "GND"). Older boards carry (net 12 "GND"); match both.
_NET_PCB = re.compile(r'\(net\s+(?:\d+\s+)?"([^"]*)"\)')
_FP = re.compile(r'\(footprint\s+"([^"]+)"')
_REF = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
_SCH_LIBID = re.compile(r'\(symbol\s+\(lib_id\s+"([^"]+)"\)')


def board_facts(board):
    """Text-extracted facts for one catalog row: nets, refs, lib_ids.
    pcbnew-free by design (host compile leg); richer geometry facts are the
    wave-3 CL-23 extension. Degrades to empty sets when files are absent."""
    nets, refs, libids = set(), [], []
    if board.get("pcb") and os.path.isfile(board["pcb"]):
        text = open(board["pcb"], encoding="utf-8", errors="replace").read()
        nets |= {n for n in _NET_PCB.findall(text) if n}
        libids = sorted(set(_FP.findall(text)))
        refs = sorted(set(_REF.findall(text)))
    elif board.get("sch") and os.path.isfile(board["sch"]):
        text = open(board["sch"], encoding="utf-8", errors="replace").read()
        libids = sorted(set(_SCH_LIBID.findall(text)))
        refs = sorted(set(_REF.findall(text)))
    # board-manifest net ALIASES (owner ruling #11, 2026-06-10): a fixed-in-
    # stone rev whose net names predate a platform convention declares the
    # role mapping in board-manifest.json; alias names join the matchable set
    # so convention-named scopes resolve honestly (the rename itself is a
    # queued erratum for the next rev, never a silent fact rewrite).
    mpath = os.path.join(board["dir"], "board-manifest.json")
    fab_target = None
    if os.path.isfile(mpath):
        try:
            manifest = json.load(open(mpath))
            aliases = manifest.get("net_aliases", {})
            nets |= {a for a, real in aliases.items()
                     if any(_net_match(real, n) or real == n for n in nets)}
            # fab-target block (owner ruling D2, 2026-06-10): vendor-scoped corpus
            # entries resolve against where the board is GOING -- {vendor,
            # service_tier}. Absent block => vendor entries resolve to zero
            # coverage on this board (review-note only, honest per RB-01).
            ft = manifest.get("fab_target")
            if isinstance(ft, dict) and ft.get("vendor"):
                fab_target = {"vendor": str(ft["vendor"]).lower(),
                              "service_tier": (str(ft["service_tier"]).lower()
                                               if ft.get("service_tier") else None)}
        except Exception:                                     # noqa: BLE001
            pass
    return {"name": board["name"], "families": board["families"],
            "nets": sorted(nets), "refs": refs, "lib_ids": libids,
            "fab_target": fab_target,
            "pins_per_lane": pins_per_lane(board["name"])}


_AUTONAME = re.compile(r"^Net-\(([^-]+)-(.+)\)$")


def _net_match(pattern, net):
    """Net-family matching by the repo's naming conventions (cec_score-style):
    a pattern matches the net name with or without its sheet-path prefix;
    fnmatch wildcards work (e.g. '/SENSEP*'); and KiCad AUTO-NAMES unwrap to
    their pad-name half (Net-(J1-CAN1_H) is electrically CAN1_H at J1)."""
    cands = {net, net.split("/")[-1]}
    m = _AUTONAME.match(net)
    if m:
        cands.add(m.group(2))
    for cand in cands:
        if fnmatch.fnmatch(cand, pattern) or fnmatch.fnmatch(cand, pattern.lstrip("/")):
            return True
    return pattern.lstrip("/") in cands


# --------------------------------------------------- §6.13 lane topology --
# Owner ruling 2026-06-10 (cluster-6 follow-through): alarm thresholds are
# defined PER-PIN, matching the spec ratings; per-lane trip values resolve
# through THIS fact at §6.13 lock time -- the single-resolver discipline.
# pins_per_lane = how many connector power pins one sensed lane (one shunt)
# aggregates. CONFIRMED 2026-06-10 via BOTH paths: the generator ground truth
# (gen-modules PINMAP: EPS 12V=[5,6,7,8], PCIe 12V=[1,2,3]) AND an independent
# schematic read (SENSEC1_HI label count in the hand-sourced schematics: 4
# connector-area labels on EPS, 3 on PCIe -- panel wf_1ad00275 verification).
# 12VHPWR Standard/Pro sense PER PIN (6 shunts, one per +12V pin).
PINS_PER_LANE = {
    "12vhpwr-standard": 1,
    "12vhpwr-pro": 1,
    "eps-8pin": 4,
    "pcie-8pin-2port": 3,
    "pcie-8pin-3port": 3,
}


def pins_per_lane(board_or_family):
    """Per-family lane-aggregation fact (None = the board has no sensed
    power lanes, e.g. Hubs). Per-lane trip = per-pin threshold x this."""
    return PINS_PER_LANE.get(board_or_family)


SCOPE_DIMS = ("net_families", "netclasses", "part_classes", "regions", "families",
              # owner ruling D2 (2026-06-10): vendor-pile scope keys. Carried ONLY by
              # vendor-pile entries (lint enforces the pile separation); resolved
              # against the board manifest's fab_target block.
              "vendor", "service_tier")


def is_schema_scope(scope):
    """SCHEMA-shape test (Ruling 6, strict): dict, every key a known dimension,
    every value a list of strings, at least one dimension declared."""
    if not isinstance(scope, dict) or not scope:
        return False
    for k, v in scope.items():
        if k not in SCOPE_DIMS:
            return False
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return False
    return True


def resolve_scope(scope, facts):
    """The shared resolver: SCHEMA-shape scope -> matches on one board's facts.
    Returns {applicable, matches:{dim:[...]}, object_count, countable} --
    `countable` is False when only non-enumerable dims (families/regions/
    netclasses-without-pro-parse) are declared, so a zero count is N/A rather
    than a mis-scope signal."""
    if not is_schema_scope(scope):
        return {"applicable": False, "matches": {}, "object_count": 0, "countable": False}
    if "families" in scope and not families_match(scope["families"], facts["families"]):
        return {"applicable": False, "matches": {}, "object_count": 0, "countable": False}
    # vendor scope (owner ruling D2, 2026-06-10): resolves against the board
    # manifest's fab_target. No declared fab target => ZERO coverage on this
    # board (vendor_unresolved=True; the compiler reports it as a review note --
    # honest per RB-01, because vendor entries can carry geometric compile
    # targets conditional on where the board is going). A declared target that
    # MISMATCHES is a resolved non-match, not unresolved.
    if "vendor" in scope or "service_tier" in scope:
        ft = facts.get("fab_target") or {}
        if not ft.get("vendor"):
            return {"applicable": False, "matches": {}, "object_count": 0,
                    "countable": False, "vendor_unresolved": True}
        if "vendor" in scope and ft["vendor"] not in [v.lower() for v in scope["vendor"]]:
            return {"applicable": False, "matches": {}, "object_count": 0, "countable": False}
        if "service_tier" in scope:
            if not ft.get("service_tier"):
                # vendor known, tier unknown: a tier-conditional rule cannot bind
                return {"applicable": False, "matches": {}, "object_count": 0,
                        "countable": False, "vendor_unresolved": True}
            if ft["service_tier"] not in [t.lower() for t in scope["service_tier"]]:
                return {"applicable": False, "matches": {}, "object_count": 0, "countable": False}
    matches, countable = {}, False
    if "net_families" in scope:
        countable = True
        matches["net_families"] = sorted(
            n for n in facts["nets"] if any(_net_match(p, n) for p in scope["net_families"]))
    if "part_classes" in scope:
        countable = True
        matches["part_classes"] = sorted(
            r for r, l in zip(facts["refs"], [""] * len(facts["refs"]))
            if any(fnmatch.fnmatch(r, p) for p in scope["part_classes"])) or sorted(
            l for l in facts["lib_ids"]
            if any(p.lower() in l.lower() for p in scope["part_classes"]))
    # netclasses/regions: declared coverage only -- not text-enumerable yet
    # (netclass membership needs the .kicad_pro parse; regions need geometry).
    count = sum(len(v) for v in matches.values())
    return {"applicable": True, "matches": matches, "object_count": count,
            "countable": countable}


# ----------------------------------------------------------------- params --
def compiled_param(key, default=None, *, root=None):
    """CL-03 Ruling 7 resolution order, the promoted-binding half: return the
    compiled PROMOTED value for `key` if the compiled tree carries one, else
    `default` (the caller's hand value). Staging values are NEVER returned --
    a staging delta is an advisory fire, not an override."""
    path = os.path.join(root or COMPILED_ROOT, "params.json")
    try:
        rows = json.load(open(path))
    except Exception:                                            # noqa: BLE001
        return default
    for row in rows if isinstance(rows, list) else []:
        if row.get("key") == key and row.get("binding") == "gate":
            return row.get("value", default)
    return default


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CEC board facts (CL-23 seed)")
    ap.add_argument("board", nargs="?", help="board name (omit to list catalog)")
    a = ap.parse_args()
    if not a.board:
        for b in board_catalog():
            print("%-22s families=%s pcb=%s" % (b["name"], b["families"], bool(b["pcb"])))
    else:
        b = find_board(a.board)
        print(json.dumps(board_facts(b), indent=1) if b else "unknown board")
