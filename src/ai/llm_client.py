"""OpenAI 兼容 LLM 客户端（单例复用）。"""
from __future__ import annotations

import base64
from pathlib import Path

import yaml
from openai import OpenAI

PIPELINE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pipeline.yaml"

_client: OpenAI | None = None
_config: dict | None = None


def _get_config() -> dict:
    global _config
    if _config is None:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
    return _config


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        from src.config import config
        cfg = _get_config()
        api_cfg = cfg.get("api", {})
        _client = OpenAI(
            base_url=api_cfg.get("base_url", config.llm_base_url or ""),
            api_key=config.llm_api_key or api_cfg.get("api_key", ""),
            timeout=api_cfg.get("timeout_seconds", 120),
        )
    return _client


def chat(
    messages: list[dict],
    role: str = "filter",
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    cfg = _get_config()
    model_cfg = cfg.get("models", {}).get(role, {})
    model_name = model_cfg.get("name", "claude-sonnet-4-6")
    resp = _get_client().chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens or model_cfg.get("max_tokens", 1024),
        temperature=temperature if temperature is not None else model_cfg.get("temperature", 0.3),
    )
    return resp.choices[0].message.content or ""


def encode_image(image_path: str | Path) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片不存在: {path}")
    ext = path.suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def chat_vision(
    text_prompt: str,
    image_paths: list[str] = [],
    role: str = "analyzer",
) -> str:
    cfg = _get_config()
    model_cfg = cfg.get("models", {}).get(role, {})
    model_name = model_cfg.get("name", "gpt-5.4")
    content: list[dict] = [{"type": "text", "text": text_prompt}]
    for img_path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": encode_image(img_path)}})
    resp = _get_client().chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": content}],
        max_tokens=model_cfg.get("max_tokens", 4096),
        temperature=model_cfg.get("temperature", 0.3),
    )
    return resp.choices[0].message.content or ""

