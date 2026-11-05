"""Small native, whole-board craft observations for final-consumer regressions."""
import cec_route_quality as quality
from test_route_junction_serial_bridges import native_board


def clean_quality():
    return quality.analyze_board(native_board([(0, 0), (4000000, 0)], 0, 0, False))
