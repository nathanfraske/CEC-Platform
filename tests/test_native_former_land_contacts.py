"""Former land centres cannot substitute for offset physical contacts."""
import pcbnew, pytest
from cec_native_land_contacts import inspect
from test_field_proposals import track
from test_lastmile import _board


@pytest.mark.parametrize('turns',range(4))
@pytest.mark.parametrize('net',['/renamed/CONTROL','/other/RAIL'])
def test_exact_offset_endpoints_and_barrel_not_imaginary_centre(turns,net):
    def at(x,y):
        x-=15;y-=15
        for _ in range(turns): x,y=-y,x
        return 15+x,15+y
    b=_board([(15,15,net)],edge=(0,0,30,30));pad=next(iter(next(iter(b.GetFootprints())).Pads()))
    pad.SetSize(pcbnew.VECTOR2I_MM(1.5,1.5))
    track(b,net,at(14,14.1),at(14.6,14.7),width=.2)
    track(b,net,at(20,15),at(15.5,15),width=.2)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*at(15.2,15.2)))
    v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetNetCode(pad.GetNetCode());b.Add(v)
    before=[(t.m_Uuid.AsString(),tuple(t.GetPosition())) for t in b.GetTracks()]
    r=inspect(b,pad)
    expected={tuple(pcbnew.VECTOR2I_MM(*at(*p))) for p in ((14.6,14.7),(15.5,15),(15.2,15.2))}
    assert {tuple(q['point_nm']) for q in r['ports']}==expected
    assert r['complete'] and not r['ampacity_or_route_authority_granted']
    assert before==[(t.m_Uuid.AsString(),tuple(t.GetPosition())) for t in b.GetTracks()]


def test_body_contact_projects_to_existing_copper_and_empty_contact_not_invented():
    b=_board([(15,15,'x')],edge=(0,0,30,30));pad=next(iter(next(iter(b.GetFootprints())).Pads()))
    assert inspect(b,pad)['ports']==[]
    track(b,'x',(10,15.2),(20,15.2),width=.2)
    assert inspect(b,pad)['ports'][0]['point_nm']==[15000000,15200000]


@pytest.mark.parametrize('kw',[dict(max_contacts=True),dict(max_contacts=0),dict(timeout_s=30),dict(timeout_s=float('nan'))])
def test_invalid_scope_never_invents_contacts(kw):
    b=_board([(15,15,'x')]);pad=next(iter(next(iter(b.GetFootprints())).Pads()))
    with pytest.raises(ValueError):inspect(b,pad,**kw)
