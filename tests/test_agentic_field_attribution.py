"""Role direction follows the effective relation, not track iteration order."""

import pcbnew

import cec_field_coupling as field
import test_field_coupling as fixtures


def test_dual_role_member_cannot_make_an_aggressor_only_member_the_victim(tmp_path, monkeypatch):
    source = fixtures.FieldCouplingTest()._board(str(tmp_path), [
        ("/DUAL", "F.Cu", (4., 8.), (20., 8.)),
        ("/DRIVER", "F.Cu", (4., 8.6), (20., 8.6)),
    ])
    board = pcbnew.LoadBoard(source)
    items = sorted(board.GetTracks(), key=lambda t: t.GetNetname() != "/DUAL")
    monkeypatch.setattr(board, "GetTracks", lambda: items)
    classes = lambda net: "DDR HighSpeed" if net == "/DUAL" else "SwitchNode"
    report = field.field_coupling_summary(source, board=board, _netclass_resolver=classes)
    assert report["blocking_count"] == 1
    row = report["interactions"][0]
    assert row["nets"] == ["/DUAL", "/DRIVER"]
    assert row["aggressor"] == "/DRIVER" and row["victim"] == "/DUAL"
    assert row["member_roles"][0]["aggressor"] and row["member_roles"][0]["victim"]
    assert row["member_roles"][1]["aggressor"] and not row["member_roles"][1]["victim"]
