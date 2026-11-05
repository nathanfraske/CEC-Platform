import math
from unittest import mock
import pcbnew,pytest,wx
quiet=wx.LogNull()
import cec_force_current as force
import cec_field_coupling as field
import cec_native_terminal_seam as seam
from test_lastmile import _board


def fixture(tmp_path,angle=0,shift=(0,0),fault=None):
    b=_board([],edge=(0,0,40,40));ni=pcbnew.NETINFO_ITEM(b,'RENAMED_SUPPLY');b.Add(ni)
    other=pcbnew.NETINFO_ITEM(b,'FOREIGN');b.Add(other)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED_PACKAGE');b.Add(fp)
    def point(x,y):
        r=math.radians(angle);return pcbnew.VECTOR2I_MM(
            20+shift[0]+x*math.cos(r)-y*math.sin(r),20+shift[1]+x*math.sin(r)+y*math.cos(r))
    pads=[]
    for index,x in enumerate((0,.3)):
        p=pcbnew.PAD(fp);p.SetNumber(str(index+1));p.SetPosition(point(x,0));p.SetSize(pcbnew.VECTOR2I(300000,1150000))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetOrientation(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        p.SetLayerSet(layers);p.SetNet(ni);fp.Add(p);pads.append(p)
    if fault=='gap':pads[1].SetPosition(point(.301,0))
    if fault=='overlap':pads[1].SetPosition(point(.299,0))
    if fault=='net':pads[1].SetNet(other)
    if fault=='number':pads[1].SetNumber('1')
    if fault=='shape':pads[1].SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    if fault=='DNP':fp.SetDNP(True)
    if fault=='tiny':
        for p in pads:p.SetSize(pcbnew.VECTOR2I(100000,1150000))
        pads[1].SetPosition(point(.1,0))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    return b,path,[force._uid(p) for p in pads]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('shift',[(0,0),(3,-2)])
def test_seam_is_source_owned_short_and_geometry_invariant(tmp_path,angle,shift):
    b,path,ids=fixture(tmp_path,angle,shift);before=path.read_bytes()
    proposal=seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
    assert len(proposal['rows'])==1 and proposal['rows'][0]['bridge_length_mm']==pytest.approx(.3)
    assert proposal['rows'][0]['width_nm']>=100000
    assert not proposal['source_geometry_extended'] and not proposal['current_qualified']
    made=seam.construct(b,path,proposal)
    assert len(made)==1 and len(list(b.GetTracks()))==1 and path.read_bytes()==before
    assert not proposal['release_authority']


@pytest.mark.parametrize('fault',['gap','overlap','net','number','shape','DNP','tiny'])
def test_no_geometry_or_terminal_authority_from_same_net_label(tmp_path,fault):
    b,path,ids=fixture(tmp_path,fault=fault)
    with pytest.raises(ValueError):seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
    assert len(list(b.GetTracks()))==0


def test_source_epoch_change_refuses_seam_construction(tmp_path):
    b,path,ids=fixture(tmp_path);proposal=seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
    pad=next(p for f in b.GetFootprints() for p in f.Pads());pad.SetLocked(True)
    with pytest.raises(ValueError,match='stale'):seam.construct(b,path,proposal)
    assert len(list(b.GetTracks()))==0


@pytest.mark.parametrize('value',[0,-1,True,float('nan'),11])
def test_finite_seam_budget_required(tmp_path,value):
    b,path,ids=fixture(tmp_path)
    with pytest.raises(ValueError):seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids],timeout_s=value)


def test_positive_declared_pair_cannot_receive_one_member_seam(tmp_path):
    b,path,ids=fixture(tmp_path)
    with mock.patch.object(seam.precision,'derive_coupled_pairs',return_value=[
            dict(p='RENAMED_SUPPLY',n='OTHER_NATIVE_MEMBER')]):
        with pytest.raises(ValueError,match='nonpaired'):seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
    assert len(list(b.GetTracks()))==0


def test_automatic_discovery_does_not_depend_on_refdes_or_net_spelling(tmp_path):
    b,path,ids=fixture(tmp_path)
    report=seam.discover(b,path,board_hint='synthetic')
    assert report['complete'] and {frozenset(r) for r in report['pad_pairs']}=={frozenset(ids)}
    assert len(list(b.GetTracks()))==0 and not report['construction_authorized']
    seam.construct(b,path,seam.plan(b,path,board_hint='synthetic',pad_pairs=report['pad_pairs']))
    replay=seam.discover(b,path,board_hint='synthetic')
    assert replay['complete'] and replay['pad_pairs']==[]


def test_failed_endpoint_receiving_leaves_no_partial_tracks_or_groups(tmp_path):
    b,path,ids=fixture(tmp_path);b.GetDesignSettings().m_TrackMinWidth=200000
    # An explicit synthetic full-class size exercises batch neckdown preflight.
    proposal=seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
    with mock.patch.object(seam.dimensions,'project_resolver',return_value=lambda _:dict(track_width=1.)):
        proposal=seam.plan(b,path,board_hint='synthetic',pad_pairs=[ids])
        with mock.patch.object(seam.fr,'_qualified_endpoint_neckdown_tracks',return_value=([],[dict(reason='synthetic_refusal')])):
            with pytest.raises(ValueError,match='independently'):seam.construct(b,path,proposal)
    assert len(list(b.GetTracks()))==0 and len(list(b.Groups()))==0
