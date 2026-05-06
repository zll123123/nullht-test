#!/usr/bin/env python3
"""基于现有输出结果重新计算断言。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.runtime_paths import DATA_FILE, OUTPUT_DIR
from services.case_loader import CaseConfig, build_cases
from services.validation_service import build_validation_result, extract_visit_plan
from utils.execution_record_writer import save_markdown_record
from utils.result_writer import RESULT_FILE_NAME


def load_case_index() -> Dict[str, CaseConfig]:
    """加载 case 索引。

    Args:
        None

    Returns:
        Dict[str, CaseConfig]: 按 case_id 索引的 case。
    """
    _, cases = build_cases(DATA_FILE)
    return {case.case_id: case for case in cases}


def rebuild_result(case_index: Dict[str, CaseConfig], result: Dict[str, Any]) -> Dict[str, Any]:
    """重算单条结果的断言信息。

    Args:
        case_index: 用例索引。
        result: 原始结果。

    Returns:
        Dict[str, Any]: 更新后的结果。
    """
    case_id = str(result.get("case_id") or "")
    if result.get("status") in {"EXECUTION_FAILED", "PLAN_ERROR", "PENDING_PLAN"}:
        return result
    case = case_index.get(case_id)
    if case is None:
        return result
    final_data = result.get("final_data") or {}
    detail_data = result.get("detail_data") or {}
    visit_plan = extract_visit_plan(final_data, detail_data)
    focus_decisions = result.get("focus_decisions") or []
    validation = build_validation_result(case, final_data, visit_plan, focus_decisions)
    result["visit_plan"] = visit_plan
    result["validation"] = validation
    if validation.get("passed"):
        result["result_type"] = "通过"
        result["failure_reason"] = ""
    else:
        failed_fields = validation.get("failed_fields") or []
        result["result_type"] = "断言失败"
        result["failure_reason"] = f"断言失败字段: {', '.join(str(field) for field in failed_fields)}"
    return result


def main() -> int:
    """程序入口。

    Args:
        None

    Returns:
        int: 退出码。
    """
    result_file = OUTPUT_DIR / RESULT_FILE_NAME
    data = json.loads(result_file.read_text(encoding="utf-8"))
    case_index = load_case_index()
    results: List[Dict[str, Any]] = [rebuild_result(case_index, item) for item in data.get("results") or []]
    result_file.write_text(json.dumps({"summary": data.get("summary"), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    from utils.execution_record_writer import build_summary

    result_file.write_text(
        json.dumps({"summary": build_summary(results), "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_markdown_record(OUTPUT_DIR, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
