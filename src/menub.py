#@L 2
# menu helper family. The engine is read from U.R at call time (never imported here).
import ui as U

def entries(cat, tab, prefix):                                 #@L 3
    R = U.R
    out = []
    categories = R.MODS['menu'].CATEGORIES[tab]
    for row in cat:
        hit = False
        for code in row[4]:
            if code in categories:
                hit = True
        if hit and row[0].lower().startswith(prefix):
            out.append(row)
    if tab == 4:
        out.sort()
    return out



def insertion(row):                                           #@L 3
    R = U.R
    prefix = row[1]
    if '(' not in prefix:
        return (prefix, False, len(prefix))
    act = prefix[:-1] in R.MODS['menu'].ACTIONS
    # MathPrint (MATHPRINT.md 3): a command with a template inserts the picker's text, every
    # box empty (diff(,), log(,), integrate(,,,), limit(,,,)); else one empty box per required
    # parameter, never prefilled; apply puts the caret in the first box in drawn order.
    # Classic (8) keeps the required boxes only: diff(,), log().
    for j in range(0 if U.CLASSIC else U.TN):
        t = U.tmpl(j)[1]
        if t.startswith(prefix):
            return (t, act, len(prefix))
    required = row[0].split('(', 1)[1].split('[', 1)[0].rstrip(',)').replace(',...', '')
    return (prefix + ',' * required.count(',') + ')', act, len(prefix))



def recall():                                                 #@L 3
    R = U.R
    rows = []
    if R.ANS is not None:
        rows.append(('Ans', 'Last result: ' + R.ANS, 'ans()'))
    count = 0
    for j in range(len(R.HIST) - 1, -1, -1):
        row = R.HIST[j]
        if row[2] == R.R_ANS:
            rows.append((row[1], row[0], '(' + row[1] + ')'))
            count += 1
            if count == 10:
                break
    for name in sorted(R.VARS):
        rows.append((name + ' = ' + R.VARS[name], 'Stored variable', name))
    for name in sorted(R.FUNCS):
        params, body = R.FUNCS[name]
        rows.append((name + '(' + ','.join(params) + ')', body, name))
    return rows


def apply(choice):                                             #@L 3
    """Put a menu's choice (text, wrap, offset) in the entry (ui.key, MATHPRINT.md 3): a
    wrapping command takes the line (or ans()) as its first argument when only closers follow
    the caret in MathPrint (Classic: the caret at the end); a relation leaves its group first
    and ! wraps a power before it; a call's text is PENDING until its slots are filled."""
    text, wrap, offset = choice
    line, at = U.LINE, U.CUR
    if wrap and (at == len(line) or not U.CLASSIC and not line[at:].strip(')]}')) and \
            (line or U.R.ANS is not None):
        first = line or 'ans()'
        j = text.find('(') + 1
        text = text[:j] + first + text[j:]
        offset += len(first)
        if len(text) > 256:
            U.STATUS = 'Input limit: 256 characters'
            return
        U.LINE, U.CUR = '', 0
    if not U.CLASSIC and not wrap and text in ('=', '!=', '<', '<=', '>', '>='):
        U.leave(0)
    line, at = U.LINE, U.CUR
    if not U.CLASSIC and text == '!':
        line, at = U.wrapend(line, at, 0)   # x^(2)|! is (x^(2))!
    if U.put(line[:at] + text + line[at:], at + offset) and not U.CLASSIC and '(' in text:
        U.PENDING = (at, at + len(text))
