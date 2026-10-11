"""Independent compressed blocks, native decoder portability and strict corruption."""
import ast
from pathlib import Path
import random
import sys

import pytest


BUILD = Path(__file__).resolve().parents[1] / 'build'
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
import codec


def encoded(sources, **kwargs):
    archive, decoder = codec.encode_blocks(sources, **kwargs)
    ast.parse(decoder, feature_version=(3, 4))
    ns = {}
    exec(compile(decoder, '<codec>', 'exec'), ns)
    return archive, ns, decoder


@pytest.mark.parametrize('data', [b'', b'A', b'A' * 5120,
                                 bytes(range(256)), bytes(range(256)) * 20,
                                 b'abcd' * 4096], ids=['empty', 'one', 'repeat', 'all256', 'repeated256', 'maxsize'])
def test_binary_roundtrip(data):
    archive, ns, decoder = encoded({'m': data})
    assert bytes(ns['_decode_bytes'](archive['m'])) == data
    assert all(record[0] <= codec.CHUNK for record in archive['m'])
    assert len(ns['_DICT']) <= codec.DICT_SIZE


@pytest.mark.parametrize('storage', ['base85', 'bytes'])
def test_random_and_maximum_incompressible_roundtrip(storage):
    rng = random.Random(7391)
    data = bytes(rng.randrange(256) for unused in range(codec.MAX_SOURCE))
    archive, ns, decoder = encoded({'m': data}, storage=storage)
    assert bytes(ns['_decode_bytes'](archive['m'])) == data


def test_modules_execute_and_decode_in_any_order():
    sources = {'a': "state=1\ndef change():\n global state\n state+=1\n",
               'b': "def value():\n return a['state']\n"}
    archive, ns, decoder = encoded(sources)
    assert ns['_decode'](archive['b']) == sources['b']
    a, b = {}, {}
    exec(ns['_decode'](archive['a']), a)
    b['a'] = a
    exec(ns['_decode'](archive['b']), b)
    a['change']()
    assert b['value']() == 2
    assert ns['_decode'](archive['a']) == sources['a']


@pytest.mark.parametrize('storage', ['base85', 'bytes'])
def test_deterministic_global_dictionary_and_compression(storage):
    common = " if value is None:\n  return None\n value=module['operation'](value)\n"
    sources = {str(i): ('def fn' + str(i) + '(value):\n' + common) * 40 for i in range(12)}
    a, ns, decoder = encoded(sources, storage=storage)
    assert (a, decoder) == codec.encode_blocks(dict(reversed(list(sources.items()))), storage=storage)
    assert len(repr(a)) + len(decoder) < sum(map(len, sources.values())) // 3
    for name in sources:
        assert ns['_decode'](a[name]) == sources[name]


def test_decoder_has_only_native_dependencies_and_bounded_bit_state():
    archive, ns, decoder = encoded({'m': 'value=42\n'})
    tree = ast.parse(decoder, feature_version=(3, 4))
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
    assert all(n.func.id not in ('eval', 'exec', 'open', '__import__')
               for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name))
    assert decoder.isascii()
    assert all(isinstance(ns[k], bytes) for k in ('_LC', '_LS', '_DC', '_DS'))
    assert isinstance(ns['_DICT'], bytearray)


@pytest.mark.parametrize('storage', ['base85', 'bytes'])
def test_decoder_fits_runtime_loader_depth(tmp_path, storage):
    import evodepth
    source = ('def function(value):\n if value is not None:\n  return value+1\n' * 70)
    archive, decoder = codec.encode_blocks({'m': source}, storage=storage)
    ns = {}
    exec(compile(decoder, str(tmp_path / 'decoder.py'), 'exec'), ns)
    # Runtime caller depth: go -> evaluator -> need -> _load -> _decode.
    with evodepth.DepthChecker([str(tmp_path)], base=4, budget=8,
                              native_penalty=1, dunder_penalty=1, gen_penalty=1) as dc:
        assert ns['_decode'](archive['m']) == source
    assert not evodepth.failures(dc)


@pytest.mark.parametrize('field,value', [(0, -1), (0, 5121), (0, '4'),
                                        (1, -1), (2, 0), (2, 200000),
                                        (3, ''), (3, '~~~~~')])
def test_bad_record_rejected(field, value):
    archive, ns, decoder = encoded({'m': 'a=1\n'})
    record = list(archive['m'][0])
    record[field] = value
    with pytest.raises(ValueError, match='corrupt source'):
        ns['_decode']((tuple(record),))


def test_mutations_and_truncation_rejected():
    archive, ns, decoder = encoded({'m': 'abc xyz 123\n' * 90})
    record = archive['m'][0]
    for position in range(len(record[3])):
        text = record[3]
        changed = codec.ALPHABET[(codec.ALPHABET.index(text[position]) + 1) % 85]
        corrupt = record[:3] + (text[:position] + changed + text[position + 1:],)
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode']((corrupt,))
    for missing in (1, 5, len(record[3])):
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode']((record[:3] + (record[3][:-missing],),))


def test_bad_container_and_total_expansion_cap():
    archive, ns, decoder = encoded({'m': 'x' * 5120})
    for records in ((), list(archive['m']), archive['m'] * 5, archive['m'] * 4):
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode'](records)
    for record in (None, (), (0,), list(archive['m'][0])):
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode']((record,))


def test_source_limits_and_empty_archive():
    with pytest.raises(ValueError, match='16384'):
        codec.encode_blocks({'x': 'x' * (codec.MAX_SOURCE + 1)})
    with pytest.raises(ValueError, match='dictionary size'):
        codec.encode_blocks({'x': 'pass\n'}, dictionary_size=4097)
    with pytest.raises(UnicodeEncodeError):
        codec.encode_blocks({'x': '\N{GREEK SMALL LETTER PI}'})
    archive, ns, decoder = encoded({})
    assert archive == {}


@pytest.mark.parametrize('data', [b'', bytes(range(256)), b'x' * 16384,
                                 b'abcdef' * 850], ids=['empty', 'all256', 'maxsize', 'overlap'])
def test_flat_bytes_archive(data):
    archive, ns, decoder = encoded({'m': data}, storage='bytes')
    assert type(archive['m']) is bytes
    assert bytes(ns['_decode_bytes'](archive['m'])) == data
    assert decoder.isascii() and repr(archive).isascii()
    assert '_A=' not in decoder and '.find(' not in decoder


def test_flat_bytes_corruption_and_limits():
    archive, ns, decoder = encoded({'m': 'text = 123\n' * 100}, storage='bytes')
    blob = archive['m']
    for position in range(len(blob)):
        altered = bytearray(blob)
        altered[position] ^= 1
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode'](bytes(altered))
    for changed in (b'', blob[:-1], blob + b'x', b'\x05' + blob[1:], bytearray(blob)):
        with pytest.raises(ValueError, match='corrupt source'):
            ns['_decode'](changed)
    with pytest.raises(ValueError, match='storage'):
        codec.encode_blocks({'m': ''}, storage='invalid')


def test_flat_bytes_modules_execute_with_no_base85_copy():
    source = 'counter=1\ndef next_value():\n global counter\n counter+=1\n return counter\n'
    archive, ns, decoder = encoded({'m': source}, storage='bytes')
    module = {}
    exec(ns['_decode'](archive['m']), module)
    assert module['next_value']() == 2
    assert module['next_value']() == 3
