"""Real process transport fixture; never a model or CUDA performance test."""

import sys

from pacttsclone.ming_process import MingProcessEngine


class FakeMingProcess(MingProcessEngine):
    def _command(self, python, root):
        return [sys.executable, "-u", str(self.settings.data_dir / "fake_ming.py")]


def factory(settings):
    return FakeMingProcess(settings)
