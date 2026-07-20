#!/usr/bin/env python3
"""执行 CSL 完整对话路径测试。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config.app_config import load_app_config, load_env_files
from config.settings import CONFIG_FILE, DATA_FILE, OUTPUT_DIR
from loguru import logger
from reporters.markdown_reporter import MARKDOWN_RECORD_FILE
from reporters.json_reporter import filter_cases, initialize_output_files
from reporters.qase_reporter import initialize_qase_report
from services.case_loader import build_cases
from services.run_service import run_cases
from utils.logger import setup_logger


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
    parser.add_argument(
        "--case-id",
        nargs="+",
        help="只执行指定 case，支持空格或逗号分隔，例如 P017 P021 或 P017,P021",
    )
    parser.add_argument("--dept", "--department", dest="dept", help="只执行指定科室，例如 ICU、心脏外科、肝病、医院管理层/药剂科")
    parser.add_argument("--scenario-keyword", help="只执行 scenario 包含指定关键字的 case，例如 首次拜访")
    parser.add_argument("--first-visit", action="store_true", help="只执行首次拜访路径 case")
    parser.add_argument("--smoke", action="store_true", help="只执行 YAML 中配置的冒烟 case")
    parser.add_argument("--dry-run", action="store_true", help="只校验配置和用例，不发起请求")
    parser.add_argument("--seed", type=int, default=7, help="随机关注点回答的随机种子")
    return parser.parse_args()


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
    initialize_qase_report(OUTPUT_DIR)
    (OUTPUT_DIR / MARKDOWN_RECORD_FILE).write_text("", encoding="utf-8")
    case_collection = build_cases(Path(args.data).expanduser().resolve())
    if args.case_id and args.smoke:
        raise ValueError("--case-id 与 --smoke 不能同时使用")
    selected_cases = filter_cases(
        case_collection.cases,
        args.case_id,
        case_collection.smoke_case_ids if args.smoke else None,
        args.dept,
        "首次拜访" if args.first_visit else args.scenario_keyword,
    )
    if args.dry_run:
        logger.info(
            "dry-run 完成，共加载 {} 个 case。case_id={}, dept={}, smoke={}",
            len(selected_cases),
            args.case_id or "-",
            args.dept or "-",
            args.smoke,
        )
        return 0
    run_cases(selected_cases, case_collection.doctor_rank, config, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
