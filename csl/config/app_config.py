"""应用配置加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from config.runtime_paths import DEV_ENV_FILE, ENV_FILE, LLM_CONFIG_FILE
from utils.yaml_loader import load_yaml_file


@dataclass
class AppConfig:
    """接口运行配置。"""

    base_url: str
    start_path: str
    message_path: str
    stop_path: str
    detail_path: str
    timeout_seconds: int
    detail_poll_wait_seconds: int
    detail_poll_interval_seconds: int
    verify_ssl: bool
    default_focus_answer: str
    log_level: str
    accept: str
    accept_language: str
    origin: str
    referer: str
    user_agent: str
    token: str
    cookie: str
    llm_enabled: bool
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_timeout_seconds: int


def load_dotenv_file(env_path: Path) -> None:
    """从本地环境文件加载键值对。

    Args:
        env_path: 环境变量文件路径。

    Returns:
        None
    """
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env_files() -> None:
    """按优先级加载环境变量文件。

    Args:
        None

    Returns:
        None
    """
    if ENV_FILE.exists():
        load_dotenv_file(ENV_FILE)
        return
    if DEV_ENV_FILE.exists():
        load_dotenv_file(DEV_ENV_FILE)


def load_app_config(config_path: Path) -> AppConfig:
    """加载并构建应用配置。

    Args:
        config_path: 配置 YAML 路径。

    Returns:
        AppConfig: 运行配置对象。
    """
    config_data = load_yaml_file(config_path)
    llm_config_data = load_yaml_file(LLM_CONFIG_FILE) if LLM_CONFIG_FILE.exists() else {}
    return AppConfig(
        base_url=os.getenv("CSL_BASE_URL", str(config_data["base_url"])).rstrip("/"),
        start_path=os.getenv("CSL_START_PATH", str(config_data["start_path"])),
        message_path=os.getenv("CSL_MESSAGE_PATH", str(config_data["message_path"])),
        stop_path=os.getenv("CSL_STOP_PATH", str(config_data["stop_path"])),
        detail_path=os.getenv("CSL_DETAIL_PATH", str(config_data.get("detail_path", ""))),
        timeout_seconds=int(os.getenv("CSL_TIMEOUT_SECONDS", config_data["timeout_seconds"])),
        detail_poll_wait_seconds=int(
            os.getenv("CSL_DETAIL_POLL_WAIT_SECONDS", config_data.get("detail_poll_wait_seconds", 240))
        ),
        detail_poll_interval_seconds=int(
            os.getenv("CSL_DETAIL_POLL_INTERVAL_SECONDS", config_data.get("detail_poll_interval_seconds", 15))
        ),
        verify_ssl=os.getenv("CSL_VERIFY_SSL", str(config_data["verify_ssl"])).lower() == "true",
        default_focus_answer=os.getenv("CSL_DEFAULT_FOCUS_ANSWER", str(config_data["default_focus_answer"])),
        log_level=os.getenv("CSL_LOG_LEVEL", str(config_data["log_level"])),
        accept=os.getenv("CSL_ACCEPT", str(config_data.get("accept", "application/json, text/plain, */*"))),
        accept_language=os.getenv("CSL_ACCEPT_LANGUAGE", str(config_data.get("accept_language", "zh-CN,zh;q=0.9"))),
        origin=os.getenv("CSL_ORIGIN", str(config_data.get("origin", ""))),
        referer=os.getenv("CSL_REFERER", str(config_data.get("referer", ""))),
        user_agent=os.getenv(
            "CSL_USER_AGENT",
            str(
                config_data.get(
                    "user_agent",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                )
            ),
        ),
        token=os.getenv("CSL_BEARER_TOKEN", ""),
        cookie=os.getenv("CSL_COOKIE", ""),
        llm_enabled=os.getenv(
            "CSL_LLM_ENABLED",
            str(llm_config_data.get("llm_enabled", False)),
        ).lower()
        == "true",
        llm_base_url=os.getenv(
            "CSL_LLM_BASE_URL",
            str(llm_config_data.get("llm_base_url", "")).rstrip("/"),
        ),
        llm_model=os.getenv(
            "CSL_LLM_MODEL",
            str(llm_config_data.get("llm_model", "")),
        ),
        llm_api_key=os.getenv("CSL_LLM_API_KEY", ""),
        llm_timeout_seconds=int(
            os.getenv(
                "CSL_LLM_TIMEOUT_SECONDS",
                llm_config_data.get("llm_timeout_seconds", 30),
            )
        ),
    )
