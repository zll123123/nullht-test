"""Qase Report 兼容结果输出。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from models.result_model import ApiCallRecord, CaseExecutionResult

QASE_REPORT_DIR_NAME = "qase-report"
QASE_RESULTS_DIR_NAME = "results"
RUN_FILE_NAME = "run.json"
RESULT_FILE_SUFFIX = ".json"
DEFAULT_TIMEZONE = timezone(timedelta(hours=8))
_RUN_STARTED_AT = datetime.now(DEFAULT_TIMEZONE)


def initialize_qase_report(output_dir: Path) -> Path:
    """初始化 Qase Report 输出目录。

    Args:
        output_dir: 主输出目录。

    Returns:
        Path: Qase Report 目录。
    """
    global _RUN_STARTED_AT
    _RUN_STARTED_AT = datetime.now(DEFAULT_TIMEZONE)
    report_dir = output_dir / QASE_REPORT_DIR_NAME
    if report_dir.exists():
        shutil.rmtree(report_dir)
    (report_dir / QASE_RESULTS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    return report_dir


def save_qase_report(output_dir: Path, results: List[CaseExecutionResult]) -> Path:
    """保存 Qase Report 兼容结果。

    Args:
        output_dir: 主输出目录。
        results: 全部 case 结果。

    Returns:
        Path: Qase Report 目录。
    """
    report_dir = output_dir / QASE_REPORT_DIR_NAME
    results_dir = report_dir / QASE_RESULTS_DIR_NAME
    results_dir.mkdir(parents=True, exist_ok=True)
    save_run_metadata(report_dir, results)
    clear_result_files(results_dir)
    for item in results:
        result_file = results_dir / f"{item.case_id}{RESULT_FILE_SUFFIX}"
        result_file.write_text(json.dumps(build_qase_result(item), ensure_ascii=False, indent=2), encoding="utf-8")
    return report_dir


def clear_result_files(results_dir: Path) -> None:
    """清空旧的结果文件。

    Args:
        results_dir: 结果目录。

    Returns:
        None
    """
    for file_path in results_dir.glob(f"*{RESULT_FILE_SUFFIX}"):
        file_path.unlink()


def save_run_metadata(report_dir: Path, results: List[CaseExecutionResult]) -> None:
    """写入运行元数据。

    Args:
        report_dir: 报告目录。
        results: 全部 case 结果。

    Returns:
        None
    """
    run_file = report_dir / RUN_FILE_NAME
    run_file.write_text(json.dumps(build_qase_run(results), ensure_ascii=False, indent=2), encoding="utf-8")


def build_qase_run(results: List[CaseExecutionResult]) -> Dict[str, Any]:
    """构建 run.json 内容。"""
    finished_at = datetime.now(DEFAULT_TIMEZONE)
    return {
        "title": "CSL 完整对话路径测试",
        "environment": "local",
        "execution": {
            "start_time": _RUN_STARTED_AT.isoformat(),
            "end_time": finished_at.isoformat(),
            "duration": calculate_run_duration_ms(results, finished_at),
        },
        "stats": build_run_stats(results),
    }


def calculate_run_duration_ms(results: List[CaseExecutionResult], finished_at: datetime) -> int:
    """计算整轮执行耗时。"""
    duration_from_calls = sum(int(sum(record.elapsed_ms for record in item.api_call_records)) for item in results)
    if duration_from_calls > 0:
        return duration_from_calls
    return int((finished_at - _RUN_STARTED_AT).total_seconds() * 1000)


def build_run_stats(results: List[CaseExecutionResult]) -> Dict[str, int]:
    """构建汇总统计。"""
    stats = {
        "total": len(results),
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "blocked": 0,
        "invalid": 0,
        "muted": 0,
    }
    for item in results:
        status = build_qase_status(item)
        if status == "passed":
            stats["passed"] += 1
        elif status == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1
    return stats


def build_qase_result(case_result: CaseExecutionResult) -> Dict[str, Any]:
    """构建单条测试结果。"""
    duration_ms = calculate_case_duration_ms(case_result.api_call_records)
    end_time = datetime.now(DEFAULT_TIMEZONE)
    start_time = end_time - timedelta(milliseconds=duration_ms)
    return {
        "title": f"{case_result.case_id} {case_result.scenario}",
        "signature": case_result.case_id,
        "testops_ids": None,
        "attachments": [],
        "steps": build_qase_steps(case_result),
        "params": {
            "case_id": case_result.case_id,
            "session_id": case_result.session_id,
            "focus_strategy": case_result.focus_strategy,
        },
        "param_groups": [],
        "relations": {},
        "message": build_qase_message(case_result),
        "fields": build_qase_fields(case_result),
        "execution": {
            "status": build_qase_status(case_result),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration_ms,
            "stacktrace": build_qase_stacktrace(case_result),
            "thread": None,
        },
    }


def calculate_case_duration_ms(records: List[ApiCallRecord]) -> int:
    """计算单条 case 的累计接口耗时。"""
    return int(sum(record.elapsed_ms for record in records))


def build_qase_status(case_result: CaseExecutionResult) -> str:
    """映射 Qase 状态。"""
    if case_result.status == "PENDING_PLAN":
        return "skipped"
    if case_result.error or case_result.result_type == "执行失败":
        return "broken"
    if case_result.validation and case_result.validation.passed:
        return "passed"
    return "failed"


def build_qase_message(case_result: CaseExecutionResult) -> str:
    """构建结果消息。"""
    return case_result.failure_reason or case_result.error or case_result.result_type or case_result.status


def build_qase_stacktrace(case_result: CaseExecutionResult) -> str | None:
    """构建错误栈信息。"""
    if case_result.error:
        return case_result.error
    if case_result.validation and case_result.validation.failed_fields:
        return f"断言失败字段: {', '.join(case_result.validation.failed_fields)}"
    return None


def build_qase_fields(case_result: CaseExecutionResult) -> Dict[str, Any]:
    """构建附加字段。"""
    return {
        "scenario": case_result.scenario,
        "status": case_result.status,
        "result_type": case_result.result_type or None,
        "failure_reason": case_result.failure_reason or None,
        "department": extract_department(case_result),
        "failed_fields": ",".join(case_result.validation.failed_fields) if case_result.validation else None,
    }


def extract_department(case_result: CaseExecutionResult) -> str:
    """提取科室字段。"""
    digest = (case_result.expected.get("visit_plan_digest") or {})
    return str(digest.get("department") or "")


def build_qase_steps(case_result: CaseExecutionResult) -> List[Dict[str, Any]]:
    """构建测试步骤。"""
    steps = [build_dialog_step(item.question, item.answer) for item in case_result.steps]
    if case_result.validation is not None:
        steps.append(build_assertion_step(case_result))
    return steps


def build_dialog_step(question: str, answer: str) -> Dict[str, Any]:
    """构建对话步骤。"""
    return {
        "step_type": "text",
        "data": {
            "action": f"系统提问：{question}\n测试回答：{answer}",
            "expected_result": "接口正常返回下一轮问题或完成标记",
        },
        "execution": {
            "status": "passed",
            "attachments": [],
        },
        "steps": [],
    }


def build_assertion_step(case_result: CaseExecutionResult) -> Dict[str, Any]:
    """构建断言步骤。"""
    passed = bool(case_result.validation and case_result.validation.passed)
    failed_fields = ", ".join(case_result.validation.failed_fields if case_result.validation else [])
    return {
        "step_type": "text",
        "data": {
            "action": "执行拜访计划断言校验",
            "expected_result": "实际结果满足 YAML 中配置的预期断言",
        },
        "execution": {
            "status": "passed" if passed else "failed",
            "attachments": [],
        },
        "steps": [
            {
                "step_type": "text",
                "data": {
                    "action": f"失败字段：{failed_fields or '无'}",
                    "expected_result": "无失败字段",
                },
                "execution": {
                    "status": "passed" if passed else "failed",
                    "attachments": [],
                },
                "steps": [],
            }
        ],
    }
