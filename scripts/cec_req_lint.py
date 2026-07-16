#!/usr/bin/env python3
"""Lint the enterprise requirements registers (docs/enterprise-requirements/*.md).

Checks (REQUIREMENTS-FORMAT.md contract):
  - REQ ID format + global uniqueness across all registers
  - UNIT matches the file it lives in (HUB in hub-*, MOD in module-*-common, etc.)
  - every requirement statement contains SHALL (drafting discipline)
  - Verify vocabulary: combinations of I/A/T/D joined by '+'
  - Gate references a known form: '—', D-ENT-#, OQ-# (ranges ok), or a Phase-N owner act
  - spec section references resolve: ONLY segments marked 'spec §x.y' or '[LOCKED §x.y]'
    are resolved against CEC-Platform-Ground-Truth-Spec.md (audit/tamper/plan § refs are
    report-internal and deliberately not resolved here)

Exit 0 clean, 1 on any error. Run from repo root: python3 scripts/cec_req_lint.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQ_DIR = os.path.join(ROOT, "docs", "enterprise-requirements")
SPEC = os.path.join(ROOT, "CEC-Platform-Ground-Truth-Spec.md")

ID_RE = re.compile(r"REQ-(HUB|MOD|24PIN|EPS|PCIE|HPWR)-(COMMON|AIR|NET)-(\d{3})")
VERIFY_RE = re.compile(r"^[IATD](\+[IATD])*$")
GATE_OK_RE = re.compile(
    r"(^—$|D-ENT-\d|OQ-\d+(\.\.\d+)?(/\d+)*|Phase-\d|Phase 2|EU-entry)"
)
UNIT_BY_FILE = {
    "hub-enterprise-requirements.md": {"HUB"},
    "module-requirements-common.md": {"MOD"},
    "module-requirements-24pin.md": {"24PIN"},
    "module-requirements-eps.md": {"EPS"},
    "module-requirements-pcie.md": {"PCIE"},
    "module-requirements-12vhpwr.md": {"HPWR"},
}

errors = []


def err(msg):
    errors.append(msg)


def spec_secs_resolve(trace, spec_text, where):
    """Resolve § refs only inside 'spec ...' / '[LOCKED ...' trace segments."""
    if not spec_text:
        return
    for seg in re.split(r"[;]", trace):
        if not re.search(r"\bspec\b|\[LOCKED", seg):
            continue
        for sec in re.findall(r"§\s*([0-9]+(?:\.[0-9]+)*)", seg):
            if not re.search(
                rf"(^#+ .*\b{re.escape(sec)}\b|§{re.escape(sec)}\b|"
                rf"\b[Ss]ection {re.escape(sec)}\b)",
                spec_text,
                re.M,
            ):
                err(f"{where}: spec section §{sec} does not resolve in "
                    f"{os.path.basename(SPEC)} -- stale after a spec rev?")


def lint_file(path, spec_text, seen_ids):
    name = os.path.basename(path)
    allowed_units = UNIT_BY_FILE.get(name)
    text = open(path).read()
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = ID_RE.search(cells[0]) if cells else None
        if not m:
            # non-requirement table row (header, matrix row, etc.)
            if cells and cells[0].startswith("REQ-"):
                err(f"{name}:{lineno}: malformed requirement ID '{cells[0]}'")
            continue
        rid, unit = m.group(0), m.group(1)
        where = f"{name}:{lineno}:{rid}"
        if rid in seen_ids:
            err(f"{where}: duplicate ID (also in {seen_ids[rid]})")
        seen_ids[rid] = name
        if allowed_units and unit not in allowed_units:
            err(f"{where}: unit {unit} does not belong in {name}")
        if len(cells) != 5:
            err(f"{where}: expected 5 columns (ID|Requirement|Trace|Verify|Gate), "
                f"got {len(cells)}")
            continue
        _, stmt, trace, verify, gate = cells
        if "SHALL" not in stmt:
            err(f"{where}: requirement statement lacks SHALL")
        if not VERIFY_RE.match(verify):
            err(f"{where}: bad Verify '{verify}' (expect I/A/T/D combos like A+T)")
        if not GATE_OK_RE.search(gate):
            err(f"{where}: bad Gate '{gate}' (expect —, D-ENT-#, OQ-#, or Phase-N act)")
        spec_secs_resolve(trace, spec_text, where)


def main():
    if not os.path.isdir(REQ_DIR):
        print("cec_req_lint: no docs/enterprise-requirements/ -- nothing to lint")
        return 0
    spec_text = open(SPEC).read() if os.path.isfile(SPEC) else ""
    if not spec_text:
        print("cec_req_lint: WARNING spec file missing; § resolution skipped")
    seen_ids = {}
    files = sorted(
        f for f in os.listdir(REQ_DIR)
        if f.endswith(".md") and f in UNIT_BY_FILE
    )
    for f in files:
        lint_file(os.path.join(REQ_DIR, f), spec_text, seen_ids)
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"cec_req_lint: {len(errors)} error(s) across {len(files)} register(s)")
        return 1
    print(f"cec_req_lint: OK -- {len(seen_ids)} requirements across "
          f"{len(files)} register(s), all IDs unique, spec refs resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
