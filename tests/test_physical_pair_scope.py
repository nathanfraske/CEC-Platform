"""Explicit one-pair measurements equal the unchanged full release oracle."""
import pcbnew
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_pair_skew as skew
from test_pair_axis_miter import fixture
from test_field_proposals import track


def two_pairs(tmp_path,quarter=0,usb_fault=False):
    source,_,_=fixture(tmp_path,angle=quarter*90)
    b=pcbnew.LoadBoard(str(source))
    for index,net in enumerate(('/second/USB_DP','/second/USB_DM')):
        y=16.+index*.33;end=6.+(skew.evaluate('usb',0.,0.)['limit_mm']+.5 if usb_fault and index else 0)
        t=track(b,net,(2,y),(end,y),width=.2)
        for x in (2.,end):
            f=pcbnew.FOOTPRINT(b);f.SetReference('END'+str(index)+str(x));b.Add(f)
            p=pcbnew.PAD(f);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            p.SetNet(b.FindNet(net));f.Add(p)
    return source,b


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('usb_fault',[False,True])
@pytest.mark.parametrize('kind',['can','usb'])
def test_selected_pair_is_exactly_the_full_oracle_row_with_no_board_mutation(tmp_path,quarter,usb_fault,kind):
    source,b=two_pairs(tmp_path,quarter,usb_fault);frozen=field._field_snapshot_inventory(b)
    full=constraints.high_speed_pair_summary(str(source),board=b)
    assert len(full['pairs'])==2
    selected=next(q for q in full['pairs'] if q['kind']==kind);scope=(selected['p'],selected['n'])
    scoped=constraints.high_speed_pair_summary(str(source),board=b,only_pair=scope)
    assert scoped['pairs']==[selected] and scoped['ok']==(not selected['violations'])
    assert not scoped['all_board_pairs_evaluated'] and not scoped['whole_board_pair_qualification']
    assert scoped['explicit_existing_pair_scope']==list(scope)
    assert 'explicit_existing_pair_scope' not in full and full==constraints.high_speed_pair_summary(str(source),board=b)
    assert field._field_snapshot_inventory(b)==frozen
    if usb_fault:assert any('skew' in e for q in full['pairs'] if q['kind']=='usb' for e in q['violations'])


@pytest.mark.parametrize('scope',[True,1,[],['a'],['a','a'],['a',True],['a','b'],('/second/USB_DM','/second/USB_DP')])
def test_unknown_reversed_coerced_or_missing_pair_cannot_yield_a_subset_verdict(tmp_path,scope):
    source,b=two_pairs(tmp_path)
    with pytest.raises(ValueError):constraints.high_speed_pair_summary(str(source),board=b,only_pair=scope)


def test_explicit_scope_cannot_make_a_pairless_board_inapplicable_instead_of_failing():
    with pytest.raises(ValueError):constraints.high_speed_pair_summary('',board=pcbnew.BOARD(),only_pair=('p','n'))
