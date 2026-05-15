"""JSON 结果输出。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, List, Optional

from config.settings import OUTPUT_DIR
from models.result_model import CaseExecutionResult
from reporters.markdown_reporter import build_summary
from services.case_loader import normalize_department

RESULT_FILE_NAME = "csl_full_path_results.json"


def initialize_output_files() -> None:
    """初始化输出目录和统一结果文件。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
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


def filter_cases(
    cases: List[Any],
    case_id: Optional[str],
    smoke_case_ids: Optional[List[str]] = None,
    department: Optional[str] = None,
) -> List[Any]:
    """按编号、冒烟集和科室过滤用例。"""
    filtered_cases = list(cases)
    if department:
        target_department = normalize_department(department)
        filtered_cases = [case for case in filtered_cases if normalize_department(str(case.department)) == target_department]
        if not filtered_cases:
            raise ValueError(f"未找到科室为 {department} 的 case")
    if smoke_case_ids:
        smoke_case_id_set = set(smoke_case_ids)
        filtered_cases = [case for case in filtered_cases if case.case_id in smoke_case_id_set]
        if not filtered_cases:
            raise ValueError("未找到任何冒烟 case")
    if not case_id:
        return filtered_cases
    filtered_cases = [case for case in filtered_cases if case.case_id == case_id]
    if not filtered_cases:
        raise ValueError(f"未找到 case: {case_id}")
    return filtered_cases
