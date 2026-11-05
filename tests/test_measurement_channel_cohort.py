import copy
from types import SimpleNamespace
import pytest
import pcbnew
import cec_measurement_channel_cohort as cohort


class Pad:
    def __init__(self,pin,net):self.pin=pin;self.net=net
    def GetNumber(self):return self.pin
    def GetNetname(self):return self.net
    def HasHole(self):return False
    def GetAttribute(self):return pcbnew.PAD_ATTRIB_SMD


class Footprint:
    def __init__(self,ref,pads,angle=0,back=False):
        self.ref=ref;self.pads=pads;self.angle=angle;self.back=back;self.uid='uuid-'+ref;self.dnp=False;self.locked=False
    def GetReference(self):return self.ref
    def Pads(self):return self.pads
    def IsDNP(self):return self.dnp
    def IsLocked(self):return self.locked
    def GetPosition(self):return SimpleNamespace(x=1234567,y=-2345678)
    def GetOrientationDegrees(self):return self.angle


def fixture(monkeypatch,angle=0,back=False):
    import cec_force_current as force,cec_cell_row_rebuild as binding
    import cec_current_topology as topology,cec_sense_topology as sense
    import cec_pair_semantics as semantics,cec_device_power_roles as roles
    import cec_constraints as constraints,cec_cell_escape_replan as escape
    owner_names=('monitor-renamed','amplifier-renamed');cap_names=('bypass-z','bypass-q');anchor_name='arbitrary-anchor'
    model={'pins':{'hi':'measurement','lo':'measurement','v':'power_input','g':'ground'}}
    owners=[Footprint(n,[Pad('hi','positive-rail'),Pad('lo','negative-rail'),Pad('v','logic'),Pad('g','GND')],angle,back)for n in owner_names]
    caps=[Footprint(n,[Pad('1','logic'),Pad('2','GND')],angle,back)for n in cap_names]
    anchor=Footprint(anchor_name,[Pad('1','positive-rail'),Pad('2','negative-rail')])
    board=SimpleNamespace(fps=[*owners,*caps,anchor]);board.GetFootprints=lambda:board.fps
    state=lambda b:repr([(f.ref,f.uid,f.angle,f.back,f.dnp,f.locked,[(p.pin,p.net)for p in f.pads])for f in b.fps])
    monkeypatch.setattr(binding,'_source_binding',state);monkeypatch.setattr(force,'_uid',lambda x:x.uid)
    monkeypatch.setattr(topology,'board_current_domains',lambda *a:{'rail':{'complete':True,'authority_refs':[anchor_name]}})
    monkeypatch.setattr(semantics,'footprint_input_contract',lambda fp:('typed',['hi','lo'])if fp.ref in owner_names else None)
    monkeypatch.setattr(roles,'footprint_contract',lambda fp:copy.deepcopy(model)if fp.ref in owner_names else None)
    monkeypatch.setattr(constraints,'_fp_assembly_state',lambda fp:(fp.dnp,False))
    rows=[dict(ref=n,ok=True,pins=['hi','lo'],input_nets=['positive-rail','negative-rail'],selected=dict(anchor_ref=anchor_name,p=dict(anchor_pad='1'),n=dict(anchor_pad='2')))for n in owner_names]
    def evidence(b,**kw):
        assert kw==dict(anchor_pairs=[],anchor_refs=[anchor_name]);return dict(details=copy.deepcopy(rows))
    monkeypatch.setattr(sense,'board_evidence',evidence)
    assigned={str(i):dict(cap_ref=c,requirement=dict(ref=o,pin='v',rail='logic',return_rail='GND'))for i,(o,c)in enumerate(zip(owner_names,cap_names))}
    monkeypatch.setattr(constraints,'_device_bypass_assignment',lambda *a,**kw:dict(assigned=copy.deepcopy(assigned)))
    prepared=[]
    def prepare(b,poses,**kw):
        prepared.append(copy.deepcopy(poses));return dict(source_native_binding=state(b))
    monkeypatch.setattr(escape,'prepare',prepare)
    return board,owners,caps,rows,assigned,prepared


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_renamed_rigid_pose_source_channel_is_stationary_seed_only(monkeypatch,angle,back):
    b,owners,caps,rows,assigned,prepared=fixture(monkeypatch,angle,back)
    before=repr([(f.ref,f.angle,f.back)for f in b.fps])
    q=cohort.select(b,board_hint='source-context',owner_uuid=owners[0].uid)
    assert q['owners']==sorted(f.ref for f in owners)and q['bypasses']==sorted(f.ref for f in caps)
    assert q['ordered_anchor_pins']==['1','2']and len(q['poses'])==4
    assert all(p[2]==angle for p in q['poses'].values())and prepared==[q['poses']]
    assert not any(q[k]for k in ('placement_authority','retirement_authority','current_authority','release_authority'))
    assert before==repr([(f.ref,f.angle,f.back)for f in b.fps])


@pytest.mark.parametrize('fault',['unknown_seed','missing_cap','dnp_owner','dnp_cap','locked_owner',
    'orphan','ambiguous','wrong_shunt','reverse_roots','missing_model_pin','wrong_cap_net',
    'shared_cap','other_owner_cap_claim','missing_power_assignment','third_owner','alias_uuid','duplicate_ref'])
def test_malformed_or_ambiguous_channel_refused(monkeypatch,fault):
    b,o,c,rows,assigned,prepared=fixture(monkeypatch);uid=o[0].uid
    if fault=='unknown_seed':uid='not-an-actual-source-owner'
    elif fault=='missing_cap':b.fps.remove(c[0])
    elif fault=='dnp_owner':o[1].dnp=True
    elif fault=='dnp_cap':c[0].dnp=True
    elif fault=='locked_owner':o[0].locked=True
    elif fault=='orphan':rows[1]['ok']=False
    elif fault=='ambiguous':rows[0]['ok']=False
    elif fault=='wrong_shunt':rows[1]['selected']['anchor_ref']='other'
    elif fault=='reverse_roots':rows[1]['selected']['p']['anchor_pad']='2';rows[1]['selected']['n']['anchor_pad']='1'
    elif fault=='missing_model_pin':o[0].pads.pop()
    elif fault=='wrong_cap_net':c[0].pads[0].net='other'
    elif fault=='shared_cap':assigned['1']['cap_ref']=c[0].ref
    elif fault=='other_owner_cap_claim':assigned['extra']=dict(cap_ref=c[0].ref,requirement=dict(ref='unrelated',pin='v',rail='logic'))
    elif fault=='missing_power_assignment':assigned.pop('0')
    elif fault=='third_owner':rows.append(copy.deepcopy(rows[0]));rows[-1]['ref']='third'
    elif fault=='alias_uuid':c[0].uid=o[0].uid
    elif fault=='duplicate_ref':c[0].ref=o[0].ref
    with pytest.raises(ValueError):cohort.select(b,board_hint='source-context',owner_uuid=uid)
    assert not prepared


def test_existing_complete_cell_compiler_refusal_is_not_replaced(monkeypatch):
    import cec_cell_escape_replan as escape
    b,o,*_=fixture(monkeypatch)
    def refuse(*a,**kw):raise ValueError('actual_source_compiler_refused')
    monkeypatch.setattr(escape,'prepare',refuse)
    with pytest.raises(ValueError,match='actual_source_compiler_refused'):cohort.select(b,board_hint='source-context',owner_uuid=o[0].uid)


def test_native_identity_mutation_refused_even_after_compiler_success(monkeypatch):
    import cec_cell_escape_replan as escape
    b,o,*_=fixture(monkeypatch)
    def mutate(*a,**kw):o[0].pads[0].net='forged';return dict(source_native_binding='forged')
    monkeypatch.setattr(escape,'prepare',mutate)
    with pytest.raises(ValueError,match='changed_source'):cohort.select(b,board_hint='source-context',owner_uuid=o[0].uid)


@pytest.mark.parametrize('kw',[{'timeout_s':0},{'timeout_s':11},{'timeout_s':float('nan')},{'max_members':9},{'max_members':3}])
def test_bounds_before_source_work(monkeypatch,kw):
    b,o,*_=fixture(monkeypatch)
    with pytest.raises(ValueError,match='bounded_source'):cohort.select(b,board_hint='source-context',owner_uuid=o[0].uid,**kw)
