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
    case_ids: Optional[List[str]],
    smoke_case_ids: Optional[List[str]] = None,
    department: Optional[str] = None,
    scenario_keyword: Optional[str] = None,
) -> List[Any]:
    """按编号、冒烟集、科室和场景关键字过滤用例。"""
    filtered_cases = list(cases)
    if department:
        target_department = normalize_department(department)
        filtered_cases = [case for case in filtered_cases if normalize_department(str(case.department)) == target_department]
        if not filtered_cases:
            raise ValueError(f"未找到科室为 {department} 的 case")
    if scenario_keyword:
        filtered_cases = [case for case in filtered_cases if scenario_keyword in str(case.scenario)]
        if not filtered_cases:
            raise ValueError(f"未找到场景包含 {scenario_keyword} 的 case")
    if smoke_case_ids:
        smoke_case_id_set = set(smoke_case_ids)
        filtered_cases = [case for case in filtered_cases if case.case_id in smoke_case_id_set]
        if not filtered_cases:
            raise ValueError("未找到任何冒烟 case")
    if not case_ids:
        return filtered_cases
    normalized_case_ids = _normalize_case_ids(case_ids)
    available_case_ids = {case.case_id for case in filtered_cases}
    missing_case_ids = [case_id for case_id in normalized_case_ids if case_id not in available_case_ids]
    if missing_case_ids:
        raise ValueError(f"未找到 case: {', '.join(missing_case_ids)}")
    case_id_order = {case_id: index for index, case_id in enumerate(normalized_case_ids)}
    filtered_cases = [case for case in filtered_cases if case.case_id in case_id_order]
    filtered_cases.sort(key=lambda case: case_id_order[case.case_id])
    return filtered_cases


def _normalize_case_ids(case_ids: List[str]) -> List[str]:
    """拆分、清理并去重 case 编号。"""
    normalized_case_ids: List[str] = []
    for item in case_ids:
        for case_id in item.split(","):
            case_id = case_id.strip()
            if case_id and case_id not in normalized_case_ids:
                normalized_case_ids.append(case_id)
    if not normalized_case_ids:
        raise ValueError("--case-id 至少需要传入一个有效 case 编号")
    return normalized_case_ids
