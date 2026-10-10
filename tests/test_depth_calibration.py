"""Depth-checker calibration (DESIGN.md 20.2) and the conftest harness (20.1).

The PROBE4 numbers are device measurements [V]. The PROBE6 'ingen' number is the design's
assumption until PROBE6 runs on the EVO (assumed to pass for now: send() costs no frame).
"""
import os
import shutil
import textwrap

import pytest

import evodepth
import framelint
from depth_shapes import levels_shapes as L
from depth_shapes import probe4_shapes as s4
from depth_shapes import probe6_shapes as s6

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPES = os.path.join(HERE, 'depth_shapes')
SUPPORT = os.path.join(HERE, 'support')


def checker(**kw):
    kw.setdefault('base', 0)
    kw.setdefault('budget', 99)
    return evodepth.DepthChecker([SHAPES], **kw)


def run_probe4(**kw):
    with checker(**kw):
        return {
            'plain': s4.measure(s4.plain),
            'mutl': s4.measure(s4.ping),
            'meth': s4.measure(s4.C().m),
            'gen': s4.measure(s4.run_gen),
            'nest3': s4.measure(s4.w1),
            'lcomp': s4.measure(s4.lc),
        }


# -- PROBE4 -----------------------------------------------------------------------------------

def test_matches_probe4_on_device():
    got = run_probe4(native_penalty=0, dunder_penalty=0)
    assert got == {'plain': 9, 'mutl': 9, 'meth': 9, 'gen': 8, 'nest3': 6, 'lcomp': 5}


def test_strict_mode_is_never_more_lenient_than_device():
    got = run_probe4()                  # native and dunder penalties 1
    assert got['gen'] == 7              # list() charged one frame; the device charged 0
    assert got['plain'] == 9 and got['nest3'] == 6


def test_hard_limit_raises_inside_code_under_test():
    with checker(native_penalty=0, budget=8) as dc:
        n = s4.measure(s4.plain)
    assert n == 9                       # measure 1 + plain 2..10; the 11th raised
    assert dc.max_depth == 11           # the deepest frame *attempted*
    assert max(dc.violations)[0] == 11


# -- PROBE6 trampoline shapes -----------------------------------------------------------------

def test_ingen_send_costs_no_frame():
    with checker(native_penalty=1, gen_penalty=0):
        assert s6.tryit(s6.INGEN) == 6  # tryit 1 > lambda 2 > tramp 3 > gen 4 > plain x6


def test_ingen_with_gen_penalty_one():
    with checker(native_penalty=1, gen_penalty=1):
        assert s6.tryit(s6.INGEN) == 5  # what PROBE6 would print if send() cost a frame


def test_trampoline_200_levels_stays_at_depth_2():
    with checker(native_penalty=1, gen_penalty=0) as dc:
        s6.cnt[0] = 0
        r = s6.tramp(s6.gchild(200))
    assert (r, s6.cnt[0]) == (200, 201)
    assert dc.max_depth == 2            # tramp 1, every generator resumed at 2


def test_trampoline_strict_counts_one_more():
    with checker(native_penalty=1, gen_penalty=1) as dc:
        s6.tramp(s6.gchild(50))
    assert dc.max_depth == 3


def test_throw_resumes_at_send_depth():
    with checker(gen_penalty=0) as dc:
        assert s6.t_throw() == '1 2'
    assert dc.max_depth == 2            # t_throw 1, gthrow 2 (send and throw)
    with checker(gen_penalty=1) as dc:
        s6.t_throw()
    assert dc.max_depth == 3


# -- levels: automatic base and the per-frame assertion ---------------------------------------

@pytest.fixture(scope='module')
def levels():
    return framelint.level_table(SHAPES)


def test_level_table_reads_annotations(levels):
    path = evodepth.norm_path(L.__file__)
    assert levels[(path, 'mk')] == 7          # module default
    assert levels[(path, 'add_')] == 6
    assert levels[(path, 'g_check')] == 2
    assert levels[(path, 'go')] == 1
    assert (evodepth.norm_path(s4.__file__), 'plain') not in levels   # unannotated


def test_deepest_planned_chain_is_7(levels):
    with checker(levels=levels, budget=8) as dc:
        L.go(3)
    assert dc.max_depth == 7
    assert dc.max_stack[-1].startswith('levels_shapes.py:mk@7')
    assert dc.violations == [] and dc.level_violations == []


def test_strict_mode_chain_is_8_within_budget(levels):
    with checker(levels=levels, budget=8, gen_penalty=1) as dc:
        L.go(3)
    assert dc.check_levels is False           # strict runs check only the budget
    assert dc.max_depth == 8
    assert dc.violations == []


def test_automatic_base_uses_declared_level(levels):
    with checker(levels=levels) as dc:
        _, d6, st = dc.measure(L.add_, 1)
        _, d4, _ = dc.measure(L.inst, 1)
    assert d6 == 7 and st[-2:] == ('levels_shapes.py:add_@6', 'levels_shapes.py:mk@7')
    assert d4 == 7
    assert dc.level_violations == []


def test_generator_called_from_a_test_starts_at_level_2(levels):
    with checker(levels=levels) as dc:
        g = L.g_check(1)
        sub = next(g)
        assert type(sub).__name__ == 'generator'
        g.close()
        sub.close()
    assert dc.max_depth == 2


def test_device_base_overrides_automatic_base(levels):
    with checker(levels=levels, base=2, auto_base=False) as dc:
        _, d, _ = dc.measure(L.add_, 1)
    assert d == 4                              # add_ at 3, mk at 4


def test_level_violation_l3_to_l3(levels):
    with checker(levels=levels) as dc:
        L.go_bad(1)                            # go_bad 2 > bad_diff 3 > diff 4 (> L3)
    names = [st[-1] for (d, lv, st) in dc.level_violations]
    assert 'levels_shapes.py:diff@4' in names
    msgs = evodepth.failures(dc)
    assert any('declared level 3' in m for m in msgs)


def test_budget_violation_reported(levels):
    with checker(levels=levels, base=5, auto_base=False, budget=8) as dc:
        L.diff(1)                              # diff 6, inst 7, mul_ 8, add_ 9, mk 10
    assert dc.max_depth == 10
    assert max(dc.violations)[0] == 10
    assert 'budget 8' in evodepth.failures(dc)[0]


def test_generator_exit_is_not_counted(levels):
    # A generator finalized while a deep frame runs must not count as running there.
    with checker(levels=levels) as dc:
        g = L.g_check(1)
        sub = next(g)
        box = [g, sub]
        del g, sub
        L.drop(box)                           # drop at 7: g closes in there
    assert dc.level_violations == []
    assert dc.max_depth == 7


def test_measure_restores_the_running_maximum(levels):
    with checker(levels=levels) as dc:
        L.go(1)
        _, d, _ = dc.measure(L.mk, 1)
    assert d == 7 and dc.max_depth == 7


# -- the conftest harness, run in a subprocess on a fake tree --------------------------------

FAKE_NODE = '''
#@L 7
N = [None] * 16
H = [0] * 16
V = [0] * 16
NN = 1
BASE = 1
ESC = None  #@native
MEMFREE = None  #@native
ONRESET = None  #@native


def reset():
    global NN
    if ONRESET is not None:
        ONRESET()
    for i in range(1, 16):
        N[i] = None
    NN = BASE
'''

FAKE_RUN = '''
#@L 2
import node as K
SIMPBUG = 0


def go(job):  #@L 1
    if job == 'leak':
        K.N[1] = (2, 'x')
        K.H[1] = 0
        K.NN = 2
        return ('expr', 'x', None, 0)
    if job == 'bug':
        return ('msg', 'internal error: TypeError', None, 0)
    return ('expr', '1', None, 0)
'''

FAKE_DEEP = '''
#@L 7
def a1(n):  #@L 3
    return a2(n)


def a2(n):  #@L 3
    return n


def c3(n):  #@L 5
    return c4(n)


def c4(n):  #@L 6
    return c5(n)


def c5(n):
    return n
'''

FAKE_TESTS = '''
import pytest
import node
import run
import deep


def test_ok():
    assert deep.c3(1) == 1


def test_level_violation():
    deep.a1(1)


@pytest.mark.device_base(6)
def test_budget():
    deep.c3(1)


def test_invariants_and_reset():
    node.N[1] = ('bad',)
    node.NN = 2


def test_reset_happened():
    assert node.NN == node.BASE and node.N[1] is None


def test_reset_scan():
    node.N[1] = ('bad',)
    node.NN = 2
    node.reset()                   # as R.go does at the end of every command


def test_hooks_injected():
    assert node.ESC() is False and node.MEMFREE() > 0


def test_full_command_must_reset():
    run.go('leak')


def test_internal_error_fails():
    run.go('bug')


@pytest.mark.allow_internal_error
def test_internal_error_allowed():
    run.go('bug')


def test_simpbug():
    run.SIMPBUG = 1


def test_simpbug_zeroed():
    assert run.SIMPBUG == 0


def test_measure_fixture(evodepth):
    r, d, st = evodepth.measure(deep.c3, 5)
    assert r == 5 and d == 7


@pytest.mark.no_depth
def test_no_depth():
    deep.a1(1)


@pytest.mark.strict_depth
def test_strict_skips_level_assertion():
    deep.a1(1)
'''


@pytest.mark.slow
@pytest.mark.no_depth
def test_conftest_harness(pytester):
    root = pytester.path
    (root / 'src').mkdir()
    (root / 'tests').mkdir()
    shutil.copytree(SUPPORT, str(root / 'tests' / 'support'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy(os.path.join(HERE, 'conftest.py'), str(root / 'tests' / 'conftest.py'))
    (root / 'src' / 'node.py').write_text(textwrap.dedent(FAKE_NODE).lstrip())
    (root / 'src' / 'run.py').write_text(textwrap.dedent(FAKE_RUN).lstrip())
    (root / 'src' / 'deep.py').write_text(textwrap.dedent(FAKE_DEEP).lstrip())
    (root / 'tests' / 'test_fake.py').write_text(FAKE_TESTS)
    res = pytester.runpytest_subprocess('tests', '-p', 'no:cacheprovider', '-rA')
    out = res.stdout.str()
    outcomes = {}
    for line in res.stdout.lines:
        for word in ('PASSED', 'FAILED'):
            if line.startswith(word + ' '):
                name = line.split('::')[-1].split(' ')[0]
                outcomes[name] = word
    assert outcomes == {
        'test_ok': 'PASSED',
        'test_level_violation': 'FAILED',
        'test_budget': 'FAILED',
        'test_invariants_and_reset': 'FAILED',
        'test_reset_happened': 'PASSED',
        'test_reset_scan': 'FAILED',
        'test_hooks_injected': 'PASSED',
        'test_full_command_must_reset': 'FAILED',
        'test_internal_error_fails': 'FAILED',
        'test_internal_error_allowed': 'PASSED',
        'test_simpbug': 'FAILED',
        'test_simpbug_zeroed': 'PASSED',
        'test_measure_fixture': 'PASSED',
        'test_no_depth': 'PASSED',
        'test_strict_skips_level_assertion': 'PASSED',
    }, out
    assert 'deep.py:a2@4' in out and 'declared level 3' in out
    assert 'device call depth 9 > budget 8' in out
    assert '[slots]' in out
    assert 'invariants violated before a reset' in out
    assert 'not BASE' in out
    assert 'internal error: TypeError' in out
    assert 'SIMPBUG' in out


def test_session_check_for_keyscript_runs():
    import sys
    from types import SimpleNamespace as NS
    C = sys.modules['conftest']
    ks = sys.modules.get('keyscript')
    if ks is not None:
        assert C._session_check in ks.AFTER_RUN
    bad = NS(mods={'node': NS(N=[None] * 4, H=[0] * 4, V=[0] * 4, NN=2, BASE=1),
                   'run': NS(HIST=[('1+', ('msg', 'internal error: TypeError', None, 0))],
                             SIMPBUG=1)})
    with pytest.raises(AssertionError) as ei:
        C._session_check(bad)
    msg = str(ei.value)
    assert '[slots]' in msg and 'not BASE' in msg
    assert 'internal error: TypeError' in msg and 'SIMPBUG' in msg
    good = NS(mods={'node': NS(N=[None] * 4, H=[0] * 4, V=[0] * 4, NN=1, BASE=1),
                    'run': NS(HIST=[('1+1', ('expr', '2', '2', 0))], SIMPBUG=0)})
    C._session_check(good)
