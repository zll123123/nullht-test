"""日志初始化工具。"""

from __future__ import annotations

import sys

from loguru import logger

from config.runtime_paths import LOG_DIR, LOG_FILE


def setup_logger(level: str) -> None:
    """初始化控制台和文件日志。

    Args:
        level: 日志级别。

    Returns:
        None
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
    logger.add(
        LOG_FILE,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        backtrace=True,
        diagnose=True,
        mode="w",
    )
