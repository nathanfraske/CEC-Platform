import math
import pytest
from cec_stack_fit_screen import vertical_screen, contact_registration


def parameters():
    # Deliberate test fixture, not a supplier qualification claim.
    return dict(gap=(21.5,22.5),cap_height=(16,17),cap_seating=(0,.2),vent_min=3,
        header_reach=(18.288-.3032,18.288+.3032),socket_height=(8.409,8.609),
        header_seating=(0,.1),socket_seating=(0,.1),insertion_limits=(3.68,6.35))


def test_interval_extrema_and_nominal_not_release():
    r=vertical_screen(**parameters())
    assert r["ok"] and not r["release_accepted"]
    assert r["vent"]["clearance_mm"][0] == pytest.approx(4.3)
    assert r["engagement"]["insertion_mm"] == pytest.approx([3.8938,5.9002])


def test_old_gap_fails_vent_and_maximum_insertion():
    r=vertical_screen(**dict(parameters(),gap=(18,18)))
    assert not r["vent"]["ok"] and not r["engagement"]["ok"]


def test_too_tall_gap_fails_minimum_insertion():
    r=vertical_screen(**dict(parameters(),gap=(24,24)))
    assert r["vent"]["ok"] and not r["engagement"]["ok"]


def test_unknown_reference_dimension_is_not_zero_tolerance():
    r=vertical_screen(**dict(parameters(),socket_height=None))
    assert not r["complete"] and not r["ok"] and "engagement" not in r


@pytest.mark.parametrize("value",[(1,-1),(math.nan,2),(0,math.inf)])
def test_invalid_intervals(value):
    with pytest.raises(ValueError):vertical_screen(**dict(parameters(),gap=value))


def contacts():
    return [dict(id=str(i),xy=p,role=r) for i,p,r in
        [(1,(0,0),"power"),(2,(0,-2.54),"ground"),(3,(2.54,0),"data")]]


def test_aligned_origin_does_not_imply_mating():
    r=contact_registration(contacts(),contacts(),[-1,0,0,1,0,0])
    assert not r["ok"] and r["mismatched"]==1


def test_true_mirror_and_translation_pass():
    cover=[dict(p,xy=(10-p["xy"][0],p["xy"][1]-5)) for p in contacts()]
    assert contact_registration(contacts(),cover,[-1,0,0,1,10,5])["ok"]


def test_geometric_mate_wrong_role_fails():
    changed=contacts();changed[0]["role"]="ground"
    assert not contact_registration(contacts(),changed,[1,0,0,1,0,0])["ok"]


def test_duplicate_contacts_rejected():
    with pytest.raises(ValueError):contact_registration(contacts(),contacts()*2,[1,0,0,1,0,0])


def test_scale_cannot_fake_mating():
    with pytest.raises(ValueError):contact_registration(contacts(),contacts(),[2,0,0,1,0,0])


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('axis',['x','y'])
def test_full_contact_field_rotations_and_handedness(angle,axis):
    from cec_stack_fit_screen import posed_contacts,mating_rotation
    rows=contacts()
    socket=[dict(r,xy=[-r['xy'][0] if axis=='x' else r['xy'][0],
                       -r['xy'][1] if axis=='y' else r['xy'][1]]) for r in rows]
    a=posed_contacts(rows,(13,9),angle)
    b=posed_contacts(socket,(27,4),mating_rotation(angle,assembly_mirror_x=True,footprint_mirror_axis=axis))
    assert contact_registration(a,b,[-1,0,0,1,40,5])['ok']


def test_flip_without_declared_footprint_handedness_refuses():
    from cec_stack_fit_screen import mating_rotation
    with pytest.raises(ValueError):mating_rotation(90,assembly_mirror_x=True)


def test_contact_pass_cannot_qualify_whole_stack():
    from cec_stack_fit_screen import qualify_stack
    r=qualify_stack({'contacts':{'ok':True,'qualified':True,'evidence':'native hash-bound replay'}},['contacts','vent','hardware','sample'])
    assert not r['release_accepted']
    assert [b['requirement'] for b in r['blockers']]==['vent','hardware','sample']


def test_nominal_or_unsourced_pass_cannot_qualify():
    from cec_stack_fit_screen import qualify_stack
    for row in ({'ok':True},{'ok':True,'qualified':True},{'ok':True,'evidence':'nominal study'}):
        assert not qualify_stack({'height':row},['height'])['release_accepted']
