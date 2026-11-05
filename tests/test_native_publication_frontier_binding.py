"""Published plot bytes alone cannot qualify a stale selected dashboard ID."""
from copy import deepcopy
import pytest
from root_native_publication_http_check_20261010 import assert_frontier_review_metadata


@pytest.mark.parametrize('hint', ['renamed-one', 'totally-different-board'])
def test_actual_review_identity_and_native_counts_must_match(hint):
    state = {'state':{'boards':{hint:{'current_opens':7, 'scored_drc':3,
        'dashboard_id':'new-source-bound-review'}}}}
    row = {'fresh_native_counts':{'opens':7, 'scored_drc':3},
        'review':{'id':'new-source-bound-review'}}
    assert assert_frontier_review_metadata(state, hint, row) is None


@pytest.mark.parametrize('field,value', [('dashboard_id','old-review'),
    ('current_opens',8), ('scored_drc',4), ('current_opens',True),
    ('current_opens',7.), ('scored_drc',-1)])
def test_old_review_or_stale_native_counts_refuse_even_if_plot_bytes_match(field,value):
    state = {'state':{'boards':{'renamed':{'current_opens':7, 'scored_drc':3,
        'dashboard_id':'new-source-bound-review'}}}}
    row = {'fresh_native_counts':{'opens':7, 'scored_drc':3},
        'review':{'id':'new-source-bound-review'}}
    altered = deepcopy(state); altered['state']['boards']['renamed'][field] = value
    with pytest.raises(ValueError, match='frontier_review_id_or_counts_stale'):
        assert_frontier_review_metadata(altered, 'renamed', row)
