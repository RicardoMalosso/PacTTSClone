"""Download the setup easter egg as a checked, locally packaged GIF.

Run before building wheels/installers; runtime never depends on Tenor being online.
"""
from pathlib import Path
from urllib.request import Request, urlopen
import time

URL = "https://media1.tenor.com/m/SfZnf2pHgtIAAAAd/choopo-jingle.gif"
TARGET = Path(__file__).resolve().parents[1] / "src/pacttsclone/static/choopo-jingle.gif"


def main():
    for attempt in range(3):
        try:
            request = Request(URL, headers={"User-Agent": "PacTTSClone-installer/1.0"})
            with urlopen(request, timeout=45) as response:
                data = response.read(20 * 1024 * 1024 + 1)
            if not data.startswith((b"GIF87a", b"GIF89a")) or len(data) > 20 * 1024 * 1024:
                raise ValueError("Download is not a valid GIF within the 20 MiB limit")
            TARGET.parent.mkdir(parents=True, exist_ok=True)
            TARGET.write_bytes(data)
            print(f"Bundled {TARGET.name} ({len(data)} bytes)")
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


if __name__ == "__main__":
    main()
