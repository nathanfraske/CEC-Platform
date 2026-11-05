"""Changed physical prefixes may retry; identical work must stay deduplicated."""
import copy
import pytest
import cec_cell_escape_replan as escape


def packet():
    def choice(uid,x):
        return dict(id=uid,cost=1,net='arbitrary',ops=[dict(kind='trk',start_nm=[x,0],end_nm=[x,1])])
    return dict(source_native_binding='literal-source',domains={
        'target':[choice('t',0)],'peer':[choice('a',1),choice('b',2)],
        'fixed':[choice('f',3)]})


def test_changed_prefix_is_new_work_but_identical_context_is_not():
    p=packet();first=escape._conflict_context_key(p,'target',{'peer':'a'})
    attempted={first}
    assert escape._conflict_context_key(p,'target',{'peer':'a'}) in attempted
    assert escape._conflict_context_key(p,'target',{'peer':'b'}) not in attempted


def test_copper_not_opaque_choice_name_or_cost_defines_context():
    p=packet();before=escape._conflict_context_key(p,'target',{'peer':'a'})
    p['domains']['peer'][0].update(id='renamed',cost=100)
    assert escape._conflict_context_key(p,'target',{'peer':'renamed'})==before
    p['domains']['peer'][0]['ops'][0]['end_nm']=[99,1]
    assert escape._conflict_context_key(p,'target',{'peer':'renamed'})!=before


def test_implicit_singleton_and_source_binding_are_part_of_context():
    p=packet();before=escape._conflict_context_key(p,'target',{})
    p['domains']['fixed'][0]['ops'][0]['end_nm']=[50,1]
    assert escape._conflict_context_key(p,'target',{})!=before
    p=packet();p['source_native_binding']='different-source'
    assert escape._conflict_context_key(p,'target',{})!=before


def test_unassigned_alternatives_and_target_menu_do_not_fund_duplicate_work():
    p=packet();before=escape._conflict_context_key(p,'target',{})
    p['domains']['peer'].append(copy.deepcopy(p['domains']['peer'][0]))
    p['domains']['target'].append(copy.deepcopy(p['domains']['target'][0]))
    assert escape._conflict_context_key(p,'target',{})==before


def test_stale_assigned_choice_fails_closed():
    with pytest.raises(ValueError,match='exact_conflict_context_choice_required'):
        escape._conflict_context_key(packet(),'target',{'peer':'missing'})


def test_initial_refinement_progress_funds_new_frontier_without_cluster_actions():
    p=packet();initial=escape._menu_copper_binding(p)
    attempted={escape._conflict_context_key(p,'target',{'peer':'a'})}
    new=copy.deepcopy(p['domains']['peer'][0]);new['id']='new';new['ops'][0]['end_nm']=[9,1]
    p['domains']['peer'].append(new)
    assert escape._followup_producer_slots(initial,p,[])==4
    assert escape._conflict_context_key(p,'target',{'peer':'new'}) not in attempted
    assert escape._conflict_context_key(p,'target',{'peer':'a'}) in attempted


def test_no_progress_and_duplicate_renames_do_not_fund_followup_loop():
    p=packet();initial=escape._menu_copper_binding(p)
    assert escape._followup_producer_slots(initial,p,[])==0
    duplicate=copy.deepcopy(p['domains']['peer'][0]);duplicate.update(id='duplicate',cost=999)
    p['domains']['peer'].append(duplicate)
    assert escape._followup_producer_slots(initial,p,[dict(added_choices=1)])==0


def test_followup_never_creates_more_than_unused_original_slots():
    p=packet();initial=escape._menu_copper_binding(p)
    p['domains']['peer'][0]['ops'][0]['end_nm']=[7,1]
    for used in range(5):
        assert escape._followup_producer_slots(initial,p,[{}]*used)==4-used
    with pytest.raises(ValueError,match='bounded_cooperative_action_accounting_required'):
        escape._followup_producer_slots(initial,p,[{}]*5)
