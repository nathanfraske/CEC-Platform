"""An exact current schematic marker, not a lonely net or name, owns NC."""
from pathlib import Path

import pcbnew
import pytest
import cec_source_no_connect as nc
import cec_force_current as force
import cec_cell_row_rebuild as row


def fixture(tmp_path,*,name='arbitrary_alias',quarter=0):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_owner');fp.SetValue('TLV7011DBVR')
    fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'));fp.SetField('MPN','TLV7011DBVR');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('3');pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));fp.Add(pad)
    source=tmp_path/'source.kicad_pcb';board.SetFileName(str(source));pcbnew.SaveBoard(str(source),board)
    angle=quarter*90
    delta=[(1,0),(0,-1),(-1,0),(0,1)][quarter];at=(10+delta[0],10+delta[1])
    symbol='''(symbol (lib_id "fixture:IC") (at 10 10 ANGLE) (unit 1)
      (uuid "d8b65464-5f7c-4ce2-8d0e-f5be83c50d70")
      (property "Reference" "arbitrary_owner") (property "Value" "TLV7011DBVR")
      (property "Footprint" "Package_TO_SOT_SMD:SOT-23-5")
      (property "MPN" "TLV7011DBVR"))'''.replace('ANGLE',str(angle))
    marker=f'(no_connect (at {at[0]} {at[1]}) (uuid "81c410bb-9531-4d95-bb14-0f81a799916b"))'
    library='''(lib_symbols (symbol "fixture:IC" (symbol "IC_1_1"
      (pin input line (at 1 0 0) (length 1.27)
        (name "opaque_input") (number "3")))))'''
    schematic=tmp_path/'current.kicad_sch'
    schematic.write_text('(kicad_sch (version 20250114) '+library+' '+symbol+' '+marker+')')
    return board,source,fp,pad,schematic,symbol,marker,at


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['arbitrary_alias','unconnected-looking-but-not-authority'])
def test_exact_current_cardinal_schematic_marker_and_isolated_land_are_read_only(tmp_path,quarter,name):
    board,source,fp,pad,sch,*_=fixture(tmp_path,name=name,quarter=quarter)
    before=row._source_binding(board);raw=[p.read_bytes() for p in (source,sch)]
    proof=nc.plan(board,force._uid(pad),board_hint=str(sch))
    assert proof['unchanged_no_connect_not_a_routing_failure']
    assert proof['schematic_files_sha256']=={str(sch):force._hash(sch)}
    assert proof['pad_uuid']==force._uid(pad)
    assert not proof['manufacturer_electrical_use_qualified'] and not proof['release_authority']
    assert before==row._source_binding(board) and raw==[p.read_bytes() for p in (source,sch)]


@pytest.mark.parametrize('fault',['missing_marker','near_marker','other_pin_number','missing_symbol'])
def test_one_terminal_or_unconnected_name_without_exact_pin_marker_grants_no_exemption(tmp_path,fault):
    board,source,fp,pad,sch,symbol,marker,at=fixture(tmp_path,name='unconnected-(arbitrary_owner-Pad3)')
    text=sch.read_text()
    if fault=='missing_marker':text=text.replace(marker,'')
    elif fault=='near_marker':text=text.replace(marker,marker.replace(f'at {at[0]} {at[1]}',f'at {at[0]+.00001} {at[1]}'))
    elif fault=='other_pin_number':text=text.replace('(number "3")','(number "4")')
    else:text=text.replace(symbol,'')
    sch.write_text(text);before=row._source_binding(board)
    if fault=='other_pin_number':
        with pytest.raises(ValueError):nc.plan(board,force._uid(pad),board_hint=str(sch))
    else:assert nc.plan(board,force._uid(pad),board_hint=str(sch)) is None
    assert before==row._source_binding(board)


@pytest.mark.parametrize('fault',['MPN','Value','Footprint','wire_endpoint','wire_middle','label',
    'junction','duplicate_marker','duplicate_symbol','mirror'])
def test_contradictory_schematic_or_contacted_marker_is_not_intent_authority(tmp_path,fault):
    board,source,fp,pad,sch,symbol,marker,at=fixture(tmp_path)
    text=sch.read_text()
    if fault in ('MPN','Value','Footprint'):
        value={'MPN':'TLV7011DBVR','Value':'TLV7011DBVR','Footprint':'Package_TO_SOT_SMD:SOT-23-5'}[fault]
        text=text.replace(f'(property "{fault}" "{value}")',f'(property "{fault}" "wrong_component")')
    elif fault=='mirror':text=text.replace('(unit 1)','(unit 1) (mirror x)')
    elif fault=='duplicate_symbol':text=text[:-1]+' '+symbol+')'
    else:
        insert={'wire_endpoint':'(wire (pts (xy 11 10) (xy 13 10)))',
            'wire_middle':'(wire (pts (xy 9 10) (xy 13 10)))',
            'label':'(label "not_unused" (at 11 10 0))',
            'junction':'(junction (at 11 10) (uuid "ab760953-e023-4ce8-8046-caa2d31d8c34"))',
            'duplicate_marker':marker}[fault]
        text=text[:-1]+' '+insert+')'
    sch.write_text(text);before=row._source_binding(board)
    with pytest.raises(ValueError):nc.plan(board,force._uid(pad),board_hint=str(sch))
    assert before==row._source_binding(board)


@pytest.mark.parametrize('fault',['other_land','native_track','zone'])
def test_native_same_net_material_cannot_be_ignored_by_a_schematic_marker(tmp_path,fault):
    board,source,fp,pad,sch,*_=fixture(tmp_path)
    if fault=='other_land':
        p=pcbnew.PAD(fp);p.SetNumber('4');p.SetNetCode(pad.GetNetCode());fp.Add(p)
    elif fault=='native_track':
        t=pcbnew.PCB_TRACK(board);t.SetNetCode(pad.GetNetCode());t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));board.Add(t)
    else:
        z=pcbnew.ZONE(board);z.SetNet(board.FindNet(pad.GetNetname()));z.SetLayer(pcbnew.F_Cu)
        z.Outline().NewOutline()
        for x,y in ((1,1),(2,1),(2,2),(1,2)):z.Outline().Append(x*1000000,y*1000000)
        board.Add(z)
    assert nc.plan(board,force._uid(pad),board_hint=str(sch)) is None


def test_hierarchy_is_followed_from_explicit_root_and_each_file_is_bound(tmp_path):
    board,source,fp,pad,leaf,*_=fixture(tmp_path)
    root=tmp_path/'root.kicad_sch'
    root.write_text('(kicad_sch (sheet (at 10 10) (size 10 10) '
        '(property "Sheetfile" "current.kicad_sch")))')
    proof=nc.plan(board,force._uid(pad),board_hint=str(root))
    assert set(proof['schematic_files_sha256'])=={str(root),str(leaf)}
    assert proof['root_schematic']==str(root) and proof['schematic']==str(leaf)
    leaf.write_text(leaf.read_text().replace('(no_connect','(not_a_no_connect'))
    assert nc.bindings_current([proof]) is False
    assert nc.plan(board,force._uid(pad),board_hint=str(root)) is None


def test_current_manifest_root_cannot_be_replaced_by_an_older_sibling_sheet(tmp_path,monkeypatch):
    board,source,fp,pad,old,*_=fixture(tmp_path)
    project=tmp_path/'beta'/'opaque_project';project.mkdir(parents=True)
    old.rename(project/'000-old-flat.kicad_sch')
    current=project/'declared-current.kicad_sch';current.write_text('(kicad_sch)')
    monkeypatch.setattr(nc.policy,'ROOT',str(tmp_path))
    monkeypatch.setattr(nc.policy,'policy_path',lambda *a,**kw:str(project/'pipeline-policy.json'))
    monkeypatch.setattr(nc.manifest,'PROJECTS',({'board':'opaque','directory':'opaque_project',
        'schematic':'declared-current.kicad_sch'},))
    assert nc._root(board,'opaque')==current
    assert nc.plan(board,force._uid(pad),board_hint='opaque') is None
    current.unlink()
    with pytest.raises(ValueError,match='current_manifest'):
        nc.plan(board,force._uid(pad),board_hint='opaque')


@pytest.mark.parametrize('fault',['missing_sheet','cycle','reused_instance'])
def test_missing_or_ambiguous_hierarchical_source_never_falls_back_to_a_leaf(tmp_path,fault):
    board,source,fp,pad,leaf,*_=fixture(tmp_path)
    root=tmp_path/'root.kicad_sch'
    file={'missing_sheet':'missing.kicad_sch','cycle':'root.kicad_sch','reused_instance':'current.kicad_sch'}[fault]
    sheet=f'(sheet (at 10 10) (size 10 10) (property "Sheetfile" "{file}"))'
    root.write_text('(kicad_sch '+sheet+(' '+sheet if fault=='reused_instance' else '')+')')
    with pytest.raises(ValueError):nc.plan(board,force._uid(pad),board_hint=str(root))


@pytest.mark.parametrize('timeout',[0.,True,10.001,float('nan'),float('inf')])
def test_noconn_source_work_is_finite_before_native_or_schematic_reads(timeout):
    with pytest.raises(ValueError):nc.plan(None,'opaque',board_hint='opaque',timeout_s=timeout)
