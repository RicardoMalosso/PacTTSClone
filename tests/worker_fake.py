import time

import numpy as np

from pacttsclone.domain import Waveform


class ProcessFakeEngine:
    """Picklable stand-in for actual process lifecycle tests, never shipped in the package."""

    def __init__(self, settings):
        self.device = "cpu"

    def transcribe(self, reference):
        return "A saved reference transcript."

    def synthesize(self, reference, request):
        if request.text == "hang":
            time.sleep(30)
        return Waveform(np.sin(np.arange(24000) * 0.1) * 0.1, 24000)
