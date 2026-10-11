"""Safe universal identifier shrinking, dynamic dispatch and physical line maps."""
import ast
import pathlib
import sys
import textwrap
import types

import pytest

BUILD = pathlib.Path(__file__).resolve().parents[1] / 'build'
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
import shrink


def source(text):
    return textwrap.dedent(text).lstrip('\n')


def load(sources, monkeypatch):
    modules = {name: types.ModuleType(name) for name in sources}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name, text in sources.items():
        exec(compile(text, '<shrink-' + name + '>', 'exec'), modules[name].__dict__)
    return modules


def example():
    return {
        'shcore': source('''
            SHARED_COUNTER = 0
            def increment_counter(amount):
                global SHARED_COUNTER
                SHARED_COUNTER += amount
                return SHARED_COUNTER
            def g_emit_value(value):
                yield increment_counter(value)
            '''),
        'shloader': source('''
            import shcore as CORE
            MODS = {'core': CORE}
            REGISTRY = {'command': ('core', 'g_emit_value')}
            def need(key):
                return MODS[key]
            '''),
        'shclient': source('''
            import shcore as CORE
            import shloader as LOADER
            def g_dispatch(value):
                module = LOADER.need('core')
                entry = LOADER.REGISTRY.get('command')
                yield getattr(module, entry[1])(value)
            def direct_read():
                alias = LOADER.MODS['core']
                return alias.increment_counter(3), getattr(CORE, 'SHARED_COUNTER')
            ''')}


def test_multimodule_mutation_registry_dispatch_and_local_alias(monkeypatch):
    sources = example()
    outputs, names = shrink.shrink_sources(sources)
    for name in ('SHARED_COUNTER', 'increment_counter', 'g_emit_value', 'g_dispatch', 'direct_read'):
        assert name in names
    modules = load(outputs, monkeypatch)
    client, core = modules['shclient'], modules['shcore']
    assert getattr(client, names['direct_read'])() == (3, 3)
    outer = getattr(client, names['g_dispatch'])(4)
    inner = next(outer)
    assert isinstance(inner, types.GeneratorType)
    assert next(inner) == 7
    with pytest.raises(StopIteration):
        next(inner)
    with pytest.raises(StopIteration):
        next(outer)
    assert getattr(core, names['SHARED_COUNTER']) == 7
    assert "'core'" in outputs['shloader'] and "'command'" in outputs['shloader']


def test_mapping_deterministic_unique_fresh_and_profitable():
    sources = example()
    sources['shother'] = 'aa=1\nab=2\nac=3\nlong_counter=4\ndef local_user(long_counter):\n return long_counter+aa\n'
    first = shrink.make_mapping(sources)
    second = shrink.make_mapping(dict(reversed(list(sources.items()))))
    assert first == second
    assert len(set(first.values())) == len(first)
    assert not {'aa', 'ab', 'ac'} & set(first.values())
    assert all(len(short) < len(long) for long, short in first.items())
    original_tokens = {n.id for value in sources.values() for n in ast.walk(ast.parse(value)) if isinstance(n, ast.Name)}
    assert not original_tokens & set(first.values())


def test_same_word_local_global_and_closure_remain_consistent(monkeypatch):
    inputs = {'shscope': source('''
        long_value = 11
        def calculate_result(long_value):
            def nested_call():
                return long_value * 2
            return nested_call()
        ''')}
    outputs, names = shrink.shrink_sources(inputs)
    module = load(outputs, monkeypatch)['shscope']
    assert getattr(module, names['calculate_result'])(7) == 14
    assert getattr(module, names['long_value']) == 11


def test_preserves_native_attributes_imports_keyword_arguments_and_class_methods():
    inputs = {'shnative': source('''
        import math as native_math
        import json
        def append(value):
            return value
        def native_attribute(value):
            return value
        def keyword_value(value):
            return value
        def class_method(value):
            return value
        class NativeUser:
            def class_method(self):
                return 1
        def exercise(external):
            external.native_attribute()
            native_math.sin(0)
            return json.dumps([], keyword_value=2)
        ''')}
    names = shrink.make_mapping(inputs)
    assert not {'append', 'native_attribute', 'keyword_value', 'class_method', 'native_math', 'json'} & names.keys()
    assert 'exercise' in names


def test_user_strings_errors_runtime_keys_and_templates_remain_unchanged():
    inputs = {'shstrings': source('''
        def descriptive_method():
            return 1
        def g_generate():
            yield 2
        MESSAGES = {'descriptive_method': 'descriptive_method', 'user': 'g_generate(x)+1'}
        REGISTRY = {'command': ('shstrings', 'g_generate')}
        ERROR = 'descriptive_method'
        ''')}
    outputs, names = shrink.shrink_sources(inputs)
    assert 'descriptive_method' not in names
    assert 'g_generate' in names
    assert "'g_generate(x)+1'" in outputs['shstrings']
    assert "'descriptive_method': 'descriptive_method'" in outputs['shstrings']
    assert "'shstrings'" in outputs['shstrings']


def test_line_count_comments_newlines_and_python34_grammar():
    text = '# comment long_function\r\nlong_state = 1\r\ndef long_function(value):\r\n    return (long_state +\r\n            value) # long_state\r\n'
    outputs, names = shrink.shrink_sources({'shline': text})
    result = outputs['shline']
    assert result.count('\n') == text.count('\n')
    assert result.count('\r\n') == text.count('\r\n')
    assert '# comment long_function' in result and '# long_state' in result
    ast.parse(result, feature_version=(3, 4))
    original = ast.parse(text)
    rewritten = ast.parse(result)
    assert [n.lineno for n in ast.walk(original) if hasattr(n, 'lineno')] == [n.lineno for n in ast.walk(rewritten) if hasattr(n, 'lineno')]


def test_computed_uppercase_lookup_preserves_data_names(monkeypatch):
    inputs = {
        'shrules': 'TRIGRULES=(1,2)\ndef a_long_function():\n return 3\n',
        'shreader': 'import shrules as RULES\ndef read_rules(name):\n return getattr(RULES,name.upper())\n'}
    outputs, names = shrink.shrink_sources(inputs)
    assert 'TRIGRULES' not in names
    assert 'a_long_function' in names
    modules = load(outputs, monkeypatch)
    assert getattr(modules['shreader'], names['read_rules'])('trigrules') == (1, 2)


def test_ambiguous_reflection_and_runtime_eval_disable_unsafe_renames():
    for dynamic in ('getattr(obj, name)', 'eval(name)', 'globals()[name]'):
        inputs = {'shdynamic': 'long_value=3\ndef long_reader(obj,name):\n return ' + dynamic + '\n'}
        assert shrink.make_mapping(inputs) == {}


def test_native_reflection_string_collision_reserves_word():
    inputs = {'shnative': 'def long_attribute():\n return 1\ndef use(obj):\n return getattr(obj,"long_attribute")\n'}
    assert 'long_attribute' not in shrink.make_mapping(inputs)


def test_concatenated_registry_string_is_reserved():
    inputs = {'shconcat': "def g_sample():\n yield 1\nREGISTRY=(('module','g_' 'sample'),)\n"}
    assert 'g_sample' not in shrink.make_mapping(inputs)


def test_module_alias_cleared_after_use_and_session_injection(monkeypatch):
    inputs = {
        'shsession': 'def long_answer():\n return 42\nMODS={}\ndef need(key):\n return MODS[key]\n',
        'shparser': 'SESSION=None\ndef parse_answer():\n S=SESSION\n M=S.need("active")\n out=M.long_answer()\n M=None\n return out\n',
        'shboot': 'import shsession as S\nimport shparser as P\nS.MODS["active"]=S\nP.SESSION=S\n'}
    outputs, names = shrink.shrink_sources(inputs)
    assert 'long_answer' in names
    module = load(outputs, monkeypatch)['shparser']
    assert getattr(module, names['parse_answer'])() == 42


def test_alias_shadowing_reserves_affected_attribute():
    inputs = {'shcore': 'def long_method():\n return 1\n',
              'shshadow': 'import shcore as M\ndef use(M):\n return M.long_method()\n'}
    assert 'long_method' not in shrink.make_mapping(inputs)


def test_explicit_reservations_and_mapping_validation():
    assert 'long_value' not in shrink.make_mapping({'shx': 'long_value=1\n'}, reserved={'long_value'})
    with pytest.raises(shrink.ShrinkError):
        shrink.transform('hello=1\n', {'hello': 'if'})
    with pytest.raises(shrink.ShrinkError):
        shrink.transform('hello=1\n', {'hello': 'aa', 'world': 'aa'})


def test_real_source_mapping_has_useful_savings_and_compiles():
    root = pathlib.Path(__file__).resolve().parents[1]
    inputs = {path.stem: path.read_text(encoding='utf-8') for path in (root / 'src').glob('*.py')}
    outputs, names = shrink.shrink_sources(inputs)
    assert len(names) > 100
    assert sum(len(inputs[key]) - len(outputs[key]) for key in inputs) > 4000
    for name, text in outputs.items():
        compile(text, name, 'exec')
        assert text.count('\n') == inputs[name].count('\n')
