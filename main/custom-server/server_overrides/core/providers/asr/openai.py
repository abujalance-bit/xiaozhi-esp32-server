"""OpenAI-compatible ASR provider with optional language hint.

Adds a `language` config field (ISO-639-1, e.g. "es") that is forwarded to
the Whisper transcription endpoint. Groq and OpenAI both accept this parameter
and it improves accuracy significantly for non-English languages.
"""
import os
import time
from typing import Optional, Tuple, List

import requests

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")
        self.language = config.get("language") or None  # e.g. "es", "en", None = auto
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file

        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
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
        file_path = artifacts.file_path
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {"model": self.model}
            if self.language:
                data["language"] = self.language

            with open(file_path, "rb") as audio_file:
                start_time = time.time()
                response = requests.post(
                    self.api_url,
                    files={"file": audio_file},
                    data=data,
                    headers=headers,
                )
                logger.bind(tag=TAG).debug(
                    f"语音识别耗时: {time.time() - start_time:.3f}s | 结果: {response.text}"
                )

            if response.status_code == 200:
                return response.json().get("text", ""), file_path
            else:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
