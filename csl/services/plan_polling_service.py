"""拜访计划异步补全服务。"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from clients.chat_client import fetch_visit_plan_detail_once
from config.app_config import AppConfig
from models.case_model import CaseConfig
from models.result_model import CaseExecutionResult
from utils.api_timing import ApiCallCollector
from validators.field_extractors import extract_visit_plan
from validators.validation_service import build_validation_result

PENDING_STATUS = "PENDING_PLAN"
DONE_STATUS = "DONE"
ERROR_STATUS = "PLAN_ERROR"


def build_case_index(cases: List[CaseConfig]) -> Dict[str, CaseConfig]:
    """构建用例索引。

    Args:
        cases: 用例列表。

    Returns:
        Dict[str, CaseConfig]: 按 case_id 索引的字典。
    """
    return {case.case_id: case for case in cases}


def mark_pending_metadata(case_result: CaseExecutionResult, config: AppConfig) -> None:
    """写入待轮询元数据。

    Args:
        case_result: 当前用例结果。
        config: 运行配置。

    Returns:
        None
    """
    case_result.status = PENDING_STATUS
    case_result.poll_attempts = 0
    case_result.next_poll_at = time.time() + max(config.detail_poll_interval_seconds, 1)
    case_result.poll_deadline_at = time.time() + max(config.detail_poll_wait_seconds, 0)


def should_poll(case_result: CaseExecutionResult, now_ts: float) -> bool:
    """判断当前用例是否到了轮询时间。

    Args:
        case_result: 用例结果。
        now_ts: 当前时间戳。

    Returns:
        bool: 是否应执行轮询。
    """
    return case_result.status == PENDING_STATUS and now_ts >= float(case_result.next_poll_at or 0)


def finalize_case_result(case: CaseConfig, case_result: CaseExecutionResult, detail_data: Dict[str, Any]) -> None:
    """用详情数据补全结果并执行断言。

    Args:
        case: 当前用例。
        case_result: 待补全结果。
        detail_data: 详情接口返回。

    Returns:
        None
    """
    final_data = case_result.final_data or {}
    focus_decisions = case_result.focus_decisions or []
    visit_plan = extract_visit_plan(final_data, detail_data)
    case_result.detail_data = detail_data
    case_result.visit_plan = visit_plan
    case_result.validation = build_validation_result(case, final_data, visit_plan, focus_decisions)
    case_result.status = DONE_STATUS
    if case_result.validation.passed:
        case_result.result_type = "通过"
        case_result.failure_reason = ""
    else:
        failed_fields = case_result.validation.failed_fields or []
        case_result.result_type = "断言失败"
        case_result.failure_reason = f"断言失败字段: {', '.join(str(field) for field in failed_fields)}"
    case_result.next_poll_at = 0.0
    case_result.poll_deadline_at = 0.0


def mark_plan_error(case_result: CaseExecutionResult, message: str) -> None:
    """标记拜访计划补全失败。

    Args:
        case_result: 当前用例结果。
        message: 错误信息。

    Returns:
        None
    """
    case_result.status = ERROR_STATUS
    case_result.result_type = "执行失败"
    case_result.error = message
    case_result.failure_reason = message
    case_result.next_poll_at = 0.0
    case_result.poll_deadline_at = 0.0


def poll_pending_case(
    session: Any,
    config: AppConfig,
    case: CaseConfig,
    case_result: CaseExecutionResult,
    now_ts: float,
) -> None:
    """轮询单个待补全用例。

    Args:
        session: 请求会话。
        config: 运行配置。
        case: 当前用例。
        case_result: 当前结果。
        now_ts: 当前时间戳。

    Returns:
        None
    """
    case_result.poll_attempts = int(case_result.poll_attempts or 0) + 1
    api_collector = ApiCallCollector(
        case_id=case.case_id,
        session_id=str(case_result.session_id),
        records=case_result.api_call_records,
    )
    detail_data = fetch_visit_plan_detail_once(
        session,
        config,
        str(case_result.session_id),
        api_collector=api_collector,
    )
    if detail_data:
        finalize_case_result(case, case_result, detail_data)
        return
    if now_ts >= float(case_result.poll_deadline_at or 0):
        mark_plan_error(case_result, f"{case.case_id} 在等待拜访计划详情时超时")
        return
    case_result.next_poll_at = now_ts + max(config.detail_poll_interval_seconds, 1)


def has_pending_results(results: List[CaseExecutionResult]) -> bool:
    """判断是否仍有待补全结果。

    Args:
        results: 全部结果。

    Returns:
        bool: 是否仍存在待补全结果。
    """
    return any(item.status == PENDING_STATUS for item in results)
