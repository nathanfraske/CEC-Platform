"""Board-independent exact echo reconciliation, including refusal cases."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_copper_echo as echo


def segment(uid, *, net='"signal"', layer='"F.Cu"', width="0.2",
            start="1 2", end="4 2", extra="", locked=False):
    return (f'(segment {"(locked yes)" if locked else ""} (start {start}) '
            f'(end {end}) (width {width}) (layer {layer}) (net {net}) '
            f'(uuid "{uid}") {extra})')


def board(*items):
    return "(kicad_pcb\n" + "\n".join(items) + "\n)\n"


class EchoTests(unittest.TestCase):
    def run_case(self, source, candidate, allowed=None):
        with tempfile.TemporaryDirectory() as temp:
            src, dst = Path(temp) / "source", Path(temp) / "candidate"
            src.write_text(source)
            dst.write_text(candidate)
            report = echo.remove_exact_echoes(src, dst, generated_uuids=allowed)
            self.assertEqual(src.read_text(), source)
            result = dst.read_text()
            second = echo.remove_exact_echoes(src, dst, generated_uuids=allowed)
            self.assertEqual(second["removed_count"], 0)
            self.assertEqual(dst.read_text(), result)
            return report, result

    def test_exact_reverse_echo_preserves_partial_net_extension_and_prefix(self):
        original = segment("original", locked=True)
        copied = segment("copy", start="4.0 2.0", end="1.0 2.0", width="0.200")
        branch = segment("branch", start="4 2", end="7 2")
        group = '(group "owner" (uuid "group") (members "original"))'
        report, result = self.run_case(board(original, group), board(original, copied, branch, group))
        self.assertEqual(report["removed_count"], 1)
        self.assertEqual(report["removed"][0]["original_uuid"], "original")
        for preserved in (original, branch, group):
            self.assertIn(preserved, result)
        self.assertNotIn(copied, result)

    def test_transforms_and_anonymous_net_names(self):
        for start, end in [("-21 9", "-21 6"), ("31 -5", "34 -2"), ("0 0", "-3 -3")]:
            with self.subTest(start=start):
                src = segment("o", start=start, end=end, net='"unseen net (a)"')
                new = segment("n", start=end, end=start, net='"unseen net (a)"')
                self.assertEqual(self.run_case(board(src), board(src, new))[0]["removed_count"], 1)

    def test_near_overlap_different_net_layer_width_and_fields_are_not_echoes(self):
        original = segment("o")
        for kwargs in ({"net": '"other"'}, {"layer": '"B.Cu"'}, {"width": "0.21"},
                       {"start": "1.000001 2"}, {"end": "5 2"},
                       {"extra": "(solder_mask_margin 0.01)"},
                       {"extra": "(unknown_future_field yes)"}):
            with self.subTest(kwargs=kwargs):
                candidate = board(original, segment("n", **kwargs))
                report, result = self.run_case(board(original), candidate)
                self.assertEqual(report["removed_count"], 0)
                self.assertEqual(result, candidate)

    def test_missing_or_changed_original_cannot_authorize_removal(self):
        original, new = segment("o"), segment("n")
        for items in [(new,), (segment("o", end="5 2"), new)]:
            self.assertEqual(self.run_case(board(original), board(*items))[0]["removed_count"], 0)

    def test_group_owned_new_item_and_unselected_new_item_are_retained(self):
        original, new = segment("o"), segment("n")
        report, _ = self.run_case(board(original), board(original, new), allowed={"elsewhere"})
        self.assertEqual(report["removed_count"], 0)
        group = '(group "proposal" (uuid "g") (members "n"))'
        report, _ = self.run_case(board(original), board(original, new, group))
        self.assertEqual(report["removed_count"], 0)
        self.assertEqual(len(report["group_owned_echoes_retained"]), 1)

    def test_existing_duplicates_are_not_touched(self):
        content = board(segment("o"), segment("already"))
        self.assertEqual(self.run_case(content, content)[1], content)

    def test_numeric_net_codes_are_rebound_by_name(self):
        source = board('(net 1 "signal")', segment("o", net="1"))
        candidate = board('(net 12 "signal")', segment("o", net="12"), segment("n", net="12"))
        self.assertEqual(self.run_case(source, candidate)[0]["removed_count"], 1)

    def test_via_dimensions_layers_and_full_padstack_are_compared(self):
        template = '(via (at 1 2) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "signal") (uuid "o"))'
        copied = template.replace('"o"', '"n"')
        self.assertEqual(self.run_case(board(template), board(template, copied))[0]["removed_count"], 1)
        for changed in (copied.replace("drill 0.3", "drill 0.2"), copied.replace('"B.Cu"', '"In1.Cu"'),
                        copied[:-1] + ' (padstack (mode custom)))'):
            self.assertEqual(self.run_case(board(template), board(template, changed))[0]["removed_count"], 0)

    def test_arc_midpoint_is_preserved(self):
        original = '(arc (start 1 1) (mid 2 3) (end 4 1) (width 0.2) (layer "F.Cu") (net "signal") (uuid "o"))'
        new = original.replace('"o"', '"n"').replace("start 1 1", "start 4 1").replace("end 4 1", "end 1 1")
        self.assertEqual(self.run_case(board(original), board(original, new))[0]["removed_count"], 1)
        self.assertEqual(self.run_case(board(original), board(original, new.replace("mid 2 3", "mid 2 4")))[0]["removed_count"], 0)

    def test_malformed_or_duplicate_identity_fails_closed(self):
        original = segment("o")
        for malformed in ("not a board", board(original, original), board(original)[:-2],
                          board(original) + "(anything)", board(original) + "junk"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    self.run_case(board(original), malformed)

    def test_native_boundary_removes_only_live_new_identity(self):
        import cec_swig_guard
        cec_swig_guard.pin()
        import pcbnew
        native = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(native, "test-net")
        native.Add(net)
        def track(x, end):
            item = pcbnew.PCB_TRACK(native)
            item.SetNet(net)
            item.SetStart(pcbnew.VECTOR2I_MM(x, 2))
            item.SetEnd(pcbnew.VECTOR2I_MM(end, 2))
            item.SetWidth(pcbnew.FromMM(0.2))
            item.SetLayer(pcbnew.F_Cu)
            native.Add(item)
            return item.m_Uuid.AsString()
        original = track(1, 4)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.kicad_pcb"
            pcbnew.SaveBoard(str(source), native, True)
            before = source.read_bytes()
            copied = track(4, 1)
            extension = track(4, 7)
            result = echo.remove_exact_echoes_board(source, native)
            self.assertEqual(source.read_bytes(), before)
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["removed"][0]["uuid"], copied)
        self.assertEqual({t.m_Uuid.AsString() for t in native.GetTracks()}, {original, extension})

    def test_locked_reconciliation_uses_full_serialized_geometry(self):
        original = segment('o', locked=True)
        for kwargs in ({}, {'width':'0.21'}, {'layer':'"B.Cu"'}, {'net':'"other"'},
                       {'start':'1.000001 2'}, {'extra':'(future_field yes)'}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)/'candidate'; path.write_text(board(original, segment('n', **kwargs)))
                report = echo.reconcile_locked_additions(path, locked_uuids={'o'})
                self.assertEqual(report['removed_count'], 0 if kwargs else 1)

    def test_locked_reconciliation_arc_and_via_fields(self):
        for kind, original, changed in (
            ('arc', '(arc (locked yes) (start 1 1) (mid 2 3) (end 4 1) (width 0.2) (layer "F.Cu") (net "s") (uuid "o"))',
             ('mid 2 3', 'mid 2 4')),
            ('via', '(via (locked yes) (at 1 2) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "s") (uuid "o"))',
             ('drill 0.3', 'drill 0.2'))):
            for different in (False, True):
                with self.subTest(kind=kind, different=different), tempfile.TemporaryDirectory() as temp:
                    new = original.replace('(locked yes)', '').replace('"o"', '"n"')
                    if different: new = new.replace(*changed)
                    path = Path(temp)/'candidate'; path.write_text(board(original, new))
                    self.assertEqual(echo.reconcile_locked_additions(path, locked_uuids={'o'})['removed_count'],
                                     0 if different else 1)

    def test_locked_reconciliation_rejects_stale_identity_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'candidate'; text = board(segment('o', locked=True)); path.write_text(text)
            with self.assertRaises(ValueError):
                echo.reconcile_locked_additions(path, locked_uuids={'missing'})
            self.assertEqual(path.read_text(), text)


if __name__ == "__main__":
    unittest.main()
