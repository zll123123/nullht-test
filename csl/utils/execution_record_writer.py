"""执行记录导出工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


MARKDOWN_RECORD_FILE = "csl_full_path_execution_record.md"


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, int]:
    """构建执行结果汇总信息。

    Args:
        results: 全部 case 执行结果。

    Returns:
        Dict[str, int]: 通过、失败、异常与总数统计。
    """
    passed = 0
    failed = 0
    errors = 0
    pending = 0
    for item in results:
        if item.get("error"):
            errors += 1
        elif item.get("status") == "PENDING_PLAN":
            pending += 1
        elif (item.get("validation") or {}).get("passed"):
            passed += 1
        else:
            failed += 1
    return {"passed": passed, "failed": failed, "errors": errors, "pending": pending, "total": len(results)}


def format_json_block(data: Any) -> str:
    """格式化 JSON Markdown 代码块。

    Args:
        data: 需要格式化的对象。

    Returns:
        str: Markdown 代码块文本。
    """
    return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"


def build_step_lines(steps: List[Dict[str, Any]]) -> List[str]:
    """构建单个 case 的问答步骤记录。

    Args:
        steps: 对话步骤列表。

    Returns:
        List[str]: Markdown 行列表。
    """
    lines: List[str] = []
    for index, step in enumerate(steps, start=1):
        lines.append(f"### Step {index}")
        lines.append(f"- 系统提问：{step.get('question', '')}")
        lines.append(f"- 测试回答：{step.get('answer', '')}")
        lines.append("- 系统响应：")
        lines.append(format_json_block(step.get("response") or {}))
    return lines


def build_validation_lines(validation: Dict[str, Any]) -> List[str]:
    """构建断言结果的展示内容。

    Args:
        validation: 断言结果字典。

    Returns:
        List[str]: Markdown 行列表。
    """
    lines = [
        f"- 断言是否通过：{validation.get('passed')}",
        f"- 断言通过数：{validation.get('passed_checks')}/{validation.get('total_checks')}",
    ]
    failed_fields = validation.get("failed_fields") or []
    lines.append(f"- 失败字段：{', '.join(str(field) for field in failed_fields) if failed_fields else '无'}")
    lines.append("- 断言明细：")
    lines.append(format_json_block(validation.get("checks") or []))
    return lines


def build_case_record_lines(case_result: Dict[str, Any]) -> List[str]:
    """构建单个 case 的完整执行记录。

    Args:
        case_result: 单个 case 执行结果。

    Returns:
        List[str]: Markdown 行列表。
    """
    lines = [
        f"## {case_result.get('case_id', '')}",
        f"- 场景：{case_result.get('scenario', '')}",
        f"- 状态：{case_result.get('status', 'UNKNOWN')}",
    ]
    if case_result.get("error"):
        lines.append(f"- 执行异常：{case_result.get('error')}")
        return lines
    lines.extend(
        [
            f"- Session ID：{case_result.get('session_id', '')}",
            f"- 关注点策略：{case_result.get('focus_strategy', '') or '默认'}",
            "- 关注点执行记录：",
            format_json_block(case_result.get("focus_decisions") or []),
            "### 对话过程",
        ]
    )
    lines.extend(build_step_lines(case_result.get("steps") or []))
    lines.extend(
        [
            "### 最终拜访计划",
            format_json_block(case_result.get("visit_plan") or {}),
            "### 详情接口返回",
            format_json_block(case_result.get("detail_data") or {}),
            "### 断言结果",
        ]
    )
    lines.extend(build_validation_lines(case_result.get("validation") or {}))
    return lines


def save_markdown_record(output_dir: Path, results: List[Dict[str, Any]]) -> Path:
    """保存 Markdown 执行记录。

    Args:
        output_dir: 输出目录。
        results: 全部 case 执行结果。

    Returns:
        Path: Markdown 文件路径。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(results)
    lines = [
        "# CSL 执行记录",
        "",
        "## 汇总",
        f"- 总数：{summary['total']}",
        f"- 通过：{summary['passed']}",
        f"- 失败：{summary['failed']}",
        f"- 异常：{summary['errors']}",
        f"- 待补全：{summary['pending']}",
        "",
    ]
    for case_result in results:
        lines.extend(build_case_record_lines(case_result))
        lines.append("")
    output_file = output_dir / MARKDOWN_RECORD_FILE
    output_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_file
