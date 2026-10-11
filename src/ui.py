#@L 2
# Calculator editor, history and the 320x210 application shell.
import gc
import ti_system as TS
import ti_graphics as G
import node as K
import parse as P
import run as R
import draw as D

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
PLAIN = {32:'x', 51:'^-1', 52:'sin(', 53:'cos(', 54:'tan(', 55:'^', 61:'^2',
         62:',', 63:'(', 64:')', 65:'/', 71:'log(', 72:'7', 73:'8', 74:'9',
         75:'*', 81:'ln(', 82:'4', 83:'5', 84:'6', 85:'-', 91:'=>',
         92:'1', 93:'2', 94:'3', 95:'+', 102:'0', 103:'.', 104:'-'}
SECOND = {32:'t', 52:'asin(', 53:'acos(', 54:'atan(', 55:'pi', 61:'sqrt(',
          62:'E', 63:'{', 64:'}', 65:'e', 71:'10^(', 75:'[', 81:'e^(',
          85:']', 103:'i', 104:'ans()'}
ALPHA = {32:'theta', 41:'a', 42:'b', 43:'c', 51:'d', 52:'e', 53:'f', 54:'g',
         55:'h', 61:'i', 62:'j', 63:'k', 64:'l', 65:'m', 71:'n', 72:'o',
         73:'p', 74:'q', 75:'r', 81:'s', 82:'t', 83:'u', 84:'v', 85:'w',
         91:'x', 92:'y', 93:'z', 94:'theta', 102:' ', 103:"'"}


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
    global LINE, CUR, MODE, STATUS, HERO, DX
    if len(LINE) + len(text) > 256:
        STATUS = 'Input limit: 256 characters'
        return
    LINE = LINE[:CUR] + text + LINE[CUR:]
    CUR += len(text) if offset is None else offset
    MODE, STATUS, HERO, DX = 0, '', not LINE, 0


def wrapped(text):                                             #@L 3
    atom = bool(text)
    for c in text:
        if not (c.isalpha() or c.isdigit() or c == '.'):
            atom = False
    if atom:
        return text
    return '(' + text + ')'


def empty_slot():                                              #@L 3
    for token in ('(,', ',,', ',)'):
        i = LINE.find(token)
        if i >= 0:
            return i + 1
    i = LINE.find('()')
    while i >= 0:
        j = i
        while j and (LINE[j-1].isalpha() or LINE[j-1].isdigit()):
            j -= 1
        name = R.ALIAS.get(LINE[j:i], LINE[j:i])
        if name in R.HINT or name in P.FNAMES:
            return i + 1
        i = LINE.find('()', i + 2)
    if LINE and LINE[-1] in '+-*/^,(=':
        return len(LINE)
    return -1


def redraw():                                                  #@L 2
    global XOFF
    D.settheme(R.SET['theme'])
    G.setColor(*D.COLORS['BG'])
    G.fillRect(0, 0, 320, 210)
    G.setColor(*D.COLORS['INK'])
    D.text('DEG' if R.SET['deg'] else 'RAD', 5, 1, True)
    D.text(STATUS[:35], 35, 1, True)
    D.text(('', '2nd', 'a', 'a-lock', 'A-LOCK')[MOD], 276, 1, True)
    if R.HIST:
        idx = SEL if MODE else len(R.HIST) - 1
        e = R.HIST[idx]
        if (not LINE and HERO) or MODE:
            D.text(e[0][:49], 8, 17, True)
            if e[2] == R.R_ANS:
                box = D.layout(e[1], 300, 110)
                D.paint(box, 10 + max(0, (300 - box['w']) // 2), 33, DX, 0)
                label = e[5][-1][0] if e[5] else 'exact'
                footer = ('+ C   ' if e[4] & R.F_PLUSC else '') + label + '  F4'
                if e[3] is not None and label == 'exact':
                    footer = '~ ' + str(e[3]) + '   ' + footer
                D.text(footer[:49], 8, 145, True)
            else:
                D.text(e[1][:49], 8, 69, True)
        else:
            first = max(0, len(R.HIST) - 3)
            for i in range(first, len(R.HIST)):
                e = R.HIST[i]
                y = 17 + (i - first) * 46
                D.text(e[0][:49], 8, y, True)
                box = D.layout(e[1], 300, 31)
                D.paint(box, 10 + max(0, 300-box['w']), y+12, 0, 0)
    else:
        D.text('cas-evo', 110, 48)
        D.text('Exact algebra and calculus', 82, 82, True)
        D.text('Type an expression or press menu', 64, 102, True)
    name = enclosing()
    hint = R.HINT.get(R.ALIAS.get(name, name), '')
    G.setColor(*D.COLORS['SUB'])
    D.text(hint[:51], 5, 158, True, D.COLORS['SUB'])
    G.setColor(*D.COLORS['LINE'])
    G.drawLine(0, 169, 319, 169)
    XOFF = max(0, min(XOFF, CUR))
    if CUR - XOFF > 36:
        XOFF = CUR - 36
    G.setColor(*D.COLORS['INK'])
    D.text(LINE[XOFF:XOFF+38], 6, 173)
    G.setColor(*D.COLORS['ACC'])
    G.drawLine(6+(CUR-XOFF)*8, 172, 6+(CUR-XOFF)*8, 188)
    for i in range(5):
        G.setColor(*D.COLORS['ACCSOFT'])
        G.fillRect(i*64, 190, 63, 20)
        G.setColor(*D.COLORS['ACC'])
        D.text(('menu', 'recall', 'setup', 'forms', 'help')[i], i*64+12, 194, True, D.COLORS['ACC'])


def boot():                                                    #@L 1
    P.SESS = R
    K.ESC = TS.escape
    if hasattr(gc, 'mem_free'):
        K.MEMFREE = R.MEMFREE = gc.mem_free
    R.BUSY = busy
    redraw()


def busy(steps):                                               #@L 2
    G.setColor(*D.COLORS['BG'])
    G.fillRect(35, 0, 235, 13)
    G.setColor(*D.COLORS['ACC'])
    D.text('Calculating' + '.' * (1 + (steps // 512) % 3), 35, 1, True)


def key(k):                                                    #@L 1
    global LINE, CUR, MOD, MODE, SEL, HERO, DX, ENTRYPOS, LASTENTRY, STATUS
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
    elif k in (25, 34) and R.HIST:
        d = (-5 if mod == 1 else -1) if k == 25 else (5 if mod == 1 else 1)
        if not MODE and k == 25:
            MODE, SEL = 1, len(R.HIST)-1
        elif MODE:
            SEL = max(0, SEL+d)
            if SEL >= len(R.HIST):
                MODE, SEL = 0, len(R.HIST)-1
        DX = 0
    elif k == 105:
        if MODE:
            e = R.HIST[SEL]
            insert(e[0] if mod == 1 else wrapped(e[1]))
        elif mod == 1:
            if R.HIST:
                ENTRYPOS = min(ENTRYPOS+1, len(R.HIST)-1) if LINE == LASTENTRY else 0
                LINE = R.HIST[-1-ENTRYPOS][0]
                CUR = len(LINE)
                LASTENTRY = LINE
        else:
            pos = empty_slot()
            if pos >= 0:
                CUR, STATUS = pos, 'fill in the empty slot'
            elif LINE or R.HIST:
                job = ('eval', LINE or R.HIST[-1][0])
    elif k == 14 and R.HIST:
        idx = SEL if MODE else len(R.HIST)-1
        if R.HIST[idx][2] == R.R_ANS:
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
        choice = R.need('menu').open(kind, LINE, CUR, enclosing()) #@calls 2
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
            if not LINE and R.ANS is not None and k in (51, 55, 61, 65, 75, 85, 91, 95) and mod == 0:
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
    global LINE, CUR, MODE, HERO, DX, STATUS, ENTRYPOS
    if job[0] == 'eval':
        LINE, CUR, MODE, HERO, DX, ENTRYPOS = '', 0, 0, True, 0, -1
    STATUS = rec[1] if rec[0] == R.R_MSG else ''
    if rec[3] & R.F_PURGEHINT:
        STATUS = 'Stored; purge(name) clears it'
    redraw()


def panic(reason):                                             #@L 1
    global STATUS, MODE, SEL, HERO, DX
    D.clear_cache()
    gc.collect()
    STATUS = ('Out of memory', 'Interrupted', 'Expression too complex', 'Display error')[reason]
    D.settheme(R.SET['theme'])
    G.setColor(*D.COLORS['BG'])
    G.fillRect(0, 0, 320, 210)
    D.text(STATUS, 8, 1, True)
    if R.HIST:
        idx = SEL if MODE and 0 <= SEL < len(R.HIST) else len(R.HIST) - 1
        e = R.HIST[idx]
        D.text(e[0][:49], 8, 27, True, D.COLORS['SUB'])
        text = e[1]
        D.text(text[:46] + '...' if len(text) > 49 else text, 8, 53, True)
    MODE, SEL, HERO, DX = 0, -1, False, 0
    G.setColor(*D.COLORS['LINE'])
    G.drawLine(0, 169, 319, 169)
    offset = max(0, CUR - 36)
    D.text(LINE[offset:offset+38], 6, 173)
    D.text('CLEAR edits; 2nd MODE quits', 8, 194, True, D.COLORS['SUB'])
