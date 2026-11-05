"""The per-case guard restores prior native values, never a numerical floor."""
import pcbnew
import pytest
from conftest import preserve_borrowed_default_scalars


def values():
    owner=pcbnew.BOARD();settings=owner.GetDesignSettings()
    default=settings.m_NetSettings.GetDefaultNetclass()
    return(default.GetTrackWidth(),default.GetClearance(),
        default.GetViaDiameter(),default.GetViaDrill())


@pytest.mark.parametrize('raises',[False,True])
@pytest.mark.parametrize('before',[(213000,237000,713000,313000),
    (527000,251000,947000,503000)])
def test_guard_restores_all_actual_prior_scalars_for_new_unrelated_boards(before,raises):
    owner=pcbnew.BOARD();settings=owner.GetDesignSettings()
    default=settings.m_NetSettings.GetDefaultNetclass()
    for setter,value in zip((default.SetTrackWidth,default.SetClearance,
            default.SetViaDiameter,default.SetViaDrill),before):setter(value)
    try:
        with preserve_borrowed_default_scalars():
            for setter,value in zip((default.SetTrackWidth,default.SetClearance,
                    default.SetViaDiameter,default.SetViaDrill),
                    (before[0]+17000,before[1]+19000,before[2]+23000,before[3]+11000)):
                setter(value)
            assert values()!=before
            if raises:raise RuntimeError('synthetic test body failed')
    except RuntimeError as exc:
        assert raises and str(exc)=='synthetic test body failed'
    assert values()==before


def test_autouse_guard_surrounds_each_test_case(request):
    # This tests the wiring as well as the separately exercised finally body.
    assert 'isolate_native_default_scalars' in request.fixturenames
