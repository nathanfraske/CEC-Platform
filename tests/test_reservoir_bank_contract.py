import copy
import pytest
from cec_reservoir_screen import check_bank, ramp_screen

def fixture():
    inventory={r:dict(value='2.5',on_board=True,in_bom=True,dnp=False,
        footprint='test:case',props={'MPN':'part'}) for r in ('A','B')}
    pins={r:{'1':'protected','2':'return'} for r in inventory}
    kwargs=dict(references=('A','B'),positive_net='protected',negative_net='return',
        capacitance=float,same_net=lambda a,b:a==b,expected_each_f=2.5,
        expected_properties={'MPN':'part'},expected_footprint='test:case')
    return inventory,pins,kwargs

def test_arbitrary_bank_contract():
    inv,pins,kw=fixture();result=check_bank(inv,pins,**kw)
    assert result['ok'] and result['nominal_f']==5
    assert not result['fabrication_qualified']

@pytest.mark.parametrize('fault',['dnp','wrong_net','reversed','value','package','mpn','bom'])
def test_bad_member_not_counted(fault):
    inv,pins,kw=fixture()
    if fault=='dnp':inv['B']['dnp']=True
    if fault=='wrong_net':pins['B']['1']='upstream'
    if fault=='reversed':pins['B']={'1':'return','2':'protected'}
    if fault=='value':inv['B']['value']='1'
    if fault=='package':inv['B']['footprint']='wrong:case'
    if fault=='mpn':inv['B']['props']['MPN']='wrong'
    if fault=='bom':inv['B']['in_bom']=False
    result=check_bank(inv,pins,**kw)
    assert not result['ok'] and result['nominal_f']==2.5

def test_duplicate_bank_members_rejected():
    inv,pins,kw=fixture();kw['references']=('A','A')
    with pytest.raises(ValueError):check_bank(inv,pins,**kw)

def test_missing_or_unparseable_member_fails_closed():
    inv,pins,kw=fixture();del inv['B']
    assert not check_bank(inv,pins,**kw)['ok']
    inv,pins,kw=fixture();inv['B']['value']='unknown'
    assert not check_bank(inv,pins,**kw)['ok']

def test_ramp_does_not_ignore_existing_load():
    kw=dict(capacitance_max_f=.01,slew_v_per_s=40,load_a=.6,leakage_a=.001,current_limit_a=1.)
    assert not ramp_screen(**kw)['ok']
    assert ramp_screen(**{**kw,'current_limit_a':1.01})['ok']
