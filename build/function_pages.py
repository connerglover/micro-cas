"""Page audited CAS functions without adding a Python forwarding frame.

Native page functions receive their original live namespace as the first argument.
The module facade keeps a page name for dynamic dispatch. Known calls use a fixed
page and evaluate the namespace expression once. Level-seven leaves and escaped
numeric callbacks stay resident: importing them could exceed the depth budget.
Pages cache only themselves; suspended generators retain exactly their own page.
This is a desktop transform, not code run on the calculator.
"""
import ast
import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import bundle


CALLBACKS = 'csin ccos ctan csec ccsc ccot casin cacos catan csinh ccosh ctanh'.split()
PREFIX = """import sys
import gc
for _pg in list(sys.modules):
 if _pg[:3]=='CVF' and _pg!=__name__:
  del sys.modules[_pg]
gc.collect()
"""


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return NotImplemented


def _immutable(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is tuple:
            pending.extend(item)
        elif type(item) not in (type(None), bool, int, float, complex, str, bytes):
            return False
    return True


def _bindings(tree):
    result = {'_env', '_read', '_load', '__name__'}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result.add(node.name)
        elif isinstance(node, ast.Import):
            result.update(a.asname or a.name for a in node.names)
        else:
            result.update(n.id for n in ast.walk(node)
                          if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
    return result


def _source_span(mapping, node):
    spans = [span for span in mapping.get('lines', [])[node.lineno - 1:node.end_lineno] if span]
    return [min(span[0] for span in spans), max(span[1] for span in spans)] if spans else None


def _statement_map(source, original, mapping):
    """AST rewriting preserves top-level order, but not individual source lines."""
    result = [None] * len(source.splitlines())
    emitted = ast.parse(source).body
    if len(emitted) != len(original):
        raise ValueError('top-level statement count changed during paging')
    for old, new in zip(original, emitted):
        span = _source_span(mapping, old)
        result[new.lineno - 1:new.end_lineno] = [span] * (new.end_lineno - new.lineno + 1)
    return {'src': mapping['src'], 'lines': result, 'granularity': 'source-statement-span'}


class Resolver:
    def __init__(self, tree, owner, meta):
        self.owner, self.meta = owner, meta
        self.aliases = {meta['names'].get('SESS', 'SESS'): 'CVRUN'} if owner == 'CVPARSE' else {}
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                    isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call) and
                    isinstance(node.value.func, ast.Name) and node.value.func.id == '_load'):
                self.aliases[node.targets[0].id] = ast.literal_eval(node.value.args[0])

    def local(self, node):
        other = copy.copy(self)
        other.aliases = dict(self.aliases)
        if isinstance(node, ast.FunctionDef):
            for arg in node.args.args:
                other.aliases.pop(arg.arg, None)
        for _ in range(8):
            before = dict(other.aliases)
            for item in ast.walk(node):
                if (isinstance(item, ast.Assign) and len(item.targets) == 1 and
                        isinstance(item.targets[0], ast.Name)):
                    owner = other(item.value)
                    if owner and owner != '#mods':
                        other.aliases[item.targets[0].id] = owner
            if before == other.aliases:
                return other
        raise ValueError('namespace aliases did not converge: ' + self.owner)

    def __call__(self, node):
        if isinstance(node, ast.Name):
            if node.id == 'MODS' and self.owner == 'CVRUN':
                return '#mods'
            return self.aliases.get(node.id)
        if isinstance(node, ast.Subscript):
            base, key = self(node.value), _literal(node.slice)
            if base == 'CVRUN' and key == 'MODS':
                return '#mods'
            if base == '#mods':
                return self.meta['runtime_modules'].get(key, '*')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Subscript):
            if self(node.func.value) == 'CVRUN' and _literal(node.func.slice) == 'need':
                return self.meta['runtime_modules'].get(_literal(node.args[0]), '*')
        return None


class Calls(ast.NodeTransformer):
    def __init__(self, owner, resolver, selected, pages, paged):
        self.owner, self.resolve, self.selected, self.pages = owner, resolver, selected, pages
        self.paged = paged

    def visit_Call(self, node):
        fn, ns, method, page = node.func, None, None, None
        if isinstance(fn, ast.Name) and fn.id in self.selected.get(self.owner, {}):
            ns = ast.Name(id='_S', ctx=ast.Load()) if self.paged else ast.parse('_env[__name__]', mode='eval').body
            method, page = ast.Constant(fn.id), ast.Constant(self.pages[self.owner, fn.id])
        elif isinstance(fn, ast.Subscript):
            owner, key = self.resolve(fn.value), _literal(fn.slice)
            if owner in self.selected and key in self.selected[owner]:
                ns, method, page = fn.value, fn.slice, ast.Constant(self.pages[owner, key])
            elif owner == '*' or owner in self.selected and key is NotImplemented:
                # Audited command/strategy dispatch uses local namespace and key
                # variables. Reject side effects rather than evaluating them twice.
                if any(isinstance(n, (ast.Call, ast.Yield)) for n in ast.walk(fn)):
                    raise ValueError('dynamic paged dispatch requires a bound namespace')
                ns, method, page = fn.value, fn.slice, copy.deepcopy(fn)
        node = self.generic_visit(node)
        if page is not None:
            imported = ast.Call(func=ast.Name(id='__import__', ctx=ast.Load()), args=[page], keywords=[])
            if isinstance(method, ast.Constant):
                node.func = ast.Attribute(value=imported, attr=method.value, ctx=ast.Load())
            else:
                node.func = ast.Call(func=ast.Name(id='getattr', ctx=ast.Load()), args=[imported, method], keywords=[])
            node.args.insert(0, ns)
        return node


class Globals(ast.NodeTransformer):
    def __init__(self, fn, bindings):
        self.bindings = bindings
        self.locals = {arg.arg for arg in fn.args.args}
        self.locals.update(n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and
                           isinstance(n.ctx, (ast.Store, ast.Del)))
        self.locals.update(n.name for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler) and n.name)
        for node in ast.walk(fn):
            if isinstance(node, ast.Global):
                self.locals.difference_update(node.names)

    def visit_Global(self, node):
        return ast.Pass()

    def visit_Name(self, node):
        if node.id in self.bindings and node.id not in self.locals:
            return ast.copy_location(ast.Subscript(value=ast.Name(id='_S', ctx=ast.Load()),
                slice=ast.Constant(node.id), ctx=node.ctx), node)
        return node


def _cleanup(source, names):
    """Drop page caches at boundaries, including failures before generator resume."""
    cleanup = "for _pg in list(sys.modules):\n if _pg[:3]=='CVF':\n  del sys.modules[_pg]\ngc.collect()"

    def insert(marker, indent, before=False, multiple=False):
        nonlocal source
        lines = source.splitlines()
        count = lines.count(marker)
        if count < 1 or count != 1 and not multiple:
            raise ValueError('missing unique page boundary: ' + marker)
        code = '\n'.join(' ' * indent + line for line in cleanup.splitlines())
        source = '\n'.join((code + '\n' + line if before else line + '\n' + code)
                           if line == marker else line for line in lines) + '\n'

    insert("  CVPH['unload']('input')", 2)
    insert('   while ' + names['stack'] + ':', 4)
    insert("    CVPH['load']('print')", 4, before=True, multiple=True)
    insert(' ' + names['stack'] + '=g=' + names['val'] + '=' + names['top'] + '=y=None', 1)
    return source


def pack(sources, meta, target_lines=100):
    """Return transformed source blocks and native page names; update metadata."""
    names = meta['names']
    original_maps = copy.deepcopy(meta['linemap'])
    meta['origin_linemap'] = original_maps
    owner_of = lambda name: meta['payloads'].get(name, {}).get('module', name)
    owners = {}
    for name, source in sources.items():
        owners.setdefault(owner_of(name), []).append(source)
    trees = {owner: ast.parse('\n'.join(parts)) for owner, parts in owners.items()}
    lazy = set(sources) - set(meta['groups']) - set(meta['payloads']) - {'CVPH', 'CASEVO'}
    selected = {owner: {} for owner in lazy | {'CVALG', 'CVPARSE'}}
    callbacks = {names.get(n, n) for n in CALLBACKS}
    levels = {owner: {names.get(n, n): level for n, level in rows.items()}
              for owner, rows in meta['levels'].items()}
    for block, source in sources.items():
        owner = owner_of(block)
        for fn in ast.parse(source).body:
            if (owner in selected and isinstance(fn, ast.FunctionDef) and
                    levels.get(owner, {}).get(fn.name, 7) < 7 and
                    not (owner == 'CVALG' and fn.name in callbacks)):
                if fn.decorator_list or any(isinstance(n, (ast.FunctionDef, ast.Lambda)) for stmt in fn.body for n in ast.walk(stmt)):
                    raise ValueError('cannot page closures/decorated function: ' + owner + '.' + fn.name)
                if '_S' in {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}:
                    raise ValueError('reserved page argument _S')
                selected[owner][fn.name] = fn
    pageids, serial = {}, 0
    for owner in sorted(selected):
        lines = target_lines
        for name, fn in selected[owner].items():
            length = fn.end_lineno - fn.lineno + 1
            generator = any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(fn))
            if generator or lines + length > target_lines:
                serial += 1
                lines = 0
            pageids[owner, name] = 'CVF%05d' % serial
            lines = target_lines if generator else lines + length
    constants = {}
    for owner, tree in trees.items():
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                key, value = node.targets[0].id, _literal(node.value)
                values[key] = value if key not in values else NotImplemented
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                for key in node.names:
                    values.pop(key, None)
        constants[owner] = values
    # Runtime family aliases are distinct from source module stems.
    man = bundle.load_manifest()
    meta['runtime_modules'] = {key: meta['modules'][mod] for key, mod in man.KEYS.items() if mod in meta['modules']}
    meta['runtime_modules'].update({k: v for k, v in meta['modules'].items() if k not in meta['runtime_modules']})
    output, pages, records = {}, {}, {}
    for block, source in sources.items():
        owner = owner_of(block)
        resolver = Resolver(trees[owner], owner, meta)
        tree, body = ast.parse(source), []
        original_statements = copy.deepcopy(tree.body)
        for node in tree.body:
            local = resolver.local(node)
            paged = isinstance(node, ast.FunctionDef) and node.name in selected.get(owner, {})
            if not paged:
                body.append(Calls(owner, local, selected, pageids, False).visit(node))
                continue
            old = node.name
            # Existing defaults are literals, except immutable constants in other
            # namespaces. Resolve those from source, never a hand-copied value.
            for index, default in enumerate(node.args.defaults):
                value = _literal(default)
                if value is NotImplemented and isinstance(default, ast.Subscript):
                    value = constants.get(local(default.value), {}).get(_literal(default.slice), NotImplemented)
                if value is NotImplemented or not _immutable(value):
                    raise ValueError('nonconstant paged default: ' + owner + '.' + old)
                node.args.defaults[index] = ast.parse(repr(value), mode='eval').body
            original_line, original_end = node.lineno, node.end_lineno
            mapping = original_maps.get(block, {})
            span = _source_span(mapping, node)
            node = Calls(owner, local, selected, pageids, True).visit(node)
            node = Globals(node, _bindings(trees[owner])).visit(node)
            node.args.args.insert(0, ast.arg(arg='_S'))
            page = pageids[owner, old]
            code = bundle.minify(ast.unparse(ast.fix_missing_locations(node)) + '\n').text
            prefix = pages.get(page, PREFIX)
            first_line = len(prefix.splitlines()) + 1
            pages[page] = prefix + code
            record = records.setdefault(page, {'module': owner, 'functions': []})
            record['functions'].append({'name': old, 'block': block,
                'block_first_line': original_line, 'block_last_line': original_end,
                'output_first_line': first_line, 'output_last_line': len(pages[page].splitlines()),
                'src': mapping.get('src'), 'source_span': span})
            if mapping:
                page_map = meta['linemap'].setdefault(page, {'src': mapping['src'],
                    'lines': [None] * len(PREFIX.splitlines()), 'granularity': 'source-function-span'})
                page_map['lines'].extend([span] * len(code.splitlines()))
            body.append(ast.Assign(targets=[ast.Name(id=old, ctx=ast.Store())], value=ast.Constant(page)))
        tree.body = body
        code = bundle.minify(ast.unparse(ast.fix_missing_locations(tree)) + '\n').text
        if owner == 'CVRUN' and any(isinstance(n, ast.FunctionDef) and n.name == 'go' for n in tree.body):
            code = _cleanup(code, names)
        output[block] = code
        if block in original_maps:
            meta['linemap'][block] = _statement_map(code, original_statements, original_maps[block])
    # Admission describes the lazy facade that actually loads. Function compilers
    # allocate separately through native import and remain subject to heap limits.
    sizer = bundle.mpy_sizer()
    if sizer is None:
        raise ValueError('function paging requires mpy-cross')
    sizes = {}
    with TemporaryDirectory(prefix='cas-evo-pages-') as temp:
        for module in sorted(lazy):
            path = Path(temp) / (module + '.py')
            path.write_text(output[module], 'ascii', newline='\n')
            sizes[module] = sizer(str(path))
    run = ast.parse(output['CVRUN'])
    dev = next(ast.literal_eval(n.value) for n in run.body if isinstance(n, ast.Assign) and
               isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'DEV')
    for node in run.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key == names['COST']:
                node.value = ast.parse(repr({k: int(sizes.get(v, 0) * man.FACTOR) + 1 for k, v in dev.items()}), mode='eval').body
            elif key == names['LINES']:
                node.value = ast.parse(repr({k: len(output.get(v, '').splitlines()) for k, v in dev.items()}), mode='eval').body
    output['CVRUN'] = bundle.minify(ast.unparse(ast.fix_missing_locations(run)) + '\n').text
    output.update(pages)
    meta['function_pages'] = records
    meta['sources'] = {k: len(v.encode('ascii')) for k, v in output.items()}
    return output, set(pages)
