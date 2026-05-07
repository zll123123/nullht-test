"""JSON 结果输出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

from config.settings import OUTPUT_DIR
from models.result_model import CaseExecutionResult
from reporters.markdown_reporter import build_summary

RESULT_FILE_NAME = "csl_full_path_results.json"


def initialize_output_files() -> None:
    """初始化输出目录和统一结果文件。"""
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


def save_results(results: List[CaseExecutionResult]) -> Path:
    """保存 JSON 执行结果。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / RESULT_FILE_NAME
    summary = build_summary(results)
    output_file.write_text(
        json.dumps(
            {"summary": summary.to_dict(), "results": [item.to_dict() for item in results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_file


def filter_cases(cases: List[Any], case_id: Optional[str], smoke_case_ids: Optional[List[str]] = None) -> List[Any]:
    """按 case 编号过滤用例。"""
    if not case_id:
        if not smoke_case_ids:
            return cases
        filtered_cases = [case for case in cases if case.case_id in set(smoke_case_ids)]
        if not filtered_cases:
            raise ValueError("未找到任何冒烟 case")
        return filtered_cases
    filtered_cases = [case for case in cases if case.case_id == case_id]
    if not filtered_cases:
        raise ValueError(f"未找到 case: {case_id}")
    return filtered_cases
