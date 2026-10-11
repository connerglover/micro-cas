"""Forms use original inert answers and survive changes to session definitions."""
import pytest
import run as R
import cascheck as C


@pytest.fixture(autouse=True)
def fresh():
    C.fresh()


def test_cycle_exact_number_and_ans():
    C.answer('sqrt(2)')
    r = R.go(('form', 0))
    assert r[0] == 'ans' and r[1].startswith('1.414213562')
    assert R.ANS == r[1] and len(R.HIST) == 1
    for _ in range(6):
        R.go(('form', 0))
    assert R.HIST[0][5][0] == ('exact', 'sqrt(2)')


def test_old_expression_is_inert_after_assignment():
    original = C.answer('expand((a+1)^2)')
    C.answer('a=3')
    r = R.go(('form', 0))
    assert 'a' in r[1]
    assert R.HIST[0][5][0] == ('exact', original)


def test_held_calculus_does_not_reexecute():
    original = C.answer('integrate(e^(x^2),x)')
    assert R.go(('form', 0))[1] == original


def test_forms_do_not_append_history():
    C.answer('(x+1)^2')
    for _ in range(8):
        assert R.go(('form', 0))[0] == 'ans'
    assert len(R.HIST) == 1
