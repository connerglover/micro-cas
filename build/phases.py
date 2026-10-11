"""Split minified device definitions into bounded, explicitly loaded source payloads.

``pack(sources, groups)`` returns (facades, extra_modules, metadata).  Sources use
device module names, without ``.py``; groups map module -> phase -> function names.
The reserved ``resident`` group loads immediately at each original definition
position. Other groups load only through CVPH.load(phase), in original module and
definition order. Callers must select phase boundaries that leave no live frames,
default arguments, tables, or other aliases holding the definitions being evicted.

This is a desktop build helper. The generated controller uses the verified device
``exec(source, namespace)`` primitive, never a forwarding function around CAS APIs.
CVPH.MEMFREE is an optional native-compatible heap hook; CVPH.CURRENT identifies the
payload during exec, so the desktop harness can inject an exec with named code.
Metadata records actual payload sizes, including indivisible oversize functions.
"""
import ast
import re


_DEVICE = re.compile(r'^[A-Z][A-Z0-9]{0,7}$')
_CONTROLLER = '''import gc
import sys
REG={}
ACTIVE={}
MEMFREE=None
CURRENT=None
PHASES=@PHASES@
def register(key,namespace): #@L 2
 REG[key]=namespace
def part(key,name,names,required,resident=False): #@L 3
 global CURRENT
 ns=REG[key]
 payload=None
 try:
  gc.collect()
  free=gc.mem_free() if MEMFREE is None else MEMFREE()
  if free<required:
   raise MemoryError('phase compile memory')
  payload=__import__(name)
  CURRENT=(key,name)
  exec(payload.CODE,ns)
 except:
  for fn in names:
   if fn in ns:
    del ns[fn]
  if resident:
   del REG[key]
  raise
 finally:
  CURRENT=None
  payload=None
  if name in sys.modules:
   del sys.modules[name]
  gc.collect()
def load(phase): #@L 2
 if phase in ACTIVE:
  return
 parts=PHASES[phase]
 required=0
 for item in parts:
  if item[0] not in REG:
   raise KeyError(item[0])
  required=max(required,item[3])
 gc.collect()
 free=gc.mem_free() if MEMFREE is None else MEMFREE()
 if free<required:
  raise MemoryError('phase compile memory')
 try:
  for item in parts:
   part(item[0],item[1],item[2],item[3])
 except:
  for item in parts:
   ns=REG[item[0]]
   for fn in item[2]:
    if fn in ns:
     del ns[fn]
  gc.collect()
  raise
 ACTIVE[phase]=True
def unload(phase): #@L 2
 if phase not in ACTIVE:
  return
 for item in PHASES[phase]:
  ns=REG[item[0]]
  for fn in item[2]:
   if fn in ns:
    del ns[fn]
 del ACTIVE[phase]
 gc.collect()
'''


def _functions(module, tree, groups):
    """Validate explicit ownership; extract only ordinary top-level definitions."""
    definitions = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name in definitions:
                raise ValueError('%s: duplicate function %s' % (module, node.name))
            definitions[node.name] = node
    owners = {}
    for phase in sorted(groups):
        if not isinstance(phase, str) or not phase:
            raise ValueError('%s: phase must be a nonempty string' % module)
        for name in groups[phase]:
            if name not in definitions:
                raise ValueError('%s: unknown function %s' % (module, name))
            if name in owners:
                raise ValueError('%s.%s: multiple phases' % (module, name))
            node = definitions[name]
            if node.decorator_list:
                raise ValueError('%s.%s: decorated definitions cannot be phased' %
                                 (module, name))
            owners[name] = phase
    return definitions, owners


def _chunks(definitions, target_lines):
    """Pack whole functions; an oversize function gets its own honest-size chunk."""
    chunk, count = [], 0
    for node in definitions:
        size = node.end_lineno - node.lineno + 1
        if chunk and count + size > target_lines:
            yield chunk
            chunk, count = [], 0
        chunk.append(node)
        count += size
        if count >= target_lines:
            yield chunk
            chunk, count = [], 0
    if chunk:
        yield chunk


def pack(sources, groups, target_lines=120):
    """Build source facades, CVPH/CVP payload sources, and precise origin metadata.

    ``metadata['payloads'][name]`` includes module, phase, functions, source_lines,
    source_bytes, required_free, oversize, and line_map (payload line -> input
    module line). ``metadata['facades'][module]['line_map']`` maps rewritten lines
    back to input lines; generated registration lines have no origin (None).
    Input is already minified and import-renamed. No files are written here.
    """
    if isinstance(target_lines, bool) or not isinstance(target_lines, int) or target_lines < 1:
        raise ValueError('target_lines must be a positive integer')
    if 'CVPH' in sources:
        raise ValueError('CVPH is reserved for the phase controller')
    for module in groups:
        if module not in sources:
            raise ValueError('unknown module %s' % module)
    facades, extras, phases = {}, {}, {}
    metadata = {'controller': 'CVPH', 'target_lines': target_lines,
                'payloads': {}, 'facades': {}}
    serial = 0

    for module in sorted(sources):
        if not _DEVICE.fullmatch(module):
            raise ValueError('invalid device module name %r' % module)
        source = sources[module]
        source.encode('ascii')
        tree = ast.parse(source, filename=module + '.py')
        definitions, owners = _functions(module, tree, groups.get(module, {}))
        lines = source.splitlines()
        if not owners:
            facades[module] = source
            metadata['facades'][module] = {'line_map': list(range(1, len(lines) + 1))}
            continue
        if 'CVPH' in definitions or any(isinstance(node, ast.Name) and
                isinstance(node.ctx, ast.Store) and node.id == 'CVPH' for node in ast.walk(tree)):
            raise ValueError('%s: CVPH binding is reserved' % module)

        # A resident run must stop at any intervening statement: tables/defaults
        # may consume a function or mutate its globals before the next def.
        runs, resident = [], []
        ordinary = {}
        for node in tree.body:
            phase = owners.get(node.name) if isinstance(node, ast.FunctionDef) else None
            if phase == 'resident':
                resident.append(node)
            else:
                if resident:
                    runs.append(('resident', resident))
                    resident = []
                if phase is not None:
                    ordinary.setdefault(phase, []).append(node)
        if resident:
            runs.append(('resident', resident))
        for phase in sorted(ordinary):
            runs.append((phase, ordinary[phase]))
        # Payload numbering depends only on the input, never dict insertion order.
        runs.sort(key=lambda item: item[1][0].lineno)
        replacements = {}
        removed = set()
        for phase, functions in runs:
            for chunk in _chunks(functions, target_lines):
                while True:
                    if serial > 99999:
                        raise ValueError('too many phase payloads')
                    name = 'CVP%05d' % serial
                    serial += 1
                    if name not in sources:
                        break
                code_lines, origins, function_records = [], [], []
                for node in chunk:
                    function_records.append({'name': node.name,
                        'source_first_line': node.lineno, 'source_last_line': node.end_lineno,
                        'payload_first_line': len(code_lines) + 1})
                    code_lines.extend(lines[node.lineno - 1:node.end_lineno])
                    origins.extend(range(node.lineno, node.end_lineno + 1))
                    removed.update(range(node.lineno, node.end_lineno + 1))
                code = '\n'.join(code_lines) + '\n'
                count, size = len(code_lines), len(code.encode('ascii'))
                required = count * 80 + size * 2 + 3072
                names = tuple(node.name for node in chunk)
                extras[name] = 'CODE=' + repr(code) + '\n'
                metadata['payloads'][name] = {'module': module, 'phase': phase,
                    'functions': function_records, 'source_lines': count,
                    'source_bytes': size, 'required_free': required,
                    'oversize': count > target_lines, 'line_map': origins}
                record = (module, name, names, required)
                if phase == 'resident':
                    replacements[chunk[0].lineno] = 'CVPH.part(%r,%r,%r,%r,True)' % record
                else:
                    phases.setdefault(phase, []).append(record)

        # Preserve the only statements Python requires before ordinary imports.
        prefix_after = 0
        for index, node in enumerate(tree.body):
            if ((index == 0 and isinstance(node, ast.Expr) and
                 isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)) or
                (isinstance(node, ast.ImportFrom) and node.module == '__future__')):
                prefix_after = node.end_lineno
            else:
                break
        rewritten, line_map = [], []
        prefix = ['import CVPH', 'CVPH.register(%r,globals())' % module]
        if prefix_after == 0:
            rewritten.extend(prefix)
            line_map.extend((None, None))
        for number, line in enumerate(lines, 1):
            if number in replacements:
                rewritten.append(replacements[number])
                line_map.append(number)
            elif number not in removed:
                rewritten.append(line)
                line_map.append(number)
            if number == prefix_after:
                rewritten.extend(prefix)
                line_map.extend((None, None))
        facades[module] = '\n'.join(rewritten) + '\n'
        metadata['facades'][module] = {'line_map': line_map}

    phases = {name: tuple(phases[name]) for name in sorted(phases)}
    extras['CVPH'] = _CONTROLLER.replace('@PHASES@', repr(phases))
    for name, source in dict(facades, **extras).items():
        compile(source, name + '.py', 'exec')
    return facades, extras, metadata
