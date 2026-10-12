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
    required = row[0].split('(', 1)[1].split('[', 1)[0].rstrip(',)').replace(',...', '')
    text = prefix + ',' * required.count(',') + ')'
    return (text, prefix[:-1] in R.MODS['menu'].ACTIONS, len(prefix))



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
