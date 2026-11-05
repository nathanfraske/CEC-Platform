"""Diagnostics label the actual source instead of a historical test board."""
import inspect
from PIL import Image
import cec_zoomplot as plot


def test_no_historical_board_or_component_defaults():
    source=inspect.getsource(plot.main)
    assert 'EPS routed_0' not in source and 'INA238' not in source
    assert 'SHA256' in source and 'sorted({ref for ref, _pad in unconn})' in source
    assert 'GND escape to plane' not in source
    assert 'plane connection not inferred' in source


def test_outside_geometry_does_not_overpaint_source_header(tmp_path):
    output=str(tmp_path/'zoom.png')
    # A wide off-view trace reaches the header unless provenance is drawn last.
    tracks=[dict(x0=-1,y0=-1,x1=5,y1=-1,w=4,layer=plot.FCU,net='/ANY')]
    plot._render([],tracks,[],[],set(),(0,0,5,5),set(),set(),
        'Source hash / layer key',output,px_w=500,top=80)
    with Image.open(output) as image:
        assert image.getpixel((499,10))==(250,250,250)
