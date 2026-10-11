"""Turn source carriers into bytecode initializers with live shared namespaces.

No calculator-side exec, wrapper around arithmetic calls, or copied global state.
The initializer runs only at load boundaries; exported functions retain their
original signatures and read/write the same logical namespace dictionaries.
"""
import ast

import bundle
import function_pages
from release import LOADER


LOADER_NATIVE = '''import gc
import sys
_env={}
def _load(name):
 if name in _env:
  return _env[name]
 ns={'__name__':name,'_load':_load,'_env':_env}
 _env[name]=ns
 module=None
 try:
  gc.collect()
  module=__import__(name)
  module.init(ns)
  del module.init
 except:
  del _env[name]
  raise
 finally:
  module=None
  if name in sys.modules:
   del sys.modules[name]
  gc.collect()
 return ns
'''


def namespace(name, context=None):
    return ast.Subscript(value=ast.Name(id='_S', ctx=ast.Load()),
                         slice=ast.Constant(name), ctx=context or ast.Load())


class Shared(ast.NodeTransformer):
    """Rewrite one scope, explicitly rejecting constructs outside this compiler."""

    def __init__(self, bindings, locals_=()):
        self.bindings, self.locals = set(bindings), set(locals_)

    def visit_Name(self, node):
        if node.id in self.bindings and node.id not in self.locals:
            return ast.copy_location(namespace(node.id, node.ctx), node)
        return node

    def visit_Global(self, node):
        return ast.Pass()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in ('globals', 'locals', 'exec', 'eval'):
            if node.func.id == 'globals' and not self.locals and not node.args and not node.keywords:
                return ast.Name(id='_S', ctx=ast.Load())
            raise ValueError('unsupported reflection in archive module: ' + node.func.id)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        raise ValueError('nested functions require a scope audit: ' + node.name)

    def visit_Lambda(self, node):
        raise ValueError('archive modules do not support closures')

    def visit_ClassDef(self, node):
        raise ValueError('nested classes require a scope audit: ' + node.name)


def initializer(source, bindings):
    """Compile facade/payload statements in order, exporting each definition.

    Function defaults are evaluated at their original statement, with globals
    resolved in the live namespace. Do not retain initializer locals afterward.
    """
    tree = ast.parse(source)
    if any(isinstance(n, ast.Name) and n.id in ('_S', '_cv_tmp') for n in ast.walk(tree)):
        raise ValueError('reserved archive initializer name')
    module_scope = Shared(bindings)
    body = [ast.Global(names=['_S']), ast.Assign(
        targets=[ast.Name(id='_S', ctx=ast.Store())], value=ast.Name(id='ns', ctx=ast.Load()))]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or node.args.kwonlyargs or node.args.posonlyargs:
                raise ValueError('unsupported archive function signature: ' + node.name)
            local = function_pages.Globals(node, bindings).locals
            local.update(a.arg for a in (node.args.vararg, node.args.kwarg) if a)
            # Imports bind locals even though their targets are not ast.Name.
            local.update(a.asname or a.name for s in ast.walk(node)
                         if isinstance(s, ast.Import) for a in s.names)
            scope = Shared(bindings, local)
            node.args.defaults = [module_scope.visit(d) for d in node.args.defaults]
            node.body = [scope.visit(s) for s in node.body]
            body.append(node)
            body.extend(ast.parse("_S[%r]=%s\ndel %s" % (node.name, node.name, node.name)).body)
        elif isinstance(node, ast.ClassDef):
            if node.decorator_list or node.keywords or any(not isinstance(s, ast.Pass) for s in node.body):
                raise ValueError('only empty exception classes are supported: ' + node.name)
            node.bases = [module_scope.visit(base) for base in node.bases]
            body.append(node)
            body.extend(ast.parse("_S[%r]=%s\ndel %s" % (node.name, node.name, node.name)).body)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if '.' in alias.name:
                    raise ValueError('dotted native import requires an audit')
                name = alias.asname or alias.name
                body.extend(ast.parse('import %s as _cv_tmp\n_S[%r]=_cv_tmp\ndel _cv_tmp' %
                                      (alias.name, name)).body)
        elif isinstance(node, ast.ImportFrom):
            raise ValueError('from imports require an archive scope audit')
        else:
            body.append(module_scope.visit(node))
    factory = ast.parse('_S=None\ndef init(ns):\n pass\n')
    factory.body[1].body = body
    text = bundle.minify(ast.unparse(ast.fix_missing_locations(factory)) + '\n').text
    ast.parse(text, feature_version=(3, 4))
    return text


def transform(files, meta):
    """Return actual archive source inputs; original release bytes stay unchanged."""
    sources, native, launchers = {}, {}, {}
    for name, data in files.items():
        source, stem = data.decode('ascii'), name[:-3]
        if stem in ('CASEVO', 'CVTEST'):
            if source.count(LOADER) != 1:
                raise ValueError('source loader changed: ' + name)
            launchers[name] = source.replace(LOADER, LOADER_NATIVE).encode('ascii')
        elif stem in meta['function_pages']:
            native[name] = data
        else:
            tree = ast.parse(source)
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign) or ast.unparse(tree.body[0].targets[0]) != 'CODE':
                raise ValueError('not a source carrier: ' + name)
            sources[stem] = ast.literal_eval(tree.body[0].value)
    # The old admission formula reserves a source parser/AST that no longer
    # exists. Actual bytecode allocation remains guarded and failure-atomic.
    controller = sources['CVPH']
    old = 'payload=_read(name)\n  exec(payload,ns)'
    if controller.count(old) != 1:
        raise ValueError('phase loader changed')
    controller = controller.replace(old, 'payload=__import__(name)\n  payload.init(ns)\n  del payload.init')
    controller = controller.replace("MemoryError('phase compile memory')",
        "MemoryError('load %s: %d free, %d needed'%(name,free,required))", 1)
    controller = controller.replace("MemoryError('phase compile memory')",
        "MemoryError('phase %s: %d free, %d needed'%(phase,free,required))", 1)
    controller = controller.replace(' if name in _env:\n   del _env[name]',
                                    ' if name in sys.modules:\n   del sys.modules[name]')
    sources['CVPH'] = controller
    owners = {}
    for name, source in sources.items():
        owner = meta['payloads'].get(name, {}).get('module', name)
        owners.setdefault(owner, []).append(source)
    bindings = {name: function_pages._bindings(ast.parse('\n'.join(parts)))
                for name, parts in owners.items()}
    result = dict(native, **launchers)
    for name, source in sources.items():
        owner = meta['payloads'].get(name, {}).get('module', name)
        result[name + '.py'] = initializer(source, bindings[owner]).encode('ascii')
    return result


def set_admission(files, meta, budgets, sizes):
    """Set each phase budget from its compiled byte size, not source line count."""
    result = dict(files)
    for name in ('CVPH',) + tuple(meta['groups']):
        tree = ast.parse(files[name + '.py'])
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and len(node.elts) == 4:
                key = node.elts[1]
                if isinstance(key, ast.Constant) and key.value in budgets:
                    node.elts[3] = ast.Constant(budgets[key.value])
            elif isinstance(node, ast.Call) and len(node.args) == 5:
                key = node.args[1]
                if (isinstance(key, ast.Constant) and key.value in budgets and
                        isinstance(node.func, ast.Subscript) and
                        isinstance(node.func.slice, ast.Constant) and node.func.slice.value == 'part'):
                    node.args[3] = ast.Constant(budgets[key.value])
        result[name + '.py'] = bundle.minify(ast.unparse(ast.fix_missing_locations(tree)) + '\n').text.encode('ascii')
    tree = ast.parse(result['CVRUN.py'])
    names = meta['names']
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Subscript) or not isinstance(target.slice, ast.Constant):
            continue
        key = target.slice.value
        if key == names['COST']:
            node.value = ast.parse(repr({key: sizes[module] * 2
                for key, module in meta['runtime_modules'].items() if module in sizes}), mode='eval').body
        elif key == names['PEAKB']:
            node.value = ast.Constant(0)  # Archive modules never invoke the source compiler.
        elif key == names['LINES']:
            node.value = ast.Dict(keys=[], values=[])
    result['CVRUN.py'] = bundle.minify(ast.unparse(ast.fix_missing_locations(tree)) + '\n').text.encode('ascii')
    return result
