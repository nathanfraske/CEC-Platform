"""A centered via plan must become real rooted copper with native receiving."""

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
from cec_pipeline import construction, connections, capabilities, protocol
from test_lastmile import _board


def source_board(tmp_path):
    board = _board([(10, 10, "GND"), (15, 10, "GND")], edge=(0, 0, 25, 25))
    for face in board.GetEnabledLayers().CuStack():
        zone = pcbnew.ZONE(board)
        zone.SetLayer(face)
        zone.SetNet(board.FindNet("GND"))
        zone.SetMinThickness(100000)
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.Outline().NewOutline()
        for x, y in ((2, 2), (22, 2), (22, 22), (2, 22)):
            zone.Outline().Append(x * 1000000, y * 1000000)
        board.Add(zone)
    via = pcbnew.PCB_VIA(board)
    via.SetNet(board.FindNet("GND"))
    via.SetPosition(pcbnew.VECTOR2I_MM(18, 18))
    via.SetWidth(600000)
    via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    board.Add(via)
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    source = tmp_path / "source.kicad_pcb"
    field._save_field_snapshot(board, source)
    return source


@pytest.mark.parametrize(
    "at",
    [
        [10000000, 12000000],
        [12000000, 10000000],
        [15000000, 12000000],
        [12000000, 15000000],
    ],
)
def test_explicit_ground_barrel_is_saved_and_rooted_without_source_retirement(
    tmp_path, at
):
    source = source_board(tmp_path)
    candidate = force._copy_family(source, tmp_path / "private")
    operation = dict(
        kind="add_connections",
        routes=[],
        vias=[dict(net="GND", at_nm=at, diameter_nm=600000, drill_nm=300000)],
    )
    before = source.read_bytes()
    record = construction._construct(
        source, candidate, dict(operations=[operation]), "opaque"
    )
    proof = connections.receive(source, candidate, board_hint="opaque")
    assert (
        proof["ok"] and proof["complete"] and proof["all_source_partitions_preserved"]
    )
    assert not record["retired_track_uuids"] and source.read_bytes() == before
    assert not proof["new_barrel_capacity_credited"] and not proof["release_authority"]


def test_schema_and_mandatory_receiving_catalog_cannot_drift():
    exposed = {row["properties"]["kind"]["const"] for row in protocol._OPERATIONS}
    assert exposed == set(capabilities.CAPABILITIES)
    assert set(capabilities.CAPABILITIES["add_connections"]) == {
        "current_pair",
        "kelvin_pair",
        "assembly_pair",
    }


def test_unqualified_small_barrel_is_refused_without_any_process_waiver(tmp_path):
    source = source_board(tmp_path)
    candidate = force._copy_family(source, tmp_path / "small")
    operation = dict(
        kind="add_connections",
        routes=[],
        vias=[
            dict(
                net="GND",
                at_nm=[10000000, 12000000],
                diameter_nm=100000,
                drill_nm=50000,
            )
        ],
    )
    with pytest.raises(ValueError, match="process_via_dimensions"):
        construction._construct(
            source, candidate, dict(operations=[operation]), "opaque"
        )


def test_floating_via_on_another_island_cannot_borrow_a_zone_uuid(tmp_path):
    source = source_board(tmp_path)
    candidate = force._copy_family(source, tmp_path / "floating")
    operation = dict(
        kind="add_connections",
        routes=[],
        vias=[
            dict(
                net="GND",
                at_nm=[23500000, 23500000],
                diameter_nm=600000,
                drill_nm=300000,
            )
        ],
    )
    construction._construct(source, candidate, dict(operations=[operation]), "opaque")
    with pytest.raises(ValueError, match="source_terminal_island"):
        connections.receive(source, candidate, board_hint="opaque")
