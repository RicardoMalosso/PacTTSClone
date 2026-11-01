import hashlib
import io
import zipfile

import pytest
from packaging.version import Version

from pacttsclone.updater import PREFIX, extract_wheel, select_release


def release(tag="v2.2.0-rc.12"):
    version = tag[1:].replace("-rc.", "rc")
    name = f"pacttsclone-{version}-py3-none-any.whl"
    return {
        "tag_name": tag,
        "draft": False,
        "assets": [
            {
                "name": name,
                "digest": "sha256:" + hashlib.sha256(b"wheel").hexdigest(),
                "size": 5,
                "browser_download_url": f"{PREFIX}{tag}/{name}",
            }
        ],
    }


def test_release_order_and_channels():
    items = [release("v2.2.0-rc.9"), release(), release("v2.2.0-rc.11")]
    assert select_release(items, "2.2.0rc10")[0] == Version("2.2.0rc12")
    assert select_release(items, "2.1.0")[0] == Version("2.2.0rc12")
    assert select_release(items, "2.1.0", False) is None
    assert select_release([release("v2.2.0")], "2.2.0rc12")[0] == Version("2.2.0")
    assert select_release(items, "2.2.0rc12") is None


@pytest.mark.parametrize("field,value", [("draft", True), ("tag_name", "latest")])
def test_reject_unpublished_or_ambiguous_release(field, value):
    item = release()
    item[field] = value
    assert select_release([item], "2.2.0rc11") is None


@pytest.mark.parametrize(
    "field,value",
    [("digest", None), ("browser_download_url", "https://example.com/update.whl"), ("size", 0)],
)
def test_reject_unverified_assets(field, value):
    item = release()
    item["assets"][0][field] = value
    assert select_release([item], "2.2.0rc11") is None


def wheel(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for key, value in entries.items():
            archive.writestr(key, value)
    return data.getvalue()


def test_extract_identity_and_dependencies(tmp_path):
    entries = {
        "pacttsclone/cli.py": "",
        "pacttsclone-2.2.0rc12.dist-info/METADATA": (
            "Name: pacttsclone\nVersion: 2.2.0rc12\nRequires-Dist: packaging>=24\n"
        ),
    }
    extract_wheel(wheel(entries), tmp_path, Version("2.2.0rc12"))
    assert (tmp_path / "pacttsclone/cli.py").exists()
    entries["pacttsclone-2.2.0rc12.dist-info/METADATA"] += "Requires-Dist: packaging>999\n"
    with pytest.raises(ValueError, match="dependency repair"):
        extract_wheel(wheel(entries), tmp_path, Version("2.2.0rc12"))


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/outside",
        "pacttsclone/../../outside",
        "pacttsclone\\outside",
        "unrelated/file",
    ],
)
def test_archive_paths(tmp_path, name):
    with pytest.raises(ValueError):
        extract_wheel(wheel({name: "bad"}), tmp_path, Version("2.2.0rc12"))


def test_stage_and_next_launch_activation(tmp_path, monkeypatch):
    import json

    from pacttsclone import updater

    monkeypatch.setattr(updater, "__version__", "2.2.0rc11")

    data = wheel(
        {
            "pacttsclone/cli.py": "",
            "pacttsclone-2.2.0rc12.dist-info/METADATA": "Name: pacttsclone\nVersion: 2.2.0rc12\n",
        }
    )
    item = release()
    item["assets"][0].update(size=len(data), digest="sha256:" + hashlib.sha256(data).hexdigest())
    monkeypatch.setenv("PACTTS_APP_ROOT", str(tmp_path))
    packages = tmp_path / "site-packages"
    packages.mkdir()
    monkeypatch.setattr(updater.sysconfig, "get_path", lambda name: str(packages))
    monkeypatch.setattr(updater.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(
        updater,
        "fetch",
        lambda url, limit: json.dumps([item]).encode() if url == updater.API else data,
    )
    instance = updater.Updater()
    instance.enabled = True
    assert instance.check()["status"] == "restart_required"
    pth = packages / "pacttsclone_update.pth"
    assert "2.2.0rc12" in pth.read_text()
    assert (tmp_path / "updates/2.2.0rc12/pacttsclone/cli.py").exists()
    assert str(tmp_path / "updates/2.2.0rc12") not in __import__("sys").path


def test_failed_hash_keeps_activation_unchanged(tmp_path, monkeypatch):
    import json

    from pacttsclone import updater

    monkeypatch.setattr(updater, "__version__", "2.2.0rc11")

    monkeypatch.setenv("PACTTS_APP_ROOT", str(tmp_path))
    monkeypatch.setattr(
        updater,
        "fetch",
        lambda url, limit: json.dumps([release()]).encode() if url == updater.API else b"wrong",
    )
    instance = updater.Updater()
    instance.enabled = True
    assert instance.check()["status"] == "failed"
    assert "checksum" in instance.state["error"]
    assert not (tmp_path / "updates").exists()


def test_publication_order_pin_and_bridge():
    from pacttsclone.updater import release_catalog

    old = release('v2.3.0-rc.1')
    old['published_at'] = '2026-10-31T10:00:00Z'
    patch = release('v2.2.1')
    patch['published_at'] = '2026-11-01T10:00:00Z'
    bridge = release('v2.3.0-rc.2')
    bridge['published_at'] = '2026-11-01T11:00:00Z'
    bridge['body'] = '<!-- pactts-update-bridge -->'
    rows = [old, bridge, patch]
    assert [r['tag'] for r in release_catalog(rows)] == ['v2.2.1', 'v2.3.0-rc.1']
    assert select_release(rows, '2.3.0rc1')[0] == Version('2.2.1')
    assert select_release(rows, '2.2.1', target='v2.3.0-rc.1')[0] == Version('2.3.0rc1')
    assert select_release(rows, '2.3.0rc1', target='v2.3.0-rc.1') is None
    assert select_release(rows, '2.2.1', False, 'v2.3.0-rc.1') is None
    patch['body'] = None
    assert select_release([patch], '2.1.1')[0] == Version('2.2.1')
    patch['prerelease'] = True
    assert select_release([patch], '2.1.1', False) is None


def test_preferences_default_and_persistence(tmp_path, monkeypatch):
    from pacttsclone.updater import Updater

    monkeypatch.setenv('PACTTS_APP_ROOT', str(tmp_path))
    app = Updater()
    app.enabled = True
    assert app.preferences == {'include_experimental': True, 'target': 'latest'}
    prefs = {'include_experimental': False, 'target': 'v2.1.1'}
    app.set_preferences(prefs)
    assert Updater().preferences == prefs
    with pytest.raises(ValueError):
        app.set_preferences({'include_experimental': False, 'target': 'v2.3.0-rc.1'})


def test_manager_api_and_boundary(tmp_path, engine):
    from fastapi.testclient import TestClient

    from pacttsclone.app import create_app
    from pacttsclone.config import Settings

    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/api/updates/manager').json()['include_experimental'] is True
        assert '/api/updates/panel.js' in client.get('/').text
        assert client.get('/api/updates/panel.js').status_code == 200
        assert client.post('/api/updates/select', json={}).status_code == 403
        token = client.get('/api/session').json()['token']
        assert client.post('/api/updates/select', json={},
                           headers={'X-PacTTS-Token': token}).status_code == 422
    assert not app.state.tunnel.permitted(('admin', None), '/api/updates/manager', 'GET')


def test_failed_preflight_preserves_pointer(tmp_path, monkeypatch):
    import json
    import subprocess

    from pacttsclone import updater

    monkeypatch.setenv('PACTTS_APP_ROOT', str(tmp_path))
    monkeypatch.setattr(updater, '__version__', '2.1.1')
    packages = tmp_path / 'site-packages'
    packages.mkdir()
    pointer = packages / 'pacttsclone_update.pth'
    pointer.write_text('previous activation\n')
    monkeypatch.setattr(updater.sysconfig, 'get_path', lambda name: str(packages))
    data = wheel({'pacttsclone/cli.py': '', 'pacttsclone-2.2.0rc12.dist-info/METADATA':
                  'Name: pacttsclone\nVersion: 2.2.0rc12\n'})
    item = release()
    item['assets'][0].update(size=len(data), digest='sha256:' + hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(updater, 'fetch', lambda url, limit:
                        json.dumps([item]).encode() if url == updater.API else data)
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(updater.subprocess, 'run', fail)
    instance = updater.Updater()
    instance.enabled = True
    instance.state.update(next_version='2.2.1')
    assert instance.check()['status'] == 'failed'
    assert pointer.read_text() == 'previous activation\n'
    assert instance.state['next_version'] == '2.2.1'


def test_select_running_version_cancels_pending(tmp_path, monkeypatch):
    import json

    from pacttsclone import updater

    monkeypatch.setenv('PACTTS_APP_ROOT', str(tmp_path))
    monkeypatch.setattr(updater, '__version__', '2.2.1')
    monkeypatch.setattr(updater, 'fetch',
                        lambda url, limit: json.dumps([release('v2.2.1')]).encode())
    instance = updater.Updater()
    instance.enabled = True
    instance.root.mkdir()
    instance.state['next_version'] = '2.3.0rc1'
    calls = []
    monkeypatch.setattr(instance, '_activate', lambda target, controller: calls.append(target))
    assert instance.check()['status'] == 'up_to_date'
    assert instance.state['next_version'] is None
    assert calls
