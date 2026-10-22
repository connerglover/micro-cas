#@L 2
# Modal catalog, TEST, variables, settings and command help. All state is text-only.
# Loaded through R.need('menu') after ui.engine(); the engine is read from U.R at call time.
import ti_system as TS
import ui as U
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
TOP = 22            # first list row; rows are 17 px apart (one 15-row text cell and a gap)
NOTE = 128          # the selected row's explanation: up to 3 lines
FOOT = 192


def open(kind, line='', cur=0, command=''):                     #@L 2
    R = U.R
    cat = R.need('cat').CAT
    tab = TABS.index(kind) if kind in TABS else 0
    selected, prefix, alpha = 0, '', 0
    confirmation = None
    about = False
    helpentry = None
    name = U.ALIAS.get(command, command)
    for row in cat:
        if row[1].rstrip('(') == name:
            helpentry = row
            break
    while True:
        if kind in TABS:
            rows = R.MODS['menub'].entries(cat, tab, prefix)
            title = TABS[tab][0].upper() + TABS[tab][1:] + (' / ' + prefix if prefix else '')
        elif kind == 'vars':
            rows = R.MODS['menub'].varrows()
            title = 'Vars'
        elif kind == 'setup':
            rows = [('Angle: ' + ('DEG' if R.SET['deg'] else 'RAD'), 'ENTER or arrows toggle'),
                    ('Clear history', 'Remove past inputs and results'),
                    ('Clear variables', 'Remove stored variables and functions'),
                    ('About cas-evo', 'Version, timing, memory and loaded modules')]
            title = 'Setup'
        elif kind == 'test':
            rows, title = [], 'TEST'
        else:
            rows, title = [], 'Help'
        selected = min(selected, max(0, len(rows)-1)) if kind != 'test' else selected % len(TEST)
        C = D.COLORS
        D.rect(0, 0, 320, 210, C['BG'])
        D.line(0, 19, 319, 19, C['LINE'])
        D.line(0, 188, 319, 188)
        D.color(C['INK'])
        D.text(title[:31], 5, 2)
        notes = []
        notetop = NOTE
        if confirmation is not None:
            D.text('Clear history?' if confirmation == 1 else 'Clear variables and functions?', 5, 40)
            notes = ['ENTER clears; CLEAR keeps them.']
        elif about:
            D.text('cas-evo 0.1.0 / TI-84 EVO', 5, 40)
            free = R.MEMFREE() if R.MEMFREE is not None else 0
            D.text('Free heap: ' + str(free) + ' bytes', 5, 57)
            D.text('Boot ' + U.secs(U.BOOT_MS) + ', engine ' + U.secs(U.ENGINE_MS), 5, 74)
            notes = D.wrap('Loaded: ' + ', '.join(R.LOADED), 31)
        elif kind == 'test':
            for j in range(len(TEST)):
                D.text(('>' if j == selected else ' ') + str(j+1) + ' ' + TEST[j], 5, TOP + 17*j)
        elif kind == 'help':
            if helpentry is not None:
                D.text(helpentry[0][:31], 5, TOP)
                D.text('Example:', 5, 97)
                for j in range(0, min(93, len(helpentry[3])), 31):
                    D.text(helpentry[3][j:j+31], 5, 114 + j//31*17)
                notes, notetop = D.wrap(helpentry[2], 31), TOP + 17
            else:
                tips = ('ENTER calculate, CLEAR cancel', '2nd ENTER: previous input',
                        'F2 or up: scroll the history', '<- input, -> result; ENTER copy',
                        'F1 menu  F3 setup  F4 forms', 'F5 help  2nd MODE quit',
                        'STO: store a result')
                for j in range(len(tips)):
                    D.text(tips[j], 5, TOP + 17*j)
        else:
            start = selected // PAGE * PAGE
            for j in range(start, min(start+PAGE, len(rows))):
                D.text((' ', '>')[j == selected] + str(j-start+1) + ' ' + rows[j][0][:28], 5, TOP + 17*(j-start))
            if rows:                    # catalog rows explain in [2], the others in [1]
                notes = D.wrap(rows[selected][2 if kind in TABS else 1], 31)
            else:
                D.text('No entries', 5, TOP)
        D.color(C['SUB'])
        for j in range(min(3, len(notes))):
            D.text(notes[j], 5, notetop + 17*j)
        footer = 'ENTER select  CLEAR back'
        if kind in TABS:
            footer = '<> tab  ALPHA find  CLEAR back'
        elif kind == 'help' and helpentry is not None:
            footer = 'ENTER pastes the example'
        D.text(footer, 5, FOOT, C['ACC'])
        key = TS.wait_key()
        if confirmation is not None:
            if key == 105:
                if confirmation == 1:
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
            if key in (24, 26, 25, 34):
                selected = (selected + (1 if key in (26, 34) else -1)) % len(TEST)
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
        elif key == 105 or key in DIGITS or kind == 'setup' and key in (24, 26) and not selected:
            if key in DIGITS:
                selected = selected // PAGE * PAGE + DIGITS[key] - 1
            if selected >= len(rows):
                selected = max(0, len(rows)-1)
                continue
            if kind == 'setup':
                if not selected:
                    R.SET['deg'] = 1 - R.SET['deg']
                elif selected < 3:
                    confirmation = selected     # 1 history, 2 variables
                else:
                    about = True
            elif kind == 'vars':
                text = rows[selected][2]
                return (text, False, len(text))
            elif rows:
                return R.MODS['menub'].insertion(rows[selected])
