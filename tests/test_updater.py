import hashlib
import io
import zipfile

import pytest
from packaging.version import Version

from pacttsclone.updater import PREFIX, extract_wheel, select_release


def release(tag="v0.3.0-rc.12"):
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
    items = [release("v0.3.0-rc.9"), release(), release("v0.3.0-rc.11")]
    assert select_release(items, "0.3.0rc10")[0] == Version("0.3.0rc12")
    assert select_release(items, "0.2.0") is None
    assert select_release([release("v0.3.0")], "0.3.0rc12")[0] == Version("0.3.0")
    assert select_release(items, "0.3.0rc12") is None


@pytest.mark.parametrize("field,value", [("draft", True), ("tag_name", "latest")])
def test_reject_unpublished_or_ambiguous_release(field, value):
    item = release()
    item[field] = value
    assert select_release([item], "0.3.0rc11") is None


@pytest.mark.parametrize(
    "field,value",
    [("digest", None), ("browser_download_url", "https://example.com/update.whl"), ("size", 0)],
)
def test_reject_unverified_assets(field, value):
    item = release()
    item["assets"][0][field] = value
    assert select_release([item], "0.3.0rc11") is None


def wheel(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for key, value in entries.items():
            archive.writestr(key, value)
    return data.getvalue()


def test_extract_identity_and_dependencies(tmp_path):
    entries = {
        "pacttsclone/cli.py": "",
        "pacttsclone-0.3.0rc12.dist-info/METADATA": (
            "Name: pacttsclone\nVersion: 0.3.0rc12\nRequires-Dist: packaging>=24\n"
        ),
    }
    extract_wheel(wheel(entries), tmp_path, Version("0.3.0rc12"))
    assert (tmp_path / "pacttsclone/cli.py").exists()
    entries["pacttsclone-0.3.0rc12.dist-info/METADATA"] += "Requires-Dist: packaging>999\n"
    with pytest.raises(ValueError, match="dependency repair"):
        extract_wheel(wheel(entries), tmp_path, Version("0.3.0rc12"))


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
        extract_wheel(wheel({name: "bad"}), tmp_path, Version("0.3.0rc12"))


def test_stage_and_next_launch_activation(tmp_path, monkeypatch):
    import json

    from pacttsclone import updater

    monkeypatch.setattr(updater, "__version__", "0.3.0rc11")

    data = wheel(
        {
            "pacttsclone/cli.py": "",
            "pacttsclone-0.3.0rc12.dist-info/METADATA": "Name: pacttsclone\nVersion: 0.3.0rc12\n",
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
    assert "0.3.0rc12" in pth.read_text()
    assert (tmp_path / "updates/0.3.0rc12/pacttsclone/cli.py").exists()
    assert str(tmp_path / "updates/0.3.0rc12") not in __import__("sys").path


def test_failed_hash_keeps_activation_unchanged(tmp_path, monkeypatch):
    import json

    from pacttsclone import updater

    monkeypatch.setattr(updater, "__version__", "0.3.0rc11")

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
