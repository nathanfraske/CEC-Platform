"""Saved project geometry wins over ambient native defaults, never a load."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_field_coupling as field
from cec_route_dimensions import DimensionContractError


def source(tmp_path,*,width=.5):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    b.GetDesignSettings().m_TrackMinWidth=200000
    b.GetDesignSettings().m_MinClearance=200000
    b.GetDesignSettings().m_ViasMinSize=500000
    b.GetDesignSettings().m_MinThroughDrill=300000
    b.GetDesignSettings().m_ViasMinAnnularWidth=100000
    for net in('arbitrary_supply','/sheet/other_control','unknown'):
        b.Add(pcbnew.NETINFO_ITEM(b,net))
    path=tmp_path/'exact-source.kicad_pcb';field._save_field_snapshot(b,path)
    settings=dict(classes=[dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='conserved_source',track_width=width,clearance=.27,via_diameter=.8,via_drill=.4)],
        netclass_assignments={'arbitrary_supply':'conserved_source'},
        netclass_patterns=[dict(netclass='conserved_source',pattern='/other_control')])
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=settings)))
    return path,pcbnew.LoadBoard(str(path)),settings


@pytest.mark.parametrize('net',['arbitrary_supply','/sheet/other_control'])
def test_exact_assignments_and_hierarchy_patterns_not_native_default_own_local_dimensions(tmp_path,net):
    path,b,settings=source(tmp_path);raw=path.read_bytes();project=path.with_suffix('.kicad_pro').read_bytes()
    got=cells._netclass(b,net)
    assert got==dict(width=500000,clearance=270000,via_dia=.8,via_drill=.4)
    assert path.read_bytes()==raw and path.with_suffix('.kicad_pro').read_bytes()==project
    assert cells._netclass(b,'unknown')==dict(width=200000,clearance=200000,via_dia=.6,via_drill=.3)


def test_byte_key_cache_does_not_reuse_changed_same_path_project(tmp_path):
    path,b,settings=source(tmp_path)
    assert cells._netclass(b,'arbitrary_supply')['width']==500000
    settings['classes'][1]['track_width']=.75
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=settings)))
    assert cells._netclass(b,'arbitrary_supply')['width']==750000
    assert cells._literal_netclass_table.cache_info().maxsize==32


def test_manufacturing_floors_are_retained_without_using_native_class(tmp_path):
    path,b,settings=source(tmp_path,width=.1)
    # This minimal synthetic sidecar declares net classes only; install the
    # actual live native clearance floor we intend to exercise, not a floor
    # from the pre-save instance that LoadBoard never attached as a project.
    b.GetDesignSettings().m_MinClearance=200000
    settings['classes'][1].update(clearance=.1,via_diameter=.3,via_drill=.1)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=settings)))
    assert cells._netclass(b,'arbitrary_supply')==dict(width=200000,clearance=200000,via_dia=.5,via_drill=.3)


@pytest.mark.parametrize('bad',[True,False,None,-.1,float('nan'),float('inf'),'0.5'])
@pytest.mark.parametrize('key',['track_width','clearance','via_diameter','via_drill'])
def test_invalid_authored_dimension_never_falls_back_to_ambient_default(tmp_path,bad,key):
    path,b,settings=source(tmp_path);settings['classes'][1][key]=bad
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=settings)))
    with pytest.raises((DimensionContractError,TypeError,ValueError)):
        cells._netclass(b,'arbitrary_supply')


@pytest.mark.parametrize('payload',['{}','{','{"net_settings": null}','{"net_settings": {"classes": []}}'])
def test_unreadable_or_empty_exact_source_is_not_an_ordinary_geometry_grant(tmp_path,payload):
    path,b,settings=source(tmp_path);path.with_suffix('.kicad_pro').write_text(payload)
    with pytest.raises(DimensionContractError):cells._netclass(b,'arbitrary_supply')


def test_unrelated_project_is_not_selected_for_a_missing_exact_sibling(tmp_path):
    path,b,settings=source(tmp_path);exact=path.with_suffix('.kicad_pro')
    unrelated=tmp_path/'unrelated.kicad_pro';unrelated.write_bytes(exact.read_bytes());exact.unlink()
    # In-memory/legacy geometry still has its old native fallback. Missing
    # actual Source never authorizes a current role or another project's .5.
    got=cells._netclass(b,'arbitrary_supply')
    assert got['width']!=500000
