"""Check that a built installer is ready for Cloudflare Pages Direct Upload."""
import argparse
import hashlib
import json
from pathlib import Path


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 20000
REQUIRED = (
    'index.html', 'app.js', 'installer.js', 'transport.js', 'isolation.js',
    'styles.css', 'sw.js', '_headers', 'package.json', 'package-meta.json',
    'cas-evo-calculator.zip', 'licenses.html', 'webtilp-source.zip',
    'installer-source.zip', 'vendor/COPYING', 'vendor/TIVarsLib-LICENSE',
    'vendor/assets.lock.json', 'fonts/OFL.txt',
)


def check(directory):
    directory = Path(directory)
    for name in REQUIRED:
        path = directory / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('missing publication asset: ' + name)
    files = sorted(path for path in directory.rglob('*') if path.is_file())
    if len(files) > MAX_FILES:
        raise ValueError('Cloudflare Pages file-count limit exceeded')
    for path in files:
        relative = path.relative_to(directory)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError('Cloudflare Pages 25 MiB limit exceeded: ' + str(relative))
        if path.is_symlink() or any(part.startswith('.') and part != '.nojekyll'
                                    for part in relative.parts):
            raise ValueError('unexpected hidden file or symlink: ' + str(relative))
        if relative.parts[0] not in ('vendor', 'fonts') and len(relative.parts) > 1:
            raise ValueError('unexpected publication directory: ' + str(relative))
        if len(relative.parts) == 1 and relative.name not in REQUIRED + ('.nojekyll',):
            raise ValueError('unexpected publication file: ' + str(relative))
    headers = (directory / '_headers').read_text('ascii')
    for header in ('/*', 'Cross-Origin-Opener-Policy: same-origin',
                   'Cross-Origin-Embedder-Policy: require-corp',
                   'Permissions-Policy: serial=(self), usb=(self)'):
        if header not in headers:
            raise ValueError('missing browser isolation/permission header: ' + header)
    manifest = (directory / 'package.json').read_bytes()
    metadata = json.loads((directory / 'package-meta.json').read_text('ascii'))
    if hashlib.sha256(manifest).hexdigest() != metadata['sha256']:
        raise ValueError('calculator manifest checksum mismatch')
    lock = json.loads((directory / 'vendor/assets.lock.json').read_text('ascii'))
    for name, digest in lock.items():
        if hashlib.sha256((directory / 'vendor' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('runtime asset checksum mismatch: ' + name)
    largest = max(files, key=lambda path: path.stat().st_size)
    print('Pages ready: %d files; largest %s = %d bytes (limit %d)' % (
        len(files), largest.name, largest.stat().st_size, MAX_FILE_BYTES))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    check(args.directory)
