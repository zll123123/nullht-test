"""通用运行编排服务。"""

from __future__ import annotations

import random
import time
from typing import Dict, List

from clients.chat_client import create_session
from config.app_config import AppConfig
from config.settings import OUTPUT_DIR
from loguru import logger
from models.case_model import CaseConfig
from models.result_model import CaseExecutionResult
from reporters.markdown_reporter import save_markdown_record
from reporters.json_reporter import save_results
from reporters.qase_reporter import save_qase_report
from services.conversation_service import build_pending_case_result
from services.plan_polling_service import (
    build_case_index,
    has_pending_results,
    mark_pending_metadata,
    poll_pending_case,
)


def build_execution_error_result(case: CaseConfig, error_message: str) -> CaseExecutionResult:
    """构建执行失败结果。

    Args:
        case: 当前用例。
        error_message: 失败原因。

    Returns:
        CaseExecutionResult: 执行失败结果。
    """
    return CaseExecutionResult(
        case_id=case.case_id,
        scenario=case.scenario,
        expected=case.expected,
        focus_strategy=case.focus_strategy.branch if case.focus_strategy else "",
        focus_decisions=[],
        session_id="",
        steps=[],
        final_data={},
        visit_plan={},
        stop_data={},
        detail_data={},
        validation=None,
        status="EXECUTION_FAILED",
        result_type="执行失败",
        error=error_message,
        failure_reason=error_message,
    )


def flush_outputs(results: List[CaseExecutionResult]) -> None:
    """刷新统一输出文件。

    Args:
        results: 全部结果。

    Returns:
        None
    """
    output_file = save_results(results)
    markdown_file = save_markdown_record(OUTPUT_DIR, results)
    qase_report_dir = save_qase_report(OUTPUT_DIR, results)
    logger.info("结果已保存: {}", output_file)
    logger.info("执行记录已保存: {}", markdown_file)
    logger.info("Qase Report 已保存: {}", qase_report_dir)


def poll_pending_results(
    session: object,
    config: AppConfig,
    results: List[CaseExecutionResult],
    case_index: Dict[str, CaseConfig],
    wait_for_next_window: bool,
) -> None:
    """按当前时机轮询待补全结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        results: 全部结果。
        case_index: 用例索引。
        wait_for_next_window: 是否等待到下一次轮询窗口。

    Returns:
        None
    """
    if not has_pending_results(results):
        return
    now_ts = time.time()
    if wait_for_next_window:
        next_poll_at = min(float(item.next_poll_at or now_ts) for item in results if item.status == "PENDING_PLAN")
        sleep_seconds = max(next_poll_at - now_ts, 0)
        if sleep_seconds > 0:
            logger.info("等待 {:.0f} 秒后轮询待生成的拜访计划。", sleep_seconds)
            time.sleep(sleep_seconds)
        now_ts = time.time()
    updated = False
    for item in results:
        if item.status != "PENDING_PLAN":
            continue
        if not wait_for_next_window and now_ts < float(item.next_poll_at or 0):
            continue
        case = case_index[item.case_id]
        poll_pending_case(session, config, case, item, now_ts)
        updated = True
    if updated:
        flush_outputs(results)


def drain_pending_results(
    session: object,
    config: AppConfig,
    results: List[CaseExecutionResult],
    case_index: Dict[str, CaseConfig],
) -> None:
    """补全全部待获取的拜访计划结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        results: 全部结果。
        case_index: 用例索引。

    Returns:
        None
    """
    while has_pending_results(results):
        poll_pending_results(session, config, results, case_index, wait_for_next_window=True)


def run_cases(
    selected_cases: List[CaseConfig],
    doctor_rank: str,
    config: AppConfig,
    seed: int,
) -> List[CaseExecutionResult]:
    """执行选中的 case 并输出结果。

    Args:
        selected_cases: 待执行用例。
        doctor_rank: 医生职称回答。
        config: 运行配置。
        seed: 随机种子。

    Returns:
        List[CaseExecutionResult]: 全部执行结果。
    """
    results: List[CaseExecutionResult] = []
    case_index = build_case_index(selected_cases)
    rng = random.Random(seed)
    session = create_session()
    for case in selected_cases:
        poll_pending_results(session, config, results, case_index, wait_for_next_window=False)
        logger.info("开始执行 {} | {}", case.case_id, case.scenario)
        try:
            case_result = build_pending_case_result(session, config, doctor_rank, case, rng)
            mark_pending_metadata(case_result, config)
            logger.info("对话完成 {} | session_id={}", case.case_id, case_result.session_id)
            results.append(case_result)
            flush_outputs(results)
        except Exception as exc:
            logger.exception("{} 执行失败: {}", case.case_id, exc)
            results.append(build_execution_error_result(case, str(exc)))
            flush_outputs(results)
    drain_pending_results(session, config, results, case_index)
    return results
