"""Desktop-only, provisional accounting for the independently loaded release.

The .mpy multiplier is an estimate, not a measurement of EVO heap allocation.
Even a passing subtotal cannot establish fit: runtime objects and lazy families
are deliberately listed as exclusions. No project source or build output changes.
"""
import ast
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory


NODE_BYTES = 16384
RESERVE_BYTES = 3072


def _dictionary_bytes(decoder):
    """Read the codec's declared expansion length without executing its source."""
    for node in ast.parse(decoder).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == '_DICT' for t in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id != '_chunk' or len(value.args) != 2:
                break
            record = ast.literal_eval(value.args[0])
            if isinstance(record, tuple) and len(record) in (4, 6):
                size = record[0]
                if type(size) is int and 0 <= size <= 4096:
                    return size
            break
        value = ast.literal_eval(value)
        if isinstance(value, bytes) and len(value) <= 4096:
            return len(value)
        break
    raise ValueError('decoder has no recognized bounded _DICT declaration')


def _archive_bytes(archive):
    """Count resident encoded bytes, not the escaped Python literal on disk."""
    size = 0
    for value in archive.values():
        if isinstance(value, bytes):
            size += len(value)  # Flat binary records include their packed headers.
        elif isinstance(value, tuple) and value:
            for record in value:
                if not (isinstance(record, tuple) and len(record) == 4 and
                        isinstance(record[3], str)):
                    raise ValueError('unrecognized archive record')
                size += len(record[3].encode('ascii'))
        else:
            raise ValueError('unrecognized archive storage')
    return size


def report(output, metadata, archive, decoder, sizer, factor=1.8, heap=173360, external=False):
    """Return JSON-ready stage estimates; ``sizer(path)`` returns .mpy bytes.

    ``output`` contains transformed source blocks, not CODE-string wrappers.
    ``metadata`` is phases.pack/release.prepare metadata including ``groups``.
    Only grouped core owners and the controller are always resident. Other
    facades and their payloads are lazy, even if their local phase is 'resident'.
    An optional unarchived CASEVO block accounts for the entry/loader if the
    caller includes their small source together, without the archive literal.

    Each stage sums archive bytes, decoded dictionary bytes, ceil(.mpy * factor)
    for each live block and decoder, node backing arrays, and a fixed reserve.
    'resident' means no optional phase; ui/input/print are mutually exclusive.
    Compiler admission is a separate requirement, not a measured peak. A raw
    .mpy subtotal is also supplied for sensitivity analysis, not as a proven
    lower bound on device memory. Temporary files are removed even on failure.
    """
    if not callable(sizer):
        raise ValueError('memory report requires an mpy_sizer callable')
    if isinstance(factor, bool) or not math.isfinite(factor) or factor < 1:
        raise ValueError('factor must be finite and at least one')
    if type(heap) is not int or heap <= 0:
        raise ValueError('heap must be a positive byte count')
    groups = metadata['groups']
    payloads = metadata['payloads']
    controller = metadata['controller']
    core = set(groups)
    resident = core | {controller}
    if 'CASEVO' in output:
        resident.add('CASEVO')
    if not resident <= set(output):
        raise ValueError('missing resident source: ' + ', '.join(sorted(resident - set(output))))
    if not set(payloads) <= set(output):
        raise ValueError('missing payload source')
    if resident & set(payloads):
        raise ValueError('a source cannot be both a facade and payload')
    if not set(archive) <= set(output):
        raise ValueError('archive contains an unknown source')
    missing_archive = set(output) - set(archive) - {'CASEVO'}
    if missing_archive and not external:
        raise ValueError('missing archive blocks: ' + ', '.join(sorted(missing_archive)))
    by_phase = {'resident': [], 'ui': [], 'input': [], 'print': []}
    for name, info in sorted(payloads.items()):
        if info['module'] in core:
            by_phase.setdefault(info['phase'], []).append(name)
        if type(info['required_free']) is not int or info['required_free'] < 0:
            raise ValueError('invalid compile admission: ' + name)
    sizes = {}
    with TemporaryDirectory(prefix='cas-evo-memory-') as temp:
        for name in sorted(output):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) or name == '_decoder':
                raise ValueError('invalid source block name: ' + name)
            path = Path(temp) / (name + '.py')
            path.write_text(output[name], encoding='ascii', newline='\n')
            size = sizer(str(path))
            if type(size) is not int or size <= 0:
                raise ValueError('invalid compiled size: ' + name)
            sizes[name] = size
        path = Path(temp) / '_decoder.py'
        path.write_text(decoder, encoding='ascii', newline='\n')
        decoder_size = 0 if external else sizer(str(path))
        if not external and (type(decoder_size) is not int or decoder_size <= 0):
            raise ValueError('invalid compiled decoder size')
    scaled = {name: math.ceil(size * factor) for name, size in sizes.items()}

    def subtotal(names):
        return {'blocks': sorted(names), 'mpy_bytes': sum(sizes[n] for n in names),
                'estimated_heap_bytes': sum(scaled[n] for n in names)}

    facade = subtotal(resident)
    phase_code = {phase: subtotal(names) for phase, names in sorted(by_phase.items())}
    fixed = {'archive_bytes': _archive_bytes(archive),
             'decoded_dictionary_bytes': 0 if external else _dictionary_bytes(decoder),
             'node_backing_bytes': NODE_BYTES, 'reserve_bytes': RESERVE_BYTES}
    fixed_total = sum(fixed.values())
    decoder_heap = math.ceil(decoder_size * factor)
    base = fixed_total + decoder_heap + facade['estimated_heap_bytes']
    base += phase_code['resident']['estimated_heap_bytes']
    raw_base = fixed_total + decoder_size + facade['mpy_bytes']
    raw_base += phase_code['resident']['mpy_bytes']
    stages = {}
    for phase, component in phase_code.items():
        extra = 0 if phase == 'resident' else component['estimated_heap_bytes']
        raw_extra = 0 if phase == 'resident' else component['mpy_bytes']
        names = component['blocks']
        admission = max((payloads[n]['required_free'] for n in names), default=0)
        total = base + extra
        stages[phase] = {'resident_subtotal_bytes': base,
                         'phase_code_bytes': extra,
                         'estimated_heap_bytes': total,
                         'raw_mpy_model_bytes': raw_base + raw_extra,
                         'headroom_bytes': heap - total,
                         'fits_known_heap_model': total <= heap,
                         'max_compile_admission_bytes': admission,
                         'headroom_after_admission_bytes': heap - total - admission}
    counted = resident | set(n for names in by_phase.values() for n in names)
    excluded = ['namespace dictionaries and their entries',
                'object headers, allocator rounding and fragmentation beyond reserve',
                'qstr pool and native-module allocations not represented by .mpy scaling',
                'working data, nodes beyond backing arrays, session/history and caches',
                'loaded lazy families, their code/data and command-specific dependencies',
                'native function pages, including suspended generator code and globals',
                'decoded source buffers and compiler temporaries beyond fixed reserve',
                'phase overlap or lingering references if the unloading contract fails']
    if 'CASEVO' not in output:
        excluded.append('inline entry and loader code absent from supplied blocks')
    else:
        excluded.append('loader code unless included in the supplied CASEVO source')
    return {'status': 'PROVISIONAL', 'device_measured': False,
            'interpretation': 'Model only: a pass does not prove calculator heap fit.',
            'known_heap_bytes': heap, 'compiled_to_heap_factor': factor,
            'rounding': 'ceil for each independently compiled block',
            'fixed_components': fixed, 'fixed_subtotal_bytes': fixed_total,
            'decoder': {'mpy_bytes': decoder_size, 'estimated_heap_bytes': decoder_heap},
            'resident_facades': facade, 'phase_payloads': phase_code,
            'block_mpy_bytes': sizes, 'stages': stages,
            'min_raw_mpy_model_bytes': min(s['raw_mpy_model_bytes'] for s in stages.values()),
            'max_estimated_heap_bytes': max(s['estimated_heap_bytes'] for s in stages.values()),
            'max_compile_admission_bytes': max((v['required_free'] for v in payloads.values()), default=0),
            'fits_known_heap_model': all(s['fits_known_heap_model'] for s in stages.values()),
            'fits_with_compile_admission_model': all(s['headroom_after_admission_bytes'] >= 0
                                                     for s in stages.values()),
            'excluded_compiled_blocks': subtotal(set(output) - counted),
            'exclusions': excluded}
