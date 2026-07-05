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
        fail(f"{fam}: no exported netlist ({netf}) -- run the generator first")
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
# 3. Joint counts match the spec §2.8 v1.4.0 ratified table, and the keying
#    pattern (pitch/gap/count) differs across every family pair.
# ---------------------------------------------------------------------------
EXPECTED_JOINTS = {"atx24-out-db": 9, "eps-out-db": 6, "pcie-out-db": 4}
for fam, n in EXPECTED_JOINTS.items():
    got = len(godb.FAMILIES[fam]["tabs"])
    check(got == n, f"{fam}: {n} ratified blade-tab joints (found {got})")

sigs = {fam: (n, *godb.TAB_PITCH_GAP[fam]) for fam, n in EXPECTED_JOINTS.items()}
fams = list(sigs)
for i, a in enumerate(fams):
    for b in fams[i + 1:]:
        check(sigs[a] != sigs[b],
              f"keying signature (count, pitch, gap) differs: {a}={sigs[a]} vs {b}={sigs[b]}")

if FAILURES:
    print(f"\n{len(FAILURES)} FAILURE(S):", file=sys.stderr)
    for f in FAILURES:
        print(f"  FAIL {f}", file=sys.stderr)
    sys.exit(1)
print("\nAll output-daughterboard checks passed.")
