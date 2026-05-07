"""关注点匹配 LLM 客户端。"""

from __future__ import annotations

import json
from typing import Any, Dict

import requests

from config.app_config import AppConfig


def build_focus_match_headers(config: AppConfig) -> Dict[str, str]:
    """构建关注点匹配请求头。

    Args:
        config: 运行配置。

    Returns:
        Dict[str, str]: 请求头。
    """
    headers = {"Content-Type": "application/json"}
    if config.llm_api_key:
        headers["Authorization"] = f"Bearer {config.llm_api_key}"
    return headers


def normalize_llm_json(content: str) -> Dict[str, Any]:
    """从模型返回文本中提取 JSON。

    Args:
        content: 模型返回文本。

    Returns:
        Dict[str, Any]: 解析后的 JSON。
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    return json.loads(text)


def build_llm_request_url(config: AppConfig) -> str:
    """构建 LLM 请求地址。

    Args:
        config: 运行配置。

    Returns:
        str: 最终请求 URL。
    """
    base_url = config.llm_base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def call_focus_match_llm(config: AppConfig, prompt: str) -> Dict[str, Any]:
    """调用大模型执行关注点匹配。

    Args:
        config: 运行配置。
        prompt: 用户提示词。

    Returns:
        Dict[str, Any]: 模型结构化结果。
    """
    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    response = requests.post(
        build_llm_request_url(config),
        json=payload,
        headers=build_focus_match_headers(config),
        timeout=config.llm_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("关注点匹配模型返回为空")
    return normalize_llm_json(content)
