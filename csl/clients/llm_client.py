"""通用 LLM 客户端，封装关注点匹配和对话评估共用的模型请求能力。"""

from __future__ import annotations

import json
from typing import Any, Dict

import requests

from config.app_config import AppConfig
from utils.api_timing import ApiCallCollector, timed_api_call


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


@timed_api_call()
def execute_llm_request(
    config: AppConfig,
    payload: Dict[str, Any],
    path: str,
    method: str = "POST",
    api_name: str = "",
    request_identifier: str = "",
    session_id: str = "",
    api_collector: ApiCallCollector | None = None,
) -> tuple[int, Dict[str, Any]]:
    """发送 LLM 原始请求。

    Args:
        config: 运行配置。
        payload: 请求体。
        path: 请求地址。
        method: 请求方法，占位给装饰器读取。
        api_name: 接口名称。
        request_identifier: 接口关联标识。
        session_id: 会话 ID。
        api_collector: 接口结果收集器。

    Returns:
        tuple[int, Dict[str, Any]]: HTTP 状态码和响应 JSON。
    """
    del method, api_name, request_identifier, session_id, api_collector
    response = requests.post(
        path,
        json=payload,
        headers=build_focus_match_headers(config),
        timeout=config.llm_timeout_seconds,
    )
    response.raise_for_status()
    return response.status_code, response.json()


def call_llm_text(
    config: AppConfig,
    prompt: str,
    api_name: str,
    api_collector: ApiCallCollector | None = None,
    session_id: str = "",
    case_id: str = "",
) -> str:
    """调用大模型并返回文本内容。

    Args:
        config: 运行配置。
        prompt: 用户提示词。
        api_name: 接口调用名称。
        api_collector: 接口结果收集器。
        session_id: 会话 ID。
        case_id: 用例标识。

    Returns:
        str: 模型返回文本。
    """
    request_url = build_llm_request_url(config)
    payload = {
        "model": config.llm_model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    data = execute_llm_request(
        config=config,
        payload=payload,
        path=request_url,
        api_name=api_name,
        request_identifier=session_id or case_id,
        session_id=session_id,
        api_collector=api_collector,
    )
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM 返回为空")
    return content


def call_llm_json(
    config: AppConfig,
    prompt: str,
    api_name: str,
    api_collector: ApiCallCollector | None = None,
    session_id: str = "",
    case_id: str = "",
) -> Dict[str, Any]:
    """调用大模型并解析 JSON。

    Args:
        config: 运行配置。
        prompt: 用户提示词。
        api_name: 接口调用名称。
        api_collector: 接口结果收集器。
        session_id: 会话 ID。
        case_id: 用例标识。

    Returns:
        Dict[str, Any]: 模型结构化结果。
    """
    content = call_llm_text(
        config=config,
        prompt=prompt,
        api_name=api_name,
        api_collector=api_collector,
        session_id=session_id,
        case_id=case_id,
    )
    return normalize_llm_json(content)


def call_focus_match_llm(
    config: AppConfig,
    prompt: str,
    api_collector: ApiCallCollector | None = None,
    session_id: str = "",
    case_id: str = "",
) -> Dict[str, Any]:
    """调用大模型执行关注点匹配。

    Args:
        config: 运行配置。
        prompt: 用户提示词。
        api_collector: 接口结果收集器。
        session_id: 会话 ID。
        case_id: 用例标识。

    Returns:
        Dict[str, Any]: 模型结构化结果。
    """
    return call_llm_json(
        config=config,
        prompt=prompt,
        api_name="call_focus_match_llm",
        api_collector=api_collector,
        session_id=session_id,
        case_id=case_id,
    )
