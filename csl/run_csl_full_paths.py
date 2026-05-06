#!/usr/bin/env python3
"""执行 CSL 完整对话路径测试。"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import List

from clients.chat_client import create_session
from config.app_config import AppConfig, load_app_config, load_env_files
from config.runtime_paths import CONFIG_FILE, DATA_FILE, OUTPUT_DIR
from loguru import logger
from services.case_loader import CaseConfig, build_cases
from services.conversation_service import build_pending_case_result
from services.plan_polling_service import (
    build_case_index,
    has_pending_results,
    mark_pending_metadata,
    poll_pending_case,
)
from utils.execution_record_writer import MARKDOWN_RECORD_FILE, save_markdown_record
from utils.logger import setup_logger
from utils.result_writer import filter_cases, initialize_output_files, save_results


def build_execution_error_result(case: CaseConfig, error_message: str) -> dict:
    """构建执行失败结果。

    Args:
        case: 当前用例。
        error_message: 失败原因。

    Returns:
        dict: 执行失败结果。
    """
    return {
        "case_id": case.case_id,
        "scenario": case.scenario,
        "status": "EXECUTION_FAILED",
        "result_type": "执行失败",
        "error": error_message,
        "failure_reason": error_message,
    }


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Args:
        None

    Returns:
        argparse.Namespace: 参数对象。
    """
    parser = argparse.ArgumentParser(description="执行 CSL 完整对话路径测试。")
    parser.add_argument("--config", default=str(CONFIG_FILE), help="配置 YAML 路径")
    parser.add_argument("--data", default=str(DATA_FILE), help="测试路径 YAML 路径")
    parser.add_argument("--case-id", help="只执行单个 case，例如 P017")
    parser.add_argument("--dry-run", action="store_true", help="只校验配置和用例，不发起请求")
    parser.add_argument("--seed", type=int, default=7, help="随机关注点回答的随机种子")
    return parser.parse_args()


def execute_cases(selected_cases: List[CaseConfig], doctor_rank: str, config: AppConfig, seed: int) -> int:
    """执行选中的 case。

    Args:
        selected_cases: 待执行用例。
        doctor_rank: 医生职称回答。
        config: 运行配置。
        seed: 随机种子。

    Returns:
        int: 进程退出码。
    """
    results = []
    case_index = build_case_index(selected_cases)
    rng = random.Random(seed)
    session = create_session()
    for case in selected_cases:
        poll_pending_results(session, config, results, case_index, wait_for_next_window=False)
        logger.info("开始执行 {} | {}", case.case_id, case.scenario)
        try:
            case_result = build_pending_case_result(session, config, doctor_rank, case, rng)
            mark_pending_metadata(case_result, config)
            logger.info("对话完成 {} | session_id={}", case.case_id, case_result["session_id"])
            results.append(case_result)
            flush_outputs(results)
        except Exception as exc:
            logger.exception("{} 执行失败: {}", case.case_id, exc)
            results.append(build_execution_error_result(case, str(exc)))
            flush_outputs(results)
    drain_pending_results(session, config, results, case_index)
    return 0


def poll_pending_results(
    session: object,
    config: AppConfig,
    results: List[dict],
    case_index: dict,
    wait_for_next_window: bool,
) -> None:
    """按当前时机轮询待补全结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        results: 全部结果。
        case_index: 用例索引。
        wait_for_next_window: 是否等待到下一次轮询窗口。

    Returns:
        None
    """
    if not has_pending_results(results):
        return
    now_ts = time.time()
    if wait_for_next_window:
        next_poll_at = min(float(item.get("next_poll_at") or now_ts) for item in results if item.get("status") == "PENDING_PLAN")
        sleep_seconds = max(next_poll_at - now_ts, 0)
        if sleep_seconds > 0:
            logger.info("等待 {:.0f} 秒后轮询待生成的拜访计划。", sleep_seconds)
            time.sleep(sleep_seconds)
        now_ts = time.time()
    updated = False
    for item in results:
        if item.get("status") != "PENDING_PLAN":
            continue
        if not wait_for_next_window and now_ts < float(item.get("next_poll_at") or 0):
            continue
        case = case_index[item["case_id"]]
        poll_pending_case(session, config, case, item, now_ts)
        updated = True
    if updated:
        flush_outputs(results)


def drain_pending_results(
    session: object,
    config: AppConfig,
    results: List[dict],
    case_index: dict,
) -> None:
    """补全全部待获取的拜访计划结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        results: 全部结果。
        case_index: 用例索引。

    Returns:
        None
    """
    while has_pending_results(results):
        poll_pending_results(session, config, results, case_index, wait_for_next_window=True)


def flush_outputs(results: List[dict]) -> None:
    """刷新统一输出文件。

    Args:
        results: 全部结果。

    Returns:
        None
    """
    output_file = save_results(results)
    markdown_file = save_markdown_record(OUTPUT_DIR, results)
    logger.info("结果已保存: {}", output_file)
    logger.info("执行记录已保存: {}", markdown_file)


def main() -> int:
    """程序入口。

    Args:
        None

    Returns:
        int: 进程退出码。
    """
    args = parse_args()
    load_env_files()
    config_path = Path(args.config).expanduser().resolve()
    config = load_app_config(config_path)
    setup_logger(config.log_level)
    initialize_output_files()
    (OUTPUT_DIR / MARKDOWN_RECORD_FILE).write_text("", encoding="utf-8")
    doctor_rank, cases = build_cases(Path(args.data).expanduser().resolve())
    selected_cases = filter_cases(cases, args.case_id)
    if args.dry_run:
        logger.info("dry-run 完成，共加载 {} 个 case。", len(selected_cases))
        return 0
    return execute_cases(selected_cases, doctor_rank, config, args.seed)


if __name__ == "__main__":
    sys.exit(main())
