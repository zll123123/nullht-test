"""CSL 对话接口客户端。"""

from __future__ import annotations

from typing import Any, Dict

import requests
from loguru import logger
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.app_config import AppConfig

DEFAULT_HEADERS = {"Content-Type": "application/json"}


def create_session() -> Session:
    """创建带重试能力的请求会话。

    Args:
        None

    Returns:
        Session: 请求会话。
    """
    retry_kwargs: Dict[str, Any] = {
        "total": 2,
        "backoff_factor": 1,
        "status_forcelist": [429, 500, 502, 503, 504],
    }
    try:
        retry = Retry(allowed_methods=["POST"], **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=["POST"], **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def build_headers(config: AppConfig) -> Dict[str, str]:
    """构建请求头。

    Args:
        config: 运行配置。

    Returns:
        Dict[str, str]: 请求头。
    """
    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = config.accept
    headers["Accept-Language"] = config.accept_language
    headers["Connection"] = "keep-alive"
    headers["User-Agent"] = config.user_agent
    if config.origin:
        headers["Origin"] = config.origin
    if config.referer:
        headers["Referer"] = config.referer
    if config.token:
        token = config.token.strip()
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    if config.cookie:
        headers["Cookie"] = config.cookie
    return headers


def post_json(session: Session, config: AppConfig, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """发送 POST 请求。

    Args:
        session: 请求会话。
        config: 运行配置。
        path: 接口路径。
        payload: 请求体。

    Returns:
        Dict[str, Any]: JSON 响应。
    """
    url = f"{config.base_url}{path}"
    response: Response = session.post(
        url,
        json=payload,
        headers=build_headers(config),
        timeout=config.timeout_seconds,
        verify=config.verify_ssl,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"接口返回非 JSON 对象: {url}")
    return data


def get_json(session: Session, config: AppConfig, path: str) -> Dict[str, Any]:
    """发送 GET 请求。

    Args:
        session: 请求会话。
        config: 运行配置。
        path: 接口路径。

    Returns:
        Dict[str, Any]: JSON 响应。
    """
    url = f"{config.base_url}{path}"
    response: Response = session.get(
        url,
        headers=build_headers(config),
        timeout=config.timeout_seconds,
        verify=config.verify_ssl,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"接口返回非 JSON 对象: {url}")
    return data


def normalize_message(data: Dict[str, Any]) -> str:
    """提取系统消息文本。

    Args:
        data: 响应数据。

    Returns:
        str: 文本消息。
    """
    message = data.get("message", "")
    if isinstance(message, list):
        return "\n".join(str(item) for item in message)
    return str(message or "")


def start_conversation(session: Session, config: AppConfig) -> Dict[str, Any]:
    """启动对话。"""
    return (post_json(session, config, config.start_path, {})).get("data") or {}


def send_message(session: Session, config: AppConfig, session_id: str, message: str) -> Dict[str, Any]:
    """发送消息。"""
    payload = {"message": message, "session_id": session_id}
    return (post_json(session, config, config.message_path, payload)).get("data") or {}


def stop_conversation(session: Session, config: AppConfig, session_id: str) -> Dict[str, Any]:
    """结束对话。"""
    return (post_json(session, config, config.stop_path, {"session_id": session_id})).get("data") or {}


def is_visit_plan_ready(detail_data: Dict[str, Any]) -> bool:
    """判断拜访计划是否已生成。

    Args:
        detail_data: 详情接口返回的 data 字段。

    Returns:
        bool: 是否可用。
    """
    visit_plan = detail_data.get("visit_plan") or {}
    return isinstance(visit_plan, dict) and bool(visit_plan)


def fetch_visit_plan_detail_once(session: Session, config: AppConfig, session_id: str) -> Dict[str, Any]:
    """单次获取拜访计划详情。

    Args:
        session: 请求会话。
        config: 运行配置。
        session_id: 会话 ID。

    Returns:
        Dict[str, Any]: 详情数据；未生成完成时返回空字典。
    """
    if not config.detail_path:
        return {}
    detail_path = f"{config.detail_path.rstrip('/')}/{session_id}"
    try:
        detail_data = (get_json(session, config, detail_path)).get("data") or {}
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = response.status_code if response is not None else 0
        if status_code == 400:
            logger.info("会话 {} 的拜访计划尚未生成完成。", session_id)
            return {}
        raise
    return detail_data if is_visit_plan_ready(detail_data) else {}
