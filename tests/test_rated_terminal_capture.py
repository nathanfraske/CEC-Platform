"""Native pad DRC space cannot stand in for a larger current-rated launch."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_terminal_capture as capture
from test_field_proposals import add_net
from test_lastmile import _board


class Guard:
    def __init__(self,*args,**kwargs):pass
    def allows_endpoint(self,*args):return True
    def __call__(self,*args):return True


def fixture(tmp_path,offset=.65,quarter=0,prefix='/a/'):
    def pose(at):
        x,y=at[0]-15,at[1]-15
        for _ in range(quarter):x,y=-y,x
        return 15+x,15+y
    net=prefix+'SUPPLY';b=_board([(*pose((10,10)),net)],edge=(0,0,30,30))
    pad=next(p for f in b.GetFootprints() for p in f.Pads())
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    pad.SetRoundRectRadiusRatio(.25)
    add_net(b,'OTHER');v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*pose((10-offset,10+.55))))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname('OTHER'));b.Add(v)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    authority=dict(current_authority=dict(amps=2.5,geometry_margin=1.25,margin_included=False,
        source='board_design_basis'),required_by_layer_nm={int(l):742453 for l in b.GetEnabledLayers().CuStack()})
    return b,path,force._uid(pad),authority


def receive(data,authority_override=None):
    board,source,uid,authority=data
    with patch.object(capture,'_authority',return_value=authority if authority_override is None else authority_override), \
         patch.object(capture.control,'Guard',Guard), \
         patch.object(capture.cells,'_netclass',return_value=dict(width=742453,clearance=200000)), \
         patch.object(capture.prefix,'supply_terminal_role',return_value=None):
        return capture.receive(board,source,board_hint='synthetic',pad_uuids=[uid])


@pytest.mark.parametrize('quarter,prefix',[(0,'/a/'),(1,'/other/'),(2,'/different/'),(3,'/z/')])
def test_drc_clear_roundrect_still_needs_actual_wider_source_launch(tmp_path,quarter,prefix):
    data=fixture(tmp_path,quarter=quarter,prefix=prefix);board,source,uid,authority=data
    pad=next(p for f in board.GetFootprints() for p in f.Pads());v=next(iter(board.GetTracks()))
    assert not pad.GetEffectiveShape(pcbnew.F_Cu).Collide(v.GetEffectiveShape(pcbnew.F_Cu),200000)
    before=source.read_bytes();result=receive(data)
    assert result['complete'] and not result['ok'] and not result['errors'],result
    assert result['terminals'][0]['faces'][0]['actual_source_width_nm']==742453
    assert source.read_bytes()==before
    assert not result['no_path_proof'] and not result['full_route_proved']


@pytest.mark.parametrize('quarter',range(4))
def test_legally_reseated_barrel_restores_current_launch_without_changing_contract(tmp_path,quarter):
    result=receive(fixture(tmp_path,offset=.75,quarter=quarter))
    assert result['ok'] and result['complete'],result
    assert result['terminals'][0]['faces'][0]['unchanged_current_authority']['amps']==2.5
    assert not result['release_authority'] and not result['terminal_ampacity_qualified']


@pytest.mark.parametrize('uids',[[],True,['a','a'],['a']*9])
def test_capture_scope_rejects_unbounded_or_ambiguous_requests(tmp_path,uids):
    board,source,uid,authority=fixture(tmp_path)
    with pytest.raises(ValueError):capture.receive(board,source,board_hint='synthetic',pad_uuids=uids)


def test_unknown_budget_has_no_capture_authority(tmp_path):
    data=fixture(tmp_path,offset=.75)
    with patch.object(capture,'_authority',return_value=None):
        r=capture.receive(data[0],data[1],board_hint='synthetic',pad_uuids=[data[2]])
    assert not r['ok'] and not r['complete'] and r['errors']==['ValueError:positive_existing_source_current_required']
