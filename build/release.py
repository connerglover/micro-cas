"""Reproducible, single-file EVO release; no on-device filesystem or custom modules.

The source tree remains normal modules. At build time project module accesses become
native dictionary lookups into exec namespaces. That preserves live globals without
proxy methods or extra arithmetic frames. Bounded code blocks load on demand.
"""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import bundle
import phases
import shrink
import memory_report


INPUT = 'fnpre fnin mclose cutname scan ti_rewrite ti_implicit untok tokens expand_names'.split()
KEEP_PRINT = ('dec10', 'fdec10')
KEEP_DRAW = ('text', 'theme', 'settheme', 'clear_cache')


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('phase hook must occur once: ' + old)
    return source.replace(old, new)


def hooks(sources):
    """Install transitions at frame-safe boundaries, before identifier shrinking."""
    s = sources['CVRUN']
    s = replace(s, 'code,ctx=start(job)', "CVPH.unload('ui')\n  CVPH.unload('print')\n  evict_all()\n  CVPH.load('input')\n  code,ctx=start(job)")
    s = replace(s, 'for k in ks:', "CVPH.unload('input')\n if job[0]=='form':\n  CVPH.load('print')\n for k in ks:")
    s = replace(s, 'rec=PR.record(val,', "top=y=g=None\n    LIVE.clear()\n    del PINNED[:]\n    evict_all()\n    K.RULECACHE.clear()\n    K.TCACHE.clear()\n    K.FCACHE.clear()\n    val=K.keep(K.BASE,val)\n    CVPH.load('print')\n    rec=PR.record(val,")
    s = replace(s, 'K.reset()\n', "K.reset()\n CVPH.unload('input')\n CVPH.unload('print')\n")
    sources['CVRUN'] = 'import CVPH\n' + s
    s = sources['CASEVO']
    s = replace(s, 'U.boot()', "CVPH.load('ui')\nU.boot()")
    s = replace(s, 'a=U.key(k)', "if 'ui' not in CVPH.ACTIVE:\n   if k==22:\n    break\n   CVPH.load('ui')\n  a=U.key(k)")
    s = replace(s, 'U.show(a,r)', "CVPH.load('ui')\n   U.show(a,r)")
    # Panic remains resident and draws a plain screen even when layout cannot load.
    sources['CASEVO'] = 'import CVPH\n' + s
    tables = sorted(shrink._bindings(ast.parse(sources['CVIDENT'])))
    dispatch = ','.join(repr(n.lower()) + ":R.MODS['ident']." + n for n in tables if n.isupper())
    sources['CVRULE'] = replace(sources['CVRULE'],
        "data=getattr(R.MODS[WHERE.get(name,'ident')],name.upper())",
        "if name=='itab':\n  data=R.MODS['itab'].ITAB\n else:\n  data={" + dispatch + '}[name]')
    return sources


def groups(sources):
    result = {}
    for mod in ('CVNODE', 'CVALG', 'CVPARSE', 'CVPRINT', 'CVRUN', 'CVDRAW', 'CVUI'):
        names = [n.name for n in ast.parse(sources[mod]).body if isinstance(n, ast.FunctionDef)]
        spec = {}
        for name in names:
            phase = 'resident'
            if mod == 'CVPARSE' and name in INPUT or mod == 'CVRUN' and name == 'start':
                phase = 'input'
            elif mod == 'CVPRINT' and name not in KEEP_PRINT:
                phase = 'print'
            elif mod == 'CVDRAW' and name not in KEEP_DRAW or mod == 'CVUI' and name not in ('busy', 'panic'):
                phase = 'ui'
            spec.setdefault(phase, []).append(name)
        result[mod] = spec
    return result


def dictionaries(source, modules, seeds=()):
    """Rewrite proven project aliases only; native math/graphics stay native."""
    tree = ast.parse(source)
    aliases, _ = shrink._aliases(tree, set(modules), seeds)
    # Generated CVPH has namespace-valued payloads; run eviction uses module dictionaries.
    edits = []
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def edit(node, text):
        edits.append((offsets[node.lineno-1]+node.col_offset,
                      offsets[node.end_lineno-1]+node.end_col_offset, text))

    def module_value(node):
        return (shrink._module_value(node, aliases) or
                isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'MODS')

    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and len(node.names) == 1 and node.names[0].name in modules:
            a = node.names[0]
            edit(node, (a.asname or a.name) + '=_load(' + repr(a.name) + ')')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'getattr' and module_value(node.args[0]):
            a, b = node.args
            edits.extend(((offsets[node.lineno-1]+node.col_offset, offsets[a.lineno-1]+a.col_offset, ''),
                          (offsets[a.end_lineno-1]+a.end_col_offset, offsets[b.lineno-1]+b.col_offset, '['),
                          (offsets[b.end_lineno-1]+b.end_col_offset, offsets[node.end_lineno-1]+node.end_col_offset, ']')))
        elif isinstance(node, ast.Attribute) and module_value(node.value):
            # Replace the suffix only, so nested MODS[...] attributes can be rewritten too.
            start = offsets[node.end_lineno-1]+node.end_col_offset-len(node.attr)-1
            edits.append((start, offsets[node.end_lineno-1]+node.end_col_offset,
                          '' if node.attr == '__dict__' else '[' + repr(node.attr) + ']'))
    # Nested edits within getattr's argument need their own pass after the call rewrite.
    selected = []
    for e in sorted(edits, key=lambda e: (e[0], -e[1])):
        if not selected or e[0] >= selected[-1][1]:
            selected.append(e)
    for lo, hi, text in reversed(selected):
        source = source[:lo] + text + source[hi:]
    # Loader imports and evictions refer to the archive, never Python's external module path.
    source = source.replace('__import__(DEV[p])', '_load(DEV[p])')
    source = source.replace('sys.modules', '_env')
    return source


def prepare(dist):
    man = bundle.load_manifest()
    result = bundle.bundle(dist=str(dist), man=man)
    if result.errors:
        raise ValueError('\n'.join(result.errors))
    sources = {p.stem: p.read_text('ascii') for p in (dist / 'device').glob('*.py')}
    original = dict(sources)
    source_map = json.loads((dist / 'linemap.json').read_text())
    sources = hooks(sources)
    origins = {}
    for mod, source in sources.items():
        old, new = original[mod].splitlines(), source.splitlines()
        spans = source_map[mod]['lines']
        mapped = []
        for tag, a, b, c, d in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
            mapped.extend(spans[a:b] if tag == 'equal' else [None] * (d-c))
        origins[mod] = mapped
    spec = groups(sources)
    shrunk, mapping = shrink.shrink_sources(sources, reserved=('MODS', 'need', 'DEV'))
    spec = {mod: {phase: [mapping.get(n, n) for n in names] for phase, names in g.items()}
            for mod, g in spec.items()}
    facades, extras, metadata = phases.pack(shrunk, spec)
    allmods = dict(facades, **extras)
    # Payloads are archive blocks directly, without a second CODE string/module.
    for name, info in metadata['payloads'].items():
        allmods[name] = ast.literal_eval(ast.parse(extras[name]).body[0].value)
    controller = allmods['CVPH']
    controller = replace(controller, 'payload=__import__(name)\n  CURRENT=(key,name)\n  exec(payload.CODE,ns)',
                         "CURRENT=(key,name)\n  payload=_decode(_data[name])\n  exec(payload,ns)")
    allmods['CVPH'] = controller
    # Rewrite namespaces after shrinking; dynamic loader source has stable helper names.
    output = {}
    for name, source in allmods.items():
        origin = metadata['payloads'].get(name, {}).get('module', name)
        seeds = shrink._aliases(ast.parse(shrunk.get(origin, source)), set(allmods),
                                (mapping.get('SESS', 'SESS'),) if origin == 'CVPARSE' else ())[0]
        if name == 'CVRUN':
            source = source.replace('__import__(' + mapping.get('DEV','DEV') + '[p])', '_load(' + mapping.get('DEV','DEV') + '[p])')
        if origin == 'CVRUN':
            source = source.replace('.__dict__', '')
        output[name] = dictionaries(source, allmods, seeds)
    metadata['names'] = mapping
    metadata['modules'] = {r[0]: r[1] for r in man.MODULES if r[1] in sources}
    metadata['groups'] = spec
    metadata['levels'] = json.loads((dist / 'levels.json').read_text())
    metadata['linemap'] = {}
    for name in output:
        info = metadata['payloads'].get(name) or metadata['facades'].get(name)
        if info:
            mod = info.get('module', name)
            metadata['linemap'][name] = {'src': source_map[mod]['src'],
                'lines': [origins[mod][i-1] if i is not None else None for i in info['line_map']]}
    metadata['sources'] = {k: len(v.encode('ascii')) for k,v in output.items()}
    return output, metadata


LOADER = '''import gc
_env={}
def _load(name):
 if name in _env:
  return _env[name]
 ns={'__name__':name,'_load':_load,'_env':_env,'_data':_data,'_decode':_decode,'exec':exec}
 _env[name]=ns
 try:
  code=_decode(_data[name])
  exec(code,ns)
 except:
  del _env[name]
  raise
 finally:
  code=None
  gc.collect()
 return ns
'''


def build(dist=ROOT / 'dist'):
    dist = Path(dist)
    output, meta = prepare(dist)
    # codec supplies a self-contained Python 3.4 decoder; each block is independently loaded.
    import codec
    entry = output.pop('CASEVO')
    archive, decoder = codec.encode_blocks(output, storage='bytes')
    code = decoder + '\n_data=' + repr(archive) + '\n' + LOADER + '\n# RUN\n' + entry
    ast.parse(code, feature_version=(3, 4))
    path = dist / 'CASEVO.py'
    path.write_text(code, encoding='ascii', newline='\n')
    meta['file_bytes'] = path.stat().st_size
    meta['archive_bytes'] = sum(len(value) for value in archive.values())
    meta['storage_limit_bytes'] = 3500000
    meta['python_heap_probe_bytes'] = 173360
    meta['device_validation'] = 'pending physical EVO run; total user RAM is not the Python heap'
    if meta['file_bytes'] > meta['storage_limit_bytes']:
        raise ValueError('single file exceeds calculator storage budget')
    meta['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Optional self-contained diagnostic program; CASEVO never imports it.
    probe = bundle.minify((ROOT/'probe/CVTEST.py').read_text()).text
    probe = shrink.transform(probe, meta['names'])
    probe = dictionaries(probe, output)
    probe_code = "import gc\nprint('CVTEST startup heap',gc.mem_free())\n" + decoder + '\n_data=' + repr(archive) + '\n' + LOADER + '\n# RUN\n' + probe
    (dist / 'CVTEST.py').write_text(probe_code, 'ascii', newline='\n')
    ast.parse(probe_code, feature_version=(3, 4))
    sizer = bundle.mpy_sizer()
    if sizer is None:
        raise ValueError('release requires mpy-cross')
    meta['mpy_bytes'] = sizer(str(path))
    meta['probe_mpy_bytes'] = sizer(str(dist/'CVTEST.py'))
    meta['memory_model'] = memory_report.report(dict(output, CASEVO=LOADER + entry),
        meta, archive, decoder, sizer, factor=bundle.load_manifest().FACTOR)
    (dist / 'release.json').write_text(json.dumps(meta, indent=1, sort_keys=True)+'\n', 'ascii', newline='\n')
    (dist / 'INSTALL.md').write_text((ROOT/'docs/INSTALL.md').read_text('utf-8'), 'utf-8', newline='\n')
    checks = []
    for name in ('CASEVO.py', 'CVTEST.py', 'INSTALL.md', 'release.json'):
        checks.append(hashlib.sha256((dist/name).read_bytes()).hexdigest()+'  '+name)
    (dist / 'SHA256SUMS').write_text('\n'.join(checks)+'\n', 'ascii', newline='\n')
    # Inspectable transformed blocks are desktop diagnostics, not required calculator files.
    blockdir = dist / 'blocks'
    blockdir.mkdir(exist_ok=True)
    for name, source in output.items():
        (blockdir / (name+'.py')).write_text(source, 'ascii', newline='\n')
    with zipfile.ZipFile(dist/'cas-evo-v1.zip', 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name in ('CASEVO.py', 'CVTEST.py', 'INSTALL.md', 'release.json', 'SHA256SUMS'):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            package.writestr(info, (dist/name).read_bytes())
    print('Single-file release: %s (%d bytes)' % (path, meta['file_bytes']))
    model = meta['memory_model']
    print('Provisional peak stage: %d bytes before excluded runtime data; known heap: %d' %
          (model['max_estimated_heap_bytes'], model['known_heap_bytes']))
    if not model['fits_known_heap_model']:
        print('HEAP FIT UNRESOLVED: model exceeds the measured Python heap; device test build only.')
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            print('::warning title=Calculator heap fit unresolved::This test build exceeds the provisional model for the measured EVO Python heap. Desktop tests do not establish hardware readiness.')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8', newline='\n') as summary:
            summary.write('## Calculator test build\n\n')
            summary.write('- Single runtime file: `CASEVO.py`, %d bytes.\n' % meta['file_bytes'])
            summary.write('- Model: %d bytes before exclusions; measured free Python heap: %d bytes.\n' %
                          (model['max_estimated_heap_bytes'], model['known_heap_bytes']))
            summary.write('- **Hardware validation pending; heap fit is not established.** See `release.json` and `INSTALL.md`.\n')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT/'dist')
    build(parser.parse_args().dist)
