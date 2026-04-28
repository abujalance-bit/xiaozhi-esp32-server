"""Ollama Vision LLM provider.

Uses Ollama's OpenAI-compatible API to run multimodal models like
minicpm-v, llava, or bakllava locally.

Example config:
  OllamaVLLM:
    type: ollama_vllm
    model_name: minicpm-v
    base_url: http://ollama:11434/v1
    api_key: ollama
    max_tokens: 500
"""
import openai
from config.logger import setup_logging
from core.providers.vllm.base import VLLMProviderBase

TAG = __name__
logger = setup_logging()


class VLLMProvider(VLLMProviderBase):
    def __init__(self, config):
        self.model_name = config.get("model_name", "minicpm-v")
        self.base_url = config.get("base_url", "http://localhost:11434/v1")
        self.api_key = config.get("api_key", "ollama")
        self.max_tokens = int(config.get("max_tokens", 500))
        self.temperature = float(config.get("temperature", 0.7))

        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def response(self, question, base64_image):
        try:
            messages = [
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
            ]
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.bind(tag=TAG).error(f"Ollama VLLM error: {e}")
            return f"Vision analysis failed: {e}"
