#@L 2
# Modal catalog, TEST, recall, settings and command help. All state is text-only.
import ti_system as TS
import ti_graphics as G
import run as R
import draw as D

TABS = ('algebra', 'calculus', 'trig', 'more', 'all')
CATEGORIES = ('A', 'C', 'T', 'SDVNF', 'ACTSDVNF')
ACTIONS = ('solve', 'factor', 'expand', 'simplify', 'partfrac', 'integrate', 'diff', 'limit', 'taylor')
TEST = ('=', '!=', '<', '<=', '>', '>=', '!')
DIGITS = {92: 1, 93: 2, 94: 3, 82: 4, 83: 5, 84: 6, 72: 7, 73: 8, 74: 9}
ALPHA = {41:'a',42:'b',43:'c',51:'d',52:'e',53:'f',54:'g',55:'h',61:'i',62:'j',
         63:'k',64:'l',65:'m',71:'n',72:'o',73:'p',74:'q',75:'r',81:'s',82:'t',
         83:'u',84:'v',85:'w',91:'x',92:'y',93:'z'}
PAGE = 6


def open(kind, line='', cur=0, command=''):                     #@L 2
    cat = R.need('cat').CAT
    tab = TABS.index(kind) if kind in TABS else 0
    selected, prefix, alpha = 0, '', 0
    confirmation = None
    about = False
    helpentry = None
    name = R.ALIAS.get(command, command)
    for row in cat:
        if row[0].split('(')[0] == name:
            helpentry = row
            break
    while True:
        if kind in TABS:
            rows = R.MODS['menub'].entries(cat, tab, prefix)
            title = TABS[tab][0].upper() + TABS[tab][1:] + (' / ' + prefix if prefix else '')
        elif kind == 'recall':
            rows = R.MODS['menub'].recall()
            title = 'Recall'
        elif kind == 'setup':
            rows = [('Angle: ' + ('DEG' if R.SET['deg'] else 'RAD'), 'ENTER or arrows to toggle'),
                    ('Theme: ' + ('Night' if R.SET['theme'] else 'Paper'), 'ENTER or arrows to toggle'),
                    ('Clear history', 'Remove past inputs and results'),
                    ('Clear variables', 'Remove stored variables and functions'),
                    ('About cas-evo', 'Version, memory and loaded modules')]
            title = 'Setup'
        elif kind == 'test':
            rows, title = [], 'TEST'
        else:
            rows, title = [], 'Help'
        selected = min(selected, max(0, len(rows)-1)) if kind != 'test' else selected % len(TEST)
        G.setColor(*D.COLORS.get('BG', D.PALETTES[0][0]))
        G.fillRect(0, 0, 320, 210)
        D.text(title[:37], 8, 4)
        if confirmation is not None:
            D.text('Clear history?' if confirmation == 2 else 'Clear variables and functions?', 8, 45, True)
            D.text('ENTER confirms; CLEAR keeps them.', 8, 73, True)
        elif about:
            D.text('cas-evo v1 / TI-84 EVO', 8, 42, True)
            free = R.MEMFREE() if R.MEMFREE is not None else 0
            D.text('Free heap: ' + str(free) + ' bytes', 8, 66, True)
            D.text('Loaded: ' + ', '.join(R.LOADED)[:41], 8, 90, True)
        elif kind == 'test':
            for j in range(len(TEST)):
                D.text(('>' if j == selected else ' ') + str(j+1) + ':' + TEST[j], 8 + j*44, 55, True)
        elif kind == 'help':
            if helpentry is not None:
                D.text(helpentry[0][:50], 8, 35, True)
                for j in range(0, len(helpentry[2]), 49):
                    D.text(helpentry[2][j:j+49], 8, 58 + j//49*15, True)
                D.text('Example:', 8, 106, True)
                for j in range(0, min(147, len(helpentry[3])), 49):
                    D.text(helpentry[3][j:j+49], 8, 126 + j//49*15, True)
            else:
                tips = ('ENTER: calculate   CLEAR: cancel', '2nd ENTER: previous input',
                        'Up/down: browse history', 'F1 menu  F2 recall  F3 setup',
                        'F4 alternate forms  F5 help', '2nd MODE: quit   STO: store')
                for j in range(len(tips)):
                    D.text(tips[j], 8, 36 + 23*j, True)
        else:
            start = selected // PAGE * PAGE
            for j in range(start, min(start+PAGE, len(rows))):
                y = 34 + (j-start)*25
                D.text(('> ' if j == selected else '  ') + str(j-start+1) + ' ' + rows[j][0][:46], 8, y, True)
                D.text(rows[j][1][:49], 20, y+12, True, D.COLORS.get('SUB', D.PALETTES[0][2]))
            if not rows:
                D.text('No entries', 8, 48, True)
        footer = 'ENTER select / CLEAR back'
        if kind in TABS:
            footer = '< > tabs / ALPHA search / CLEAR back'
        D.text(footer, 8, 193, True)
        key = TS.wait_key()
        if confirmation is not None:
            if key == 105:
                if confirmation == 2:
                    del R.HIST[:]
                else:
                    R.VARS.clear()
                    R.FUNCS.clear()
                confirmation = None
            elif key in (45, 11):
                confirmation = None
            continue
        if about:
            if key in (105, 45, 11):
                about = False
            continue
        if key in (45, 11):
            return None
        if kind == 'help':
            if key == 105:
                return None if helpentry is None else (helpentry[3], False, len(helpentry[3]))
            continue
        if kind == 'test':
            if key in (24, 26):
                selected = (selected + (1 if key == 26 else -1)) % len(TEST)
            elif key == 105 or key in DIGITS and DIGITS[key] <= len(TEST):
                index = selected if key == 105 else DIGITS[key] - 1
                return (TEST[index], False, len(TEST[index]))
            continue
        if kind in TABS and key == 31:
            alpha = 2 if alpha == 1 else 1
            continue
        if kind in TABS and alpha and key in ALPHA:
            prefix += ALPHA[key]
            selected = 0
            alpha = 0 if alpha == 1 else alpha
            continue
        if kind in TABS and key == 23:
            prefix, selected = prefix[:-1], 0
        elif key in (25, 34) and rows:
            selected = (selected + (1 if key == 34 else -1)) % len(rows)
        elif key in (24, 26) and kind in TABS:
            tab = (tab + (1 if key == 26 else -1)) % len(TABS)
            prefix, selected = '', 0
        elif key == 105 or key in DIGITS or (kind == 'setup' and key in (24, 26)):
            if key in DIGITS:
                selected = selected // PAGE * PAGE + DIGITS[key] - 1
            if selected >= len(rows):
                selected = max(0, len(rows)-1)
                continue
            if kind == 'setup':
                if selected < 2:
                    setting = 'deg' if selected == 0 else 'theme'
                    R.SET[setting] = 1 - R.SET[setting]
                    D.theme(R.SET['theme'])
                elif selected in (2, 3):
                    confirmation = selected
                else:
                    about = True
            elif kind == 'recall':
                text = rows[selected][2]
                return (text, False, len(text))
            elif rows:
                return R.MODS['menub'].insertion(rows[selected])
