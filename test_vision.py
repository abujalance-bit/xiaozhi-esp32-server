#!/usr/bin/env python3
"""
Test Ollama vision via the OpenAI-compatible API.

Usage:
  python test_vision.py                            # uses qwen3.5:9b + generated test image
  python test_vision.py qwen3.5:9b                 # explicit model, generated image
  python test_vision.py qwen3.5:9b /path/to/photo.jpg
  python test_vision.py qwen3.5:9b /path/to/photo.jpg http://localhost:11434/v1
"""

import sys
import base64
import json
import struct
import zlib

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


def make_test_png():
    """Generate a tiny 8x8 red/white checkerboard PNG — no PIL dependency."""
    width, height = 8, 8
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            row += [255, 0, 0] if (x + y) % 2 == 0 else [255, 255, 255]
        rows.append(bytes([0] + row))

    def png_chunk(tag, data):
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + png_chunk(b"IEND", b"")
    )


def test_vision(model: str, base_url: str, image_path: str = None):
    if image_path:
        with open(image_path, "rb") as f:
            image_data = f.read()
        ext = image_path.lower()
        mime = "image/jpeg" if ext.endswith((".jpg", ".jpeg")) else "image/png"
        print(f"Image: {image_path} ({len(image_data)} bytes)")
    else:
        print("No image file given — using generated 8x8 checkerboard PNG.")
        image_data = make_test_png()
        mime = "image/png"

    b64 = base64.b64encode(image_data).decode()
    print(f"Base64 size: {len(b64)} chars")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe what you see in this image in one sentence.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 1000,
        "think": False,   # disable Qwen3 chain-of-thought so answer lands in content
        "stream": False,
    }

    url = f"{base_url.rstrip('/')}/chat/completions"
    print(f"\nPOST {url}")
    print(f"Model:  {model}")
    print(f"Prompt: 'Describe what you see in this image in one sentence.'\n")

    try:
        r = requests.post(url, json=payload, timeout=120)
    except requests.exceptions.ConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        print("Is Ollama running? Try: ollama serve")
        return
    except requests.exceptions.Timeout:
        print("TIMEOUT after 120s — model may not be loaded or is very slow")
        return

    print(f"HTTP status: {r.status_code}")

    try:
        data = r.json()
    except Exception:
        print(f"Non-JSON response body:\n{r.text[:500]}")
        return

    print("\n=== Full response ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    print("\n=== content field ===")
    choices = data.get("choices", [])
    if not choices:
        print("No choices — model error or wrong model name")
        error = data.get("error", {})
        if error:
            print(f"Error: {error}")
        return

    msg = choices[0].get("message", {})
    content = msg.get("content")
    reasoning = msg.get("reasoning")
    finish_reason = choices[0].get("finish_reason")
    print(f"finish_reason: {finish_reason}")
    print(f"content:   {repr(content)}")
    print(f"reasoning: {repr(reasoning[:120] + '...' if reasoning and len(reasoning) > 120 else reasoning)}")

    effective = (content or reasoning or "").strip()
    if effective:
        print(f"\n--- Effective answer ---\n{effective}")
    else:
        print("\n*** Both content and reasoning are empty — model does not support vision or wrong model name ***")


if __name__ == "__main__":
    model      = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:9b"
    image_path = sys.argv[2] if len(sys.argv) > 2 else None
    base_url   = sys.argv[3] if len(sys.argv) > 3 else "http://192.168.1.72:11434/v1"

    test_vision(model, base_url, image_path)
