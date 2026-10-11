"""Command-boundary memory contracts, independent of unrun EVO heap measurements."""
import pytest
import cascheck as C
import node as K
import run as R


def test_repeated_mixed_commands_release_arena():
    C.fresh()
    commands = ('factor(x^6-1)', 'solve(x^2-2,x)', 'expand((x+y)^4)', 'simplify(sin(x)^2+cos(x)^2)')
    for i in range(24):
        C.answer(commands[i % len(commands)])
        assert K.NN == K.BASE and not R.LIVE and not R.PINNED and not R.NEEDED
    assert len(R.HIST) <= R.HISTMAX
    assert all(isinstance(entry[1], str) for entry in R.HIST)


def test_oversized_expansion_fails_cleanly_and_next_command_works():
    C.fresh()
    rec = R.go(('eval', 'expand((a+b+c+d+f+g)^20)'))
    assert rec[0] == 'msg' and rec[1] in ('too large', 'expression too complex', 'Out of memory')
    assert K.NN == K.BASE and not R.LIVE
    assert C.answer('2+3') == '5'
