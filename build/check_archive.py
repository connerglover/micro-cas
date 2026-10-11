"""Run strict-depth acceptance on the verified inputs to the EVO compiler.

Native micro_smoke --archive separately executes the actual MPY v5 bytecode.
"""
import hashlib
import json
from pathlib import Path

from check_release import Release, ROOT


def verify_sources(archive, dist=ROOT / 'dist'):
    archive = Path(archive)
    manifest = json.loads((archive / 'archive.json').read_text('ascii'))
    meta = json.loads((Path(dist) / 'release.json').read_text('ascii'))
    files = {}
    for info in manifest['files']:
        name = info['module'] + '.py'
        data = (archive / 'source' / name).read_bytes()
        if len(data) != info['compiledSourceBytes'] or hashlib.sha256(data).hexdigest() != info['compiledSourceSha256']:
            raise ValueError('compiler input changed: ' + name)
        if info['sourceSha256'] != meta['files'][name]['sha256']:
            raise ValueError('archive built from a different release: ' + name)
        files[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    if files.keys() != meta['files'].keys():
        raise ValueError('archive module set differs from source release')
    meta.update(format='archive-initializers-v1', files=files,
                file_bytes=files['CASEVO.py']['bytes'], sha256=files['CASEVO.py']['sha256'])
    (archive / 'source/release.json').write_text(json.dumps(meta) + '\n', 'ascii')
    return archive / 'source'


class ArchiveRelease(Release):
    def __init__(self, archive=ROOT / 'dist/archive', **kwargs):
        super().__init__(verify_sources(archive), **kwargs)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'dist/archive')
    args = parser.parse_args()
    app = ArchiveRelease(args.archive).boot()
    for command, want in [('2+3', '5'), ('diff(x^3,x)', '3*x^2'), ('sum(k^2,k,1,10)', '385')]:
        assert app.go(command)[:2] == ('ans', want)
        app.assert_clean()
    print('Archive initializer acceptance passed; strict depth %d/8' % app.max_depth)
