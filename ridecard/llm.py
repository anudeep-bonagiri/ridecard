"""Tiny client for any local OpenAI-compatible server (Ollama, llama.cpp, LM Studio, vLLM).

Nothing here talks to a hosted model. Default is Ollama on localhost with Gemma 3.
"""
import json
import os
import re
import urllib.request

BASE_URL = os.environ.get("RIDECARD_LLM_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("RIDECARD_MODEL", "gemma3:4b")
if os.environ.get("RIDECARD_GGUF"):
    MODEL = os.path.basename(os.environ["RIDECARD_GGUF"])


GGUF = os.environ.get("RIDECARD_GGUF")  # optional: run a GGUF file in-process with llama-cpp-python, no server
_local = None


def _local_model():
    global _local
    if _local is None:
        from llama_cpp import Llama
        _local = Llama(GGUF, n_ctx=4096, verbose=False)
    return _local


def chat(messages, max_tokens=600, temperature=0.4):
    if GGUF:
        r = _local_model().create_chat_completion(messages, max_tokens=max_tokens, temperature=temperature)
        return r["choices"][0]["message"]["content"].strip()
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"].strip()


def chat_json(messages, max_tokens=300):
    """Ask for JSON and pull the first object out of the reply. Small models wrap JSON in prose or fences."""
    text = chat(messages, max_tokens=max_tokens, temperature=0.1)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"model did not return JSON: {text[:200]}")
    return json.loads(m.group(0))


def available():
    if GGUF:
        return os.path.exists(GGUF)
    try:
        urllib.request.urlopen(BASE_URL.rstrip("/") + "/models", timeout=3)
        return True
    except Exception:
        return False
