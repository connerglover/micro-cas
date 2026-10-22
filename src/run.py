#@L 2
"""CVRUN: the runner (go, the generator trampoline), the lazy loader, the command registry and
the text-only session (DESIGN 7.9, 7.11, 10, 15.1, 18.4-18.6).

go(job) evaluates one command and returns a record (kind, text, approx, flags); it never raises,
except KeyboardInterrupt after its reset. No node id survives a command: Ans, the history, the
variables and the functions are text. The UI (or a test) sets P.SESS = R once, so that the parser
sees this module's tables (docs/notes/T1.3.md, T1.6.md).
"""
import gc
import sys

import node as K
import parse as P
import printer as PR

# -- the command registry (DESIGN 15.1) ------------------------------------------------------------
# name: (family key, generator, min args, max args, flags, rule sets compiled at start).
# approx/evalf are builtins of g_eval (docs/notes/T1.5.md), not commands.
CMDS = {
    'simplify': ('norm', 'g_simplify', 1, 1, 0, ('trigsin', 'trigcos', 'tlin', 'lncollect')),
    'expand': ('norm', 'g_expand', 1, 1, P.F_NOAUTO, ()),
    'factor': ('fact', 'g_factor', 1, 2, P.F_NOAUTO, ()),
    'together': ('norm', 'g_together', 1, 1, P.F_NOAUTO, ()),
    'solve': ('solve', 'g_solve', 1, 2, P.F_SOLN, ()),
    'diff': ('diff', 'g_diff', 1, 3, P.F_ALWAYSAUTO, ('trigsin', 'trigcos')),
    'integrate': ('int', 'g_integrate', 1, 4, 0, ('itab',)),
    'limit': ('lim', 'g_limit', 2, 4, 0, ()),
    'taylor': ('ser', 'g_taylor', 1, 4, P.F_NOAUTO, ()),
    'partfrac': ('int2b', 'g_partfrac', 1, 2, P.F_NOAUTO, ()),
    'sum': ('sum', 'g_sum', 2, 4, 0, ()),
    'riemann': ('sum', 'g_riemann', 5, 6, 0, ()),
    'desolve': ('ode', 'g_desolve', 1, 3, 0, ()),
    'grad': ('diff', 'g_grad', 1, 2, 0, ()),
}
ALIAS = {'int': 'integrate', 'd': 'diff', 'deriv': 'diff', 'lim': 'limit', 'series': 'taylor',
         'ratnormal': 'together', 'dsolve': 'desolve', 'gradient': 'grad'}
MACROS = {'polararea': (4, 4, 'integrate((#1)^2/2,#2,#3,#4)'),
          'paramarea': (5, 5, 'integrate((#2)*diff(#1,#3),#3,#4,#5)'),
          'arclen': (4, 5, None)}       # None: P.AMAC by argument count
# The hint-line signatures are UI data: ui.HINT (the UI shows them before the engine loads).

# -- the loader tables (DESIGN 4.3, 18.4); the bundler rewrites DEV, PARTS, FAMILY, CLOSURE,
# COST, LINES, PEAKB and FRAG (build/bundle.py). Desktop DEV: runtime key -> src module.
DEPS = {'norm': (),                     # poly, rules, ident and diff are parts of norm
        'fact': ('norm',), 'solve': ('norm', 'fact'),
        'int': ('norm',), 'int2': ('norm',), 'int3': ('norm',), 'int3b': ('norm',),
        'int2b': ('norm', 'int2'),      # partial fractions call need('fact') themselves
        'lim': ('norm',),
        'def': ('norm',),               # integration, solve and limits are separate phases
        'sum': ('norm',),
        'ode': ('norm',),
        'menu': ()}
DEV = {'cat': 'catalog',
 'catb': 'catalogb',
 'def': 'defint',
 'defb': 'defintb',
 'defc': 'defintc',
 'diff': 'diff',
 'fact': 'factor',
 'factb': 'factorb',
 'factc': 'factorc',
 'factd': 'factord',
 'form': 'forms',
 'ident': 'ident',
 'int': 'integ',
 'int2': 'integ2',
 'int2b': 'integ2b',
 'int3': 'integ3',
 'int3b': 'integ3b',
 'itab': 'itab',
 'lim': 'limit',
 'limb': 'limitb',
 'limc': 'limitc',
 'menu': 'menu',
 'menub': 'menub',
 'norm': 'norm',
 'normb': 'normb',
 'normc': 'normc',
 'ode': 'ode',
 'odeb': 'odeb',
 'odec': 'odec',
 'oded': 'oded',
 'poly': 'poly',
 'polyb': 'polyb',
 'polyc': 'polyc',
 'rules': 'rules',
 'rulesb': 'rulesb',
 'ser': 'series',
 'serb': 'seriesb',
 'solve': 'solve',
 'solveb': 'solveb',
 'solvec': 'solvec',
 'solved': 'solved',
 'solvee': 'solvee',
 'sum': 'sums',
 'sumb': 'sumsb',
 'sumc': 'sumsc'}
PARTS = {'def': ('def', 'defb', 'defc'),
 'fact': ('fact', 'factb', 'factc', 'factd', 'form'),
 'int': ('int', 'itab'),
 'lim': ('lim', 'limb', 'limc', 'ser', 'serb'),
 'menu': ('menu', 'menub', 'cat'),
 'norm': ('norm', 'normb', 'normc', 'poly', 'polyb', 'polyc', 'rules', 'rulesb', 'ident', 'diff'),
 'ode': ('ode', 'odeb', 'odec', 'oded'),
 'solve': ('solve', 'solveb', 'solvec', 'solved', 'solvee'),
 'sum': ('sum', 'sumb', 'sumc')}
FAMILY = {'cat': 'menu',
 'defb': 'def',
 'defc': 'def',
 'diff': 'norm',
 'factb': 'fact',
 'factc': 'fact',
 'factd': 'fact',
 'form': 'fact',
 'ident': 'norm',
 'itab': 'int',
 'limb': 'lim',
 'limc': 'lim',
 'menub': 'menu',
 'normb': 'norm',
 'normc': 'norm',
 'odeb': 'ode',
 'odec': 'ode',
 'oded': 'ode',
 'poly': 'norm',
 'polyb': 'norm',
 'polyc': 'norm',
 'rules': 'norm',
 'rulesb': 'norm',
 'ser': 'lim',
 'serb': 'lim',
 'solveb': 'solve',
 'solvec': 'solve',
 'solved': 'solve',
 'solvee': 'solve',
 'sumb': 'sum',
 'sumc': 'sum'}
CLOSURE = {'catb': ('catb',),
 'def': ('norm', 'def'),
 'fact': ('norm', 'fact'),
 'int': ('norm', 'int'),
 'int2': ('norm', 'int2'),
 'int2b': ('norm', 'int2', 'int2b'),
 'int3': ('norm', 'int3'),
 'int3b': ('norm', 'int3b'),
 'lim': ('norm', 'lim'),
 'menu': ('menu',),
 'norm': ('norm',),
 'ode': ('norm', 'ode'),
 'solve': ('norm', 'fact', 'solve'),
 'sum': ('norm', 'sum')}
COST = {}           # part key -> steady bytes; LINES: part key -> lines (the bundler's numbers)
LINES = {}
PEAKB = 80          # compile peak per line (18.7)
FRAG = 3072
EVDICT = 0          # 1: clear a module's globals before deleting it (device; see unload)
SOFT = ()           # device: stateless packs to unload when no family can give way (FASTBOOT)
VIEW = ()           # device: UI packs; only unloaded while go() computes (none of their code runs)
AUX = ()            # device: computation code that never reaches the loader; unloaded last
INGO = False        # go() is computing
ROOM = {}           # device: phase -> (soft pack, bytes it needs to load); see room()
SHEDAT = 0          # device: below this many free bytes after parsing, idle soft packs unload
KEEPFREE = 40960    # between commands, evict LRU families until this much is free (18.5)

# -- loader state ------------------------------------------------------------------------------
MODS = {}           # part key -> module
LOADED = []         # loaded family keys, in load order
USE = {}            # family key -> LRU stamp
CLOCK = [0]
PINNED = []         # families preloaded for the running command (never evicted during it)
LIVE = {}           # family -> pins held by suspended generators (never evicted while > 0)
NEEDED = []         # per trampoline slot: the families that generator obtained through need

MEMFREE = None  #@native
BUSY = None         # U.busy (L2), called every 512 engine steps

# -- the trampoline (DESIGN 10) ----------------------------------------------------------------
SCOPE = ['scope']   # unique sentinels, compared with 'is'
TICK = ['tick']
KBI = ['kbi']
MAXGEN = 64
BUDGET = 20000
LASTSOFT = [None]


def _g():                                                       #@L 2
    yield


GEN = type(_g())

# -- the session (DESIGN 7.11): text only ------------------------------------------------------
ANS = None          # the text of the last answer that was not a message
HIST = []           # [input, output, kind, approx, flags, forms]
VARS = {}           # name -> canonical text
FUNCS = {}          # name -> (params tuple, body text)
SET = {'deg': 0}
HISTMAX = 40
HISTTEXT = 8192
MAXOPEN = 64        # autoclose: more open brackets leave the line as typed
MAXANS = 8
HINTV = ('x', 'y', 't', 'z', 'n', 'k', 'theta')     # a store here sets F_PURGEHINT

# the running command (read by the printer and CVFORM if they wish)
LINE = ''           # the input with autoclose applied (the history text)
CTX = None          # the evaluation context [deg, mainvar, approx, inert]
FLAGS = 0           # the record flags found by start
TARGET = None       # the variable that rules 2-3 store into
FORMINDEX = 0
FORMNAME = 'exact'

# -- records: (kind, text, approx, flags) --------------------------------------------------------
R_ANS = 'ans'
R_MSG = 'msg'
F_PLUSC = 1         # an antiderivative: the view draws + C (7.9 rule 6, 13.6)
F_PURGEHINT = 2     # a store into a working variable (7.9)
F_APPROX = 4        # the answer is a numeric fallback (13.6; set by the printer)
F_DEG = 8           # evaluated in degree mode (F4 re-parses in the entry's mode)
F_SOLN = P.F_SOLN   # 16: the result of solve (the printer's sentinel messages)

M_INTERRUPTED = 'Interrupted'
M_OOM = 'Out of memory'
M_TOO_COMPLEX = 'Expression too complex'
M_UNDEFINED = 'Undefined'
M_INTERNAL = 'Internal error'
M_TOO_LONG = 'Too long to compute'
M_NOANS = 'No answer yet'
M_MANYANS = 'Too many Ans'
M_BADNAME = 'Invalid variable name'
M_CIRC = 'Circular definition'
M_ERROR = 'Error'
REC_OOM = (R_MSG, M_OOM, None, 0)  # preallocated: built with no memory to spare (18.6)


def scoped(g):                                                  #@L 7
    return (SCOPE, g)


def okname(v):                                                  #@L 7
    """A valid variable or function name (7.9): [a-z][a-z0-9]*, not a command, function,
    constant or VALUE word; theta is allowed, and d (D9)."""
    if not v or v[0] < 'a' or v[0] > 'z':
        return False
    for ch in v:
        if not ('a' <= ch <= 'z' or '0' <= ch <= '9'):
            return False
    if v == 'theta' or v == 'd':
        return True
    return not (v in P.FNAMES or v in P.VNAMES or v in CMDS or v in ALIAS or v in MACROS or
                v == 'ans')


# -- the runner ----------------------------------------------------------------------------------

def go(job):                                                    #@L 1
    """job: ('eval', text) or ('form', history index). Returns a record; never raises, except
    KeyboardInterrupt, which is re-raised after the reset (10.4, 18.6)."""
    global LINE, CTX, FLAGS, TARGET, INGO
    INGO = True
    for attempt in (0, 1):   # an Out of memory with stale families loaded is retried once
        before = list(LOADED)
        rec = None
        err = None
        stack = g = val = None
        LASTSOFT[0] = None
        LINE = job[1] if job[0] == 'eval' else ''
        CTX = None
        FLAGS = 0
        TARGET = None
        try:
            sweep()
            room('input')
            code, ctx, ks, rs = start(job)
            # parsed: the input code is idle until the next line. A command without families
            # (arithmetic) keeps the layout pack, which would otherwise reload to show it.
            while MEMFREE is not None and (attempt or ks and MEMFREE() < SHEDAT) and shed():
                pass
            for k in ks:                     # the preload (18.4), before the node table grows
                need(k)
                for c in CLOSURE.get(FAMILY.get(k, k), (k,)):
                    if c not in PINNED:
                        PINNED.append(c)
            for r in rs:
                if r not in K.RULECACHE:
                    MODS['rules'].rset(r)
            ks = rs = None
            if code is None:                 # purge or a definition: ctx is the message
                rec = (R_MSG, ctx, None, 0)
            else:
                if job[0] == 'eval':         # the root generator is created here, never in a helper
                    g = P.g_eval(code, ctx)
                else:
                    g = MODS['form'].g_form(code, ctx)
                stack = [g]
                marks = [-1]
                NEEDED.append([])
                steps = 0
                while stack:
                    steps += 1
                    if not steps & 31:
                        if K.ESC is not None and K.ESC():
                            raise K.Cancel()
                        if steps > BUDGET:
                            raise K.CasError(M_TOO_LONG)
                        if not steps & 511 and BUSY is not None:
                            BUSY(steps)                                     #@calls 2
                    top = stack[-1]
                    try:
                        y = top.send(val)
                    except StopIteration:
                        y = None
                    except K.CasSoft as e:
                        LASTSOFT[0] = e
                        y = None
                    else:
                        if y is TICK:
                            val = None
                            continue
                        if type(y) is GEN or (type(y) is tuple and len(y) == 2 and
                                              y[0] is SCOPE):
                            if len(stack) >= MAXGEN:
                                raise K.CasError(K.M_COMPLEX)
                            if type(y) is GEN:
                                stack.append(y)
                                marks.append(-1)
                            else:
                                stack.append(y[1])
                                marks.append(K.NN)
                            NEEDED.append([])
                            val = None
                            continue
                    stack.pop()
                    for f in NEEDED.pop():   # this generator no longer keeps its families live
                        for c in CLOSURE.get(f, (f,)):
                            LIVE[c] -= 1
                    m = marks.pop()
                    if m >= 0:
                        y = K.keep(m, y)
                    val = y
                stack = g = None
                if val is None:              # the root failed: Undefined, or another soft failure
                    e = LASTSOFT[0]
                    if e is not None and e.args and type(e.args[0]) is str:
                        rec = (R_MSG, e.args[0], None, 0)
                    else:
                        rec = (R_MSG, M_UNDEFINED, None, 0)
                else:
                    del PINNED[:]            # computed: its families may give way to the printer
                    room('print')
                    rec = PR.record(val, (job[0], LINE, ctx, FLAGS))   # text, decimal, sentinels
        except K.Cancel:
            err = M_INTERRUPTED
        except K.CasError as e:
            err = e.args
        except K.CasSoft:                    # Undefined from start() or the printer
            err = M_UNDEFINED
        except (MemoryError, K.CasMemory):
            err = M_OOM
        except RuntimeError:                 # depth: should never fire if the tests pass
            err = M_TOO_COMPLEX
        except KeyboardInterrupt:
            err = KBI                        # re-raised below, after the reset
        except Exception as e:               # a bug: report it, never lose the session
            err = (M_INTERNAL, type(e).__name__)
        stack = g = val = top = y = None     # every path: drop the generator frames first (top:
        del NEEDED[:]                        # the last one resumed), reset (18.6), then the message
        LASTSOFT[0] = None
        LIVE.clear()
        spare = False                # an earlier command's families, or idle soft packs, may
        for f in before:             # have caused the failure; the retry runs without them
            if f not in PINNED:
                spare = True
        for t in (SOFT, VIEW, AUX):
            for n in t:
                if n in sys.modules:
                    spare = True
        del PINNED[:]
        K.reset()
        try:
            if sweep() and type(err) is tuple and err and err[0] == M_INTERNAL:
                err = M_OOM          # a pack import cut short by memory caused this error
            if err is M_OOM:
                evict_all()
                if spare and attempt == 0:
                    continue         # once more on a heap holding only what this command needs
            else:
                trim()
        except MemoryError:          # the cleanup itself ran out: still never raise
            if err is not KBI:
                err = M_OOM
            MODS.clear()
            del LOADED[:]
        break
    INGO = False
    if err is KBI:
        raise KeyboardInterrupt()
    try:
        if err is not None:
            rec = msg_rec(err)
        return finish(job, rec)
    except MemoryError:                  # the session store after the reset: still no raise
        evict_all()
        return REC_OOM


def start(job):                                                 #@L 2
    """The text passes and the runner's input rules (7.1, 7.9), then the preload (18.4).
    Returns (code, ctx), or (None, message) for purge and definitions."""
    global LINE, CTX, FLAGS, TARGET, FORMINDEX
    ks = []                              # the families to preload, and the rule sets
    rs = []
    if job[0] != 'eval':                 # F4: the entry's original answer text, inert (14)
        FORMINDEX = job[1]
        e = HIST[job[1]]
        code = P.rpn(P.tokens(e[5][0][1] if e[5] else e[1], 0))
        FLAGS = e[4] & F_DEG
        ctx = [1 if FLAGS else 0, None, 0, 1]
        ks.append('form')
    else:
        s = job[1]
        st = []                          # 1. autoclose (FlowCE console_autoclose)
        for ch in s:
            if ch == '(' or ch == '[' or ch == '{':
                st.append(P.PAIR[ch])
                if len(st) > MAXOPEN:
                    st = None
                    break
            elif ch == ')' or ch == ']' or ch == '}':
                if not st or st.pop() != ch:
                    st = None            # a mismatched closer: rpn reports it
                    break
        while st:
            s = s + st.pop()
        LINE = s
        if 'ans()' in s:                 # 2. Ans, in parentheses
            if ANS is None:
                raise K.CasError(M_NOANS)
            if s.count('ans()') > MAXANS:
                raise K.CasError(M_MANYANS)
            s = s.replace('ans()', '(' + ANS + ')')
        tk = P.lex(s)                    # stage 3
        n = len(tk)
        if n and tk[0][1] == 'purge' and tk[0][4] & P.F_CALL:  # rule 0: purge(name, ...),
            if n < 4 or n & 1 or tk[n - 1][0] != P.K_RP:       # whole names (no cutting)
                raise K.CasError(P.M_PURGE)
            out = []
            for j in range(2, n - 1):
                if tk[j][0] != (P.K_COMMA if j & 1 else P.K_NAME):
                    raise K.CasError(P.M_PURGE)
                if not j & 1:
                    out.append(tk[j][1])
            for v in out:
                if v in VARS:
                    del VARS[v]
                if v in FUNCS:
                    del FUNCS[v]
            return None, ', '.join(out) + ' deleted', (), ()
        tk = P.ti_implicit(P.ti_rewrite(tk))     # stages 4-5: the line as typed, before stage 6
        n = len(tk)
        t0 = tk[0] if n else (0, '', 0, 0, 0)
        call = t0[0] == P.K_NAME and t0[4] & P.F_CALL and n > 1
        c = 2
        while call and c < n and tk[c][0] != P.K_RP:
            c += 1
        if call and c + 2 < n and tk[c + 1][0] == P.K_OP and tk[c + 1][1] == ':=':
            # rule 1: f(x, ...) := body (stage 4 wrote := for f(x)=body)
            f = t0[1]
            if not okname(f):
                raise K.CasError(M_BADNAME)
            ps = []
            for j in range(2, c):
                u = tk[j]
                if j & 1:
                    if u[0] != P.K_COMMA:
                        raise K.CasError(P.M_ASSIGN)
                elif u[0] != P.K_NAME or u[4] or not okname(u[1]) or u[1] in ps or u[1] == f:
                    raise K.CasError(P.M_ASSIGN)
                else:
                    ps.append(u[1])
            if not c & 1:                # f() or a trailing comma
                raise K.CasError(P.M_ASSIGN)
            body = tk[c + 2:]
            P.rpn(body)                  # a syntax error shows now, not at the first use
            FUNCS[f] = (tuple(ps), P.untok(body))
            if f in VARS:
                del VARS[f]
            return None, f + '(' + ','.join(ps) + ') defined', (), ()
        d = 0
        j = -1
        cm = 0
        for i in range(n):
            k = tk[i][0]
            if k == P.K_LP or k == P.K_LB:
                d += 1
            elif k == P.K_RP or k == P.K_RB:
                d -= 1
            elif d == 0 and k == P.K_COMMA:
                cm = 1
            elif d == 0 and k == P.K_OP and tk[i][1] == '=>' and j < 0:
                j = i
        nm = None
        if j >= 0:                       # rule 2: expr => name
            u = tk[n - 1]
            if j != n - 2 or u[0] != P.K_NAME or u[4] or not okname(u[1]):
                raise K.CasError(M_BADNAME)
            nm = u[1]
            toks = P.expand_names(tk[:j])
        else:
            toks = None
            if n > 2 and t0[0] == P.K_NAME and not t0[4] and tk[1][0] == P.K_OP and (
                    tk[1][1] == '=' or tk[1][1] == ':=') and not cm and okname(t0[1]):
                nm = t0[1]               # rule 3: name = expr, name not in expr (as typed)
                for i in range(2, n):
                    if tk[i][0] == P.K_NAME and tk[i][1] == nm:
                        nm = None
                if nm is not None:
                    toks = P.expand_names(tk[2:])
            if toks is None:
                toks = P.expand_names(tk)
        TARGET = nm
        code = P.rpn(toks)
        if nm is None and code and code[-1][0] == 'o' and code[-1][1] == '=':
            u = None                     # rule 4: a lone equation in one unknown -> solve
            for it in code:
                if it[0] == 's' and it[1] not in P.CONSTS and it[1] != u:
                    u = it[1] if u is None else ''
            if u:
                code.append(('s', u, code[-1][2]))
                code.append(('F', 'solve', 2, code[-1][2]))
        FLAGS = F_DEG if SET['deg'] else 0
        if call and ALIAS.get(t0[1], t0[1]) == 'integrate':      # rule 6: + C
            d = 0
            cm = 0
            for i in range(1, n):
                k = tk[i][0]
                if k == P.K_LP or k == P.K_LB:
                    d += 1
                elif k == P.K_RP or k == P.K_RB:
                    d -= 1
                    if not d:
                        break
                elif d == 1 and k == P.K_COMMA:
                    cm += 1
            if cm <= 1:
                FLAGS |= F_PLUSC
        i = len(code) - 1
        while i >= 0 and code[i][0] == 'P':
            i -= 1
        if i >= 0 and code[i][0] == 'F':
            e = CMDS.get(ALIAS.get(code[i][1], code[i][1]))
            if e is not None:
                FLAGS |= e[4] & F_SOLN
        ctx = [SET['deg'], None, 0, 0]
        for it in code:                  # the commands of the line
            if it[0] == 'F':
                f = ALIAS.get(it[1], it[1])
                e = CMDS.get(f)
                if e is not None:
                    definite = f == 'integrate' and it[2] == 4 and e[1] == 'g_integrate'
                    family = 'def' if definite else e[0]
                    if family not in ks:
                        ks.append(family)
                    for r in (() if definite else e[5]):
                        if r not in rs:
                            rs.append(r)
    CTX = ctx
    return code, ctx, ks, rs


def finish(job, rec):                                           #@L 2
    """After the reset: the store of rules 2-3, the history and Ans (eval jobs only). The
    history entry is made first, so a MemoryError there leaves VARS and ANS unchanged."""
    global ANS
    if job[0] != 'eval':
        e = HIST[job[1]]
        if e[5] is None:
            e[5] = [('exact', e[1])]
        if rec is not None and rec[0] == R_ANS:
            if FORMNAME == 'exact':
                e[5] = e[5][:1]
            elif (FORMNAME, rec[1]) not in e[5]:
                e[5].append((FORMNAME, rec[1]))
            e[1] = rec[1]
            ANS = rec[1]
        else:
            e[1] = e[5][0][1]
            e[5] = e[5][:1]
            ANS = e[1]
        return rec
    if rec is None:
        return rec
    nm = None
    if rec[0] == R_ANS:
        s = rec[1]
        nm = TARGET
        if nm is not None:
            i = 0                        # the stored text must not name its own variable
            n = len(s)
            while i < n and nm is not None:
                j = i
                while j < n and (s[j].isalpha() or s[j].isdigit() or s[j] == "'"):
                    j += 1
                if j > i:
                    if s[i:j] == nm and (j >= n or s[j] != '('):
                        nm = None
                    i = j
                else:
                    i += 1
            if nm is None:
                rec = (R_MSG, M_CIRC, None, 0)
        if rec[0] == R_ANS:
            fl = rec[3] | FLAGS
            if nm in HINTV:
                fl |= F_PURGEHINT
            rec = (R_ANS, s, rec[2], fl)
    HIST.append([LINE, rec[1], rec[0], rec[2], rec[3], None])
    if rec[0] == R_ANS:
        if nm is not None:
            VARS[nm] = rec[1]
            if nm in FUNCS:
                del FUNCS[nm]
        ANS = rec[1]
    t = 0
    for e in HIST:
        t += len(e[0]) + len(e[1])
    while len(HIST) > HISTMAX or (t > HISTTEXT and len(HIST) > 1):
        e = HIST.pop(0)
        t -= len(e[0]) + len(e[1])
    return rec


def msg_rec(err):                                               #@L 2
    """A message record, built on the empty table (preallocated texts)."""
    if type(err) is tuple:
        if len(err) == 2 and err[0] is M_INTERNAL:
            return (R_MSG, M_INTERNAL + ': ' + err[1], None, 0)
        err = err[0] if err and type(err[0]) is str else M_ERROR
    return (R_MSG, err, None, 0)


# -- the lazy loader (DESIGN 18.4, 18.5) -----------------------------------------------------------

def need(key):                                                  #@L 3
    """Load the family of key and its DEPS closure (one compile at a time, evicting LRU
    families that are neither pinned nor live), pin the closure while the calling generator is
    on the trampoline, and return the module of key."""
    fam = FAMILY.get(key, key)
    cl = CLOSURE.get(fam, (fam,))
    CLOCK[0] += 1
    now = CLOCK[0]
    for f in cl:                         # LRU stamp; this closure is no victim of this call
        USE[f] = now
    for f in cl:
        if f in LOADED:
            continue
        for p in PARTS.get(f, (f,)):
            n = DEV[p]
            if n in sys.modules:         # on the calculator a family's parts share one pack
                MODS[p] = sys.modules[n]
                continue
            want = COST.get(p, 0) + PEAKB * LINES.get(p, 0) + FRAG
            while MEMFREE is not None and MEMFREE() < want:
                gc.collect()            # reclaim prior decode buffers before evicting/refusing
                if MEMFREE() >= want:
                    break
                if shed():              # input/printer/layout code is idle while computing
                    continue
                v = victim(now)
                if v is None:
                    if shed(None, AUX):
                        continue
                    raise K.CasMemory()
                evict(v)
            while True:
                try:
                    MODS[p] = __import__(n)  # the body runs one level deeper; defines only
                    break
                except MemoryError:          # often fragmentation: free one more thing, retry
                    unload(n)                # MicroPython 1.12 keeps the half-run module
                    if not shed():
                        v = victim(now)
                        if v is not None:
                            evict(v)
                        elif not shed(None, AUX):
                            raise
                    gc.collect()
                except BaseException:        # [on] in the middle of the body
                    unload(n)
                    raise
        LOADED.append(f)
    if NEEDED:
        sl = NEEDED[-1]
        if fam not in sl:
            sl.append(fam)
            for f in cl:
                LIVE[f] = LIVE.get(f, 0) + 1
    return MODS[key]


def victim(now):                                                #@L 4
    """The least recently used family that no pin, live generator or current closure holds."""
    v = None
    for x in LOADED:
        if x not in PINNED and not LIVE.get(x, 0) and USE[x] != now and (
                v is None or USE[x] < USE[v]):
            v = x
    return v


def drop(keys, cache=False):                                    #@L 3
    """Phase eviction (18.5): the families of keys leave the calling generator's pins and
    PINNED; each one that no suspended generator keeps live is evicted now. A failed search
    strategy uses cache=True to release only its own pin and retain an LRU cache entry."""
    sl = NEEDED[-1] if NEEDED else []
    for k in keys:
        f = FAMILY.get(k, k)
        if f in sl:
            sl.remove(f)
            for c in CLOSURE.get(f, (f,)):
                LIVE[c] -= 1
        if not cache and f in PINNED:
            PINNED.remove(f)
        if not cache and f in LOADED and not LIVE.get(f, 0):
            evict(f)


def evict(f):                                                   #@L 4
    # the bookkeeping first: an [on] or MemoryError inside unload leaves at worst a pack that
    # need() imports again, never LOADED naming a family that MODS has lost
    if f in LOADED:
        LOADED.remove(f)
    for p in PARTS.get(f, (f,)):
        MODS.pop(p, None)
    for p in PARTS.get(f, (f,)):
        unload(DEV.get(p))
    gc.collect()


def unload(n):                                                  #@L 5
    """Drop a loaded module (on the calculator a pack). With EVDICT its globals become None
    first: MicroPython's collector is conservative, and a stale word left on the C stack by the
    import would otherwise keep the whole module alive (docs/notes/FASTBOOT.md)."""
    if n not in sys.modules:
        return
    m = sys.modules[n]
    del sys.modules[n]
    if EVDICT:
        try:                    # dir() allocates: on a full heap the module just leaves
            for k in dir(m):    # sys.modules (the Out-of-memory cleanup must not raise)
                if not k.startswith('__'):
                    setattr(m, k, None)
        except MemoryError:
            pass


def sweep():                                                    #@L 2
    """Drop every soft, view or aux pack whose import was cut short: MicroPython 1.12 keeps
    such a module in sys.modules, and code reaching it would fail until the session ends. A
    pack's last statement binds __ok__ (build/packs.py). True when one was dropped."""
    found = False
    for t in (SOFT, VIEW, AUX):
        for n in t:
            if n in sys.modules and getattr(sys.modules[n], '__ok__', None) is None:
                unload(n)
                found = True
    return found


def trim():                                                     #@L 2
    """Between commands: evict LRU families until KEEPFREE bytes are free (18.5)."""
    while LOADED and MEMFREE is not None and MEMFREE() < KEEPFREE:
        v = LOADED[0]
        for f in LOADED:
            if USE.get(f, 0) < USE.get(v, 0):
                v = f
        evict(v)


def shed(keep=None, packs=None):                                #@L 4
    """Unload one cached soft pack (input, printer, layout) other than keep; False when none
    is loaded. Code reaches soft packs only through __import__, so the next use reloads it."""
    if packs is None:
        packs = (VIEW + SOFT) if INGO else SOFT
    for n in packs:
        if n != keep and n in sys.modules:
            unload(n)
            gc.collect()
            return True
    return False


def room(phase):                                                #@L 2
    """Load a phase's soft pack: unpinned families, then other soft packs, give way until the
    pack and FRAG fit, and once more if the import still fails. A no-op on the desktop (ROOM is
    empty) and when the pack is loaded. Only called between computations (nothing is live)."""
    if phase not in ROOM or MEMFREE is None:
        return
    name, cost = ROOM[phase]
    if name in sys.modules:
        if getattr(sys.modules[name], '__ok__', None) is not None:
            return
        unload(name)                     # cut short by a MemoryError elsewhere: import it again
    want = cost + FRAG
    while MEMFREE() < want:
        gc.collect()
        if MEMFREE() >= want:
            break
        v = None
        for x in LOADED:
            if x not in PINNED and not LIVE.get(x, 0) and (v is None or USE[x] < USE[v]):
                v = x
        if v is not None:
            evict(v)
        elif not shed(name) and not shed(name, AUX):
            break
    try:
        __import__(name)                 # the body runs one level deeper; defines only
    except MemoryError:                  # often fragmentation, not exhaustion: everything that
        unload(name)                     # this boundary can spare goes, then one more try
        for f in list(LOADED):                                  #@unordered-ok
            if f not in PINNED and not LIVE.get(f, 0):
                evict(f)
        while shed(name):
            pass
        gc.collect()
        try:
            __import__(name)
        except BaseException:
            unload(name)
            raise


def evict_all():                                                #@L 2
    """After MemoryError (18.6): every lazy module, including a family cut short, then gc.
    Allocates nothing that can fail first: it runs on a full heap."""
    del LOADED[:]
    while MODS:
        for p in MODS:          # any key (dict.popitem is missing on the device) #@unordered-ok
            break
        del MODS[p]
        unload(DEV.get(p))
    for n in SOFT:
        unload(n)
    for n in AUX:
        unload(n)
    if INGO:
        for n in VIEW:
            unload(n)
    gc.collect()
