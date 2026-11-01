"""Real installed-interpreter staging, historical rollback, persistent pin and forward update."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.version import Version

from pacttsclone import __version__, updater

wheel, root = map(Path, sys.argv[1:])
root.mkdir(parents=True, exist_ok=True)
builder_path = Path(__file__).parents[1] / 'scripts/build-update-bridge.py'
spec = importlib.util.spec_from_file_location('builder', builder_path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
fixture = root / 'fixture.whl'
builder.build(wheel, fixture, __version__, '999.0.0')
data = fixture.read_bytes()
name = 'pacttsclone-999.0.0-py3-none-any.whl'
release = [{'tag_name': 'v999.0.0', 'published_at': '2099-01-01T00:00:00Z', 'assets': [{
    'name': name, 'size': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(),
    'browser_download_url': updater.PREFIX + 'v999.0.0/' + name}]}]
original = __version__
os.environ['PACTTS_APP_ROOT'] = str(root)
pth = Path(sysconfig.get_path('purelib')) / 'pacttsclone_update.pth'
assert not pth.exists(), 'Acceptance needs a clean base installation'
instance = updater.Updater()
instance.enabled = True
real_fetch = updater.fetch
updater.fetch = lambda target, limit: (
    json.dumps(release).encode() if target == updater.API else data)


def probe(code):
    return subprocess.check_output([sys.executable, '-c', code], text=True).strip()


try:
    state = instance.check()
    assert state['status'] == 'restart_required', state
    assert __version__ == original
    assert probe('import pacttsclone; print(pacttsclone.__version__)') == '999.0.0'
    headers = {'User-Agent': 'PacTTSClone-update-acceptance'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urlopen(Request('https://api.github.com/repos/RicardoMalosso/PacTTSClone/releases/tags/v2.1.1',
                         headers=headers), timeout=30) as response:
        historical = json.load(response)
    asset = historical['assets']
    asset = next(a for a in asset if a['name'] == 'pacttsclone-2.1.1-py3-none-any.whl')
    old_data = real_fetch(asset['browser_download_url'], updater.MAX_DOWNLOAD)
    assert len(old_data) == asset['size']
    assert 'sha256:' + hashlib.sha256(old_data).hexdigest() == asset['digest']
    legacy = root / 'historical'
    legacy.mkdir(exist_ok=True)
    updater.extract_wheel(old_data, legacy, Version('2.1.1'))
    spec = importlib.util.spec_from_file_location('pacttsclone.legacy_updater',
                                                legacy / 'pacttsclone/updater.py')
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    def identity(tag):
        version = Version(tag[1:].replace('-rc.', 'rc'))
        name = f'pacttsclone-{version}-py3-none-any.whl'
        return {'tag_name': tag, 'assets': [{'name': name, 'size': 1,
                'digest': 'sha256:' + '0' * 64,
                'browser_download_url': updater.PREFIX + tag + '/' + name}]}
    releases = [identity('v2.2.1'), identity('v2.3.0-rc.2')]
    assert str(old.select_release(releases, '2.1.1')[0]) == '2.2.1'
    assert str(old.select_release(releases, '2.3.0rc1')[0]) == '2.3.0rc2'
    updater.fetch = lambda target, limit: (
        json.dumps([historical]).encode() if target == updater.API else old_data)
    instance.set_preferences({'include_experimental': True, 'target': 'v2.1.1'})
    state = instance.check()
    assert state['status'] == 'restart_required', state
    code = f'''
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import pacttsclone
assert pacttsclone.__version__ == '2.1.1'
import pacttsclone.voices as v
v.BUILTIN_CATALOG=None
from pacttsclone import updater
from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import GenerationSettings
assert updater.CONTROL_VERSION >= 1
GenerationSettings.model_validate({{'kitten': {{}}}})
with TemporaryDirectory(dir={str(root)!r}) as d:
    app=create_app(Settings(data_dir=Path(d)))
    assert any(r.path == '/api/updates/manager' for r in app.routes)
    manager=app.state.updater
    manager.enabled=True
    assert manager.preferences['target']=='v2.1.1'
    updater.fetch=lambda target, limit: json.dumps({release + [historical]!r}).encode()
    assert manager.check()['status']=='up_to_date', manager.state
    manager.set_preferences({{'include_experimental':True, 'target':'latest'}})
    updater.fetch=lambda target, limit: (json.dumps({release!r}).encode() if target == updater.API
                                        else Path({str(fixture)!r}).read_bytes())
    assert manager.check()['status']=='restart_required', manager.state
print('Historical application kept updater, honored pin and staged Latest')
'''
    print(probe(code))
    assert probe('import pacttsclone; print(pacttsclone.__version__)') == '999.0.0'
finally:
    pth.unlink(missing_ok=True)
assert probe('import pacttsclone; print(pacttsclone.__version__)') == original
print('Verified next-launch activation, real 2.1.1 rollback and forward update; base restored')
