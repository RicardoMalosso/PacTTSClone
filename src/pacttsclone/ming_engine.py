"""Ming 3.0 dense adapter. Import only inside its dedicated inference runtime."""

import importlib.metadata
from pathlib import Path

import numpy as np

from .domain import UserError, Waveform

UPSTREAM_REVISION = "9332fb9443325d4726ce02cefd4ec1c211df4079"
MODEL_ID = "inclusionAI/Ming-3.0-tts-0.5b"
RUNTIME_REQUIREMENTS = {
    "torch": "2.6.0",
    "torchaudio": "2.6.0",
    "transformers": "4.46.3",
    "accelerate": "1.3.0",
    "x-transformers": "2.9.2",
    "diffusers": "0.33.0",
}


def check_runtime(torch):
    if not torch.cuda.is_available():
        raise UserError("Ming requires NVIDIA CUDA; CPU fallback is disabled.")
    if torch.cuda.get_device_capability()[0] < 8 or not torch.cuda.is_bf16_supported():
        raise UserError(
            "Ming's upstream BF16 runtime requires a compatible GPU. "
            "GTX 1660 SUPER is unsupported by this runtime."
        )
    for package, expected in RUNTIME_REQUIREMENTS.items():
        try:
            actual = importlib.metadata.version(package).split("+")[0]
        except importlib.metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            raise UserError(
                f"Ming needs its isolated runtime: {package}=={expected}; found {actual}. "
                "Do not replace OmniVoice's packages."
            )


def generation_arguments(reference, request):
    if request.language != "en":
        raise UserError(
            "Select English explicitly for Ming cloning. Portuguese and Automatic "
            "are not supported by this initial adapter."
        )
    if not request.ref_text:
        raise UserError("Ming cloning requires the exact saved reference transcript.")
    if request.duration is not None or request.speed != 1.0:
        raise UserError("Ming TTS mode does not accept OmniVoice duration or speed controls.")
    if request.steps != 32 or not request.denoise:
        raise UserError("OmniVoice steps and denoise overrides are unsupported by Ming.")
    if not request.preprocess_prompt:
        raise UserError("OmniVoice prompt preprocessing overrides are unsupported by Ming.")
    return {
        "task": "TTS",
        "text": request.text,
        "language_id": "English",
        "prompt_wav_path": reference,
        "prompt_text": request.ref_text,
        "use_spk_emb": True,
        "cfg": request.guidance_scale,
        "trim_silence": request.postprocess_output,
    }


class MingEngine:
    def __init__(self, settings):
        self.settings = settings
        self.model = None
        self.device = None
        self.observer = lambda *args: None
        self.residency_observer = lambda *args: None
        self.last_gpu_seconds = None

    def _load(self):
        if self.model is not None:
            return
        checkpoint = Path(self.settings.model)
        if not checkpoint.is_dir():
            raise UserError("Install and verify Ming locally before activation.")
        try:
            import torch

            check_runtime(torch)
            from ming_tts import MingTTS
        except ImportError as exc:
            raise UserError("Ming's isolated runtime/source installation is missing.") from exc
        self.observer("load_model", "cuda")
        self.model = MingTTS(str(checkpoint), device="cuda:0", text_normalization=False)
        self.device = "cuda"
        self.residency_observer(True, self.device)

    def transcribe(self, reference):
        raise UserError("Add the exact reference transcript before using Ming cloning.")

    def synthesize(self, reference, request):
        arguments = generation_arguments(reference, request)
        try:
            self._load()
            self.observer("inference", "cuda")
            waveform = self.model.synthesize(**arguments)
            samples = waveform.detach().float().cpu().numpy()
            if samples.ndim != 2 or samples.shape[0] != 1:
                raise UserError("Ming returned an invalid mono waveform.")
            samples = samples[0]
            if not samples.size or not np.isfinite(samples).all():
                raise UserError("Ming returned empty or invalid audio.")
            return Waveform(samples, self.model.sample_rate)
        except UserError:
            raise
        except Exception as exc:
            self.model = None
            self.residency_observer(False, self.device)
            raise UserError(
                "Ming generation failed; CPU fallback is disabled. " + str(exc)[:500]
            ) from exc
