"""KittenTTS2 lifecycle shares the serialized, cancellable isolated installer."""

from .kitten_engine import available_voices
from .ming_lifecycle import MingLifecycle


class KittenLifecycle(MingLifecycle):
    profile = "kitten"
    engine_id = "kittentts2"
    display_name = "KittenTTS2"
    worker_file = "kitten_runtime_worker.py"
    response_marker = "@@PACTTS_KITTEN@@"

    def row(self):
        row = super().row()
        row.update(
            name="KittenTTS2 · 1.7B packed",
            runtime_reserve_bytes=20 * 1024**3,
            license="Apache-2.0 code; Stellon Labs Community License weights; MIT decoder",
            runtime="Private Python 3.12; PyTorch CUDA 12.8; native BF16 GPU (Ampere+)",
            languages="20 upstream languages including Portuguese; automatic detection",
            source="https://github.com/KittenML/KittenTTS",
            vram="About 8 GB free VRAM recommended upstream; estimate, not measured here",
            features="Reference cloning (5–30 s + transcript); 115 preset voices; expression tags",
            capabilities={
                "Voice cloning": "Supported; exact transcript required",
                "Style / emotion": "Stable/expressive presets; leading emotion tags",
                "Vocal tags": "Inline event tags; emphasis (beta)",
                "Streaming": "Not exposed",
                "Voice conversion": "Not supported",
                "Singing": "Not supported",
            },
            voices=available_voices(),
        )
        return row
