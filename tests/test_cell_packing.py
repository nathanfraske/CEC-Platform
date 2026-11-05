"""Synthetic cooperative packing, independent of any product or refdes."""
import sys
from pathlib import Path

import pytest
from shapely.geometry import box
from shapely.affinity import translate
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_cell_packing as packing


def test_existing_legal_group_is_unchanged():
    result = packing.negotiate_translation(box(2, 4, 8, 8), bounds=(0, 0, 20, 20),
        axis=1, reserve=lambda delta, shape: {"seat": [11, 10]})
    assert result["ok"] and not result["applied"]
    assert result["trials"] == 1


@pytest.mark.parametrize("axis", [0, 1])
def test_future_macro_drives_complete_group_translation(axis):
    group = box(4, 4, 12, 12)
    future = box(9, 9, 16, 16)
    result = packing.negotiate_translation(group, bounds=(0, 0, 20, 20),
        axis=axis, reserve=lambda delta, shape: (
            {"group": "future-macro"} if shape.distance(future) >= .3 else None))
    assert result["ok"] and result["applied"]
    delta = result["translation_mm"]
    assert delta[axis] == -4. and delta[1-axis] == 0.
    assert translate(group, xoff=delta[0], yoff=delta[1]).area == group.area


def test_clearance_and_outline_are_hard_before_reservation():
    seen = []
    group = box(1, 1, 3, 3)
    obstacle = box(.8, 3.1, 3.2, 4)
    result = packing.negotiate_translation(group, bounds=(.5, .5, 4, 5), axis=1,
        fixed=[obstacle], max_trials=5,
        reserve=lambda delta, shape: seen.append(delta))
    assert not result["ok"] and not seen
    assert result["trials"] == 5
    assert result["rejections"]["fixed_obstacle"] > 0
    assert result["rejections"]["bounds"] > 0


def test_exhausted_search_does_not_claim_geometric_impossibility():
    result = packing.negotiate_translation(box(50, 50, 51, 51),
        bounds=(0, 0, 100, 100), axis=0, max_trials=1000000,
        reserve=lambda delta, shape: None)
    assert result["trials"] == packing.MAX_TRANSLATION_TRIALS
    assert result["reason"] == "bounded_search_exhausted"
    assert not result["ok"]


def test_actual_copper_width_and_via_edges_are_in_envelope():
    shape = packing.rigid_envelope(courtyard_boxes=[(0, 0, 1, 1)],
        tracks=[{"start_mm": (1, 1), "end_mm": (5, 1), "width_mm": 2}],
        vias=[{"at_mm": (4, 5), "dia_mm": 2}])
    assert shape.bounds[2] >= 6 and shape.bounds[3] >= 6
    result = packing.negotiate_translation(shape, bounds=(0, 0, 5.9, 6.1),
        axis=1, max_trials=1, reserve=lambda *_: {"must_not": "fit"})
    assert result["rejections"]["bounds"] == 1


@pytest.mark.parametrize("options", [{"step_mm": 0}, {"clearance": -1},
                                    {"axis": 3}, {"bounds": (0, 0, 0, 5)}])
def test_bad_geometry_policy_fails_closed(options):
    args = dict(bounds=(0, 0, 10, 10), axis=1, reserve=lambda *_: None)
    args.update(options)
    with pytest.raises(ValueError):
        packing.negotiate_translation(box(1, 1, 2, 2), **args)


def test_contact_sites_clear_every_macro_member_and_obstacle():
    parts = [(-1., -1., 1., 1.), (2., -.5, 3., .5)]
    obstacles = [(0., 0., 10., 2.), (0., 4.9, 10., 10.)]
    options = dict(bounds=(1., 1., 7., 9.), obstacles=obstacles, clearance=.3)
    sites = packing.contact_translation_sites(parts, **options)
    assert sites and sites == packing.contact_translation_sites(parts, **options)
    for x, y in sites:
        for px0, py0, px1, py1 in parts:
            for ox0, oy0, ox1, oy1 in obstacles:
                assert (x+px1+.3 <= ox0 or ox1+.3 <= x+px0
                        or y+py1+.3 <= oy0 or oy1+.3 <= y+py0)


def test_contact_search_never_drops_obstacles_to_meet_its_budget():
    args = dict(bounds=(1., 1., 10., 10.), obstacles=[(0., 0., 20., 20.)])
    assert not packing.contact_translation_sites([(-1., -1., 1., 1.)], **args)
    assert not packing.contact_translation_sites([(-1., -1., 1., 1.)],
        bounds=(1., 1., 10., 10.), obstacles=[(0., 0., 2., 2.)], max_exclusions=0)
    with pytest.raises(ValueError):
        packing.contact_translation_sites([(0., 0., float('nan'), 1.)], **args)


def test_native_oracle_and_json_sites_backtrack_without_weakening_geometry():
    seen=[]
    groups={'arbitrary-cell':dict(members=[box(0,0,1,1)],bounds=(0,0,4,0),
                                  preferred=(0,0),sites=[[2.,0.],[2.,0.]])}
    # Contact-space boundaries are not the only native legal sites. Supplemental
    # JSON points share the same fixed/member clearance and bounded search.
    result=packing.pack_translations(groups,[],max_nodes=8,
        accept_translation=lambda key,delta: seen.append((key,delta)) or delta==(2.,0.))
    assert result['ok'] and result['translations']=={'arbitrary-cell':[2.,0.]}
    assert seen[0][1]==(0.,0.) and len(seen)<=8
    assert not result['admission_authority']


def test_native_oracle_is_never_called_for_a_geometrically_blocked_site():
    seen=[]
    groups={'cell':dict(members=[box(0,0,1,1)],bounds=(0,0,0,0),sites=[[0.,0.]])}
    result=packing.pack_translations(groups,[box(0,0,1,1)],
        accept_translation=lambda *args: seen.append(args) or True)
    assert not result['ok'] and not seen


@pytest.mark.parametrize('reply',[None,1,{'ok':True}])
def test_native_oracle_unknown_or_truthy_non_boolean_is_not_admission(reply):
    groups={'cell':dict(members=[box(0,0,1,1)],bounds=(0,0,0,0))}
    with pytest.raises(ValueError,match='explicit bool'):
        packing.pack_translations(groups,[],accept_translation=lambda *_:reply)


def test_supplemental_sites_do_not_escape_declared_bounds_or_node_budget():
    groups={'cell':dict(members=[box(0,0,1,1)],bounds=(0,0,4,0),
                        sites=[[100.,0.],[2.,0.],[3.,0.]])}
    seen=[]
    result=packing.pack_translations(groups,[],max_nodes=1,
        accept_translation=lambda key,delta:seen.append(delta) or False)
    assert not result['ok'] and result['exhausted'] and result['nodes']==1
    assert seen==[(0.,0.)]


@pytest.mark.parametrize('sites',[[[float('nan'),0.]],[[0.,0.]]*257,[[0.]]])
def test_bad_supplemental_sites_fail_closed(sites):
    groups={'cell':dict(members=[box(0,0,1,1)],bounds=(0,0,4,0),sites=sites)}
    with pytest.raises(ValueError,match='supplemental'):
        packing.pack_translations(groups,[])
