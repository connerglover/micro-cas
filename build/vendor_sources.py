"""Mirror pinned WebTILP corresponding source beside its distributed WASM."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output=ROOT / 'dist/vendor-source', lock=ROOT / 'website/vendor/sources.lock.json'):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = json.loads(Path(lock).read_text('utf-8'))
    for row in records:
        target = output / row['name']
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
            with urllib.request.urlopen(row['url'], timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('source download checksum mismatch: ' + row['name'])
            target.write_bytes(data)
    with zipfile.ZipFile(output / 'webtilp-source.zip', 'w', compression=zipfile.ZIP_STORED) as archive:
        for row in records:
            info = zipfile.ZipInfo(row['name'], date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, (output / row['name']).read_bytes())
        archive.writestr('sources.lock.json', Path(lock).read_bytes())
        archive.writestr('README.txt', 'Pinned WebTILP and linked dependency source. The tilibs archive contains\nwebtilp/build_wasm_deps.sh, patches, build instructions and licenses.\nDeployment build records accompany the installer under vendor/.\n')
    return output / 'webtilp-source.zip'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/vendor-source')
    args = parser.parse_args()
    print(build(args.out))
