"""Literal source-tail + inward-pad extension; existing debt stays debt."""
import math
import pcbnew
import pytest
import cec_force_current as force
import cec_decoupler_cell as cells
import cec_retained_source_supply_contact as contact
from test_source_supply_endpoint_cut import fixture as source_fixture


def fixture(tmp_path,monkeypatch,angle=0,back=False):
    b,cap,owner,root,tree=source_fixture(tmp_path,monkeypatch)
    b.SetCopperLayerCount(6);props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    pad=cap.FindPadByNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(.56,.62));pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.25)
    group=pcbnew.PCB_GROUP(b);group.SetName('CEC_LOCAL_ENDPOINT_NECKDOWN');b.Add(group)
    def edge(a,z,width,member=False):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));t.SetWidth(round(width*1e6));t.SetLayer(0);t.SetNet(pad.GetNet());t.SetLocked(True);b.Add(t)
        if member:group.AddItem(t)
        return t
    lead=edge((5,5.205),(5,5.43),.2,True);fixed=edge((5,5.43),(6,5.43),.5);other=edge((10,10),(12,10),.2,True)
    zero=pcbnew.VECTOR2I(0,0)
    if angle:
        turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for fp in b.GetFootprints():fp.Rotate(zero,turn)
        for t in b.GetTracks():t.Rotate(zero,turn)
    if back:
        for fp in b.GetFootprints():fp.Flip(zero,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for t in b.GetTracks():t.Flip(zero,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    path=tmp_path/'parent.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
    parent=pcbnew.LoadBoard(str(path));child=pcbnew.LoadBoard(str(path))
    theta=math.radians(angle);dx=-.055*math.sin(theta);dy=-.055*math.cos(theta)
    if back:dx=-dx
    child.FindFootprintByReference('FILTER').Move(pcbnew.VECTOR2I(round(dx*1e6),round(dy*1e6)))
    authority=dict(current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'),profile='jlcpcb_6l_pofv_high_current',required_by_layer_nm={int(lead.GetLayer()):40323},release_authority=False)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:authority)
    return parent,child,force._uid(lead),force._uid(fixed),force._uid(other),root,authority


def invoke(parent,child,uid,root):
    return contact.plan(parent,child,track_uuid=uid,board_hint=str(root),source_floor=lambda t:(500000,200000))


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_cardinal_original_width_path_retained_without_thin_qualification(tmp_path,monkeypatch,angle,back):
    b,child,uid,fixed,other,root,authority=fixture(tmp_path,monkeypatch,angle,back)
    proof=invoke(b,child,uid,root)
    assert proof and proof['source_width_nm']==200000
    assert proof['actual_factory_transverse_floor_nm']==200000
    assert proof['source_class_floor_nm']==500000
    assert proof['original_class_and_escape_debt_retained_unqualified']
    assert not proof['new_thin_copper_allowance']and not proof['current_qualified']
    assert other in proof['source_group_member_uuids']
    for p in proof['source_contacts']:
        assert p['before']['residual_outlines']==p['after']['residual_outlines']==0
        assert fixed in p['fixed_source_branch_track_uuids']
    assert proof['source_tail_only_exact_literal_identity']
    assert proof['outward_source_polygon_not_lower_material_authority']


@pytest.mark.parametrize('fault',['touch','one_nm_sliver','one_nm_lateral','width','fixed_end','axis45',
    'other_group_member','lock','group_name','group_lock','new_underwidth_trace','retirement',
    'source_mpn','projected_part','no_current','current_floor','factory_width','wrong_net','other_pad_uuid',
    'pad_mask','pad_rounding','projected_rules','projected_profile'])
def test_identity_material_source_or_incoming_changes_never_use_debt_retention(tmp_path,monkeypatch,fault):
    b,child,uid,fixed,other,root,authority=fixture(tmp_path,monkeypatch)
    tracks={force._uid(t):t for t in child.GetTracks()};fp=child.FindFootprintByReference('FILTER')
    if fault=='touch':fp.Move(pcbnew.VECTOR2I(0,-150000))
    elif fault=='one_nm_sliver':fp.Move(pcbnew.VECTOR2I(0,-149999))
    elif fault=='one_nm_lateral':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault in('width','factory_width'):tracks[uid].SetWidth(199999)
    elif fault=='fixed_end':tracks[uid].SetEnd(tracks[uid].GetEnd()+pcbnew.VECTOR2I(0,1))
    elif fault=='axis45':fp.SetOrientationDegrees(45)
    elif fault=='other_group_member':tracks[other].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='lock':tracks[uid].SetLocked(False)
    elif fault=='group_name':next(g for g in child.Groups()).SetName('arbitrary')
    elif fault=='group_lock':next(g for g in child.Groups()).SetLocked(True)
    elif fault=='new_underwidth_trace':
        t=pcbnew.PCB_TRACK(child);t.SetStart(pcbnew.VECTOR2I_MM(5,5));t.SetEnd(pcbnew.VECTOR2I_MM(6,5));t.SetWidth(10000);t.SetNet(tracks[uid].GetNet());child.Add(t)
    elif fault=='retirement':child.Remove(tracks[other])
    elif fault=='source_mpn':root.write_text(root.read_text().replace('CL05B104KO5NNNC','UNSELECTED'))
    elif fault=='projected_part':fp.SetValue('1nF')
    elif fault=='no_current':monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:None)
    elif fault=='current_floor':authority['required_by_layer_nm'][0]=200001
    elif fault=='wrong_net':tracks[uid].SetNetCode(0)
    elif fault=='pad_mask':fp.FindPadByNumber('1').SetLocalSolderMaskMargin(1)
    elif fault=='pad_rounding':fp.FindPadByNumber('1').SetRoundRectRadiusRatio(.1)
    elif fault=='projected_rules':child.GetDesignSettings().m_TrackMinWidth=199999
    elif fault=='projected_profile':
        properties=child.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';child.SetProperties(properties)
    else:fp.FindPadByNumber('1').m_Uuid.Clone(pcbnew.KIID())
    try:proof=invoke(b,child,uid,root)
    except ValueError:return
    assert proof is None


def test_existing_component_qualification_budget_is_not_called_or_reinterpreted(tmp_path,monkeypatch):
    import cec_fr as fr
    b,child,uid,fixed,other,root,authority=fixture(tmp_path,monkeypatch)
    def forbidden(*a,**k):raise AssertionError('retained debt is not a new neckdown qualification')
    monkeypatch.setattr(fr,'_qualified_endpoint_neckdown_tracks',forbidden)
    proof=invoke(b,child,uid,root)
    assert proof and proof['original_class_and_escape_debt_retained_unqualified']
