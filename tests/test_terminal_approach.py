"""Joint forward-access proposal regressions, not electrical-route waivers."""
import copy
import math

import pytest

import cec_terminal_range as search
from cec_cell_packing import contact_translation_sites
from cec_translation_halfplanes import normalized, contains, clip_rectangle
from cec_placement_search_domain import rotate_board_point
from test_terminal_range import native_fixture, geometry


@pytest.mark.parametrize('planes', [((1,0,2),(0,1,2)), ((1,1,3),),
                                   ((1,0,4),(-1,0,-4))])
def test_disc_line_and_line_line_witnesses(planes):
    sites=search.translation_sites([(2,0),(2,2)],4,halfplanes=planes)
    assert sites
    assert all(contains(p,normalized(planes)) for p in sites)
    assert all(math.dist(p,c)<=4+1e-8 for p in sites for c in [(2,0),(2,2)])


def test_empty_directional_domain_does_not_ignore_constraints():
    assert search.translation_sites([(0,0)],2,halfplanes=[(1,0,3)])==[]
    assert clip_rectangle((-1,-1,1,1),normalized([(1,0,2)]))==[]


@pytest.mark.parametrize('plane', [(0,0,1),(float('nan'),1,0),(1,0,float('inf')),(1,2)])
def test_bad_directional_geometry_is_not_silently_dropped(plane):
    with pytest.raises(ValueError):search.translation_sites([(0,0)],2,halfplanes=[plane])
    with pytest.raises(ValueError):contact_translation_sites([(-.1,-.1,.1,.1)],
        bounds=(-5,-5,5,5),translation_halfplanes=[plane])


def test_native_cavity_sampler_applies_both_reach_and_direction_before_truncation():
    sites=contact_translation_sites([(-.1,-.1,.1,.1)],bounds=(-5,-5,5,5),
        obstacles=[(1,-5,1.5,5)],clearance=.1,preferred_origin=(0,0),max_sites=1,
        reach_discs=[((0,0),4)],translation_halfplanes=[(1,0,2),(0,1,1)])
    assert len(sites)==1
    assert sites[0]==pytest.approx((2,1))


@pytest.mark.parametrize('angle',[0,31,90,180,270])
def test_joint_direction_moves_all_pins_and_preserves_cell(angle):
    poses,pairs=geometry(angle,(123,-45))
    direction=rotate_board_point((1,0),(0,0),angle)
    for pair in pairs:
        pair['approach']=dict(origin=pair['source'],normal=direction,min_mm=2)
    original=copy.deepcopy((poses,pairs))
    moves=search.joint_cell_proposals(poses,'owner',pairs,
        max_distance_mm=9,max_translation_mm=40)
    assert moves
    assert all(min(m['approach_slacks_mm'])>=-1e-8 for m in moves)
    assert (poses,pairs)==original
    def hostile_provider(*args,**kwargs):return [(0,0),(-20,0),(1000,1000)]
    moves=search.joint_cell_proposals(poses,'owner',pairs,
        max_distance_mm=9,max_translation_mm=40,site_provider=hostile_provider)
    assert all(min(m['approach_slacks_mm'])>=-1e-8 for m in moves)


def measured_fixture(tmp_path,flipped=False):
    import pcbnew,cec_fr
    source,board,candidate,_,details=native_fixture(tmp_path,flipped)
    owner=board.FindFootprintByReference('owner')
    owner.SetOrientationDegrees((owner.GetOrientationDegrees()+180)%360)
    pcbnew.SaveBoard(str(source),board,True);board=pcbnew.LoadBoard(str(source))
    owner=board.FindFootprintByReference('owner')
    candidate.P['owner']=(owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,
                          owner.GetOrientationDegrees())
    pads=list(board.FindFootprintByReference('anchor').Pads())
    pad=next(p for p in pads if p.GetNetname()=='renamed_a')
    other=next(p for p in pads if p.GetNetname()=='renamed_b')
    target=next(p for p in owner.Pads() if p.GetNumber()=='7')
    size=pad.GetSize();reach=math.hypot(size.x/1e6,size.y/1e6)/2
    tx,ty,nx,ny=cec_fr._inner_edge_pt(pad,other.GetPosition(),inset_mm=min(.12,reach*.25))
    point=lambda p:(p.GetPosition().x/1e6,p.GetPosition().y/1e6)
    target_pos=point(target)
    row=dict(net='renamed_a',source_ref='anchor',target_ref='owner',target_pad='7',
        source_position_mm=point(pad),target_position_mm=target_pos,
        tap_start_position_mm=(tx,ty),inward_vector=(nx,ny),
        target_inward_mm=(target_pos[0]-tx)*nx+(target_pos[1]-ty)*ny,
        canonical_min_inward_mm=.3,max_distance_mm=25,required_closer_mm=0)
    assert row['target_inward_mm']<.3
    return source,board,candidate,[row],details


@pytest.mark.parametrize('flipped',[False,True])
@pytest.mark.parametrize('cavities',[False,True])
def test_loaded_in_range_wrong_launch_moves_both_inputs_not_one(tmp_path,flipped,cavities):
    import pcbnew
    source,board,candidate,rows,details=measured_fixture(tmp_path,flipped)
    before=source.read_bytes();before_poses=dict(candidate.P)
    moves=search.from_native_relations(board,candidate,rows,details,{'owner':['bypass']},
        max_translation_mm=30,use_cavities=cavities)
    assert moves
    for move in moves:
        assert move['approach_proposal_only'] and len(move['approach_slacks_mm'])==2
        assert min(move['approach_slacks_mm'])>=-1e-8
        assert set(move['placements'])=={'owner','bypass'}
        trial=pcbnew.LoadBoard(str(source))
        for ref,(x,y,angle) in move['placements'].items():
            fp=trial.FindFootprintByReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.SetOrientationDegrees(angle)
        path=tmp_path/'trial.kicad_pcb';pcbnew.SaveBoard(str(path),trial,True)
        trial=pcbnew.LoadBoard(str(path))
        for pair in move['terminal_correspondences']:
            target=next(p for p in trial.FindFootprintByReference('owner').Pads()
                        if p.GetNetname()==pair['net'])
            actual=(target.GetPosition().x/1e6,target.GetPosition().y/1e6)
            rule=pair['approach']
            inward=sum((actual[i]-rule['origin'][i])*rule['normal'][i] for i in (0,1))
            assert inward>=rule['min_mm']-3e-6
    assert source.read_bytes()==before and candidate.P==before_poses


@pytest.mark.parametrize('field,value',[('inward_vector',(1,0)),('target_inward_mm',-9),
    ('source_position_mm',(0,0)),('tap_start_position_mm',(0,0)),
    ('target_position_mm',(0,0)),('target_pad','99'),('net','not_the_net'),
    ('canonical_min_inward_mm',float('nan')),('canonical_min_inward_mm',-.3),
    ('target_inward_mm','invalid'),('inward_vector',(float('nan'),1))])
def test_measured_certificate_must_bind_to_live_native_pads(tmp_path,field,value):
    _,board,candidate,rows,details=measured_fixture(tmp_path)
    rows[0][field]=value
    assert search.from_native_relations(board,candidate,rows,details,{},max_translation_mm=30)==[]


def test_new_primitive_is_in_protected_generic_core():
    import cec_generalization_gate as gate,cec_translation_halfplanes as halfplanes
    assert 'scripts/cec_translation_halfplanes.py' in gate.GENERIC_ENGINE_MODULES
    assert not gate.audit_file(halfplanes.__file__)
