"""Source-window ports retain pair polarity, station and heading, not refdes."""
from copy import deepcopy
import pytest
import cec_pair_source_windows as windows


def source(quarter=0,mirror=False):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+30000000,y+30000000]
    pair=dict(p='a'+str(quarter),n='b'+str(quarter),width=.25,gap=.2)
    rows=[];bad={}
    for index,net in enumerate((pair['p'],pair['n'])):
        y=index*450000;points=[(0,y),(4000000,y),(5000000,y+1000000),
            (6000000,y+1000000),(7000000,y),(11000000,y)]
        bad[net]=[net+'1',net+'2',net+'3']
        rows += [dict(uuid=net+str(i),net=net,layer_id=8,width_nm=250000,
            start_nm=point(*a),end_nm=point(*b)) for i,(a,b) in enumerate(zip(points,points[1:]))]
    return rows,pair,bad


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
@pytest.mark.parametrize('reverse_rows',(False,True))
def test_normalized_ports_are_common_cardinal_stations_with_no_source_mutation(quarter,mirror,reverse_rows):
    rows,pair,bad=source(quarter,mirror)
    if reverse_rows:
        rows=list(reversed(rows))
        for row in rows:row['start_nm'],row['end_nm']=row['end_nm'],row['start_nm']
    before=deepcopy(rows);plans=windows.candidates(rows,pair,bad)
    assert plans and rows==before
    for plan in plans:
        for station in (plan['entry'],plan['exit']):
            axis=station['axis'];assert station['p'][axis]==station['n'][axis]
            assert abs(station['p'][1-axis]-station['n'][1-axis])==450000
            assert sum(abs(v) for v in station['heading'])==1
        assert not plan['admission_granted']
        assert all(row['uuid'] not in bad[net] for container in ('prefix','suffix')
            for net,pieces in plan[container].items() for row in pieces)


@pytest.mark.parametrize('fault',('branch','disconnected','duplicate','self_loop','wrong_width',
    'different_face','foreign_net','foreign_bad','one_member','invalid_bad','invalid_row','same_net'))
def test_ambiguous_partial_or_changed_source_context_is_not_a_window(fault):
    rows,pair,bad=source()
    if fault=='branch':
        row=deepcopy(rows[0]);row.update(uuid='extra',start_nm=list(rows[0]['end_nm']),end_nm=[34000000,31000000]);rows.append(row)
    elif fault=='disconnected':rows[1]['start_nm'][0]+=1000
    elif fault=='duplicate':rows[-1]['uuid']=rows[0]['uuid']
    elif fault=='self_loop':rows[0]['end_nm']=tuple(rows[0]['start_nm'])
    elif fault=='wrong_width':rows[0]['width_nm']=249999
    elif fault=='different_face':rows[0]['layer_id']=6
    elif fault=='foreign_net':rows[0]['net']='other'
    elif fault=='foreign_bad':bad[pair['p']].append('absent')
    elif fault=='one_member':bad.pop(pair['n'])
    elif fault=='invalid_bad':bad[pair['n']]='not a set'
    elif fault=='invalid_row':rows[0]=None
    else:pair['n']=pair['p']
    with pytest.raises(ValueError):windows.candidates(rows,pair,bad)


@pytest.mark.parametrize('limit',(1,2,8,16))
def test_finite_limit_and_literal_endpoint_fragments(limit):
    rows,pair,bad=source();plans=windows.candidates(rows,pair,bad,limit=limit)
    assert 0<len(plans)<=limit
    originals={r['uuid']:r for r in rows}
    for plan in plans:
        for direction in ('prefix','suffix'):
            for pieces in plan[direction].values():
                for row in pieces:
                    old=originals[row['uuid']]
                    assert all(row[key]==old[key] for key in ('uuid','net','width_nm','layer_id'))


@pytest.mark.parametrize('fault',('limit','guard','pair_width','pair_gap','nan','row_bound'))
def test_geometric_and_proposal_bounds_are_not_waived(fault):
    rows,pair,bad=source();kwargs={}
    if fault=='limit':kwargs['limit']=65
    elif fault=='guard':kwargs['guard_nm']=0
    elif fault=='pair_width':pair['width']=True
    elif fault=='pair_gap':pair['gap']=0.
    elif fault=='nan':pair['width']=float('nan')
    else:rows*=30
    with pytest.raises(ValueError):windows.candidates(rows,pair,bad,**kwargs)


def test_empty_or_unbracketed_native_obstruction_is_not_a_global_no_path_proof():
    rows,pair,bad=source();assert windows.candidates(rows,pair,{net:[] for net in bad})==[]
    for net in bad:bad[net]=[r['uuid'] for r in rows if r['net']==net]
    assert windows.candidates(rows,pair,bad)==[]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
@pytest.mark.parametrize('step',(250000,500000))
def test_query_fragments_partition_exact_original_integer_segments(quarter,mirror,step):
    rows,pair,bad=source(quarter,mirror);before=deepcopy(rows)
    pieces=windows.subdivide(rows,max_span_nm=step)
    assert rows==before and len(pieces)>len(rows)
    assert len({r['uuid'] for r in pieces})==len(pieces)
    for parent in rows:
        owned=[r for r in pieces if r['source_native_track_uuid']==parent['uuid']]
        assert owned[0]['start_nm']==parent['start_nm'] and owned[-1]['end_nm']==parent['end_nm']
        assert all(a['end_nm']==b['start_nm'] for a,b in zip(owned,owned[1:]))
        dx=parent['end_nm'][0]-parent['start_nm'][0];dy=parent['end_nm'][1]-parent['start_nm'][1]
        for row in owned:
            assert (row['start_nm'][0]-parent['start_nm'][0])*dy==(row['start_nm'][1]-parent['start_nm'][1])*dx
            assert all(row[k]==parent[k] for k in ('net','layer_id','width_nm'))


@pytest.mark.parametrize('fault',('double_subdivide','duplicate_parent','zero_parent','budget','step','invalid_parent'))
def test_query_subdivision_never_snaps_or_silently_drops_a_parent(fault):
    rows,pair,bad=source();kwargs={}
    if fault=='double_subdivide':rows=windows.subdivide(rows)
    elif fault=='duplicate_parent':rows.append(deepcopy(rows[0]))
    elif fault=='zero_parent':rows[0]['end_nm']=rows[0]['start_nm']
    elif fault=='budget':kwargs['max_fragments']=1
    elif fault=='step':kwargs['max_span_nm']=0
    else:rows[0]=None
    with pytest.raises(ValueError):windows.subdivide(rows,**kwargs)


def test_irreducible_native_lattice_stroke_stays_whole_not_rounded():
    row=dict(uuid='source',net='p',layer_id=8,width_nm=250000,
        start_nm=[0,0],end_nm=[1000001,1000000])
    result=windows.subdivide([row],max_span_nm=250000)
    assert len(result)==1 and result[0]['start_nm']==row['start_nm'] and result[0]['end_nm']==row['end_nm']


@pytest.mark.parametrize('offset',(1000,50000,200000))
def test_phase_offset_query_boundaries_do_not_erase_legal_pair_flats(offset):
    rows,pair,_=source()
    # Lengthening only the first N stroke changes its exact subdivision
    # phase, not the two members' geometric common flat or lane separation.
    nrows=[r for r in rows if r['net']==pair['n']]
    nrows[0]['start_nm'][0]-=offset
    fragments=windows.subdivide(rows)
    bad={net:[r['uuid'] for r in fragments if r['net']==net
        and r['source_native_track_uuid'] in (net+'1',net+'2',net+'3')] for net in (pair['p'],pair['n'])}
    assert windows.candidates(fragments,pair,bad)


def test_small_menu_explores_both_handoff_frontiers_not_only_one_blocked_start():
    rows,pair,_=source();fragments=windows.subdivide(rows)
    bad={net:[r['uuid'] for r in fragments if r['net']==net
        and r['source_native_track_uuid'] in (net+'1',net+'2',net+'3')] for net in (pair['p'],pair['n'])}
    plans=windows.candidates(fragments,pair,bad,limit=4)
    assert len(plans)==4
    assert len({(q['entry']['p'],q['entry']['n']) for q in plans})>=2


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_small_portfolio_keeps_both_exact_boundaries_of_source_flat(quarter,mirror):
    rows,pair,_=source(quarter,mirror);fragments=windows.subdivide(rows)
    bad={net:[r['uuid'] for r in fragments if r['net']==net
        and r['source_native_track_uuid'] in (net+'1',net+'2',net+'3')] for net in (pair['p'],pair['n'])}
    plans=windows.candidates(fragments,pair,bad,limit=4);groups={}
    for q in plans:
        port=q['entry'];key=(port['p_index'],port['n_index'])
        groups.setdefault(key,set()).add((port['p'],port['n']))
    assert any(len(points)>=2 for points in groups.values())
    assert len({(q['exit']['p'],q['exit']['n']) for q in plans})>=2


@pytest.mark.parametrize('prefer_exit',(False,True))
def test_native_feedback_schedule_diversifies_the_failed_endpoint_first(prefer_exit):
    rows,pair,_=source();pieces=windows.subdivide(rows)
    bad={net:[r['uuid'] for r in pieces if r['net']==net
        and r['source_native_track_uuid'] in (net+'1',net+'2',net+'3')] for net in (pair['p'],pair['n'])}
    plans=windows.candidates(pieces,pair,bad,limit=64);history=[];selected=[]
    side='exit' if prefer_exit else 'entry'
    for _ in range(8):
        index=windows.next_candidate(plans,history,prefer_exit=prefer_exit)
        assert index is not None and index not in history
        history.append(index);selected.append(tuple(plans[index][side]['p']))
    assert len(set(selected))==len(selected)
    assert windows.next_candidate(plans,list(range(len(plans)))) is None
