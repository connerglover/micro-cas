"""Reproducible EVO release: a few cached library packs plus one RAM launcher.

docs/notes/FASTBOOT.md explains the design. build/bundle.py turns src/ into device modules;
build/packs.py merges them into packs (build/manifest.py PACKS); build/shrink.py shortens
identifiers. The run module receives the loader tables it needs on the calculator: the pack of
every runtime key, the soft/view/aux packs, and heap estimates measured from compiled sizes.

Outputs in DIST: the pack sources (CAS*.py), the RAM launcher CAS.py, release.json (names,
packs, levels and a source line map), SHA256SUMS, INSTALL.md and the build input
cas-evo-packs.zip for build/archive.py. The diagnostic probe CVTEST (probe/CVTEST.py, shrunk
with the same mapping) goes to DIST/dev/CVTEST.py for the native CI checks only: it is not a
release file and never ships (release.json records it under devtools). Nothing here runs on
the calculator.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import archive
import bundle
import packs
import shrink
import transfer


RESERVED = ('MODS', 'need', 'DEV')
PACKAGE = 'cas-evo-packs.zip'
PROBE_PREFIX = "import gc\nprint('CVTEST startup heap',gc.mem_free())\n"
DEVPROBE = 'dev/CVTEST.py'          # developer/CI only; not in files, launchers or any ZIP


def invalidate(dist):
    """Discard only known generated release outputs; never leave a stale download."""
    names = {'CAS.py', 'CASEVO.py', 'CVTEST.py', DEVPROBE, PACKAGE, 'cas-evo-v1.zip',
             'cas-evo-development.zip', 'release.json', 'SHA256SUMS', 'INSTALL.md',
             'transfer-check.json'}
    previous = dist / 'release.json'
    if previous.is_file():
        meta = json.loads(previous.read_text('ascii'))
        for name in meta.get('files', {}):
            if not re.fullmatch(r'[A-Z][A-Z0-9]{0,7}\.py', name):
                raise ValueError('unsafe previous release filename: ' + name)
            names.add(name)
    for name in sorted(names):
        path = dist / name
        if path.is_file():
            path.unlink()


def _shrunk(pack_sources, clients, entry, seeds=None):
    """Minify and shrink every pack, the entry client and (as an extra source) CVTEST."""
    sources = dict((name, bundle.minify(text).text) for name, text in pack_sources.items())
    sources[entry] = bundle.minify(clients[entry]).text
    probe = bundle.minify(clients['CVTEST']).text
    out, mapping = shrink.shrink_sources(sources, reserved=RESERVED, reuse=True,
                                         local_names=True, extra_sources=(probe,), seeds=seeds)
    return out, mapping, shrink.transform(probe, mapping, allow_reuse=True)


def _sizes(sources, sizer, man):
    with tempfile.TemporaryDirectory(prefix='cas-evo-packs-') as temp:
        out = {}
        for name in sorted(sources):
            path = Path(temp) / (name + '.py')
            path.write_text(sources[name], 'ascii', newline='\n')
            out[name] = sizer(str(path), archive.mpy_flags(man, name))
        return out


def _levels(man, meta, mapping, dist):
    """{pack: {final function name: level}} for the desktop depth checker."""
    table = json.loads((dist / 'levels.json').read_text('ascii'))
    out = {}
    for device, rows in table.items():
        if device not in meta['owner']:
            continue
        for fn, level in rows.items():
            renamed = meta['renames'].get('%s.%s' % (device, fn), fn)
            pack = meta['place'].get('%s.%s' % (device, fn), meta['owner'][device])
            out.setdefault(pack, {})[mapping.get(renamed, renamed)] = level
    return out


def _linemap(final, meta, dist):
    """Each pack line -> [first, last, source file] of the source statement it came from."""
    device = json.loads((dist / 'linemap.json').read_text('ascii'))
    out = {}
    for pack, text in final.items():
        body = ast.parse(text).body
        origins = meta['statements'][pack]
        if len(body) != len(origins):
            raise ValueError('%s: statements changed after merging' % pack)
        lines = [None] * len(text.splitlines())
        for stmt, origin in zip(body, origins):
            if origin is None:
                continue
            module, first, last = origin
            spans = [s for s in device[module]['lines'][first - 1:last] if s]
            if not spans:
                continue
            entry = [min(s[0] for s in spans), max(s[1] for s in spans), device[module]['src']]
            for i in range(stmt.lineno - 1, stmt.end_lineno):
                lines[i] = entry
        out[pack] = {'src': None, 'lines': lines, 'granularity': 'source-statement-span'}
    return out


def prepare(dist, man=None):
    """Bundle, merge and shrink. Returns (files {name: text}, metadata)."""
    man = man or bundle.load_manifest()
    result = bundle.bundle(dist=str(dist), man=man)
    if result.errors:
        raise ValueError('\n'.join(result.errors))
    device = dict((p.stem, p.read_text('ascii')) for p in (dist / 'device').glob('*.py'))
    entry = man.ENTRY[1]
    clients = {entry: device.pop(entry),
               'CVTEST': (ROOT / 'probe/CVTEST.py').read_text('ascii')}
    pack_sources, client_sources, meta = packs.merge(device, man, clients)
    runpack = meta['owner']['CVRUN']
    # parse.SESS holds the run module (set by ui.engine and CVTEST): command dispatch through
    # it is a registry lookup, as in v1's explicit seed.
    seeds = {meta['owner']['CVPARSE']: {meta['renames'].get('CVPARSE.SESS', 'SESS')}}
    sizer = bundle.mpy_sizer()
    if sizer is None:
        raise ValueError('the release needs mpy-cross to measure pack sizes')
    shrunk, mapping, probe = _shrunk(pack_sources, client_sources, entry, seeds)
    sizes = _sizes(dict((k, v) for k, v in shrunk.items() if k != entry), sizer, man)
    rows = man.rows()
    family = {}
    for key in man.PARTS:
        family[key] = meta['owner'][rows[man.src_of(key)][1]]
    factor, fixed = man.PACKCOST
    cost = packs.costs(meta, family, sizes, factor, fixed)
    factor, fixed = man.ROOMCOST
    room = dict((phase, (pack, int(sizes[pack] * factor) + fixed))
                for phase, pack in sorted(man.ROOMS.items()))
    pack_sources[runpack] = packs.loader_tables(pack_sources[runpack], {
        'COST': cost, 'ROOM': room, 'SHEDAT': man.SHEDAT})
    shrunk, mapping, probe = _shrunk(pack_sources, client_sources, entry, seeds)
    final = dict((k, v) for k, v in shrunk.items() if k != entry)
    sizes = _sizes(final, sizer, man)
    for pack, size in sizes.items():
        if size > man.PACKMAX:
            raise ValueError('%s compiles to %d bytes, over PACKMAX %d' % (pack, size, man.PACKMAX))
    files = dict((name + '.py', text) for name, text in final.items())
    files[entry + '.py'] = shrunk[entry]
    files[DEVPROBE] = PROBE_PREFIX + probe
    for name, text in files.items():
        text.encode('ascii')
        ast.parse(text, filename=name, feature_version=(3, 4))
    meta.update({
        'format': 'packs-v1',
        'release': man.VERSION,
        'names': mapping,
        'modules': dict((r[0], r[1]) for r in man.MODULES if r[1] in meta['owner']),
        'levels': _levels(man, meta, mapping, dist),
        'linemap': _linemap(final, meta, dist),
        'cost': cost, 'room': room, 'mpy_estimate': sizes,
        'launchers': [entry + '.py'],
    })
    return files, meta


def build(dist=ROOT / 'dist'):
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    invalidate(dist)
    man = bundle.load_manifest()
    files, meta = prepare(dist, man)
    data = dict((name, text.encode('ascii')) for name, text in sorted(files.items()))
    dev = dict((name, data.pop(name)) for name in list(data) if name.startswith('dev/'))
    launchers = dict((name, data[name]) for name in meta['launchers'])
    # The probe still fits the converter (a developer may send it); it is not a launcher.
    checked = dict(launchers, **dict((name.split('/')[-1], blob) for name, blob in dev.items()))
    checks = dict((name, transfer.inspect_source(blob, name)) for name, blob in checked.items())
    meta['transfer_check'] = {'converter_version': transfer.CONVERTER_VERSION,
        'fits_converter_limit': all(c['fits_converter_limit'] for c in checks.values()),
        'files': checks, 'physical_transfer_verified': False}
    (dist / 'transfer-check.json').write_text(
        json.dumps(meta['transfer_check'], indent=2) + '\n', 'ascii', newline='\n')
    transfer.require_transferable(checked)
    meta['files'] = dict((name, {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()})
                         for name, blob in sorted(data.items()))
    meta['total_source_bytes'] = sum(len(blob) for blob in data.values())
    meta['devtools'] = dict((name.split('/')[-1], {'path': name, 'bytes': len(blob),
                                                   'sha256': hashlib.sha256(blob).hexdigest()})
                            for name, blob in sorted(dev.items()))
    meta['device_validation'] = 'pending physical EVO run; total user RAM is not the Python heap'
    for name, blob in list(data.items()) + list(dev.items()):
        (dist / name).parent.mkdir(parents=True, exist_ok=True)
        (dist / name).write_bytes(blob)
    (dist / 'release.json').write_text(json.dumps(meta, indent=1, sort_keys=True) + '\n',
                                       'ascii', newline='\n')
    (dist / 'INSTALL.md').write_text((ROOT / 'docs/INSTALL.md').read_text('utf-8'), 'utf-8',
                                     newline='\n')
    members = sorted(data) + ['INSTALL.md', 'release.json']
    sums = [hashlib.sha256((dist / name).read_bytes()).hexdigest() + '  ' + name
            for name in members]
    (dist / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', 'ascii', newline='\n')
    with zipfile.ZipFile(dist / PACKAGE, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name in members + ['SHA256SUMS']:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            package.writestr(info, (dist / name).read_bytes())
    kinds = meta['kinds']
    print('Packs: %s' % ', '.join('%s (%s, ~%d B)' % (p, kinds[p], meta['mpy_estimate'][p])
                                  for p in sorted(meta['mpy_estimate'])))
    print('Launcher: %s; passes the TI Connect Evo converter size gate. Developer probe %s '
          '(not shipped): %d B.' % (', '.join('%s %d B' % (n, len(launchers[n])) for n in sorted(launchers)),
                                    DEVPROBE, sum(len(b) for b in dev.values())))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8', newline='\n') as summary:
            summary.write('## Pack build\n\n')
            summary.write('- %d packs and 1 launcher; packs compile to %d bytes (mpy-cross '
                          'estimate).\n' % (len(meta['mpy_estimate']), sum(meta['mpy_estimate'].values())))
            summary.write('- Download `cas-evo-calculator.zip` or use `cas-evo-web-installer`; '
                          'this intermediate source build is not installed directly.\n')
            summary.write('- Physical calculator validation pending. See `INSTALL.md`.\n')
    return dist / (man.ENTRY[1] + '.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    build(args.dist)
