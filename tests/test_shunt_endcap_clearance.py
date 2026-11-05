"""Source-width terminal cleanup is geometric, not current qualification."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_shunt_endcap_clearance as cap
import cec_force_current as force
import cec_field_coupling as field
import cec_source_cut_chain as chain
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,angle=0,back=False,width_nm=2800000):
    b=_board([],edge=(0,0,50,50));nets={}
    for name in ('OTHER_FEED','OTHER_RETURN'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    fps={}
    def pad(ref,pin,net,xy,size,value,library):
        if ref not in fps:
            f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value)
            f.SetFPID(pcbnew.LIB_ID(*library));b.Add(f);fps[ref]=f
        p=pcbnew.PAD(fps[ref]);p.SetNumber(pin);p.SetNet(nets[net]);p.SetSize(pcbnew.VECTOR2I_MM(*size))
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());fps[ref].Add(p);return p
    anchor=pad('RENAMED_SHUNT','1','OTHER_FEED',(20,30),(3,1.5),'0.5mR',('Resistor_SMD','R_2512'))
    pad('RENAMED_SHUNT','2','OTHER_RETURN',(20,24),(3,1.5),'0.5mR',('Resistor_SMD','R_2512'))
    pad('RENAMED_SENSOR','8','OTHER_FEED',(16,28),(.3,1.4),'INA240A3',('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    pad('RENAMED_SENSOR','1','OTHER_RETURN',(16,25),(.3,1.4),'INA240A3',('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    pad('RENAMED_TERMINAL','1','OTHER_FEED',(20,34),(2,2),'Native',('Fixture','Terminal'))
    edge=track(b,'OTHER_FEED',(20,30),(20,33.5),width=2.8);edge.SetLocked(True)
    edge.SetWidth(width_nm)
    if back:
        mirror=pcbnew.VECTOR2I_MM(25,25)
        for f in b.GetFootprints():f.Flip(mirror,False)
        edge.Flip(mirror,False)
    origin=pcbnew.VECTOR2I_MM(25,25);rotation=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for i in [*b.GetFootprints(),*b.GetTracks()]:i.Rotate(origin,rotation)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    scope=dict(board_hint='synthetic',pad_uuid=force._uid(anchor),track_uuid=force._uid(edge))
    domain=dict(complete=True,source_refs=['RENAMED_TERMINAL'],sink_refs=['RENAMED_SHUNT'],
        authority_refs=['RENAMED_TERMINAL','RENAMED_SHUNT'])
    # Deliberately inherited width debt: no local polish may claim to rate it.
    contract=dict(required_by_layer_mm={'F.Cu':4.,'B.Cu':4.},amps=20.,source='fixture_design_basis')
    return source,scope,domain,contract


def construct(tmp_path,angle=0,back=False,width_nm=2800000):
    source,scope,domain,contract=fixture(tmp_path,angle,back,width_nm)
    with patch.object(cap.topology,'board_current_domains',return_value={'OTHER_FEED':domain}), \
         patch.object(cap.topology,'route_width_contracts',return_value={'OTHER_FEED':contract}):
        b=pcbnew.LoadBoard(str(source));proposal=cap.plan(b,source,**scope)
        child=force._copy_family(source,tmp_path/'child');cap.materialize(b,proposal)
        field._save_field_snapshot(b,child);cap.compile_saved(child,proposal)
    return source,child,scope,domain,contract


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,False),(270,False),(0,True)])
def test_renamed_rotated_native_cap_preserves_source_width_not_ampacity(tmp_path,angle,back):
    source,child,scope,domain,contract=construct(tmp_path,angle,back);before=source.read_bytes()
    with patch.object(cap.topology,'board_current_domains',return_value={'OTHER_FEED':domain}), \
         patch.object(cap.topology,'route_width_contracts',return_value={'OTHER_FEED':contract}):
        proof=cap.receive(source,child,**scope)
        assert proof['ok'] and proof['complete'],proof
        assert not proof['current_authority'] and not proof['inherited_debt_qualified'] and not proof['release_authority']
        assert proof['proposal']['source_width_nm']==2800000
        assert proof['modified_native_uuids']==[scope['track_uuid']]
        phases=[dict(kind='force_endcap',candidate=str(child),pad_uuid=scope['pad_uuid'],track_uuid=scope['track_uuid'])]
        receipt=chain.receive(source,child,board_hint='synthetic',phases=phases)
        assert receipt['ok'] and receipt['complete'],receipt
        assert receipt['exact_source_force_collector_uuids']==proof['added_native_uuids']
    assert source.read_bytes()==before


def test_odd_integer_width_keeps_exact_asymmetric_native_cross_section(tmp_path):
    source,child,scope,domain,contract=construct(tmp_path,width_nm=2800001)
    with patch.object(cap.topology,'board_current_domains',return_value={'OTHER_FEED':domain}), \
         patch.object(cap.topology,'route_width_contracts',return_value={'OTHER_FEED':contract}):
        proof=cap.receive(source,child,**scope)
    assert proof['ok'] and proof['proposal']['source_width_nm']==2800001,proof


@pytest.mark.parametrize('fault',['unknown_sensor','inward','diagonal','land_width','source_authority','dnp','group','unfilled_keeper'])
def test_plan_refuses_unowned_or_unqualified_source_geometry(tmp_path,fault):
    source,scope,domain,contract=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));edge=next(iter(b.GetTracks()))
    if fault=='unknown_sensor':b.FindFootprintByReference('RENAMED_SENSOR').SetValue('UNKNOWN')
    elif fault=='inward':edge.SetEnd(pcbnew.VECTOR2I_MM(20,27))
    elif fault=='diagonal':edge.SetEnd(pcbnew.VECTOR2I_MM(21,33))
    elif fault=='land_width':b.FindFootprintByReference('RENAMED_SHUNT').FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(2.7,1.5))
    elif fault=='source_authority':domain['complete']=False
    elif fault=='dnp':b.FindFootprintByReference('RENAMED_SHUNT').SetDNP(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(edge)
    else:
        z=pcbnew.ZONE(b);z.SetNet(edge.GetNet());z.SetLayer(pcbnew.F_Cu);z.Outline().NewOutline()
        for xy in [(18,29),(22,29),(22,36),(18,36)]:z.Outline().Append(pcbnew.VECTOR2I_MM(*xy))
        b.Add(z)
    with patch.object(cap.topology,'board_current_domains',return_value={'OTHER_FEED':domain}), \
         patch.object(cap.topology,'route_width_contracts',return_value={'OTHER_FEED':contract}),pytest.raises(ValueError):
        cap.plan(b,source,**scope)


@pytest.mark.parametrize('fault',['width','boundary','pad_pose','barrel','collector','thermal_relief','extra'])
def test_receiving_rejects_any_unowned_saved_material_or_rating_mutation(tmp_path,fault):
    source,child,scope,domain,contract=construct(tmp_path);b=pcbnew.LoadBoard(str(child))
    edge=next(t for t in b.GetTracks() if force._uid(t)==scope['track_uuid']);z=next(iter(b.Zones()))
    if fault=='width':edge.SetWidth(2799999)
    elif fault=='boundary':edge.SetEnd(pcbnew.VECTOR2I_MM(20,33.6))
    elif fault=='pad_pose':b.FindFootprintByReference('RENAMED_SHUNT').Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(edge.GetNet());v.SetPosition(pcbnew.VECTOR2I_MM(20,30));v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    elif fault=='collector':z.Outline().Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='thermal_relief':z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    else:track(b,'OTHER_FEED',(40,40),(41,40))
    field._save_field_snapshot(b,child)
    with patch.object(cap.topology,'board_current_domains',return_value={'OTHER_FEED':domain}), \
         patch.object(cap.topology,'route_width_contracts',return_value={'OTHER_FEED':contract}):
        proof=cap.receive(source,child,**scope)
    assert not proof['ok'] and proof['errors'],proof
