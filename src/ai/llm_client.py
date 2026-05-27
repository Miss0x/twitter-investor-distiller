"""
OpenAI 兼容 LLM 客户端（单例复用）
===============================
整个项目的 AI 调用入口。特点：
1. 单例模式：只创建一个 OpenAI 客户端实例，避免重复初始化
2. 多角色配置：不同任务（filter/analyzer）可用不同的模型名、token 数、温度
3. 多模态支持：chat_vision() 可传入图片 base64 编码进行视觉分析
4. 指数退避重试：网络波动时自动重试，间隔 1s/2s/4s

依赖配置：
- config/pipeline.yaml：定义 API base_url、模型名、超时时间、模型角色参数
- src/config.py：提供统一的 .env 密钥管理
"""

from __future__ import annotations

import base64
import time as _time
from pathlib import Path

import yaml
from openai import OpenAI

# ── 配置文件路径：项目根目录/config/pipeline.yaml ──
PIPELINE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pipeline.yaml"

# ── 全局单例 ──
_client: OpenAI | None = None       # OpenAI 客户端实例，全局复用
_config: dict | None = None         # pipeline.yaml 配置缓存，懒加载


def _get_config() -> dict:
    """
    懒加载 pipeline.yaml 配置。
    首次调用时读取文件，后续直接返回缓存的 dict。
    
    Returns:
        dict: pipeline.yaml 的完整配置，包含 api/models 等节
    """
    global _config
    if _config is None:
        with open(PIPELINE_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
    return _config


def _get_client() -> OpenAI:
    """
    获取或创建 OpenAI 客户端单例。
    base_url 和 api_key 优先使用 src/config.py 中的 .env 值，
    其次使用 pipeline.yaml 中的硬编码值（开发调试用）。
    
    Returns:
        OpenAI: 已配置的客户端实例
    """
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
    max_retries: int = 3,
) -> str:
    """
    纯文本对话（核心函数，流水线中过滤和分析都用它）。
    
    根据 role 从 pipeline.yaml 的 models 节读取对应的模型名和默认参数。
    支持指数退避重试（1s → 2s → 4s），避免偶发网络错误导致任务失败。
    
    Args:
        messages: OpenAI 格式的消息列表，如 [{"role": "system", "content": "..."},
                  {"role": "user", "content": "..."}]
        role: 模型角色名（"filter"/"analyzer"），用于从配置文件查找对应模型
        max_tokens: 最大输出 token 数，None 则使用配置文件默认值
        temperature: 采样温度（0-1），None 则使用配置文件默认值
        max_retries: 最大重试次数（默认 3 次）
    
    Returns:
        str: 模型返回的文本内容
    
    Raises:
        最后一次请求的异常（所有重试耗尽后）
    """
    cfg = _get_config()
    model_cfg = cfg.get("models", {}).get(role, {})
    model_name = model_cfg.get("name", "gpt-4o")
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = _get_client().chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens or model_cfg.get("max_tokens", 1024),
                temperature=temperature if temperature is not None else model_cfg.get("temperature", 0.3),
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                _time.sleep(2 ** attempt)  # 指数退避：1s, 2s, 4s
    raise last_err


def encode_image(image_path: str | Path) -> str:
    """
    将本地图片编码为 OpenAI Vision API 要求的 data URL 格式。
    
    Args:
        image_path: 图片文件路径
    
    Returns:
        str: data:image/{mime};base64,{data} 格式的字符串
    
    Raises:
        FileNotFoundError: 图片文件不存在
    """
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
    """
    多模态对话：文本 + 图片 → LLM 分析。
    用于推文分析时，将推文文字和图片一起发给模型，获取更准确的投资信号判断。
    
    Args:
        text_prompt: 文本提示词（包含推文内容和分析要求）
        image_paths: 本地图片路径列表（最多 3 张，避免 token 过大）
        role: 模型角色名（默认 "analyzer"）
    
    Returns:
        str: 模型输出的分析结果（JSON 格式）
    """
    cfg = _get_config()
    model_cfg = cfg.get("models", {}).get(role, {})
    model_name = model_cfg.get("name", "gpt-5.4")
    # 构建多模态 content 数组：先放文字，再逐张追加图片
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
