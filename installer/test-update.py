"""Exercise actual installed-interpreter update activation and rollback with a local fixture."""

import hashlib
import io
import json
import os
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

from pacttsclone import __version__, updater

wheel = Path(sys.argv[1])
root = Path(sys.argv[2])
version = "999.0.0"
original_version = __version__
result = io.BytesIO()
with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(result, "w") as archive:
    for member in source.infolist():
        name = member.filename.replace(
            f"pacttsclone-{original_version}.dist-info", f"pacttsclone-{version}.dist-info"
        )
        data = source.read(member)
        if name == "pacttsclone/__init__.py":
            data = data.replace(original_version.encode(), version.encode())
        if name.endswith(".dist-info/METADATA"):
            data = data.replace(
                f"Version: {original_version}".encode(), f"Version: {version}".encode()
            )
        archive.writestr(name, data)
data = result.getvalue()
name = f"pacttsclone-{version}-py3-none-any.whl"
url = f"{updater.PREFIX}v{version}/{name}"
release = [
    {
        "tag_name": f"v{version}",
        "draft": False,
        "assets": [
            {
                "name": name,
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "browser_download_url": url,
            }
        ],
    }
]
updater.fetch = lambda target, limit: (
    json.dumps(release).encode() if target == updater.API else data
)
os.environ["PACTTS_APP_ROOT"] = str(root)
pth = Path(sysconfig.get_path("purelib")) / "pacttsclone_update.pth"
assert not pth.exists(), "Acceptance requires a clean base installation"
instance = updater.Updater()
instance.enabled = True
try:
    state = instance.check()
    assert state["status"] == "restart_required", state
    assert __version__ == original_version, "Running process switched versions"
    output = subprocess.check_output(
        [sys.executable, "-c", "import pacttsclone; print(pacttsclone.__version__)"], text=True
    )
    assert output.strip() == version, output
finally:
    pth.unlink(missing_ok=True)
output = subprocess.check_output(
    [sys.executable, "-c", "import pacttsclone; print(pacttsclone.__version__)"], text=True
)
assert output.strip() == original_version
print("Installed Python activated verified overlay on next launch and rolled back successfully")
