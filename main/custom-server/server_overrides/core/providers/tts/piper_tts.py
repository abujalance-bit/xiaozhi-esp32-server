"""Piper TTS provider — offline, ARM64-compatible.

Supports GPU acceleration via onnxruntime CUDA provider when use_cuda=true
is set in the model config and onnxruntime-gpu is installed (e.g. via the
dustynv/jetson-containers base image).

Model files (.onnx + .onnx.json) must be placed in the configured model_dir.
Download models from: https://huggingface.co/rhasspy/piper-voices
Browse samples at:    https://rhasspy.github.io/piper-samples/

Example model config (GPU):
  {
    "type": "piper_tts",
    "voice_model": "en_US-lessac-medium",
    "model_dir": "/data/models/piper/",
    "output_dir": "tmp/",
    "use_cuda": true,
    "length_scale": 1.0
  }
"""
import os
import wave
import asyncio

from core.providers.tts.base import TTSProviderBase


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = "wav"

        voice_model = config.get("voice_model", "en_US-lessac-medium")
        model_dir   = config.get("model_dir", "models/piper/")
        self.use_cuda    = bool(config.get("use_cuda", False))
        self.length_scale = float(config.get("length_scale", 1.0))
        self.noise_scale  = float(config.get("noise_scale", 0.667))
        self.noise_w      = float(config.get("noise_w", 0.8))

        self.model_path = os.path.join(model_dir, f"{voice_model}.onnx")
        self._piper_voice = None
        self._sample_rate = 22050

        self._load_model()

    def _load_model(self):
        try:
            from piper.voice import PiperVoice
        except ImportError:
            raise RuntimeError(
                "piper-tts is not installed. Run: pip install piper-tts"
            )

        if self.use_cuda:
            try:
                import onnxruntime as _ort
                available = [p.lower() for p in _ort.get_available_providers()]
                if "cudaexecutionprovider" not in available:
                    import logging
                    logging.getLogger(__name__).warning(
                        "use_cuda=true but CUDAExecutionProvider is not available "
                        "in onnxruntime — falling back to CPU. "
                        "Make sure onnxruntime-gpu is installed."
                    )
                    self.use_cuda = False
            except ImportError:
                self.use_cuda = False

        try:
            self._piper_voice = PiperVoice.load(
                self.model_path,
                use_cuda=self.use_cuda,
            )
            self._sample_rate = self._piper_voice.config.sample_rate
            device_label = "CUDA" if self.use_cuda else "CPU"
            import logging
            logging.getLogger(__name__).info(
                f"Piper TTS loaded '{os.path.basename(self.model_path)}' on {device_label}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Piper model at '{self.model_path}': {e}\n"
                "Download from https://huggingface.co/rhasspy/piper-voices"
            )

    async def text_to_speak(self, text, output_file):
        if not text or not text.strip():
            return None

        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(None, self._synthesize, text)

        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with wave.open(output_file, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio_bytes)
        return audio_bytes

    def _synthesize(self, text):
        chunks = []
        for audio_bytes in self._piper_voice.synthesize_stream_raw(
            text,
            length_scale=self.length_scale,
            noise_scale=self.noise_scale,
            noise_w=self.noise_w,
        ):
            chunks.append(audio_bytes)
        return b"".join(chunks)
