"""Override of upstream fun_local.py — adds device passthrough from model config.

The upstream file hard-codes CPU by leaving the `device` parameter out of the
AutoModel call. This override reads `device` from the model config so the web UI
can switch between "cpu" and "cuda:0" without rebuilding the image.
"""
import os
import io
import sys
import time
import asyncio
import psutil

from funasr import AutoModel
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.utils import lang_tag_filter
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()

MAX_RETRIES = 2
RETRY_DELAY = 1


class CaptureOutput:
    def __enter__(self):
        self._output = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = self._output

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self._original_stdout
        self.output = self._output.getvalue()
        self._output.close()
        if self.output:
            logger.bind(tag=TAG).info(self.output.strip())


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()

        min_mem_bytes = 2 * 1024 * 1024 * 1024
        total_mem = psutil.virtual_memory().total
        if total_mem < min_mem_bytes:
            logger.bind(tag=TAG).error(
                f"Less than 2 GB RAM available ({total_mem / (1024**2):.0f} MB) — "
                "FunASR may fail to load"
            )

        self.interface_type = InterfaceType.LOCAL
        self.model_dir = config.get("model_dir")
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file
        device = config.get("device", "cpu")

        os.makedirs(self.output_dir, exist_ok=True)

        logger.bind(tag=TAG).info(f"Loading FunASR model from '{self.model_dir}' on {device}")
        with CaptureOutput():
            self.model = AutoModel(
                model=self.model_dir,
                device=device,
                vad_kwargs={"max_single_segment_time": 30000},
                disable_update=True,
                hub="hf",
            )

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus", artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                if artifacts is None:
                    return "", None

                start_time = time.time()
                result = await asyncio.to_thread(
                    self.model.generate,
                    input=artifacts.pcm_bytes,
                    cache={},
                    language="auto",
                    use_itn=True,
                    batch_size_s=60,
                )
                text = lang_tag_filter(result[0]["text"])
                logger.bind(tag=TAG).debug(
                    f"ASR took {time.time() - start_time:.3f}s | result: {text['content'] if isinstance(text, dict) else text}"
                )
                return text, artifacts.file_path

            except OSError as e:
                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    logger.bind(tag=TAG).error(
                        f"ASR failed after {retry_count} retries: {e}", exc_info=True
                    )
                    return "", None
                logger.bind(tag=TAG).warning(f"ASR retry {retry_count}/{MAX_RETRIES}: {e}")
                time.sleep(RETRY_DELAY)

            except Exception as e:
                logger.bind(tag=TAG).error(f"ASR error: {e}", exc_info=True)
                return "", None
