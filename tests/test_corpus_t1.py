"""T1 milestone oracle acceptance through run.go, with the real lazy families."""
from pathlib import Path
import pytest
import cascheck as C
import node as K
import run as R

ROWS = [line.split('\t') for line in (Path(__file__).parent / 'corpus/t1.tsv').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')]


@pytest.mark.oracle
@pytest.mark.parametrize('source,check,reference,note', ROWS)
def test_t1_corpus(source, check, reference, note):
    C.fresh()
    rec = R.go(('eval', source))
    assert K.NN == K.BASE and not R.LIVE and not R.PINNED
    assert rec[0] == ('msg' if check == 'msg' else 'ans'), (source, rec)
    if check in ('text', 'msg'):
        assert rec[1] == reference
    elif check == 'roots':
        ours = [part.split('=', 1)[1] for part in rec[1].split(',')]
        want = reference.split(';')
        assert len(ours) == len(want), rec
        for a, b in zip(ours, want):
            C.equivalent(a, b)
    else:
        C.equivalent(rec[1], reference)


def test_t1_session():
    C.fresh()
    assert C.answer('a=3') == '3'
    C.equivalent(C.answer('a^2+1'), '10')
    assert C.answer('ans()+2') == '12'
    assert R.go(('eval', 'f(x):=x^2+a'))[0] == 'msg'
    assert C.answer('f(4)') == '19'
    assert R.go(('eval', 'purge(a,f)'))[0] == 'msg'
    assert not R.VARS and not R.FUNCS
    assert all(type(entry[1]) is str for entry in R.HIST)
