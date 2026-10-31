"""Derive immutable release identity from the package's sole version source."""

import os
import re
from pathlib import Path

text = Path("pyproject.toml").read_text()
version = re.search(r'^version = "([^"]+)"', text, re.M)[1]
match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:rc(\d+))?", version)
if not match:
    raise SystemExit("Expected X.Y.Z or X.Y.ZrcN")
tag = "v" + match[1] + (f"-rc.{match[2]}" if match[2] else "")
if f'__version__ = "{version}"' not in Path("src/pacttsclone/__init__.py").read_text():
    raise SystemExit("Runtime version differs from package version")
output = (
    f"version={version}\ntag={tag}\ninstaller_version={tag[1:]}\n"
    f"numeric_version={match[1]}.0\n"
    f"prerelease={str(bool(match[2])).lower()}\nmake_latest={str(not bool(match[2])).lower()}\n"
)
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(output)
else:
    print(output, end="")
