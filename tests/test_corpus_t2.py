"""T2 corpus runs all calculus families through their production loader."""
from pathlib import Path
import pytest
import run as R
import cascheck as C


def rows():
    return [line.split('\t') for line in Path(__file__).with_name('corpus').joinpath('t2.tsv').read_text().splitlines() if line and not line.startswith('#')]


@pytest.mark.parametrize('command,expected', rows())
def test_corpus(command, expected):
    C.fresh()
    C.equivalent(C.answer(command), expected)


def test_mixed_calculus_session():
    C.fresh()
    for command, expected in rows() * 2:
        C.equivalent(C.answer(command), expected)
        assert not R.LIVE and not R.NEEDED and not R.PINNED


@pytest.mark.parametrize('command', ['limit(x,x,[1,2])', 'integrate(x,x,[1,2],3)', 'taylor(x,x,[1,2],2)'])
def test_centers_and_bounds_are_scalar(command):
    C.fresh()
    assert R.go(('eval', command))[0] == 'msg'
