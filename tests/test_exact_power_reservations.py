"""An admitted physical authority supersedes its coarse search halo only."""
from copy import deepcopy
import json
import pcbnew
import pytest
import cec_fr
import cec_power_guard_geometry as geometry


def fixture():
    return dict(placement_scope='complete', frozen_nets=['BUS'],
        exact_admission={'passed': True}, vias=[],
        corridors=[dict(net='BUS',layer='In3.Cu',x0=0,y0=0,x1=10,y1=8)],
        pours=[dict(net='BUS',layer='In3.Cu',polygon=[[0,0],[10,0],[10,2],[0,2]])])


def native_board():
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    for index,net in enumerate(('BUS','RETURN')):
        b.Add(pcbnew.NETINFO_ITEM(b,net))
        # KiCad intentionally prunes unused nets at serialization.
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(net));t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(pcbnew.FromMM(.2));t.SetStart(pcbnew.VECTOR2I_MM(30,30+index))
        t.SetEnd(pcbnew.VECTOR2I_MM(31,30+index));b.Add(t)
    return b


def via_ok(b,x,y):
    net=b.FindNet('RETURN').GetNetCode()
    return cec_fr._via_spot_clear(b,pcbnew.VECTOR2I_MM(x,y),pcbnew.FromMM(.6),
        pcbnew.FromMM(.2),{net},net_code=net,drill_nm=pcbnew.FromMM(.3))


@pytest.mark.parametrize('turn',range(4))
def test_exact_halo_retires_without_changing_any_physical_source(turn):
    s=fixture();s['frozen_nets']=['OTHER_BUS'];s['corridors'][0]['net']='OTHER_BUS'
    s['pours'][0]['net']='OTHER_BUS'
    def point(x,y):
        for _ in range(turn):x,y=-y,x
        return [x+17,y-23]
    s['pours'][0]['polygon']=[point(x,y) for x,y in s['pours'][0]['polygon']]
    corners=[point(x,y) for x,y in ((0,0),(10,8))]
    s['corridors'][0].update(x0=min(p[0] for p in corners),x1=max(p[0] for p in corners),
                            y0=min(p[1] for p in corners),y1=max(p[1] for p in corners))
    before=deepcopy(s);rows=geometry.reservations(s)
    assert rows and all(r.get('authority')=='exact_frozen_polygon' for r in rows)
    assert s==before


def test_native_via_uses_free_halo_but_cannot_pierce_frozen_bus(monkeypatch,tmp_path):
    s=fixture();b=native_board();path=tmp_path/'native.kicad_pcb'
    pcbnew.SaveBoard(str(path),b,True);b=pcbnew.LoadBoard(str(path))
    monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:s)
    assert via_ok(b,5,4)
    assert not via_ok(b,5,1)
    assert not via_ok(b,5,2.4)  # actual copper still gets full clearance
    s['exact_admission']['passed']=False
    assert not via_ok(b,5,4)


@pytest.mark.parametrize('case',['no_pass','truthy_pass','no_vias','bad_via','nan_via','missing_net'])
def test_incomplete_proof_does_not_free_any_search_space(case):
    s=fixture()
    if case=='no_pass':s.pop('exact_admission')
    elif case=='truthy_pass':s['exact_admission']['passed']=1
    elif case=='no_vias':s.pop('vias')
    elif case=='bad_via':s['vias']=[{}]
    elif case=='nan_via':s['vias']=[dict(x_mm=float('nan'),y_mm=2)]
    else:s['frozen_nets'].append('MISSING')
    assert s['corridors'][0] in geometry.reservations(s)


@pytest.mark.parametrize('kind',['bridge_via','protected_channel','unknown'])
def test_explicit_or_unknown_reservations_are_not_raster_halos(kind):
    s=fixture();s['corridors'][0]['kind']=kind
    assert s['corridors'][0] in geometry.reservations(s)


def test_other_net_future_bridge_and_large_land_survive():
    s=fixture();s['corridors'] += [dict(net='FUTURE',layer='B.Cu',x0=30,y0=30,x1=35,y1=35)]
    # Its centre is outside the old rectangle but its large land reaches it.
    s['vias']=[dict(net='BUS',x_mm=11,y_mm=4,diameter_mm=2.4)]
    assert all(r in geometry.reservations(s) for r in s['corridors'])
    s['vias'][0]['x_mm']=20
    rows=geometry.reservations(s)
    assert s['corridors'][0] not in rows and s['corridors'][1] in rows


def test_projection_is_deterministic_detached_and_json_reload_safe():
    s=fixture();a=geometry.reservations(s);b=geometry.reservations(json.loads(json.dumps(s)))
    assert a==b
    a[0]['x0']=999
    assert geometry.reservations(s)==b
