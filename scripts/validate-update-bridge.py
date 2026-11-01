"""Validate repacked metadata, RECORD and actual isolated imports."""
import base64
import csv
import hashlib
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

with zipfile.ZipFile(sys.argv[1]) as archive:
    prefix = 'pacttsclone-2.3.0rc2.dist-info/'
    assert 'Version: 2.3.0rc2' in archive.read(prefix + 'METADATA').decode()
    for name, digest, size in csv.reader(io.StringIO(archive.read(prefix + 'RECORD').decode())):
        if not digest:
            assert name == prefix + 'RECORD'
            continue
        data = archive.read(name)
        assert len(data) == int(size)
        actual = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        assert digest == 'sha256=' + actual
    with tempfile.TemporaryDirectory() as directory:
        archive.extractall(directory)
        subprocess.run([sys.executable, '-c',
                        f'import sys; sys.path.insert(0, {str(Path(directory))!r}); '
                        'import pacttsclone; assert pacttsclone.__version__=="2.3.0rc2"; '
                        'import pacttsclone.app, pacttsclone.cli'], check=True)
print('Bridge identity, RECORD and application imports verified')
