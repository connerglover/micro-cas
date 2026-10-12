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

# Screen rows. A text cell is 15 rows of ink starting at its top (draw.py); 31 columns.
#   0..18  status: angle, status text, modifier chip; a rule at 19
#  20..150 stage: the hero (input 22, answer view 10..309 x 40..131, footer 134) or the
#          newest entries stacked upwards from 150 (input row, then the answer right-aligned)
# 151..168 hint (153); a rule at 169
# 170..189 editor (172): 30 columns at x 10..309, scroll markers at x 0 and 310, caret
# 190..209 F-key tabs (191..209), labels at 193
VIEWW = 300
HEROH = 92
LISTH = 60
FKEYS = ('menu', 'recall', 'setup', 'forms', 'help')
CHIPS = ('', '2nd', 'a', 'a-lock', 'A-LOCK')
# The TI-84 Evo keypad (TI's Evo key map and keypad notes): x^n left of sin (51; 2nd xRoot),
# the fraction template on the CE's apps key (42), / * - + one row up (55 65 75 85), and < >
# in the CE's + place (95), which switches representations: here the answer's forms (as F4).
PLAIN = {32:'x', 42:'/', 51:'^', 52:'sin(', 53:'cos(', 54:'tan(', 55:'/', 61:'^2',
         62:',', 63:'(', 64:')', 65:'*', 71:'log(', 72:'7', 73:'8', 74:'9',
         75:'-', 81:'ln(', 82:'4', 83:'5', 84:'6', 85:'+', 91:'=>',
         92:'1', 93:'2', 94:'3', 102:'0', 103:'.', 104:'-'}
SECOND = {32:'t', 51:'surd(', 52:'asin(', 53:'acos(', 54:'atan(', 55:'pi', 61:'sqrt(',
          62:'E', 63:'{', 64:'}', 65:'e', 71:'10^(', 75:'[', 81:'e^(',
          85:']', 103:'i', 104:'ans()'}
ALPHA = {32:'theta', 41:'a', 42:'b', 43:'c', 51:'d', 52:'e', 53:'f', 54:'g',
         55:'h', 61:'i', 62:'j', 63:'k', 64:'l', 65:'m', 71:'n', 72:'o',
         73:'p', 74:'q', 75:'r', 81:'s', 82:'t', 83:'u', 84:'v', 85:'w',
         91:'x', 92:'y', 93:'z', 94:'theta', 102:' ', 103:"'"}
# The hint line's signatures (UI data, available before the engine loads; each fits the 31
# columns). ALIAS repeats run.ALIAS (tests/test_run.py keeps the two equal).
HINT = {'simplify': 'simplify(e)', 'expand': 'expand(e)', 'factor': 'factor(e,[x])',
        'together': 'together(e)', 'solve': 'solve(eq,[x])', 'diff': 'diff(f,x,[n])',
        'integrate': 'integrate(f,x,[a,b])', 'limit': 'limit(f,x,a,[dir])',
        'taylor': 'taylor(f,x=a,[n])', 'partfrac': 'partfrac(e,[x])',
        'sum': 'sum(f,k,a,b)', 'riemann': 'riemann(f,x,a,b,n,[method])',
        'desolve': 'desolve(eq,[y])', 'grad': 'grad(f,[x,y,z])',
        'polararea': 'polararea(r,t,a,b)', 'paramarea': 'paramarea(x,y,t,a,b)',
        'arclen': 'arclen(f,x,a,b)', 'purge': 'purge(x,...)', 'approx': 'approx(e)'}
ALIAS = {'int': 'integrate', 'd': 'diff', 'deriv': 'diff', 'lim': 'limit', 'series': 'taylor',
         'ratnormal': 'together', 'dsolve': 'desolve', 'gradient': 'grad'}


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
    """Show s in the status text area at once (accent color), without a redraw."""
    n = room()
    D.rect(45, 0, 10*n, 19, D.COLORS['BG'])
    D.text(s[:n], 45, 2, D.COLORS['ACC'])


def enclosing():                                               #@L 3
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
                return LINE[j:i]
    return ''


def insert(text, offset=None):                                  #@L 3
    global LINE, CUR, MODE, STATUS, HERO, DX, NOTE
    if len(LINE) + len(text) > 256:
        STATUS = 'Input limit: 256 characters'
        return
    LINE = LINE[:CUR] + text + LINE[CUR:]
    CUR += len(text) if offset is None else offset
    MODE, STATUS, HERO, DX, NOTE = 0, '', not LINE, 0, ''


def wrapped(text):                                             #@L 3
    atom = bool(text)
    for c in text:
        if not (c.isalpha() or c.isdigit() or c == '.'):
            atom = False
    if atom:
        return text
    return '(' + text + ')'


def empty_slot():                                              #@L 3
    """The caret position of an empty argument slot, or -1. Needs the engine (P.FNAMES)."""
    for token in ('(,', ',,', ',)'):
        i = LINE.find(token)
        if i >= 0:
            return i + 1
    i = LINE.find('()')
    while i >= 0:
        j = i
        while j and (LINE[j-1].isalpha() or LINE[j-1].isdigit()):
            j -= 1
        name = ALIAS.get(LINE[j:i], LINE[j:i])
        if name in HINT or name in P.FNAMES:
            return i + 1
        i = LINE.find('()', i + 2)
    if LINE and LINE[-1] in '+-*/^,(=':
        return len(LINE)
    return -1


def redraw():                                                  #@L 2
    """Repaint the shell. The status, hint and editor rows are always redrawn; the stage and
    the F-key bar only when FULL is set or the stage's view changed. Drawing is batched by
    color: background, rules, gray text, ink, accent."""
    global XOFF, DX, FULL, VIEW
    theme = R.SET['theme'] if R is not None else 0
    hist = R.HIST if R is not None else []
    D.theme(theme)
    C = D.COLORS
    hero = bool(hist) and bool(MODE or (not LINE and HERO))
    full = FULL or VIEW != (theme, MODE, SEL, hero, DX, len(hist))
    plan = []
    e = box = None
    span = 0
    if full and hero:
        e = hist[SEL if MODE else len(hist) - 1]
        if e[2] == R.R_ANS:
            box = D.layout(e[1], VIEWW, HEROH)
            span = max(0, box['w'] - VIEWW)
            DX = min(DX, span)
    elif full and hist:
        y = 150
        for i in range(len(hist) - 1, max(-1, len(hist) - 6), -1):
            f = hist[i]
            b = D.layout(f[1], VIEWW, LISTH) if f[2] == R.R_ANS else None
            top = y - 17 - (min(b['h'], LISTH) if b is not None else 15)
            if top < 21:
                break
            plan.append((top, f, b))
            y = top - 3
    if full:
        D.rect(0, 0, 320, 210, C['BG'])
        D.color(C['ACCSOFT'])
        for i in range(5):
            D.rect(64*i, 191, 63, 19)
        D.line(0, 19, 319, 19, C['LINE'])
        D.line(0, 169, 319, 169)
    else:
        D.rect(0, 0, 320, 19, C['BG'])
        D.rect(0, 151, 320, 18)
        D.rect(0, 170, 320, 20)
    name = enclosing()
    D.text(HINT.get(ALIAS.get(name, name), '')[:31], 5, 153, C['SUB'])
    footer = ''
    if e is not None:
        D.text(e[0][:31], 5, 22)
        if box is not None:
            label = e[5][-1][0] if e[5] else 'exact'
            footer = label + '  F4'
            left = ('+ C  ' if e[4] & R.F_PLUSC else '') + (
                '~ ' + str(e[3]) if e[3] is not None and label == 'exact' else '')
            D.text(left[:29 - len(footer)], 5, 134)
        else:
            lines = D.wrap(e[1], 31)
            for j in range(min(5, len(lines))):
                D.text(lines[j], 5, 48 + 17*j)
    for top, f, b in plan:
        D.text(f[0][:31], 5, top)
        if b is None:
            D.text(f[1][:30], 310 - 10*len(f[1][:30]), top + 17)
    if full and not hist:
        D.text('Exact algebra and calculus', 30, 84)
        D.text('Type math, or press menu', 40, 104)
    D.color(C['INK'])
    D.text('DEG' if R is not None and R.SET['deg'] else 'RAD', 5, 2)
    D.text(STATUS[:room()], 45, 2)
    XOFF = max(0, min(XOFF, CUR))
    if CUR - XOFF > 29:
        XOFF = CUR - 29
    D.text(LINE[XOFF:XOFF+30], 10, 172)
    if box is not None:
        D.paint(box, 10, 40, DX if span else (box['w'] - VIEWW) // 2,
                (box['h'] - HEROH) // 2 if box['h'] < HEROH else 0)
    for top, f, b in plan:
        if b is not None:
            D.paint(b, 10, top + 17, min(0, b['w'] - VIEWW), 0)
    if full and not hist:
        D.text('cas-evo', 125, 58)
    D.color(C['ACC'])
    D.text(CHIPS[MOD], 315 - 10*len(CHIPS[MOD]), 2)
    x = 9 + 10*(CUR - XOFF)
    D.line(x, 171, x, 187)
    if XOFF:
        D.text('<', 0, 172)
    if len(LINE) > XOFF + 30:
        D.text('>', 310, 172)
    if full:
        for i in range(5):
            D.text(FKEYS[i], 64*i + (63 - 10*len(FKEYS[i])) // 2, 193)
        D.text(footer, 315 - 10*len(footer), 134)
        if DX:
            D.text('<', 0, 78)
        if DX < span:
            D.text('>', 310, 78)
    VIEW = (theme, MODE, SEL, hero, DX, len(hist))
    FULL = False


def boot(t0=None):                                             #@L 1
    """The first screen, without the engine. t0: the clock() reading at the top of casevo."""
    global BOOT_MS, STATUS, FULL
    D.reset()
    FULL = True
    redraw()
    BOOT_MS = since(t0)
    STATUS = 'ready ' + secs(BOOT_MS) if BOOT_MS is not None else 'ready'
    redraw()


def engine():                                                  #@L 2
    """The run module, imported (leaf first) and wired on the first call, with the load time
    in ENGINE_MS and a 'Loading engine...' status drawn while it loads."""
    global K, A, P, PR, R, ENGINE_MS, STATUS, NOTE
    if R is not None:
        return R
    t0 = clock()
    STATUS = 'Loading engine...'
    status(STATUS)
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
    global LINE, CUR, MOD, MODE, SEL, HERO, DX, ENTRYPOS, LASTENTRY, STATUS, FULL
    job = None
    if k == 21:
        MOD = 4 if MOD == 3 else 3 if MOD == 4 else 0 if MOD == 1 else 1
        redraw()
        return None
    if k == 31:
        MOD = 3 if MOD in (1, 2) else 0 if MOD >= 3 else 2
        redraw()
        return None
    mod = MOD
    if MOD < 3:
        MOD = 0
    hist = R.HIST if R is not None else []
    if mod >= 2 and k in ALPHA:
        insert(ALPHA[k].upper() if mod == 4 else ALPHA[k])
    elif k == 22 and mod == 1:
        return QUIT
    elif k == 45:
        if MODE:
            MODE = 0
        elif LINE:
            LINE, CUR = '', 0
        else:
            HERO = False
        STATUS = ''
        TS.escape()
    elif k == 23:
        at = LINE.rfind('ans()', 0, CUR + 4)
        if at >= 0 and at < CUR <= at + 5:
            LINE = LINE[:at] + LINE[at+5:]
            CUR = at
        elif CUR:
            LINE = LINE[:CUR-1] + LINE[CUR:]
            CUR -= 1
    elif k in (24, 26):
        d = -1 if k == 24 else 1
        if MODE or not LINE:
            DX = max(0, DX + d*24)
        elif mod == 1:
            CUR = 0 if d < 0 else len(LINE)
        else:
            CUR = max(0, min(len(LINE), CUR + d))
    elif k in (25, 34) and hist:
        d = (-5 if mod == 1 else -1) if k == 25 else (5 if mod == 1 else 1)
        if not MODE and k == 25:
            MODE, SEL = 1, len(hist)-1
        elif MODE:
            SEL = max(0, SEL+d)
            if SEL >= len(hist):
                MODE, SEL = 0, len(hist)-1
        DX = 0
    elif k == 105:
        if MODE:
            e = hist[SEL]
            insert(e[0] if mod == 1 else wrapped(e[1]))
        elif mod == 1:
            if hist:
                ENTRYPOS = min(ENTRYPOS+1, len(hist)-1) if LINE == LASTENTRY else 0
                LINE = hist[-1-ENTRYPOS][0]
                CUR = len(LINE)
                LASTENTRY = LINE
        else:
            if LINE:
                engine()                # the first ENTER loads the engine
            pos = empty_slot() if LINE else -1
            if pos >= 0:
                CUR, STATUS = pos, 'fill in the empty slot'
            elif LINE or hist:
                job = ('eval', LINE or hist[-1][0])
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
        if choice is not None:
            text, wrap, offset = choice
            if wrap and (CUR == len(LINE)) and (LINE or R.ANS is not None):
                first = LINE or 'ans()'
                j = text.find('(') + 1
                text = text[:j] + first + text[j:]
                offset += len(first)
                if len(text) > 256:
                    STATUS, text = 'Input limit: 256 characters', None
                else:
                    LINE, CUR = '', 0
            if text is not None:
                insert(text, offset)
    else:
        text = SECOND.get(k) if mod == 1 else PLAIN.get(k)
        if text is not None:
            if not LINE and R is not None and R.ANS is not None and \
                    k in (51, 55, 61, 65, 75, 85, 91, 95) and mod == 0:
                insert('ans()')
            insert(text)
    if job is not None:
        STATUS = 'Calculating...'
        D.clear_cache()
    redraw()
    if job is not None:
        D.clear_cache()
    return job


def show(job, rec):                                             #@L 1
    global LINE, CUR, MODE, HERO, DX, STATUS, ENTRYPOS, FULL, NOTE
    if job[0] == 'eval':
        LINE, CUR, MODE, HERO, DX, ENTRYPOS = '', 0, 0, True, 0, -1
    STATUS = rec[1] if rec[0] == R.R_MSG else NOTE
    NOTE = ''
    if rec[3] & R.F_PURGEHINT:
        STATUS = 'Stored; purge(name) clears it'
    FULL = True
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
    global STATUS, MODE, SEL, HERO, DX, FULL
    D.clear_cache()
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
