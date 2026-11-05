"""Offset reverse callouts retain the real outline/leader and readable floors."""
import copy
import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union
import cec_dense_reference_mapping as maps
import cec_field_coupling as field
from test_dense_reference_mapping import fixture


@pytest.mark.parametrize('face',[pcbnew.F_SilkS,pcbnew.B_SilkS])
@pytest.mark.parametrize('quarter',range(4))
def test_finite_fractional_periphery_escapes_blocked_old_five_centers(face,quarter):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNIQUE_42');board.Add(fp)
    shape=affinity.rotate(box(9,9.5,11,10.5),90*quarter,origin=(10,10))
    f=dict(height=1.,stroke=.15,clearance=.15,edge=.2)
    obstacles=[];x0,y0,x1,y1=shape.bounds;gap=f['clearance']+f['stroke']+.03
    for angle in (0,90):
        glyph=maps.polygon(maps.make_text(board,fp.GetReference(),(10,10),face,1.,.15,angle),face)
        a,b,c,d=glyph.bounds;hx,hy=(c-a)/2,(d-b)/2
        for x,y in ((10,10),(10,y0-gap-hy),(x1+gap+hx,10),
                (10,y1+gap+hy),(x0-gap-hx,10)):
            obstacles.append(box(x-.005,y-.005,x+.005,y+.005))
    blocked=unary_union(obstacles);material=box(0,0,30,30);before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError,match='no_readable_clear_projected'):
        maps.reverse_component(board,(fp,shape),face,f,blocked,material,box(0,0,0,0))
    items,ink,rows=maps.reverse_component(board,(fp,shape),face,f,blocked,material,
        box(0,0,0,0),peripheral_seats=True)
    assert material.covers(ink)and not ink.intersects(blocked)
    assert rows[0]['courtyard_xy_mm']==[list(p)for p in shape.exterior.coords]
    assert rows[0]['text_mirrored']is (face==pcbnew.B_SilkS)
    text=next(i for i in items if i.GetClass()=='PCB_TEXT')
    assert text.GetTextThickness()==150000 and text.GetTextSize().y==1000000
    assert field._field_snapshot_inventory(board)==before
    with pytest.raises(ValueError,match='no_readable_clear_projected'):
        maps.reverse_component(board,(fp,shape),face,f,material,material,
            box(0,0,0,0),peripheral_seats=True)


@pytest.mark.parametrize('back',[False,True])
def test_explicit_menu_flag_survives_full_saved_reconstruction_and_cannot_be_forged(tmp_path,back):
    source,grade,uid=fixture(tmp_path,back=back);before=source.read_bytes()
    old=maps.plan(source,grade=grade,board_hint='synthetic',maximum_components=1)
    assert 'peripheral_reverse_seats'not in old
    q=maps.plan(source,grade=grade,board_hint='synthetic',maximum_components=1,
        owner_uuid_scope=[uid],peripheral_reverse_seats=True,
        reverse_ownership='rigid_root_group_per_component')
    child=maps.force._copy_family(source,tmp_path/'peripheral');maps.write_private(source,child,q)
    r=maps.receive(source,child,q)
    assert r['ok']and r['complete']and not r['release_authority'],r
    assert source.read_bytes()==before
    forged=copy.deepcopy(q);forged['peripheral_reverse_seats']='yes'
    with pytest.raises(ValueError,match='explicit_finite_reverse_reference_periphery'):
        maps.construct(source,forged)
