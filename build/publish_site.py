"""Publish a verified website to pages without switching or rewriting main."""
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


def publish(directory, run_url, repo=ROOT):
    check(directory)
    source = git(repo, 'rev-parse', 'HEAD')
    if remote_head(repo, 'main') != source:
        print('Skipped: this build is no longer the current main commit.')
        return None
    parent = remote_head(repo, 'pages')
    if parent:
        git(repo, 'fetch', '--no-tags', 'origin', 'refs/heads/pages')
        parent = git(repo, 'rev-parse', 'FETCH_HEAD')
        metadata = json.loads(git(repo, 'show', parent + ':deployment.json'))
        if metadata.get('generator') != GENERATOR:
            raise ValueError('refusing to overwrite an unrelated pages branch')
    entries = directory_entries(TEMPLATES)
    entries['public'] = directory_entries(directory)
    entries['deployment.json'] = (json.dumps({
        'generator': GENERATOR, 'source_commit': source, 'run_url': run_url,
    }, indent=2) + '\n').encode('ascii')
    snapshot = tree(repo, entries)
    if parent and git(repo, 'rev-parse', parent + '^{tree}') == snapshot:
        print('No publication changes.')
        return parent
    message = ('deploy: website from %s\n\nSource: %s\nBuild: %s\n\n'
               'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n'
               % (source[:12], source, run_url)).encode('utf-8')
    args = ['commit-tree', snapshot]
    if parent:
        args.extend(['-p', parent])
    commit = git(repo, *args, data=message)
    if remote_head(repo, 'main') != source:
        print('Skipped: main advanced while preparing the website.')
        return None
    # First publication is an independent root; later publications preserve its
    # history. No force push: a concurrent pages update safely rejects this push.
    git(repo, 'push', 'origin', commit + ':refs/heads/pages')
    print('Published %s from main %s' % (commit, source))
    return commit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--run-url', required=True)
    args = parser.parse_args()
    try:
        publish(args.directory, args.run_url)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr.decode('utf-8', errors='replace')) from error
