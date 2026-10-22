"""Compile the library packs for EVO archive; keep the source launcher CAS for RAM.

Requires MicroPython v1.12 mpy-cross, not the v1.29 sizing compiler.
The EVO ABI is MPY v5, feature flags 3, with 31-bit small integers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import bundle

COMPILER_REVISION = '1f371947309c5ea6023b6d9065415697cbc75578'
LAUNCHERS = {'CAS.py'}
HEADER = b'M\x05\x03\x1f'


def mpy_flags(man, pack):
    """Extra mpy-cross flags of a pack: -O3 (no line-number tables) for a TIGHT pack."""
    return ['-O3'] if pack in getattr(man, 'TIGHT', ()) else []


def compile_archive(package, output, compiler):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source_dir = output / 'source'
    source_dir.mkdir(exist_ok=True)
    for stale in list(output.glob('*.mpy')) + list(output.glob('*.py')):
        stale.unlink()                    # never mix objects from different builds
    man = bundle.load_manifest()
    result = {'schema': 2, 'version': 'packs-v1', 'compilerRevision': COMPILER_REVISION,
              'abi': 'MPY v5.3 / 31-bit small ints', 'runtimeCompilation': False,
              'files': []}
    with zipfile.ZipFile(package) as archive:
        meta = json.loads(archive.read('release.json'))
        if meta.get('format') != 'packs-v1':
            raise ValueError('not a pack release: ' + str(meta.get('format')))
        result['release'] = meta['release']
        for name, info in sorted(meta['files'].items()):
            source = archive.read(name)
            if len(source) != info['bytes'] or hashlib.sha256(source).hexdigest() != info['sha256']:
                raise ValueError('source checksum mismatch: ' + name)
            (source_dir / name).write_bytes(source)
            launcher = name in LAUNCHERS
            module = name[:-3]
            if launcher:
                target = output / name
                target.write_bytes(source)
            else:
                target = output / (module + '.mpy')
                subprocess.run([str(compiler), '-mcache-lookup-bc', '-msmall-int-bits=31'] +
                               mpy_flags(man, module) +
                               ['-s', name, '-o', str(target), str(source_dir / name)], check=True)
                data = target.read_bytes()
                if data[:4] != HEADER:
                    raise ValueError('wrong EVO bytecode ABI: ' + target.name)
                if len(data) > man.PACKMAX:
                    raise ValueError('%s is %d bytes, over PACKMAX %d' % (target.name, len(data), man.PACKMAX))
            data = target.read_bytes()
            result['files'].append(dict(name=target.name, module=module,
                kind='source' if launcher else 'bytecode',
                destination='ram' if launcher else 'archive', bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), sourceBytes=info['bytes'],
                sourceSha256=info['sha256'], pack=meta['kinds'].get(module, 'launcher')))
    result['totalBytes'] = sum(f['bytes'] for f in result['files'])
    result['ramSourceBytes'] = sum(f['bytes'] for f in result['files'] if f['destination'] == 'ram')
    (output / 'archive.json').write_text(json.dumps(result, indent=2) + '\n', 'ascii')
    (source_dir / 'release.json').write_text(json.dumps(meta, indent=1, sort_keys=True) + '\n',
                                             'ascii')
    print('%d files; %d bytecode/source bytes; %d launcher source bytes in RAM' %
          (len(result['files']), result['totalBytes'], result['ramSourceBytes']))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'dist/cas-evo-packs.zip')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/archive')
    parser.add_argument('--mpy-cross', type=Path, required=True)
    args = parser.parse_args()
    compile_archive(args.package, args.out, args.mpy_cross)
