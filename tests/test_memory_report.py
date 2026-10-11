"""Reproducible heap estimates stay explicit about their incomplete model."""
import copy
import json
from pathlib import Path
import sys

import pytest


BUILD = Path(__file__).resolve().parents[1] / 'build'
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
import codec
import memory_report as mr


def fixture_data():
    output = {name: 'value=' + str(i) + '\n' for i, name in enumerate(
        ('CVCORE', 'CVPH', 'CVRES', 'CVUI', 'CVINPUT', 'CVPRINT', 'CVLAZY', 'CVLAZYP'))}
    metadata = {'groups': {'CVCORE': {}}, 'controller': 'CVPH',
                'facades': {'CVCORE': {}, 'CVLAZY': {}},
                'payloads': {name: {'module': owner, 'phase': phase, 'required_free': limit}
                             for name, owner, phase, limit in (
        ('CVRES', 'CVCORE', 'resident', 20), ('CVUI', 'CVCORE', 'ui', 30),
        ('CVINPUT', 'CVCORE', 'input', 40), ('CVPRINT', 'CVCORE', 'print', 50),
        ('CVLAZYP', 'CVLAZY', 'resident', 60))}}
    archive = {name: b'abc' for name in output}
    decoder = "_DICT=b'12345'\n"
    sizes = {'CVCORE': 100, 'CVPH': 20, 'CVRES': 200, 'CVUI': 300,
             'CVINPUT': 400, 'CVPRINT': 500, 'CVLAZY': 10000,
             'CVLAZYP': 20000, '_decoder': 50}
    return output, metadata, archive, decoder, sizes


def test_exact_components_stages_and_lazy_exclusion():
    output, metadata, archive, decoder, sizes = fixture_data()
    before = copy.deepcopy((output, metadata, archive))
    paths, seen = [], {}

    def sizer(path):
        path = Path(path)
        paths.append(path)
        seen[path.stem] = path.read_text('ascii')
        return sizes[path.stem]

    got = mr.report(output, metadata, archive, decoder, sizer, factor=1.5, heap=20000)
    assert seen == dict(output, _decoder=decoder)
    assert all(not p.exists() for p in paths)
    assert (output, metadata, archive) == before
    assert got['fixed_components'] == {'archive_bytes': 24, 'decoded_dictionary_bytes': 5,
                                       'node_backing_bytes': 16384, 'reserve_bytes': 3072}
    assert got['resident_facades'] == {'blocks': ['CVCORE', 'CVPH'], 'mpy_bytes': 120,
                                      'estimated_heap_bytes': 180}
    assert got['phase_payloads']['resident']['blocks'] == ['CVRES']
    assert got['excluded_compiled_blocks']['blocks'] == ['CVLAZY', 'CVLAZYP']
    fixed = 24 + 5 + 16384 + 3072
    base = fixed + 75 + 180 + 300
    assert got['stages']['resident']['estimated_heap_bytes'] == base
    assert got['stages']['ui']['estimated_heap_bytes'] == base + 450
    assert got['stages']['input']['estimated_heap_bytes'] == base + 600
    assert got['stages']['print']['estimated_heap_bytes'] == base + 750
    assert got['stages']['print']['headroom_bytes'] == 20000 - base - 750
    assert got['min_raw_mpy_model_bytes'] == fixed + 50 + 120 + 200
    assert got['max_compile_admission_bytes'] == 60
    assert got['stages']['input']['max_compile_admission_bytes'] == 40
    assert got['status'] == 'PROVISIONAL' and got['device_measured'] is False
    assert got['fits_known_heap_model'] is False
    assert got['fits_with_compile_admission_model'] is False
    for term in ('namespace', 'object headers', 'qstr', 'working data', 'lazy families', 'entry'):
        assert any(term in line for line in got['exclusions'])
    json.dumps(got, allow_nan=False)


def test_individual_rounding_entry_and_admission_are_separate():
    output, metadata, archive, decoder, sizes = fixture_data()
    output['CASEVO'] = 'entry=1\n'
    sizes = {name: 1 for name in list(output) + ['_decoder']}
    got = mr.report(output, metadata, archive, decoder, lambda p: sizes[Path(p).stem],
                    factor=1.1, heap=20000)
    assert got['resident_facades']['estimated_heap_bytes'] == 6
    assert 'CASEVO' in got['resident_facades']['blocks']
    peak = got['max_estimated_heap_bytes']
    got = mr.report(output, metadata, archive, decoder, lambda p: 1,
                    factor=1.1, heap=peak)
    assert got['fits_known_heap_model'] is True
    assert got['fits_with_compile_admission_model'] is False
    assert 'does not prove' in got['interpretation']


def test_paged_sources_remove_only_archive_and_decoder_costs():
    output, metadata, archive, decoder, sizes = fixture_data()
    sizer = lambda p: sizes[Path(p).stem]
    embedded = mr.report(output, metadata, archive, decoder, sizer)
    paged = mr.report(output, metadata, {}, '', sizer, external=True)
    assert paged['fixed_components']['archive_bytes'] == 0
    assert paged['fixed_components']['decoded_dictionary_bytes'] == 0
    assert paged['decoder']['mpy_bytes'] == 0
    assert paged['resident_facades'] == embedded['resident_facades']
    assert paged['excluded_compiled_blocks'] == embedded['excluded_compiled_blocks']
    assert paged['max_estimated_heap_bytes'] == embedded['max_estimated_heap_bytes'] - 24 - 5 - 90


@pytest.mark.parametrize('storage', ['bytes', 'base85'])
def test_actual_codec_dictionary_and_archive_payload_size(storage):
    output, metadata, unused, unused_decoder, sizes = fixture_data()
    output = {name: ('value=1234\n' + 'other=value+1\n') * 50 for name in output}
    archive, decoder = codec.encode_blocks(output, storage=storage)
    ns = {}
    exec(decoder, ns)
    got = mr.report(output, metadata, archive, decoder, lambda path: 100)
    assert got['fixed_components']['decoded_dictionary_bytes'] == len(ns['_DICT'])
    expected = (sum(map(len, archive.values())) if storage == 'bytes' else
                sum(len(r[3]) for records in archive.values() for r in records))
    assert got['fixed_components']['archive_bytes'] == expected
    assert mr.report(output, metadata, archive, decoder, lambda path: 100) == got


def test_decoder_is_parsed_without_execution():
    output, metadata, archive, unused, sizes = fixture_data()
    decoder = "raise RuntimeError('must not execute')\n_DICT=_chunk((42,0,0,b'',0,0),b'')\n"
    got = mr.report(output, metadata, archive, decoder, lambda path: 100)
    assert got['fixed_components']['decoded_dictionary_bytes'] == 42


def test_compile_error_propagates_and_cleans_tempfiles():
    output, metadata, archive, decoder, sizes = fixture_data()
    paths = []

    def broken(path):
        paths.append(Path(path))
        raise RuntimeError('mpy-cross failed')

    with pytest.raises(RuntimeError, match='mpy-cross failed'):
        mr.report(output, metadata, archive, decoder, broken)
    assert paths and not paths[0].parent.exists()


@pytest.mark.parametrize('change,match', [
    ('resident', 'missing resident'), ('payload', 'missing payload'),
    ('archive', 'missing archive'), ('sizer', 'mpy_sizer'),
    ('size', 'invalid compiled'), ('factor', 'factor'), ('heap', 'heap'),
    ('dictionary', '_DICT')])
def test_incomplete_or_invalid_evidence_is_rejected(change, match):
    output, metadata, archive, decoder, sizes = fixture_data()
    kwargs = {}
    sizer = lambda path: 100
    if change == 'resident':
        del output['CVCORE']
    elif change == 'payload':
        del output['CVRES']
    elif change == 'archive':
        del archive['CVRES']
    elif change == 'sizer':
        sizer = None
    elif change == 'size':
        sizer = lambda path: -1
    elif change == 'factor':
        kwargs['factor'] = float('nan')
    elif change == 'heap':
        kwargs['heap'] = 0
    elif change == 'dictionary':
        decoder = '_DICT=make_dictionary()\n'
    with pytest.raises(ValueError, match=match):
        mr.report(output, metadata, archive, decoder, sizer, **kwargs)
