"""The upstream generic field generator must not reintroduce mask collisions."""
import builtins
import importlib.util
from pathlib import Path
import os
import pcbnew
import pytest


def generator():
    path=Path(__file__).resolve().parents[1]/'scripts/gen-daughterboard-libassets.py'
    spec=importlib.util.spec_from_file_location('solder_field_generator_under_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_import_is_read_only_and_cannot_regenerate_unrelated_library_assets(monkeypatch):
    old=builtins.open
    def opened(path,mode='r',*a,**kw):
        assert not any(c in mode for c in('w','a','+','x'))
        return old(path,mode,*a,**kw)
    monkeypatch.setattr(builtins,'open',opened)
    monkeypatch.setattr(os,'makedirs',lambda *a,**kw:pytest.fail('import must not create output directories'))
    assert generator().FIELDS


@pytest.mark.parametrize('index',range(3))
@pytest.mark.parametrize('mask,gap',[(0.,.15),(.05,.2)])
def test_all_field_families_have_closed_native_mask_clear_outline_without_land_or_courtyard_change(tmp_path,index,mask,gap):
    g=generator();name,pads,descr=g.FIELDS[index]
    path=tmp_path/(name+'.kicad_mod');path.write_text(g.solder_field(name,descr,pads,
        mask_expansion_mm=mask,silk_clearance_mm=gap))
    fp=pcbnew.FootprintLoad(str(tmp_path),name);assert fp is not None
    lines=[x for x in fp.GraphicalItems()if x.GetLayer()==pcbnew.F_SilkS]
    assert len(lines)==4 and {x.GetWidth()for x in lines}=={150000}
    assert len({tuple(p)for x in lines for p in(x.GetStart(),x.GetEnd())})==4
    for p in fp.Pads():
        original=next(x for x in pads if x[0]==p.GetNumber())
        assert tuple(p.GetSize())==(round(original[4]*1e6),round(original[5]*1e6))
        assert p.GetDrillSize().x==round(original[3]*1e6)
        poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,pcbnew.F_Cu,round(mask*1e6),1,pcbnew.ERROR_OUTSIDE)
        assert not any(poly.Collide(x.GetEffectiveShape(),round(gap*1e6))for x in lines)
    fab=[x for x in fp.GraphicalItems()if x.GetLayer()==pcbnew.F_Fab]
    assert min(p.y for x in fab for p in(x.GetStart(),x.GetEnd()))==-1850000
    assert max(p.y for x in fab for p in(x.GetStart(),x.GetEnd()))==7350000
    court=next(x for x in fp.GraphicalItems()if x.GetLayer()==pcbnew.F_CrtYd)
    assert court.GetStart().y==-2350000 and court.GetEnd().y==7850000


@pytest.mark.parametrize('value',[True,-.1,float('nan'),float('inf')])
def test_bad_factory_geometry_never_generates_a_looser_frame(value):
    g=generator();name,pads,descr=g.FIELDS[0]
    with pytest.raises(ValueError):g.solder_field(name,descr,pads,silk_clearance_mm=value)


@pytest.mark.parametrize('pads',[[],[None],[('1',0,0,1,0,2,'oval')],
    [('1',float('nan'),0,1,2,2,'oval')],[('1',0,0,True,2,2,'oval')]])
def test_untyped_or_nonphysical_lands_do_not_define_a_silk_envelope(pads):
    g=generator()
    with pytest.raises(ValueError):g.solder_field('arbitrary','fixture',pads)
