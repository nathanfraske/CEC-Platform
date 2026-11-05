"""Only catalog authority is synthetic; geometry and saved receiving are native."""
from unittest.mock import patch
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_full_current_acute_cleanup as op
import cec_full_current_planar_reflow as full
import cec_scalar_corner_stage as scalar
from test_scalar_acute_stage import fixture as acute_fixture

def fixture(tmp_path,quarter=0,back=False):
    b,net,tracks,_=acute_fixture(quarter*90,False,pcbnew.B_Cu if back else pcbnew.F_Cu)
    for t in tracks:t.SetWidth(500000)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    project['net_settings']['classes'][0]['track_width']=.5
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    contract=dict(net=net,required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},
        routing_layers=['F.Cu','B.Cu'],current_authority=dict(
            amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    domains={net:dict(net=net,complete=True,source_refs=['source'],sink_refs=['sink'])}
    return source,[force._uid(t)for t in tracks],net,contract,domains

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_saved_full_class_shortcut_reconstructs_and_receives(tmp_path,quarter,back):
    source,ids,net,contract,domains=fixture(tmp_path,quarter,back)
    with patch.object(full.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(full.topology,'board_current_domains',return_value=domains):
        b=pcbnew.LoadBoard(str(source));q=op.plan(b,source,board_hint='synthetic',source_track_uuids=ids)
        # Legacy ordinary scalar public inventory still excludes class .5.
        assert not scalar.inventory(b,{net},geometry_policy='acute_shortcut')['selected']
        child=force._copy_family(source,tmp_path/'candidate')
        construction=op.construct_private(source,child,q,board_hint='synthetic')
        assert construction['complete']
        received=op.receive(source,child,board_hint='synthetic',source_track_uuids=ids)
        assert received['ok'] and received['complete'],received
        assert received['strictly_shorter']
        assert not received['current_qualified'] and not received['release_authority']

@pytest.mark.parametrize('fault',['no_authority','incomplete','group','wrong_pair','width_change'])
def test_unknown_or_unowned_source_does_not_get_corner_permission(tmp_path,fault):
    source,ids,net,contract,domains=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source))
    if fault=='no_authority':domains={}
    elif fault=='incomplete':domains[net]['complete']=False
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(next(iter(b.GetTracks())))
        field._save_field_snapshot(b,source)
    elif fault=='wrong_pair':ids=[ids[0],'not_source']
    else:
        next(iter(b.GetTracks())).SetWidth(400000);field._save_field_snapshot(b,source)
    with patch.object(full.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(full.topology,'board_current_domains',return_value=domains):
        with pytest.raises((ValueError,KeyError)):
            op.plan(b,source,board_hint='synthetic',source_track_uuids=ids)

@pytest.mark.parametrize('fault',['narrow','wrong_layer','extra_via','source_pose'])
def test_saved_candidate_tampering_refuses_without_geometry_claim(tmp_path,fault):
    source,ids,net,contract,domains=fixture(tmp_path)
    with patch.object(full.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(full.topology,'board_current_domains',return_value=domains):
        q=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',source_track_uuids=ids)
        child=force._copy_family(source,tmp_path/'candidate')
        op.construct_private(source,child,q,board_hint='synthetic')
        b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()))
        if fault=='narrow':t.SetWidth(400000)
        elif fault=='wrong_layer':t.SetLayer(pcbnew.B_Cu)
        elif fault=='source_pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,1))
        else:
            via=pcbnew.PCB_VIA(b);via.SetNet(t.GetNet());via.SetPosition(t.GetStart())
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(900000);via.SetDrill(500000);b.Add(via)
        field._save_field_snapshot(b,child)
        r=op.receive(source,child,board_hint='synthetic',source_track_uuids=ids)
        assert not r['ok'] and r['errors'],r
