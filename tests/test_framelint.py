"""FRAMELINT (DESIGN.md 17.3, 10.2, 4.2): good and bad snippets, and src/ itself."""
import json
import os
import textwrap

import pytest

import framelint
import lint

# -- a good miniature tree, shaped like the design sketches -----------------------------------

GOOD = {
    'node': '''
        #@L 7
        # node table sketch (DESIGN 5.10, 6.1, 8.4)
        import array
        import gc

        NUM = 0
        SYM = 2
        COMP = 8
        ADD = 8
        MUL = 9
        M25 = 0x1FFFFFF
        NB = 1024
        NMAX = 768
        LOWMEM = 24576
        OVF = 1 << 29
        N = [None] * NMAX
        H = [0] * NMAX
        NX = [0] * NMAX
        V = [0] * NMAX
        B = array.array('i', [0] * NB)
        NN = 1
        BASE = 15
        SYMN = []
        SYMI = {}
        ZERO = 1
        ONE = 2
        MONE = 3
        Q0 = (NUM, 0, 0, 1)
        Q1 = (NUM, 1, 0, 1)
        M_COMPLEX = 'expression too complex'
        ESC = None  #@native
        MEMFREE = None  #@native


        class CasError(Exception):
            pass


        class CasSoft(Exception):
            pass


        class CasMemory(BaseException):
            pass


        def mk(t):
            global NN
            op = t[0]
            v = 0
            if op >= COMP:
                h = op
                for j in range(1, len(t)):
                    c = t[j]
                    h = ((h << 5) ^ (h >> 20) ^ H[c]) & M25
                    v |= V[c]
            elif op == NUM:
                h = (((t[1] % 33554393) << 3) ^ ((t[2] % 1048573) << 1)
                     ^ (t[3] % 65521)) & M25
            else:
                h = 5381
                for ch in t[1]:
                    h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & M25
                bit = SYMI.get(t[1])
                if bit is None:
                    bit = len(SYMN)
                    SYMN.append(t[1])
                    SYMI[t[1]] = bit
                v = (1 << bit) if bit < 29 else OVF
            b = h & (NB - 1)
            i = B[b]
            while i:
                if H[i] == h and N[i] == t:
                    return i
                i = NX[i]
            i = NN
            if i >= NMAX:
                raise CasError(M_COMPLEX)
            if not i & 255 and MEMFREE() < LOWMEM:
                gc.collect()
                if MEMFREE() < LOWMEM:
                    raise CasMemory()
            N[i] = t
            H[i] = h
            NX[i] = B[b]
            V[i] = v
            B[b] = i
            NN = i + 1
            return i


        def nmul(x, y):
            if x[2] == 0 and y[2] == 0:
                a = x[1] * y[1]
                b = 0
            else:
                a = x[1] * y[1] - x[2] * y[2]
                b = x[1] * y[2] + x[2] * y[1]
            d = x[3] * y[3]
            g = a if a >= 0 else -a
            h = b if b >= 0 else -b
            while h:
                g, h = h, g % h
            h = d
            while h:
                g, h = h, g % h
            if g > 1:
                a //= g
                b //= g
                d //= g
            return (NUM, a, b, d)


        def tiefix(lst):
            return lst


        def add_(terms, k=None):                                        #@L 6
            c = Q0
            acc = {}
            st = []
            m0 = Q1 if k is None else k
            for e in terms:
                st.append((e, m0))
            while st:
                e, m = st.pop()
                t = N[e]
                if t[0] == NUM:
                    c = nmul(c, m)
                    continue
                if e in acc:
                    acc[e] = nmul(acc[e], m)
                else:
                    acc[e] = m
            lst = []
            for e in acc:                            #@unordered-ok (sorted below)
                lst.append((H[e], e, mk(acc[e])))
            cid = mk(c)
            if not lst:
                return cid
            lst.sort()
            tiefix(lst)
            out = [ADD, cid]
            for r in lst:
                out.append(r[1])
                out.append(r[2])
            return mk(tuple(out))


        def mul_(k, pairs):                                             #@L 5
            out = [MUL, k]
            for b, e in pairs:
                out.append(b)
                out.append(e)
            return add_([mk(tuple(out))])


        def release(m):
            global NN
            for i in range(NN - 1, m - 1, -1):
                B[H[i] & (NB - 1)] = NX[i]
                N[i] = None
            NN = m


        def keep(m, y):                                                 #@L 4
            if y is None:
                release(m)
                return None
            return y


        def reset():                                                    #@L 2
            release(BASE)
    ''',
    'alg': '''
        #@L 7
        import math
        import node as K

        P_CONST = 0
        P_FN = 3
        FNUM = (math.sin, math.cos)


        def postorder(e):
            out = [e]
            st = [e]
            while st:
                t = K.N[st.pop()]
                if t[0] >= K.COMP:
                    for j in range(1, len(t)):
                        st.append(t[j])
                        out.append(t[j])
            out.sort()
            return out


        def csin(z):                                                    #@L 5
            return complex(math.sin(z.real), 0.0)


        def ccos(z):                                                    #@L 5
            return complex(math.cos(z.real), 0.0)


        def nrun(prog, xs):                                             #@L 4
            r = [0.0] * len(prog)
            for i in range(len(prog)):
                ins = prog[i]
                if ins[0] == P_CONST:
                    v = ins[1]
                else:
                    a = r[ins[2]]
                    try:
                        v = FNUM[ins[1]](a)      #@calls 7  natives such as math.sin
                    except ValueError:
                        v = FCPX[ins[1]](a)      #@calls 5  complex helpers
                r[i] = v
            return r[-1]


        def nev(e, env):                                                #@L 3
            return nrun(postorder(e), env)


        FCPX = (csin, ccos)                                             #@table 5
    ''',
    'parse': '''
        #@L 7
        import node as K


        def inst(code, env):                                            #@L 4
            return K.mul_(K.ONE, [(code, K.ONE)])


        def g_atom(code):                                               #@L 2
            yield code


        def g_eval(code, ctx):                                          #@L 2
            r = yield g_atom(code)
            if r is None:
                return
            yield inst(r, ctx)
    ''',
    'printer': '''
        #@L 3
        import node as K
        import alg as A


        def text(e, ctx):
            return '%d' % K.N[e][1]


        def record(val, job):                                           #@L 2
            if val is None:
                return ('msg', 'undefined', None, 0)
            return ('expr', text(val, None), A.nev(val, ()), 0)
    ''',
    'run': '''
        #@L 2
        import sys
        import node as K
        import parse as P
        import printer as PR

        MODS = {}
        LOADED = []
        NEEDED = []
        LIVE = {}
        DEV = {'int': 'integ', 'form': 'forms'}
        BUSY = None
        MEMFREE = None  #@native
        SCOPE = ['scope']
        TICK = ['tick']
        MAXGEN = 64


        def _g():
            yield


        GEN = type(_g())


        def scoped(g):                                                  #@L 7
            return (SCOPE, g)


        def need(key):                                                  #@L 3
            if key not in MODS:
                MODS[key] = __import__(DEV.get(key, key))
            if NEEDED:
                NEEDED[-1].append(key)
                LIVE[key] = LIVE.get(key, 0) + 1
            return MODS[key]


        def start(job):
            return (job[1], None)


        def go(job):                                                    #@L 1
            stack = g = val = None
            try:
                code, ctx = start(job)
                if job[0] == 'eval':
                    g = P.g_eval(code, ctx)
                else:
                    g = MODS['form'].g_form(code, ctx)
                stack = [g]
                marks = [-1]
                steps = 0
                while stack:
                    steps += 1
                    if not steps & 31:
                        if K.ESC():
                            raise K.CasError('interrupted')
                        if not steps & 511:
                            BUSY(steps)                                 #@calls 2
                    top = stack[-1]
                    try:
                        y = top.send(val)
                    except StopIteration:
                        y = None
                    except K.CasSoft:
                        y = None
                    else:
                        if y is TICK:
                            val = None
                            continue
                        if type(y) is GEN:
                            stack.append(y)
                            marks.append(-1)
                            val = None
                            continue
                        if type(y) is tuple and len(y) == 2 and y[0] is SCOPE:
                            stack.append(y[1])
                            marks.append(K.NN)
                            val = None
                            continue
                    stack.pop()
                    m = marks.pop()
                    if m >= 0:
                        y = K.keep(m, y)
                    val = y
                rec = PR.record(val, job)
            except K.CasError as e:
                rec = ('msg', e.args[0], None, 0)
            stack = g = val = None
            K.reset()
            return rec
    ''',
    'forms': '''
        #@L 2
        import node as K


        def g_form(code, ctx):
            yield K.keep(K.NN, code)
    ''',
    'integ': '''
        #@L 2
        import node as K
        import alg as A
        import run as R

        STRATS = (('int', 'g_table'), ('int', 'g_parts'))


        def scale(c, e):                                                #@L 4
            return K.mul_(K.ONE, [(c, K.ONE), (e, K.ONE)])


        def check(f, g):                                                #@L 3
            return K.add_([f, scale(K.MONE, g)])


        def g_check(F, f, x):
            v = A.nev(check(F, f), (x,))
            if v != 0.0:
                return
            yield F


        def g_table(f, x, depth):
            yield None


        def g_parts(f, x, depth):
            r = yield g_int(f, x, depth + 1)
            yield r


        def g_int(f, x, depth):
            if depth > 3:
                return
            for mod, name in STRATS:
                M = R.need(mod)
                r = yield R.scoped(getattr(M, name)(f, x, depth))      #@calls 2
                if r is not None:
                    ok = yield R.scoped(g_check(r, f, x))
                    if ok is not None:
                        yield scale(K.ONE, r)
                        return
            T = R.need('int')
            yield T.scale(K.ZERO, f)
    ''',
    'casevo': '''
        import node as K
        import alg as A
        import parse as P
        import printer as PR
        import run as R
        import ti_system

        while True:
            k = ti_system.wait_key()
            if k == 45:
                break
            rec = R.go(('eval', 'x'))
    ''',
}


def good(name):
    """A GOOD module's source, dedented."""
    return textwrap.dedent(GOOD[name]).lstrip('\n')


def tree(**mods):
    out = {}
    for k in GOOD:
        out[k] = good(k)
    for k in mods:
        if mods[k] is None:
            out.pop(k, None)
        else:
            out[k] = textwrap.dedent(mods[k]).lstrip('\n')
    return out


def errors(**mods):
    return framelint.lint_sources(tree(**mods))


def only(**mods):
    """Errors for just these modules (no GOOD tree around them)."""
    src = {}
    for k in mods:
        src[k] = textwrap.dedent(mods[k]).lstrip('\n')
    return framelint.lint_sources(src)


def has(errs, *needles):
    for e in errs:
        if all(n in e for n in needles):
            return True
    return False


# -- the good tree ---------------------------------------------------------------------------

def test_good_tree_is_clean():
    assert errors() == []


def test_good_tree_passes_the_subset_lint():
    t = tree()
    for name in sorted(t):
        assert lint.lint(t[name], name + '.py') == [], name


def test_levels_and_report():
    an = framelint.analyze_sources(tree())
    lv = an.levels()
    assert lv['node']['mk'] == 7 and lv['node']['add_'] == 6 and lv['run']['go'] == 1
    assert lv['integ']['g_int'] == 2 and lv['integ']['scale'] == 4
    rep = an.report()
    # g_check(2) > check(3) > scale(4) > mul_(5) > add_(6) > mk(7)
    assert '7: 2 integ.g_check > 3 integ.check > 4 integ.scale > 5 node.mul_ > ' \
           '6 node.add_ > 7 node.mk' in rep
    assert ('7: 0 casevo.<module> > 1 run.go > 2 printer.record > 3 alg.nev > '
            '7 alg.postorder') in rep


def test_dev_table_resolves_keys():
    errs = only(run='''
        #@L 2
        DEV = {'zz': 'mtwo'}


        def need(key):                                                  #@L 3
            return __import__(DEV[key])
    ''', mone='''
        #@L 4
        import run as R


        def f(x):
            M = R.need('zz')
            return M.g(x)
    ''', mtwo='''
        #@L 4
        def g(x):
            return x
    ''')
    assert has(errs, 'mone.py:7', 'f (L4) -> mtwo.g (L4): callee must be > 4')


# -- edges -----------------------------------------------------------------------------------

def test_l4_to_l4_edge():
    errs = only(m='''
        #@L 4
        def a(x):
            return b(x)


        def b(x):
            return x
    ''')
    assert errs == ['m.py:3: a (L4) -> b (L4): callee must be > 4']


def test_cross_module_edge_through_alias():
    errs = errors(alg=good('alg').replace(
        "def csin(z):                                                    #@L 5",
        "def csin(z):                                                    #@L 6\n"
        "    K.add_([])"))
    assert has(errs, 'alg.py', 'csin (L6) -> node.add_ (L6): callee must be > 6')


def test_mods_literal_and_need_resolution():
    errs = errors(forms='''
        #@L 5
        import node as K
        import run as R


        def f(x):
            M = R.need('int')
            return M.check(x, x, x)


        def h(x):
            return R.MODS['int'].scale(x, x)


        def g_form(code, ctx):                                          #@L 2
            yield f(code)
    ''')
    assert has(errs, 'forms.py:7', 'f (L5) -> run.need (L3)')
    assert has(errs, 'forms.py:8', 'f (L5) -> integ.check (L3)')
    assert has(errs, 'forms.py:12', 'h (L5) -> integ.scale (L4)')


def test_unknown_attribute_and_unresolved_name():
    errs = errors(alg=good('alg') + '''

def bad(e):
    K.nosuch(e)
    return undefined_thing(e)
''')
    assert has(errs, "alg.py", "calls node has no 'nosuch'")
    assert has(errs, "alg.py", "calls unresolved name 'undefined_thing'")


def test_missing_and_out_of_range_levels():
    errs = only(m='''
        def a(x):
            return x


        def b(x):                                                       #@L 8
            return x


        def c(x):                                                       #@L 0
            return x
    ''')
    assert has(errs, 'm.py:1', 'no #@L annotation on a()')
    assert has(errs, 'm.py:5', 'b() is at level 8')
    assert has(errs, 'm.py:9', 'c() is at level 0')


# -- dynamic calls, hooks and tables ---------------------------------------------------------

def test_dynamic_call_needs_annotation():
    errs = only(m='''
        #@L 4
        HOOK = None
        NAT = None  #@native


        def a(f, x):
            NAT()
            HOOK(x)
            f(x)
            return getattr(x, 'y')(x)
    ''')
    assert not has(errs, 'm.py:7')
    for line in (8, 9, 10):
        assert has(errs, 'm.py:%d' % line, 'needs "#@calls k"')


def test_calls_level_must_exceed_caller():
    errs = only(m='''
        #@L 4
        def a(f, x):
            f(x)  #@calls 4
            return f(x)  #@calls 5
    ''')
    assert errs == ['m.py:3: a (L4) -> #@calls 4: callee must be > 4']


def test_tables():
    errs = only(m='''
        #@L 5
        def f(x):
            return x


        def g(x):                                                       #@L 7
            return x


        T1 = (f, g)
        T2 = (f, g)                                                     #@table 6
        T3 = (g,)                                                       #@table 6


        def use(i, x):                                                  #@L 3
            T3[i](x)  #@calls 7
            return T3[i](x)  #@calls 6
    ''')
    assert has(errs, 'm.py:10', 'needs "#@table k"', 'holds f')
    assert has(errs, 'm.py:11', '#@table 6 holds f at L5')
    assert not has(errs, 'm.py:12')
    assert has(errs, 'm.py:16', '#@calls 7 through a #@table 6')
    assert not has(errs, 'm.py:17')


# -- generators ------------------------------------------------------------------------------

def test_generator_called_without_yield():
    errs = only(m='''
        #@L 3
        def g_a(x):                                                     #@L 2
            yield x


        def g_b(x):                                                     #@L 2
            s = g_a(x)
            r = yield s
            yield r


        def plain(x):                                                   #@L 1
            return g_a(x)
    ''')
    assert has(errs, 'm.py:7', 'g_b() calls generator g_a without yield')
    assert has(errs, 'm.py:13', 'plain() calls generator g_a without yield')


def test_generator_referenced_without_call():
    errs = only(m='''
        #@L 2
        def g_a(x):
            yield x


        def f(x):
            h = g_a
            return h


        TAB = (g_a,)                                                    #@table 2
    ''')
    assert has(errs, 'm.py:7', 'f() references g_a without calling it')
    assert has(errs, 'm.py:11', 'module body references generator g_a')


def test_generator_level_and_yield():
    errs = only(m='''
        #@L 3
        def g_a(x):
            yield x


        def g_b(x):                                                     #@L 2
            return x
    ''')
    assert has(errs, 'm.py:2', 'generator g_a() must be exactly L2, not L3')
    assert has(errs, 'm.py:6', 'g_b() is named g_* but has no yield')


def test_generator_protocol_bans():
    errs = only(m='''
        #@L 2
        def g_a(x):
            yield from range(3)


        def g_b(x):
            if x:
                return 7
            yield x


        def g_c(x):
            try:
                yield x
            except:
                pass


        def g_d(x):
            try:
                yield x
            finally:
                x = 0
    ''')
    assert has(errs, 'm.py:3', 'yield from in generator g_a()')
    assert has(errs, 'm.py:8', 'return value in generator g_b()')
    assert has(errs, 'm.py:15', 'bare except: in generator g_c()')
    assert has(errs, 'm.py:20', 'finally in generator g_d()')
    assert len(errs) == 4


def test_virtual_generator_calls_are_not_frame_edges():
    errs = only(m='''
        #@L 2
        def g_a(x):
            yield x


        def g_b(x):
            r = yield g_a(x)
            yield r
    ''')
    assert errs == []


def test_dynamic_virtual_call_needs_calls_2():
    errs = only(m='''
        #@L 2
        def g_a(M, x):
            r = yield getattr(M, 'g_x')(x)
            s = yield getattr(M, 'g_x')(x)  #@calls 2
            yield (r, s)
    ''')
    assert errs == ['m.py:3: dynamic call in g_a() needs "#@calls k" (k: the level of the '
                    'callees)']


# -- imports and module bodies ---------------------------------------------------------------

def test_imports_inside_functions():
    errs = only(m='''
        #@L 3
        def f(x):
            import math
            return __import__('gc')
    ''')
    assert has(errs, 'm.py:3', 'import inside f()')
    assert has(errs, 'm.py:4', '__import__ inside f()')


def test_module_body_rules():
    errs = errors(alg=good('alg') + '''
ROOT = K.mk((2, 'x'))
if ROOT:
    ROOT = 0
TWICE = postorder(1)
''')
    assert has(errs, 'module body calls K.mk')
    assert has(errs, 'module body calls postorder')
    assert has(errs, 'module body: only imports, defs')


def test_nested_def():
    errs = only(m='''
        #@L 3
        def f(x):
            def inner(y):
                return y
            return inner(x)
    ''')
    assert has(errs, 'm.py:3', 'nested def inside f()')


def test_entry_body_is_level_0():
    errs = errors(casevo=good('casevo') + '''
g = P.g_eval(1, None)
''')
    assert has(errs, 'casevo.py', 'calls generator parse.g_eval without yield')


def test_import_cycle():
    errs = errors(parse=good('parse').replace('import node as K',
                                                'import node as K\nimport run as R'))
    assert has(errs, 'import cycle')


# -- src/ itself -----------------------------------------------------------------------------

SRC_FILES = lint.device_files(lint.SRC)


@pytest.fixture(scope='module')
def src_analysis():
    return framelint.analyze_dir(lint.SRC)


@pytest.mark.parametrize('path', SRC_FILES, ids=[os.path.basename(p) for p in SRC_FILES])
def test_src_framelint_clean(path, src_analysis):
    mine = []
    for e in src_analysis.errors:
        if os.path.normcase(e.split(':')[0]) == os.path.normcase(path) or \
                e.startswith(path + ':'):
            mine.append(e)
    assert mine == []


def test_cli_report_and_levels(tmp_path, capsys):
    d = tmp_path / 'src'
    d.mkdir()
    t = tree()
    for name in t:
        (d / (name + '.py')).write_text(t[name])
    out = tmp_path / 'levels.json'
    rc = framelint.main([str(d), '--report', '--levels', str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert '0 casevo.<module> > 1 run.go > ' in printed
    lv = json.loads(out.read_text())
    assert lv['node']['mk'] == 7


def test_hooks_through_an_alias():
    errs = errors(forms='''
        #@L 2
        import node as K
        import run as R


        def g_form(code, ctx):
            K.ESC()
            K.MEMFREE()
            R.BUSY(1)
            R.BUSY(1)  #@calls 3
            yield code
    ''', node=good('node').replace('ESC = None  #@native', 'ESC = None'))
    assert has(errs, 'forms.py:7', 'needs "#@calls k"')        # ESC lost its #@native
    assert not has(errs, 'forms.py:8')                         # MEMFREE is #@native
    assert has(errs, 'forms.py:9', 'needs "#@calls k"')        # BUSY holds U.busy (L2)
    assert not has(errs, 'forms.py:10')


def test_lazy_modules_are_not_imported_at_module_level():
    errs = errors(forms='''
        #@L 2
        import node as K
        import integ as IN


        def g_form(code, ctx):
            yield code
    ''')
    assert has(errs, 'forms.py:3', 'module-level import of lazy module integ')
