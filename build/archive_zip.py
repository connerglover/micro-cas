"""Create the calculator download from checksum-verified EVO transfer objects."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(directory, output):
    directory, output = Path(directory), Path(output)
    manifest = json.loads((directory / 'package.json').read_text('ascii'))
    if manifest.get('schema') != 2 or manifest.get('runtimeCompilation') is not False:
        raise ValueError('not a compiled archive package')
    files, seen = {}, set()
    for item in manifest['files']:
        name, module = item['name'], item['module']
        launcher = module in ('CASEVO', 'CVTEST')
        extension = '.8xpy2' if launcher else '.8mp2'
        if (not re.fullmatch(r'[A-Z][A-Z0-9]{0,7}', module) or name != module + extension
                or module in seen or item['destination'] != ('ram' if launcher else 'archive')):
            raise ValueError('invalid archive filename/destination: ' + name)
        data = (directory / name).read_bytes()
        if (base64.b64decode(item['data'], validate=True) != data or len(data) != item['bytes']
                or hashlib.sha256(data).hexdigest() != item['sha256']):
            raise ValueError('transfer object changed: ' + name)
        # Do not publish an arbitrary renamed .mpy as a TI transfer object.
        if not data.startswith(b'\xbf\x68metaData'):
            raise ValueError('missing EVO CBOR metadata header: ' + name)
        files[name] = data
        seen.add(module)
    if not {'CASEVO', 'CVTEST'} <= seen or sum(map(len, files.values())) != manifest['totalBytes']:
        raise ValueError('incomplete calculator package')
    if sum(map(len, files.values())) > 3500000:
        raise ValueError('calculator storage budget exceeded')
    public = dict(manifest, files=[{k: v for k, v in item.items() if k != 'data'} for item in manifest['files']])
    files['archive.json'] = (json.dumps(public, indent=2) + '\n').encode('ascii')
    files['INSTALL.md'] = (ROOT / 'docs/INSTALL.md').read_bytes()
    files['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
        for name, data in sorted(files.items())).encode('ascii')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    temporary.replace(output)
    print('%s: %d transfer objects, %d bytes zipped' % (output, len(seen), output.stat().st_size))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'dist/archive-transfer')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/cas-evo-calculator.zip')
    args = parser.parse_args()
    build(args.input, args.out)
