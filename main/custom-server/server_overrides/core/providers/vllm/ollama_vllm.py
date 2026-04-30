"""Ollama Vision LLM provider.

Uses Ollama's OpenAI-compatible API to run multimodal models locally.
Passes think=false to suppress Qwen3/Qwen3.5 chain-of-thought for vision
tasks — descriptions don't need reasoning, and thinking tokens eat into
max_tokens leaving content empty.

Example config:
  OllamaVLLM:
    type: ollama_vllm
    model_name: qwen3.5:9b
    base_url: http://localhost:11434/v1
    api_key: ollama
    max_tokens: 1000
"""
import requests as _requests
from config.logger import setup_logging
from core.providers.vllm.base import VLLMProviderBase

TAG = __name__
logger = setup_logging()


class VLLMProvider(VLLMProviderBase):
    def __init__(self, config):
        self.model_name = config.get("model_name", "qwen3.5:9b")
        self.base_url = config.get("base_url", "http://localhost:11434/v1").rstrip("/")
        self.max_tokens = int(config.get("max_tokens", 1000))
        self.temperature = float(config.get("temperature", 0.7))

    def response(self, question, base64_image):
        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "think": False,   # disable Qwen3 chain-of-thought; no-op for other models
                "stream": False,
            }

            r = _requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]

            # content is the normal reply; reasoning is Qwen3 thinking fallback
            content = msg.get("content") or msg.get("reasoning") or ""
            content = content.strip()

            if not content:
                return "No pude obtener una descripción de la imagen."
            return content

        except Exception as e:
            logger.bind(tag=TAG).error(f"Ollama VLLM error: {e}")
            return f"No pude analizar la imagen: {e}"
