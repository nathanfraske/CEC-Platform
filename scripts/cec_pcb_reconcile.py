#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_pcb_reconcile -- PCB reconciliation for the hierarchical schematic
#  conversion (docs/standard-tier-review/round4-hier-conversion-2026-07-04.md).
# ============================================================================
# The four module boards' flat schematics are being regenerated as
# hierarchical (root + leaf) projects. That regeneration changes every symbol
# UUID / sheet path (breaking each PCB footprint's `(path ...)` link) and
# renames leaf-internal nets from "/NAME" to "/<sheetname>/NAME" (inter-sheet
# nets keep their exact old names via labeled root lanes -- see the plan doc's
# "Measured facts" section). This module repairs the .kicad_pcb (and the
# .kicad_pro / .kicad_dru netclass references) to match, headlessly, with hard
# verification at every step.
#
# CALIBRATION FINDINGS (2026-07-04, this session -- do not re-derive, the plan
# doc's assumed format was WRONG on two counts):
#   1. A footprint's `(path "...")` field is NOT "/<root_sch_uuid>/<symbol_uuid>".
#      Measured against the committed hub-standard PCB (flat project): the path
#      is JUST "/<symbol_uuid>" -- the root schematic's own document uuid is
#      NEVER part of it. Confirmed via `kicad-cli sch export netlist`'s
#      `(sheetpath (tstamps "..."))` field, which for a flat (root-level)
#      symbol is literally "/" (not the root doc uuid) -- concatenated with the
#      symbol's own `(tstamps "...")` (== the schematic symbol's own uuid) that
#      gives the exact PCB path string. For a symbol nested N sheets deep, the
#      sheetpath tstamps is "/<sheet1_uuid>/.../<sheetN_uuid>/" (the chain of
#      SHEET-INSTANCE uuids from the root's `(sheet ...)` blocks, never the
#      root document's own uuid) -- confirmed structurally against
#      hub-enterprise's nested 01-power-input -> 01a-efuse-main sheets. So:
#          footprint_path = sheetpath_tstamps + own_tstamps
#      (sheetpath_tstamps already ends with "/", so this is plain
#      concatenation, no separator logic needed.) `kicad-cli sch export
#      netlist` computes this for us directly -- symbol_paths() below does NOT
#      hand-walk the sheet hierarchy; it parses the exported netlist's
#      per-component sheetpath+tstamps, which is simpler and matches KiCad's
#      own back-annotation logic exactly rather than an independently
#      re-derived approximation.
#   2. KiCad 10's NATIVE pcbnew writer no longer serializes numeric net codes
#      at all: pads / track segments / vias / zones all carry a bare
#      `(net "<name>")` string field (no `(net <N> "<name>")`, no separate
#      `(net_name "<name>")` for zones -- that is pre-10 syntax). Measured on
#      hub-standard.kicad_pcb and 12vhpwr-standard-module.kicad_pcb (both
#      generator "pcbnew"): zero occurrences of the numbered form anywhere.
#      HOWEVER the repo's own custom generator (scripts/cec_pcb.py /
#      gen-module-pcb.py, `generator "cec-cec_pcb"`) still emits the OLDER
#      `(net <N> "<name>")` form in both the top net dictionary AND inline on
#      every pad -- and KiCad 10 loads that fine (backward-compatible reader).
#      eps-8pin / pcie-8pin-2port / pcie-8pin-3port are ALL in this older
#      generator form (and are placement-only, zero copper, so no zone/segment
#      net strings exist there today); 12vhpwr-standard is real-pcbnew-native
#      form WITH filled zones. reconcile_pcb() below therefore handles BOTH
#      syntaxes uniformly via one regex that makes the numeric code optional.
# ============================================================================
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cec_toolchain as TC  # noqa: E402

try:
    import pcbnew                       # only the verify step needs it
except ImportError:                     # host without the KiCad python bindings
    pcbnew = None


def _require_pcbnew(action="this operation"):
    if pcbnew is None:
        raise RuntimeError(f"{action} requires the KiCad python bindings (pcbnew), "
                            "which are not importable on this host.")
    return pcbnew


# --------------------------------------------------------------- netlist I/O
def _export_netlist_text(sch_path):
    """Run `kicad-cli sch export netlist` and return the exported text, or
    raise RuntimeError with kicad-cli's stderr on failure."""
    cli = TC.require_kicad_cli("schematic netlist export")
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as f:
        out = f.name
    try:
        r = subprocess.run([cli, "sch", "export", "netlist", "-o", out, sch_path],
                            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out) or not os.path.getsize(out):
            raise RuntimeError(
                f"kicad-cli sch export netlist failed for {sch_path} "
                f"(rc={r.returncode}): {r.stderr.strip()}")
        return open(out, encoding="utf-8").read()
    finally:
        if os.path.exists(out):
            os.unlink(out)


def netlist_groups(sch_path):
    """{frozenset({(ref, pin), ...}): net_name} for every net in sch_path.

    This is the name-AGNOSTIC connectivity fingerprint: two exports of "the
    same circuit" under different net names produce identical group keys (the
    (ref,pin) membership), which is exactly the invariant a rename must
    preserve and a real connectivity change must not. Mirrors
    cec_sch_mcp._netlist_groups's parsing approach (paren-depth-bounded block
    extraction, not a single greedy regex) -- kept local here rather than
    imported so this module has no dependency on the `mcp` pip package, which
    is not part of the core kicad-cli/pcbnew toolchain this script otherwise
    only needs.

    `sch_path` may be the ROOT .kicad_sch of a hierarchical project (with
    sibling leaf .kicad_sch files in the same directory) -- kicad-cli resolves
    the whole hierarchy from the root file. For a baseline extracted from git
    history, a FLAT baseline needs only that one file (self-contained via its
    embedded lib_symbols); a hierarchical baseline needs its leaf files
    checked out alongside it too -- see checkout_git_tree() below, used by the
    CLI to populate an explicit workdir before calling this function.
    """
    txt = _export_netlist_text(sch_path)
    groups = {}
    for m in re.finditer(r'\(net\s+\(code', txt):
        d, i = 0, m.start()
        while True:
            c = txt[i]
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            i += 1
        blk = txt[m.start():i + 1]
        nm = re.search(r'\(name "([^"]*)"\)', blk)
        mem = frozenset(re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk))
        if mem:
            groups[mem] = nm.group(1) if nm else "?"
    return groups


def symbol_paths(root_sch_path):
    """{ref: "/<sheet-uuid-chain>/<symbol-uuid>"} for every schematic
    component with a footprint, exactly matching what KiCad stores in each
    footprint's `(path "...")` field (see the CALIBRATION FINDINGS header).

    Built from `kicad-cli sch export netlist`'s per-`(comp ...)` block: each
    carries `(sheetpath (names "...") (tstamps "<chain>"))` followed by the
    component's own `(tstamps "<uuid>")`. Power/no-footprint symbols (refs
    like "#PWR1", "#FLG1") never appear as `(comp ...)` entries in the
    exported netlist, so this dict naturally only contains footprint-bearing
    refs -- no filtering needed.
    """
    txt = _export_netlist_text(root_sch_path)
    paths = {}
    for m in re.finditer(r'\(comp\s*\(ref "([^"]+)"\)', txt):
        ref = m.group(1)
        start = m.start()
        d, i = 0, start
        while True:
            c = txt[i]
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            i += 1
        blk = txt[start:i + 1]
        sp = re.search(
            r'\(sheetpath\s*\(names "[^"]*"\)\s*\(tstamps "([^"]*)"\)\s*\)'
            r'\s*\(tstamps "([^"]*)"\)', blk)
        if not sp:
            continue
        sheet_tstamps, own_tstamps = sp.groups()
        paths[ref] = sheet_tstamps + own_tstamps
    return paths


# ------------------------------------------------------------- rename mapping
_LEAF_RENAME_RE = re.compile(r'^/([^/]+)(/.+)$')


def build_rename_map(old_groups, new_groups):
    """{old_name: new_name} for nets whose name changed, matched by identical
    (ref,pin) connectivity group -- the name-agnostic bridge between a flat
    baseline and its hierarchical successor.

    Hard asserts (raise ValueError on any violation -- these are correctness
    gates, not warnings):
      * group-key sets are EXACTLY equal (0 missing / 0 extra) -- otherwise
        the schematic conversion changed connectivity, which this tool must
        never paper over.
      * old_groups values are unique (a sane netlist has one name per net) and
        likewise new_groups -- defensive; a violation here means the netlist
        export itself is inconsistent.
      * the induced old_name -> new_name mapping is a BIJECTION (no two old
        names collapsing onto one new name, and vice versa).
      * every CHANGED pair matches the one allowed shape: old "/X" ->
        new "/<leaf>/X" -- identical terminal net name, prefixed by exactly
        one new leading path segment (the leaf sheet name). Anything else
        (a truncated/altered basename, a multi-segment old name, an inserted
        SUFFIX instead of a prefix, etc.) is a hard error.
    """
    old_keys, new_keys = set(old_groups), set(new_groups)
    missing = old_keys - new_keys
    extra = new_keys - old_keys
    if missing or extra:
        raise ValueError(
            f"connectivity group mismatch: {len(missing)} missing, "
            f"{len(extra)} extra (baseline groups={len(old_groups)}, "
            f"new groups={len(new_groups)})")

    if len(set(old_groups.values())) != len(old_groups):
        raise ValueError("baseline netlist has duplicate net names across "
                          "distinct connectivity groups")
    if len(set(new_groups.values())) != len(new_groups):
        raise ValueError("new netlist has duplicate net names across "
                          "distinct connectivity groups")

    full_map = {old_groups[k]: new_groups[k] for k in old_keys}
    if len(set(full_map.values())) != len(full_map):
        # find the collision(s) for a useful error
        seen = {}
        dupes = []
        for old, new in full_map.items():
            if new in seen:
                dupes.append((seen[new], old, new))
            else:
                seen[new] = old
        raise ValueError(f"rename map is not a bijection -- names collapsed: {dupes}")

    changed = {old: new for old, new in full_map.items() if old != new}

    for old, new in changed.items():
        m = _LEAF_RENAME_RE.match(new)
        ok = bool(m) and m.group(2) == old and old.count('/') == 1 and old.startswith('/')
        if not ok:
            raise ValueError(
                f"disallowed rename shape: '{old}' -> '{new}' (only "
                f"'/X' -> '/<leaf>/X', same terminal segment, is permitted)")

    return changed


# ------------------------------------------------------------- PCB reconcile
# One net-name regex covers every construct that carries a net STRING in a
# .kicad_pcb, in BOTH the syntaxes measured in this repo (see the
# CALIBRATION FINDINGS header): the legacy cec-cec_pcb generator's
# `(net <N> "<name>")` (top dict entries AND inline on every pad) and native
# KiCad 10's code-free `(net "<name>")` (pads / segments / vias / zones), plus
# the older paired zone form `(net_name "<name>")` (with a separate bare
# `(net <N>)` alongside it that carries no name and needs no edit). The
# optional `(?:\s+\d+)?` makes the numeric code optional so one pattern
# matches all of the above; the group split (prefix / name / suffix) makes
# substitution a pure string swap that never touches surrounding formatting.
_NET_STR_RE = re.compile(r'(\(net(?:_name)?(?:\s+\d+)?\s+")((?:[^"\\]|\\.)*)("\))')
_PATH_RE = re.compile(r'(\(path ")([^"]*)("\))')
_FP_REF_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"')
_SHEETNAME_RE = re.compile(r'(\(property\s+"Sheetname"\s+")([^"]*)("\))')
_SHEETFILE_RE = re.compile(r'(\(property\s+"Sheetfile"\s+")([^"]*)("\))')


def _iter_footprint_blocks(text):
    """Yield (start, end, block_text) for each top-level `(footprint "...")`
    s-expr span, via paren-depth counting (footprints nest arbitrarily deep
    -- pads, 3D models, private text -- so a regex alone cannot find the
    matching close paren)."""
    for m in re.finditer(r'\(footprint "', text):
        start = m.start()
        d, i = 0, start
        while True:
            c = text[i]
            if c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            i += 1
        yield start, i + 1, text[start:i + 1]


def _pcbnew_net_names(pcb_path):
    """{net_name, ...} as pcbnew itself resolves them on load -- the ground
    truth for "did the rename actually take," independent of our own regex
    bookkeeping."""
    _require_pcbnew("PCB net-identity verification")
    board = pcbnew.LoadBoard(pcb_path)
    names = set()
    for net in board.GetNetInfo().NetsByNetcode().values():
        names.add(net.GetNetname())
    return names


def reconcile_pcb(pcb_path, rename_map, path_map, dry_run=False, sheet_names=None):
    """Rewrite pcb_path in place: rename every net string per rename_map, and
    relink every footprint's `(path ...)` (by matching its `Reference`
    property against path_map) to the new hierarchical instance path.

    sheet_names, if given, is {ref: (new_sheetname, new_sheetfile)} and
    additionally updates a footprint's `Sheetname`/`Sheetfile` properties when
    present -- no board in this repo carries those today (verified: they are
    only written by KiCad's own schematic<->PCB sync once a board has gone
    through a real hierarchical "Update PCB from Schematic", which is out of
    scope for this headless tool), so this is a forward-compatible no-op in
    current use, exercised directly by a synthetic unit test.

    dry_run=True computes and returns the report WITHOUT writing or running
    the pcbnew verification pass (useful for a quick preview).

    On any post-rewrite verification failure the original file bytes are
    restored before raising -- callers never observe a half-reconciled board.
    """
    original_text = open(pcb_path, encoding="utf-8").read()

    report = {"net_renames": 0, "path_updates": 0, "path_unchanged": 0,
              "mechanical_skipped": 0, "path_absent_known_ref": [],
              "sheetname_updates": 0, "sheetfile_updates": 0,
              "path_missing_ref": [], "path_map_misses": []}

    # ---- 1. net-string renames, everywhere in the file
    def _net_repl(m):
        name = m.group(2)
        if name in rename_map:
            report["net_renames"] += 1
            return m.group(1) + rename_map[name] + m.group(3)
        return m.group(0)

    text = _NET_STR_RE.sub(_net_repl, original_text)

    # ---- 2. per-footprint path (+ optional Sheetname/Sheetfile) relink
    pieces = []
    last = 0
    for start, end, blk in _iter_footprint_blocks(text):
        refm = _FP_REF_RE.search(blk)
        ref = refm.group(1) if refm else None
        pathm = _PATH_RE.search(blk)
        new_blk = blk
        if pathm is None:
            if ref is not None and ref in path_map:
                # a real schematic-backed component that simply has no
                # `(path ...)` field in THIS board today -- measured on
                # eps-8pin/pcie-8pin-2port/pcie-8pin-3port (generator
                # "cec-cec_pcb"/"cec-gen-pcie-condensed": every one of their
                # ~45-58 real footprints carries zero `path` fields; only
                # boards saved by real pcbnew, e.g. 12vhpwr-standard, carry
                # them). Pre-existing, unrelated to this rename -- left
                # untouched (never fabricate a new field) but reported
                # distinctly from true mechanical parts so it is not silently
                # conflated with "nothing to do here."
                report["path_absent_known_ref"].append(ref)
            else:
                # genuinely mechanical (mounting hole / fiducial / logo /
                # test point) -- never linked to a schematic symbol at all.
                report["mechanical_skipped"] += 1
        elif ref is None or ref not in path_map:
            report["path_missing_ref"].append(ref)
        else:
            new_path = path_map[ref]
            old_path = pathm.group(2)
            if old_path != new_path:
                new_blk = _PATH_RE.sub(
                    lambda m: m.group(1) + new_path + m.group(3), new_blk, count=1)
                report["path_updates"] += 1
            else:
                report["path_unchanged"] += 1

        if sheet_names and ref in sheet_names:
            new_sn, new_sf = sheet_names[ref]
            if _SHEETNAME_RE.search(new_blk):
                new_blk = _SHEETNAME_RE.sub(
                    lambda m: m.group(1) + new_sn + m.group(3), new_blk, count=1)
                report["sheetname_updates"] += 1
            if _SHEETFILE_RE.search(new_blk):
                new_blk = _SHEETFILE_RE.sub(
                    lambda m: m.group(1) + new_sf + m.group(3), new_blk, count=1)
                report["sheetfile_updates"] += 1

        pieces.append(text[last:start])
        pieces.append(new_blk)
        last = end
    pieces.append(text[last:])
    new_text = "".join(pieces)

    report["path_map_misses"] = sorted(
        r for r in path_map if r not in {m.group(1) for m in _FP_REF_RE.finditer(text)})
    report["changed"] = new_text != original_text

    if dry_run:
        report["dry_run"] = True
        report["verified"] = None
        return report

    if not report["changed"]:
        report["verified"] = True
        return report

    before_nets = _pcbnew_net_names(pcb_path)   # ground truth, pre-image

    with open(pcb_path, "w", encoding="utf-8") as f:
        f.write(new_text)

    def _rollback(reason):
        with open(pcb_path, "w", encoding="utf-8") as f:
            f.write(original_text)
        raise RuntimeError(f"reconcile_pcb verification failed, rolled back: {reason}")

    try:
        after_nets = _pcbnew_net_names(pcb_path)
    except Exception as e:                      # noqa: BLE001 -- deliberate: any load failure rolls back
        _rollback(f"reconciled board would not load in pcbnew: {e}")
        raise  # unreachable, _rollback always raises; keeps linters happy

    # Scope the text-level orphan scan to actual net-string CONSTRUCTS (the
    # same regex the rename itself used), not a blind whole-file substring
    # search -- a bare `"OLDNAME"` can legitimately still occur elsewhere
    # (e.g. `(pinfunction "GND")`, an unrelated property value) without that
    # being an orphaned net reference.
    remaining_net_strings = {m.group(2) for m in _NET_STR_RE.finditer(new_text)}

    problems = []
    if len(after_nets) != len(before_nets):
        problems.append(f"net count changed: {len(before_nets)} -> {len(after_nets)}")
    for old, new in rename_map.items():
        if new not in after_nets:
            problems.append(f"renamed net missing after rewrite: {new!r}")
        if old in after_nets:
            problems.append(f"orphan old net name still present (pcbnew): {old!r}")
        if old in remaining_net_strings:
            problems.append(f"orphan old net-name string still present in a net construct: {old!r}")

    if problems:
        _rollback("; ".join(problems))

    report["verified"] = True
    report["net_count_before"] = len(before_nets)
    report["net_count_after"] = len(after_nets)
    return report


# --------------------------------------------------------- project reconcile
def _fnmatch_any(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def reconcile_project(pro_path, dru_path, rename_map, dry_run=False):
    """Keep `.kicad_pro` netclass patterns (and any literal net names in
    `.kicad_dru`) matching the SAME underlying nets after a rename.

    A netclass's real invariant is not "the pattern text" but "which nets it
    covers." Only nets that actually appear in rename_map can possibly change
    membership (an unrenamed net's name string is byte-identical before/after,
    so its fnmatch outcome against any unchanged pattern cannot change) --
    that lets this function work from rename_map alone, without needing the
    full old/new net-name universe.

    For each netclass and each (old, new) rename pair:
      * matched before, NOT matched after -> the rename silently orphaned the
        net from its netclass (a leaf-scoped rename outrunning a wildcard,
        e.g. "/SENSEC*" no longer matching "/02-sensing/SENSEC1_HI"). Fixed by
        APPENDING an explicit `{netclass, pattern: new}` entry -- the minimal
        change that restores exactly this one net without touching any
        sibling pattern's other members.
      * NOT matched before, matched after -> the rename accidentally walked
        the net into a class it never belonged to (a coincidental match
        against an unrelated existing pattern). There is no safe additive
        fix (narrowing the pre-existing pattern risks its other members) --
        this raises ValueError. The test suite exercises this path directly
        (`.kicad_pro`_membership-equality: "a clear failure when equality is
        impossible").

    `.kicad_dru`: no board in this repo references a literal net name in a
    rule `condition` today (all observed conditions are `A.NetClass == ...`;
    verified by grep across every committed `.kicad_dru`) -- this is
    therefore a currently-inert, forward-compatible pass: any quoted
    occurrence of an old net name inside the file is replaced with the new
    name, and the count is reported. Exercised directly by a synthetic test
    with a fabricated condition string.
    """
    with open(pro_path, encoding="utf-8") as f:
        data = json.load(f)
    ns = data.setdefault("net_settings", {})
    patterns = ns.setdefault("netclass_patterns", [])

    by_class = {}
    for p in patterns:
        by_class.setdefault(p["netclass"], []).append(p["pattern"])

    changes = []
    unresolvable = []
    additions = []
    for cls, pats in by_class.items():
        for old, new in rename_map.items():
            was = _fnmatch_any(old, pats)
            now = _fnmatch_any(new, pats)
            if was == now:
                continue
            if was and not now:
                additions.append({"netclass": cls, "pattern": new})
                changes.append({"netclass": cls, "old": old, "new": new,
                                 "action": "added_explicit_pattern"})
            else:
                unresolvable.append({
                    "netclass": cls, "old": old, "new": new,
                    "reason": "rename causes an unintended NEW match against "
                              "an existing pattern in this netclass -- no "
                              "safe additive fix"})

    if unresolvable:
        raise ValueError(
            f"netclass membership equality impossible for {pro_path}: {unresolvable}")

    if additions:
        patterns.extend(additions)
        # re-verify: every affected (class, new-name) pair must now match
        # under the UPDATED pattern set, restoring exact prior membership.
        by_class2 = {}
        for p in patterns:
            by_class2.setdefault(p["netclass"], []).append(p["pattern"])
        for c in changes:
            if not _fnmatch_any(c["new"], by_class2[c["netclass"]]):
                raise ValueError(
                    f"post-fix membership re-check failed for netclass "
                    f"{c['netclass']!r}, net {c['new']!r}")

    report = {"netclass_changes": changes, "unresolvable": unresolvable}

    if additions and not dry_run:
        with open(pro_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, sort_keys=True))

    dru_report = {"changed": 0, "occurrences": []}
    if dru_path and os.path.exists(dru_path):
        with open(dru_path, encoding="utf-8") as f:
            dru_text = f.read()
        new_dru = dru_text
        for old, new in rename_map.items():
            for quote in ("'", '"'):
                token = f"{quote}{old}{quote}"
                if token in new_dru:
                    n = new_dru.count(token)
                    new_dru = new_dru.replace(token, f"{quote}{new}{quote}")
                    dru_report["changed"] += n
                    dru_report["occurrences"].append(old)
        if new_dru != dru_text and not dry_run:
            with open(dru_path, "w", encoding="utf-8") as f:
                f.write(new_dru)
    report["dru"] = dru_report
    return report


# --------------------------------------------------------------- DRC parity
_SCHEMATIC_PARITY_FLAG = None


def schematic_parity_supported():
    """Whether this kicad-cli build understands `pcb drc --schematic-parity`
    (present in 10.0.4, per `kicad-cli pcb drc --help`; probed rather than
    assumed so an older/newer kicad-cli degrades gracefully instead of
    erroring)."""
    global _SCHEMATIC_PARITY_FLAG
    if _SCHEMATIC_PARITY_FLAG is None:
        cli = TC.require_kicad_cli("PCB DRC flag probe")
        r = subprocess.run([cli, "pcb", "drc", "--help"], capture_output=True, text=True)
        _SCHEMATIC_PARITY_FLAG = "--schematic-parity" in (r.stdout + r.stderr)
    return _SCHEMATIC_PARITY_FLAG


def run_drc(pcb_path, schematic_parity=True):
    """`kicad-cli pcb drc --format json` (+ `--schematic-parity` when
    supported), parsed. No `--exit-code-violations`, so a clean return only
    signals the command itself ran; the caller inspects violation content."""
    cli = TC.require_kicad_cli("PCB DRC")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    try:
        cmd = [cli, "pcb", "drc", "--format", "json", "-o", out]
        if schematic_parity and schematic_parity_supported():
            cmd.append("--schematic-parity")
        cmd.append(pcb_path)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not os.path.exists(out) or not os.path.getsize(out):
            raise RuntimeError(
                f"kicad-cli pcb drc failed for {pcb_path} (rc={r.returncode}): "
                f"{r.stderr.strip()}")
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)
    finally:
        if os.path.exists(out):
            os.unlink(out)


def _violation_multiset(drc_json):
    from collections import Counter
    c = Counter()
    for v in drc_json.get("violations", None) or []:
        c[("violation", v["type"])] += 1
    for v in drc_json.get("schematic_parity", None) or []:
        c[("schematic_parity", v["type"])] += 1
    for v in drc_json.get("unconnected_items", None) or []:
        c[("unconnected", v["type"])] += 1
    return c


def drc_parity(pcb_path, baseline_json, schematic_parity=True):
    """Compare pcb_path's CURRENT DRC/schematic-parity/unconnected-item TYPE
    multiset against a baseline (a dict already loaded, or a path to a
    previously-saved `kicad-cli pcb drc --format json` report). Equal
    multisets == the reconciliation changed nothing DRC/parity-visible -- the
    gate `reconcile_pcb`'s caller must hold for the routed, CI-gated
    12vhpwr-standard board (0 unconnected / 0 schematic-parity / cosmetic-
    silk-only, per CLAUDE.md's action item 4)."""
    if isinstance(baseline_json, str):
        with open(baseline_json, encoding="utf-8") as f:
            baseline = json.load(f)
    else:
        baseline = baseline_json

    after = run_drc(pcb_path, schematic_parity=schematic_parity)
    before_ms = _violation_multiset(baseline)
    after_ms = _violation_multiset(after)

    return {
        "equal": before_ms == after_ms,
        "before_total": sum(before_ms.values()),
        "after_total": sum(after_ms.values()),
        "only_before": {f"{k[0]}:{k[1]}": v for k, v in (before_ms - after_ms).items()},
        "only_after": {f"{k[0]}:{k[1]}": v for k, v in (after_ms - before_ms).items()},
    }


# ---------------------------------------------------------------- git + CLI
def repo_root(start=None):
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                        text=True, cwd=start or HERE)
    if r.returncode != 0:
        raise RuntimeError(f"not inside a git repo: {r.stderr.strip()}")
    return r.stdout.strip()


def git_show_tree(rev, rel_path, dest_dir):
    """Extract the git tree at rev:rel_path (a directory, relative to the
    repo root) into dest_dir, reproducing the full file layout via
    `git archive | tar -x`. A FLAT baseline schematic is self-contained (its
    embedded lib_symbols carry everything kicad-cli needs) so a single file
    would suffice for that case per se, but extracting the whole board
    directory is the general form that also covers a hierarchical baseline
    (root + leaf .kicad_sch files, fp-lib-table, the .kicad_pro) -- and costs
    nothing extra for the flat case. Returns dest_dir/rel_path."""
    os.makedirs(dest_dir, exist_ok=True)
    root = repo_root()
    archive = subprocess.Popen(["git", "archive", rev, "--", rel_path],
                                stdout=subprocess.PIPE, cwd=root)
    extract = subprocess.run(["tar", "-x", "-C", dest_dir], stdin=archive.stdout,
                              capture_output=True, text=True)
    archive.stdout.close()
    archive.wait()
    if archive.returncode != 0 or extract.returncode != 0:
        raise RuntimeError(
            f"git archive {rev} -- {rel_path} failed "
            f"(archive rc={archive.returncode}, tar rc={extract.returncode}): "
            f"{extract.stderr.strip()}")
    out = os.path.join(dest_dir, rel_path)
    if not os.path.isdir(out):
        raise RuntimeError(f"git archive produced no {out} -- bad rev or path?")
    return out


def _find_one(board_dir, ext):
    matches = sorted(
        p for p in os.listdir(board_dir)
        if p.endswith(ext) and os.path.isfile(os.path.join(board_dir, p)))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one *{ext} file in {board_dir}, found {matches}")
    return os.path.join(board_dir, matches[0])


def reconcile_board(board_dir, baseline_rev, dry_run=False, workdir=None):
    """End-to-end driver: locate the board's live files, extract the
    baseline flat schematic at baseline_rev via git, build the rename map,
    reconcile the PCB + project/DRU, and check DRC parity. Returns a single
    combined report dict. This is what the CLI wires up; factored out so it
    is directly callable/testable without going through argv."""
    board_dir = os.path.abspath(board_dir)
    root = repo_root(board_dir)
    rel_board = os.path.relpath(board_dir, root)

    new_sch = _find_one(board_dir, ".kicad_sch")
    pcb_path = _find_one(board_dir, ".kicad_pcb")
    pro_path = _find_one(board_dir, ".kicad_pro")
    dru_candidates = [p for p in os.listdir(board_dir) if p.endswith(".kicad_dru")]
    dru_path = os.path.join(board_dir, dru_candidates[0]) if dru_candidates else None

    own_tmp = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix="cec_pcb_reconcile_")
    try:
        baseline_root = git_show_tree(baseline_rev, rel_board, workdir)
        baseline_sch = _find_one(baseline_root, ".kicad_sch")

        old_groups = netlist_groups(baseline_sch)
        new_groups = netlist_groups(new_sch)
        rename_map = build_rename_map(old_groups, new_groups)
        path_map = symbol_paths(new_sch)

        before_drc = run_drc(pcb_path) if TC.have_kicad_cli() else None

        pcb_report = reconcile_pcb(pcb_path, rename_map, path_map, dry_run=dry_run)
        proj_report = reconcile_project(pro_path, dru_path, rename_map, dry_run=dry_run)

        parity_report = None
        if before_drc is not None and not dry_run:
            parity_report = drc_parity(pcb_path, before_drc)

        return {
            "board": rel_board,
            "baseline_rev": baseline_rev,
            "rename_map": rename_map,
            "pcb": pcb_report,
            "project": proj_report,
            "drc_parity": parity_report,
        }
    finally:
        if own_tmp:
            import shutil
            shutil.rmtree(workdir, ignore_errors=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Reconcile a module .kicad_pcb (+ .kicad_pro/.kicad_dru) "
                    "after its schematic converts from flat to hierarchical.")
    ap.add_argument("--board", required=True,
                     help="module directory, e.g. modules/eps-8pin")
    ap.add_argument("--baseline-rev", required=True,
                     help="git rev holding the pre-conversion FLAT schematic")
    ap.add_argument("--dry-run", action="store_true",
                     help="compute and print the report; write nothing")
    args = ap.parse_args(argv)

    report = reconcile_board(args.board, args.baseline_rev, dry_run=args.dry_run)

    print(f"[cec_pcb_reconcile] board={report['board']} "
          f"baseline={report['baseline_rev']} dry_run={args.dry_run}")
    print(f"[cec_pcb_reconcile] {len(report['rename_map'])} renamed nets:")
    for old, new in sorted(report["rename_map"].items()):
        print(f"    {old} -> {new}")
    print("[cec_pcb_reconcile] PCB report:")
    print(json.dumps(report["pcb"], indent=2))
    print("[cec_pcb_reconcile] project/DRU report:")
    print(json.dumps(report["project"], indent=2))

    rc = 0
    if report["pcb"].get("path_missing_ref"):
        print(f"[cec_pcb_reconcile] WARNING: footprints with a path but no "
              f"matching ref in the new schematic: {report['pcb']['path_missing_ref']}",
              file=sys.stderr)

    if report["drc_parity"] is not None:
        print("[cec_pcb_reconcile] DRC parity report:")
        print(json.dumps(report["drc_parity"], indent=2))
        if not report["drc_parity"]["equal"]:
            print("[cec_pcb_reconcile] DRC PARITY MISMATCH", file=sys.stderr)
            rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
