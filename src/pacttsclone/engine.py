import gc
import importlib.util
import os

from .config import Settings
from .domain import GenerationRequest, UserError, Waveform


def choose_device(torch, requested: str) -> str:
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise UserError("CUDA indisponível. Instale PyTorch com CUDA ou use --device cpu.")
    if requested not in {"cpu", "cuda"}:
        raise UserError("Dispositivo inválido: use auto, cuda ou cpu.")
    return requested


def dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("torch", "omnivoice"))


class OmniVoiceEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.device = None
        self.asr_loaded = False
        self.observer = lambda *args: None
        self.last_gpu_seconds = None
        self.residency_observer = lambda loaded, device: None
        if settings.offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def _load(self):
        if self.model is not None:
            return
        self.observer("load_model", "cpu")
        try:
            import torch
            from omnivoice import OmniVoice
        except ImportError as exc:
            raise UserError(
                "Dependências de inferência ausentes/incompatíveis. Instale PyTorch e .[inference]."
            ) from exc
        self.device = choose_device(torch, self.settings.device)
        if self.device != "cpu":
            self.observer("load_model", self.device)
        self.model = OmniVoice.from_pretrained(
            self.settings.model,
            device_map=self.device,
            dtype=torch.float16 if self.device == "cuda" else torch.float32,
            attn_implementation="sdpa",
            load_asr=False,
            asr_model_name=self.settings.asr_model,
            asr_device="cpu",
        )
        self.model.eval()
        self.residency_observer(True, self.device)

    def transcribe(self, reference: str) -> str:
        self._load()
        self.observer("transcribe", "cpu")
        if not self.asr_loaded:
            self.model.load_asr_model(model_name=self.settings.asr_model, device="cpu")
            self.asr_loaded = True
        import soundfile as sf

        # The worker has already decoded and validated reference.wav. Pass PCM
        # directly so Transformers does not launch a second FFmpeg decoder.
        samples, sample_rate = sf.read(reference, dtype="float32")
        return self.model.transcribe((samples, sample_rate))

    def synthesize(self, reference: str, request: GenerationRequest) -> Waveform:
        try:
            self._load()
            import torch
            from omnivoice import OmniVoiceGenerationConfig

            if not request.ref_text and not self.asr_loaded:
                self.model.load_asr_model(model_name=self.settings.asr_model, device="cpu")
                self.asr_loaded = True
            self.observer("inference", self.device)
            events = None
            if self.device == "cuda" and hasattr(torch.cuda, "Event"):
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                events = (
                    torch.cuda.Event(enable_timing=True),
                    torch.cuda.Event(enable_timing=True),
                )
                events[0].record()
            with torch.inference_mode():
                audio = self.model.generate(
                    text=request.text,
                    language=None if request.language == "auto" else request.language,
                    ref_audio=reference,
                    ref_text=request.ref_text or None,
                    speed=request.speed,
                    generation_config=OmniVoiceGenerationConfig(num_step=request.steps),
                )
            if events:
                events[1].record()
                torch.cuda.synchronize()
                self.last_gpu_seconds = events[0].elapsed_time(events[1]) / 1000
            return Waveform(audio[0], self.model.sampling_rate)
        except UserError:
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "out of memory" in message or isinstance(exc, MemoryError):
                # Drop caches/model after OOM so a retry doesn't retain broken state.
                self.model = None
                self.residency_observer(False, self.device)
                self.asr_loaded = False
                gc.collect()
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                raise UserError(
                    "Memória insuficiente. Reduza o texto ou reinicie com --device cpu."
                ) from exc
            raise UserError(
                "Falha no OmniVoice. Verifique a instalação, conexão para baixar modelos "
                "ou cache no modo offline. Consulte o terminal para detalhes."
            ) from exc
