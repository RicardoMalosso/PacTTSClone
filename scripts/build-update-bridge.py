"""Re-version a validated wheel without changing its application payload."""
import base64
import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path


def build(source, destination, current, bridge):
    entries = {}
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            name = item.filename.replace(f'pacttsclone-{current}.dist-info',
                                         f'pacttsclone-{bridge}.dist-info')
            data = archive.read(item)
            if name.endswith('.dist-info/RECORD'):
                continue
            if name == 'pacttsclone/__init__.py':
                data = data.replace(current.encode(), bridge.encode())
            if name.endswith('.dist-info/METADATA'):
                data = data.replace(f'Version: {current}'.encode(), f'Version: {bridge}'.encode())
            entries[name] = data
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, data in entries.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
        writer.writerow([name, 'sha256=' + digest, len(data)])
    name = f'pacttsclone-{bridge}.dist-info/RECORD'
    writer.writerow([name, '', ''])
    entries[name] = record.getvalue().encode()
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


if __name__ == '__main__':
    build(*sys.argv[1:])
