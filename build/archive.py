"""Compile companions for EVO archive; retain two source launchers for RAM.

Requires MicroPython v1.12 mpy-cross, not the v1.29 sizing compiler.
The EVO ABI is MPY v5, feature flags 3, with 31-bit small integers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import archive_modules

ROOT = Path(__file__).resolve().parents[1]
COMPILER_REVISION = '1f371947309c5ea6023b6d9065415697cbc75578'
LAUNCHERS = {'CASEVO.py', 'CVTEST.py'}


def compile_archive(package, output, compiler):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source_dir = output / 'source'
    source_dir.mkdir(exist_ok=True)
    result = {'schema': 2, 'version': 'v1', 'compilerRevision': COMPILER_REVISION,
              'abi': 'MPY v5.3 / 31-bit small ints', 'runtimeCompilation': False,
              'files': []}

    compiled = {}

    def compile_one(name, source):
        path, target = source_dir / name, output / (name[:-3] + '.mpy')
        if compiled.get(name) == source:
            return target.stat().st_size
        path.write_bytes(source)
        subprocess.run([str(compiler), '-mcache-lookup-bc', '-msmall-int-bits=31',
                        '-s', name, '-o', str(target), str(path)], check=True)
        data = target.read_bytes()
        if data[:4] != b'M\x05\x03\x1f':
            raise ValueError('wrong EVO bytecode ABI: ' + target.name)
        compiled[name] = source
        return len(data)

    with zipfile.ZipFile(package) as archive:
        meta = json.loads(archive.read('release.json'))
        originals = {}
        for name, info in sorted(meta['files'].items()):
            source = archive.read(name)
            if len(source) != info['bytes'] or hashlib.sha256(source).hexdigest() != info['sha256']:
                raise ValueError('source checksum mismatch: ' + name)
            originals[name] = source
        sources = archive_modules.transform(originals, meta)
        budgets, sizes = {}, {}
        for name in sorted(set(meta['payloads']) | set(meta['runtime_modules'].values())):
            size = compile_one(name + '.py', sources[name + '.py'])
            # Import allocates bytecode, objects and a small module namespace.
            # This is an admission reserve, never a substitute for native tests.
            if name in meta['payloads']:
                budgets[name] = size * 2 + 2048
            sizes[name] = size
        sources = archive_modules.set_admission(sources, meta, budgets, sizes)
        result['phaseRequiredFree'] = budgets
        result['runtimeModuleMpyBytes'] = {name: sizes[name] for name in sorted(set(meta['runtime_modules'].values()))}
        for name, source in sorted(sources.items()):
            info = meta['files'][name]
            path = source_dir / name
            path.write_bytes(source)
            launcher = name in LAUNCHERS
            filename = name if launcher else name[:-3] + '.mpy'
            target = output / filename
            if launcher:
                target.write_bytes(source)
            else:
                compile_one(name, source)
            data = target.read_bytes()
            result['files'].append(dict(name=filename, module=name[:-3],
                kind='source' if launcher else 'bytecode',
                destination='ram' if launcher else 'archive', bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), sourceBytes=info['bytes'],
                sourceSha256=info['sha256'], compiledSourceBytes=len(source),
                compiledSourceSha256=hashlib.sha256(source).hexdigest()))
    result['totalBytes'] = sum(f['bytes'] for f in result['files'])
    result['ramSourceBytes'] = sum(f['bytes'] for f in result['files'] if f['destination'] == 'ram')
    (output / 'archive.json').write_text(json.dumps(result, indent=2) + '\n', 'ascii')
    # The existing strict-depth artifact harness also runs the exact initializer
    # inputs to the bytecode compiler. Native tests separately run the MPY bytes.
    host_meta = dict(meta, format='archive-initializers-v1')
    host_meta['files'] = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sources.items()}
    host_meta['file_bytes'] = len(sources['CASEVO.py'])
    host_meta['sha256'] = host_meta['files']['CASEVO.py']['sha256']
    (source_dir / 'release.json').write_text(json.dumps(host_meta, indent=1) + '\n', 'ascii')
    print('%d files; %d bytecode/source bytes; %d launcher source bytes in RAM' %
          (len(result['files']), result['totalBytes'], result['ramSourceBytes']))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'dist/cas-evo-v1.zip')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/archive')
    parser.add_argument('--mpy-cross', type=Path, required=True)
    args = parser.parse_args()
    compile_archive(args.package, args.out, args.mpy_cross)
