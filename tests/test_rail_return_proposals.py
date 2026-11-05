from types import SimpleNamespace as Part
import cec_device_bypass as bypass

def fixture():
    comps = {'C91': Part(value='100nF', footprint='C_0402', props={}, excluded_from_bom=False)}
    nets = {'LOGIC':[('C91','1')], 'GND':[('C91','2')]}
    req = dict(ref='U77',pin='5',return_pin='3',rail='LOGIC',return_rail='VCC',kind='100n',source='device contract')
    sheets = {'C91':'can-leaf','U77':'can-leaf'}
    return comps,nets,[req],sheets

def test_named_rail_not_refdes_selects_cap():
    args=fixture()
    assert bypass.rail_return_repair_proposals(*args)[0]['cap']=='C91'

def test_ambiguous_or_owned_or_other_sheet_is_not_guessed():
    c,n,r,s=fixture()
    c['C92']=c['C91'];s['C92']='can-leaf'
    n['LOGIC'].append(('C92','1'));n['GND'].append(('C92','2'))
    assert bypass.rail_return_repair_proposals(c,n,r,s)==[]
    del c['C92']
    c['C91'].props={'BypassOwner':'U78.5'}
    assert bypass.rail_return_repair_proposals(c,n,r,s)==[]
    c['C91'].props={};s['C91']='other-leaf'
    assert bypass.rail_return_repair_proposals(c,n,r,s)==[]

def test_ground_requirement_and_bulk_are_not_rewritten():
    c,n,r,s=fixture()
    r[0]['return_rail']='GND'
    assert bypass.rail_return_repair_proposals(c,n,r,s)==[]
    r[0]['return_rail']='VCC';c['C91'].footprint='CP_Elec'
    assert bypass.rail_return_repair_proposals(c,n,r,s)==[]
