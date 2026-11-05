import pytest
from shapely.geometry import box
from cec_cell_packing import pack_translations

def test_bounded_cooperative_packing_preserves_cells():
    groups={
        'first':dict(members=[box(0,0,2,2),box(3,0,4,1)],bounds=(0,0,10,10)),
        'second':dict(members=[box(0,0,3,3)],bounds=(0,0,10,10))}
    result=pack_translations(groups,[box(0,0,5,5)],clearance=.2)
    assert result['ok'] and not result['admission_authority']
    assert groups['first']['members'][0].bounds==(0,0,2,2)

def test_impossible_or_budget_exhausted_is_not_outline_growth():
    groups={'cell':dict(members=[box(0,0,2,2)],bounds=(0,0,1,1))}
    assert not pack_translations(groups,[box(-10,-10,10,10)])['ok']
    with pytest.raises(ValueError):pack_translations(groups,[],max_nodes=0)

@pytest.mark.parametrize('bounds', [(0,0,float('nan'),1),(2,0,1,1),(0,1,2,0)])
def test_invalid_domains_fail_closed(bounds):
    with pytest.raises(ValueError):
        pack_translations({'cell':dict(members=[box(0,0,1,1)],bounds=bounds)},[])

def test_search_never_exceeds_budget():
    result=pack_translations({'cell':dict(members=[box(0,0,1,1)],bounds=(0,0,5,5))},
                             [box(0,0,2,2)],max_nodes=1)
    assert not result['ok'] and result['nodes']==1 and result['exhausted']
def test_degenerate_edge_slide_domain_is_not_empty():
    from shapely.geometry import box
    from cec_cell_packing import pack_translations
    r=pack_translations({'row':dict(members=[box(1,1,3,3)],
        bounds=(-2,0,0,0),preferred=(0,0))},[box(2.9,2,5,4)],clearance=.2)
    assert r['ok'] and r['translations']['row'][1]==0
    assert r['translations']['row'][0]<-.29


def test_line_domain_keeps_directed_halfplane():
    from cec_cell_packing import contact_translation_sites
    r=contact_translation_sites([(0,0,1,1)],bounds=(-2,0,2,0),
        translation_halfplanes=[(1,0,1)],preferred_origin=(0,0))
    assert r and all(x>=1 for x,y in r)
