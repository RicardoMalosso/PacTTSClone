"""Read-only discovery of published Windows update candidates.

Discovery does not establish publisher authenticity and never installs a wheel.
"""

import json
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASES_URL = "https://api.github.com/repos/RicardoMalosso/PacTTSClone/releases?per_page=100"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?rc[.-]?(\d+))?$", re.I)
_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_MAX_RESPONSE = 2 * 1024 * 1024


def version_key(value: str):
    """Compare the project's stable and release-candidate version forms."""
    if len(value) > 64:
        return None
    match = _VERSION.fullmatch(value)
    if not match:
        return None
    major, minor, patch, rc = match.groups()
    return (int(major), int(minor), int(patch), 1 if rc is None else 0, int(rc or 0))


def installed_version():
    try:
        return version("pacttsclone")
    except PackageNotFoundError:
        return None


@dataclass(frozen=True)
class Candidate:
    version: str
    release_url: str
    prerelease: bool
    wheel_name: str
    wheel_url: str
    wheel_size: int
    wheel_sha256: str


def select_release(releases, current: str, include_prereleases: bool):
    current_key = version_key(current)
    if current_key is None:
        raise ValueError("Unsupported installed version")
    if not isinstance(releases, list):
        raise ValueError("Invalid release response")
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is not False:
            continue
        prerelease = release.get("prerelease")
        if not isinstance(prerelease, bool) or (prerelease and not include_prereleases):
            continue
        tag = release.get("tag_name")
        key = version_key(tag) if isinstance(tag, str) else None
        if key is None or key <= current_key or prerelease != (key[3] == 0):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        # Require one precisely named wheel, matching the parsed release version.
        wheel_version = f"{key[0]}.{key[1]}.{key[2]}" + (f"rc{key[4]}" if prerelease else "")
        name = f"pacttsclone-{wheel_version}-py3-none-any.whl"
        wheels = [a for a in assets if isinstance(a, dict) and a.get("name") == name]
        if len(wheels) != 1:
            continue
        asset = wheels[0]
        raw_digest = asset.get("digest")
        digest = _DIGEST.fullmatch(raw_digest) if isinstance(raw_digest, str) else None
        size = asset.get("size")
        url = f"https://github.com/RicardoMalosso/PacTTSClone/releases/download/{tag}/{name}"
        release_url = f"https://github.com/RicardoMalosso/PacTTSClone/releases/tag/{tag}"
        if (
            not digest
            or type(size) is not int
            or not 0 < size <= 150 * 1024 * 1024
            or asset.get("browser_download_url") != url
            or release.get("html_url") != release_url
            or asset.get("state") != "uploaded"
        ):
            continue
        candidate = Candidate(tag, release_url, prerelease, name, url, size, digest[1])
        candidates.append((key, candidate))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check_releases(current: str, include_prereleases: bool):
    request = Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PacTTSClone-update-check"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read(_MAX_RESPONSE + 1)
        if len(payload) > _MAX_RESPONSE:
            raise ValueError("Release response too large")
        return select_release(json.loads(payload), current, include_prereleases)
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not check GitHub releases") from exc
