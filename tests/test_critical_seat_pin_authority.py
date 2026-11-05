"""Initial critical seating must use the same true pads as route receiving."""
import math

import pytest

import cec_pcb
import cec_synth_pipeline as synth
from test_terminal_pin_contract import fixture


def seat(data,monkeypatch):
    nl,local,poses,_,follower,lo=data
    anchor=next(ref for ref in poses if ref!=follower)
    hi=next(net for net in nl.nets if net!=lo and net!='SUPPLY')
    monkeypatch.setattr(cec_pcb,'local_pads',lambda ref:local[ref])
    monkeypatch.setattr(cec_pcb,'local_pad_sizes',lambda ref:{p:(.2,.2) for p in local[ref]})
    monkeypatch.setattr(synth,'_courtyard_info',lambda *a:(0.,0.,1.5,1.5))
    monkeypatch.setattr(synth,'_downstream_comparators',lambda *a:[])
    def bbox(ref,x=0.,y=0.,rot=0.,**kwargs):
        hx,hy=(.5,2.2) if ref==anchor else (1.5,1.5)
        points=[cec_pcb._rot(a,b,rot) for a in (-hx,hx) for b in (-hy,hy)]
        return (x+min(p[0] for p in points),x+max(p[0] for p in points),
                y+min(p[1] for p in points),y+max(p[1] for p in points))
    monkeypatch.setattr(cec_pcb,'courtyard_bbox',bbox)
    anchors={anchor:poses[anchor]}
    topo=[dict(shunt=anchor,hi=hi,lo=lo)]
    seated=synth._seat_sense_ics(topo,anchors,nl,{ref:ref for ref in poses},300,300)
    return seated,anchors,anchor,hi,lo


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('reflected',[False,True])
def test_vbus_order_and_reference_spelling_cannot_change_actual_input_seat(monkeypatch,angle,reflected):
    data=fixture(offset=(137,51),angle=angle,reflected=reflected)
    first,poses,anchor,hi,lo=seat(data,monkeypatch)
    follower=data[-2]
    assert first==[follower]  # This deliberately has no U-prefix.
    data[0].nets[lo].reverse()
    again,second,*_=seat(data,monkeypatch)
    assert again==first and second==poses
    for net,pin in ((hi,'10'),(lo,'9')):
        source_pin=next(p for r,p in data[0].nets[net] if r==anchor)
        source=cec_pcb.pad_global(anchor,source_pin,poses,{r:r for r in poses})
        target=cec_pcb.pad_global(follower,pin,poses,{r:r for r in poses})
        assert math.dist(source,target)<9.


@pytest.mark.parametrize('fault',['missing_native_input','wrong_net','shorted_inputs'])
def test_known_but_invalid_initial_input_geometry_cannot_use_vbus_fallback(monkeypatch,fault):
    data=fixture();nl,local,_,_,follower,lo=data
    if fault=='missing_native_input':del local[follower]['9']
    else:
        nl.nets[lo].remove((follower,'9'))
        destination='UNRELATED' if fault=='wrong_net' else '/arbitrary/rail_HI'
        nl.nets.setdefault(destination,[]).append((follower,'9'))
    with pytest.raises(ValueError,match='current-input terminal'):
        seat(data,monkeypatch)


def test_unknown_device_is_not_assigned_a_guessed_current_input_seat(monkeypatch):
    seated,poses,*_=seat(fixture(value='UNKNOWN_MONITOR'),monkeypatch)
    assert not seated and len(poses)==1
