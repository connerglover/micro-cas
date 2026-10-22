#@L 2
# menu helper family. The engine is read from U.R at call time (never imported here).
import ui as U
import draw as D

def entries(cat, tab, prefix):                                 #@L 3
    """The rows of tab whose name or insertion text starts with the find prefix: name matches
    first, then the others (su: Sum, then surd's Nth Root); the All tab sorted by name."""
    R = U.R
    out = []
    more = []
    categories = R.MODS['menu'].CATEGORIES[tab]
    for row in cat:
        hit = False
        for code in row[4]:
            if code in categories:
                hit = True
        if hit and row[0].lower().startswith(prefix):
            out.append(row)
        elif hit and row[1].startswith(prefix):
            more.append(row)
    if tab == 4:
        for rows in (out, more):
            keyed = []
            for row in rows:
                keyed.append((row[0].lower(), row))
            keyed.sort()
            for j in range(len(keyed)):
                rows[j] = keyed[j][1]
    return out + more



def insertion(row):                                           #@L 3
    R = U.R
    prefix = row[1]
    if '(' not in prefix:
        return (prefix, False, len(prefix))
    act = prefix[:-1] in R.MODS['menu'].ACTIONS
    # MathPrint (MATHPRINT.md 3): a command with a template inserts the picker's text, every
    # box empty (diff(,), log(,), integrate(,,,), limit(,,,)); any other one its boxed count
    # from draw.ARGS (the required arguments and the optional ones worth filling, QPL Q4:
    # solve(,), taylor(,,), riemann(,,,,,)), never prefilled; apply puts the caret in the
    # first box in drawn order.
    for j in range(U.TN):
        t = U.tmpl(j)[1]
        if t.startswith(prefix):
            return (t, act, len(prefix))
    n = 1
    i = D.ARGS.find(';' + prefix[:-1] + ':')
    if i >= 0:
        n = int(D.ARGS[i + len(prefix) + 2])
    return (prefix + ',' * (n - 1) + ')', act, len(prefix))



def varrows():                                                 #@L 3
    """The vars key's rows: Ans, the stored variables and the functions (the history scrolls
    on the page itself: up)."""
    R = U.R
    rows = []
    if R.ANS is not None:
        rows.append(('Ans', 'Last result: ' + R.ANS, 'ans()'))
    for name in sorted(R.VARS):
        rows.append((name + ' = ' + R.VARS[name], 'Stored variable', name))
    for name in sorted(R.FUNCS):
        params, body = R.FUNCS[name]
        rows.append((name + '(' + ','.join(params) + ')', body, name))
    return rows


def apply(choice):                                             #@L 3
    """Put a menu's choice (text, wrap, offset) in the entry (ui.key, MATHPRINT.md 3): a
    wrapping command takes the line (or ans()) as its first argument when only closers follow
    the caret; a relation leaves its group first
    and ! wraps a power before it; a call's text is PENDING until its slots are filled."""
    text, wrap, offset = choice
    line, at = U.LINE, U.CUR
    if wrap and not line[at:].strip(')]}') and (line or U.R.ANS is not None):
        first = line or 'ans()'
        j = text.find('(') + 1
        text = text[:j] + first + text[j:]
        offset += len(first)
        if len(text) > 256:
            U.STATUS = 'Input limit: 256 characters'
            return
        U.LINE, U.CUR = '', 0
    if not wrap and text in ('=', '!=', '<', '<=', '>', '>='):
        U.leave(0)
    line, at = U.LINE, U.CUR
    if text == '!':
        line, at = U.wrapend(line, at, 0)   # x^(2)|! is (x^(2))!
    if U.put(line[:at] + text + line[at:], at + offset) and '(' in text:
        U.PENDING = (at, at + len(text))
