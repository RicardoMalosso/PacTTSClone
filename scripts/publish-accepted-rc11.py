"""Publish the existing RC11 draft after checking its completed acceptance run."""

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = "RicardoMalosso/PacTTSClone"
RUN = 40971665005
TARGET = "24196cbe86a730e1c036e456b77eee298e51ee23"
SOURCE = "3fc2447ff3e482717e7c977e3bd3b4bfe88ff11c"
TAG = "v0.3.0-rc.11"
RELEASE = 428493183
FILES = {
    "PacTTSClone-Setup-0.3.0-rc.11.exe",
    "pacttsclone-0.3.0rc11-py3-none-any.whl",
    "FFmpeg-provenance.zip",
    "SHA256SUMS.txt",
}


def api(path, body=None):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "PATCH",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(os.environ.get("GITHUB_REPOSITORY") == REPO, "Unexpected repository")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "Main branch required")
    run = api(f"actions/runs/{RUN}")
    require(run["head_sha"] == SOURCE and run["status"] == "completed", "Unexpected run")
    jobs = api(f"actions/runs/{RUN}/jobs?per_page=100")["jobs"]
    require(len(jobs) == 8, "Unexpected acceptance jobs")
    setup = [j for j in jobs if j["name"] == "installer / windows-setup"]
    require(len(setup) == 1, "Missing Windows acceptance job")
    require(
        all(j["conclusion"] == "success" for j in jobs if j["id"] != setup[0]["id"]),
        "Full test suite did not pass",
    )
    steps = {s["name"]: s["conclusion"] for s in setup[0]["steps"]}
    for name in (
        "Validate scripts and download/cache helpers",
        "Fetch verified Gyan FFmpeg Essentials",
        "Build application wheel",
        "Compile small unsigned setup",
        "Interactive wizard folder and delay checks",
        "Actual CPU install, HTTP launch, repeat setup and uninstall",
        "Checksums",
        "Prepare draft prerelease",
    ):
        require(steps.get(name) == "success", f"Acceptance step did not pass: {name}")
    require(
        steps.get("Publish accepted RC11 prerelease") == "failure",
        "Unexpected recovery state",
    )
    release = api(f"releases/{RELEASE}")
    require(
        release["tag_name"] == TAG
        and release["target_commitish"] == TARGET
        and release["prerelease"],
        "Unexpected release target or type",
    )
    root = Path(sys.argv[1])
    require({p.name for p in root.iterdir()} == FILES, "Unexpected downloaded files")
    sums = {}
    for line in (root / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in sums and name in FILES, "Unexpected checksum entry")
        sums[name] = digest
    require(set(sums) == FILES - {"SHA256SUMS.txt"}, "Incomplete checksum manifest")
    assets = {a["name"]: a for a in release["assets"]}
    require(len(release["assets"]) == len(FILES) and set(assets) == FILES, "Unexpected assets")
    for name in FILES:
        path = root / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(name not in sums or sums[name] == digest, f"Checksum mismatch: {name}")
        require(
            assets[name]["size"] == path.stat().st_size
            and assets[name]["digest"] == "sha256:" + digest,
            f"Uploaded asset mismatch: {name}",
        )
        print(f"Verified {name}: {digest}")
    if release["draft"]:
        release = api(
            f"releases/{RELEASE}",
            {"draft": False, "prerelease": True, "make_latest": "false"},
        )
    require(not release["draft"] and release["published_at"], "Publication did not complete")
    print(release["html_url"])


if __name__ == "__main__":
    main()
