import os
import subprocess
import sys
from pathlib import Path


def test_release_candidate_has_separate_windows_numeric_version(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "release-identity.py"
    (tmp_path / "pyproject.toml").write_text('version = "2.2.0rc1"\n')
    package = tmp_path / "src" / "pacttsclone"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "2.2.0rc1"\n')
    env = dict(os.environ)
    env.pop("GITHUB_OUTPUT", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert values["installer_version"] == "2.2.0-rc.1"
    assert values["numeric_version"] == "2.2.0.0"
    assert values["prerelease"] == "true"
