"""Offline ASR provider using faster-whisper (CTranslate2 backend).

Supports all Whisper languages including Spanish. Significantly faster than
OpenAI Whisper on CUDA — on Jetson AGX Orin, medium runs in ~300-800 ms.

Config keys:
  model_size_or_path  str   "tiny","base","small","medium","large-v3", or local path
  device              str   "cuda" | "cpu" | "auto"   (default: "cuda")
  compute_type        str   "float16" | "int8_float16" | "int8"  (default: "float16")
  language            str   ISO-639-1 code ("es","en",...) or null for auto-detect
  output_dir          str   tmp directory for intermediate files
"""
import os
import time
import asyncio
from typing import Optional, Tuple, List

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.LOCAL
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file

        model_path = config.get("model_size_or_path", "medium")
        device = config.get("device", "cuda")
        compute_type = config.get("compute_type", "float16")
        lang = config.get("language") or None  # None triggers auto-detect
        self.language = lang

        os.makedirs(self.output_dir, exist_ok=True)

        from faster_whisper import WhisperModel
        logger.bind(tag=TAG).info(
            f"Loading faster-whisper '{model_path}' on {device} ({compute_type})"
        )
        self.model = WhisperModel(model_path, device=device, compute_type=compute_type)
        logger.bind(tag=TAG).info("faster-whisper ready")

    def requires_file(self) -> bool:
        return True

    def prefers_temp_file(self) -> bool:
        # Use a throw-away temp file so we don't accumulate WAV files in output_dir.
        return True

    async def speech_to_text(
        self,
        opus_data: List[bytes],
        session_id: str,
        audio_format: str = "opus",
        artifacts=None,
    ) -> Tuple[Optional[str], Optional[str]]:
        if artifacts is None:
            return "", None

        # temp_path is preferred; file_path is the fallback when delete_audio_file=False
        audio_path = artifacts.temp_path or artifacts.file_path
        if not audio_path:
            return "", None

        try:
            start_time = time.time()
            segments, info = await asyncio.to_thread(self._transcribe, audio_path)
            text = " ".join(s.text.strip() for s in segments).strip()
            logger.bind(tag=TAG).debug(
                f"faster-whisper: {time.time() - start_time:.3f}s | "
                f"lang={info.language} p={info.language_probability:.2f} | {text!r}"
            )
            return text, audio_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"faster-whisper transcription failed: {e}", exc_info=True)
            return "", None

    def _transcribe(self, audio_path: str):
        """Blocking transcription — called via asyncio.to_thread."""
        segments, info = self.model.transcribe(
            audio_path,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        # Consume the generator here (inside the thread) before returning.
        return list(segments), info
