"""Routing representatives do not erase any Source supply-fork obligation."""
import copy
import inspect
import time
import pcbnew
import pytest
import cec_cell_shared_fork as fork
import cec_cell_macro_requests as compiler
import cec_cell_escape_replan as escape
import cec_complete_cell_receiving as receiving
import cec_complete_macro_cell as macro
from cec_native_items import discard_items
from test_cell_shared_fork import fixture,power_authority
from test_field_proposals import track


def setup_source(tmp_path,monkeypatch,quarter=0,back=False,renamed=False):
    board,path,root,left,right,old,xy=fixture(tmp_path,quarter,back,renamed,power=True)
    net=root.GetNetname();face=list(root.GetLayerSet().CuStack())[0]
    power_authority(monkeypatch,net,face)
    cap=pcbnew.FOOTPRINT(board);board.Add(cap);cap.SetReference('ANOTHER_SELECTED_CERAMIC')
    cap.SetValue('100nF');cap.SetLayer(face)
    for number,name,at in [('1',net,(9.,10.)),('2','GND',(9.,8.))]:
        pad=pcbnew.PAD(cap);cap.Add(pad);pad.SetNumber(number);pad.SetNet(board.FindNet(name))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetPosition(xy(at));pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    selected=cap.FindPadByNumber('1')
    monkeypatch.setattr(fork.leaf,'_bypass_supply_owner',lambda *a,**kw:
        dict(owner=root.GetParentFootprint().GetReference(),pin=root.GetNumber(),rail=net))
    extra=track(board,net,list(xy((9,10))/1e6),list(xy((10,10))/1e6),width=.2,layer=face)
    extra.SetLocked(True);old.append(extra)
    pcbnew.SaveBoard(str(path),board)
    plan=fork.plan(board,[fork.force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference(),cap.GetReference()],
        kind='rated_supply',board_hint='synthetic',allow_owned_locked=True)
    discard_items(board,old)
    return board,plan,root,selected,left,right


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('renamed',[False,True])
def test_explicit_representative_preserves_every_fixed_and_mandatory_Source_port(tmp_path,monkeypatch,quarter,back,renamed):
    board,plan,root,cap,left,right=setup_source(tmp_path,monkeypatch,quarter,back,renamed)
    pair=(fork.force._uid(root),fork.force._uid(cap));before=escape.row._source_binding(board)
    default=fork.connections(board,plan,mandatory_links=[pair])
    changed=fork.connections(board,plan,mandatory_links=[pair],preferred_supply_root_pad_uuids=[pair[1]])
    moving=lambda rows:{p['pad_uuid']for r in rows for p in(r['a'],r['b'])if 'pad_uuid'in p}
    assert moving(default)=={pair[0]} and moving(changed)=={pair[1]}
    fixed=lambda rows:{u for r in rows for p in(r['a'],r['b'])for u in p.get('native_uuids',[])}
    assert fixed(default)==fixed(changed)=={fork.force._uid(left),fork.force._uid(right)}
    assert len(default)==len(changed)==2
    assert all(r['width_nm']==plan['width_nm']and r['unchanged_full_rail_current_contract']==
        plan['unchanged_full_rail_current_contract']for r in changed)
    assert all(r['source_typed_multiport_fork']==plan for r in changed)
    assert before==escape.row._source_binding(board)


@pytest.mark.parametrize('fault',['fixed_port','other_net','scalar_role','no_contract','duplicate_cohort',
    'no_mandatory_link','duplicate_id','unknown_id'])
def test_choice_cannot_add_roots_roles_loads_or_skip_mandatory_links(tmp_path,monkeypatch,fault):
    board,plan,root,cap,left,right=setup_source(tmp_path,monkeypatch)
    ids=[fork.force._uid(cap)];mandatory=[(fork.force._uid(root),ids[0])]
    if fault=='fixed_port':ids=[fork.force._uid(left)]
    elif fault=='other_net':cap.SetNet(board.FindNet('GND'))
    elif fault=='scalar_role':plan['kind']='scalar_input'
    elif fault=='no_contract':plan.pop('unchanged_full_rail_current_contract')
    elif fault=='duplicate_cohort':ids.append(fork.force._uid(root))
    elif fault=='no_mandatory_link':mandatory=[]
    elif fault=='duplicate_id':ids*=2
    else:ids=['not-a-native-source-pad']
    before=escape.row._source_binding(board)
    with pytest.raises(ValueError):fork.connections(board,plan,mandatory_links=mandatory,preferred_supply_root_pad_uuids=ids)
    assert before==escape.row._source_binding(board)


def test_scalar_and_all_legacy_empty_choices_are_byte_exact(tmp_path,monkeypatch):
    board,plan,root,cap,left,right=setup_source(tmp_path,monkeypatch)
    pair=(fork.force._uid(root),fork.force._uid(cap))
    assert fork.connections(board,plan,mandatory_links=[pair])==fork.connections(board,plan,
        mandatory_links=[pair],preferred_supply_root_pad_uuids=[])
    assert compiler.packet_options(dict(explicit_native_macro_options={'shared_supply_root_pad_uuids':[pair[1]]}))=={
        'shared_supply_root_pad_uuids':[pair[1]]}
    for fn in(escape.prepare,escape._prepare_source,compiler.compile,receiving.receive,macro.receive):
        assert inspect.signature(fn).parameters['shared_supply_root_pad_uuids'].default==()


@pytest.mark.parametrize('bad',[None,True,'pad',['same']*2,['u']*9])
def test_unbounded_or_ambiguous_choices_refuse_before_Source_reads(bad):
    with pytest.raises(ValueError):fork.supply_root_ids(bad)
