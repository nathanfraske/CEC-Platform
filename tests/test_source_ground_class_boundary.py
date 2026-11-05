"""A positive low-power source endpoint may own its existing class-width leg."""
import time
import copy
import json

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_ground_cut_boundaries as boundaries
import cec_macro_cut_components as components
import cec_cell_row_rebuild as row
import cec_force_current as force
from cec_native_items import discard_items
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,width=.5):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('DIFFERENT_OWNER');fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.))
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetNet(net);fp.Add(pad);pad.SetPosition(fp.GetPosition())
    edge=track(board,'GND',(10,10),(12,10),width=width)
    retained=track(board,'GND',(12,10),(14,10),width=.5)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    # This is an authored synthetic Source geometry class, not an ambient
    # headless NETCLASS mock or a declaration of load/current capability.
    project=path.with_suffix('.kicad_pro')
    data=json.loads(project.read_text()) if project.exists() else {
        'net_settings':{'classes':[dict(name='Default',track_width=.2,clearance=.2)],
            'netclass_patterns':[]}}
    settings=data['net_settings'];spec=copy.deepcopy(next(c for c in settings['classes']if c['name']=='Default'))
    spec.update(name='EXPLICIT_SYNTHETIC_GROUND',track_width=.5)
    settings['classes'].append(spec)
    settings['netclass_assignments']=dict(settings.get('netclass_assignments')or{})
    settings['netclass_assignments']['GND']='EXPLICIT_SYNTHETIC_GROUND'
    project.write_text(json.dumps(data))
    source,posed=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    model=dict(pins={'2':'ground','5':'power_input'},source='synthetic_manufacturer')
    monkeypatch.setattr(compiler.roles,'footprint_contract',lambda fp:model)
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:set())
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(source),poses={'DIFFERENT_OWNER':[10.5,10.,0.]},
        device_contracts={'DIFFERENT_OWNER':model},selected_bypasses={},retired_track_uuids=[],board_hint='synthetic')
    actual=next(t for t in source.GetTracks() if force._uid(t)==force._uid(edge))
    transport=dict(source_process_barrel_motion=[],changes=[dict(uuid=force._uid(actual),net='GND',
        source_nm=[list(actual.GetStart()),list(actual.GetEnd())])])
    return source,posed,actual,retained,proposal,transport,model


def test_full_class_leg_gets_all_fixed_ports_and_ground_fragment_debts(tmp_path,monkeypatch):
    source,posed,edge,trunk,proposal,transport,model=fixture(tmp_path,monkeypatch)
    extras=compiler._extra_ownership(source,None,transport,proposal,time.monotonic()+10.)
    assert extras[0]['authority']['source_full_class_width_nm']==500000
    uid=force._uid(edge);discard_items(posed,[t for t in posed.GetTracks() if force._uid(t)==uid])
    posed.FindFootprintByReference('DIFFERENT_OWNER').Move(pcbnew.VECTOR2I_MM(.5,0))
    requests,records=components.requests(source,posed,extras,{uid},transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+10.)
    assert len(requests)==1 and len(records[0]['surviving_contacts'])==2
    assert next(iter(requests.values()))['width_nm']==500000
    proposal['retired_track_uuids']=[uid]
    ground=boundaries.requests(source,posed,proposal)
    assert len(ground)==1 and next(iter(ground.values()))['width_nm']==500000


@pytest.mark.parametrize('fault',['oversize','untyped','power_stage','not_moving_owner'])
def test_source_ground_net_does_not_own_arbitrary_trunks(tmp_path,monkeypatch,fault):
    source,posed,edge,trunk,proposal,transport,model=fixture(tmp_path,monkeypatch,width=.6 if fault=='oversize' else .5)
    if fault=='untyped':monkeypatch.setattr(compiler.roles,'footprint_contract',lambda fp:None)
    elif fault=='power_stage':model['pins']['3']='switch'
    elif fault=='not_moving_owner':proposal['poses']={}
    with pytest.raises(ValueError):
        compiler._extra_ownership(source,None,transport,proposal,time.monotonic()+10.)


def test_component_cannot_claim_class_width_without_the_source_authority(tmp_path,monkeypatch):
    source,posed,edge,trunk,proposal,transport,model=fixture(tmp_path,monkeypatch)
    uid=force._uid(edge);extras=compiler._extra_ownership(source,None,transport,proposal,time.monotonic()+10.)
    extras[0]['authority'].pop('source_full_class_width_nm')
    with pytest.raises(ValueError,match='ownership_changed'):
        components.requests(source,posed,extras,{uid},transport,project_contacts=compiler._project_contacts,
            deadline=time.monotonic()+10.)
