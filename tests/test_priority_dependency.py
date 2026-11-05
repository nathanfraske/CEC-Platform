"""Atomic, board-neutral priority dependency replacement contracts."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_priority_dependency as dependency
import cec_frozen_copper


def contract():
    return {"schema": 1, "items": 4, "nets": ["s+", "s-", "rail", "reference"],
            "members": {"a": 1, "b": 1, "c": 1, "d": 1},
            "member_nets": {"a": "s+", "b": "s-", "c": "rail", "d": "reference"},
            "items_by_net": {"s+": 1, "s-": 1, "rail": 1, "reference": 1},
            "placement_preserved_nets": ["s+", "s-", "rail"],
            "placement_power_nets": ["rail"], "placement_preserved_uuids": ["return"],
            "qualified_critical_pairs": [{"name": "anonymous", "p": "s+", "n": "s-", "qualified": True}]}


def conflict(net="s+"):
    return {"ok": False, "violations": [{"kind": "fixed_copper_pad_collision",
                                          "copper_net": net, "copper_uuid": "track"}]}


class DependencyTest(unittest.TestCase):
    def test_reconstruction_effort_is_funded_but_explicit_limit_wins(self):
        self.assertEqual(dependency.operation_budget({},env={})["requested_s"],780)
        self.assertEqual(dependency.operation_budget({"priority_dependency_trials":0},env={})["requested_s"],240)
        self.assertEqual(dependency.operation_budget({"priority_dependency_max_pairs":0},env={})["requested_s"],240)
        result=dependency.operation_budget({"power_terminal_repair_timeout_s":90},env={})
        self.assertTrue(result["explicit_limit"])
        self.assertEqual(result["requested_s"],90)
        result=dependency.operation_budget({"priority_dependency_trials":1,"priority_dependency_max_pairs":2},
                                          env={"CEC_PRECISION_PAIR_TIMEOUT":"45"})
        self.assertEqual(result["requested_s"],360)

    def test_nonfinite_budget_cannot_disable_operation_guard(self):
        for value in ("nan","inf","-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                dependency.operation_budget({},env={"CEC_PRECISION_PAIR_TIMEOUT":value})

    def test_rejected_exact_artifacts_are_bounded_and_not_promoted(self):
        import cec_power_failure
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = root / "exact.kicad_pcb"
            state = root / "state.json"
            board.write_text("exact rejected copper")
            state.write_text('{"passed": false}')
            evidence = root / "diagnostics"
            first = cec_power_failure.retain_exact_trial(board, state, evidence,
                                                       limit=1, minimum_free_gib=0)
            second = cec_power_failure.retain_exact_trial(board, state, evidence,
                                                        limit=1, minimum_free_gib=0)
            self.assertTrue(first["retained"])
            self.assertFalse(first["release_authority"])
            self.assertEqual(Path(first["board"]).read_bytes(), board.read_bytes())
            self.assertEqual(second["reason"], "diagnostic_artifact_budget_exhausted")
            self.assertEqual(board.read_text(), "exact rejected copper")

    def test_atomic_release_keeps_power_and_item_scoped_returns(self):
        original = contract()
        before = copy.deepcopy(original)
        plan = dependency.release_plan(original, conflict())
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["nets"], ["s+", "s-"])
        reduced = plan["retained_contract"]
        self.assertEqual(reduced["members"], {"c": 1, "d": 1})
        self.assertEqual(reduced["placement_preserved_nets"], ["rail"])
        self.assertEqual(reduced["placement_preserved_uuids"], ["return"])
        self.assertEqual(reduced["items"], 2)
        self.assertEqual(original, before)

    def test_power_unknown_and_anchor_collisions_fail_closed(self):
        for report in (conflict("rail"), conflict("unknown"),
                       {"ok": False, "violations": [{"kind": "frozen_anchor_moved"}]},
                       {"ok": True, "violations": conflict()["violations"]},
                       {"ok": False, "violations": []}):
            with self.subTest(report=report):
                self.assertFalse(dependency.release_plan(contract(), report)["ok"])

    def test_complete_native_anchor_witness_can_release_only_whole_signal_pair(self):
        anchor = {'kind':'frozen_anchor_moved', 'ref':'component',
                  'attachments_complete':True,
                  'attachments':[dict(pad='7', copper_net='s+', copper_uuid='trace')]}
        report = dict(ok=False, violations=[anchor])
        plan = dependency.release_plan(contract(), report)
        self.assertTrue(plan['ok'])
        self.assertEqual(plan['nets'], ['s+', 's-'])
        for net in ('rail', 'unknown', 'reference'):
            other = copy.deepcopy(report)
            other['violations'][0]['attachments'].append(dict(pad='8', copper_net=net, copper_uuid='other'))
            self.assertFalse(dependency.release_plan(contract(), other)['ok'])
        for field in ('attachments_complete', 'attachments'):
            other = copy.deepcopy(report)
            del other['violations'][0][field]
            self.assertFalse(dependency.release_plan(contract(), other)['ok'])

    def test_handoff_is_a_bounded_fair_offer_not_release_authority(self):
        offer = dependency.placement_handoff(contract(), conflict(),
            dict(kind='rotate', ref='component', position=[1,2,90]))
        self.assertTrue(offer['priority_dependency_replacement'])
        self.assertNotIn('retained_contract', offer['dependency_offer'])
        self.assertIsNone(dependency.placement_handoff(contract(), conflict('rail'),
            dict(kind='rotate', ref='component', position=[1,2,90])))
        other = dict(offer, placements={'second':[2,3,90]})
        power = dict(kind='shift', placements={'third':[3,4,0]})
        report = dict(rounds=[dict(priority_dependency_candidates=[offer,other],
                                  power_replan_candidates=[power,power])])
        self.assertEqual(dependency.handoff_candidates(report,2),[offer,power])
        self.assertEqual(dependency.handoff_candidates(report,9),[offer,power,other])
        self.assertEqual(dependency.handoff_candidates(report,0),[])

    def test_unreproduced_dependency_offer_cannot_authorize_a_placement(self):
        import cec_full_pipeline as pipeline
        import cec_synth_pipeline as synth
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'board.kicad_pcb'
            source.write_text('protected source')
            ordinary = dict(baseline_key=[0,1]+[0]*17, rounds=[dict(
                priority_dependency_candidates=[dict(kind='shift',
                    priority_dependency_replacement=True, placements={'component':[1,2,0]})])])
            def materialize(candidate,cfg,path):
                Path(path).write_text('unproven proposal')
            with mock.patch.object(synth,'placement_candidate_from_board',return_value=SimpleNamespace(
                    P={},protected_power_prefix=contract())), \
                    mock.patch.object(synth,'materialize',side_effect=materialize), \
                    mock.patch.object(pipeline,'_ensure_placement_route_authority') as power, \
                    mock.patch.object(dependency,'rebuild') as rebuild:
                result = pipeline._repair_placement_priority_routes_with_power_replan(
                    SimpleNamespace(params={}),source,ordinary,allow_authored_prefix=True)
            self.assertEqual(result['power_replan']['trials'][0]['reason'],
                             'offered_pair_dependency_not_reproduced')
            self.assertEqual(source.read_text(),'protected source')
            power.assert_not_called()
            rebuild.assert_not_called()

    def test_retained_copper_is_screened_before_offer_and_context_is_reused(self):
        contexts = {}
        move = dict(kind='shift',ref='movable',position=[1,2,0])
        with mock.patch.object(cec_frozen_copper,'FrozenCopperContext') as constructor:
            checker = constructor.return_value
            checker.check.return_value = dict(ok=False,violations=[dict(copper_net='rail')])
            result = dependency.screen_placement_handoff('source',contract(),conflict(),move,contexts=contexts)
            self.assertFalse(result['ok'])
            self.assertEqual(result['reason'],'replacement_target_conflicts_with_retained_copper')
            self.assertNotIn('handoff',result)
            checker.check.return_value = dict(ok=True)
            result = dependency.screen_placement_handoff('source',contract(),conflict(),move,contexts=contexts)
            self.assertTrue(result['ok'])
            self.assertTrue(result['handoff']['priority_dependency_replacement'])
            self.assertEqual(constructor.call_count,1)
            self.assertEqual(constructor.call_args.args,('source',('rail',)))
            self.assertEqual(constructor.call_args.kwargs,dict(item_uuids=('return',)))

    def test_reconstruction_honors_both_declared_power_authority_modes(self):
        import cec_critical_checkpoint as checkpoint
        import cec_synth_pipeline as synth
        from contextlib import nullcontext
        for params, required in (({},False), ({'pour_first':True},True),
                                  ({'pour_reserve':True,'overunder':True},True)):
            cfg = SimpleNamespace(params=params)
            with mock.patch.object(checkpoint,'construct',return_value={'ok':False}) as construct, \
                    mock.patch.object(synth,'_oracle_env',return_value=nullcontext()) as environment:
                result = dependency.construct_released_pairs(cfg,'source','out',['pair'])
            construct.assert_called_once_with('source','out',['pair'],frozen_route_config=cfg if required else None)
            environment.assert_called_once_with(params)
            self.assertFalse(result['ok'])

    def test_future_craft_checker_failures_are_not_dropped(self):
        import cec_full_pipeline as pipeline
        evidence = {'new_checker':{'ok':False,'witnesses':[{'why':'new constraint'}]},
                    'known_good':{'ok':True},'errors':['native failure'],'ok':False}
        compact = pipeline._placement_craft_failures(evidence)
        self.assertEqual(set(compact),{'new_checker','errors'})
        evidence['new_checker']['witnesses'].clear()
        self.assertEqual(len(compact['new_checker']['witnesses']),1)

    def test_no_missing_power_or_member_identity_is_inferred(self):
        for field in ("placement_power_nets", "member_nets", "placement_preserved_nets"):
            item = contract()
            del item[field]
            self.assertFalse(dependency.release_plan(item, conflict())["ok"])

    def test_unqualified_pair_cannot_be_released(self):
        item = contract()
        item["qualified_critical_pairs"][0]["qualified"] = False
        self.assertFalse(dependency.release_plan(item, conflict())["ok"])

    def test_transitive_shared_net_closure_obeys_budget(self):
        item = contract()
        item["qualified_critical_pairs"].append({"name": "sibling", "p": "s-", "n": "third", "qualified": True})
        item["members"]["e"] = 1
        item["member_nets"]["e"] = "third"
        item["placement_preserved_nets"].append("third")
        self.assertFalse(dependency.release_plan(item, conflict(), max_pairs=1)["ok"])
        plan = dependency.release_plan(item, conflict(), max_pairs=2)
        self.assertEqual(plan["nets"], ["s+", "s-", "third"])
        item["placement_power_nets"].append("third")
        self.assertFalse(dependency.release_plan(item, conflict(), max_pairs=2)["ok"])

    def test_policy_disabled(self):
        self.assertFalse(dependency.release_plan(contract(), conflict(), max_pairs=0)["ok"])

    def test_all_rebuild_obligations_are_mandatory(self):
        row = {"constructed": True, "retained_prefix": {"ok": True},
               "all_original_pairs": {"ok": True}, "placement_unchanged": True,
               "authority": {"ok": True}, "physical_ok": True}
        self.assertTrue(dependency.rebuilt_admitted(row))
        for field in row:
            bad = copy.deepcopy(row)
            bad[field] = {"ok": False} if isinstance(bad[field], dict) else False
            self.assertFalse(dependency.rebuilt_admitted(bad), field)

    def test_typed_collision_retains_full_rows(self):
        report = conflict()
        report["violations"] *= 20
        error = cec_frozen_copper.FrozenCopperConflict(report)
        report["violations"].clear()
        self.assertIsInstance(error, ValueError)
        self.assertEqual(len(error.report["violations"]), 20)

    def test_pipeline_requires_rebuild_before_promotion(self):
        import cec_full_pipeline as pipeline
        import cec_synth_pipeline as synth
        import cec_route_preflight as preflight
        import cec_priority_replacement_receipt as receipts
        for rebuilt_ok, first_physical_failure, budget, normal_offer in (
                (False,False,1,False), (True,False,1,False), (True,True,1,False), (False,False,0,False),
                (False,False,1,True), (True,False,1,True), (True,True,1,True), (False,False,0,True)):
            with self.subTest(rebuilt_ok=rebuilt_ok, first_physical_failure=first_physical_failure, budget=budget), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "source.kicad_pcb"
                source.write_text("baseline")
                cfg = SimpleNamespace(params={"priority_dependency_trials": budget})
                ordinary = {"baseline_key": [0]*19, "rounds": [{"power_replan_candidates": [
                    {"kind": "shift", "placements": {"movable": [1, 0, 0]}}]}]}
                if first_physical_failure:
                    ordinary["rounds"][0]["power_replan_candidates"].append(
                        {"kind": "shift", "placements": {"movable": [2, 0, 0]}})
                if normal_offer:
                    ordinary['baseline_key'][1] = 1
                    offers = ordinary['rounds'][0].pop('power_replan_candidates')
                    for row in offers:
                        row['priority_dependency_replacement'] = True
                    ordinary['rounds'][0]['priority_dependency_candidates'] = offers
                def candidate(*args, **kwargs):
                    return SimpleNamespace(P={"movable": (0, 0, 0)}, protected_power_prefix=contract())
                def materialize(item, _cfg, path):
                    if "a" in item.protected_power_prefix["members"]:
                        raise cec_frozen_copper.FrozenCopperConflict(conflict())
                    Path(path).write_text("candidate")
                with mock.patch.object(synth, "placement_candidate_from_board", side_effect=candidate), \
                        mock.patch.object(synth, "materialize", side_effect=materialize), \
                        mock.patch.object(synth, "_oracle_pads_in_bounds", return_value={"ok": True}), \
                        mock.patch.object(synth, "_oracle_courtyard_overlaps", side_effect=(
                            [{"ok": False, "findings": ["overlap"]}, {"ok": True}] if first_physical_failure
                            else [{"ok": True}])), \
                        mock.patch.object(synth, "placement_craft_evidence", return_value={}), \
                        mock.patch.object(pipeline, "_placement_craft_gate", return_value={"ok": True}), \
                        mock.patch.object(pipeline, "_placement_constraint_gate", return_value={"ok": True}), \
                        mock.patch.object(pipeline, "_ensure_placement_route_authority", return_value={"ok": True}), \
                        mock.patch.object(pipeline, "_measure_placement_physical", return_value={
                            key: {"ok": True} for key in ("pads_in_bounds", "courtyards", "craft_gate", "constraint_gate")}), \
                        mock.patch.object(dependency, "rebuild", return_value={"ok": rebuilt_ok}) as rebuild, \
                        mock.patch.object(receipts, "issue", return_value={"checksum":"test-only"}) as issue, \
                        mock.patch.object(receipts, "stage", return_value={"count":1}) as stage, \
                        mock.patch.object(pipeline, "_measure_placement_priority_routes", return_value={"key": [0]*19}) as measure, \
                        mock.patch.object(preflight, "placement_evidence_key", side_effect=lambda e: tuple(e["key"])):
                    result = pipeline._repair_placement_priority_routes_with_power_replan(
                        cfg, source, ordinary, allow_authored_prefix=True, repairing_failed_authority=not normal_offer)
                self.assertEqual(bool(result.get("changed")), rebuilt_ok)
                self.assertEqual(source.read_text(), "candidate" if rebuilt_ok else "baseline")
                self.assertEqual(result["power_replan"]["priority_dependency_trials"], budget)
                self.assertEqual(result["power_replan"]["priority_dependency_screens"],
                                 2 if first_physical_failure else budget)
                self.assertEqual(rebuild.call_count, budget)
                self.assertEqual(measure.call_count, 1 if rebuilt_ok else 0)
                self.assertEqual(issue.call_count, 1 if rebuilt_ok else 0)
                self.assertEqual(stage.call_count, 1 if rebuilt_ok else 0)
                if not budget:
                    self.assertEqual(result["power_replan"]["trials"][0]["reason"],
                                     "priority_dependency_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
