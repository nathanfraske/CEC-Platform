import copy

import pytest

from cec_blueprint_ownership import partition_supply


def fixture():
    tpl = {"anchor": "sensor", "parts": {r: {"offset_mm": [i, i]} for i, r in enumerate(("sensor", "bypass", "filter"))},
           "net_roles": {"rail": "VCC", "return": "GND", "signal": "SENSE"},
           "ports": {"rail": {"pads": [{"ref": "sensor", "pad": "p"}, {"ref": "bypass", "pad": "a"}]},
                     "return": {"pads": [{"ref": "sensor", "pad": "g"}, {"ref": "bypass", "pad": "b"}]}},
           "internal_pads": {"signal": {"pads": [{"ref": "sensor", "pad": "s"}, {"ref": "filter", "pad": "x"}]}},
           "internal_tracks": [{"net_role": r, "layer": "F.Cu", "width_mm": .3, "start_rel_mm": [0, 0], "end_rel_mm": [1, 1]} for r in ("rail", "return", "signal")],
           "vias": [{"net_role": "return"}, {"net_role": "signal"}], "gnd_vias": [{"at_rel_mm": [5, 5]}]}
    kwargs = {"ref_map": {"sensor": "AMP_A", "bypass": "CAP_B", "filter": "FILTER_C"},
              "net_map": {}, "requirements": {"CAP_B": {"owner": "AMP_A", "pin": "p", "rail": "VCC", "return_rail": "GND"}},
              "pin_nets": {("AMP_A", "p"): "VCC", ("AMP_A", "g"): "GND", ("CAP_B", "a"): "VCC", ("CAP_B", "b"): "GND"}}
    return tpl, kwargs


def test_partition_preserves_precision_and_source():
    tpl, kw = fixture()
    original = copy.deepcopy(tpl)
    out, report = partition_supply(tpl, **kw)
    assert tpl == original
    assert set(out["parts"]) == {"sensor", "filter"}
    assert out["internal_tracks"] == [original["internal_tracks"][2]]
    assert out["vias"] == [{"net_role": "signal"}]
    assert out["ports"]["rail"]["pads"] == [{"ref": "sensor", "pad": "p"}]
    assert report["released_refs"] == ["CAP_B"]
    assert report["removed_copper"] == {"internal_tracks": 2, "port_tracks": 0, "vias": 1, "gnd_vias": 1}
    twice, again = partition_supply(out, **kw)
    assert twice == out and not again["released_refs"]


@pytest.mark.parametrize("defect", ["unknown_owner", "third_pin", "wrong_rail", "missing_land", "force_user", "unverified_pad", "anchor_cap", "signal_cap"])
def test_ambiguous_ownership_retains_complete_template(defect):
    tpl, kw = fixture()
    if defect == "unknown_owner": kw["requirements"]["CAP_B"]["owner"] = "ELSEWHERE"
    if defect == "third_pin": kw["pin_nets"][("CAP_B", "c")] = "GND"
    if defect == "wrong_rail": kw["pin_nets"][("CAP_B", "a")] = "OTHER"
    if defect == "missing_land": tpl["ports"]["return"]["pads"].pop()
    if defect == "force_user": tpl["ports"]["rail"]["pads"].append({"ref": "filter", "pad": "x"})
    if defect == "unverified_pad": kw["pin_nets"].pop(("AMP_A", "g"))
    if defect == "anchor_cap": tpl["anchor"] = "bypass"
    if defect == "signal_cap": tpl["internal_pads"]["signal"]["pads"].append({"ref": "bypass", "pad": "b"})
    out, report = partition_supply(tpl, **kw)
    assert out == tpl and not report["released_refs"]


def test_renamed_refs_pins_nets_and_rotated_geometry_do_not_change_partition():
    tpl, kw = fixture()
    kw["ref_map"] = {k: v + "_RENAMED" for k, v in kw["ref_map"].items()}
    kw["requirements"] = {k + "_RENAMED": {**q, "owner": q["owner"] + "_RENAMED", "rail": "POWER_BUS", "return_rail": "RETURN_BUS"} for k, q in kw["requirements"].items()}
    rename = {"VCC": "POWER_BUS", "GND": "RETURN_BUS"}
    kw["pin_nets"] = {(r + "_RENAMED", p): rename[n] for (r, p), n in kw["pin_nets"].items()}
    kw["net_map"] = {"rail": "POWER_BUS", "return": "RETURN_BUS"}
    for part in tpl["parts"].values(): part.update(rot_delta=270, offset_mm=[28.7, -4.2])
    out, report = partition_supply(tpl, **kw)
    assert report["released_refs"] == ["CAP_B_RENAMED"]
    assert out["internal_tracks"] == [tpl["internal_tracks"][2]]


def test_duplicate_destinations_fail_closed():
    tpl, kw = fixture()
    kw["ref_map"]["filter"] = "AMP_A"
    with pytest.raises(ValueError, match="one-to-one"):
        partition_supply(tpl, **kw)


def test_delegated_internal_role_becomes_external_port_not_resynthesized():
    tpl, kw = fixture()
    tpl["internal_pads"]["rail"] = tpl["ports"].pop("rail")
    out, report = partition_supply(tpl, **kw)
    assert "rail" not in out["internal_pads"]
    assert out["ports"]["rail"]["pads"] == [{"ref": "sensor", "pad": "p"}]
    assert report["released_refs"]


def test_compiler_fresh_stamp_and_resume_locks_use_same_partition(monkeypatch):
    from types import SimpleNamespace
    import cec_synth_pipeline as synth
    import cec_cell_extract
    tpl, kw = fixture()
    for part in tpl["parts"].values(): part.update(rot_delta=0, flipped=False)
    nl = SimpleNamespace(comps={ref: None for ref in kw["ref_map"].values()}, nets={})
    for (ref, pin), net in kw["pin_nets"].items():
        nl.nets.setdefault(net, []).append((ref, pin))
    cell = {"template": tpl, "ref_map": kw["ref_map"], "net_map": {},
            "anchor_ref": "AMP_A", "ideal_internal": False}
    cfg = SimpleNamespace(sch="source-owned.sch", params={"blueprint_cells": [cell]})
    monkeypatch.setattr(synth, "View", lambda _: SimpleNamespace(nl=nl))
    monkeypatch.setattr(synth, "_device_bypass_specs", lambda *a, **k: kw["requirements"])
    compiled = synth._compiled_blueprint_template(cfg, cell, nl=nl)
    stamp = synth._declared_blueprint_stamps(cfg, {"AMP_A": (30, 20, 90)})[0]
    assert compiled == stamp["template"]
    assert synth._declared_blueprint_refs(cfg) == {"AMP_A", "FILTER_C"}
    assert synth._stamped_blueprint_refs([stamp]) == {"AMP_A", "FILTER_C"}
    # Native stamp requires via geometry, which is not needed for this lock
    # partition fixture. Its unchanged precision-track data is tested above.
    stamp["template"]["vias"] = []
    placed, copper = cec_cell_extract.stamp(stamp["template"], at_mm=(30, 20),
        rot=90, ref_map=kw["ref_map"], lay_tracks=True)
    assert set(placed) == {"AMP_A", "FILTER_C"}
    assert {t["net"] for t in copper["tracks"]} == {"SENSE"}


def test_shared_role_with_unassigned_part_is_not_silently_deleted():
    tpl, kw = fixture()
    tpl["parts"]["other"] = {"offset_mm": [9, 9]}
    tpl["ports"]["return"]["pads"].append({"ref": "other", "pad": "b"})
    kw["pin_nets"][("other", "b")] = "GND"
    out, report = partition_supply(tpl, **kw)
    assert not report["released_refs"] and out == tpl
