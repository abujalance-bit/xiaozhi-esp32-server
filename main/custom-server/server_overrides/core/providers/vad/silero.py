"""Override of upstream vad/silero.py — finds the ONNX model from the silero_vad
pip package instead of requiring a manually-cloned git repo at model_dir.

The upstream provider expects the GitHub repo structure:
  {model_dir}/src/silero_vad/data/silero_vad.onnx

The pip package (silero_vad in requirements.txt) bundles the same ONNX file at:
  {site-packages}/silero_vad/data/silero_vad.onnx

This override tries the pip package location first, then falls back to the
git-clone path if model_dir is set, so both deployment styles work.
"""
import os
import time
import numpy as np
import opuslib_next
import onnxruntime
from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

TAG = __name__
logger = setup_logging()


def _locate_onnx(config_model_dir: str | None) -> str:
    # 1. pip package (silero_vad installed from requirements.txt)
    try:
        import silero_vad as _pkg
        pip_path = os.path.join(os.path.dirname(_pkg.__file__), "data", "silero_vad.onnx")
        if os.path.isfile(pip_path):
            logger.bind(tag=TAG).info(f"Silero VAD model found via pip package: {pip_path}")
            return pip_path
    except ImportError:
        pass

    # 2. Cloned-repo layout at model_dir
    if config_model_dir:
        repo_path = os.path.join(
            config_model_dir, "src", "silero_vad", "data", "silero_vad.onnx"
        )
        if os.path.isfile(repo_path):
            logger.bind(tag=TAG).info(f"Silero VAD model found at model_dir: {repo_path}")
            return repo_path

    raise FileNotFoundError(
        "silero_vad.onnx not found. Either:\n"
        "  • Install the pip package:  pip install silero-vad  (already in requirements.txt)\n"
        "  • Or set model_dir to the cloned snakers4/silero-vad repo path"
    )


class VADProvider(VADProviderBase):
    def __init__(self, config):
        logger.bind(tag=TAG).info("Initialising SileroVAD", config)

        model_path = _locate_onnx(config.get("model_dir"))
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        # VAD runs on CPU — the model is tiny and GPU overhead is not worth it
        self.session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=opts
        )

        threshold = config.get("threshold", "0.5")
        threshold_low = config.get("threshold_low", "0.2")
        min_silence_duration_ms = config.get("min_silence_duration_ms", "1000")

        self.vad_threshold = float(threshold) if threshold else 0.5
        self.vad_threshold_low = float(threshold_low) if threshold_low else 0.2
        self.silence_threshold_ms = (
            int(min_silence_duration_ms) if min_silence_duration_ms else 1000
        )
        self.frame_window_threshold = 3

    def _init_connection_state(self, conn):
        if not hasattr(conn, "_vad_opus_decoder"):
            conn._vad_opus_decoder = opuslib_next.Decoder(16000, 1)
        if not hasattr(conn, "_vad_state"):
            conn._vad_state = np.zeros((2, 1, 128), dtype=np.float32)
        if not hasattr(conn, "_vad_context"):
            conn._vad_context = np.zeros((1, 64), dtype=np.float32)

    def release_conn_resources(self, conn):
        for attr in ("_vad_opus_decoder", "_vad_state", "_vad_context"):
            if hasattr(conn, attr):
                try:
                    delattr(conn, attr)
                except Exception:
                    pass

    def is_vad(self, conn, opus_packet):
        if conn.client_listen_mode == "manual":
            return True

        try:
            self._init_connection_state(conn)

            pcm_frame = conn._vad_opus_decoder.decode(opus_packet, 960)
            conn.client_audio_buffer.extend(pcm_frame)

            client_have_voice = False
            while len(conn.client_audio_buffer) >= 512 * 2:
                chunk = conn.client_audio_buffer[: 512 * 2]
                conn.client_audio_buffer = conn.client_audio_buffer[512 * 2 :]

                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                audio_input = np.concatenate(
                    [conn._vad_context, audio_float32.reshape(1, -1)], axis=1
                ).astype(np.float32)

                ort_inputs = {
                    "input": audio_input,
                    "state": conn._vad_state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                out, state = self.session.run(None, ort_inputs)

                conn._vad_state = state
                conn._vad_context = audio_input[:, -64:]
                speech_prob = out.item()

                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice

                conn.last_is_voice = is_voice
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.vad_last_voice_time
                    if stop_duration >= self.silence_threshold_ms:
                        conn.client_voice_stop = True
                if client_have_voice:
                    conn.client_have_voice = True
                    conn.vad_last_voice_time = time.time() * 1000

            return client_have_voice

        except opuslib_next.OpusError as e:
            logger.bind(tag=TAG).info(f"Opus decode error: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"VAD error: {e}")
