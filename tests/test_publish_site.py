"""Exercise website publication against a real local Git remote."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build'))
import publish_site
from check_pages import LEGACY, REQUIRED

pytestmark = [pytest.mark.no_depth, pytest.mark.no_invariants]


@pytest.fixture
def publication(tmp_path):
    repo, remote, site = (tmp_path / name for name in ('repo', 'remote.git', 'site'))
    for directory in (repo, remote, site):
        directory.mkdir()
    git = lambda *args: publish_site.git(repo, *args)
    publish_site.git(remote, 'init', '--bare')
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test Publisher')
    git('config', 'user.email', 'publisher@example.invalid')
    git('config', 'core.autocrlf', 'true')
    (repo / 'private.txt').write_text('Not a website asset.\n')
    git('add', '.')
    git('commit', '-m', 'source')
    git('remote', 'add', 'origin', str(remote))
    git('push', 'origin', 'main')
    for name in REQUIRED:
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture\r\n')
    manifest = b'{"files": []}\n'
    (site / 'package.json').write_bytes(manifest)
    legacy = b'{"schema": 1, "files": []}\n'
    for name in LEGACY:
        (site / name).write_bytes(legacy)
    (site / 'package-meta.json').write_text(json.dumps({
        'sha256': hashlib.sha256(manifest).hexdigest(),
        'legacy': dict((name, hashlib.sha256(legacy).hexdigest()) for name in LEGACY),
    }))
    (site / 'vendor/assets.lock.json').write_text('{}')
    (site / '_headers').write_text(
        '/*\n  Cross-Origin-Opener-Policy: same-origin\n'
        '  Cross-Origin-Embedder-Policy: require-corp\n'
        '  Permissions-Policy: serial=(self), usb=(self)\n')
    return repo, site, git


def test_publication_is_independent_exact_and_preserves_source(publication):
    repo, site, git = publication
    main = git('rev-parse', 'HEAD')
    commit = publish_site.publish(site, 'https://example.invalid/build/1', repo)
    assert publish_site.remote_head(repo, 'pages') == commit
    assert git('rev-list', '--parents', '-n', '1', commit) == commit
    assert git('rev-parse', 'HEAD') == main
    assert publish_site.remote_head(repo, 'main') == main
    assert git('status', '--porcelain') == ''
    files = git('ls-tree', '-r', '--name-only', commit).splitlines()
    assert 'private.txt' not in files
    assert 'public/index.html' in files
    assert not any(name.startswith('.github/') for name in files)
    raw = subprocess.check_output(['git', '-C', str(repo), 'show', commit + ':public/index.html'])
    assert raw == (site / 'index.html').read_bytes()  # No CRLF conversion.
    config = json.loads(git('show', commit + ':wrangler.jsonc'))
    assert config['assets']['directory'] == './public'
    assert 'main' not in config  # Assets-only Worker.
    assert publish_site.publish(site, 'https://example.invalid/build/1', repo) == commit


def test_update_keeps_history_and_removes_stale_assets(publication):
    repo, site, git = publication
    old_asset = site / 'fonts/old.ttf'
    old_asset.write_bytes(b'old')
    first = publish_site.publish(site, 'https://example.invalid/build/1', repo)
    old_asset.unlink()
    (site / 'index.html').write_bytes(b'updated\n')
    second = publish_site.publish(site, 'https://example.invalid/build/2', repo)
    assert git('rev-parse', second + '^') == first
    assert 'public/fonts/old.ttf' not in git('ls-tree', '-r', '--name-only', second).splitlines()
    assert git('show', first + ':public/fonts/old.ttf') == 'old'


def test_stale_build_cannot_publish(publication):
    repo, site, git = publication
    old = git('rev-parse', 'HEAD')
    git('commit', '--allow-empty', '-m', 'new main')
    git('push', 'origin', 'main')
    git('checkout', '--detach', old)
    assert publish_site.publish(site, 'https://example.invalid/old-build', repo) is None
    assert publish_site.remote_head(repo, 'pages') is None


def test_unrelated_pages_branch_is_preserved(publication):
    repo, site, git = publication
    (repo / 'deployment.json').write_text('{"generator": "someone-else"}')
    git('add', '.')
    git('commit', '-m', 'unrelated website')
    git('push', 'origin', 'main', 'HEAD:pages')
    previous = publish_site.remote_head(repo, 'pages')
    with pytest.raises(ValueError, match='unrelated pages branch'):
        publish_site.publish(site, 'https://example.invalid/build/1', repo)
    assert publish_site.remote_head(repo, 'pages') == previous


def test_invalid_artifact_cannot_publish(publication):
    repo, site, git = publication
    (site / 'package.json').write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='checksum mismatch'):
        publish_site.publish(site, 'https://example.invalid/build/1', repo)
    assert publish_site.remote_head(repo, 'pages') is None


@pytest.mark.parametrize('name', LEGACY)
def test_altered_legacy_record_cannot_publish(publication, name):
    repo, site, git = publication
    (site / name).write_bytes(b'{"schema": 1, "files": ["changed"]}\n')
    with pytest.raises(ValueError, match='legacy manifest checksum mismatch'):
        publish_site.publish(site, 'https://example.invalid/build/1', repo)
    assert publish_site.remote_head(repo, 'pages') is None


# -- v0.1.0: the workflow publishes from v* tags (docs/HOSTING.md) --------------------------------

def tag(git, name, annotated=True):
    if annotated:
        git('tag', '-a', name, '-m', 'release ' + name)
    else:
        git('tag', name)
    git('push', 'origin', 'refs/tags/' + name)


@pytest.mark.parametrize('annotated', [True, False])
def test_a_tag_build_publishes_and_records_its_ref(publication, annotated):
    repo, site, git = publication
    tag(git, 'v0.1.0', annotated)
    commit = publish_site.publish(site, 'https://example.invalid/build/1', repo,
                                  'refs/tags/v0.1.0')
    assert commit and publish_site.remote_head(repo, 'pages') == commit
    meta = json.loads(git('show', commit + ':deployment.json'))
    assert meta['source_ref'] == 'refs/tags/v0.1.0'
    assert meta['source_commit'] == git('rev-parse', 'HEAD')


def test_a_moved_or_missing_tag_cannot_publish(publication):
    repo, site, git = publication
    assert publish_site.publish(site, 'https://example.invalid/b/1', repo,
                                'refs/tags/v0.1.0') is None           # no such tag
    old = git('rev-parse', 'HEAD')
    git('commit', '--allow-empty', '-m', 'later')
    tag(git, 'v0.1.0')
    git('checkout', '--detach', old)                                  # a build of the old commit
    assert publish_site.publish(site, 'https://example.invalid/b/2', repo,
                                'refs/tags/v0.1.0') is None
    assert publish_site.remote_head(repo, 'pages') is None


def test_an_older_release_never_replaces_a_newer_one(publication):
    repo, site, git = publication
    tag(git, 'v0.1.0')
    tag(git, 'v0.2.0')
    newer = publish_site.publish(site, 'https://example.invalid/b/1', repo, 'refs/tags/v0.2.0')
    (site / 'index.html').write_bytes(b'rebuilt\n')
    assert publish_site.publish(site, 'https://example.invalid/b/2', repo,
                                'refs/tags/v0.1.0') is None
    assert publish_site.remote_head(repo, 'pages') == newer
    tag(git, 'v0.10.0')                                               # numeric, not text, order
    assert publish_site.publish(site, 'https://example.invalid/b/3', repo, 'refs/tags/v0.10.0')


def test_release_versions():
    assert publish_site.version('refs/tags/v0.1.0') == (0, 1, 0)
    assert publish_site.version('refs/tags/v1.2.3-rc1') == (1, 2, 3)
    assert publish_site.version('refs/heads/main') is None
    assert publish_site.version('refs/tags/vnext') is None
