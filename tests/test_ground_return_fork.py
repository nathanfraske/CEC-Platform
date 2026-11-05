"""A low-power Ground T-fork is bounded, typed and stops at real fixed ports."""
import copy
import time
import pcbnew
import pytest

import cec_cell_shared_fork as fork
import cec_cell_row_rebuild as row
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,back=False):
    board=_board([],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    for name in ('GND','OTHER','RAIL'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    def xy(point):
        x,y=point
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    def part(ref,at):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue('TLV7011DBVR')
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'));fp.SetLayer(face);board.Add(fp)
        for pin,net,point in [('1','OTHER',(at[0]-2,at[1]-2)),('2','GND',at),
                ('3','OTHER',(at[0]-2,at[1]-1)),('4','OTHER',(at[0]-2,at[1]+1)),
                ('5','RAIL',(at[0]-2,at[1]+2))]:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(board.FindNet(net))
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(face)
            p.SetLayerSet(layers);fp.Add(p);p.SetPosition(xy(point))
        return fp
    owner=part('opaque_owner',(10,10));fixed=part('opaque_fixed',(12,12))
    via=pcbnew.PCB_VIA(board);via.SetPosition(xy((14,10)));via.SetNet(board.FindNet('GND'))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    edges=[]
    for a,b in [((10,10),(14,10)),((12,10),(12,12)),((14,10),(18,10))]:
        t=track(board,'GND',[v/1e6 for v in xy(a)],[v/1e6 for v in xy(b)],layer=face,width=.2)
        t.SetLocked(True);edges.append(t)
    source=tmp_path/'source.kicad_pcb';board.SetFileName(str(source));pcbnew.SaveBoard(str(source),board)
    return board,source,owner,fixed,via,edges


def plan(board,owner,**options):
    return fork.plan(board,[force._uid(owner.FindPadByNumber('2'))],moving_refs=[owner.GetReference()],
        kind='ground_return',board_hint='opaque_design',allow_owned_locked=True,**options)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_interior_t_junction_is_owned_but_the_fixed_barrel_mesh_is_not(tmp_path,quarter,back):
    board,path,owner,fixed,via,edges=fixture(tmp_path,quarter,back)
    before=row._source_binding(board);raw=path.read_bytes();q=plan(board,owner)
    assert set(q['track_uuids'])=={force._uid(t) for t in edges[:2]}
    ports={p['native_uuid'] for p in q['retained_native_ports']}
    assert {force._uid(via),force._uid(edges[2]),force._uid(fixed.FindPadByNumber('2'))}<=ports
    assert q['fixed_ground_terminal_contracts'] and q['source_vias_zones_wide_tracks_and_groups_never_retired']
    assert q['source_ground_width_preserved_not_aggregate_injection_rating']
    assert q['every_retained_ground_fragment_plane_and_original_return_still_requires_receiving']
    assert not q['current_authority'] and not q['release_authority']
    assert before==row._source_binding(board) and raw==path.read_bytes()


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('protection',['pad','track'])
def test_unchanged_native_ground_pickup_stays_an_exact_retained_port(tmp_path,back,protection):
    board,path,owner,fixed,via,edges=fixture(tmp_path,back=back)
    options=({'retained_ground_pad_uuids':[force._uid(fixed.FindPadByNumber('2'))]}
        if protection=='pad' else {'retained_ground_track_uuids':[force._uid(edges[1])]})
    q=plan(board,owner,**options)
    assert q['track_uuids']==[force._uid(edges[0])]
    assert force._uid(edges[1]) in {p['native_uuid'] for p in q['retained_native_ports']}


@pytest.mark.parametrize('fault',['unknown_root','wrong_role','DNP','locked','root_hole','fixed_hole','unknown_fixed','fixed_regulator'])
def test_untyped_or_high_current_terminal_cannot_become_a_small_ground_fork(tmp_path,monkeypatch,fault):
    board,path,owner,fixed,via,edges=fixture(tmp_path)
    if fault=='unknown_root':owner.SetValue('not_a_manufacturer_model')
    elif fault=='wrong_role':
        actual=fork.roles.footprint_contract
        def wrong(fp):
            q=copy.deepcopy(actual(fp))
            if fp.GetReference()==owner.GetReference():q['pins']['2']='signal_input'
            return q
        monkeypatch.setattr(fork.roles,'footprint_contract',wrong)
    elif fault=='DNP':owner.SetDNP(True)
    elif fault=='locked':owner.SetLocked(True)
    elif fault=='root_hole':owner.FindPadByNumber('2').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='fixed_hole':fixed.FindPadByNumber('2').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='unknown_fixed':fixed.SetValue('unknown_fixed_device')
    else:
        actual=fork.roles.footprint_contract
        def model(fp):
            q=copy.deepcopy(actual(fp))
            if fp.GetReference()==fixed.GetReference():q['pins']['1']='power_output'
            return q
        monkeypatch.setattr(fork.roles,'footprint_contract',model)
    pcbnew.SaveBoard(str(path),board);before=row._source_binding(board)
    with pytest.raises(ValueError):plan(board,owner)
    assert before==row._source_binding(board)


def test_ground_strapped_address_is_a_retained_boundary_not_a_new_moving_root(tmp_path,monkeypatch):
    board,path,owner,fixed,via,edges=fixture(tmp_path);actual=fork.roles.footprint_contract
    def model(fp):
        q=copy.deepcopy(actual(fp))
        if fp.GetReference()==fixed.GetReference():q['pins']['2']='address'
        return q
    monkeypatch.setattr(fork.roles,'footprint_contract',model)
    q=plan(board,owner)
    assert q['fixed_ground_terminal_contracts'][0]['role']=='address'
    with pytest.raises(ValueError):plan(board,fixed)


@pytest.mark.parametrize('back',[False,True])
def test_existing_moving_package_address_strap_is_rebuilt_without_inventing_a_ground_root(tmp_path,monkeypatch,back):
    board,path,owner,fixed,via,edges=fixture(tmp_path,back=back);actual=fork.roles.footprint_contract
    address=owner.FindPadByNumber('4');address.SetNet(board.FindNet('GND'))
    address.SetPosition(owner.FindPadByNumber('2').GetPosition()+pcbnew.VECTOR2I_MM(0,1))
    def model(fp):
        q=copy.deepcopy(actual(fp))
        if fp.GetReference()==owner.GetReference():q['pins']['4']='address'
        return q
    monkeypatch.setattr(fork.roles,'footprint_contract',model)
    ground=owner.FindPadByNumber('2')
    link=track(board,'GND',[v/1e6 for v in ground.GetPosition()],
        [v/1e6 for v in address.GetPosition()],width=.2,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    pcbnew.SaveBoard(str(path),board);before=row._source_binding(board)
    q=plan(board,owner)
    assert force._uid(link) in q['track_uuids']
    contract=next(p for p in q['moving_source_terminal_contracts'] if p['pad_uuid']==force._uid(address))
    assert contract['role']=='address' and contract['existing_source_ground_address_strap_only']
    assert contract['new_ground_role_or_current_inferred'] is False
    assert before==row._source_binding(board)
    with pytest.raises(ValueError):fork.plan(board,[force._uid(address)],moving_refs=[owner.GetReference()],
        kind='ground_return',board_hint='opaque',allow_owned_locked=True)


@pytest.mark.parametrize('options',[{'max_tracks':True},{'max_tracks':0},{'max_tracks':33},
    {'max_length_mm':True},{'max_length_mm':0},{'max_length_mm':32.001},{'max_length_mm':float('nan')}])
def test_larger_explicit_work_scope_never_removes_finite_native_bounds(tmp_path,options):
    board,path,owner,*_=fixture(tmp_path)
    with pytest.raises(ValueError):plan(board,owner,**options)


@pytest.mark.parametrize('protection',[{'retained_ground_pad_uuids':['invented']},
    {'retained_ground_track_uuids':['invented']},{'retained_ground_pad_uuids':True}])
def test_protected_contacts_are_literal_bounded_native_source_identities(tmp_path,protection):
    board,path,owner,*_=fixture(tmp_path)
    with pytest.raises(ValueError):plan(board,owner,**protection)
