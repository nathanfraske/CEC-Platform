#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Tests for scripts/cec_thermal_sources.py (Tier-0 heat-source inventory +
#  material-limit gate + emissivity extraction). AM-04 discipline: external
#  anchors (a hand-computed LDO case, the platform's own documented LED
#  figure, real vendored-datasheet numbers) + teeth (a sabotaged input must
#  visibly fail) + additive-only (no mutation of any board/schematic file).
#  Own-module isolation: imports ONLY cec_thermal_sources, never
#  cec_synth_pipeline / cec_thermal2d.
# ============================================================================
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_thermal_sources as TS                              # noqa: E402

HUB_DIR = os.path.join(ROOT, "beta", "hub-standard-rev2")
HUB_SCH = os.path.join(HUB_DIR, "hub-standard-rev2.kicad_sch")
HUB_PCB = os.path.join(HUB_DIR, "candidate", "hub-standard-rev2-candidate.kicad_pcb")
HPWR_DIR = os.path.join(ROOT, "beta", "12vhpwr-standard")

try:
    import pcbnew                                             # noqa: F401
    _HAVE_PCBNEW = True
except Exception:
    _HAVE_PCBNEW = False

import shutil
_HAVE_KICAD_CLI = shutil.which("kicad-cli") is not None


class T1LdoHandAnchor(unittest.TestCase):
    """The task's required hand-computed LDO case: LP5907 5V->3.3V at a chosen
    load current, computed two ways (by hand here, by the module in
    _ldo_power) and asserted equal."""

    def test_hand_value_100mA(self):
        comp = TS.SourceComp(ref="U3", value="LP5907MFX-3.3")
        cfg = TS._cfg({"i_load_U3_A": 0.100})
        hs = TS._ldo_power(comp, "LP5907", cfg)
        # By hand: P = (Vin-Vout)*Iload + Vin*Iq
        #        = (5.0-3.3)*0.100 + 5.0*12e-6 = 0.17 + 0.00006 = 0.17006 W
        hand = (5.0 - 3.3) * 0.100 + 5.0 * 12e-6
        self.assertAlmostEqual(hand, 0.17006, delta=1e-6)
        self.assertAlmostEqual(hs.watts, hand, delta=1e-4)
        self.assertEqual(hs.family, "ldo")
        self.assertIn("LP5907.pdf", hs.citation)

    def test_zero_load_is_just_quiescent(self):
        comp = TS.SourceComp(ref="U3", value="LP5907MFX-3.3")
        cfg = TS._cfg({"i_load_U3_A": 0.0})
        hs = TS._ldo_power(comp, "LP5907", cfg)
        self.assertAlmostEqual(hs.watts, 5.0 * 12e-6, delta=1e-7)

    def test_teeth_higher_load_raises_power_monotonically(self):
        comp = TS.SourceComp(ref="U3", value="LP5907MFX-3.3")
        lo = TS._ldo_power(comp, "LP5907", TS._cfg({"i_load_U3_A": 0.05}))
        hi = TS._ldo_power(comp, "LP5907", TS._cfg({"i_load_U3_A": 0.20}))
        self.assertGreater(hi.watts, lo.watts)

    def test_tlv75533_reviewed_direct_12vhpwr_case(self):
        comp = TS.SourceComp(ref="U16", value="TLV75533PDRVR")
        cfg = TS._cfg({"i_load_U16_A": 0.2123268, "vin_U16_V": 5.25})
        hs = TS._ldo_power(comp, "TLV75533", cfg)
        hand = (5.25 - 3.3) * 0.2123268 + 5.25 * 25e-6
        self.assertAlmostEqual(hs.watts, hand, delta=1e-6)
        self.assertAlmostEqual(hs.watts, 0.414169, delta=1e-6)


class T1bBuckAnchor(unittest.TestCase):
    def test_tlv62569_loss_floor(self):
        comp = TS.SourceComp(ref="U3", value="TLV62569DBVR")
        cfg = TS._cfg({"i_load_U3_A": 0.215386, "vout_U3_V": 3.318,
                       "efficiency_U3": 0.85})
        hs = TS._buck_power(comp, "TLV62569", cfg)
        hand = 3.318 * 0.215386 * (1.0 / 0.85 - 1.0) + 5.0 * 35e-6
        self.assertAlmostEqual(hs.watts, hand, delta=1e-6)
        self.assertTrue(hs.unverified)

    def test_invalid_efficiency_rejected(self):
        comp = TS.SourceComp(ref="U3", value="TLV62569DBVR")
        with self.assertRaises(ValueError):
            TS._buck_power(comp, "TLV62569", TS._cfg({"efficiency_U3": 0.0}))


class T2LedPlatformAnchor(unittest.TestCase):
    """ANCHOR (hard rule): the LED budget number must reconcile with the
    platform's own documented ~0.4A/board full-white figure (CLAUDE.md)."""

    def test_seven_leds_matches_platform_anchor(self):
        refs = ["DL%d" % i for i in range(1, 8)]
        cfg = TS._cfg(None)
        hs = TS._led_power(refs, cfg)
        total_A = hs.watts / cfg.get("vcc_5vsb_V")
        self.assertAlmostEqual(total_A, 0.4, delta=1e-6,
                               msg="7-LED aggregate must reproduce the CLAUDE.md "
                                   "'~0.4A per board' anchor exactly")
        self.assertTrue(hs.unverified, "per-LED split has no vendored datasheet -- "
                                       "must be marked UNVERIFIED")

    def test_scales_with_led_count(self):
        cfg = TS._cfg(None)
        hs4 = TS._led_power(["DL1", "DL2", "DL3", "DL4"], cfg)
        hs7 = TS._led_power(["DL%d" % i for i in range(1, 8)], cfg)
        # Linear in count (same per-LED draw): 4/7 of the 7-LED figure. Delta is
        # sized to the module's own display rounding (round(..., 6)), not an
        # arbitrary tight bound.
        self.assertAlmostEqual(hs4.watts, hs7.watts * 4 / 7, delta=1e-5)

    def test_override_budget_respected(self):
        cfg = TS._cfg({"led_full_white_budget_A": 0.8})
        hs = TS._led_power(["DL%d" % i for i in range(1, 8)], cfg)
        self.assertAlmostEqual(hs.watts / cfg.get("vcc_5vsb_V"), 0.8, delta=1e-6)


class T3McuDatasheetAnchor(unittest.TestCase):
    """The ESP32-S3 active-current figures must match the vendored datasheet
    table exactly (regression against a re-read of the wrong table/row)."""

    def test_wroom1_matches_table_6_6(self):
        spec = TS.MCU_SPECS["ESP32-S3-WROOM-1"]
        self.assertAlmostEqual(spec["i_active_typ_A"], 0.0662, delta=1e-6)
        self.assertAlmostEqual(spec["i_active_max_A"], 0.0813, delta=1e-6)
        self.assertEqual(spec["vcc_V"], 3.3)

    def test_mini1_reuses_same_silicon_table(self):
        # Same ESP32-S3 die -- must be identical to WROOM-1 (documented reuse,
        # not an independent citation; a drift here would silently invent a
        # different number for the same chip).
        self.assertEqual(TS.MCU_SPECS["ESP32-S3-MINI-1"]["i_active_typ_A"],
                         TS.MCU_SPECS["ESP32-S3-WROOM-1"]["i_active_typ_A"])

    def test_c6_lower_current_than_s3(self):
        c6 = TS.MCU_SPECS["ESP32-C6-MINI-1"]["i_active_max_A"]
        s3 = TS.MCU_SPECS["ESP32-S3-WROOM-1"]["i_active_max_A"]
        self.assertLess(c6, s3)  # sanity: single-core RISC-V C6 draws less than dual-core S3

    def test_duty_interpolates_between_typ_and_max(self):
        comp = TS.SourceComp(ref="U1", value="ESP32-S3-WROOM-1")
        full = TS._mcu_power(comp, "ESP32-S3-WROOM-1", TS._cfg({"mcu_duty": 1.0}))
        half = TS._mcu_power(comp, "ESP32-S3-WROOM-1", TS._cfg({"mcu_duty": 0.5}))
        typ_only = TS.MCU_SPECS["ESP32-S3-WROOM-1"]["i_active_typ_A"] * 3.3
        self.assertGreater(full.watts, half.watts)
        self.assertGreater(half.watts, typ_only - 1e-6)


class T4CanTransceiver(unittest.TestCase):
    def test_duty_zero_is_pure_recessive(self):
        comp = TS.SourceComp(ref="U2", value="TJA1051T/3")
        hs = TS._can_xcvr_power(comp, "TJA1051T/3", TS._cfg({"can_dominant_duty": 0.0}))
        spec = TS.CAN_XCVR_SPECS["TJA1051T/3"]
        self.assertAlmostEqual(hs.watts, spec["vcc_V"] * spec["icc_recessive_typ_A"], delta=1e-6)

    def test_duty_one_is_pure_dominant(self):
        comp = TS.SourceComp(ref="U2", value="TJA1051T/3")
        hs = TS._can_xcvr_power(comp, "TJA1051T/3", TS._cfg({"can_dominant_duty": 1.0}))
        spec = TS.CAN_XCVR_SPECS["TJA1051T/3"]
        self.assertAlmostEqual(hs.watts, spec["vcc_V"] * spec["icc_dominant_typ_A"], delta=1e-6)


class T5DnpDetection(unittest.TestCase):
    """Locks DNP detection against the REAL repo text captured from the
    hub-standard netlist (2026-07-06) for U9 (TPS61040, rung-3 provision) --
    not just a synthetic string -- so a future edit to that description that
    accidentally drops the DNP language is caught."""

    def test_real_u9_description_detected_as_dnp(self):
        comp = TS.SourceComp(
            ref="U9", value="TPS61040DBVR",
            description="H2 rung-3 (owner ruling + coordinator part correction, "
                        "2026-07-03), DNP position-only: 28V-capable low-power boost "
                        "(TPS61040, VIN 1.8-6V, 400mA switch limit, internal soft "
                        "start) trickle-charges the 16V 4700uF reservoir...",
            props={"DNP_Note": "Position-only insurance -- rung-3 provision (H2, "
                               "beta-lock-register 2026-07-03); populate per the "
                               "OQ-56 bench decision, never for beta."})
        self.assertFalse(TS.is_populated(comp))

    def test_ordinary_component_is_populated(self):
        comp = TS.SourceComp(ref="U3", value="LP5907MFX-3.3", description="")
        self.assertTrue(TS.is_populated(comp))

    def test_bare_kicad_dnp_flag_detected(self):
        comp = TS.SourceComp(ref="U99", value="X", props={"__dnp__": True})
        self.assertFalse(TS.is_populated(comp))


class T6Classify(unittest.TestCase):
    def test_family_matches(self):
        cases = [("LP5907MFX-3.3", "ldo"), ("TLV75533PDBVR", "ldo"),
                 ("TLV62569DBVR", "buck"), ("SK6812MINI-E", None),  # handled by ref-prefix path
                 ("ESP32-S3-WROOM-1", "mcu"), ("ESP32-S3-MINI-1-N4R2", "mcu"),
                 ("TJA1051T/3", "can_xcvr"), ("INA238AIDGSR", "sense_amp"),
                 ("INA240A3", "sense_amp"), ("PESD5V0S1BA", "protection_diode"),
                 ("REF3030", "reference"), ("TPS2121RUXR", "power_mux"),
                 ("TPS3839K33", "supervisor")]
        for value, expect in cases:
            comp = TS.SourceComp(ref="U1", value=value)
            fam, _ = TS.classify(comp)
            if expect is not None:
                self.assertEqual(fam, expect, msg="value=%r" % value)

    def test_led_matches_by_ref_prefix_and_value(self):
        comp = TS.SourceComp(ref="DL3", value="SK6812MINI-E")
        fam, part = TS.classify(comp)
        self.assertEqual(fam, "led")
        self.assertEqual(part, "SK6812")

    def test_unknown_part_classifies_none(self):
        comp = TS.SourceComp(ref="C1", value="10uF")
        fam, part = TS.classify(comp)
        self.assertIsNone(fam)


class T7MaterialLimitGate(unittest.TestCase):
    """J2: absolute-T vs material limits, independent of the dT-rise gate."""

    def test_platform_operating_point_passes_everything(self):
        # design ambient 50C + dT_max 30C rise = 80C (thermal-gates corpus anchor).
        checks = TS.material_limit_gate(80.0)
        for c in checks:
            self.assertTrue(c.passed, msg="%s should pass at the platform's own 80C "
                                          "steady-state operating point" % c.material)
        names = {c.material for c in checks}
        self.assertEqual(names, set(TS.MATERIAL_LIMITS))

    def test_margin_sign_and_arithmetic(self):
        checks = TS.material_limit_gate(100.0, materials=["fr4_tg"])
        self.assertEqual(len(checks), 1)
        c = checks[0]
        self.assertAlmostEqual(c.margin_C, c.limit_C - 100.0, delta=1e-9)

    def test_teeth_over_temp_fails_and_reports_negative_margin(self):
        # SABOTAGE: a peak local temperature well past every material's limit.
        checks = TS.material_limit_gate(200.0)
        for c in checks:
            self.assertFalse(c.passed, msg="%s must FAIL at 200C" % c.material)
            self.assertLess(c.margin_C, 0.0)

    def test_connector_housing_limit_matches_research_doc_cross_check(self):
        # docs/research/thermal-gates-derivation-2026-06-10.md's own Molex Mini-Fit
        # Jr 105C connector-operating-temp figure is reused for the TE blade joint
        # housing family (both Nylon 6/6, same order of magnitude) -- pin the value.
        self.assertEqual(TS.MATERIAL_LIMITS["connector_housing_nylon66"]["limit_C"], 105.0)

    def test_cap_floor_matches_thermal_gates_corpus_ceiling(self):
        import json
        path = os.path.join(ROOT, "corpus", "staging", "general", "thermal-gates.json")
        entries = json.load(open(path))
        ceiling = next(e for e in entries if e["id"] == "thermal.gates.t_max_ceiling")["value"]
        self.assertEqual(TS.MATERIAL_LIMITS["aluminum_electrolytic_105C"]["limit_C"], ceiling)


@unittest.skipUnless(_HAVE_KICAD_CLI, "kicad-cli absent -- container/toolchain leg")
class T8HubInventory(unittest.TestCase):
    """Real end-to-end run against the committed hub-standard schematic."""

    @classmethod
    def setUpClass(cls):
        cls.inv = TS.inventory(HUB_DIR)

    def test_total_is_positive_and_dominated_by_leds(self):
        self.assertGreater(self.inv.total_W, 0.0)
        led = next(s for s in self.inv.sources if s.family == "led")
        self.assertGreater(led.watts, self.inv.total_W * 0.5,
                           "the 7x SK6812 chain should dominate Hub Standard's "
                           "beyond-shunt heat budget")

    def test_expected_families_present(self):
        fams = {s.family for s in self.inv.sources}
        for expect in ("buck", "led", "mcu", "can_xcvr"):
            self.assertIn(expect, fams)

    def test_no_mutation_of_board_files(self):
        sch = HUB_SCH
        before = os.path.getmtime(sch)
        TS.inventory(HUB_DIR)
        after = os.path.getmtime(sch)
        self.assertEqual(before, after, "inventory() must never write to the schematic")

    def test_deterministic(self):
        inv2 = TS.inventory(HUB_DIR)
        self.assertEqual(self.inv.total_W, inv2.total_W)
        self.assertEqual(sorted(s.ref for s in self.inv.sources),
                         sorted(s.ref for s in inv2.sources))


@unittest.skipUnless(_HAVE_KICAD_CLI, "kicad-cli absent -- container/toolchain leg")
class T9HpwrInventory(unittest.TestCase):
    """Real end-to-end run against the committed 12vhpwr-standard schematic --
    the second required worked board."""

    @classmethod
    def setUpClass(cls):
        cls.inv = TS.inventory(HPWR_DIR)

    def test_six_ina240_channels_present(self):
        sense = [s for s in self.inv.sources if s.family == "sense_amp"]
        self.assertEqual(len(sense), 6)
        for s in sense:
            self.assertTrue(s.unverified, "INA240 has no vendored datasheet -- must be flagged")

    def test_reference_present(self):
        refs = [s for s in self.inv.sources if s.family == "reference"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].part, "REF3030")

    def test_total_small_relative_to_shunt_power(self):
        # Sanity bound: the beyond-shunt inventory on a 6-shunt 40A-class module should
        # be a small fraction of a single shunt's own I^2R (per spec §6.4, 1mOhm at a
        # design-basis 8.33A/pin: P = I^2R ~= 0.0694W/shunt, ~0.417W across 6 shunts) --
        # NOT dominate it, since shunts are the platform's own already-modeled dominant
        # source and this module's job is everything BESIDES that.
        shunt_class_total_W = 6 * (8.33 ** 2) * 1e-3
        self.assertLess(self.inv.total_W, shunt_class_total_W * 3)


@unittest.skipUnless(_HAVE_PCBNEW, "pcbnew absent -- container leg")
class T10Emissivity(unittest.TestCase):

    def test_partition_sums_to_one(self):
        import glob
        pcbs = [p for p in glob.glob(os.path.join(HPWR_DIR, "*.kicad_pcb"))
               if "-routed" not in p and ".merged." not in p]
        regions = TS.emissivity_regions(sorted(pcbs)[0])
        total_frac = sum(r["area_fraction"] for r in regions["regions"])
        # Each fraction is independently rounded to 4 decimals for display, so the
        # sum can be off by a few 1e-4 even though the underlying areas are an
        # exact partition (asserted separately via area_mm2 below).
        self.assertAlmostEqual(total_frac, 1.0, delta=1e-3)
        total_area = sum(r["area_mm2"] for r in regions["regions"])
        self.assertAlmostEqual(total_area, regions["board_area_mm2"], delta=0.5)
        self.assertEqual({r["class"] for r in regions["regions"]},
                         {"solder_mask_copper", "exposed_pad_metal", "silkscreen"})

    def test_format_contract_keys(self):
        regions = TS.emissivity_regions(HUB_PCB)
        self.assertIn("board", regions)
        self.assertIn("board_area_mm2", regions)
        self.assertGreater(regions["board_area_mm2"], 0)
        for r in regions["regions"]:
            for key in ("class", "area_mm2", "area_fraction", "emissivity", "citation"):
                self.assertIn(key, r)

    def test_exposed_pad_fraction_is_plausible(self):
        import glob
        pcbs = [p for p in glob.glob(os.path.join(HPWR_DIR, "*.kicad_pcb"))
               if "-routed" not in p and ".merged." not in p]
        regions = TS.emissivity_regions(sorted(pcbs)[0])
        exposed = next(r for r in regions["regions"] if r["class"] == "exposed_pad_metal")
        self.assertGreater(exposed["area_fraction"], 0.0)
        self.assertLess(exposed["area_fraction"], 0.5)

    def test_teeth_degenerate_board_raises(self):
        import tempfile
        # A minimal .kicad_pcb with no Edge.Cuts outline -- board_area must come out
        # <= 0 and the function must raise rather than silently report a bogus 100%
        # partition over a zero-area board.
        blank = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False,
                                            mode="w")
        blank.write('(kicad_pcb (version 20240108) (generator "test")\n'
                   '(general (thickness 1.6))\n(layers)\n(setup)\n)\n')
        blank.close()
        try:
            with self.assertRaises(Exception):
                TS.emissivity_regions(blank.name)
        finally:
            os.remove(blank.name)


class T11IsolationDiscipline(unittest.TestCase):
    """Own-module isolation (plan discipline): this module must not import
    cec_synth_pipeline or cec_thermal2d. Checks actual `import`/`from ... import`
    STATEMENTS only (line-start regex), not prose -- this module's own docstring
    legitimately mentions both names in comments explaining what it does NOT do."""

    def test_no_forbidden_imports(self):
        import re
        src = open(os.path.join(ROOT, "scripts", "cec_thermal_sources.py")).read()
        forbidden = ("cec_synth_pipeline", "cec_thermal2d")
        for line in src.splitlines():
            m = re.match(r"^\s*(import|from)\s+(\S+)", line)
            if m:
                for name in forbidden:
                    self.assertNotIn(name, m.group(2),
                                     msg="forbidden import statement: %r" % line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
