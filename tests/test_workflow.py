"""The release workflow (.github/workflows/build.yml, docs/HOSTING.md): it runs only for v* tags
(and by hand), attaches cas-evo-<tag>.zip to the tag's GitHub Release with the built-in token,
and publishes the website from tags. Text checks: the suite has no YAML parser."""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_depth, pytest.mark.no_invariants]

WORKFLOW = (Path(__file__).resolve().parents[1] / '.github/workflows/build.yml').read_text()


def block(name, indent=2):
    """The lines of a job (or the top-level 'on:' block with indent 0)."""
    lines = WORKFLOW.splitlines()
    head = ' ' * indent + name + ':'
    start = lines.index(head, 0 if name == 'on' else lines.index('jobs:'))
    out = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        out.append(line)
    return '\n'.join(out)


def test_runs_only_for_v_tags_releases_and_by_hand():
    on = block('on', 0)
    assert "tags: ['v*']" in on
    assert 'types: [published]' in on and 'workflow_dispatch:' in on
    assert 'branches' not in on and 'pull_request' not in on


def test_one_run_per_tag_at_a_time():
    head = WORKFLOW[:WORKFLOW.index('jobs:')]
    assert 'github.event.release.tag_name || github.ref_name' in head
    assert 'cancel-in-progress: false' in head
    check = block('check')
    assert 'cas-evo-$TAG.zip' in check and 'build=false' in check
    assert "needs.check.outputs.build == 'true'" in block('build')


def test_only_the_publishing_jobs_may_write():
    assert WORKFLOW.count('contents: write') == 2
    assert 'permissions:\n  contents: read' in WORKFLOW
    for job in ('release', 'publish'):
        text = block(job)
        assert 'contents: write' in text
        assert "startsWith(github.ref, 'refs/tags/v')" in text
    for job in ('check', 'build'):
        assert 'contents: write' not in block(job)


def test_release_job_creates_or_reuses_the_release_and_uploads_the_zip():
    text = block('release')
    assert 'gh release view "$TAG"' in text and 'gh release create "$TAG"' in text
    assert '--verify-tag' in text
    assert 'gh release upload "$TAG" "cas-evo-$TAG.zip"' in text and '--clobber' in text
    assert 'GH_TOKEN: ${{ github.token }}' in text
    assert 'name: cas-evo-v1' in text


def test_publish_job_checks_the_tag():
    assert '--ref "$GITHUB_REF"' in block('publish')


def test_actions_are_pinned_to_full_commits():
    for line in WORKFLOW.splitlines():
        if 'uses:' in line:
            ref = line.split('@', 1)[1].split()[0]
            assert len(ref) == 40 and all(c in '0123456789abcdef' for c in ref), line


def test_a_release_for_a_non_v_tag_builds_nothing():
    # release: published fires for every tag; only v* tags are releases of the calculator.
    check = block('check')
    assert "startsWith(github.event.release.tag_name, 'v')" in check
    assert "github.event_name != 'release'" in check
