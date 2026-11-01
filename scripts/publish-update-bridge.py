"""Publish the one-time migration wheel only after the stable installer passes acceptance."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

REPO = os.environ['GITHUB_REPOSITORY']
SHA = os.environ['GITHUB_SHA']
TAG = 'v2.3.0-rc.2'
STABLE = 'v2.2.1'


def api(path, *args):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}', *args]))


stable = api(f'releases/tags/{STABLE}')
assert not stable['draft'] and not stable['prerelease'] and stable['target_commitish'] == SHA
wheel = Path('bridge-dist/pacttsclone-2.3.0rc2-py3-none-any.whl')
sums = wheel.parent / 'SHA256SUMS.txt'
sums.write_text(f'{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n')
notes = wheel.parent / 'notes.md'
notes.write_text('<!-- pactts-update-bridge -->\n'
                 '# Updater compatibility bridge\n\n'
                 'This update-only wheel lets existing 2.3.0-rc.1 installations receive the '
                 'new updater. It contains the same application changes as 2.2.1. '
                 'Experimental releases default on; Configuration supports previous-version pins. '
                 'After restarting, Latest follows publication date and selects 2.2.1.\n\n'
                 f'For a new installation use the [2.2.1 installer](https://github.com/{REPO}'
                 f'/releases/tag/{STABLE}). No model download or GPU validation is implied.\n')
releases = api('releases?per_page=100')
existing = next((r for r in releases if r['tag_name'] == TAG), None)
if not existing:
    subprocess.run(['gh', 'release', 'create', TAG, '--draft', '--prerelease', '--target', SHA,
                    '--title', 'PacTTSClone updater migration (2.3.0-rc.2)',
                    '--notes-file', str(notes), str(wheel), str(sums)], check=True)
    existing = next(r for r in api('releases?per_page=100') if r['tag_name'] == TAG)
assert existing['target_commitish'] == SHA and existing['prerelease']
assert len(existing['assets']) == 2
for file in (wheel, sums):
    asset = next(a for a in existing['assets'] if a['name'] == file.name)
    assert asset['size'] == file.stat().st_size
    assert asset['digest'] == 'sha256:' + hashlib.sha256(file.read_bytes()).hexdigest()
if existing['draft']:
    api(f"releases/{existing['id']}", '--method', 'PATCH', '-F', 'draft=false',
        '-f', 'make_latest=false')
api(f"releases/{stable['id']}", '--method', 'PATCH', '-f', 'make_latest=true')
assert api('releases/latest')['tag_name'] == STABLE
print('Published verified RC migration bridge; 2.2.1 is Latest')
