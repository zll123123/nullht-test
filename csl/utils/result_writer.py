"""执行结果输出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.runtime_paths import OUTPUT_DIR
from utils.execution_record_writer import build_summary

RESULT_FILE_NAME = "csl_full_path_results.json"


def initialize_output_files() -> None:
    """初始化输出目录和统一结果文件。

    Args:
        None

    Returns:
        None
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / RESULT_FILE_NAME
    output_file.write_text(
        json.dumps(
            {"summary": {"passed": 0, "failed": 0, "errors": 0, "pending": 0, "total": 0}, "results": []},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def save_results(results: List[Dict[str, Any]]) -> Path:
    """保存 JSON 执行结果。

    Args:
        results: 全部执行结果。

    Returns:
        Path: 输出文件路径。
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / RESULT_FILE_NAME
    output_file.write_text(
        json.dumps({"summary": build_summary(results), "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_file


def filter_cases(cases: List[Any], case_id: Optional[str]) -> List[Any]:
    """按 case 编号过滤用例。

    Args:
        cases: 全部 case 列表。
        case_id: 可选目标 case 编号。

    Returns:
        List[Any]: 过滤后的 case 列表。
    """
    if not case_id:
        return cases
    filtered_cases = [case for case in cases if case.case_id == case_id]
    if not filtered_cases:
        raise ValueError(f"未找到 case: {case_id}")
    return filtered_cases
