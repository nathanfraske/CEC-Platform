import pytest
import cec_swig_guard; cec_swig_guard.pin()
import pcbnew
import cec_native_placement_context as context
import cec_field_coupling as field


def fixture(tmp_path, *, pad_layer=pcbnew.F_Cu, old_y=4, new_y=0):
    source=pcbnew.BOARD()
    source.SetCopperLayerCount(2)
    for name in ('rail','GND'):
        source.Add(pcbnew.NETINFO_ITEM(source,name))
    fp=pcbnew.FOOTPRINT(source);fp.SetReference('CELL_A');source.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('SUPPLY');pad.SetSize(pcbnew.VECTOR2I(1000000,1000000))
    pad.SetPosition(pcbnew.VECTOR2I(0,old_y*1000000));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(pad_layer)
    pad.SetLayerSet(layers);pad.SetNetCode(source.GetNetcodeFromNetname('rail'));fp.Add(pad)
    t=pcbnew.PCB_TRACK(source);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(source.GetNetcodeFromNetname('GND'))
    t.SetWidth(300000);t.SetStart(pcbnew.VECTOR2I(-2000000,0));t.SetEnd(pcbnew.VECTOR2I(2000000,0));source.Add(t)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(source,path)
    candidate=pcbnew.LoadBoard(str(path))
    next(p for f in candidate.GetFootprints() for p in f.Pads()).SetPosition(pcbnew.VECTOR2I(0,new_y*1000000))
    return source,candidate,str(t.m_Uuid.AsString())


def test_new_native_contact_is_logged_without_mutation_or_eviction(tmp_path):
    source,child,uid=fixture(tmp_path);before=field._field_snapshot_inventory(child)
    r=context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A'],track_uuids=[uid])
    assert len(r['new_contacts'])==1 and r['new_contacts'][0]['foreign_net']=='rail'
    assert r['new_contacts'][0]['layers']==[int(pcbnew.F_Cu)]
    assert not r['new_contacts'][0]['automatic_ripup_authorized'] and not r['release_authority']
    assert field._field_snapshot_inventory(child)==before


def test_inherited_contact_is_not_new_or_legality_permission(tmp_path):
    source,child,uid=fixture(tmp_path)
    # Introduce synthetic inherited debt only in memory; a shorted source
    # need not pass the separate, strict serialization/admission boundary.
    next(p for f in source.GetFootprints() for p in f.Pads()).SetPosition(pcbnew.VECTOR2I(0,0))
    r=context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A'],track_uuids=[uid])
    assert not r['new_contacts'] and len(r['inherited_contacts'])==1
    assert not r['clearance_qualified']


def test_opposite_surface_pad_does_not_short_front_copper(tmp_path):
    source,child,uid=fixture(tmp_path,pad_layer=pcbnew.B_Cu)
    assert not context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A'],track_uuids=[uid])['contacts']


def test_relabelled_net_cannot_hide_relocation_failure(tmp_path):
    source,child,uid=fixture(tmp_path)
    next(p for f in child.GetFootprints() for p in f.Pads()).SetNetCode(child.GetNetcodeFromNetname('GND'))
    with pytest.raises(ValueError,match='pad_identity'):
        context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A'],track_uuids=[uid])


def test_stale_native_item_refuses(tmp_path):
    source,child,uid=fixture(tmp_path)
    with pytest.raises(ValueError,match='stale_scope'):
        context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A'],track_uuids=['missing'])


def test_duplicate_scope_refuses(tmp_path):
    source,child,uid=fixture(tmp_path)
    with pytest.raises(ValueError,match='unique_explicit_scope'):
        context.new_foreign_pad_contacts(source,child,footprint_refs=['CELL_A','CELL_A'],track_uuids=[uid])
