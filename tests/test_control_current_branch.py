"""Control topology must not disguise a load, trunk or guessed current limit."""
import copy

import pcbnew
import pytest
import cec_control_current_branch as controls
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
from test_tied_control_access import captured_fixture


def fixture(tmp_path,monkeypatch,*,angle=0,back=False,bridge=True,distributed=False):
    source,candidate=captured_fixture(tmp_path,angle=angle,back=back,bridge=bridge)
    b=pcbnew.LoadBoard(str(candidate));net='RAIL_OTHER'
    domain=dict(net=net,complete=True,amps=3.,source_refs=['POWER_CONTACT_0'],
        sink_refs=['POWER_CONTACT_0'],authority_refs=['POWER_CONTACT_0'])
    # A synthetic terminal domain is sufficient for this classification-only
    # fixture: all other actual lands are compared as well. No power is rated.
    monkeypatch.setattr(topology,'distributed_supply_contracts',lambda *a,**k:dict(contracts={net:copy.deepcopy(domain)}))
    return source,candidate,b,({} if distributed else {net:domain})


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
@pytest.mark.parametrize('distributed',[False,True])
def test_control_classification_preserves_all_other_native_load_partitions(tmp_path,monkeypatch,angle,back,distributed):
    source,candidate,b,domains=fixture(tmp_path,monkeypatch,angle=angle,back=back,distributed=distributed)
    old=field._field_snapshot_inventory(b)
    proof=controls.inventory(b,candidate,domains)
    assert proof['complete'] and proof['uuids'] and not proof['refusals'],proof
    row=proof['proofs'][0]
    assert row['partitions_unchanged_after_collective_removal']
    assert row['control_input_current_max_a'] is None and not row['new_numeric_load_assumed']
    assert not row['current_path_qualified'] and not row['release_authority']
    assert row['unchanged_source_current_authority']['amps']==3.
    assert field._field_snapshot_inventory(b)==old


@pytest.mark.parametrize('fault',['unknown_package','dnp','wrong_tie','unqualified_via',
    'foreign_group','incomplete_domain','declared_current_terminal','new_load_at_control_departure'])
def test_unknown_or_load_bearing_branch_retains_aggregate_width_obligation(tmp_path,monkeypatch,fault):
    source,candidate,b,domains=fixture(tmp_path,monkeypatch)
    owner=b.FindFootprintByReference('OWNER_RENAMED_0')
    if fault=='unknown_package':owner.SetValue('UNQUALIFIED_LDO')
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='wrong_tie':owner.FindPadByNumber('4').SetNet(b.FindNet('OUTPUT_OTHER'))
    elif fault=='unqualified_via':
        for v in b.GetTracks():
            if v.GetClass()=='PCB_VIA' and v.GetPosition().y>10000000:
                v.SetWidth(250000);v.SetDrill(200000)
    elif fault=='foreign_group':
        t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.IsLocked())
        g=pcbnew.PCB_GROUP(b);g.SetName('NOT_CONTROL_AUTHORITY');b.Add(g);g.AddItem(t)
    elif fault=='incomplete_domain':domains['RAIL_OTHER']['complete']=False
    elif fault=='declared_current_terminal':
        domains['RAIL_OTHER']['sink_refs'].append(owner.GetReference())
    else:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('ACTUAL_LOAD');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet('RAIL_OTHER'))
        p.SetPosition(pcbnew.VECTOR2I_MM(12,10.65));p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    old=field._field_snapshot_inventory(b)
    proof=controls.inventory(b,candidate,domains)
    assert proof['complete'],proof
    if fault=='new_load_at_control_departure':
        # The first surface edge can still be an exclusive EN leaf. The
        # bridge BEYOND that newly encountered load must not get classified;
        # it now carries a real load and retains the full supply obligation.
        assert len(proof['uuids'])==1,proof
        excluded={force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'
                  and t.GetLayer()==pcbnew.B_Cu}
        assert excluded and not excluded.intersection(proof['uuids'])
    else:assert not proof['uuids'],proof
    assert field._field_snapshot_inventory(b)==old


@pytest.mark.parametrize('budget',[0,True,float('nan'),11])
def test_unknown_deadlines_refuse_without_classification(tmp_path,monkeypatch,budget):
    source,candidate,b,domains=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):controls.inventory(b,candidate,domains,timeout_s=budget)
