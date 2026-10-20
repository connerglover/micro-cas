#@L 2
# Calculator editor, history and the 320x210 application shell. The engine (node, alg, parse,
# printer, run) is imported by engine() on first use; until then the shell runs with an empty
# history, theme 0 and radians (docs/notes/FASTBOOT.md). All drawing goes through draw.py.
import gc
import sys
import time
import ti_system as TS
import draw as D

K = None            #@lazy node     (engine() binds the engine modules)
A = None            #@lazy alg
P = None            #@lazy parse
PR = None           #@lazy printer
R = None            #@lazy run
MONO = getattr(time, 'monotonic', None)          #@native
TICKS = getattr(time, 'ticks_ms', None)          #@native
TDIFF = getattr(time, 'ticks_diff', None)        #@native
BOOT_MS = None      # from the top of casevo.py to the first screen (None: no clock)
ENGINE_MS = None    # importing and wiring the engine

QUIT = ['quit']
LINE = ''
CUR = 0
XOFF = 0
MOD = 0
MODE = 0
SEL = -1
HERO = True
DX = 0
ENTRYPOS = -1
LASTENTRY = ''
STATUS = ''
NOTE = ''           # shown in the status bar with the next answer (the engine load time)
FULL = True         # the next redraw repaints everything, not only the status and edit rows
VIEW = None         # what the stage showed at the last redraw
# The MathPrint editor model (docs/notes/MATHPRINT.md 1.1, 6.5): LINE and CUR stay the state, in
# engine syntax; emodel() derives the rest from (LINE, CLASSIC) and the keys read it.
EXOFF = 0           # pixel scroll of a 2D entry (XOFF scrolls a flat one, in characters)
EH = 20             # entry box height: 20, 40, 60 or 80
EDMAP = None        # the caret map of the last 2D layout of LINE (draw.mlayout mode 2), or None
EDL = None          # the last painted entry: EDMAP's display list (as laid out) and key
EKEY = None
EMODEL = None       # (LINE, CLASSIC) of the model; None: rebuild at the next emodel()
EFLAT = True        # LINE is drawn and edited as a flat (1D) line
PENDING = None      # (a, b): put the caret in the first empty slot of LINE[a:b] (emodel)
ED1D = False        # LINE is 2D but over the layout caps (or out of memory): edited flat
EFAIL = None        # the LINE a panic (reason 0 or 3) ran on: edited flat until it changes
CLASSIC = False     # F3 setup: Entry Classic, today's 1D editor
VIEWEND = -1        # the bottom history entry shown in MODE
STATVIEW = None     # what the status row last showed (repainted only when it changes)
HINTVIEW = None     # what the hint row last showed
CARETC = 'INK'      # the caret's color slot
EDIFF = True        # False: every entry change repaints the whole entry box (no diff paint)
PAGEMAX = 5         # history entries shown at most

# Screen rows (MATHPRINT.md 6.1). A text cell is 15 rows of ink starting at its top (draw.py);
# EY = 190 - EH is the entry box's top (170 at EH 20, when every row is today's).
#   0..18      status: angle, status text, modifier chip; a rule at 19
#  20..EY-21   history: entries stacked upwards from EY-20, input left, result right-aligned
# EY-19..EY-2  hint, or the focused entry's footer (text at EY-17); a rule at EY-1
#  EY..189     entry: content centred, view x 10..309, scroll markers at x 0 and 310, caret
# 190..209     F-key tabs (191..209), labels at 193
VIEWW = 300
HEROH = 92
LISTH = 60
FKEYS = ('menu', 'recall', 'setup', 'forms', 'help')
CHIPS = ('', '2nd', 'a', 'a-lock', 'A-LOCK')
# The TI-84 Evo keypad (TI's Evo key map and keypad notes): x^n left of sin (51; 2nd xRoot),
# the fraction template on the CE's apps key (42), / * - + one row up (55 65 75 85), and < >
# in the CE's + place (95), which switches representations: here the answer's forms (as F4).
# (key codes, texts): kmap(T, k) is the text of key k in table T, or None.
PLAIN = (b' *34567=>?@AGHIJKQRSTU[\\]^fgh',
         'x|/|^|sin(|cos(|tan(|/|^2|,|(|)|*|log(|7|8|9|-|ln(|4|5|6|+|=>|1|2|3|0|.|-')
SECOND = (b' 34567=>?@AGKQUgh',
         't|surd(|asin(|acos(|atan(|pi|sqrt(|E|{|}|e|10^(|[|e^(|]|i|ans()')
ALPHA = (b' )*+34567=>?@AGHIJKQRSTU[\\]^fg',
         "theta|a|b|c|d|e|f|g|h|i|j|k|l|m|n|o|p|q|r|s|t|u|v|w|x|y|z|theta| |'")
# The hint line's signatures (UI data, available before the engine loads; each fits the 31
# columns). ALIAS repeats run.ALIAS (tests/test_run.py keeps the two equal).
HINT = (' simplify(e) expand(e) factor(e,[x]) together(e) solve(eq,[x]) diff(f,x,[n])'
        ' integrate(f,x,[a,b]) limit(f,x,a,[dir]) taylor(f,x=a,[n]) partfrac(e,[x])'
        ' sum(f,k,a,b) riemann(f,x,a,b,n,[method]) desolve(eq,[y]) grad(f,[x,y,z])'
        ' polararea(r,t,a,b) paramarea(x,y,t,a,b) arclen(f,x,a,b) purge(x,...) approx(e) ')
ALIAS = {'int': 'integrate', 'd': 'diff', 'deriv': 'diff', 'lim': 'limit', 'series': 'taylor',
         'ratnormal': 'together', 'dsolve': 'desolve', 'gradient': 'grad'}
# The template picker (MATHPRINT.md 3.2): (label, text, caret); caret -1: the first empty slot
# in drawn order (PENDING). Rows 1 and 2 are the fraction and power keys' actions.
TMPL = ('n/d  fraction##0;x^n  power##0;sqrt  square root#sqrt()#5;n-root  nth root#surd(,)#5;'
        'e^x#e^()#3;10^x#10^()#4;log_b  log base b#log(,)#-1;|x|  absolute value#abs()#4;'
        'int  integral#integrate(,x)#-1;int a..b  definite#integrate(,x,,)#-1;'
        'd/dx  derivative#diff(,x)#-1;sum  k=a..b#sum(,k,,)#-1;lim  limit#limit(,x,)#-1')
TN = 13
# The prefilled second parameter of these rows (menub.insertion): it counts as empty for DEL.
PREFILL = {'integrate': 'x', 'diff': 'x', 'limit': 'x', 'riemann': 'x', 'arclen': 'x', 'sum': 'k'}


def hint(name):                                                #@L 4
    """The hint-row signature of the command name (HINT), or ''."""
    i = HINT.find(' ' + name + '(')
    return HINT[i + 1:HINT.find(' ', i + 1)] if i >= 0 else ''


def tmpl(j):                                                   #@L 3
    """TMPL row j: [label, text, caret]."""
    return TMPL.split(';')[j].split('#')


def kmap(t, k):                                                #@L 3
    """The text of key k in the key table t (PLAIN, SECOND, ALPHA), or None."""
    i = t[0].find(bytes((k,))) if 0 < k < 256 else -1
    return t[1].split('|')[i] if i >= 0 else None


def clock():                                                   #@L 4
    """time.monotonic() (seconds) if the device has it, else time.ticks_ms(), else None."""
    if MONO is not None:
        return MONO()
    if TICKS is not None:
        return TICKS()
    return None


def since(t0):                                                 #@L 3
    """Milliseconds from t0 (a clock() reading) to now, or None without a clock."""
    t = clock()
    if t is None or t0 is None:
        return None
    if MONO is not None:
        return int((t - t0) * 1000)
    if TDIFF is not None:
        return TDIFF(t, t0)
    return t - t0


def secs(ms):                                                  #@L 3
    if ms is None or ms < 0:
        return '?'
    return str(ms // 1000) + '.' + str(ms % 1000 // 100) + 's'


def room():                                                    #@L 4
    """Columns for the status text: from x 45 to the modifier chip (or the right edge)."""
    chip = CHIPS[MOD]
    return (270 - 10*len(chip) - (10 if chip else 0)) // 10


def status(s):                                                 #@L 3
    """Show s in the status text area at once (accent color), without a redraw; the next redraw
    repaints the status row (STATVIEW)."""
    global STATVIEW
    STATVIEW = None
    n = room()
    D.rect(45, 0, 10*n, 19, D.COLORS['BG'])
    D.text(s[:n], 45, 2, D.COLORS['ACC'])


def enclosing():                                               #@L 3
    """The name of the call around the caret (hint row, help): the letters and digits before
    the innermost '(' that has one, leading digits dropped (2sin( is sin). A '(' without a name
    (a group, a hidden fraction or exponent paren) is skipped (MATHPRINT.md 7.4)."""
    depth = 0
    for i in range(CUR - 1, -1, -1):
        c = LINE[i]
        if c == ')':
            depth += 1
        elif c == '(':
            if depth:
                depth -= 1
            else:
                j = i
                while j and (LINE[j-1].isalpha() or LINE[j-1].isdigit()):
                    j -= 1
                while j < i and LINE[j].isdigit():
                    j += 1
                if j < i:
                    return LINE[j:i]
    return ''


def insert(text, offset=None):                                  #@L 3
    """Insert text at the caret (offset: the caret's move, default len(text)); False past 256."""
    return put(LINE[:CUR] + text + LINE[CUR:], CUR + (len(text) if offset is None else offset))


def put(line, cur):                                            #@L 4
    """Every edit: the new line and caret with a typed key's side effects, unless the line would
    pass 256 characters (then only STATUS says so and False is returned)."""
    global LINE, CUR, MODE, STATUS, HERO, DX, NOTE
    if len(line) > 256:
        STATUS = 'Input limit: 256 characters'
        return False
    LINE, CUR = line, cur
    MODE, STATUS, HERO, DX, NOTE = 0, '', not line, 0, ''
    return True


def wrapped(text):                                             #@L 3
    atom = bool(text)
    for c in text:
        if not (c.isalpha() or c.isdigit() or c == '.'):
            atom = False
    if atom:
        return text
    return '(' + text + ')'


def tidy(s, back=0):                                           #@L 3
    """ENTER's text in MathPrint (docs/notes/MATHPRINT.md 1.3): drop the structure parens
    around a fraction operand or exponent that is one number or letter (x^(-1) also), when the
    neighbours keep the meaning, and the empty base of log(u,). History stays short 1D text.
    back: recalled text instead (1.4): wrap each stacked-fraction operand and exponent that is
    not one group in parens, so the recalled input is 2D again. A construct with an operand
    that ends in a letter right before '(' is left as it is: x(2) is a product unless x is a
    user function, and wrapping would change which. (The layout already keeps a fraction or
    power over a name the engine may cut, a/bc, inline.) Past 256 characters: s unchanged."""
    r = None
    try:
        r = D.mparse(s, D.mlex(s), 1) if s else None
    except MemoryError:                     # the 1D text, as Classic sends it
        gc.collect()
    if r is None:
        return s
    nodes = r[0]
    n = len(s)
    ins = []                                # (i, t): t goes before s[i]; '' drops s[i]
    for nd in nodes:
        k = nd[0]
        if back:
            if k != 'Q' and k != 'W':
                continue
            m = len(ins)
            for o in ((nd[4][0], nd[4][1]) if k == 'Q' else (nd[4][1],)):
                g = nodes[o]
                e = g[2]
                if e < n and s[e] == '(' and s[e - 1].isalpha():
                    del ins[m:]
                    break
                if g[0] != 'G' or not g[4] & 2:
                    ins.append((g[1], '('))
                    ins.append((e, ')'))
            continue
        cands = ()
        if k == 'Q':
            cands = ((nd[4][0], False), (nd[4][1], False))
        elif k == 'W':
            cands = ((nd[4][1], True),)
        elif k == 'T' and s[nd[1]:nd[4][0]] == 'log' and nodes[nodes[nd[3][1]][3][0]][0] == 'E':
            ins.append((nodes[nd[3][0]][2], ''))
        for gi, power in cands:
            g = nodes[gi]
            if g[0] != 'G' or not g[4] & 2:
                continue
            a = g[1]
            b = g[2] - 1
            c = s[b + 1] if b + 1 < n else ''
            j = a + 1
            sign = power and j < b and s[j] == '-'
            if sign:
                j += 1
            num = j < b
            for i in range(j, b):
                if not (s[i].isdigit() or s[i] == '.'):
                    num = False
            if not (num or not sign and b == a + 2 and s[a + 1].isalpha()):
                continue
            if sign and c and c not in '+-,)=<>':
                continue
            if a and (s[a - 1].isalpha() or s[a - 1].isdigit() or s[a - 1] == '.'):
                continue
            if a > 2 and s[a - 1] in '+-' and s[a - 2] == 'E' and s[a - 3].isdigit():
                continue                    # 2E+(3)/(4): 2E+3 would be one number (D.mlex)
            if c and (c.isalpha() or c.isdigit() or c in ".([!'^"):
                continue
            ins.append((a, ''))
            ins.append((b, ''))
    if not ins:
        return s
    ins.sort()
    out = []
    p = 0
    for i, c in ins:
        out.append(s[p:i])
        out.append(c)
        p = i if c else i + 1
    out.append(s[p:])
    t = ''.join(out)
    return s if len(t) > 256 else t


def empty_slot():                                              #@L 3
    """The caret position of an empty argument slot, or -1. Needs the engine (P.FNAMES). In
    MathPrint the empty base of log(u,) is optional (tidy drops it), so it is skipped."""
    for token in ('(,', ',,', ',)'):
        i = LINE.find(token)
        while i >= 0 and token == ',)' and not CLASSIC:
            o = bmatch(LINE, i + 1, -1)
            # the call name as the layout reads it (D.mname): 2log( and xlog( are log_b too
            if o < 3 or D.mname(LINE, o) != o - 3 or LINE[o-3:o] != 'log':
                break
            if len(spans(o, i + 1)) != 2:
                break
            i = LINE.find(token, i + 2)
        if i >= 0:
            return i + 1
    i = LINE.find('()')
    while i >= 0:
        j = i
        while j and (LINE[j-1].isalpha() or LINE[j-1].isdigit()):
            j -= 1
        name = ALIAS.get(LINE[j:i], LINE[j:i])
        if hint(name) or name in P.FNAMES:
            return i + 1
        while j < i and LINE[j].isdigit():
            j += 1
        if j == i and not CLASSIC:
            return i + 1                    # an empty group: 2*()
        i = LINE.find('()', i + 2)
    if not CLASSIC:                         # an operator before an autoclosed closer: sin(2+)
        for i in range(1, len(LINE)):
            if LINE[i] in ')]}' and LINE[i-1] in '+-*/^=<>':
                return i
    if LINE and LINE[-1] in '+-*/^,(=':
        return len(LINE)
    return -1


def empty_map():                                               #@L 3
    """ENTER's engine-free empty-slot check (MATHPRINT.md 2.2), or -1: the first empty box in
    drawn order of a 2D line (an empty log base is optional); on a flat or degraded line, the
    first hidden empty pair ^(), /() or ()/( that empty_slot does not know. Never lays out."""
    M = EDMAP
    if M is not None and M[0] == LINE:
        for e in M[12]:
            if not e[1] & 2:
                return e[0]
        return -1
    best = -1
    for t, d in (('^()', 2), ('/()', 2), ('()/(', 1)):
        i = LINE.find(t)
        if i >= 0 and (best < 0 or i + d < best):
            best = i + d
    return best


def emodel():                                                  #@L 2
    """The editor model of LINE (MATHPRINT.md 6.5): flat or 2D and its caret map, the pending
    caret, the caret snapped to a stop, the entry height and scroll. It draws nothing. Rebuilt
    only when (LINE, CLASSIC) changed, so a degraded line (over the caps, out of memory, or the
    line a panic ran on) is not laid out again until its text changes."""
    global EMODEL, EFLAT, EDMAP, ED1D, PENDING, CUR, EH, EXOFF
    s = LINE
    n = len(s)
    if EMODEL != (s, CLASSIC):
        EMODEL = (s, CLASSIC)
        EDMAP = None
        ED1D = False
        EFLAT = CLASSIC or s == EFAIL or n > 160 or D.mflat(s)
        if not EFLAT:
            try:
                EDMAP = D.mlayout(s, 2)
            except MemoryError:
                EDMAP = None
                ED1D = 2                # key() frees the idle engine packs and tries again
                gc.collect()
            if EDMAP is None:
                EFLAT = True
                ED1D = ED1D or True
    M = EDMAP
    if PENDING is not None:
        if M is not None:
            for e in M[12]:
                if PENDING[0] <= e[0] < PENDING[1]:
                    CUR = e[0]
                    break
        PENDING = None
    CUR = max(0, min(CUR, n))
    if M is None:
        while not CLASSIC and CUR < n and not D.mstop(s, CUR):
            CUR += 1                        # Classic: every index is a stop (8)
        EXOFF = 0
        if not n:
            EH = 20
        return
    X = M[5]
    while CUR < n and X[CUR] < 0:
        CUR += 1
    h = M[3] + M[4]
    EH = max(EH, 20 if h <= 19 else 40 if h <= 36 else 60 if h <= 56 else 80)
    x = X[CUR]
    if 9 + x - EXOFF > 304:
        EXOFF = x + 9 - 304 + 60
    elif 9 + x - EXOFF < 10:
        EXOFF = max(0, x - 60)
    EXOFF = min(EXOFF, max(0, M[2] - 230))    # keeps the 60 px look-ahead at the end


def bmatch(s, i, d):                                           #@L 5
    """The index of the bracket matching s[i], an opener (d = 1) or a closer (d = -1), any
    bracket type counting; -1 if it has none."""
    depth = 0
    while 0 <= i < len(s):
        c = s[i]
        if c in '([{':
            depth += d
        elif c in ')]}':
            depth -= d
        if not depth:
            return i
        i += d
    return -1


def spans(o, cl):                                              #@L 4
    """The top-level argument spans [a, e) between the opener at o and the closer at cl."""
    out = []
    depth = 0
    a = o + 1
    for j in range(o + 1, cl):
        c = LINE[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ',' and not depth:
            out.append((a, j))
            a = j + 1
    out.append((a, cl))
    return out


def edslot(i):                                                 #@L 4
    """The slot row (s, e, kind, os, oe, k, n, hidden, dep) of caret i (MATHPRINT.md 4.1): the
    caret map's when it is fresh (the stale-map rule, 1.1), else a bracket scan of the flat line,
    where every bracket is visible and a top-level comma also ends the slot (R root, G group,
    C call)."""
    M = EDMAP
    if M is not None and M[0] == LINE and M[9][i] >= 0:
        return M[10][M[9][i]]
    s = LINE
    n = len(s)
    depth = 0
    a = o = -1
    k = 0
    for j in range(i - 1, -1, -1):
        c = s[j]
        if c in ')]}':
            depth += 1
        elif c in '([{':
            if not depth:
                o = j
                break
            depth -= 1
        elif c == ',' and not depth:
            if a < 0:
                a = j + 1
            k += 1
    if a < 0:
        a = o + 1
    e = -1
    oe = n
    ns = k + 1
    depth = 0
    for j in range(i, n):
        c = s[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if not depth and o >= 0:
                oe = j + 1
                if e < 0:
                    e = j
                break
            depth -= 1
        elif c == ',' and not depth:
            if e < 0:
                e = j
            ns += 1
    if e < 0:
        e = n
    if o < 0:
        return (a, e, 'R', 0, n, k, ns, False, 0)
    m = D.mname(s, o)
    if m >= 0:
        return (a, e, 'C', m, oe, k, ns, False, 1)
    return (a, e, 'G', o, oe, k, ns, False, 1)


def edterm(i):                                                 #@L 4
    """Where the term that ends at caret i starts (the fraction key's capture, MATHPRINT.md 2.1):
    letters, digits, . ' ! and bare ^, closed bracket groups with a name before them, hidden
    exponents and whole stacked fractions, inside the current slot."""
    s = LINE
    M = EDMAP
    fresh = M is not None and M[0] == s
    lo = 0
    if fresh and M[9][i] >= 0:
        lo = M[10][M[9][i]][0]
    p = i
    while p > lo:
        c = s[p - 1]
        if c.isalpha() or c.isdigit() or c in ".'!^":
            p -= 1
            continue
        if p < i and p - 1 > lo and (c == '/' and (s[p-2].isalpha() or s[p-2].isdigit() or
                                                   s[p-2] in ")]}.'!") or
                                     c in '+-' and s[p-2] == 'E' and p > 2 and
                                     s[p-3].isdigit() and s[p].isdigit()):
            p -= 1                          # an inline a/b is one term; so is 2E+3
            continue
        if c not in ')]}':
            break
        q = -1
        if fresh:
            for x in M[11]:
                if x[3] == 'Q' and x[2] == p:
                    q = x[0]
        if q < 0:
            q = bmatch(s, p - 1, -1)
            if q < 0:
                break
        p = q
    return p


def leave(grp):                                                #@L 4
    """The leave rule (MATHPRINT.md 2): while the caret ends a hidden denominator or exponent
    slot, move it to the end of that fraction or power. grp (+ and -): only out of a slot that
    holds exactly one visible group."""
    global CUR
    M = EDMAP
    if M is None or M[0] != LINE:
        return
    while M[9][CUR] >= 0:
        r = M[10][M[9][CUR]]
        if CUR != r[1] or not (r[2] == 'Q' and r[5] == 1 or r[2] == 'W' and r[7]):
            return
        if grp and not (r[1] > r[0] and LINE[r[0]] in '([{' and
                        bmatch(LINE, r[0], 1) == r[1] - 1):
            return
        CUR = r[4]


def keep(os, oe, u):                                           #@L 4
    """DEL's keep-(U) test (MATHPRINT.md 4.3): the text u that replaces the construct [os, oe)
    keeps parens when it has a top-level operator or sign, unless the construct is alone in its
    slot (a line start, opener or comma before it; a line end, closer or comma after it)."""
    depth = 0
    op = False
    for c in u:
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif not depth and c in '+-*/^=<>,:':
            op = True
    if not op:
        return False
    b = LINE[os - 1] if os else ','
    a = LINE[oe] if oe < len(LINE) else ')'
    return not (b in '([{,' and a in ')]},')


def blank(a, e, k, os):                                        #@L 4
    """Slot [a, e) counts as empty for DEL: no text, or the prefilled x or k (second parameter)
    of the call or template that starts at os (MATHPRINT.md 3)."""
    if a == e:
        return True
    return k == 1 and LINE[a:e] == PREFILL.get(LINE[os:LINE.find('(', os)], '')


def wrapend(s, c, base):                                       #@L 4
    """(s, c) with the stacked fraction or power that ends at caret c wrapped in parens, so a
    following ^, ! or ' applies to all of it (MATHPRINT.md 2: x^(2)|^ is (x^(2))^); base: the
    stop between a power's base and its exponent (where down lands) counts as its end."""
    M = EDMAP
    if M is None or M[0] != s:
        return s, c
    if base:
        for q in M[11]:
            if q[1] == c and q[3] == 'W' and q[2] > c:
                c = q[2]
    cs = -1
    for q in M[11]:
        if q[2] == c and (q[3] == 'Q' or q[3] == 'W') and (cs < 0 or q[0] < cs):
            cs = q[0]
    if cs >= 0:
        s = s[:cs] + '(' + s[cs:c] + ')' + s[c:]
        c += 2
    return s, c


def edins(op, t=''):                                           #@L 3
    """Insert at the caret (MATHPRINT.md 2): 'frac' the fraction template with term capture,
    'pow' x^() and 'sq' x^(2) (a stacked fraction or power that ends at the caret is wrapped
    first), 'open' a bracket closed at the end of the slot, 'close' a closer, 'comma', and
    'text' t (a text ending in '(' gets its closer)."""
    global CUR
    s = LINE
    c = CUR
    M = EDMAP
    if op == 'frac':
        if M is not None and M[0] == s:
            for q in M[11]:             # at a power's base stop: from the power's end
                if q[1] == c and q[3] == 'W' and q[2] > c:
                    c = q[2]
        p = edterm(c)
        if p == c:
            mid, cur = '()/()', c + 1
        elif s[p] == '(' and bmatch(s, p, 1) == c - 1:
            mid, cur = s[p:c] + '/()', c + 2       # the group is the numerator
        else:
            mid, cur = '(' + s[p:c] + ')/()', c + 4
        r = edslot(c)
        if r[2] == 'W' and not r[7]:            # a bare exponent gets its parens first
            put(s[:r[0]] + '(' + s[r[0]:p] + mid + s[c:r[1]] + ')' + s[r[1]:], cur + 1)
        else:
            put(s[:p] + mid + s[c:], cur)
    elif op == 'pow' or op == 'sq':
        s, c = wrapend(s, c, 1)
        if op == 'pow':
            put(s[:c] + '^()' + s[c:], c + 2)
        else:
            put(s[:c] + '^(2)' + s[c:], c + 4)
    elif op == 'open':
        r = edslot(c)
        if r[2] == 'W' and r[7] and r[0] == c and r[1] == c:
            return                          # the empty exponent box is the group
        e = r[1]
        put(s[:c] + t + s[c:e] + ')]}'['([{'.index(t)] + s[e:], c + 1)
    elif op == 'close':
        if c < len(s) and s[c] == t:
            CUR = c + 1                     # step over its closer, hidden or visible
            return
        o = -1
        depth = 0
        for j in range(c - 1, -1, -1):
            if s[j] in ')]}':
                depth += 1
            elif s[j] in '([{':
                if not depth:
                    o = j
                    break
                depth -= 1
        if o < 0:
            put(s[:c] + t + s[c:], c + 1)   # at the root: a literal closer
            return
        if s[o] != '([{'[')]}'.index(t)]:
            return
        if M is not None and M[0] == s:
            for q in M[10]:
                if q[0] == o + 1 and (q[2] == 'T' or q[2] == 'Q' or q[2] == 'W' and q[7]):
                    return                  # a template or hidden slot: nothing to close
        cl = bmatch(s, o, 1)
        if cl < 0:
            put(s[:c] + t + s[c:], c + 1)   # closes an unclosed group
        elif cl > c and (s.find(',', c, cl) < 0 or len(spans(c - 1, cl)) == 1):
            # moves the autoclosed closer here, unless that would leave a top-level comma
            # (a later argument) outside the call: then there is nothing to close (4)
            put(s[:c] + t + s[c:cl] + s[cl+1:], c + 1)
    elif op == 'comma':
        leave(0)
        c = CUR
        if c < len(s) and s[c] == ',':
            CUR = c + 1
        else:
            put(s[:c] + ',' + s[c:], c + 1)
    elif t[-1] == '(':
        put(s[:c] + t + ')' + s[c:], c + len(t))
    else:
        put(s[:c] + t + s[c:], c + len(t))


def eddel():                                                   #@L 3
    """DEL (MATHPRINT.md 4.3), the first rule that matches; hidden characters are only ever
    removed with their construct. True: the caller moves the caret left (into a construct, or
    to the previous slot of a template) instead."""
    global CUR
    s = LINE
    c = CUR
    if not c:
        return False
    at = s.rfind('ans()', 0, c + 4)
    if at >= 0 and at < c <= at + 5:
        put(s[:at] + s[at+5:], at)
        return False
    M = EDMAP
    if M is not None and M[0] == s and M[9][c] >= 0:
        X, Y, SLOTS = M[5], M[6], M[10]
        r = SLOTS[M[9][c]]
        kind, os, oe = r[2], r[3], r[4]
        if r[0] == c and kind != 'R':
            sib = []                        # the owner's slots, in drawn order
            full = True
            for q in SLOTS:
                if q[2] == kind and q[3] == os and q[4] == oe:
                    sib.append(q)
                    if not blank(q[0], q[1], q[5], os):
                        full = False
            if full and (kind == 'Q' or kind == 'W' or kind == 'T'):
                put(s[:os] + s[oe:], os)    # an empty construct; a power's base stays
                return False
            if kind == 'W':
                CUR = os
                return False
            if kind == 'Q':
                num = sib[0]
                if sib[1][0] == sib[1][1]:
                    u = s[num[0]:num[1]]
                    if keep(os, oe, u):
                        u = '(' + u + ')'
                    put(s[:os] + u + s[oe:], os + (len(u) if r[5] else 0))
                elif r[5]:
                    CUR = num[1]
                else:
                    CUR = os
                return False
            if (kind == 'T' or kind == 'C') and r[0] == sib[0][0]:
                for q in sib[1:]:
                    if not blank(q[0], q[1], q[5], os):
                        CUR = os            # other slots hold text: to the outer start
                        return False
                u = s[r[0]:r[1]]
                k = keep(os, oe, u)
                put(s[:os] + ('(' + u + ')' if k else u) + s[oe:], os + (1 if k else 0))
                return False
            if kind == 'T':
                return True                 # a later template slot: like left
            if kind == 'G' and not r[5] and r[0] == os + 1 and sib[-1][1] == oe - 1:
                put(s[:os] + s[os+1:oe-1] + s[oe:], os)
                return False
        p = c - 1
        while p and X[p] < 0:
            p -= 1
        t = s[p:c]
        if Y[p] == Y[c] and (len(t) == 1 and t not in '()[]{},' or t == 'pi' or t == 'oo' or
                             t == 'theta'):
            put(s[:p] + s[c:], p)           # one visible leaf: a character or a glyph
            return False
        best = None
        for q in M[11]:
            if q[2] == c and (best is None or q[0] > best[0]):
                best = q
        if best is not None:
            kind, os, oe = best[3], best[1], best[2]
            full = True
            last = -1
            for q in SLOTS:
                if q[2] == kind and q[3] == os and q[4] == oe:
                    last = q[1]
                    if not blank(q[0], q[1], q[5], os):
                        full = False
            if kind == 'Q' or kind == 'W' or kind == 'T' or last == oe - 1:
                if full:
                    put(s[:os] + s[oe:], os)
                    return False
                return True                 # into the construct
    elif s[c - 1] in '([{':
        o = c - 1
        cl = bmatch(s, o, 1)
        if cl >= 0:
            m = D.mname(s, o)
            if m < 0:
                put(s[:o] + s[o+1:cl] + s[cl+1:], o)
                return False
            sp = spans(o, cl)
            for k in range(1, len(sp)):
                if not blank(sp[k][0], sp[k][1], k, m):
                    CUR = m
                    return False
            u = s[sp[0][0]:sp[0][1]]
            k = keep(m, cl + 1, u)
            put(s[:m] + ('(' + u + ')' if k else u) + s[cl+1:], m + (1 if k else 0))
            return False
    elif s[c - 1] in ')]}':
        o = bmatch(s, c - 1, -1)
        if o >= 0:
            m = D.mname(s, o)
            if m < 0:
                m = o
            sp = spans(o, c - 1)
            for k in range(len(sp)):
                if not blank(sp[k][0], sp[k][1], k, m):
                    return True
            put(s[:m] + s[c:], m)
            return False
    put(s[:c-1] + s[c:], c - 1)
    return False


def edmove(d, mod):                                            #@L 3
    """Left/right (d = -1/1; MATHPRINT.md 4.2): the previous or next stop in drawn order (2D) or
    in the line (flat), with no layout; 2nd: home or end."""
    global CUR
    n = len(LINE)
    if mod == 1:
        CUR = 0 if d < 0 else n
        return
    M = EDMAP
    if M is not None and M[0] == LINE:
        X, Y, ORD = M[5], M[6], M[8]
        while CUR < n and X[CUR] < 0:
            CUR += 1
        x = X[CUR]
        y = Y[CUR]
        r = ORD.index(CUR) + d
        while 0 <= r < len(ORD) and X[ORD[r]] == x and Y[ORD[r]] == y:
            r += d
        if 0 <= r < len(ORD):
            CUR = ORD[r]
        return
    c = CUR + d
    while 0 < c < n and not D.mstop(LINE, c):
        c += d
    CUR = max(0, min(n, c))


def edvert(d):                                                 #@L 3
    """Up/down (d = -1/1; MATHPRINT.md 4.4): the nearest stop above or below inside the innermost
    fraction, power or template around the caret, then the next one out; from an exponent down
    to just after its base, and back up. False when there is none (or the line is flat)."""
    global CUR
    M = EDMAP
    if M is None or M[0] != LINE or M[5][CUR] < 0:
        return False
    X, Y = M[5], M[6]
    x = X[CUR]
    y = Y[CUR]
    if d < 0:
        for r in M[10]:
            if r[2] == 'W' and r[3] == CUR:
                CUR = r[0]
                return True
    out = []
    for q in M[11]:
        if q[1] < CUR < q[2] and (q[3] == 'Q' or q[3] == 'W' or q[3] == 'T'):
            out.append((q[2] - q[1], q[1], q[2], q[3]))
    out.sort()
    for q in out:
        if q[3] == 'W' and d > 0:
            CUR = q[1]
            return True
        best = None
        for i in range(q[1] + 1, q[2]):
            if X[i] >= 0 and (Y[i] < y - 2 if d < 0 else Y[i] > y + 2):
                b = (abs(Y[i] - y) // 8, abs(X[i] - x), i)
                if best is None or b < best:
                    best = b
        if best is not None:
            CUR = best[2]
            return True
    return False


def paste(text, bare):                                         #@L 3
    """A history paste at the caret (MATHPRINT.md 7.4): text, or bare (when given) inside an
    empty hidden fraction or exponent slot, whose parens already group it."""
    if bare is not None:
        r = edslot(CUR)
        if r[0] == CUR and r[1] == CUR and (r[2] == 'Q' or r[2] == 'W' and r[7]):
            text = bare
    put(LINE[:CUR] + text + LINE[CUR:], CUR + len(text))


def edkey(k, mod):                                             #@L 2
    """A MathPrint editing key (MATHPRINT.md 2): DEL, the arrows, up and down, the template
    keys and the keys that insert text."""
    global MODE, SEL, DX
    if k == 23:
        if eddel():
            edmove(-1, 0)
        return
    if k == 24 or k == 26:
        edmove(-1 if k == 24 else 1, mod)
        return
    if k == 25:
        if not LINE or mod == 1 or not edvert(-1):
            if R is not None and R.HIST:
                MODE, SEL, DX = 1, len(R.HIST) - 1, 0
        return
    if k == 34:
        edvert(1)
        return
    if mod == 0 and not LINE and R is not None and R.ANS is not None and \
            k in (51, 55, 61, 65, 75, 85, 91):  # 95 has no text here (key's F4 branch)
        put('ans()', 5)                     # the leading-operator rule; the map is now stale
    if mod == 0 and k == 42:
        edins('frac')
    elif mod == 0 and k == 51:
        edins('pow')
    elif mod == 0 and k == 61:
        edins('sq')
    elif mod == 0 and k == 62:
        edins('comma')
    elif mod == 1 and k == 51:
        put(LINE[:CUR] + 'surd(,)' + LINE[CUR:], CUR + 5)
    else:
        t = kmap(SECOND if mod == 1 else PLAIN, k)
        if t is None:
            return
        if t in '([{':
            edins('open', t)
        elif t in ')]}':
            edins('close', t)
        else:
            if mod == 0 and (k == 75 or k == 85 or k == 91):
                leave(k != 91)
            edins('text', t)


def picker():                                                  #@L 2
    """The template picker (2nd + the fraction key; MATHPRINT.md 3.2), engine-free: the TMPL
    row picked, or None. It changes no editor state; key applies the row."""
    C = D.COLORS
    sel = 0
    while True:
        page = sel // 7
        D.rect(0, 0, 320, 210, C['BG'])
        D.line(0, 19, 319, 19, C['LINE'])
        D.line(0, 188, 319, 188)
        n = min(7, TN - page * 7)
        D.color(C['INK'])
        D.text('Templates  ' + str(page + 1) + '/2', 5, 2)
        for j in range(page * 7, page * 7 + n):
            D.text(('>' if j == sel else ' ') + str(j - page * 7 + 1) + ' ' + tmpl(j)[0], 5,
                   22 + 17 * (j - page * 7))
        D.text('1-' + str(n) + ' pick  <> page  CLEAR back', 5, 192, C['ACC'])
        k = TS.wait_key()
        if k == 45 or k == 11 or k == 42:
            return None
        if k == 105:
            return sel
        if k == 25 or k == 34:
            sel = (sel + (1 if k == 34 else -1)) % TN
        elif k == 24 or k == 26:
            sel = min((1 - page) * 7 + sel % 7, TN - 1)
        else:
            t = kmap(PLAIN, k)
            if t is not None and t.isdigit() and 0 < int(t) <= 7 and \
                    page * 7 + int(t) <= TN:
                return page * 7 + int(t) - 1


def epaint(full):                                              #@L 3
    """Paint the entry box (MATHPRINT.md 6.4, step 5), first matching path: the whole box (a
    full redraw, a flat line, a changed geometry, no previous entry, or EDIFF off); a caret
    move on an unchanged 2D line: only a 2 px strip at the old caret and the items meeting it;
    a 2D text change: everything right of the leftmost change. Nothing when neither the line,
    the caret nor the geometry changed. full: the screen is already cleared. Every path stores
    the painted display list in EDL (EDMAP's own, in layout coordinates: drawn at
    10 - EXOFF, top; no copy) and (LINE, CUR, geometry, caret column, caret top) in EKEY."""
    global EDL, EKEY
    C = D.COLORS
    ey = 190 - EH
    M = EDMAP
    if EFLAT or M is None or M[0] != LINE:
        M = None
        h = 15
        asc = 11
    else:
        h = M[3] + M[4]
        asc = M[3]
    top = ey + (EH - h) // 2
    geo = (M is None, XOFF if M is None else 0, EXOFF, EH, C['BG'], top, asc)
    old = EKEY
    box = False
    if M is None:
        cx = 9 + 10 * (CUR - XOFF)
        cy = top
    else:
        cx = 9 + M[5][CUR] - EXOFF
        cy = top + M[6][CUR]
        for e in M[12]:
            if e[0] == CUR and not e[1] & 1:
                box = True              # the caret in the middle of the box (5.4)
                cx += 5
    if not full and old is not None and old[0] == LINE and old[1] == CUR and old[2] == geo:
        return
    EKEY = (LINE, CUR, geo, cx, cy)
    path = 0
    if not full and EDIFF and M is not None and old is not None and old[2] == geo and \
            EDL is not None:
        path = 2
        if old[0] == LINE:
            path = 1
            for e in M[12]:             # the trailing box at the caret shows or hides: diff
                if e[1] & 1 and (e[0] == CUR or e[0] == old[1]):
                    path = 2
    was = EDL
    dl = EDL = None if M is None else M[1]
    dx = 10 - EXOFF
    clip = (10, ey, 309, 189)
    ink = C['INK']
    x0 = 0
    if path == 1:
        x0 = old[3]
        D.rect(x0, old[4] - 1, 2, 17, C['BG'])
        D.mrender(dl, dx, top, clip, x0, x0 + 1, C['SUB'], True, CUR)
        D.mrender(dl, dx, top, clip, x0, x0 + 1, ink, False)
    elif path == 2:
        x0 = min(cx, old[3]) - dx       # in display-list coordinates (the geometry is the same)
        n = max(len(was), len(dl))
        for j in range(n):
            a = was[j] if j < len(was) else None
            b = dl[j] if j < len(dl) else None
            for it in (a, b):           # a trailing box shown or hidden at either caret: changed
                if it is not None and (a != b or it[0] == 'b' and it[6] & 1 and
                                       (it[5] == CUR or it[5] == old[1])):
                    x = it[1]
                    if it[0] == 'l' and it[3] < x:
                        x = it[3]
                    if x < x0:
                        x0 = x
        x0 = max(0, x0 + dx)
        D.rect(x0, ey, 320 - x0, EH, C['BG'])
        D.mrender(dl, dx, top, clip, x0, 319, C['SUB'], True, CUR)
        D.mrender(dl, dx, top, clip, x0, 319, ink, False)
    else:
        if not full:
            D.rect(0, ey, 320, EH, C['BG'])
        if M is None:
            D.text(LINE[XOFF:XOFF + 30], 10, top, ink)
        else:
            if not full:                # a full redraw draws the boxes in its SUB batch
                D.mrender(dl, dx, top, clip, 0, 319, C['SUB'], True, CUR)
            D.mrender(dl, dx, top, clip, 0, 319, ink, False)
    if M is None:
        less = XOFF > 0
        more = len(LINE) > XOFF + 30
    else:
        less = EXOFF > 0
        more = M[2] - EXOFF > 300
    by = top + asc - 11
    if less and path != 1 and x0 < 10:
        D.text('<', 0, by, ink)
    if more and path != 1:
        D.text('>', 310, by, ink)
    if M is None:                       # a flat line: today's caret
        D.line(cx, cy - 1, cx, cy + 15, C[CARETC])
    elif box:                           # inside an empty slot's box, clear of its outline
        D.line(cx, cy + 1, cx, cy + 11, C[CARETC])
    else:                               # the text cell: 1 px clear of a fraction bar
        D.line(cx, cy, cx, cy + 14, C[CARETC])


def redraw():                                                  #@L 2
    """Repaint the shell (MATHPRINT.md 6.4). A full redraw (FULL, or the view changed: theme,
    MODE, selection, page, answer scroll, history length, entry height) paints everything in
    six color batches: background, accent tint (tabs, selection band), rules and empty boxes,
    ink, gray, accent. Otherwise only the rows whose contents changed: the status row
    (STATVIEW), the hint row (HINTVIEW) and the entry (epaint); nothing at all when nothing
    changed. emodel() ran before: redraw never lays out the entry."""
    global XOFF, DX, FULL, VIEW, VIEWEND, STATVIEW, HINTVIEW
    theme = R.SET['theme'] if R is not None else 0
    hist = R.HIST if R is not None else []
    n = len(hist)
    D.theme(theme)
    C = D.COLORS
    ey = 190 - EH
    sb = ey - 20
    XOFF = max(0, min(XOFF, CUR))
    if CUR - XOFF > 29:
        XOFF = CUR - 29
    fi = (SEL if MODE else n - 1) if n else -1
    left = right = ''
    if n and (MODE or not LINE and HERO):           # the focused entry's footer
        e = hist[fi]
        if e[2] == R.R_ANS:
            label = e[5][-1][0] if e[5] else 'exact'
            right = label + '  F4'
            left = (('+ C  ' if e[4] & R.F_PLUSC else '') + (
                '~ ' + str(e[3]) if e[3] is not None and label == 'exact' else ''))[
                :29 - len(right)]
    else:
        name = enclosing()
        left = hint(ALIAS.get(name, name))[:31]
    deg = R is not None and R.SET['deg']
    sv = (STATUS[:room()], MOD, deg)
    hv = (left, right, ey)
    chip = CHIPS[MOD]
    span = VIEW[7] if VIEW is not None else DX
    if DX > span:                   # the focused answer's overflow at the last full redraw:
        DX = span                   # <-/-> past it is a no-op key, not a full redraw
    if not FULL and VIEW == (theme, MODE, SEL, VIEWEND, DX, n, EH, span):
        st = sv != STATVIEW
        ht = hv != HINTVIEW
        if st:
            D.rect(0, 0, 320, 19, C['BG'])
        if ht:
            D.rect(0, ey - 19, 320, 18, C['BG'])
        epaint(False)
        if st:
            D.text('DEG' if deg else 'RAD', 5, 2, C['INK'])
            D.text(sv[0], 45, 2)
        if ht and left:
            D.text(left, 5, ey - 17, C['SUB'])
        if ht and right:
            D.text(right, 315 - 10*len(right), ey - 17, C['ACC'])
        if st and chip:
            D.text(chip, 315 - 10*len(chip), 2, C['ACC'])
        STATVIEW = sv
        HINTVIEW = hv
        return
    # The history page (MATHPRINT.md 7.1, 7.2): entries stacked upwards from sb, the focused
    # one always shown. In MODE the page ends at VIEWEND; when SEL is above the page, a forward
    # pass from SEL finds the new VIEWEND and the page is planned again from it.
    plan = []
    span = 0
    d = -1
    start = n - 1
    if MODE:
        start = VIEWEND if SEL <= VIEWEND < n else SEL
    for ps in range(3 if n else 0):
        plan = []
        y = sb
        used = 0
        i = start
        while 0 <= i < n and len(plan) < PAGEMAX:
            f = hist[i]
            inp = None
            try:
                inp = D.mlayout(f[0], 1)
            except Exception:       # MemoryError, or a layout bug: drawn 1D, the shell lives on
                gc.collect()
            if inp is None or inp[1] > VIEWW or inp[2] + inp[3] > LISTH:
                inp = None
                iw = 10 * len(f[0][:31])
                ia = 11
                ih = 15
            else:
                iw = inp[1]
                ia = inp[2]
                ih = inp[2] + inp[3]
            b = lines = None
            if f[2] == R.R_ANS:
                b = D.layout(f[1], VIEWW, HEROH)
                rw = b[1]
                ra = b[2]
                cap = LISTH
                if i == fi:         # the stage's height, less the input's when it goes under it
                    cap = sb - 21
                    if iw + rw + 20 > VIEWW or b[3] > LISTH:
                        cap -= ih + 2
                    cap = max(15, min(HEROH, cap))
                    span = max(0, rw - VIEWW)
                rh = min(b[3], cap)
            else:
                lines = D.wrap(f[1], 30)[:3] if i == fi else [f[1][:30]]
                rw = 0
                for t in lines:
                    rw = max(rw, 10 * len(t))
                ra = 11
                rh = 17 * len(lines) - 2
            if iw + rw + 20 <= VIEWW and rh <= LISTH:
                a = max(ia, ra)
                h = a + max(ih - ia, rh - ra)
                it = a - ia
                rt = a - ra
            else:
                h = ih + 2 + rh
                it = 0
                rt = ih + 2
            if d > 0:
                if plan and used + h > sb - 21:
                    break
                used += h + 3
                plan.append(i)
            else:
                if plan and y - h < 21:
                    break
                y -= h
                plan.append((y, h, i, inp, it, b, lines, rt, rw, rh))
                y -= 3
            i += d
        if d > 0:
            start = plan[-1]
            d = -1
        elif MODE and plan[-1][2] > SEL:
            start = SEL
            d = 1
        else:
            break
    if MODE and plan:
        VIEWEND = plan[0][2]
    DX = min(DX, span)
    D.rect(0, 0, 320, 210, C['BG'])
    D.color(C['ACCSOFT'])
    for i in range(5):
        D.rect(64*i, 191, 63, 19)
    for p in plan:
        if MODE and p[2] == SEL:
            y = max(20, p[0] - 1)
            D.rect(0, y, 320, min(sb, p[0] + p[1] + 1) - y)
    D.line(0, 19, 319, 19, C['LINE'])
    D.line(0, ey - 1, 319, ey - 1)
    epaint(True)
    D.text('DEG' if deg else 'RAD', 5, 2, C['INK'])
    D.text(sv[0], 45, 2)
    for p in plan:
        b = p[5]
        if b is not None:
            y = p[0] + p[7]
            x = 310 - p[8] if p[8] <= VIEWW else 10 - (DX if p[2] == fi else 0)
            D.render(b[0], x, (10, max(20, y), 309, min(sb - 1, y + p[9] - 1)), y)
            if p[2] == fi and span:
                y += p[9] // 2 - 7
                if DX:
                    D.text('<', 0, y)
                if DX < span:
                    D.text('>', 310, y)
    clip = (0, 20, 319, sb - 1)
    D.color(C['SUB'])
    if EDL is not None:                 # the entry's empty-slot boxes (epaint skipped them)
        D.mrender(EDL, 10 - EXOFF, EKEY[2][5], (10, ey, 309, 189), 0, 319, C['SUB'], True, CUR)
    for p in plan:
        if p[3] is None:
            D.text(hist[p[2]][0][:31], 5, p[0] + p[4], None, clip)
        else:
            D.mrender(p[3][0], 5, p[0] + p[4], clip, 0, 319, C['SUB'], False)
        if p[6] is not None:
            for j in range(len(p[6])):
                D.text(p[6][j], 310 - 10*len(p[6][j]), p[0] + p[7] + 17*j, None, clip)
    D.text(left, 5, ey - 17)
    if not n and 118 < ey - 21:
        D.text('Type math, or press menu', 40, 104)
    D.color(C['ACC'])
    D.text(chip, 315 - 10*len(chip), 2)
    for i in range(5):
        D.text(FKEYS[i], 64*i + (63 - 10*len(FKEYS[i])) // 2, 193)
    D.text(right, 315 - 10*len(right), ey - 17)
    VIEW = (theme, MODE, SEL, VIEWEND, DX, n, EH, span)
    FULL = False
    STATVIEW = sv
    HINTVIEW = hv


def boot(t0=None):                                             #@L 1
    """The first screen, without the engine. t0: the clock() reading at the top of casevo."""
    global BOOT_MS, STATUS, FULL
    D.reset()
    FULL = True
    emodel()
    redraw()
    BOOT_MS = since(t0)
    STATUS = 'ready ' + secs(BOOT_MS) if BOOT_MS is not None else 'ready'
    redraw()


def engine():                                                  #@L 2
    """The run module, imported (leaf first) and wired on the first call, with the load time
    in ENGINE_MS and a 'Loading engine...' status drawn while it loads."""
    global K, A, P, PR, R, ENGINE_MS, STATUS, NOTE, BALLAST
    if R is not None:
        return R
    t0 = clock()
    STATUS = 'Loading engine...'
    status(STATUS)
    BALLAST = None                      # the low heap it kept free takes the engine
    gc.collect()
    before = list(sys.modules)
    try:
        import node as K
        import alg as A
        import parse as P
        import printer as PR
        import run as R
    except BaseException:
        # MicroPython 1.12 keeps a module whose import failed: drop everything this attempt
        # added, so the next ENTER imports a whole engine instead of a half-run one.
        for name in list(sys.modules):
            if name not in before:
                del sys.modules[name]
        K = A = P = PR = R = None
        raise
    before = None
    P.SESS = R
    K.ESC = TS.escape
    if hasattr(gc, 'mem_free'):
        K.MEMFREE = R.MEMFREE = gc.mem_free
    R.BUSY = busy
    D.P = P
    D.PR = PR
    ENGINE_MS = since(t0)
    NOTE = STATUS = 'engine ' + (secs(ENGINE_MS) if ENGINE_MS is not None else 'loaded')
    return R


def busy(steps):                                               #@L 2
    status('Calculating' + '.' * (1 + (steps // 512) % 3))


def key(k):                                                    #@L 1
    """One key (MATHPRINT.md 2: dispatch order). MathPrint editing keys go to edkey; Classic
    keeps the 1D editor. The editor model is refreshed before dispatch and before every redraw;
    a job (ENTER, F4) frees it before the computation."""
    global LINE, CUR, MOD, MODE, SEL, HERO, DX, ENTRYPOS, LASTENTRY, STATUS, FULL, XOFF, EXOFF
    global PENDING, VIEWEND, EDMAP, EDL, EKEY, EMODEL, ED1D, BALLAST
    job = None
    if k == 21 or k == 31:
        if k == 21:
            MOD = 4 if MOD == 3 else 3 if MOD == 4 else 0 if MOD == 1 else 1
        else:
            MOD = 3 if MOD in (1, 2) else 0 if MOD >= 3 else 2
        emodel()
        redraw()
        return None
    if EMODEL != (LINE, CLASSIC):
        emodel()
    mod = MOD
    if MOD < 3:
        MOD = 0
    hist = R.HIST if R is not None else []
    al = kmap(ALPHA, k) if mod >= 2 else None
    if al is not None:
        line, at = LINE, CUR
        if k == 103 and not CLASSIC:
            line, at = wrapend(line, at, 0)     # the prime, like !: (x^(2))'
        t = al.upper() if mod == 4 else al
        put(line[:at] + t + line[at:], at + len(t))
    elif k == 22 and mod == 1:
        return QUIT
    elif k == 45:
        if MODE:
            MODE = 0
        elif LINE:
            LINE, CUR, XOFF, EXOFF, PENDING = '', 0, 0, 0, None
        else:
            HERO = False
        STATUS = ''
        TS.escape()
    elif k in (24, 26) and (MODE or not LINE):
        DX = max(0, DX + (-24 if k == 24 else 24))
    elif k in (25, 34) and MODE:
        d = (-5 if mod == 1 else -1) if k == 25 else (5 if mod == 1 else 1)
        SEL = max(0, SEL+d)
        if SEL >= len(hist):
            MODE, SEL = 0, len(hist)-1
        DX = 0
    elif k == 105:
        if MODE:
            e = hist[SEL]
            if CLASSIC:
                insert(e[0] if mod == 1 else wrapped(e[1]))
            elif mod == 1:
                paste(tidy(e[0], 1), None)
            else:
                paste(wrapped(e[1]), e[1])
        elif mod == 1:
            if hist:
                ENTRYPOS = min(ENTRYPOS+1, len(hist)-1) if LINE == LASTENTRY else 0
                LINE = hist[-1-ENTRYPOS][0]
                if not CLASSIC:
                    LINE = tidy(LINE, 1)
                CUR = len(LINE)
                LASTENTRY = LINE
        else:
            pos = -1
            if LINE and not CLASSIC:
                pos = empty_map()       # engine-free: the model is fresh
            if pos < 0 and LINE:
                engine()                # the first ENTER loads the engine
                pos = empty_slot()
            if pos >= 0:
                CUR, STATUS = pos, 'fill in the empty slot'
            elif LINE or hist:
                job = ('eval', (LINE if CLASSIC or LINE == EFAIL else tidy(LINE)) or
                       hist[-1][0])     # a failed line is not parsed again (EFAIL)
    elif (k == 14 or k == 95) and hist:
        idx = SEL if MODE else len(hist)-1
        if hist[idx][2] == R.R_ANS:
            job = ('form', idx)
    elif k in (11, 12, 13, 15, 22, 41, 44) or (k == 102 and mod == 1):
        kind = 'algebra'
        if k in (12, 44):
            kind = 'recall'
        elif k in (13, 22):
            kind = 'setup'
        elif k == 15:
            kind = 'help'
        elif k == 41:
            kind = 'test' if mod == 1 else 'calculus'
        elif k == 102:
            kind = 'all'
        engine()
        FULL = True
        choice = R.need('menu').open(kind, LINE, CUR, enclosing())
        if not R.HIST:
            MODE, SEL = 0, -1
        elif SEL >= len(R.HIST):
            SEL = len(R.HIST) - 1
        VIEWEND = min(VIEWEND, len(R.HIST) - 1)
        if EMODEL != (LINE, CLASSIC):
            emodel()                    # the menu may have switched Classic
        if choice is not None:
            R.need('menub').apply(choice)   # CASMNU is loaded: the menu just ran
    elif k == 42 and mod == 1 and not CLASSIC:
        row = picker()
        FULL = True
        if row == 0:
            edins('frac')
        elif row == 1:
            edins('pow')
        elif row is not None:
            text, at = tmpl(row)[1], CUR
            c = int(tmpl(row)[2])
            if put(LINE[:at] + text + LINE[at:], at + (c if c >= 0 else text.find('(') + 1)) and \
                    c < 0:
                PENDING = (at, at + len(text))
    elif not CLASSIC:
        edkey(k, mod)
    elif k == 23:
        at = LINE.rfind('ans()', 0, CUR + 4)
        if at >= 0 and at < CUR <= at + 5:
            LINE = LINE[:at] + LINE[at+5:]
            CUR = at
        elif CUR:
            LINE = LINE[:CUR-1] + LINE[CUR:]
            CUR -= 1
    elif k in (24, 26):
        if mod == 1:
            CUR = 0 if k == 24 else len(LINE)
        else:
            CUR = max(0, min(len(LINE), CUR + (-1 if k == 24 else 1)))
    elif k in (25, 34) and hist:
        if k == 25:
            MODE, SEL = 1, len(hist)-1
        DX = 0
    else:
        text = kmap(SECOND if mod == 1 else PLAIN, k)
        if text is not None:
            if not LINE and R is not None and R.ANS is not None and \
                    k in (51, 55, 61, 65, 75, 85, 91, 95) and mod == 0:
                insert('ans()')
            insert(text)
    if job is not None:
        STATUS = 'Calculating...'
        D.clear_cache()
    emodel()
    if ED1D == 2 and (R is not None or BALLAST is not None):
        EDL = EKEY = EMODEL = BALLAST = None    # the layout ran out of memory: the boot block,
        D.clear_cache()                 # the idle soft and aux packs (input, printer), the
        while R is not None and (R.shed() or R.shed(None, R.AUX)):  # layout caches and the
            pass                        # last entry paint give way, then one more try; the
        emodel()                        # families stay (room() reloads a soft pack as usual)
        ED1D = bool(ED1D)               # no more tries until the text changes (5.3)
    redraw()
    if job is not None:
        EDMAP = EDL = EKEY = EMODEL = PENDING = None
        D.clear_cache()
    return job


def show(job, rec):                                             #@L 1
    global LINE, CUR, MODE, HERO, DX, STATUS, ENTRYPOS, FULL, NOTE, EH, XOFF, EXOFF
    global EDMAP, EDL, EKEY, EMODEL, PENDING, VIEWEND
    if job[0] == 'eval':
        LINE, CUR, MODE, HERO, DX, ENTRYPOS = '', 0, 0, True, 0, -1
    EH, XOFF, EXOFF, VIEWEND = 20, 0, 0, -1
    EDMAP = EDL = EKEY = EMODEL = PENDING = None
    STATUS = rec[1] if rec[0] == R.R_MSG else NOTE
    NOTE = ''
    if rec[3] & R.F_PURGEHINT:
        STATUS = 'Stored; purge(name) clears it'
    FULL = True
    emodel()
    redraw()


def reason(e):                                                   #@L 1
    """The panic message for an exception the entry loop caught; anything that is not the
    program's (the desktop key script's stop) is raised again. node.CasMemory is the engine's
    Out of memory outside a command (a layout, a menu): a BaseException, so that engine code's
    'except Exception' cannot swallow it."""
    if isinstance(e, MemoryError) or K is not None and isinstance(e, K.CasMemory):
        return 0
    if isinstance(e, KeyboardInterrupt):
        return 1
    if isinstance(e, RuntimeError):
        return 2
    if isinstance(e, Exception):
        return 3
    raise e


def panic(reason):                                             #@L 1
    """After an exception in the entry loop: a plain screen (no layout), with or without the
    engine. The next key redraws everything."""
    global STATUS, MODE, SEL, HERO, DX, FULL, EH, XOFF, EXOFF, EDMAP, EDL, EKEY, PENDING, EMODEL
    global EFLAT, ED1D, VIEWEND, EFAIL, STATVIEW, HINTVIEW
    D.clear_cache()
    EH, XOFF, EXOFF, VIEWEND = 20, 0, 0, -1
    EDMAP = EDL = EKEY = PENDING = EMODEL = STATVIEW = HINTVIEW = None
    EFLAT, ED1D = True, False
    if reason == 0 or reason == 3:
        EFAIL = LINE        # drawn and edited flat until it changes: never retry a failing layout
    if R is not None:
        R.sweep()           # a pack cut short by MemoryError would fail every later key
    gc.collect()
    STATUS = ('Out of memory', 'Interrupted', 'Expression too complex', 'Display error')[reason]
    D.reset()
    D.theme(R.SET['theme'] if R is not None else 0)
    C = D.COLORS
    hist = R.HIST if R is not None else []
    e = None
    if hist:
        e = hist[SEL if MODE and 0 <= SEL < len(hist) else len(hist) - 1]
    D.rect(0, 0, 320, 210, C['BG'])
    D.line(0, 169, 319, 169, C['LINE'])
    D.color(C['SUB'])
    if e is not None:
        D.text(e[0][:31], 5, 30)
    D.text('CLEAR edits; 2nd MODE quits', 5, 193)
    D.color(C['INK'])
    D.text(STATUS, 5, 2)
    if e is not None:
        D.text(e[1][:28] + '...' if len(e[1]) > 31 else e[1], 5, 56)
    offset = max(0, CUR - 29)
    D.text(LINE[offset:offset+30], 10, 172)
    MODE, SEL, HERO, DX, FULL = 0, -1, False, 0, True


# Boot order (MATHPRINT.md 0.8): the view pack CASUX is imported right after this module, and
# the engine's resident packs only at the first ENTER or menu. This block keeps the low heap
# free while CASUX loads, so CASUX sits above it; boot() releases it at once, and the engine
# later loads into that low heap: shedding CASUX during a computation then leaves one hole at
# the top, not one under the engine (native ui_calculus needed about 194 KB without the block,
# 180 KB with it, whether it is released at boot or held until the engine loads).
BALLAST = bytearray(80000) if hasattr(gc, 'mem_free') and gc.mem_free() > 144000 else None
