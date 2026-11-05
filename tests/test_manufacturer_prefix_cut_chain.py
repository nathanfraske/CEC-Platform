"""A received native prefix is not arbitrary unowned-metadata permission."""
from unittest.mock import patch
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_manufacturer_land_pattern as pattern
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items
from test_rated_barrel_contact_fault_repair import case,OPTIONS


def fixture(tmp_path,quarter=0,name='UNRELATED',back=False):
    data=case(tmp_path,quarter,prefix='/'+name+'/')
    source,old_child,cuts,old,new,net,contract=data
    old_routes=pcbnew.LoadBoard(str(old_child));board=pcbnew.LoadBoard(str(source))
    fp=pcbnew.FootprintLoad(str(pattern.ROOT/'lib/vendor/Resistor_SMD.pretty'),'R_2512_6332Metric')
    fp.SetFPIDAsString('cec-Resistor_SMD:R_2512_6332Metric');fp.SetReference(name+'_SHUNT')
    fp.SetValue('0.5mΩ');fp.SetField('MPN','CSS2H-2512R-L500F');board.Add(fp)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(quarter*90);fp.SetPosition(pcbnew.VECTOR2I_MM(17.2,26.5))
    for pad in fp.Pads():
        target=pcbnew.NETINFO_ITEM(board,'/UNRELATED_ISOLATED_SHUNT_'+pad.GetNumber())
        board.Add(target);pad.SetNet(target)
    label=pcbnew.PCB_TEXT(board);label.SetText(name+'_OPAQUE_GUIDE');label.SetLocked(True)
    label.SetLayer(pcbnew.B_SilkS);label.SetMirrored(True);label.SetPosition(pcbnew.VECTOR2I_MM(6,22))
    board.Add(label);field._save_field_snapshot(board,source)
    # This is a legal historical spelling: absent text angle means zero.
    # The native manufacturer writer emits the explicit zero. No electrical
    # or graphical property changes; the first stock receiver proves that.
    source_text=raw.raw_text(source);nodes,_,_,_=literal._inventory(source_text)
    a,b,node=nodes[force._uid(label)];x,y=literal._child(node,'at');values=literal._atoms(node[x+1:y-1])
    assert values[0][0]=='at' and len(values) in (3,4)
    if len(values)==4:
        assert float(values[3][0])==0
        node=node[:x]+'('+' '.join(t for _,t in values[:3])+')'+node[y:]
    raw.write_raw(source,source_text[:a]+node+source_text[b:])
    board=pcbnew.LoadBoard(str(source));q=pattern.plan(board,[force._uid(fp)]);pattern.materialize(board,q)
    prefix=force._copy_family(source,tmp_path/'received-manufacturer-prefix');field._save_field_snapshot(board,prefix)
    # The intended regression is an ACTUAL syntax change, not a caller flag.
    _,old_nodes=chain.additive._nodes(source);_,prefix_nodes=chain.additive._nodes(prefix)
    assert chain.sexpr._freeze(old_nodes[force._uid(label)])!=chain.sexpr._freeze(prefix_nodes[force._uid(label)])
    final=force._copy_family(prefix,tmp_path/'final');child=pcbnew.LoadBoard(str(final))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t) in set(cuts)|{old}])
    for item in old_routes.GetTracks():
        new_item=item.Duplicate();child.Add(new_item);new_item.SetNet(child.FindNet(net))
    field._save_field_snapshot(child,final)
    phases=[dict(kind='manufacturer_land_pattern',candidate=str(prefix),footprint_uuids=[force._uid(fp)]),
        dict(kind='rated_barrel_reseat',candidate=str(final),retired_track_uuids=cuts,retired_via_uuids=[old],**OPTIONS)]
    return source,prefix,final,phases,net,contract,force._uid(label)


def receive(data):
    source,prefix,final,phases,net,contract,label=data
    with patch.object(rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        return chain.receive(source,final,board_hint='synthetic',phases=phases,timeout_s=10.,per_phase_leases=True)


@pytest.mark.parametrize('quarter,name',[(0,'A'),(1,'RENAMED'),(2,'NESTED'),(3,'OTHER')])
@pytest.mark.parametrize('back',[False,True])
def test_exact_received_manufacturer_prefix_composes_with_source_cuts_without_false_text_angle_motion(tmp_path,quarter,name,back):
    data=fixture(tmp_path,quarter,name,back);before=[p.read_bytes() for p in data[:3]]
    proof=receive(data)
    assert proof['ok'] and proof['complete'],proof
    assert proof['strict_manufacturer_land_patterns_received']
    assert proof['independently_received_manufacturer_prefix_is_exact_projection_basis']
    assert proof['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert [p.read_bytes() for p in data[:3]]==before
    assert not proof['release_authority'] and not proof['current_authority']


@pytest.mark.parametrize('where,fault',[('prefix','move'),('prefix','text'),('prefix','lock'),
    ('final','move'),('final','text'),('final','lock'),('final','unowned_copper')])
def test_received_prefix_cannot_launder_unowned_changes_in_either_phase(tmp_path,where,fault):
    data=fixture(tmp_path);path=data[1] if where=='prefix' else data[2]
    board=pcbnew.LoadBoard(str(path));label=next(t for t in board.GetDrawings() if force._uid(t)==data[-1])
    if fault=='move':label.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='text':label.SetText('NOT_THE_SOURCE')
    elif fault=='lock':label.SetLocked(False)
    else:next(iter(next(iter(board.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(board,path);before=[p.read_bytes() for p in data[:3]]
    proof=receive(data)
    assert not proof['ok'] and proof['errors'],proof
    assert [p.read_bytes() for p in data[:3]]==before


def test_unreceived_prefix_proposal_has_no_projection_authority(tmp_path):
    data=list(fixture(tmp_path));data[3][0]['footprint_uuids']=['not-the-source-part']
    proof=receive(data)
    assert not proof['ok'] and proof['errors']
