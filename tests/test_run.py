"""T1.6 runner and session (DESIGN 7.9, 7.11, 10, 15.1, 18.4-18.6, 20.12).

Acceptance (section 21.4): the trampoline protocol (10.2) incl. CasSoft -> None, TICK and MAXGEN;
regions; budget and cancel; need/drop/eviction with fake sizes, live pins and families; the 7.9
rules incl. purge; the text-only session; records; R.go never raises (the 20.12 fuzz and
injection cases, KeyboardInterrupt re-raised after the reset); the MemoryError path (mk patched).

The lazy modules are fakes served by a meta-path finder (the real ones belong to later tasks),
and the printer's record is a test-side reference printer (``ptext``), so these tests pin the
runner alone. The ``realprinter`` tests run the real ``PR.record`` once T1.7 has written it.
"""
import importlib.abc
import importlib.util
import os
import sys
import textwrap
import types

import pytest

import gen
import node as K
from test_node import arena  # noqa: F401 - the debug-arena fixture (DESIGN 20.4)
import parse as P
import printer as PR
import run as R

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NOAUTO = P.F_NOAUTO
REAL_RECORD = getattr(PR, 'record', None)
ORIG_CMDS = dict(R.CMDS)

# -- a reference printer (test side): canonical, fully parenthesized, re-parseable text ----------

FNAME = {}
for _n, _op in P.ONEARG.items():
    FNAME[_op] = _n
CONNAME = ('pi', 'e', 'oo', 'undef', 'true', 'false')
RELNAME = {K.EQ: '=', K.NE: '!=', K.LT: '<', K.LE: '<='}
JOBS = []                   # every job the runner handed to the printer
TEXTCALLS = [0]
TEXTFAIL = [0]              # raise MemoryError at this ptext call (0: never)


def ptext(e):
    TEXTCALLS[0] += 1
    if TEXTCALLS[0] == TEXTFAIL[0]:
        raise MemoryError()
    t = K.N[e]
    op = t[0]
    if op == K.NUM:
        a, b, d = t[1], t[2], t[3]
        if b:
            return '((%d+%d*i)/%d)' % (a, b, d)
        if d == 1 and a >= 0:
            return str(a)
        return '(%d/%d)' % (a, d)
    if op == K.FLT:
        s = ('%r' % t[1]).replace('e', 'E')
        if t[2]:
            s = '(%s+%s*i)' % (s, ('%r' % t[2]).replace('e', 'E'))
        return '(' + s + ')' if s[0] == '-' else s
    if op == K.SYM:
        return t[1]
    if op == K.CON:
        return CONNAME[t[1]]
    if op == K.ADD:
        s = '(' + ptext(t[1])
        for j in range(2, len(t), 2):
            s += '+(%s)*(%s)' % (ptext(t[j + 1]), ptext(t[j]))
        return s + ')'
    if op == K.MUL:
        s = '(' + ptext(t[1])
        for j in range(2, len(t), 2):
            s += '*(%s)^(%s)' % (ptext(t[j]), ptext(t[j + 1]))
        return s + ')'
    if op == K.CALL:
        return '%s(%s)' % (K.N[t[1]][1], ','.join(ptext(x) for x in t[2:]))
    if op == K.LST:
        return '[' + ','.join(ptext(x) for x in t[1:]) + ']'
    if op in RELNAME:
        return '(%s%s%s)' % (ptext(t[1]), RELNAME[op], ptext(t[2]))
    if op == K.BIGO:
        return 'O(%s)' % ptext(t[1])
    if op == K.FACT:
        return '(%s)!' % ptext(t[1])
    if op in FNAME:
        return '%s(%s)' % (FNAME[op], ptext(t[1]))
    raise AssertionError('ptext: op %d' % op)


def stub_record(val, job):
    """PR.record stand-in: (kind, text, approx, flags). Flags 0: finish() must add its own."""
    JOBS.append(job)
    t = K.N[val]
    if job[3] & P.F_SOLN and (val == K.TRUE or (t[0] == K.LST and len(t) == 1)):
        return ('msg', 'every x is a solution' if val == K.TRUE else 'no solution', None, 0)
    return ('ans', ptext(val), None, 0)


# -- fake lazy modules (a meta-path finder; import counts per module) -----------------------------

class Fakes(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.src = {}
        self.imports = {}

    def find_spec(self, name, path=None, target=None):
        if name in self.src:
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__
        self.imports[name] = self.imports.get(name, 0) + 1
        code = compile(textwrap.dedent(self.src[name]), '<%s>' % name, 'exec')
        exec(code, module.__dict__)


def generic(key):
    """A fake family part: each command generator returns CALL(name, args), and logs."""
    out = ['import node as K', 'import run as R', 'import fk_log as L',
           'L.events.append(("import", %r))' % key]
    for name in sorted(ORIG_CMDS):
        e = ORIG_CMDS[name]
        if e[0] == key:
            out.append('def %s(args, ctx):' % e[1])
            out.append('    L.events.append((%r, args, list(ctx), list(R.PINNED)))' % name)
            out.append('    yield K.mk((K.CALL, K.sym(%r)) + tuple(args))' % name)
    if key == 'norm':
        out += ['def g_autosimp(e):', '    L.events.append(("autosimp", e))', '    yield e']
    if key == 'rules':
        out += ['def rset(name):', '    L.events.append(("rset", name))',
                '    K.RULECACHE[name] = {}']
    if key == 'form':
        out += ['import parse as P', 'def g_form(code, ctx):',
                '    L.events.append(("form", list(ctx)))',
                '    r = yield P.g_eval(code, ctx)', '    yield r']
    return '\n'.join(out) + '\n'


TST = '''
import node as K
import run as R
import fk_log as L

def g_val(args, ctx):
    yield args[0]
    L.events.append('resumed after its value')

def g_chain(n):
    if n > 0:
        r = yield g_chain(n - 1)
        yield K.add_([r, K.ONE])
        return
    yield K.ZERO

def g_nest(args, ctx):
    r = yield g_chain(K.N[args[0]][1])
    yield r

def g_none(args, ctx):
    return
    yield

def g_soft(args, ctx):
    raise K.Undefined()
    yield

def g_softm(args, ctx):
    raise K.CasSoft('no closed form')
    yield

def g_catch(args, ctx):
    r = yield g_soft(args, ctx)
    L.events.append(('catch', r, type(R.LASTSOFT[0]).__name__))
    yield K.sym('caught') if r is None else r

def g_tick(args, ctx):
    for i in range(K.N[args[0]][1]):
        yield R.TICK
    yield args[1]

def g_loop(args, ctx):
    while True:
        yield R.TICK

def g_junk(a, n):
    x = a
    for i in range(n):
        x = K.add_([x, K.sym('j%d' % i)])
    yield K.add_([a, K.ONE])

def g_scope(args, ctx):
    m = K.NN
    r = yield R.scoped(g_junk(args[0], 20))
    L.events.append(('scope', m, K.NN, r))
    yield K.mul_(K.TWO, [(r, K.ONE)])

def g_junknone(a):
    for i in range(20):
        K.sym('z%d' % i)
    return
    yield

def g_scnone(args, ctx):
    m = K.NN
    r = yield R.scoped(g_junknone(args[0]))
    L.events.append(('scnone', m, K.NN, r))
    yield args[0]

def g_pairj(a):
    K.sym('waste')
    yield (K.add_([a, K.ONE]), K.add_([a, K.TWO]))

def g_scpair(args, ctx):
    r = yield R.scoped(g_pairj(args[0]))
    yield K.mk((K.LST,) + r)

def g_empty(args, ctx):
    yield K.mk((K.LST,))

def g_true(args, ctx):
    yield K.TRUE

def g_err(args, ctx):
    raise K.CasError('custom message', 3)
    yield

def g_type(args, ctx):
    raise TypeError('a bug')
    yield

def g_rt(args, ctx):
    raise RuntimeError('maximum recursion depth exceeded')
    yield

def g_mem(args, ctx):
    K.sym('w1')
    raise MemoryError()
    yield

def g_cm(args, ctx):
    raise K.CasMemory()
    yield

def g_kbi(args, ctx):
    K.sym('w2')
    raise KeyboardInterrupt()
    yield

def g_ctx(args, ctx):
    L.events.append(('ctx', list(ctx)))
    yield args[0]
'''

TCMDS = {
    'tval': ('tst', 'g_val', 1, 1, NOAUTO, ()),
    'tnest': ('tst', 'g_nest', 1, 1, NOAUTO, ()),
    'tnone': ('tst', 'g_none', 1, 1, NOAUTO, ()),
    'tsoft': ('tst', 'g_soft', 1, 1, NOAUTO, ()),
    'tsoftm': ('tst', 'g_softm', 1, 1, NOAUTO, ()),
    'tcatch': ('tst', 'g_catch', 1, 1, NOAUTO, ()),
    'ttick': ('tst', 'g_tick', 2, 2, NOAUTO, ()),
    'tloop': ('tst', 'g_loop', 1, 1, NOAUTO, ()),
    'tscope': ('tst', 'g_scope', 1, 1, NOAUTO, ()),
    'tscnone': ('tst', 'g_scnone', 1, 1, NOAUTO, ()),
    'tscpair': ('tst', 'g_scpair', 1, 1, NOAUTO, ()),
    'tempty': ('tst', 'g_empty', 1, 1, NOAUTO | P.F_SOLN, ()),
    'ttrue': ('tst', 'g_true', 1, 1, NOAUTO | P.F_SOLN, ()),
    'terr': ('tst', 'g_err', 1, 1, NOAUTO, ()),
    'ttype': ('tst', 'g_type', 1, 1, NOAUTO, ()),
    'trt': ('tst', 'g_rt', 1, 1, NOAUTO, ()),
    'tmem': ('tst', 'g_mem', 1, 1, NOAUTO, ()),
    'tcm': ('tst', 'g_cm', 1, 1, NOAUTO, ()),
    'tkbi': ('tst', 'g_kbi', 1, 1, NOAUTO, ()),
    'tctx': ('tst', 'g_ctx', 1, 1, NOAUTO, ()),
}

FRESH = (('ANS', None), ('HIST', list), ('VARS', dict), ('FUNCS', dict), ('MODS', dict),
         ('LOADED', list), ('USE', dict), ('PINNED', list), ('LIVE', dict), ('NEEDED', list))


@pytest.fixture
def env(monkeypatch):
    """A fresh session and loader, fake lazy modules for every key, the reference printer."""
    fk = Fakes()
    log = types.ModuleType('fk_log')
    log.events = []
    fk.log = log.events
    sys.modules['fk_log'] = log
    sys.meta_path.insert(0, fk)
    for name, make in FRESH:
        monkeypatch.setattr(R, name, make() if make is not None else None)
    monkeypatch.setattr(R, 'SET', {'deg': 0, 'theme': 0})
    monkeypatch.setattr(R, 'CLOCK', [0])
    dev = {}
    for k in R.DEV:
        dev[k] = 'fk_' + k
        fk.src['fk_' + k] = generic(k)
    dev['tst'] = 'fk_tst'
    fk.src['fk_tst'] = TST
    monkeypatch.setattr(R, 'DEV', dev)
    cmds = dict(R.CMDS)
    cmds.update(TCMDS)
    monkeypatch.setattr(R, 'CMDS', cmds)
    monkeypatch.setattr(P, 'SESS', R)
    monkeypatch.setattr(PR, 'record', stub_record, raising=False)
    del JOBS[:]
    TEXTFAIL[0] = 0
    try:
        yield fk
    finally:
        sys.meta_path.remove(fk)
        for n in list(sys.modules):
            if n.startswith('fk_'):
                del sys.modules[n]


def ev(s):
    return R.go(('eval', s))


def txt(s):
    r = ev(s)
    assert r[0] == 'ans', (s, r)
    return r[1]


def same(a, b):
    """The texts of a and b as computed by the runner are equal (same canonical node)."""
    return txt(a) == txt(b)


def clean():
    """The state every command must leave."""
    assert K.NN == K.BASE
    assert R.NEEDED == [] and R.PINNED == [] and not R.LIVE


# -- tables and API --------------------------------------------------------------------------------

def test_frozen_api():
    for name in ('go', 'start', 'need', 'drop', 'MODS', 'scoped', 'TICK', 'CMDS', 'ALIAS',
                 'DEPS', 'PARTS', 'MACROS', 'HINT', 'ANS', 'HIST', 'VARS', 'FUNCS', 'SET'):
        assert hasattr(R, name), name
    assert R.scoped(None) == (R.SCOPE, None)
    assert R.TICK is not R.SCOPE and R.MAXGEN == 64 and R.BUDGET == 20000


def test_loader_tables_match_the_manifest():
    sys.path.insert(0, os.path.join(ROOT, 'build'))
    try:
        import bundle
    finally:
        sys.path.pop(0)
    man = bundle.load_manifest(os.path.join(ROOT, 'build', 'manifest.py'))
    want = bundle.desktop_tables(man, R.DEPS)
    assert R.DEV == want['DEV']
    assert R.PARTS == want['PARTS']
    assert R.FAMILY == want['FAMILY']
    assert R.CLOSURE == want['CLOSURE']
    assert R.EVDICT == (1 if man.EVICT == 'dict' else 0)
    assert R.PEAKB == man.PEAKB and R.FRAG == man.FRAG


def test_registry_shape(monkeypatch):
    monkeypatch.setattr(P, 'SESS', R)
    flags = P.F_NOAUTO | P.F_ALWAYSAUTO | P.F_SOLN
    for name in sorted(R.CMDS):
        fam, g, lo, hi, fl, rs = R.CMDS[name]
        assert R.FAMILY.get(fam, fam) in R.CLOSURE, name
        assert g.startswith('g_') and 0 <= lo <= hi and fl & ~flags == 0, name
        assert P.classify(name) == P.C_FN or name == 'd'
        if rs:                                          # a rule set needs the rules family
            assert 'rules' in R.CLOSURE[R.FAMILY.get(fam, fam)], name
        assert name in R.HINT
    for a in R.ALIAS:
        assert R.ALIAS[a] in R.CMDS
    for m in R.MACROS:
        assert m in R.HINT
    assert 'approx' not in R.CMDS and 'evalf' not in R.ALIAS   # g_eval builtins (T1.5)
    assert R.CMDS['solve'][4] & P.F_SOLN and R.CMDS['diff'][4] & P.F_ALWAYSAUTO


def test_okname():
    for v in ('x', 'a1', 'abc', 'theta', 'd', 'k2z'):
        assert R.okname(v), v
    for v in ('', 'X', '1a', 'a_b', 'sin', 'pi', 'e', 'i', 'oo', 'undef', 'true', 'solve',
              'int', 'diff', 'polararea', 'purge', 'approx', 'ans', 'mid', 'O', "y'"):
        assert not R.okname(v), v


# -- the trampoline protocol (10.2-10.4) -----------------------------------------------------------

def test_plain_value_and_never_resumed(env):
    assert txt('tval(x)') == 'x'
    assert 'resumed after its value' not in env.log
    clean()


def test_virtual_calls_nest_without_frames(env, evodepth):
    r, depth, stack = evodepth.measure(ev, 'tnest(40)')
    assert r[:2] == ('ans', '40')
    r1, d1, _ = evodepth.measure(ev, 'tnest(1)')
    assert r1[1] == '1' and depth == d1          # 40 logical levels cost no frame
    assert depth <= 7


def test_maxgen(env):
    assert txt('tnest(61)') == '61'               # g_eval, g_nest, 62 chains: 64 generators
    assert ev('tnest(62)') == ('msg', K.M_COMPLEX, None, 0)
    clean()


def test_bare_return_is_failure(env):
    assert ev('tnone(x)') == ('msg', 'undefined', None, 0)


def test_soft_failure(env):
    assert ev('tsoft(x)') == ('msg', 'undefined', None, 0)
    assert ev('tsoftm(x)') == ('msg', 'no closed form', None, 0)
    assert txt('tcatch(x)') == 'caught'
    assert ('catch', None, 'Undefined') in env.log
    assert ev('1/0') == ('msg', 'undefined', None, 0)     # Undefined in g_eval itself
    clean()


def test_tick(env, monkeypatch):
    seen = []
    monkeypatch.setattr(R, 'BUSY', seen.append)
    assert txt('ttick(2000,7)') == '7'
    assert seen and all(s % 512 == 0 for s in seen) and len(seen) >= 3


def test_budget(env):
    assert ev('tloop(1)') == ('msg', 'too long', None, 0)
    clean()


def test_cancel(env, monkeypatch):
    polls = [0]

    def esc():
        polls[0] += 1
        return polls[0] >= 3

    monkeypatch.setattr(K, 'ESC', esc)
    assert ev('tloop(1)') == ('msg', 'Interrupted', None, 0)
    assert polls[0] == 3
    clean()


def test_scoped_region(env):
    assert same('tscope(x)', '2*(x+1)')
    ((_, m, nn, r),) = [e for e in env.log if e[0] == 'scope']
    assert r == m and nn == m + 1                 # the garbage went; x+1 moved down to m
    assert txt('tscnone(y)') == 'y'
    ((_, m, nn, r),) = [e for e in env.log if e[0] == 'scnone']
    assert r is None and nn == m
    assert same('tscpair(x)', '[x+1,x+2]')
    clean()


def test_regions_under_the_debug_arena(env, arena):
    """20.4: released ids are never reused, so an id leaking out of a region would fail."""
    assert same('tscope(x)', '2*(x+1)')
    assert txt('tscnone(y)') == 'y'
    assert same('tscpair(x)', '[x+1,x+2]')
    assert same('tnest(20)', '20')


# -- errors and records -----------------------------------------------------------------------------

def test_record_shapes(env):
    for s in ('1+2', 'x', '1+', 'purge(q)', 'f(x)=x', 'tsoft(1)', 'tempty(1)'):
        r = ev(s)
        assert type(r) is tuple and len(r) == 4, (s, r)
        assert r[0] in ('ans', 'msg') and type(r[1]) is str and type(r[3]) is int
        assert r[2] is None or type(r[2]) is str
        clean()


def test_casError_messages(env):
    assert ev('terr(1)') == ('msg', 'custom message', None, 0)
    assert ev('1+') == ('msg', 'missing operand', None, 0)
    assert ev('(1]') == ('msg', 'mismatched bracket', None, 0)
    assert ev('sin(x,y)') == ('msg', P.M_ARGS, None, 0)
    assert ev('2^(10^6)') == ('msg', K.M_BIG, None, 0)
    assert ev("x'") == ('msg', P.M_PRIME, None, 0)
    clean()


@pytest.mark.allow_internal_error
def test_internal_error(env):
    assert ev('ttype(1)') == ('msg', 'internal error: TypeError', None, 0)
    clean()
    assert txt('1+1') == '2'                       # the session goes on


def test_runtime_error(env):
    assert ev('trt(1)') == ('msg', 'Expression too complex', None, 0)
    clean()


def test_memoryerror_path(env):
    assert txt('tval(1)') == '1'
    assert 'fk_tst' in sys.modules and R.MODS
    for s in ('tmem(x)', 'tcm(x)'):
        assert ev(s) == ('msg', 'Out of memory', None, 0)
        clean()
        assert R.MODS == {} and R.LOADED == []    # evict_all (18.6)
        assert 'fk_tst' not in sys.modules
    assert txt('tval(2)') == '2' and env.imports['fk_tst'] == 3


def test_keyboardinterrupt_reraised_after_reset(env):
    ev('1+1')
    n = len(R.HIST)
    with pytest.raises(KeyboardInterrupt):
        R.go(('eval', 'tkbi(x+1)'))
    clean()
    assert len(R.HIST) == n and R.ANS == '2'


def test_msg_rec():
    assert R.msg_rec('Interrupted') == ('msg', 'Interrupted', None, 0)
    assert R.msg_rec(('missing )',)) == ('msg', 'missing )', None, 0)
    assert R.msg_rec(('missing operand', 4)) == ('msg', 'missing operand', None, 0)
    assert R.msg_rec(()) == ('msg', 'error', None, 0)
    assert R.msg_rec((R.M_INTERNAL, 'KeyError')) == ('msg', 'internal error: KeyError', None, 0)


def test_cas_soft_outside_the_loop(env, monkeypatch):
    def bad(val, job):
        raise K.Undefined()
    monkeypatch.setattr(PR, 'record', bad, raising=False)
    assert ev('1+1') == ('msg', 'undefined', None, 0)


# -- the session (7.11) -----------------------------------------------------------------------------

def test_text_only_session(env):
    for s in ('a=x+1', 'f(t)=t^2', 'b=f(a)', '2+3', 'tempty(1)', 'x+1=>c'):
        ev(s)
        clean()
    assert type(R.ANS) is str
    for k in R.VARS:                                            # order free
        assert type(R.VARS[k]) is str
    for k in R.FUNCS:
        ps, body = R.FUNCS[k]
        assert type(ps) is tuple and type(body) is str
    for e in R.HIST:
        assert len(e) == 6 and type(e[0]) is str and type(e[1]) is str and e[5] is None
        assert e[2] in ('ans', 'msg') and type(e[4]) is int


def test_ans(env):
    assert ev('ans()+1') == ('msg', 'no answer yet', None, 0)
    assert txt('2+3') == '5' and R.ANS == '5'
    assert txt('ans()*2') == '10' and R.ANS == '10'
    assert ev('1+')[0] == 'msg' and R.ANS == '10'               # a message never becomes Ans
    assert ev('tempty(1)') == ('msg', 'no solution', None, 0) and R.ANS == '10'
    assert txt('x-1') and same('ans()^2', '(x-1)^2')            # in parentheses
    assert ev('ans()' * 9) == ('msg', 'too many ans()', None, 0)
    assert R.HIST[-1][0] == 'ans()' * 9                         # the history keeps ans()


def test_ans_of_a_list(env):
    txt('[1,2]')
    assert same('ans()', '[1,2]')


def test_autoclose(env):
    assert same('sin(x', 'sin(x)') and R.HIST[-1][0] == 'sin(x)'
    assert same('[1,(2', '[1,(2)]') and R.HIST[-1][0] == '[1,(2)]'
    assert ev('(1]') == ('msg', 'mismatched bracket', None, 0) and R.HIST[-1][0] == '(1]'
    assert ev('1)')[0] == 'msg' and R.HIST[-1][0] == '1)'
    deep = '(' * 65 + 'x'
    assert ev(deep) == ('msg', 'too deeply nested', None, 0) and R.HIST[-1][0] == deep


def test_history_caps(env):
    for i in range(45):
        ev(str(i))
    assert len(R.HIST) == 40 and R.HIST[0][0] == '5' and R.HIST[-1][1] == '44'
    long = '+'.join(['1'] * 120)                                 # 239 characters
    for i in range(40):
        ev(long)
    tot = sum(len(e[0]) + len(e[1]) for e in R.HIST)
    assert tot <= R.HISTTEXT and len(R.HIST) < 40
    assert R.HIST[-1] == [long, '120', 'ans', None, 0, None]


def test_degree_flag_and_ctx(env):
    R.SET['deg'] = 1
    r = ev('tctx(1)')
    assert r[3] & R.F_DEG
    assert ('ctx', [1, None, 0, 0]) in env.log
    assert JOBS[-1][2] == [1, None, 0, 0] and JOBS[-1][1] == 'tctx(1)'
    R.SET['deg'] = 0
    assert not ev('tctx(1)')[3] & R.F_DEG


# -- the runner's input rules (7.9) -----------------------------------------------------------------

def test_purge(env):
    ev('a=1')
    ev('f(x)=x')
    ev('b=2')
    assert ev('purge(a,f)') == ('msg', 'a, f purged', None, 0)
    assert R.VARS == {'b': '2'} and R.FUNCS == {}
    assert ev('purge(zz)') == ('msg', 'zz purged', None, 0)      # a whole name, never cut
    ev('ab=5')
    assert ev('purge(ab)') == ('msg', 'ab purged', None, 0) and 'ab' not in R.VARS
    for s in ('purge(x+1)', 'purge()', 'purge(b)+1', 'purge(b,)', '1+purge(b)'):
        assert ev(s) == ('msg', P.M_PURGE, None, 0), s
    assert R.VARS == {'b': '2'}
    assert txt('a') == 'a'                       # forgotten: a is a symbol again


def test_definitions(env):
    assert ev('f(x)=x^2+1') == ('msg', 'f(x) defined', None, 0)
    assert R.FUNCS == {'f': (('x',), 'x^2+1')}
    assert txt('f(3)') == '10'
    assert ev('g(x,y):=x*y') == ('msg', 'g(x,y) defined', None, 0)
    assert txt('g(2,3)') == '6'
    assert ev('f(x)=2x') == ('msg', 'f(x) defined', None, 0) and R.FUNCS['f'] == (('x',), '2*x')
    assert txt('f(5)') == '10'
    assert ev('k(t)=t') == ('msg', 'k(t) defined', None, 0)
    assert R.HIST[-1][2] == 'msg' and R.ANS == '10'


def test_definition_body_unexpanded(env):
    ev('a=2')
    ev('h(x)=a*x')
    assert R.FUNCS['h'] == (('x',), 'a*x')
    ev('a=5')
    assert txt('h(1)') == '5'
    ev('x=7')                                    # a parameter shadows a stored variable
    assert txt('h(3)') == '15'


def test_definition_errors(env):
    ev('f(x)=x')
    for s, m in (('f(pi)=1', P.M_ASSIGN), ('f(x,x)=1', P.M_ASSIGN), ('F(x)=x', R.M_BADNAME),
                 ('f(f)=1', P.M_ASSIGN), ('f(x)=x+', 'missing operand'),
                 ('f(x,1):=1', P.M_ASSIGN), ('f():=1', P.M_ASSIGN)):
        r = ev(s)
        assert r == ('msg', m, None, 0), (s, r)
    assert ev('f(x,)=1')[0] == 'msg'             # not a definition (stage 4): a bad call
    assert R.FUNCS == {'f': (('x',), 'x')}


def test_definition_replaces_a_variable(env):
    ev('f=3')
    assert R.VARS == {'f': '3'}
    assert ev('f(x)=x+1') == ('msg', 'f(x) defined', None, 0)
    assert R.VARS == {} and txt('f(1)') == '2'
    ev('f=4')
    assert R.FUNCS == {} and R.VARS == {'f': '4'}


def test_store_arrow(env):
    assert txt('1+2=>b') == '3' and R.VARS == {'b': '3'}
    assert txt('7=>b') == '7' and R.VARS == {'b': '7'}           # the target is not expanded
    assert txt('b+1') == '8'
    for s in ('5=>2', '5=>sin', '5=>X', '5=>', '1=>a=>b', '5=>f(x)'):
        assert ev(s) == ('msg', R.M_BADNAME, None, 0), s
    assert ev('1+=>a') == ('msg', 'missing operand', None, 0) and 'a' not in R.VARS
    assert ev('x+1=>x') == ('msg', R.M_CIRC, None, 0) and 'x' not in R.VARS
    assert R.ANS == '8'
    txt('1,2=>v')
    assert same('v', '[1,2]')


def test_store_equals(env):
    r = ev('x=3')
    assert r[:2] == ('ans', '3') and r[3] & R.F_PURGEHINT and R.VARS == {'x': '3'}
    r = ev('q=3')
    assert r[:2] == ('ans', '3') and not r[3] & R.F_PURGEHINT
    assert txt('x+q') == '6'
    assert not ev('x+1')[3] & R.F_PURGEHINT
    for v in R.HINTV:
        assert ev(v + '=1')[3] & R.F_PURGEHINT
    assert txt('x=x+1') == 'false'                 # x occurs: an equation, 1=2
    assert txt('q:=5') == '5' and R.VARS['q'] == '5'
    assert ev('w:=w+1') == ('msg', P.M_ASSIGN, None, 0)


def test_store_references(env):
    txt('a=x+1')
    assert same('a', 'x+1')
    txt('x=2')
    assert txt('a') == '3'
    assert ev('b=a+b')[0] == 'ans'                 # b occurs in the typed rhs: an equation
    txt('c=b+1')                                   # stores b+1 (b unknown)
    assert ev('b=c') == ('msg', R.M_CIRC, None, 0) and 'b' not in R.VARS
    txt('y=1,2')                                   # a top-level comma: not a store
    assert 'y' not in R.VARS


def test_lone_equation_solves(env):
    r = ev('2x+1=5')
    assert r[0] == 'ans' and r[1].startswith('solve(')
    assert len([e for e in env.log if e[0] == 'solve']) == 1
    assert same('2x+1=5', 'solve(2*x+1=5,x)')
    assert JOBS[-1][3] & P.F_SOLN
    assert ev('x=x^2-2')[1].startswith('solve(')                # x occurs: not a store
    assert not ev('x^2=y')[1].startswith('solve(')              # two unknowns
    assert txt('2=3') == 'false'
    assert txt('pi=3') == '(pi=3)'                              # constants are not unknowns
    assert txt('sin(t)=1/2').startswith('solve(')
    assert not txt('x=1,x=2').startswith('solve(')              # a list, not a lone equation


def test_solve_sentinels_through_the_printer(env):
    assert ev('tempty(1)') == ('msg', 'no solution', None, 0)
    assert ev('ttrue(1)') == ('msg', 'every x is a solution', None, 0)
    assert JOBS[-1][3] & P.F_SOLN
    assert txt('tval(true)') == 'true'                          # no F_SOLN: an answer
    assert not JOBS[-1][3] & P.F_SOLN


def test_plus_c(env):
    for s in ('integrate(x^2,x)', 'int(x,x)', 'integrate(x)', 'integrate(sin(x),x)+1'):
        assert ev(s)[3] & R.F_PLUSC, s
    for s in ('integrate(x,x,0,1)', '2*integrate(x,x)', 'diff(x^2,x)', 'x'):
        assert not ev(s)[3] & R.F_PLUSC, s


def test_preload_and_rule_sets(env):
    ev('simplify(x)')
    names = [e[1] for e in env.log if e[0] == 'rset']
    assert names == ['trigsin', 'trigcos', 'tlin', 'lncollect']
    i = env.log.index(('rset', 'lncollect'))
    j = [k for k in range(len(env.log)) if env.log[k][0] == 'simplify'][0]
    assert i < j                                   # compiled at start, before the trampoline
    pinned = env.log[j][3]
    assert pinned == ['poly', 'rules', 'ident', 'norm']
    assert R.LOADED == ['poly', 'rules', 'ident', 'norm']
    del env.log[:]
    ev('integrate(x,x,0,1)')
    assert 'def' in R.LOADED and 'int' in R.LOADED
    ((_, args, ctx, pinned),) = [e for e in env.log if e[0] == 'integrate']
    assert 'def' in pinned and pinned[-1] == 'def'
    assert ('rset', 'itab') in env.log


def test_no_preload_for_plain_expressions(env):
    assert txt('x^2+2') and R.LOADED == []
    txt('1/(x+1)+x')                               # a simplify candidate: norm, at the end
    assert ('autosimp',) == tuple(e[0] for e in env.log if e[0] == 'autosimp')
    assert R.LOADED == ['poly', 'rules', 'ident', 'norm']


def test_macros_and_aliases(env):
    assert same('polararea(1,t,0,pi)', 'integrate((1)^2/2,t,0,pi)')
    assert same('d(x^2,x)', 'diff(x^2,x)')
    assert txt('d(x+1)') != txt('diff(x+1)')       # D9: d with one argument is d*(x+1)


def test_form_job(env):
    ev('x+1')
    n = len(R.HIST)
    r = R.go(('form', 0))
    assert r[0] == 'ans' and r[1] == R.HIST[0][1]
    assert ('form', [0, None, 0, 1]) in env.log     # inert, the entry's angle mode
    assert len(R.HIST) == n and R.ANS == R.HIST[0][1]
    R.HIST[0][5] = [('exact', '2+3')]              # forms[0] is the original text
    assert R.go(('form', 0))[1] == '5'
    R.SET['deg'] = 1
    ev('tctx(1)')
    R.SET['deg'] = 0
    R.go(('form', len(R.HIST) - 1))
    assert ('form', [1, None, 0, 1]) in env.log
    assert 'form' in R.LOADED
    clean()


# -- the lazy loader (18.4, 18.5) -------------------------------------------------------------------

@pytest.fixture
def heap(env, monkeypatch):
    """Fake families la, lb (needs la), lc, ld, lp (parts lp, lpb), xint, xint2, xint3, xold, xd,
    xa; every part costs 10000 bytes of a fake heap of h.total bytes."""
    keys = ('la', 'lb', 'lc', 'ld', 'lp', 'lpb', 'xold', 'xa')
    for k in keys:
        R.DEV[k] = 'fk_' + k
        env.src['fk_' + k] = ('import fk_log as L\nL.events.append(("import", %r))\n'
                              'X = %r\n\ndef f(x):\n    return x\n' % (k, k))
    for k in ('xint', 'xint2', 'xint3', 'xd'):
        R.DEV[k] = 'fk_' + k
    env.src['fk_xint'] = '''
        import run as R
        def g_xint(args, ctx):
            M = R.need('xint3')
            r = yield M.g_parts(args, ctx)
            yield r
        def g_inner(args, ctx):
            M = R.need('xint2')
            r = yield M.g_tab(args, ctx)
            yield r
        '''
    env.src['fk_xint3'] = '''
        import run as R
        def g_parts(args, ctx):
            r = yield R.MODS['xint'].g_inner(args, ctx)
            yield r
        '''
    env.src['fk_xint2'] = '''
        import node as K
        def g_tab(args, ctx):
            yield K.add_([args[0], K.ONE])
        '''
    env.src['fk_xd'] = '''
        import run as R
        import fk_log as L
        def g_outer(args, ctx):
            R.need('xa')
            r = yield g_child(args, ctx)
            L.events.append(('outer', 'xa' in R.LOADED, R.LIVE.get('xa', 0)))
            yield R.MODS['xa'].f(r)
        def g_child(args, ctx):
            R.need('xa')
            L.events.append(('child', R.LIVE.get('xa', 0)))
            R.drop(('xa',))
            L.events.append(('dropped', 'xa' in R.LOADED, R.LIVE.get('xa', 0)))
            yield args[0]
        def g_phase(args, ctx):
            R.need('xa')
            R.drop(('xa',))
            L.events.append(('phase', 'xa' in R.LOADED))
            R.need('xa')
            yield args[0]
        '''
    cl = dict(R.CLOSURE)
    cl.update({'la': ('la',), 'lb': ('la', 'lb'), 'lc': ('lc',), 'ld': ('ld',), 'lp': ('lp',)})
    monkeypatch.setattr(R, 'CLOSURE', cl)
    parts = dict(R.PARTS)
    parts['lp'] = ('lp', 'lpb')
    monkeypatch.setattr(R, 'PARTS', parts)
    fam = dict(R.FAMILY)
    fam['lpb'] = 'lp'
    monkeypatch.setattr(R, 'FAMILY', fam)
    cost = {}
    for k in keys + ('xint', 'xint2', 'xint3', 'xd'):
        cost[k] = 10000
    monkeypatch.setattr(R, 'COST', cost)
    monkeypatch.setattr(R, 'LINES', {'la': 50})
    monkeypatch.setattr(R, 'PEAKB', 0)
    monkeypatch.setattr(R, 'FRAG', 0)
    monkeypatch.setattr(R, 'KEEPFREE', 0)
    R.CMDS['xint'] = ('xint', 'g_xint', 1, 1, NOAUTO, ())
    R.CMDS['xd'] = ('xd', 'g_outer', 1, 1, NOAUTO, ())
    R.CMDS['xphase'] = ('xd', 'g_phase', 1, 1, NOAUTO, ())
    h = types.SimpleNamespace(total=1 << 20)

    def memfree():
        used = 0
        for p in R.MODS:                                         # sum: order free
            used += R.COST.get(p, 0)
        return h.total - used

    monkeypatch.setattr(R, 'MEMFREE', memfree)
    return h


def test_need_loads_the_closure_leaf_first(heap, env):
    m = R.need('lb')
    assert m.X == 'lb' and R.LOADED == ['la', 'lb'] and sorted(R.MODS) == ['la', 'lb']
    assert env.log == [('import', 'la'), ('import', 'lb')]
    assert R.USE['la'] == R.USE['lb'] == R.CLOCK[0]
    assert R.need('la').X == 'la' and env.imports == {'fk_la': 1, 'fk_lb': 1}
    assert R.USE['la'] > R.USE['lb']
    assert R.LIVE == {}                               # no generator: no live pin


def test_need_part_key_loads_the_family(heap, env):
    assert R.need('lpb').X == 'lpb'
    assert R.LOADED == ['lp'] and sorted(R.MODS) == ['lp', 'lpb']
    assert R.need('lp').X == 'lp' and env.imports == {'fk_lp': 1, 'fk_lpb': 1}


def test_lru_eviction(heap, env):
    heap.total = 30000
    R.need('la')
    R.need('lc')
    R.need('ld')
    R.need('la')                                   # la is now the most recent
    R.need('lp')                                   # two parts: evicts lc, then ld
    assert R.LOADED == ['la', 'lp']
    assert sorted(R.MODS) == ['la', 'lp', 'lpb']
    for n in ('fk_lc', 'fk_ld'):
        assert n not in sys.modules
    R.need('la')                                   # lp is now the LRU family
    assert R.need('lc').X == 'lc' and env.imports['fk_lc'] == 2      # re-import is correct
    assert R.LOADED == ['la', 'lc']                # lp went as a unit
    assert 'fk_lp' not in sys.modules and 'fk_lpb' not in sys.modules


def test_want_counts_the_compile_peak(heap, env, monkeypatch):
    monkeypatch.setattr(R, 'PEAKB', 100)            # la: 50 lines -> 5000 more bytes needed
    heap.total = 14000
    with pytest.raises(K.CasMemory):
        R.need('la')
    heap.total = 15000
    assert R.need('la').X == 'la'


def test_pinned_and_live_are_never_evicted(heap, env):
    heap.total = 20000
    R.need('la')
    R.PINNED.append('la')
    R.need('lc')
    R.need('ld')                                   # evicts lc, not the pinned la
    assert R.LOADED == ['la', 'ld']
    R.NEEDED.append([])
    R.need('ld')                                   # a live pin from a generator's slot
    assert R.LIVE == {'ld': 1} and R.NEEDED == [['ld']]
    with pytest.raises(K.CasMemory):
        R.need('lc')
    assert R.LOADED == ['la', 'ld']
    del R.NEEDED[:]
    R.LIVE.clear()
    del R.PINNED[:]


def test_the_closure_being_loaded_is_no_victim(heap, env):
    heap.total = 15000
    with pytest.raises(K.CasMemory):
        R.need('lb')                               # la loads, then lb finds only la
    assert R.LOADED == ['la'] and 'la' in R.MODS
    R.evict_all()
    heap.total = 20000
    R.need('lc')
    R.need('lb')                                   # la loads; lb evicts lc, never la
    assert R.LOADED == ['la', 'lb'] and 'fk_lc' not in sys.modules


def test_live_pins_cover_the_closure(heap, env):
    R.NEEDED.append([])
    R.need('lb')
    assert R.NEEDED == [['lb']] and R.LIVE == {'la': 1, 'lb': 1}
    R.need('lb')
    assert R.LIVE == {'la': 1, 'lb': 1}           # once per slot
    R.NEEDED.append([])
    R.need('la')
    assert R.LIVE == {'la': 2, 'lb': 1}
    R.drop(('la',))                                # the inner slot's pin goes; la still live
    assert R.LIVE == {'la': 1, 'lb': 1} and 'la' in R.LOADED
    R.NEEDED.pop()
    R.drop(('lb',))
    assert R.LIVE == {'la': 0, 'lb': 0} and R.LOADED == ['la']   # lb evicted; la not named
    R.PINNED.append('la')
    R.drop(['la'])
    assert R.PINNED == [] and R.LOADED == []      # drop unpins and evicts
    del R.NEEDED[:]
    R.LIVE.clear()


def test_suspended_parts_and_a_nested_need(heap, env):
    """20.12: a suspended g_parts with a nested g_int that needs CVINT2 under a tiny heap."""
    heap.total = 30000
    R.need('xold')                                 # an earlier command's family
    assert same('xint(x)', 'x+1')
    assert env.imports['fk_xint3'] == 1 and env.imports['fk_xint2'] == 1
    assert env.imports['fk_xint'] == 1
    assert 'xold' not in R.LOADED                  # the only victim that was not live
    clean()
    R.evict_all()                                  # again with nothing evictable
    heap.total = 20000
    env.imports.clear()
    assert ev('xint(x)') == ('msg', 'Out of memory', None, 0)
    assert env.imports.get('fk_xint3') == 1       # never evicted while live, never twice
    clean()


def test_drop_of_a_live_family(heap, env):
    assert txt('xd(x)') == 'x'
    assert ('child', 2) in env.log
    assert ('dropped', True, 1) in env.log         # still live in the outer slot
    assert ('outer', True, 1) in env.log
    assert env.imports['fk_xa'] == 1
    assert txt('xphase(y)') == 'y'
    assert ('phase', False) in env.log             # a phase drop of a non-live family evicts
    assert env.imports['fk_xa'] == 2               # at most 2 imports per command (18.5)
    clean()


def test_trim_between_commands(heap, env, monkeypatch):
    heap.total = 45000
    monkeypatch.setattr(R, 'KEEPFREE', 25000)
    R.need('la')
    R.need('lc')
    R.need('ld')
    R.need('la')
    assert txt('1+1') == '2'
    assert R.LOADED == ['la', 'ld']                # lc, the LRU, went: 25000 free now


def test_evict_all_after_a_cut_import(heap, env):
    env.src['fk_lpb'] = 'raise MemoryError()\n'
    R.CMDS['tlp'] = ('lp', 'g_x', 1, 1, NOAUTO, ())
    assert ev('tlp(1)') == ('msg', 'Out of memory', None, 0)
    assert R.MODS == {} and R.LOADED == [] and 'fk_lp' not in sys.modules
    clean()


def test_evdict(heap, env, monkeypatch):
    monkeypatch.setattr(R, 'EVDICT', 1)
    m = R.need('lc')
    heap.total = 10000
    R.need('ld')
    assert 'X' not in m.__dict__ and R.LOADED == ['ld']
    R.evict_all()
    assert R.MODS == {} and R.LOADED == []


# -- 20.12: R.go never raises ---------------------------------------------------------------------

def fuzz(seed, count, deg=0):
    g = gen.Gen(seed, syms=('x', 'y', 't'))
    kinds = {}
    for i in range(count):
        R.SET['deg'] = deg if i % 3 else 1 - deg
        line = g.line()
        r = R.go(('eval', line))
        assert type(r) is tuple and len(r) == 4 and r[0] in ('ans', 'msg'), (line, r)
        assert type(r[1]) is str
        assert K.NN == K.BASE and not R.LIVE and not R.NEEDED and not R.PINNED, line
        kinds[r[0]] = kinds.get(r[0], 0) + 1
        if i % 50 == 49:
            R.go(('eval', 'a=x+1'))
            R.go(('eval', 'f(u)=u^2'))
    return kinds


def test_fuzz_fast(env):
    kinds = fuzz(1, 300)
    assert kinds.get('ans', 0) > 50 and kinds.get('msg', 0) > 50


@pytest.mark.slow
def test_fuzz_2000(env):
    fuzz(2, 2000)


INJECT = ('1+2*x', 'sin(x)^2+1/2', 'x+1=>a', '2x+1=5', 'tscope(x)', 'f(t)=t+1',
          'tnest(5)', '[1,x]', 'integrate(x,x)')


def counted(mod, name):
    orig = getattr(mod, name)
    box = [0, 0]                     # calls, fail at

    def f(*a):
        box[0] += 1
        if box[0] == box[1]:
            raise MemoryError()
        return orig(*a)

    setattr(mod, name, f)
    return box, orig


@pytest.mark.parametrize('where', ['mk', 'keep', 'text'])
def test_memoryerror_injection(env, where):
    hits = 0
    for s in INJECT:
        for k in range(1, 400):
            R.go(('eval', 'purge(a)'))
            if where == 'text':
                TEXTCALLS[0] = 0
                TEXTFAIL[0] = k
                box = None
            else:
                box, orig = counted(K, where)
                box[1] = k
            try:
                r = R.go(('eval', s))
            finally:
                if box is not None:
                    setattr(K, where, orig)
                TEXTFAIL[0] = 0
            calls = TEXTCALLS[0] if box is None else box[0]
            clean()
            if calls < k:                              # the command needed fewer than k
                assert r[1] != 'Out of memory', (s, k)
                break
            assert r == ('msg', 'Out of memory', None, 0), (s, k, r)
            assert R.MODS == {} and R.LOADED == []
            assert 'a' not in R.VARS
            hits += 1
    assert hits >= {'mk': 100, 'keep': 1, 'text': 20}[where], hits


@pytest.mark.allow_internal_error
def test_typeerror_injection(env, monkeypatch):
    orig = P.g_eval

    def broken(code, ctx):
        yield K.sym(None)                            # a TypeError inside mk's hash loop

    monkeypatch.setattr(P, 'g_eval', broken)
    r = ev('1+1')
    assert r == ('msg', 'internal error: TypeError', None, 0)
    clean()
    monkeypatch.setattr(P, 'g_eval', orig)
    assert txt('1+1') == '2'


# -- depth --------------------------------------------------------------------------------------------

@pytest.mark.parametrize('kind', ['sin', 'square', 'frac', 'paren', 'sum', 'prod', 'exp', 'ln'])
def test_nesting_invariance(env, evodepth, kind):
    depths = []
    for n in (1, 8, 32):
        r, d, st = evodepth.measure(R.go, ('eval', gen.nested(kind, n)))
        assert r[0] == 'ans', (kind, n, r)
        depths.append(d)
    assert depths[0] == depths[1] == depths[2], (kind, depths)
    assert max(depths) <= 7


@pytest.mark.strict_depth
def test_strict_budget(env):
    for s in ('1+2*x', 'x=3', 'f(t)=t^2', 'f(2)', '2x+1=5', 'tscope(x)', 'tnest(30)',
              'xx+1=>b', 'simplify(1/(x+1)+x)'):
        R.go(('eval', s))
        clean()


# -- the real printer (T1.7), when it exists ----------------------------------------------------------

realprinter = pytest.mark.skipif(REAL_RECORD is None, reason='printer.record (T1.7) not written')


@realprinter
def test_real_printer_session(env, monkeypatch):
    monkeypatch.setattr(PR, 'record', REAL_RECORD)
    r = ev('1+2')
    assert r[0] == 'ans' and r[1] == '3' and R.ANS == '3'
    assert ev('x=3')[3] & R.F_PURGEHINT and R.VARS['x'] == '3'
    ev('purge(x)')
    ev('2*x+3=>a')
    assert txt('a-2*x-3') == '0'
    assert ev('x+1=>x') == ('msg', R.M_CIRC, None, 0)
    ev('f(t)=t^2')
    assert txt('f(3)') == '9'
    clean()


@realprinter
def test_real_printer_messages_and_decimals(env, monkeypatch):
    monkeypatch.setattr(PR, 'record', REAL_RECORD)
    assert ev('2<3')[:2] == ('ans', 'true')
    assert ev('tempty(1)') == ('msg', 'no solution', None, 0)
    assert ev('ttrue(1)')[0] == 'msg'
    r = ev('1/3')
    assert r[:3] == ('ans', '1/3', '0.3333333333') and R.ANS == '1/3'
    assert ev('7^5000') == ('msg', 'Done', None, 0) and R.ANS == '1/3'
    R.SET['deg'] = 1
    r = ev('sin(30)')
    assert r[:2] == ('ans', '1/2') and r[3] & R.F_DEG
    R.SET['deg'] = 0
    clean()


@realprinter
def test_real_printer_answer_path_has_no_stage_6(env, monkeypatch):
    """20.12 session row: an old entry's re-parse never sees a variable stored later."""
    monkeypatch.setattr(PR, 'record', REAL_RECORD)
    old = txt('(a+1)^2')
    txt('a=3')
    assert txt('(a+1)^2') == '16'
    r = R.go(('form', 0))
    assert r[:2] == ('ans', old)
    assert txt('ans()+0') == '16'                  # Ans is the newest answer, a=3 applies
    clean()
