"""Publish a verified website to pages without switching or rewriting the source ref.

The workflow publishes from a v* tag (docs/HOSTING.md): the build's commit must still be what
that tag names on the remote, and pages never goes back to an older release than it holds.
"""
import argparse
import json
from pathlib import Path
import subprocess

from check_pages import check


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).resolve().parent / 'cloudflare'
GENERATOR = 'cas-evo/build/publish_site.py'


def git(repo, *args, data=None):
    return subprocess.run(['git', '-C', str(repo), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout.decode('utf-8').strip()


def remote_head(repo, branch):
    result = git(repo, 'ls-remote', '--heads', 'origin', 'refs/heads/' + branch)
    return result.split()[0] if result else None


def remote_ref(repo, ref):
    """The commit a remote ref names (an annotated tag peeled to its commit), or None."""
    result = git(repo, 'ls-remote', 'origin', ref, ref + '^{}')
    found = dict(reversed(line.split('\t')) for line in result.splitlines() if line)
    return found.get(ref + '^{}') or found.get(ref)


def version(ref):
    """(0, 1, 0) for refs/tags/v0.1.0; None for a ref that is not a v* release tag."""
    name = ref.rsplit('/', 1)[-1]
    if not ref.startswith('refs/tags/v'):
        return None
    try:
        return tuple(int(part) for part in name[1:].split('-')[0].split('.'))
    except ValueError:
        return None


def tree(repo, entries):
    """Write exact bytes to Git, bypassing source-checkout line-ending filters."""
    records = []
    for name, value in sorted(entries.items()):
        if isinstance(value, dict):
            mode, kind, digest = '040000', 'tree', tree(repo, value)
        else:
            mode, kind = '100644', 'blob'
            digest = git(repo, 'hash-object', '-w', '--stdin', data=value)
        records.append(('%s %s %s\t%s\0' % (mode, kind, digest, name)).encode('utf-8'))
    return git(repo, 'mktree', '-z', data=b''.join(records))


def directory_entries(directory):
    entries = {}
    for path in sorted(Path(directory).iterdir()):
        if path.is_symlink():
            raise ValueError('symlinks cannot be published: ' + str(path))
        entries[path.name] = directory_entries(path) if path.is_dir() else path.read_bytes()
    return entries


def publish(directory, run_url, repo=ROOT, ref='refs/heads/main'):
    check(directory)
    source = git(repo, 'rev-parse', 'HEAD')
    if remote_ref(repo, ref) != source:
        print('Skipped: this build is no longer what %s names.' % ref)
        return None
    parent = remote_head(repo, 'pages')
    if parent:
        git(repo, 'fetch', '--no-tags', 'origin', 'refs/heads/pages')
        parent = git(repo, 'rev-parse', 'FETCH_HEAD')
        metadata = json.loads(git(repo, 'show', parent + ':deployment.json'))
        if metadata.get('generator') != GENERATOR:
            raise ValueError('refusing to overwrite an unrelated pages branch')
        held = version(metadata.get('source_ref', ''))
        if held is not None and version(ref) is not None and version(ref) < held:
            print('Skipped: pages already holds the newer release %s.' % metadata['source_ref'])
            return None
    entries = directory_entries(TEMPLATES)
    entries['public'] = directory_entries(directory)
    entries['deployment.json'] = (json.dumps({
        'generator': GENERATOR, 'source_commit': source, 'source_ref': ref, 'run_url': run_url,
    }, indent=2) + '\n').encode('ascii')
    snapshot = tree(repo, entries)
    if parent and git(repo, 'rev-parse', parent + '^{tree}') == snapshot:
        print('No publication changes.')
        return parent
    message = ('deploy: website from %s\n\nSource: %s (%s)\nBuild: %s\n\n'
               'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n'
               % (source[:12], source, ref, run_url)).encode('utf-8')
    args = ['commit-tree', snapshot]
    if parent:
        args.extend(['-p', parent])
    commit = git(repo, *args, data=message)
    if remote_ref(repo, ref) != source:
        print('Skipped: %s moved while preparing the website.' % ref)
        return None
    # First publication is an independent root; later publications preserve its
    # history. No force push: a concurrent pages update safely rejects this push.
    git(repo, 'push', 'origin', commit + ':refs/heads/pages')
    print('Published %s from %s %s' % (commit, ref, source))
    return commit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--run-url', required=True)
    parser.add_argument('--ref', default='refs/heads/main',
                        help='the remote ref this build is from (the workflow: refs/tags/v...)')
    args = parser.parse_args()
    try:
        publish(args.directory, args.run_url, ref=args.ref)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.decode('utf-8', errors='replace')) from error
