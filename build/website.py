"""Build a self-contained installer site from the exact verified calculator ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import archive_zip
from check_pages import LEGACY
import vendor_sources

ROOT = Path(__file__).resolve().parents[1]


def build(package, output):
    output = Path(output).resolve()
    if output == ROOT or ROOT / 'website' == output:
        raise ValueError('output must not overwrite project source')
    package = Path(package)
    data = json.loads(package.read_text('ascii'))
    files = data['files']
    lock = json.loads((ROOT / 'website/vendor/assets.lock.json').read_text('ascii'))
    for name, digest in lock.items():
        if hashlib.sha256((ROOT / 'website/vendor' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('pinned runtime asset changed: ' + name)
    output.mkdir(parents=True, exist_ok=True)
    for name in ['index.html', 'styles.css', 'app.js', 'installer.js', 'transport.js',
                 'isolation.js', 'sw.js', 'licenses.html', '_headers'] + list(LEGACY):
        shutil.copyfile(ROOT / 'website' / name, output / name)
    # The records of earlier-release objects that the installer may remove or replace.
    legacy = {}
    for name in LEGACY:
        blob = (ROOT / 'website' / name).read_bytes()
        if json.loads(blob).get('schema') != 1:
            raise ValueError('unexpected legacy manifest schema: ' + name)
        legacy[name] = hashlib.sha256(blob).hexdigest()
    for name in ['vendor', 'fonts']:
        shutil.copytree(ROOT / 'website' / name, output / name, dirs_exist_ok=True)
    encoded = (json.dumps(data, separators=(',', ':')) + '\n').encode('ascii')
    (output / 'package.json').write_bytes(encoded)
    (output / 'package-meta.json').write_text(json.dumps(dict(
        sha256=hashlib.sha256(encoded).hexdigest(), count=len(files), totalBytes=data['totalBytes'],
        legacy=legacy
    )) + '\n', 'ascii')
    (output / 'cas-evo-calculator.zip').unlink(missing_ok=True)    # its name before v1.0.2
    archive_zip.build(package.parent, output / 'microcas-calculator.zip')
    shutil.copyfile(vendor_sources.build(), output / 'webtilp-source.zip')
    # Corresponding source for our browser integration and its build tooling.
    # Product/direction briefs and review artifacts never enter the served site.
    with zipfile.ZipFile(output / 'installer-source.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / 'website').glob('*')):
            if path.is_file():
                archive.write(path, 'website/' + path.name)
        for path in sorted((ROOT / 'website/tests').glob('*.js')):
            archive.write(path, 'website/tests/' + path.name)
        for name in ('website.py', 'serve_website.py', 'vendor_sources.py', 'archive_zip.py', 'package_archive.mjs',
                     'legacy_manifest.mjs'):
            archive.write(ROOT / 'build' / name, 'build/' + name)
    (output / '.nojekyll').touch()
    shutil.copyfile(ROOT / 'build/serve_website.py', output.parent / 'serve_installer.py')
    (output.parent / 'START-INSTALLER.txt').write_text(
        'Run: python serve_installer.py --directory website\n'
        'Then open http://127.0.0.1:4173 in Chrome or Edge.\n'
        'A USB data cable and browser device permission are required.\n'
        'Physical calculator acceptance remains separate from software tests.\n', 'ascii')
    print('Installer: %d verified files, %d transfer bytes -> %s' % (len(files), data['totalBytes'], output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'dist/archive-transfer/package.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist/website')
    args = parser.parse_args()
    build(args.package, args.out)
