import pytest

from pacttsclone.update_check import select_release, version_key


def release(tag, *, draft=False, prerelease=True):
    normalized = tag.removeprefix("v").replace("-rc.", "rc")
    name = f"pacttsclone-{normalized}-py3-none-any.whl"
    base = "https://github.com/RicardoMalosso/PacTTSClone/releases"
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"{base}/tag/{tag}",
        "assets": [{"name": name, "state": "uploaded", "size": 123,
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": f"{base}/download/{tag}/{name}"}],
    }


def test_version_order_and_channel():
    releases = [release("v0.3.0-rc.10"), release("v0.3.0-rc.11", draft=True),
                release("v0.3.0-rc.9"), release("v0.3.0", prerelease=False)]
    assert select_release(releases, "0.3.0rc9", True).version == "v0.3.0"
    assert select_release(releases[:-1], "0.3.0rc9", True).version == "v0.3.0-rc.10"
    assert select_release(releases[:-1], "0.3.0rc9", False) is None
    assert version_key("0.3.0rc10") > version_key("0.3.0rc9")


def test_untrusted_or_incomplete_release_is_not_offered():
    item = release("v0.3.0-rc.10")
    item["assets"][0]["browser_download_url"] = "https://example.com/file.whl"
    assert select_release([item], "0.3.0rc9", True) is None
    item = release("v0.3.0-rc.10")
    item["assets"][0]["digest"] = None
    assert select_release([item], "0.3.0rc9", True) is None
    item = release("v0.3.0-rc.10")
    item["assets"].append(item["assets"][0])
    assert select_release([item], "0.3.0rc9", True) is None


def test_invalid_input_is_rejected():
    with pytest.raises(ValueError):
        select_release([], "unknown", True)
    with pytest.raises(ValueError):
        select_release({}, "0.3.0rc9", True)
