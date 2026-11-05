"""A bound outer region is not a waiver or a fake complete larger disc."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_paged_ground_cell_pose_frontier as original
import cec_annular_ground_cell_pose_frontier as annular

def seed(tmp_path,monkeypatch):
    from test_complete_macro_cell import fixture
    source,parent,private,packet=fixture(tmp_path,monkeypatch)
    cap,selected=next(iter(packet['source_plan']['selected_bypasses'].items()));owner=selected['owner']
    return dict(source=str(source),source_sha256=force._hash(source),board_hint='opaque',
        poses={r:[parent.FindFootprintByReference(r).GetPosition().x/1e6,
            parent.FindFootprintByReference(r).GetPosition().y/1e6,
            parent.FindFootprintByReference(r).GetOrientationDegrees()] for r in (cap,owner)},
        source_selected_bypass=dict(ref=owner,pin=selected['pin'],rail=selected['rail']),required_ground_pad_entries=[])

def test_default_annulus_retains_every_original_site_without_global_module_mutation(tmp_path,monkeypatch):
    s=seed(tmp_path,monkeypatch);before=original.prepare
    a=original.prepare(s,radius_mm=2.);b=annular.prepare(s,radius_mm=2.)
    assert a['lattice']==b['lattice'] and a['geometry']==b['geometry']
    assert original.prepare is before and a['identity']!=b['identity']

@pytest.mark.parametrize('inner',[.5,1.,1.5])
def test_annulus_is_literal_disclosed_region_not_lost_inner_prefix(tmp_path,monkeypatch,inner):
    s=seed(tmp_path,monkeypatch);c=annular.prepare(s,radius_mm=2.,minimum_ground_shift_mm=inner)
    parent=c['parent'];gp=next(p for p in parent.FindFootprintByReference(c['cap'].GetReference()).Pads() if p.GetNetname()=='GND')
    origin=tuple(gp.GetPosition());full=original.points(origin,2000000,500000)
    assert c['lattice']==[p for p in full if sum((p[i]-origin[i])**2 for i in (0,1))>round(inner*1e6)**2]
    assert c['settings']['minimum_ground_shift_mm']==inner
    assert str(annular._parent) in c['helpers']

@pytest.mark.parametrize('inner',[True,-.1,2.,3.,float('nan')])
def test_invalid_or_unbounded_annular_region_refuses(tmp_path,monkeypatch,inner):
    s=seed(tmp_path,monkeypatch)
    with pytest.raises(ValueError):annular.prepare(s,radius_mm=2.,minimum_ground_shift_mm=inner)

def test_a_disc_cursor_cannot_be_reused_as_an_outer_region_cursor(tmp_path,monkeypatch):
    s=seed(tmp_path,monkeypatch);disc=original.prepare(s,radius_mm=2.)
    first=original.scan(disc,page_states=1,timeout_s=10.)
    outer=annular.prepare(s,radius_mm=2.,minimum_ground_shift_mm=1.)
    with pytest.raises(ValueError,match='cursor_changed'):
        annular.scan(outer,resume=first['coverage']['continuation'],page_states=1,timeout_s=10.)
