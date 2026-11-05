"""Source-authorized Kelvin demands may displace only exact ordinary edges."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_future_pose_clearance as future
import cec_cell_row_rebuild as row
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_local_branch_access import fixture as cell_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,ref='RENAMED_MONITOR',locked=False):
    source,_,_=cell_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    discard_items(b,list(b.GetTracks()))
    owner=b.FindFootprintByReference('U_RENAMED');owner.SetReference(ref)
    other=b.FindFootprintByReference('OTHER');b.Remove(other)
    shunt=b.FindFootprintByReference('FIXED');shunt.SetReference('ARBITRARY_SHUNT')
    shunt.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0603'))
    p=pcbnew.PAD(shunt);p.SetNumber('2');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.45,.45));p.SetPosition(pcbnew.VECTOR2I_MM(10,17))
    p.SetNetCode(b.GetNetcodeFromNetname('MEASURE_PLUS'));shunt.Add(p)
    b.Add(pcbnew.NETINFO_ITEM(b,'/ORDINARY_CTRL'))
    blocker=track(b,'/ORDINARY_CTRL',(13,15.5),(13,18))
    blocker.SetLocked(locked)
    for number,xy in enumerate(((13,15.5),(13,18))):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('CTRL_'+str(number));b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        p.SetNet(blocker.GetNet());fp.Add(p)
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    domains={net:dict(complete=True,authority_refs=['ARBITRARY_SHUNT'])
        for net in ('MEASURE_PLUS','MEASURE_MINUS')}
    return pcbnew.LoadBoard(str(source)),source,force._uid(owner.FindPadByNumber('3')),force._uid(blocker),domains


@pytest.mark.parametrize('angle,ref',[(0,'IC_A'),(90,'RENAMED'),(180,'SENSOR_B'),(270,'MONITOR')])
def test_source_sense_reservation_has_native_identity_not_board_coordinates(tmp_path,angle,ref):
    b,source,uid,blocked,domains=fixture(tmp_path,angle,ref)
    binding=row._source_binding(b);saved=source.read_bytes()
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        plans=[future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic',
            corridor_style=style) for style in ('y_first','x_first')]
    p=next(p for p in plans if p['ok'])
    assert p['retired_track_uuids']==[blocked],p
    link=p['links'][0]
    assert link['owner']==ref and link['pin']=='3' and link['destination_ref']=='ARBITRARY_SHUNT'
    assert link['points_nm'][0]==list(b.FindFootprintByReference(ref).FindPadByNumber('3').GetPosition())
    assert p['sense_link_not_yet_constructed'] and not p['kelvin_qualified'] and not p['release_authority']
    assert row._source_binding(b)==binding and source.read_bytes()==saved


@pytest.mark.parametrize('fault',['wrong_pin','wrong_package','dnp','no_authority','partial_authority',
    'back','connected','force_cap','locked','wide','group'])
def test_sense_preclear_refuses_invented_inputs_and_protected_material(tmp_path,fault):
    b,source,uid,blocked,domains=fixture(tmp_path,locked=fault=='locked')
    owner=b.FindFootprintByReference('RENAMED_MONITOR')
    edge=next(t for t in b.GetTracks() if force._uid(t)==blocked)
    if fault=='wrong_pin':uid=force._uid(owner.FindPadByNumber('5'))
    elif fault=='wrong_package':owner.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
    elif fault=='dnp':owner.SetAttributes(owner.GetAttributes()|pcbnew.FP_DNP)
    elif fault=='no_authority':domains={}
    elif fault=='partial_authority':domains['MEASURE_PLUS']['complete']=False
    elif fault=='back':owner.Flip(owner.GetPosition(),True)
    elif fault=='connected':track(b,'MEASURE_PLUS',(16,15),(17,15))
    elif fault=='force_cap':track(b,'MEASURE_PLUS',(10,17),(13,17),width=2.)
    elif fault=='wide':edge.SetWidth(500000)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(edge)
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        if fault in ('force_cap','locked','wide','group'):
            p=future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic')
            assert not p['ok'] and any(not r['ordinary_retirement_allowed'] for r in p['blockers']),p
        else:
            with pytest.raises(ValueError):
                future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic')


def test_sense_preclear_restores_ordinary_boundaries_and_chain_receives_exact_cuts(tmp_path):
    b,source,uid,blocked,domains=fixture(tmp_path,locked=True)
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        result=future.prepare(source,{},tmp_path/'prefix',board_hint='synthetic',
            sense_input_pad_uuids=[uid],allow_locked_track_uuids=[blocked])
    assert result['ok'],result
    assert result['source_opens']==result['opens'] and not result['future_blockers']
    phase=dict(kind='ordinary',candidate=result['board'],retired_track_uuids=[blocked],
        allow_locked_track_uuids=[blocked])
    proof=chain.receive(source,result['board'],board_hint='synthetic',phases=[phase])
    assert proof['ok'] and proof['complete'],proof
    assert proof['retired_track_uuids']==[blocked] and not proof['retired_via_uuids']
    assert not proof['current_authority'] and not proof['release_authority']
    forged=dict(phase,retired_track_uuids=['not-a-source-track'])
    assert not chain.receive(source,result['board'],board_hint='synthetic',phases=[forged])['ok']


def test_sense_constructor_rederives_source_and_rejects_modified_reservation(tmp_path):
    b,source,uid,blocked,domains=fixture(tmp_path)
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        p=future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic')
        p['links'][0]['points_nm'][0][0]+=1
        with pytest.raises(ValueError,match='plan_identity_changed'):
            future.construct(b,p,source=source)


def test_source_native_lookahead_never_changes_the_source_or_invents_a_cut(tmp_path):
    b,source,uid,blocked,domains=fixture(tmp_path,locked=True)
    saved=source.read_bytes();binding=row._source_binding(b)
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        refused=future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic',
            corridor_style='native_maze')
        assert not refused['ok'] and not refused['retired_track_uuids']
        p=future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic',
            corridor_style='native_maze',allow_locked_track_uuids=[blocked])
        assert p['ok'] and p['retired_track_uuids']==[blocked]
        received=future.prepare(source,{},tmp_path/'maze-prefix',board_hint='synthetic',
            corridor_style='native_maze',sense_input_pad_uuids=[uid],allow_locked_track_uuids=[blocked])
        assert received['ok'],received
    assert source.read_bytes()==saved and row._source_binding(b)==binding


@pytest.mark.parametrize('style',['raw_diagonal',None,False,0])
def test_corridor_policy_is_a_finite_source_derived_menu(tmp_path,style):
    b,source,uid,blocked,domains=fixture(tmp_path)
    with pytest.raises(ValueError,match='corridor_style'):
        future.plan_sense_input_links(b,[uid],source=source,board_hint='synthetic',corridor_style=style)
