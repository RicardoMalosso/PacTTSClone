"""Setup smoke: real imports/tools; no model download or generation."""

import argparse
import subprocess

import fastapi  # noqa: F401
import omnivoice  # noqa: F401
import soundfile  # noqa: F401
import torch
import torchaudio  # noqa: F401

from pacttsclone.app import create_app  # noqa: F401

parser = argparse.ArgumentParser()
parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
args = parser.parse_args()
if args.device == "cuda":
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable: update the NVIDIA driver or rerun setup in CPU mode.")
    print(torch.cuda.get_device_name(0))
else:
    if torch.version.cuda is not None:
        raise SystemExit("Expected CPU-only PyTorch.")
for tool in ("ffmpeg", "ffprobe"):
    subprocess.run([tool, "-version"], check=True, stdout=subprocess.DEVNULL)
print("Runtime imports and audio tools OK")
