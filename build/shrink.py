"""Conservative, line-preserving identifier shrinking for device source bundles.

``make_mapping({module_name: source})`` plans one universal word mapping. ``transform``
applies that mapping to one source without changing line breaks. ``shrink_sources`` returns
``(rewritten_sources, mapping)``. Run this before or after phase-one whitespace minification,
but before replacing source import names with device import names (or use device module keys).

Every replacement is global by identifier spelling, including locals, keyword references,
and project-module attributes. Fresh targets cannot capture an existing local. A spelling
used as an import binding, builtin/native/unknown attribute, keyword argument, class member,
or ambiguous string is reserved everywhere. Computed uppercase reflection reserves uppercase
names. These conservative exclusions are deliberate: a smaller safe map beats a broken app.

Only exact string literals proven to describe reflection or g_* registry entries are
rewritten. Runtime keys, expression templates, comments, and error messages retain their
contents. Existing grammar and physical line count are preserved; inserted identifiers and
string spellings are valid Python 3.4. No AST unparse or runtime wrapper is introduced.
"""
import ast
import builtins
import io
import keyword
import string
import tokenize


REFLECT = {'getattr', 'setattr', 'hasattr', 'delattr'}
ALPHABET = string.ascii_lowercase + string.ascii_uppercase


class ShrinkError(ValueError):
    pass


def _bindings(tree):
    """All bindings in module scope, without descending into functions or classes."""
    out = set()
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.add(node.id)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        pending.extend(ast.iter_child_nodes(node))
    return out


def _native_names():
    out = set(dir(builtins)) | set(keyword.kwlist)
    for value in (str, bytes, int, float, complex, list, tuple, dict, set, object, type,
                  Exception, type(iter([])), type((v for v in ()))):
        out.update(dir(value))
    return out


def _module_value(node, aliases):
    """Recognize project modules, including aliases returned by the lazy loader."""
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Subscript):
        value = node.value
        return isinstance(value, ast.Attribute) and value.attr == 'MODS' and _module_value(value.value, aliases)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        value = node.func.value
        if node.func.attr == 'need':
            return _module_value(value, aliases)
        if node.func.attr == 'get' and isinstance(value, ast.Attribute) and value.attr == 'MODS':
            return _module_value(value.value, aliases)
    return False


def _aliases(tree, modules, seeds=()):
    aliases = set(seeds)
    imports = set()
    stores = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.update(name.name.split('.'))
                imports.add(name.asname or name.name.split('.')[0])
                if name.name in modules:
                    aliases.add(name.asname or name.name)
        elif isinstance(node, ast.ImportFrom):
            imports.update((node.module or '').split('.'))
            for name in node.names:
                imports.add(name.name)
                imports.add(name.asname or name.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    stores.setdefault(target.id, []).append(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # A module alias shadowed by a parameter is no longer proven module-valued.
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            for arg in args:
                stores.setdefault(arg.arg, []).append(ast.Name(id='_unknown_parameter'))
    changed = True
    while changed:
        changed = False
        for name, values in stores.items():
            nonnull = [v for v in values if not isinstance(v, ast.Constant) or v.value is not None]
            if name not in aliases and nonnull and all(_module_value(v, aliases) for v in nonnull):
                aliases.add(name)
                changed = True
    # Imported aliases that are ever rebound to a non-module value are ambiguous globally.
    while True:
        ambiguous = {name for name in aliases if name in stores and
                     not all(_module_value(v, aliases) or isinstance(v, ast.Constant) and
                             v.value is None for v in stores[name])}
        if not ambiguous:
            break
        aliases.difference_update(ambiguous)
    return aliases, imports


def _parents(tree):
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _safe_literal(node, parents, aliases):
    parent = parents.get(node)
    if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id in REFLECT:
        return len(parent.args) > 1 and parent.args[1] is node and _module_value(parent.args[0], aliases)
    if not node.value.startswith('g_'):
        return False
    # Generator registry entries are container values, never command/runtime dictionary keys.
    nested = False
    while isinstance(parent, (ast.Tuple, ast.List, ast.Dict)):
        if isinstance(parent, ast.Dict) and node in parent.keys:
            return False
        nested = True
        node = parent
        parent = parents.get(node)
    return nested and isinstance(parent, (ast.Assign, ast.AnnAssign))


def _literal_is_one_token(source, node):
    segment = ast.get_source_segment(source, node)
    if segment is None:
        return False
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(segment).readline)
              if t.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER)]
    return len(tokens) == 1 and tokens[0].type == tokenize.STRING


def _registry_reference(node, tree, aliases):
    """The two device dispatch forms: registry tuple[index], and for key,name in TABLE."""
    if isinstance(node, ast.Subscript):
        base = node.value
        while isinstance(base, ast.Subscript):
            base = base.value
        if isinstance(base, ast.Attribute):
            return _module_value(base.value, aliases)
        if isinstance(base, ast.Name):
            for assignment in ast.walk(tree):
                if isinstance(assignment, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == base.id for t in assignment.targets):
                    value = assignment.value
                    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
                        owner = value.func.value
                        if isinstance(owner, ast.Attribute) and _module_value(owner.value, aliases):
                            return True
    if isinstance(node, ast.Name):
        for loop in ast.walk(tree):
            if isinstance(loop, ast.For) and isinstance(loop.target, (ast.Tuple, ast.List)):
                if any(isinstance(t, ast.Name) and t.id == node.id for t in loop.target.elts):
                    if isinstance(loop.iter, ast.Name):
                        for assignment in tree.body:
                            if isinstance(assignment, ast.Assign) and any(
                                    isinstance(t, ast.Name) and t.id == loop.iter.id for t in assignment.targets):
                                return isinstance(assignment.value, (ast.List, ast.Tuple))
    return False


def _short_names():
    # aa, ab, ... aZ, ba, ...; 2+ characters avoid tiny bindings and common Python locals.
    width = 2
    while True:
        digits = [0] * width
        while True:
            yield ''.join(ALPHABET[i] for i in digits)
            j = width - 1
            while j >= 0 and digits[j] == len(ALPHABET) - 1:
                digits[j] = 0
                j -= 1
            if j < 0:
                break
            digits[j] += 1
        width += 1


def _clears_every_name(call, parents):
    """setattr(obj, k, None) inside 'for k in dir(obj)': it reaches every attribute that
    exists at run time, whatever it is called, so it constrains no spelling (run.unload)."""
    if call.func.id != 'setattr' or len(call.args) != 3 or call.keywords:
        return False
    obj, key, value = call.args
    if not (isinstance(key, ast.Name) and isinstance(value, ast.Constant) and value.value is None):
        return False
    node = parents.get(call)
    while node is not None:
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and \
                node.target.id == key.id and isinstance(node.iter, ast.Call) and \
                isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'dir' and \
                len(node.iter.args) == 1 and ast.dump(node.iter.args[0]) == ast.dump(obj):
            return True
        if isinstance(node, (ast.FunctionDef, ast.Module)):
            return False
        node = parents.get(node)
    return False


def make_mapping(sources, reserved=(), local_names=False, seeds=None):
    """Return a stable old-name -> new-name dict; keys in sources are import module names."""
    trees = {name: ast.parse(source, filename=name) for name, source in sources.items()}
    candidates = set()
    for tree in trees.values():
        candidates.update(_bindings(tree))
        if local_names:
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    candidates.add(node.id)
                elif isinstance(node, ast.arg):
                    candidates.add(node.arg)
                elif isinstance(node, ast.ExceptHandler) and node.name:
                    candidates.add(node.name)
    blocked = _native_names() | set(reserved)
    used = set(blocked)
    counts = {}
    computed_upper = False
    # A resident may receive its session module from boot(), e.g. P.SESS=R. Track that
    # attribute into the receiving module, including its initial None placeholder.
    given = seeds or {}
    seeds = {name: set(given.get(name, ())) for name in sources}
    for tree in trees.values():
        aliases, imports = _aliases(tree, set(sources))
        owners = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for entry in node.names:
                    if entry.name in sources:
                        owners[entry.asname or entry.name] = entry.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _module_value(node.value, aliases):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        owner = owners.get(target.value.id)
                        if owner is not None:
                            seeds[owner].add(target.attr)
    for name in sorted(sources):
        source, tree = sources[name], trees[name]
        aliases, imports = _aliases(tree, set(sources), seeds[name])
        blocked.update(imports)
        parents = _parents(tree)
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                used.add(token.string)
                counts[token.string] = counts.get(token.string, 0) + 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and not _module_value(node.value, aliases):
                blocked.add(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                blocked.add(node.arg)
            elif isinstance(node, ast.ClassDef):
                blocked.update(_bindings(node))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.isidentifier():
                    used.add(node.value)
                if node.value in candidates and not (_safe_literal(node, parents, aliases) and
                                                       _literal_is_one_token(source, node)):
                    blocked.add(node.value)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in REFLECT:
                if _clears_every_name(node, parents):
                    continue                # names come from dir() at run time: any spelling
                if len(node.args) > 1 and not isinstance(node.args[1], ast.Constant):
                    lookup = node.args[1]
                    target = lookup.func if isinstance(lookup, ast.Call) else None
                    if isinstance(target, ast.Attribute) and target.attr == 'upper' and _module_value(node.args[0], aliases):
                        computed_upper = True
                    elif not (_module_value(node.args[0], aliases) and _registry_reference(lookup, tree, aliases)):
                        blocked.update(candidates)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('eval', 'exec', 'globals', 'locals'):
                blocked.update(candidates)
    if computed_upper:
        blocked.update(name for name in candidates if name.isupper())
    eligible = [name for name in candidates if name not in blocked and len(name) > 2 and
                name.isascii() and name.isidentifier() and not name.startswith('__')]
    eligible.sort(key=lambda name: (-(len(name) - 2) * counts.get(name, 0), name))
    mapping = {}
    shorts = _short_names()
    for name in eligible:
        short = next(shorts)
        while short in used:
            short = next(shorts)
        if len(short) < len(name):
            mapping[name] = short
            used.add(short)
    return mapping


def _lexical_names(source):
    """Names sharing lexical namespaces; attributes belong to their receiver."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def coalesce_mapping(sources, mapping, extra_sources=(), reserved=()):
    """Reuse fresh spellings only for names that never share a module's scopes.

    MicroPython retains interned identifier strings even after code eviction.
    Coloring this conservative interference graph bounds that permanent pool.
    Attribute accesses and proven reflection still use the universal word map;
    every target namespace's own lexical bindings keep distinct spellings.
    Extra entry/probe sources participate in capture prevention too.
    """
    conflicts = {name: set() for name in mapping}
    extra_sources = tuple(extra_sources)
    unavailable = _native_names() | set(reserved)
    written = set()
    for source in list(sources.values()) + list(extra_sources):
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                unavailable.add(token.string)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isidentifier():
                unavailable.add(node.value)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
                written.add(node.attr)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in REFLECT:
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    written.add(node.args[1].value)
        names = _lexical_names(source) & mapping.keys()
        for name in names:
            conflicts[name].update(names - {name})
    # Writes can introduce a receiver binding absent from its own source. Keep
    # these spellings unique without assuming that every module alias is static.
    for name in written & mapping.keys():
        conflicts[name].update(mapping.keys() - {name})
        for other in mapping.keys() - {name}:
            conflicts[other].add(name)
    targets = []
    fresh = _short_names()
    result = {}
    for name in sorted(mapping, key=lambda name: (-len(conflicts[name]), name)):
        used = {result[other] for other in conflicts[name] if other in result}
        target = next((target for target in targets if target not in used), None)
        if target is None:
            target = next(fresh)
            while target in unavailable:
                target = next(fresh)
            targets.append(target)
        if len(target) >= len(name):
            raise ShrinkError('no profitable identifier for entry constraints')
        result[name] = target
    return result


def transform(source, mapping, allow_reuse=False):
    """Apply a mapping produced by make_mapping; preserve every physical line and comment."""
    if not allow_reuse and len(set(mapping.values())) != len(mapping):
        raise ShrinkError('replacement names must be unique')
    if allow_reuse:
        active = _lexical_names(source) & mapping.keys()
        if len({mapping[name] for name in active}) != len(active):
            raise ShrinkError('replacement names collide in a lexical namespace')
    for before, after in mapping.items():
        if not before.isidentifier() or not after.isidentifier() or keyword.iskeyword(after):
            raise ShrinkError('invalid replacement identifier')
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    edits = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        replacement = None
        if token.type == tokenize.NAME and token.string in mapping:
            replacement = mapping[token.string]
        elif token.type == tokenize.STRING:
            value = ast.literal_eval(token.string)
            if isinstance(value, str) and value in mapping:
                replacement = ascii(mapping[value])
        if replacement is not None:
            # Strings containing newlines cannot be exact identifier strings, but reject a
            # manually supplied mapping rather than silently invalidating a source line map.
            if token.start[0] != token.end[0]:
                raise ShrinkError('cannot replace a multiline token')
            begin = starts[token.start[0] - 1] + token.start[1]
            end = starts[token.end[0] - 1] + token.end[1]
            edits.append((begin, end, replacement))
    for begin, end, replacement in reversed(edits):
        source = source[:begin] + replacement + source[end:]
    return source


def shrink_sources(sources, reserved=(), reuse=False, extra_sources=(), local_names=False,
                   seeds=None):
    """Return ({module: transformed source}, mapping), deterministic across dict order.
    seeds: {module: names} that hold a project module at run time (e.g. parse.SESS)."""
    mapping = make_mapping(sources, reserved, local_names, seeds)
    extra_sources = tuple(extra_sources)
    # Entry/probe text is transformed with the same map later. Its user-facing
    # strings are not reflection metadata and must never become identifiers.
    for source in extra_sources:
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                mapping.pop(node.value, None)
    if reuse:
        mapping = coalesce_mapping(sources, mapping, extra_sources, reserved)
    return {name: transform(source, mapping, allow_reuse=reuse)
            for name, source in sources.items()}, mapping
