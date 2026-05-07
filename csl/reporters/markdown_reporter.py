"""Markdown 执行记录输出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from models.result_model import CaseExecutionResult, ExecutionSummary

MARKDOWN_RECORD_FILE = "csl_full_path_execution_record.md"


def format_json_block(value: Any) -> str:
    """格式化 JSON 代码块。"""
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def build_summary(results: List[CaseExecutionResult]) -> ExecutionSummary:
    """构建汇总结果。"""
    summary = ExecutionSummary(total=len(results))
    for item in results:
        if item.status == "PENDING_PLAN":
            summary.pending += 1
        elif item.error:
            summary.errors += 1
        elif item.validation and item.validation.passed:
            summary.passed += 1
        else:
            summary.failed += 1
    return summary


def build_failed_case_summary_lines(results: List[CaseExecutionResult]) -> List[str]:
    """构建失败汇总。"""
    failed_cases = [item for item in results if item.result_type != "通过" and not (item.validation and item.validation.passed)]
    lines = [f"未通过 case 数：{len(failed_cases)}"]
    for item in failed_cases:
        failed_fields = ", ".join(item.validation.failed_fields if item.validation else [])
        lines.append(
            f"- {item.case_id} | {item.result_type or item.status} | "
            f"失败字段：{failed_fields or '-'} | 原因：{item.failure_reason or item.error or '-'}"
        )
    return lines


def build_case_record_lines(case_result: CaseExecutionResult) -> List[str]:
    """构建单个 case 的 Markdown 记录。"""
    lines = [
        f"## {case_result.case_id} {case_result.scenario}",
        f"- 状态：{case_result.status}",
        f"- session_id：{case_result.session_id or '-'}",
        f"- 关注点策略：{case_result.focus_strategy or '-'}",
    ]
    for step in case_result.steps or []:
        lines.append(f"- 系统提问：{step.question or ''}")
        lines.append(f"- 测试回答：{step.answer or ''}")
    if case_result.focus_decisions:
        lines.extend(["- 关注点执行结果：", format_json_block([item.to_dict() for item in case_result.focus_decisions])])
    if case_result.visit_plan:
        lines.extend(["- 最终拜访计划：", format_json_block(case_result.visit_plan or {})])
    if case_result.validation:
        lines.extend(["- 断言结果：", format_json_block(case_result.validation.to_dict())])
    return lines


def save_markdown_record(output_dir: Path, results: List[CaseExecutionResult]) -> Path:
    """保存 Markdown 执行记录。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / MARKDOWN_RECORD_FILE
    summary = build_summary(results)
    lines = [
        "# CSL 完整对话路径执行记录",
        "",
        f"- 总数：{summary.total}",
        f"- 通过：{summary.passed}",
        f"- 失败：{summary.failed}",
        f"- 异常：{summary.errors}",
        f"- 待完成：{summary.pending}",
        "",
        "## 失败汇总",
        *build_failed_case_summary_lines(results),
        "",
        "## 执行明细",
    ]
    for item in results:
        lines.extend(["", *build_case_record_lines(item)])
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_file
