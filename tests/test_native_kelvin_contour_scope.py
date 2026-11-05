import copy
import pytest
from root_native_kelvin_contour_scope_20261012 import frozen_nets


def inventory(net='completely_renamed', status='unknown'):
    return dict(complete=True,identity_stable=True,source_unchanged=True,code_unchanged=True,errors=[],
        clipped_isolation=dict(expected=1,details=[dict(net=net,status=status,
            source_pad=dict(uuid='native-source',net=net),
            sense_terminal=dict(uuid='native-sense',net=net))]))


@pytest.mark.parametrize('net', ['a', '/rail/renamed', 'not_a_power_name'])
@pytest.mark.parametrize('status', ['unknown', 'pass', 'fail'])
def test_every_actual_leg_is_frozen_without_qualification_or_lexical_guess(net,status):
    r=inventory(net,status);before=copy.deepcopy(r)
    assert frozen_nets(r)=={net} and r==before


@pytest.mark.parametrize('key', ['complete','identity_stable','source_unchanged','code_unchanged'])
def test_incomplete_or_changed_scope_refuses(key):
    r=inventory();r[key]=False
    with pytest.raises(ValueError):frozen_nets(r)


@pytest.mark.parametrize('change', ['count','bool_count','missing_source','missing_sense','wrong_net',
    'missing_uuid','same_uuid','duplicate','missing_details','errors'])
def test_ambiguous_missing_or_forged_identity_refuses(change):
    r=inventory();c=r['clipped_isolation'];d=c['details'][0]
    if change=='count':c['expected']=2
    elif change=='bool_count':c['expected']=True
    elif change=='missing_source':d.pop('source_pad')
    elif change=='missing_sense':d.pop('sense_terminal')
    elif change=='wrong_net':d['source_pad']['net']='wrong'
    elif change=='missing_uuid':d['sense_terminal'].pop('uuid')
    elif change=='same_uuid':d['sense_terminal']['uuid']=d['source_pad']['uuid']
    elif change=='duplicate':c['details'].append(copy.deepcopy(d));c['expected']=2
    elif change=='missing_details':c.pop('details')
    elif change=='errors':r['errors']=['unresolved input']
    with pytest.raises(ValueError):frozen_nets(r)


def test_absent_native_kelvin_scope_has_no_name_based_freezes():
    r=inventory();r['clipped_isolation']=dict(expected=0,details=[])
    assert frozen_nets(r)==set()
