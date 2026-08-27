import os
import sys
from dataclasses import dataclass, field

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_constraint_ir as ir  # noqa: E402


@dataclass
class Source:
    id: str
    title: str = "title"
    category: str = "routing"
    severity: str = "hard"
    checkable: str = "yes"
    directive: str = "none"
    rule: str = "rule text"
    source: str = "datasheet section 1"
    status: str = "ratified"
    params: dict = field(default_factory=dict)
    checker: str = ""
    corpus_id: str = ""
    superseded_by: str = ""


def test_registry_compiles_to_order_independent_typed_fingerprint():
    first = ir.compile_registry([
        Source("b", severity="soft", params={"limit": 2}),
        Source("a", params={"layers": ["F.Cu", "B.Cu"]}),
    ])
    second = ir.compile_registry(list(reversed([
        Source("b", severity="soft", params={"limit": 2}),
        Source("a", params={"layers": ["F.Cu", "B.Cu"]}),
    ])))
    assert first.fingerprint == second.fingerprint
    assert [row.id for row in first.records] == ["a", "b"]
    assert first.records[0].release_blocking
    assert not first.records[1].release_blocking
    assert first.records[0].provenance.source == "datasheet section 1"


def test_registry_refuses_duplicate_or_untyped_authority():
    with pytest.raises(ValueError, match="duplicate"):
        ir.compile_registry([Source("a"), Source("a")])
    with pytest.raises(ValueError, match="severity"):
        ir.compile_registry([Source("a", severity="important")])
    with pytest.raises(ValueError, match="source"):
        ir.compile_registry([Source("a", source="")])


def test_net_selector_resolution_is_exact_unique_or_fail_closed():
    result = ir.resolve_net_selectors(
        ("/EXACT", "COMP_THRESH", "SENSE", "MISSING"),
        ("/EXACT", "/POWER/COMP_THRESH", "/A/SENSE", "/B/SENSE"))
    assert result["resolved"] == ["/EXACT", "/POWER/COMP_THRESH"]
    assert result["ambiguous"]["SENSE"] == ["/A/SENSE", "/B/SENSE"]
    assert result["unresolved"] == ["MISSING"]
    assert not result["ok"]
    assert {row["resolution"] for row in result["provenance"]} == {
        "exact", "unique_leaf"}
    assert len(result["fingerprint"]) == 64


def test_live_design_registry_compiles_and_matches_release_blocking_policy():
    import cec_constraints

    bundle = cec_constraints.compiled_constraint_ir()
    assert len(bundle.records) == len(cec_constraints.REGISTRY)
    expected = sum(
        row.status == "ratified" and not row.superseded_by
        and row.checkable == "yes" and row.severity in ("hard", "strong")
        for row in cec_constraints.REGISTRY)
    assert bundle.as_dict(include_records=False)[
        "release_blocking_count"] == expected
    assert len(bundle.fingerprint) == 64
