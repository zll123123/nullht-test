#!/usr/bin/env python3
"""执行 CSL 完整对话路径测试。"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import List

from clients.chat_client import create_session
from config.app_config import AppConfig, load_app_config, load_env_files
from config.runtime_paths import CONFIG_FILE, DATA_FILE, OUTPUT_DIR
from loguru import logger
from services.case_loader import CaseConfig, build_cases
from services.conversation_service import run_case
from utils.execution_record_writer import save_markdown_record
from utils.logger import setup_logger
from utils.result_writer import filter_cases, save_results


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
    rng = random.Random(seed)
    session = create_session()
    for case in selected_cases:
        logger.info("开始执行 {} | {}", case.case_id, case.scenario)
        try:
            case_result = run_case(session, config, doctor_rank, case, rng)
            logger.info("执行完成 {} | validation={}", case.case_id, case_result["validation"]["passed"])
            results.append(case_result)
        except Exception as exc:
            logger.exception("{} 执行失败: {}", case.case_id, exc)
            results.append({"case_id": case.case_id, "scenario": case.scenario, "error": str(exc)})
    output_file = save_results(results)
    markdown_file = save_markdown_record(OUTPUT_DIR, results)
    logger.info("结果已保存: {}", output_file)
    logger.info("执行记录已保存: {}", markdown_file)
    return 0


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
    doctor_rank, cases = build_cases(Path(args.data).expanduser().resolve())
    selected_cases = filter_cases(cases, args.case_id)
    if args.dry_run:
        logger.info("dry-run 完成，共加载 {} 个 case。", len(selected_cases))
        return 0
    return execute_cases(selected_cases, doctor_rank, config, args.seed)


if __name__ == "__main__":
    sys.exit(main())
