"""Piper TTS provider — offline, ARM64-compatible, no GPU required.

Model files (.onnx + .onnx.json) must be placed in the configured model_dir.
Download models from: https://github.com/rhasspy/piper/releases

Example config.yaml entry:
  PiperTTS:
    type: piper_tts
    voice_model: en_US-lessac-medium
    model_dir: models/piper/
    output_dir: tmp/
    length_scale: 1.0   # speed (lower = faster)
    noise_scale: 0.667
    noise_w: 0.8
"""
import os
import wave
import struct
import asyncio

from core.providers.tts.base import TTSProviderBase


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = "wav"

        voice_model = config.get("voice_model", "en_US-lessac-medium")
        model_dir = config.get("model_dir", "models/piper/")

        self.model_path = os.path.join(model_dir, f"{voice_model}.onnx")
        self.length_scale = float(config.get("length_scale", 1.0))
        self.noise_scale = float(config.get("noise_scale", 0.667))
        self.noise_w = float(config.get("noise_w", 0.8))

        self._piper_voice = None
        self._sample_rate = 22050  # will be updated after model loads

        self._load_model()

    def _load_model(self):
        try:
            from piper.voice import PiperVoice
            self._piper_voice = PiperVoice.load(
                self.model_path,
                use_cuda=False,
            )
            self._sample_rate = self._piper_voice.config.sample_rate
        except ImportError:
            raise RuntimeError(
                "piper-tts is not installed. Add 'piper-tts' to requirements.txt."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Piper model at '{self.model_path}': {e}\n"
                "Download models from https://github.com/rhasspy/piper/releases"
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
                wf.setsampwidth(2)  # 16-bit PCM
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
