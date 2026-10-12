"""CVPARSE: lexer, TI input passes, classifier hook, shunting-yard and builders (DESIGN 7).

T1.3: the token passes lex (stage 3), ti_rewrite (stage 4), ti_implicit (stage 5), classify
and its hook, rpn (stage 7), and untok. T1.5: tokens (stages 3-6), expand_names (stage 6),
tcode and inst (templates and rule patterns), g_eval (user input), exact and approx (floats).

A token is the flat tuple (kind, value, start, end, flags); start and end are source offsets.
Tokens made by a pass (an implicit '*', the parentheses of sin x) have start == end, or span
the blanks they replace, so untok can rebuild the text (docs/notes/T1.3.md).
"""
import math

import node as K
import alg as A

# token kinds (DESIGN 7.2)
K_NUM = 0           # value (p, 1) for an integer, a float for a decimal (D8)
K_NAME = 1          # value: the name ('pi' for the pi glyph, 'theta' for the theta glyph)
K_OP = 2            # + - * / ^ = != < <= > >= => :=
K_LP = 3            # (
K_RP = 4            # )
K_LB = 5            # [ or {
K_RB = 6            # ] or }
K_COMMA = 7
K_POST = 8          # postfix ! or '

# token flags
F_IMPL = 1          # a '*' inserted by stage 4 or 5 (drawn as a thin gap)
F_CALL = 2          # a name whose '(' opens a call

# name classes (DESIGN 7.3; FlowCE TI_NAME_*)
C_UNK = 0
C_VAL = 1
C_FN = 2
C_KEY = 3
C_UFN = 4

MAXNEST = 32        # open brackets in rpn
MAXCUT = 32         # longer unknown names are never cut (FlowCE IM_MAXCUT)

LET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
DIG = '0123456789'
ALNUM = LET + DIG
PI_CH = chr(0x3c0)
TH_CH = chr(0x3b8)

# -- the classifier tables (DESIGN 7.3) -------------------------------------------------------
# FUNCTION: the function names the builder knows, plus O and purge. Commands, aliases and
# macros come from the session hook.
FNAMES = {'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'asec', 'acsc',
          'acot', 'sinh', 'cosh', 'tanh', 'asinh', 'acosh', 'atanh', 'ln', 'log', 'log10',
          'exp', 'sqrt', 'surd', 'abs', 'sign', 'floor', 'ceil', 'O', 'purge', 'approx',
          'evalf'}
# VALUE: constants and the Riemann methods (so that mid is not cut into m*i*d)
VNAMES = {'pi', 'e', 'i', 'oo', 'inf', 'infinity', 'undef', 'theta', 'true', 'false',
          'left', 'right', 'mid', 'trap'}
KWORDS = set()      # KEYWORD: none in v1 (no programming)
# The classify hook: the module (run) whose CMDS, ALIAS, MACROS (FUNCTION), VARS (VALUE) and
# FUNCS (USERFN) tables classify reads at call time. None: no session.
SESS = None

# -- ti_rewrite tables (FlowCE src/tiinput.cc) ---------------------------------------------------
# unary functions that may be written without parentheses or with a power; longest first, the
# first prefix match wins
FNT = ('asinh', 'acosh', 'atanh', 'log10', 'sinh', 'cosh', 'tanh', 'asin', 'acos', 'atan',
       'sqrt', 'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'exp', 'abs', 'log', 'ln')
INV = {'sin': 'asin', 'cos': 'acos', 'tan': 'atan', 'sec': 'asec', 'csc': 'acsc',
       'cot': 'acot', 'sinh': 'asinh', 'cosh': 'acosh', 'tanh': 'atanh'}
# Greek names stay whole (FlowCE im_greek)
GREEK = {'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota',
         'kappa', 'lambda', 'mu', 'nu', 'xi', 'omicron', 'rho', 'sigma', 'tau', 'upsilon',
         'phi', 'chi', 'psi', 'omega'}
CALL1 = ('f', 'g', 'h')                 # call letters (DESIGN 7.5)

# -- rpn tables (DESIGN 7.7) --------------------------------------------------------------------
PREC = {'=>': 1, ':=': 1, '=': 3, '!=': 3, '<': 3, '<=': 3, '>': 3, '>=': 3, '+': 4, '-': 4,
        '*': 5, '/': 5, 'neg': 6, '^': 7}
PAIR = {'(': ')', '[': ']', '{': '}'}
OP2 = ('!=', '<=', '>=', '=>', ':=')
OP1 = '+-*/^=<>'

# -- builder tables (DESIGN 7.6, 7.8, 9.2) --------------------------------------------------------
# ctx, the evaluation context: the list [deg, mainvar, approx, inert]. g_eval sets X_APPROX when
# the input has a float; command generators receive the same list (DESIGN 15.1).
X_DEG = 0           # 1: degree mode (6.5)
X_MV = 1            # the main variable id for the printer, or None (12.3); g_eval leaves it
X_APPROX = 2        # 1: the input had a float: exact() on input, approx() on the result (6.3)
X_INERT = 3         # 1: inert mode (F4, the round trip): commands build CALL nodes, no simplify
# registry flags (the fifth field of R.CMDS entries, DESIGN 15.1); bits apart from F_IMPL/F_CALL
F_NOAUTO = 4        # skip the default simplify path
F_ALWAYSAUTO = 8    # always run it
F_SOLN = 16         # the result is a solution list (the printer's sentinel messages)
MAXEXP = 64         # stage 6: expansions per line
MAXDEF = 16         # stage 6: nested expansions
M_ARGS = 'wrong number of arguments'
M_DEEP = 'definition too deeply nested'
M_SYNTAX = 'syntax error'
M_ASSIGN = 'invalid assignment'
M_PRIME = "invalid use of '"
M_PURGE = 'invalid use of purge'
# one-argument functions -> op codes (5.2)
ONEARG = {'sin': K.SIN, 'cos': K.COS, 'tan': K.TAN, 'sec': K.SEC, 'csc': K.CSC, 'cot': K.COT,
          'asin': K.ASIN, 'acos': K.ACOS, 'atan': K.ATAN, 'sinh': K.SINH, 'cosh': K.COSH,
          'tanh': K.TANH, 'ln': K.LN, 'abs': K.ABS, 'sign': K.SIGN, 'floor': K.FLOOR,
          'ceil': K.CEIL}
INVAUX = {'asec': K.ACOS, 'acsc': K.ASIN, 'acot': K.ATAN}     # asec(u) = acos(1/u), ...
# the other builder functions: name -> (min, max) arguments
FARGS = {'sqrt': (1, 1), 'exp': (1, 1), 'log': (1, 2), 'log10': (1, 1), 'surd': (2, 2),
         'O': (1, 1), 'asinh': (1, 1), 'acosh': (1, 1), 'atanh': (1, 1)}
CONSTS = {'pi': K.PI, 'e': K.E, 'i': K.I, 'oo': K.OO, 'inf': K.OO, 'infinity': K.OO,
          'undef': K.UNDEF, 'true': K.TRUE, 'false': K.FALSE}
RELOPS = {'=': K.EQ, '!=': K.NE, '<': K.LT, '<=': K.LE, '>': K.GT, '>=': K.GE}
D180 = (0, 1, 0, 180)               # the NUM tuple 1/180: a degree is pi/180 (6.5)
R180 = (0, 180, 0, 1)
# rule letters (DESIGN 9.2): letter -> (slot, constraint). inst makes (WILD, slot, constraint)
# leaves in pattern mode. x is the focus variable, bound by the engine before matching; T is
# the right-hand-side slot of the solve inverse table (9.3).
W_ANY = 0
W_FREE = 1
W_NUMB = 2
W_INT = 3
W_LIN = 4
W_QUAD = 5
W_REST = 6
WSLOT = {'U': (0, 0), 'V': (1, 0), 'W': (2, 0), 'A': (3, 1), 'B': (4, 1), 'C': (5, 1),
         'K': (6, 1), 'M': (7, 2), 'N': (8, 2), 'P': (9, 3), 'L': (10, 4), 'Q': (11, 5),
         'R': (12, 6), 'x': (13, 0), 'T': (14, 0)}
XSLOT = 13
TSLOT = 14
NSLOT = 15
# macros whose expansion depends on the argument count (R.MACROS entry with template None)
AMAC = {'arclen': ('integrate(sqrt(1+diff(#1,#2)^2),#2,#3,#4)',
                   'integrate(sqrt(diff(#1,#3)^2+diff(#2,#3)^2),#3,#4,#5)')}
NOSES = {}          # VARS, FUNCS and MACROS when there is no session


# -- classifier -----------------------------------------------------------------------------------

def classify(name):                                             #@L 7
    """FlowCE's five classes for a name (DESIGN 7.3): C_UNK, C_VAL, C_FN, C_KEY or C_UFN."""
    if name in KWORDS:
        return C_KEY
    if name in VNAMES:
        return C_VAL
    S = SESS
    if S is not None:
        if name in S.VARS:
            return C_VAL
        if name in S.FUNCS:
            return C_UFN
    if name in FNAMES:
        return C_FN
    # D9: the alias d is a call only with 2+ arguments (iscall), never by class
    if S is not None and name != 'd' and (name in S.CMDS or name in S.ALIAS or
                                          name in S.MACROS):
        return C_FN
    return C_UNK


def iscall(v, c, ode, w, q):                                    #@L 7
    """True if the name v, of class c, opens a call with the '(' at w[q] (DESIGN 7.2, 7.5;
    FlowCE lcall). ode: the line contains desolve, so y, y', y'' and u are call letters."""
    if c == C_FN or c == C_UFN:
        return True
    if c != C_UNK:
        return False
    if v in CALL1 or ode and (v == 'u' or v.rstrip("'") == 'y'):
        return True
    if len(v) > 1 and v[1] != "'":
        return True                     # an uncut unknown name before '(' is a call
    if v == 'd':                        # D9: d(f,x) is diff only with a top-level comma
        d = 0
        for j in range(q, len(w)):
            k = w[j][0]
            if k == K_LP or k == K_LB:
                d += 1
            elif k == K_RP or k == K_RB:
                d -= 1
                if d == 0:
                    return False
            elif k == K_COMMA and d == 1:
                return True
    return False


# -- stage 3: lex ---------------------------------------------------------------------------------

def numval(t, pos, fl):                                         #@L 7
    """The value of the number text t: (p, 1), or a float if fl (a '.' or an exponent)."""
    if not fl:
        return (int(t), 1)
    v = float(t)
    if v - v != 0:                      # inf
        raise K.CasError('number too large', pos)
    return v


def lex(s):                                                     #@L 6
    """Text -> tokens (DESIGN 7.2). Sets F_CALL on the names whose '(' opens a call."""
    toks = []
    n = len(s)
    i = 0
    ode = 0
    while i < n:
        c = s[i]
        j = i + 1
        if c == ' ' or c == '\t':
            i = j
            continue
        if c in DIG or c == '.' and j < n and s[j] in DIG:
            j = i
            while j < n and s[j] in DIG:
                j += 1
            fl = 0
            if j < n and s[j] == '.':
                fl = 1
                j += 1
                while j < n and s[j] in DIG:
                    j += 1
            if j < n and s[j] == 'E':           # D14: only E (the EE key) starts an exponent
                k = j + 1
                if k < n and (s[k] == '+' or s[k] == '-'):
                    k += 1
                if k < n and s[k] in DIG:
                    fl = 1
                    j = k + 1
                    while j < n and s[j] in DIG:
                        j += 1
            toks.append((K_NUM, numval(s[i:j], i, fl), i, j, 0))
        elif c in LET:
            while j < n and s[j] in ALNUM:
                j += 1
            if j == i + 1 and c == 'y':
                while j < n and s[j] == "'":    # y', y''
                    j += 1
            v = s[i:j]
            if 'desolve' in v or v == 'dsolve':
                ode = 1
            toks.append((K_NAME, v, i, j, 0))
        elif c == PI_CH:
            toks.append((K_NAME, 'pi', i, j, 0))
        elif c == TH_CH:
            toks.append((K_NAME, 'theta', i, j, 0))
        elif s[i:i + 2] in OP2:
            j = i + 2
            toks.append((K_OP, s[i:j], i, j, 0))
        elif c in OP1:
            toks.append((K_OP, c, i, j, 0))
        elif c == '(':
            toks.append((K_LP, c, i, j, 0))
        elif c == ')':
            toks.append((K_RP, c, i, j, 0))
        elif c == '[' or c == '{':
            toks.append((K_LB, c, i, j, 0))
        elif c == ']' or c == '}':
            toks.append((K_RB, c, i, j, 0))
        elif c == ',':
            toks.append((K_COMMA, c, i, j, 0))
        elif c == '!' or c == "'":
            toks.append((K_POST, c, i, j, 0))
        else:
            raise K.CasError('invalid character', i)
        i = j
    for k in range(len(toks) - 1):
        t = toks[k]
        if t[0] == K_NAME and toks[k + 1][0] == K_LP and \
                iscall(t[1], classify(t[1]), ode, toks, k + 1):
            toks[k] = (K_NAME, t[1], t[2], t[3], F_CALL)
    return toks


# -- stage 4: ti_rewrite --------------------------------------------------------------------------

def fnpre(v, k):                                                #@L 7
    """Length of the first FNT name that v[k:] starts with; 0 if none (FlowCE im_fnprefix)."""
    for f in FNT:
        if v[k:k + len(f)] == f:
            return len(f)
    return 0


def fnin(v):                                                    #@L 7
    """Where a function name starts after letters inside the name v (xsinx: 1); len(v) if
    nowhere (FlowCE im_fnin)."""
    n = len(v)
    k = 1
    while k < n and v[k - 1] in LET:
        for f in FNT:
            if v[k:k + len(f)] == f:
                return k
        k += 1
    return n


def mclose(w, k):                                               #@L 7
    """Index of the ')' that closes the '(' at w[k]; len(w) if it is not closed."""
    d = 0
    n = len(w)
    while k < n:
        if w[k][0] == K_LP:
            d += 1
        elif w[k][0] == K_RP:
            d -= 1
            if d == 0:
                return k
        k += 1
    return n


def cutname(u, c):                                              #@L 7
    """The name token u cut after c characters: (left piece, right piece)."""
    v = u[1]
    return ((K_NAME, v[:c], u[2], u[2] + c, 0), (K_NAME, v[c:], u[2] + c, u[3], u[4]))


def scan(w, k, cm, run):                                        #@L 7
    """FlowCE powend (run=0: the exponent that starts at w[k], right after a '^') and runend
    (run=1: the bare argument of sin x that starts at w[k]). cm maps a name to (class, prefix,
    fnin). Returns (j, c): the end is before w[j], or inside the name w[j] after c characters."""
    n = len(w)
    j = k
    pw = not run                        # an exponent comes next
    while j < n:
        t = w[j]
        if (j > k or pw) and t[2] != w[j - 1][3]:
            break                       # a blank ends it
        if pw:
            pw = False
            if t[0] == K_LP:
                d = 0
                while j < n:
                    if w[j][0] == K_LP:
                        d += 1
                    elif w[j][0] == K_RP:
                        d -= 1
                        if d == 0:
                            break
                    j += 1
                j = j + 1 if j < n else n
            elif t[0] == K_NUM:
                j += 1
            elif t[0] == K_NAME:
                x = cm[t[1]]
                if x[0] != C_UNK and x[0] != C_VAL:
                    pw = True           # sin^sin(x): a function is no exponent (FlowCE
                    break               # takes it, and a second pass then differs)
                if x[0] == C_UNK and x[2] < len(t[1]):
                    return (j, x[2])    # x^xsinx: the function is not the exponent's
                j += 1
            else:
                pw = True
                break
            if not run:
                return (j, 0)
            continue
        if t[0] == K_NUM:
            j += 1
        elif t[0] == K_NAME:
            x = cm[t[1]]
            if x[0] == C_KEY or x[0] == C_FN or x[0] == C_UFN or x[1]:
                break                   # the next function: sin x cos x
            if x[0] == C_UNK and x[2] < len(t[1]):
                return (j, x[2])        # ... or one inside the name: sin xcosx
            j += 1
        elif t[0] == K_OP and t[1] == '^' and j > k:
            pw = True
            j += 1
        else:
            break
    if pw and run:
        j -= 1                          # a '^' with no exponent is not part of the run
    return (j, 0)


def ti_rewrite(toks):                                           #@L 6
    """Stage 4: paper notation (DESIGN 7.4; FlowCE ti_rewrite, cat 5.5) on a token list.
    f(x)=... -> f(x):=..., xsinx -> x*sin(x), sin2x -> sin(2x), sin^2x -> sin(x)^2,
    sin^-1(x) -> asin(x), sin x+1 -> sin(x)+1. FlowCE's recursion on the argument of sin^2(...)
    is a splice: the argument goes back on the work list, ahead of the rest of the line."""
    cm = {}                             # name -> (class, FNT prefix, fnin)
    for t in toks:
        if t[0] == K_NAME and t[1] not in cm:
            cm[t[1]] = (classify(t[1]), fnpre(t[1], 0), fnin(t[1]))
    w = list(toks)
    out = []
    n = len(w)
    deq = None                          # rule 0: the '=' of f(x)=... becomes ':='
    p = 0
    if n > 1 and w[0][0] == K_NAME and w[1][0] == K_LP and w[1][2] == w[0][3] and \
            cm[w[0][1]][0] != C_FN and cm[w[0][1]][0] != C_KEY:
        j = 2
        while j < n and w[j][0] == K_NAME:
            j += 1
            if j < n and w[j][0] == K_COMMA:
                j += 1
                continue
            if j + 2 < n and w[j][0] == K_RP and w[j + 1][0] == K_OP:
                o = w[j + 1]
                if o[1] == '=' and not (w[j + 2][0] == K_OP and w[j + 2][1] == '=' and
                                        w[j + 2][2] == o[3]):
                    deq = o
                if deq is not None or o[1] == ':=':     # f(x):=... too, so that a second
                    t = w[0]                            # pass changes nothing
                    out.append((K_NAME, t[1], t[2], t[3], F_CALL))   # never rewritten
                    p = 1
            break
    while p < len(w):
        t = w[p]
        if t is deq:
            out.append((K_OP, ':=', t[2], t[3], 0))
            p += 1
            continue
        if t[0] != K_NAME:
            out.append(t)
            p += 1
            continue
        v = t[1]
        L = len(v)
        c, f, fi = cm[v]
        if c != C_FN and c != C_UNK:
            f = 0
        n = len(w)
        nx = None                       # the next token, when no blank comes first
        if p + 1 < n and w[p + 1][2] == t[3]:
            nx = w[p + 1]
        seg = None                      # tokens that go back on the work list ...
        q = p + 1                       # ... in place of w[p:q]
        rest = None
        if f == 0:
            # rule 1: letters times a function in one name (xsinx, 2xlnx)
            if c == C_UNK and fi < L and not (nx and nx[0] == K_OP and nx[1] == ':='):
                a, b = cutname(t, fi)
                out.append(a)
                out.append((K_OP, '*', a[3], a[3], F_IMPL))
                seg = [b]
        elif c == C_UNK:
            # rule 2: a function glued to its argument (sinx, sin2x, ln2, sinx^2)
            if not (nx and nx[0] == K_LP):
                k = f
                while k < L and not (v[k] in LET and fnpre(v, k)):
                    k += 1
                if k > f:
                    s0 = t[2]
                    seg = []
                    a = f
                    while a < k:                # the letters and digits after the name
                        b = a + 1
                        if v[a] in DIG:
                            while b < k and v[b] in DIG:
                                b += 1
                            fl = 0
                            if b + 1 < k and v[b] == 'E' and v[b + 1] in DIG:
                                fl = 1
                                b += 2
                                while b < k and v[b] in DIG:
                                    b += 1
                            seg.append((K_NUM, numval(v[a:b], s0 + a, fl), s0 + a, s0 + b, 0))
                        else:
                            while b < k and v[b] in ALNUM:
                                b += 1
                            seg.append((K_NAME, v[a:b], s0 + a, s0 + b, 0))
                        a = b
                    if k < L:
                        rest = (K_NAME, v[k:], s0 + k, t[3], t[4])
                    elif nx and nx[0] == K_OP and nx[1] == '^':
                        e, ec = scan(w, p + 2, cm, 0)
                        if e > p + 2 or ec:
                            for u in w[p + 1:e]:
                                seg.append(u)
                            q = e
                            if ec:
                                a, rest = cutname(w[e], ec)
                                seg.append(a)
                                q = e + 1
                    out.append((K_NAME, v[:f], s0, s0 + f, F_CALL))
                    out.append((K_LP, '(', s0 + f, s0 + f, 0))
                    z = seg[-1][3]
                    seg.append((K_RP, ')', z, z, 0))
        elif f == L:
            if nx and nx[0] == K_OP and nx[1] == '^':
                # rule 3: sin^2(x), sin^2x, sin^-1(x)
                a = p + 2
                inv = 0
                if a + 1 < n:
                    m = w[a]
                    o = w[a + 1]
                    inv = m[0] == K_OP and m[1] == '-' and m[2] == nx[3] and \
                        o[0] == K_NUM and o[1] == (1, 1) and o[2] == m[3] and o[3] == o[2] + 1
                if inv:
                    e = a + 2
                    ec = 0
                    nm = INV.get(v)
                else:
                    e, ec = scan(w, a, cm, 0)
                    nm = v
                if nm is not None and not ec and e > a:
                    zo = None
                    if e < n and w[e][0] == K_LP:
                        m = mclose(w, e)
                        seg = w[e + 1:m]
                        st = w[e][3]
                        if m < n:
                            zo = w[m]
                        q = m + 1
                    else:
                        r, rc = scan(w, e, cm, 1)
                        if r > e or rc:
                            seg = w[e:r]
                            q = r
                            if rc:
                                a, rest = cutname(w[r], rc)
                                seg.append(a)
                                q = r + 1
                            st = seg[0][2]
                    if seg is not None:
                        out.append((K_NAME, nm, t[2], t[3], F_CALL))
                        out.append((K_LP, '(', t[3], st, 0))
                        z = seg[-1][3] if seg else st
                        if zo is not None:
                            z = zo[2]
                        seg.append((K_RP, ')', z, zo[3] if zo is not None else z, 0))
                        if not inv:
                            for u in w[p + 1:e]:
                                seg.append(u)       # the power goes after the argument
            elif not (nx and nx[0] == K_LP):
                # rule 4: sin x, sin 2x, sin x^2, sin x+1
                r, rc = scan(w, p + 1, cm, 1)
                if r > p + 1 or rc:
                    seg = w[p + 1:r]
                    q = r
                    if rc:
                        a, rest = cutname(w[r], rc)
                        seg.append(a)
                        q = r + 1
                    out.append((K_NAME, v, t[2], t[3], F_CALL))
                    out.append((K_LP, '(', t[3], seg[0][2], 0))
                    z = seg[-1][3]
                    seg.append((K_RP, ')', z, z, 0))
        if seg is None:
            out.append(t)
            p += 1
            continue
        if rest is not None:
            seg.append(rest)
        for u in seg:
            if u[0] == K_NAME and u[1] not in cm:
                cm[u[1]] = (classify(u[1]), fnpre(u[1], 0), fnin(u[1]))
        w = seg + w[q:]
        p = 0
    n = len(out)
    for k in range(n):                  # a name keeps F_CALL only before a '('
        t = out[k]
        if t[0] == K_NAME and t[4] & F_CALL and (k + 1 == n or out[k + 1][0] != K_LP):
            out[k] = (K_NAME, t[1], t[2], t[3], t[4] & ~F_CALL)
    return out


# -- stage 5: ti_implicit -------------------------------------------------------------------------

def ti_implicit(toks, cut=1):                                   #@L 6
    """Stage 5: cut unknown names and insert implicit '*' (DESIGN 7.5; FlowCE
    ti_implicit_mult with im_cut, cat 5.6). Only '*' tokens (F_IMPL) are inserted, besides the
    pieces of cut names, so the pass is idempotent. Sets or clears F_CALL on every name.
    cut=0 keeps unknown names whole (FlowCE split_unknown = false)."""
    w = toks
    n = len(w)
    ode = 0
    asgn = 0
    for t in w:
        if t[0] == K_NAME and ('desolve' in t[1] or t[1] == 'dsolve'):
            ode = 1
        elif t[0] == K_OP and t[1] == ':=':
            asgn = 1
    out = []
    lk = 0                              # previous token: 0 none, 1 number, 2 name, 3 =>, 4 other
    lend = False                        # it ends a value
    lcall = False                       # it is a name, and a '(' after it opens a call
    i = -1
    while i + 1 < n:
        i += 1
        t = w[i]
        k = t[0]
        if k == K_NUM:
            if lend and lk != 1:
                e = out[-1][3]
                out.append((K_OP, '*', e, e, F_IMPL))
            out.append(t)
            lk = 1
            lend = True
            lcall = False
            continue
        if k != K_NAME:
            if k == K_LP and lend and not lcall:
                e = out[-1][3]
                out.append((K_OP, '*', e, e, F_IMPL))
            out.append(t)
            lend = k == K_RP or k == K_RB and t[1] == ']' or \
                k == K_POST and t[1] == '!' and lend
            lk = 3 if k == K_OP and t[1] == '=>' else 4
            lcall = False
            continue
        v = t[1]
        c = classify(v)
        if lend and c != C_KEY:
            e = out[-1][3]
            out.append((K_OP, '*', e, e, F_IMPL))
        q = i + 1
        paren = q < n and w[q][0] == K_LP
        dfn = False                     # a definition f(x):=...
        if paren and asgn:
            m = mclose(w, q)
            dfn = m + 1 < n and w[m + 1][0] == K_OP and w[m + 1][1] == ':='
        asg = q < n and w[q][0] == K_OP and w[q][1] == ':='
        L = len(v)
        x = v                           # the last piece and its class
        xc = c
        ok = 0
        # a name that starts with a function name (lncos, expi) is not cut: stage 4 left it
        # whole on purpose, and pieces would make a second stage 4 read ln lncos(x) differently
        if cut and c == C_UNK and not dfn and not asg and lk != 3 and 2 <= L <= MAXCUT and \
                v not in GREEK and not fnpre(v, 0):
            ok = 1
            for ch in v:
                if ch not in LET:
                    ok = 0
                    break
        if ok:
            # im_cut: the fewest pieces; a piece is a letter, a VALUE name, or (last, before
            # '(') a FUNCTION or USERFN name; ties go to the longest first piece
            cnt = [0] * (L + 1)
            nxt = [0] * (L + 1)
            a = L - 1
            while a >= 0:
                best = 255
                bn = a + 1
                b = L if a else L - 1   # the whole name is never a piece
                while b > a:
                    if cnt[b] + 1 < best:
                        good = b == a + 1
                        if not good:
                            sub = v[a:b]
                            if sub != 'oo' and sub != 'inf':
                                tc = classify(sub)
                                good = tc == C_VAL or paren and b == L and \
                                    (tc == C_FN or tc == C_UFN)
                        if good:
                            best = cnt[b] + 1
                            bn = b
                    b -= 1
                cnt[a] = best
                nxt[a] = bn
                a -= 1
            if cnt[0] > 3 or cnt[0] == L and paren and L > 2:
                ok = 0
        if ok:
            s0 = t[2]
            a = 0
            while True:
                b = nxt[a]
                if b >= L:
                    break
                out.append((K_NAME, v[a:b], s0 + a, s0 + b, 0))
                out.append((K_OP, '*', s0 + b, s0 + b, F_IMPL))
                a = b
            x = v[a:]
            s0 += a
            e0 = t[3]
            while x[0] == 'y' and q < n and w[q][0] == K_POST and w[q][1] == "'" and \
                    w[q][2] == e0:
                x += "'"                # xy' is x*y', as lex reads y' (DESIGN 7.2)
                e0 = w[q][3]
                q += 1
                i += 1
            paren = q < n and w[q][0] == K_LP
            xc = classify(x)
        else:
            s0 = t[2]
            e0 = t[3]
        lk = 2
        lend = xc == C_VAL or xc == C_UNK
        lcall = dfn or iscall(x, xc, ode, w, q)
        out.append((K_NAME, x, s0, e0, F_CALL if lcall and paren else 0))
    return out


# -- stage 7: rpn ---------------------------------------------------------------------------------

def rpn(toks):                                                  #@L 7
    """Tokens -> an RPN list (DESIGN 7.7). Items: ('n', value, ti) number, ('s', name, ti),
    ('o', op, ti) operator ('neg' for prefix minus), ('F', name, nargs, ti) call,
    ('L', n, ti) list (ti -1: a bare top-level list), ('P', ti) parenthesized group."""
    out = []
    ops = []
    argc = []
    top = 1                             # items of a bare top-level list
    val = False
    n = len(toks)
    for i in range(n):
        tk = toks[i]
        k = tk[0]
        if k == K_NUM or k == K_NAME:
            if val:
                raise K.CasError('missing operator', tk[2])
            if k == K_NAME and tk[4] & F_CALL:
                if i + 1 == n or toks[i + 1][0] != K_LP:
                    raise K.CasError('missing (', tk[3])
                ops.append(('f', tk[1], i))
                continue
            out.append(('n' if k == K_NUM else 's', tk[1], i))
            val = True
        elif k == K_LP or k == K_LB:
            if val:
                raise K.CasError('missing operator', tk[2])
            if len(argc) >= MAXNEST:
                raise K.CasError('too deeply nested', tk[2])
            ops.append(('(', tk[1], i))
            argc.append(1)
        elif k == K_COMMA or k == K_RP or k == K_RB:
            while ops and ops[-1][0] == 'o':
                out.append(ops.pop())
            if k == K_COMMA and not ops:        # a top-level comma: the line is a list
                if not val:
                    raise K.CasError('empty argument', tk[2])
                top += 1
                val = False
                continue
            if not ops or ops[-1][0] != '(':
                raise K.CasError('unbalanced', tk[2])
            if k == K_COMMA:
                if not val:
                    raise K.CasError('empty argument', tk[2])
                argc[-1] += 1
                val = False
                continue
            o = ops.pop()
            m = argc.pop()
            if PAIR[o[1]] != tk[1]:
                raise K.CasError('mismatched bracket', tk[2])
            if not val:                         # () [] f(), but not (a+) or f(a,)
                if o[2] != i - 1:
                    raise K.CasError('empty argument' if m > 1 else 'missing operand', tk[2])
                m = 0
            if o[1] != '(':
                out.append(('L', m, i))
            elif ops and ops[-1][0] == 'f':
                out.append(('F', ops.pop()[1], m, i))
            elif m == 1:
                out.append(('P', i))
            elif m > 1:
                out.append(('L', m, i))
            else:
                raise K.CasError('empty ()', tk[2])
            val = True
        elif k == K_POST:
            if not val:
                raise K.CasError('missing operand', tk[2])
            out.append(('o', tk[1], i))
        else:
            o = tk[1]
            if not val:
                if o == '-':
                    ops.append(('o', 'neg', i))
                elif o != '+':
                    raise K.CasError('missing operand', tk[2])
                continue
            p = PREC[o]
            while ops and ops[-1][0] == 'o':
                q = PREC[ops[-1][1]]
                if q > p or q == p and o != '^' and o != '=>' and o != ':=':
                    out.append(ops.pop())
                else:
                    break
            ops.append(('o', o, i))
            val = False
    e = toks[-1][3] if toks else 0
    while ops:
        o = ops.pop()
        if o[0] != 'o':
            raise K.CasError('missing )', e)
        out.append(o)
    if not val and toks:
        raise K.CasError('missing operand', e)
    if top > 1:
        out.append(('L', top, -1))      # bare top-level list (solutions)
    return out


# -- tokens -> text -------------------------------------------------------------------------------

def untok(toks, s=None):                                        #@L 7
    """Tokens -> text: the golden tests, and the body text of a definition (DESIGN 7.1, 7.9).
    With the source s, numbers keep their typed form and blanks are kept, so that
    untok(lex(s), s) == s when s has no pi or theta glyph."""
    if s is not None and not toks and not s.strip(' \t'):
        return s                        # a blank line
    out = []
    pe = 0                              # the largest end offset so far
    pt = ''                             # the previous token's text
    pk = -1
    run = 0                             # tokens written since the last blank
    p2 = None                           # (kind, text) of the token before the previous one
    p3 = None                           # ... and of the one before that
    if s is not None and toks and not s[:toks[0][2]].strip(' \t'):
        out.append(s[:toks[0][2]])
    for t in toks:
        k = t[0]
        v = t[1]
        if k != K_NUM:
            x = v
        elif s is not None and t[2] < t[3]:
            x = s[t[2]:t[3]]
        elif type(v) is tuple:
            x = '%d' % v[0] if v[1] == 1 else '%d/%d' % v
        else:
            x = repr(v).replace('e', 'E')       #@float-ok  (no source: tests only)
        if pt:
            g = ''
            if s is not None and pe < t[2]:
                g = s[pe:t[2]]
                if g.strip(' \t'):
                    g = ''              # not blanks: tokens were moved or dropped there
            if g:
                out.append(g)
                run = 0
            elif k == K_NAME and (pk == K_NAME and pt[-1] != "'" or pk == K_NUM and
                                  x[0] == 'E' and len(x) > 1 and x[1] in DIG and
                                  'E' not in pt) or \
                    k == K_NUM and x[0] in DIG and (pk == K_NUM or pk == K_NAME and
                                                    pt[-1] != "'") or \
                    k == K_NUM and pk == K_NUM and '.' not in pt and 'E' not in pt or \
                    len(pt) == 1 and pt + x[0] in OP2 or \
                    x == "'" and pk == K_NAME and pt.rstrip("'") == 'y' or \
                    k == K_NUM and x[0] in DIG and run >= 3 and pk == K_OP and \
                    (pt == '+' or pt == '-') and p2 == (K_NAME, 'E') and \
                    p3[0] == K_NUM and 'E' not in p3[1]:
                out.append(' ')         # these would lex as one token (the last: 2E-3)
                run = 0
        out.append(x)
        run += 1
        p3 = p2
        p2 = (pk, pt)
        pt = x
        pk = k
        if t[3] > pe:
            pe = t[3]
    if s is not None and toks and not s[pe:].strip(' \t'):
        out.append(s[pe:])
    return ''.join(out)


# -- stages 3-6 and stage 6: expand_names (T1.5) ---------------------------------------------------

def tokens(text, ctxt=1):                                       #@L 3
    """Stages 3-6 (DESIGN 7.1): lex, ti_rewrite, ti_implicit, then expand_names unless ctxt is
    0 (the answer path: F4 and the round trip re-parse answer text without the session)."""
    t = ti_implicit(ti_rewrite(lex(text)))
    if ctxt:
        t = expand_names(t)
    return t


def expand_names(toks):                                         #@L 5
    """Stage 6 (DESIGN 7.6), one loop over a work list:
    1. sum( and riemann( whose second argument is the bare letter i: every name i in the call
       becomes the first of k, j, m that the call does not use and that is not stored;
    2. a stored variable (SESS.VARS) becomes ( lex(text) );
    3. a user function call f(a1, ...) (SESS.FUNCS[f] = (params, body text)) becomes
       ( body ), with each parameter name replaced by (ai);
    4. a macro call (SESS.MACROS[m] = (min, max, template with #1 .. #9)) likewise; a template
       None takes AMAC[m][count - min].
    A splice goes back on the work list, so names inside it expand too. At most MAXEXP
    expansions and MAXDEF nested ones (M_DEEP). Never expanded: the name after '=>', a name
    before ':=', and the arguments of purge(...). Spliced tokens take the offsets of the name
    they replace."""
    S = SESS
    VS = NOSES if S is None else S.VARS
    FS = NOSES if S is None else S.FUNCS
    MS = NOSES if S is None else S.MACROS
    w = list(toks)
    out = []
    ends = []                           # per open expansion: the tokens left after it
    cnt = 0
    p = 0
    while p < len(w):
        while ends and len(w) - p <= ends[-1]:
            ends.pop()
        t = w[p]
        q = p + 1
        if t[0] != K_NAME:
            out.append(t)
            p = q
            continue
        v = t[1]
        seg = None
        if t[4] & F_CALL and (v == 'purge' or v == 'sum' or v == 'riemann' or v in FS or
                              v in MS):
            m = mclose(w, q)
            if v == 'purge':            # names to forget, never their values
                while p <= m and p < len(w):
                    out.append(w[p])
                    p += 1
                continue
            args = []                   # the argument token lists (top-level commas)
            cur = []
            d = 0
            for j in range(q + 1, m):
                u = w[j]
                k = u[0]
                if k == K_LP or k == K_LB:
                    d += 1
                elif k == K_RP or k == K_RB:
                    d -= 1
                if k == K_COMMA and d == 0:
                    args.append(cur)
                    cur = []
                else:
                    cur.append(u)
            if m > q + 1:
                args.append(cur)
            n = len(args)
            if v == 'sum' or v == 'riemann':
                a = args[1] if n > 1 else ()
                if a and a[0][0] == K_NAME and a[0][1] == 'i' and (
                        len(a) == 1 or a[1][0] == K_OP and a[1][1] == '='):
                    used = set()
                    for j in range(q + 1, m):
                        if w[j][0] == K_NAME:
                            used.add(w[j][1])
                    nm = None
                    for c in ('k', 'j', 'm'):
                        if nm is None and c not in used and c not in VS:
                            nm = c
                    for j in range(q + 1, m):
                        u = w[j]
                        if nm is not None and u[0] == K_NAME and u[1] == 'i' and \
                                not u[4] & F_CALL:
                            w[j] = (K_NAME, nm, u[2], u[3], u[4])
            elif v in FS:
                ps, body = FS[v]
                if n != len(ps):
                    raise K.CasError(M_ARGS)
                seg = []
                for u in lex(body):
                    j = -1
                    if u[0] == K_NAME and not u[4] & F_CALL:
                        for c in range(n):
                            if ps[c] == u[1]:
                                j = c
                    if j < 0:
                        seg.append((u[0], u[1], t[2], t[3], u[4]))
                    else:
                        seg.append((K_LP, '(', t[2], t[3], 0))
                        for x in args[j]:
                            seg.append(x)
                        seg.append((K_RP, ')', t[2], t[3], 0))
                q = m + 1
            elif v in MS:
                lo, hi, tx = MS[v]
                if n < lo or n > hi:
                    raise K.CasError(M_ARGS)
                if tx is None:
                    tx = AMAC[v]
                    if n - lo >= len(tx):
                        raise K.CasError(M_ARGS)
                    tx = tx[n - lo]
                pcs = tx.split('#')
                seg = []
                for c in range(len(pcs)):
                    s = pcs[c]
                    if c:
                        seg.append((K_LP, '(', t[2], t[3], 0))
                        for x in args[ord(s[0]) - 49]:
                            seg.append(x)
                        seg.append((K_RP, ')', t[2], t[3], 0))
                        s = s[1:]
                    for u in lex(s):
                        seg.append((u[0], u[1], t[2], t[3], u[4]))
                q = m + 1
        elif v in VS and not t[4] & F_CALL and not (out and out[-1][0] == K_OP and
                                                     out[-1][1] == '=>') and \
                not (q < len(w) and w[q][0] == K_OP and w[q][1] == ':='):
            seg = []
            for u in lex(VS[v]):
                seg.append((u[0], u[1], t[2], t[3], u[4]))
        if seg is None:
            out.append(t)
            p += 1
            continue
        cnt += 1
        if cnt > MAXEXP or len(ends) >= MAXDEF:
            raise K.CasError(M_DEEP)
        ends.append(len(w) - q)
        seg.insert(0, (K_LP, '(', t[2], t[3], 0))
        seg.append((K_RP, ')', t[2], t[3], 0))
        for u in w[q:]:
            seg.append(u)
        w = seg
        p = 0
    return out


# -- builders (T1.5, DESIGN 7.8) ------------------------------------------------------------------

def exact(v):                                                   #@L 5
    """The rational of the float v's 15-significant-digit decimal (DESIGN 6.3): 0.25 -> 1/4,
    0.1 -> 1/10, 2.5E-3 -> 1/400. Integers only (frexp is exact), so every platform agrees."""
    if v == 0.0:
        return K.ZERO
    m, ex = math.frexp(v)
    p = int(m * 9007199254740992.0)     # v = p * 2^(ex - 53) exactly
    ex -= 53
    q = 1
    if ex >= 0:
        p *= 2 ** ex
    else:
        q = 2 ** (-ex)
    s = 1
    if p < 0:
        s = -1
        p = -p
    e = len(str(p)) - len(str(q))       # 10^e <= p/q < 10^(e+1), or e is one too big
    if e >= 0:
        if p < q * 10 ** e:
            e -= 1
    elif p * 10 ** (-e) < q:
        e -= 1
    k = 14 - e                          # p/q ~ m / 10^k with 15 digits in m
    if k >= 0:
        d = q
        m, r = divmod(p * 10 ** k, q)
    else:
        d = q * 10 ** (-k)
        m, r = divmod(p, d)
    if 2 * r >= d:                      # half-up
        m += 1
    if k >= 0:
        return K.num(s * m, 0, 10 ** k)
    return K.num(s * m * 10 ** (-k))


def tcode(s):                                                   #@L 5
    """A template or rule string -> RPN (DESIGN 7.8, 9.4): lex and rpn only, so rule strings
    write every '*'. Keep only the most recent template: rule patterns already
    have compiled nodes, so their RPN must not accumulate in the small heap."""
    c = K.TCACHE.get(s)
    if c is None:
        K.TCACHE.clear()
        c = rpn(lex(s))
        K.TCACHE[s] = c
    return c


def inst(code, env):                                            #@L 4
    """Builds tcode RPN with the constructors (DESIGN 7.8, 9.6). env None: pattern mode, and
    each rule letter of WSLOT becomes the leaf (WILD, slot, constraint); x is the slot XSLOT,
    which the matcher binds first. env a slot list (NSLOT ids): template mode, and a letter is
    its bound id (0: CasError). Lowercase names are literal: constants or symbols. Functions:
    ONEARG, sqrt, exp, log; any other call is CALL(SYM(name), args). No angle mode, no
    commands, no floats."""
    st = []
    for it in code:
        k = it[0]
        if k == 'n':
            v = it[1]
            x = K.num(v[0], 0, v[1])
        elif k == 's':
            v = it[1]
            w = WSLOT.get(v)
            if w is None:
                x = CONSTS.get(v)
                if x is None:
                    x = K.sym(v)
            elif env is None:
                x = K.mk((K.WILD, w[0], w[1]))
            else:
                x = env[w[0]]
                if not x:
                    raise K.CasError('rule letter %s is unbound' % v)
        elif k == 'o':
            o = it[1]
            b = st.pop()
            if o == 'neg':
                x = K.add_([b], K.MONE)
            elif o == '!':
                x = K.fn_(K.FACT, b)
            else:
                a = st.pop()
                if o == '+':
                    x = K.add_([a, b])
                elif o == '-':
                    x = K.add_([a, K.add_([b], K.MONE)])
                elif o == '*':
                    x = K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])
                elif o == '/':
                    x = K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])
                elif o == '^':
                    x = K.mul_(K.ONE, [(a, b)])
                else:
                    x = K.rel_(RELOPS[o], a, b)
        elif k == 'F':
            n = it[2]
            a = st[len(st) - n:]
            del st[len(st) - n:]
            f = it[1] if n == 1 else ''
            op = ONEARG.get(f)
            if op is not None:
                x = K.fn_(op, a[0])
            elif f == 'sqrt':
                x = K.mul_(K.ONE, [(a[0], K.HALF)])
            elif f == 'exp':
                x = K.mul_(K.ONE, [(K.E, a[0])])
            elif f == 'log':
                x = K.mul_(K.ONE, [(K.fn_(K.LN, a[0]), K.ONE), (K.LN10, K.MONE)])
            else:
                x = K.mk((K.CALL, K.sym(it[1])) + tuple(a))
        elif k == 'L':
            n = it[1]
            x = K.mk((K.LST,) + tuple(st[len(st) - n:]))
            del st[len(st) - n:]
        else:
            continue                    # 'P': a group
        st.append(x)
    return st[-1]


def fnb(f, a, deg):                                             #@L 4
    """The node of the function call f(a[0], ...) for g_eval (DESIGN 7.8), or 0 if f is not a
    builder function. log(u) = ln(u)/ln(10), log(u,b) = ln(u)/ln(b), exp(u) = e^u,
    sqrt(u) = u^(1/2), surd(u,n) = u^(1/n), O(u) = BIGO(u), asec(u) = acos(1/u) (acsc, acot
    likewise), asinh/acosh/atanh by their logarithms. deg (6.5): a trig argument u becomes
    u*pi/180, term by term over a sum, and an inverse-trig result is multiplied by 180/pi."""
    op = ONEARG.get(f)
    g = INVAUX.get(f)
    if op is None and g is None and f not in FARGS:
        return 0
    r = FARGS.get(f, (1, 1))
    if len(a) < r[0] or len(a) > r[1]:
        raise K.CasError(M_ARGS)
    u = a[0]
    if g is not None:
        op = g
        u = K.mul_(K.ONE, [(u, K.MONE)])
    if op is not None:
        if deg and K.SIN <= op <= K.COT:
            t = K.N[u]
            if t[0] == K.ADD:
                lst = [K.mul_(K.nmul(K.N[t[1]], D180), [(K.PI, K.ONE)])]
                for j in range(2, len(t), 2):
                    lst.append(K.mul_(K.nmul(K.N[t[j + 1]], D180),
                                      [(t[j], K.ONE), (K.PI, K.ONE)]))
                u = K.add_(lst)
            else:
                u = K.mul_(D180, [(u, K.ONE), (K.PI, K.ONE)])
        r = K.fn_(op, u)
        if deg and K.ASIN <= op <= K.ATAN:
            r = K.mul_(R180, [(r, K.ONE), (K.PI, K.MONE)])
        return r
    if f == 'sqrt':
        return K.mul_(K.ONE, [(u, K.HALF)])
    if f == 'exp':
        return K.mul_(K.ONE, [(K.E, u)])
    if f == 'log' or f == 'log10':
        b = K.LN10 if len(a) == 1 else K.fn_(K.LN, a[1])
        return K.mul_(K.ONE, [(K.fn_(K.LN, u), K.ONE), (b, K.MONE)])
    if f == 'surd':
        return K.mul_(K.ONE, [(u, K.mul_(K.ONE, [(a[1], K.MONE)]))])
    if f == 'O':
        K.chk(u)
        return K.mk((K.BIGO, u))
    if f == 'atanh':                    # ln((1+u)/(1-u))/2
        r = K.mul_(K.ONE, [(K.add_([K.ONE, u]), K.ONE), (K.add_([K.ONE, K.neg_(u)]), K.MONE)])
        return K.mul_(K.HALF, [(K.fn_(K.LN, r), K.ONE)])
    r = K.add_([K.mul_(K.ONE, [(u, K.TWO)]), K.ONE if f == 'asinh' else K.MONE])
    return K.fn_(K.LN, K.add_([u, K.mul_(K.ONE, [(r, K.HALF)])]))   # ln(u+sqrt(u^2+-1))


def issent(x):                                                  #@L 7
    """True for a result sentinel (DESIGN 10.5): TRUE, FALSE, DNE, DIVG, HOLD."""
    return x == K.TRUE or x == K.FALSE or K.DNE <= K.N[x][0] <= K.HOLD


def approx(e):                                                  #@L 3
    """giac evalf (DESIGN 6.3): every constant subexpression of e (numbers, pi, e, and sums,
    products and functions of them) becomes a FLT, through A.nprog/A.nrun. Exact stay: the
    real rational exponent of a non-constant base (x^2), a NUM or e base under a non-constant
    exponent (2^x, e^x), the coefficients 1 and -1, a zero constant term, the sentinels, and a
    constant that does not evaluate (Undefined, overflow). So 1/2+x -> 0.5+x, sqrt(2)*x ->
    1.41421356237*x, x^2/3 -> 0.333333333333*x^2, 1/3 -> 0.333333333333."""
    ev = {}                             # id -> a constant that nrun can evaluate
    nw = {}                             # id -> its image, for the other ids
    fv = {}                             # constant id -> its FLT (or itself)
    for n in A.postorder(e):
        t = K.N[n]
        op = t[0]
        if op < K.COMP:
            c = op <= K.FLT or n == K.PI or n == K.E
            nw[n] = n
        else:
            c = op == K.ADD or op == K.MUL or K.FN0 <= op <= K.FACT
            j = 1
            while c and j < len(t):
                c = ev[t[j]]
                j += 1
        ev[n] = c
        if n != e and (c or op < K.COMP):
            continue                    # a leaf, or a constant that its parent converts
        if op < K.COMP and not c:
            break
        todo = []
        cn = K.ONE
        if c:
            todo.append(n)
        elif op == K.MUL:
            cp = []
            for j in range(2, len(t), 2):
                b = t[j]
                x = t[j + 1]
                if ev[b] and ev[x]:
                    cp.append((b, x))
                    continue
                if ev[x] and not (K.N[x][0] == K.NUM and not K.N[x][2]):
                    todo.append(x)
                if ev[b] and not ev[x] and K.N[b][0] != K.NUM and b != K.E:
                    todo.append(b)
            cn = K.mul_(t[1], cp) if cp else t[1]
            if cn != K.ONE and cn != K.MONE:
                todo.append(cn)
        elif op == K.ADD:
            if t[1] != K.ZERO:
                todo.append(t[1])
            for j in range(2, len(t), 2):
                if ev[t[j]]:
                    todo.append(t[j])
                if t[j + 1] != K.ONE and t[j + 1] != K.MONE:
                    todo.append(t[j + 1])
        elif op < K.DNE or op > K.HOLD:
            for j in range(1, len(t)):
                if ev[t[j]]:
                    todo.append(t[j])
        for x in todo:
            if x not in fv:
                y = x
                if K.N[x][0] != K.FLT:
                    try:
                        v = A.nrun(A.nprog(x, ()), ())
                        if type(v) is complex:
                            y = K.flt(v.real, v.imag)
                        else:
                            y = K.flt(v)
                    except (ArithmeticError, ValueError, K.CasSoft, K.CasError):
                        y = x
                fv[x] = y
        if c:
            break
        if op == K.ADD:
            lst = [K.ZERO if t[1] == K.ZERO else fv[t[1]]]
            for j in range(2, len(t), 2):
                k = t[j + 1]
                b = fv[t[j]] if ev[t[j]] else nw[t[j]]
                lst.append(K.mul_(k if k == K.ONE or k == K.MONE else fv[k], [(b, K.ONE)]))
            r = K.add_(lst)
        elif op == K.MUL:
            pr = []
            for j in range(2, len(t), 2):
                b = t[j]
                x = t[j + 1]
                if ev[b] and ev[x]:
                    continue
                if not ev[b]:
                    b = nw[b]
                elif K.N[b][0] != K.NUM and b != K.E:
                    b = fv[b]                   # (a constant base: x is not constant)
                if not ev[x]:
                    x = nw[x]
                elif not (K.N[x][0] == K.NUM and not K.N[x][2]):
                    x = fv[x]
                pr.append((b, x))
            cn = fv[cn] if cn in fv else cn
            if K.N[cn][0] > K.FLT:              # a constant that stayed exact (2^100000)
                pr.append((cn, K.ONE))
                cn = K.ONE
            r = K.mul_(cn, pr)
        elif K.FN0 <= op:
            r = K.fn_(op, nw[t[1]])
        elif K.DNE <= op <= K.HOLD:
            r = n
        else:
            u = [op]
            for j in range(1, len(t)):
                u.append(fv[t[j]] if ev[t[j]] else nw[t[j]])
            if K.EQ <= op <= K.LE:
                r = K.rel_(op, u[1], u[2])
            else:
                r = K.mk(tuple(u))
        nw[n] = r
    return fv[e] if ev[e] else nw[e]


def g_eval(code, ctx):                                          #@L 2
    """Evaluates the RPN of user input (DESIGN 7.8); ctx is [deg, mainvar, approx, inert].
    - numbers: K.num; a float sets ctx[X_APPROX] and is built through exact() (in inert mode
      it stays a FLT);
    - names: CONSTS, else a symbol (theta, left, mid, ... too);
    - operators: the constructors; '-' is add_([a, add_([b], -1)]), neg is add_([a], -1);
      a relation with a sentinel operand is built as it stands (no fold);
    - functions: fnb, in the angle mode; approx/evalf: approx() at once;
    - a command (SESS.CMDS, through SESS.ALIAS): r = yield its generator(args, ctx), after
      SESS.need loaded its module; a None result fails g_eval too (bare return). In inert mode
      a command is CALL(SYM(name), args), like any other unknown call;
    - lists: LST.
    Then the default result path, unless inert: when the last item is a command with
    F_ALWAYSAUTO, or is not one with F_NOAUTO and A.simplify_candidate(r) holds,
    r = yield norm.g_autosimp(r) (a None result keeps r). Last, approx(r) if ctx[X_APPROX]."""
    S = SESS
    deg = ctx[X_DEG]
    inert = ctx[X_INERT]
    st = []
    fl = 0                              # the registry flags of the last item, if a command
    for it in code:
        k = it[0]
        if k == 'P':
            continue
        fl = 0
        if k == 'n':
            v = it[1]
            if type(v) is not float:
                x = K.num(v[0], 0, v[1])
            elif inert:
                x = K.flt(v)
            else:
                ctx[X_APPROX] = 1
                x = exact(v)
        elif k == 's':
            x = CONSTS.get(it[1])
            if x is None:
                x = K.sym(it[1])
        elif k == 'o':
            o = it[1]
            if o == "'":
                raise K.CasError(M_PRIME)
            b = st.pop()
            if o == 'neg':
                x = K.add_([b], K.MONE)
            elif o == '!':
                x = K.fn_(K.FACT, b)
            else:
                a = st.pop()
                if o == '+':
                    x = K.add_([a, b])
                elif o == '-':
                    x = K.add_([a, K.add_([b], K.MONE)])
                elif o == '*':
                    x = K.mul_(K.ONE, [(a, K.ONE), (b, K.ONE)])
                elif o == '/':
                    x = K.mul_(K.ONE, [(a, K.ONE), (b, K.MONE)])
                elif o == '^':
                    x = K.mul_(K.ONE, [(a, b)])
                else:
                    r = RELOPS.get(o)
                    if r is None:
                        raise K.CasError(M_ASSIGN)          # => or := inside an expression
                    if issent(a) or issent(b):
                        if r >= K.GT:
                            a, b = b, a
                            r -= K.GT - K.LT
                        x = K.mk((r, a, b))
                    else:
                        x = K.rel_(r, a, b)
        elif k == 'F':
            f = it[1]
            n = it[2]
            a = st[len(st) - n:]
            del st[len(st) - n:]
            x = fnb(f, a, deg)
            if not x:
                nm = f
                ent = None
                if S is not None:
                    nm = S.ALIAS.get(f, f)
                    ent = S.CMDS.get(nm)
                if inert:
                    ent = None
                elif nm == 'approx' or nm == 'evalf':
                    if n != 1:
                        raise K.CasError(M_ARGS)
                    x = approx(a[0])
                    fl = F_NOAUTO
                elif nm == 'purge':
                    raise K.CasError(M_PURGE)
                if x:
                    pass
                elif ent is not None:
                    if n < ent[2] or n > ent[3]:
                        raise K.CasError(M_ARGS)
                    if nm == 'integrate' and n == 4 and ent[1] == 'g_integrate':
                        M = S.need('def')                               #@calls 3
                        x = yield M.g_defint(tuple(a), ctx)             #@calls 2
                    else:
                        M = S.need(ent[0])                              #@calls 3
                        x = yield getattr(M, ent[1])(tuple(a), ctx)     #@calls 2
                    if x is None:
                        return
                    fl = ent[4]
                else:
                    x = K.mk((K.CALL, K.sym(nm)) + tuple(a))
        elif k == 'L':
            n = it[1]
            x = K.mk((K.LST,) + tuple(st[len(st) - n:]))
            del st[len(st) - n:]
        else:
            raise K.CasError(M_SYNTAX)
        st.append(x)
    if len(st) != 1:
        raise K.CasError(M_SYNTAX)
    r = st[0]
    if not inert and S is not None and (
            fl & F_ALWAYSAUTO or not fl & F_NOAUTO and A.simplify_candidate(r)):
        M = S.need('norm')                                              #@calls 3
        x = yield M.g_autosimp(r)                                       #@calls 2
        if x is not None:
            r = x
    if ctx[X_APPROX] and not inert:
        r = approx(r)
    yield r
