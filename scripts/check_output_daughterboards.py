#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Verification harness for modules/output-daughterboards/{atx24,eps,pcie}-out-db
# (spec Sec.2.8 v1.4.0 output-connector daughterboards). Checks, per family:
#   - ERC clean (error severity)
#   - DRC clean (error severity)
#   - static connectivity audit (audit-sch.py) clean
#   - every TE 63849-1 blade tab lands on its spec-mapped output-field net
#     (via the exported netlist -- ground truth, not a hand assertion)
#   - the field connector's own pin map matches the family's real-world
#     standard (ATX-24 / EPS8 / PCIe8 CEM), pin-by-pin
#   - the keying pattern (tab pitch/gap/count) differs across all three
#     families, per CLAUDE.md's asymmetric-keying convention
#
#   python3 scripts/check_output_daughterboards.py
# Exits 0 on pass, non-zero on any failed assertion (printed to stderr).
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "godb", os.path.join(ROOT, "scripts", "gen-output-daughterboard.py"))
godb = importlib.util.module_from_spec(_spec)
sys.argv = ["check_output_daughterboards.py"]   # keep godb's __main__ inert
_spec.loader.exec_module(godb)

FAILURES = []


def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
    else:
        print(f"  OK   {msg}")


def board_dir(fam):
    return os.path.join(ROOT, "modules", "output-daughterboards", fam)


def carve(t, i):
    d = 0; ins = esc = False; j = i
    while j < len(t):
        c = t[j]
        if ins:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': ins = False
        else:
            if c == '"': ins = True
            elif c == "(": d += 1
            elif c == ")":
                d -= 1
                if d == 0: return t[i:j + 1]
        j += 1


def netlist_membership(net_path):
    """{net_name: {(ref, pin), ...}} from a kicad-cli-exported .net file."""
    t = open(net_path).read()
    out = {}
    for m in re.finditer(r"\(net\b", t):
        b = carve(t, m.start())
        nm = re.search(r'\(name "([^"]*)"\)', b)
        if not nm:
            continue
        nodes = set()
        for mm in re.finditer(r"\(node\b", b):
            nb = carve(b, mm.start())
            rr = re.search(r'\(ref "([^"]+)"\)', nb)
            pp = re.search(r'\(pin "([^"]+)"\)', nb)
            if rr and pp:
                nodes.add((rr.group(1), pp.group(1)))
        out[nm.group(1)] = nodes
    return out


def net_of(membership, ref, pin):
    for name, nodes in membership.items():
        if (ref, pin) in nodes:
            return name
    return None


# ---------------------------------------------------------------------------
# 1. ERC / DRC / audit-sch, per family
# ---------------------------------------------------------------------------
for fam, cfg in godb.FAMILIES.items():
    bdir = board_dir(fam)
    base = cfg["base"]
    sch = os.path.join(bdir, f"{base}.kicad_sch")
    pcb = os.path.join(bdir, f"{base}.kicad_pcb")
    check(os.path.exists(sch), f"{fam}: schematic exists ({sch})")
    check(os.path.exists(pcb), f"{fam}: PCB exists ({pcb})")
    if not (os.path.exists(sch) and os.path.exists(pcb)):
        continue

    with tempfile.TemporaryDirectory() as td:
        erc_json = os.path.join(td, "erc.json")
        subprocess.run(["kicad-cli", "sch", "erc", "--severity-error",
                       "--format", "json", "-o", erc_json, sch],
                      capture_output=True)
        erc = json.load(open(erc_json))
        erc_errs = erc["sheets"][0]["violations"] if erc.get("sheets") else []
        check(len(erc_errs) == 0, f"{fam}: ERC 0 errors (found {len(erc_errs)})")

        drc_json = os.path.join(td, "drc.json")
        subprocess.run(["kicad-cli", "pcb", "drc", "--severity-error",
                       "--format", "json", "-o", drc_json, pcb],
                      capture_output=True)
        drc = json.load(open(drc_json))
        drc_errs = drc.get("violations", [])
        unconn = drc.get("unconnected_items", [])
        check(len(drc_errs) == 0, f"{fam}: DRC 0 errors (found {len(drc_errs)})")
        check(len(unconn) == 0, f"{fam}: DRC 0 unconnected (found {len(unconn)})")

r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "audit-sch.py"),
                   *[os.path.join(board_dir(f), f"{godb.FAMILIES[f]['base']}.kicad_sch")
                     for f in godb.FAMILIES]],
                  capture_output=True, text=True)
check(r.returncode == 0, "audit-sch.py: all three daughterboard sheets clean")


# ---------------------------------------------------------------------------
# 2. Every blade tab lands on its spec-mapped net (ground truth: the
#    exported netlist, not the generator's own config -- a real regression
#    guard, not a tautology).
# ---------------------------------------------------------------------------
for fam, cfg in godb.FAMILIES.items():
    bdir = board_dir(fam)
    netf = os.path.join(bdir, f"{cfg['base']}.net")
    if not os.path.exists(netf):
        check(False, f"{fam}: no exported netlist ({netf}) -- run the generator first")
        continue
    membership = netlist_membership(netf)
    for ref, expected_net in cfg["tabs"]:
        actual = net_of(membership, ref, "1")
        pcb_net = godb._PCB_NET.get(expected_net, expected_net) \
            if fam == "atx24-out-db" else expected_net
        check(actual == pcb_net,
              f"{fam}: tab {ref} on net {expected_net!r} (netlist: {actual!r})")

    # field connector's own pin map, pin-by-pin
    field_ref = cfg["field_ref"]
    for pin, expected_net in cfg["field_net"].items():
        actual = net_of(membership, field_ref, str(pin))
        if expected_net is None:
            check(actual is None or actual.startswith("unconnected-"),
                  f"{fam}: field pin {pin} is NC (netlist: {actual!r})")
        else:
            pcb_net = godb._PCB_NET.get(expected_net, expected_net) \
                if fam == "atx24-out-db" else expected_net
            check(actual == pcb_net,
                  f"{fam}: field pin {pin} on net {expected_net!r} (netlist: {actual!r})")

    # 24-pin's signal header, same treatment
    if cfg["header"]:
        h = cfg["header"]
        for pin, expected_net in h["net"].items():
            actual = net_of(membership, h["ref"], str(pin))
            if expected_net is None:
                check(actual is None or actual.startswith("unconnected-"),
                      f"{fam}: header pin {pin} is reserved/NC (netlist: {actual!r})")
            else:
                pcb_net = godb._PCB_NET.get(expected_net, expected_net)
                check(actual == pcb_net,
                      f"{fam}: header pin {pin} on net {expected_net!r} (netlist: {actual!r})")


# ---------------------------------------------------------------------------
# 3. Joint counts match the spec §2.8 v1.4.0 ratified table, and -- the real
#    keying safety property -- NO family's tab grid can seat, as a rigid
#    subset, onto any OTHER family's grid under any translation combined
#    with a 0/90/180/270 rotation. This replaces the old (count, pitch, gap)
#    1-D signature comparison, which could not express a 2-D grid at all (a
#    3x3 and a 2x2 grid can share a "pitch" while still being mechanically
#    incompatible, or share nothing and still nest as corner subsets -- pitch
#    alone proves nothing). The daughterboard's own tab-centre positions
#    (from pcb_placement(), the exact coordinates written to the committed
#    .kicad_pcb) ARE the authoritative main-board mating drawing per family
#    -- see each README's "Keying" section for the rendered grid.
# ---------------------------------------------------------------------------
EXPECTED_JOINTS = {"atx24-out-db": 9, "eps-out-db": 6, "pcie-out-db": 4}
for fam, n in EXPECTED_JOINTS.items():
    got = len(godb.FAMILIES[fam]["tabs"])
    check(got == n, f"{fam}: {n} ratified blade-tab joints (found {got})")


def tab_centres(fam):
    _w, _h, P = godb.pcb_placement(fam)
    return [(P[ref][0], P[ref][1]) for ref, _net in godb.FAMILIES[fam]["tabs"]]


def _rot90(pts, k):
    """Rotate every point by k*90 degrees about the origin (k=0..3)."""
    out = []
    for (x, y) in pts:
        for _ in range(k):
            x, y = -y, x
        out.append((x, y))
    return out


def _bipartite_full_match(edges, n_left, n_right):
    """Kuhn/Hopcroft-style augmenting-path matching: True iff every LEFT
    node (0..n_left-1) can be matched to a DISTINCT right node along the
    given adjacency lists (`edges[i]` = right-node indices reachable from
    left node i)."""
    match_right = [-1] * n_right

    def try_left(u, seen):
        for v in edges[u]:
            if seen[v]:
                continue
            seen[v] = True
            if match_right[v] == -1 or try_left(match_right[v], seen):
                match_right[v] = u
                return True
        return False

    return all(try_left(u, [False] * n_right) for u in range(n_left))


def subset_seats(sup, sub, tol=0.5):
    """True if EVERY point of `sub` maps -- under SOME translation combined
    with a 0/90/180/270 rotation -- onto a DISTINCT point of `sup`, each
    within `tol` mm. Tries every (sup-point, rotated-sub-point) pair as the
    anchor that fixes the translation (a valid whole-set mapping, if one
    exists, must be attainable this way for at least one such pair), then
    verifies the FULL point set with a real bipartite match -- not just
    that counts/pitches happen to coincide."""
    for k in range(4):
        rk = _rot90(sub, k)
        for (ax, ay) in sup:
            for (bx, by) in rk:
                tx, ty = ax - bx, ay - by
                moved = [(x + tx, y + ty) for (x, y) in rk]
                edges = [[j for j, (sx, sy) in enumerate(sup)
                          if (sx - mx) ** 2 + (sy - my) ** 2 <= tol ** 2]
                         for (mx, my) in moved]
                if _bipartite_full_match(edges, len(moved), len(sup)):
                    return True
    return False


CENTRES = {fam: tab_centres(fam) for fam in EXPECTED_JOINTS}
fams = list(CENTRES)
for a in fams:
    for b in fams:
        if a == b:
            continue
        check(not subset_seats(CENTRES[a], CENTRES[b]),
              f"no-subset-seating: {b}'s {len(CENTRES[b])} tabs cannot seat "
              f"as a subset of {a}'s {len(CENTRES[a])} clip positions under "
              f"any translation + 90-deg rotation (checked within 0.5mm)")

if FAILURES:
    print(f"\n{len(FAILURES)} FAILURE(S):", file=sys.stderr)
    for f in FAILURES:
        print(f"  FAIL {f}", file=sys.stderr)
    sys.exit(1)
print("\nAll output-daughterboard checks passed.")
