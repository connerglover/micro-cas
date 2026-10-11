"""Device line -> source line, from dist/linemap.json (DESIGN 19.3; task M0.4).

    python build/linemap.py CVNODE 123        # the source location and its text
    python build/linemap.py CVNODE:123
    python build/linemap.py --tb [FILE]       # annotate a device traceback (FILE or stdin)
    python build/linemap.py --map PATH ...    # another linemap.json (default dist/linemap.json)
    python build/linemap.py --map dist/release.json CVF00001:8  # release function span

A device error reports only a file and a line. The bundler writes one device line per logical
source line, so each device line maps to a span of source lines (first, last).

linemap.json: {device name: {"src": source path (repo-relative when inside the repo),
"lines": [[first, last], ...]}}, entry i for device line i + 1.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT = os.path.join(ROOT, 'dist', 'linemap.json')

# 'File "CVNODE.py", line 123' (MicroPython) or 'File "CVNODE", line 123'
TB = re.compile(r'File "([A-Za-z][A-Za-z0-9]{0,7})(?:\.py)?", line (\d+)')


def load(path=DEFAULT):
    with open(path, encoding='utf-8') as fh:
        table = json.load(fh)
    return table.get('linemap', table)


def _dev(name):
    name = name.strip()
    if name.lower().endswith('.py'):
        name = name[:-3]
    return name.upper()


def lookup(table, dev, line):
    """(source path, first line, last line) of a device line. KeyError for an unknown
    module, IndexError for a line outside it."""
    ent = table.get(_dev(dev))
    if ent is None:
        raise KeyError('no device module %s in the line map' % _dev(dev))
    lines = ent['lines']
    if not 1 <= line <= len(lines):
        raise IndexError('%s has %d lines, not %d' % (_dev(dev), len(lines), line))
    if lines[line - 1] is None:
        raise KeyError('generated loader code has no source location')
    a, b = lines[line - 1]
    return ent['src'], a, b


def _source(path):
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    try:
        with open(p, encoding='utf-8', errors='replace') as fh:
            return fh.read().splitlines()
    except OSError:
        return None


def describe(table, dev, line):
    """'src/node.py:17' (or ':17-19'), then the source lines."""
    src, a, b = lookup(table, dev, line)
    out = ['%s:%d' % (src, a) if a == b else '%s:%d-%d' % (src, a, b)]
    text = _source(src)
    if text is not None:
        for i in range(a, b + 1):
            if 0 < i <= len(text):
                out.append('  %d: %s' % (i, text[i - 1].rstrip()))
    return '\n'.join(out)


def translate(text, table):
    """Append '  [src:line]' to every traceback line that names a mapped device line."""
    out = []
    for ln in text.split('\n'):
        mo = TB.search(ln)
        if mo is not None:
            try:
                src, a, _ = lookup(table, mo.group(1), int(mo.group(2)))
                ln = '%s  [%s:%d]' % (ln, src, a)
            except (KeyError, IndexError):
                pass
        out.append(ln)
    return '\n'.join(out)


def main(argv=None, out=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = sys.stdout if out is None else out
    path = DEFAULT
    tb = None
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--map' and i + 1 < len(argv):
            path = argv[i + 1]
            i += 2
            continue
        if a == '--tb':
            tb = '-'
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                tb = argv[i + 1]
                i += 1
            i += 1
            continue
        pos.append(a)
        i += 1
    try:
        table = load(path)
    except (OSError, ValueError) as e:
        out.write('error: cannot read %s: %s\n' % (path, e))
        return 1
    if tb is not None:
        if tb == '-':
            text = sys.stdin.read()
        else:
            with open(tb, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
        out.write(translate(text, table))
        return 0
    if len(pos) == 1 and ':' in pos[0]:
        pos = pos[0].rsplit(':', 1)
    if len(pos) != 2 or not pos[1].isdigit():
        out.write(__doc__)
        return 2
    try:
        out.write(describe(table, pos[0], int(pos[1])) + '\n')
    except (KeyError, IndexError) as e:
        out.write('error: %s\n' % (e.args[0] if e.args else e))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
