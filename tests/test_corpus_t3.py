"""Mixed T3 integration using the real parser/loader/runner/printer."""
from pathlib import Path
import pytest
import run as R
import cascheck as C


def rows():
    return [line.split('\t') for line in Path(__file__).with_name('corpus').joinpath('t3.tsv').read_text().splitlines() if line and not line.startswith('#')]


@pytest.mark.parametrize('command,expected', rows())
def test_corpus(command, expected):
    C.fresh()
    C.equivalent(C.answer(command), expected)


def test_mixed_session_lifetimes():
    C.fresh()
    for command, expected in rows():
        C.equivalent(C.answer(command), expected)
        assert not R.LIVE and not R.NEEDED and not R.PINNED


def test_divergence_never_becomes_principal_value():
    C.fresh()
    for command in ('integrate(1/x,x,-1,1)', 'integrate(1/x^2,x,-1,1)', 'sum(k,k,1,oo)'):
        rec = R.go(('eval', command))
        assert rec[0] == 'msg' and 'Diverg' in rec[1]
    assert C.answer('sum(1/k,k,1,oo)') == 'oo'
