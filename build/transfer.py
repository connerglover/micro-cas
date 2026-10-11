"""Check the ASCII .py size limit reproduced in TI Connect Evo 7.1.0.792.

This is a converter-size gate, not proof of USB transfer or calculator execution.
See docs/reference/transfer-limits.md for the actual-converter boundary tests.
"""
import argparse
from pathlib import Path
import re


CONVERTER_VERSION = '7.1.0.792'
OBJECT_LIMIT = 65535
OBJECT_OVERHEAD = 18


def inspect_source(source, filename):
    """Account for source bytes plus the Python object header and module name."""
    path = Path(filename)
    name = path.stem.upper()
    if path.suffix.lower() != '.py' or not re.fullmatch(r'[A-Z][A-Z0-9]{0,7}', name):
        raise ValueError('invalid calculator Python name: ' + str(filename))
    source.decode('ascii')  # The release deliberately avoids encoding/conversion ambiguity.
    limit = OBJECT_LIMIT - OBJECT_OVERHEAD - len(name)
    return {'name': name, 'source_bytes': len(source), 'max_source_bytes': limit,
            'python_object_bytes': len(source) + OBJECT_OVERHEAD + len(name),
            'fits_converter_limit': 0 < len(source) <= limit}


def require_transferable(files):
    """Reject every known-invalid generated file before publishing a package."""
    failures = []
    for name, source in files.items():
        info = inspect_source(source, name)
        if not info['fits_converter_limit']:
            failures.append('%s: %d source bytes; TI Connect Evo limit is %d' %
                            (name, info['source_bytes'], info['max_source_bytes']))
    if failures:
        raise ValueError('Not transferable:\n' + '\n'.join(failures))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args(argv)
    failed = False
    for path in args.files:
        info = inspect_source(path.read_bytes(), path.name)
        fits = info['fits_converter_limit']
        failed |= not fits
        print('%s: %d / %d source bytes: %s' %
              (path.name, info['source_bytes'], info['max_source_bytes'],
               'within converter size limit (device execution unverified)' if fits else 'REJECTED'))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
