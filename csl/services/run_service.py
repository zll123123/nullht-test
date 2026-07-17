"""通用运行编排服务。"""

from __future__ import annotations

import random
import subprocess
import time
from pathlib import Path
from typing import Dict, List

from clients.chat_client import create_session
from config.app_config import AppConfig
from config.settings import OUTPUT_DIR, PLAN_REVIEW_FILE
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
from services.plan_review_runner import run_local_plan_reviews

QASE_REPORT_HTML_FILE = "report.html"


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
        stop_error="",
        first_can_stop_step_index=0,
        stop_called_step_index=0,
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


def is_success_result(case_result: CaseExecutionResult) -> bool:
    """判断 case 是否成功。

    Args:
        case_result: 当前结果。

    Returns:
        bool: 是否成功。
    """
    return bool(case_result.status == "DONE" and case_result.validation and case_result.validation.passed)


def build_retryable_result(case: CaseConfig, previous_result: CaseExecutionResult | None, error_message: str) -> CaseExecutionResult:
    """构建可重试失败结果。

    Args:
        case: 当前用例。
        previous_result: 上一次结果。
        error_message: 错误信息。

    Returns:
        CaseExecutionResult: 失败结果。
    """
    if previous_result is None:
        return build_execution_error_result(case, error_message)
    if previous_result.validation is not None and not previous_result.validation.passed:
        previous_result.error = ""
        previous_result.result_type = "断言失败"
        previous_result.failure_reason = error_message
        previous_result.status = "DONE"
        return previous_result
    previous_result.error = error_message
    previous_result.failure_reason = error_message
    previous_result.result_type = "执行失败"
    previous_result.status = "EXECUTION_FAILED"
    return previous_result


def is_retryable_result(case_result: CaseExecutionResult) -> bool:
    """判断结果是否需要重试。

    Args:
        case_result: 当前结果。

    Returns:
        bool: 是否需要重试。
    """
    return not is_success_result(case_result)


def resolve_case_once(
    session: object,
    config: AppConfig,
    doctor_rank: str,
    case: CaseConfig,
    rng: random.Random,
    existing_results: List[CaseExecutionResult],
    case_index: Dict[str, CaseConfig],
) -> CaseExecutionResult:
    """执行单个 case 的一次尝试并完成轮询补全。

    Args:
        session: 请求会话。
        config: 运行配置。
        doctor_rank: 医生职称回答。
        case: 当前用例。
        rng: 随机种子。
        existing_results: 已完成结果列表。
        case_index: 用例索引。

    Returns:
        CaseExecutionResult: 本次尝试的最终结果。
    """
    candidate_result = build_pending_case_result(session, config, doctor_rank, case, rng)
    mark_pending_metadata(candidate_result, config)
    temp_results = [*existing_results, candidate_result]
    while candidate_result.status == "PENDING_PLAN":
        poll_pending_results(session, config, temp_results, case_index, wait_for_next_window=False)
    return candidate_result


def generate_qase_html_report(qase_report_dir: Path) -> Path | None:
    """生成 Qase 静态 HTML 报告。

    Args:
        qase_report_dir: Qase Report 结果目录。

    Returns:
        Path | None: 生成成功时返回 HTML 路径，否则返回 None。
    """
    report_html_path = qase_report_dir / QASE_REPORT_HTML_FILE
    command = [
        "qase-report",
        "generate",
        str(qase_report_dir),
        "-o",
        str(report_html_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        logger.warning("未找到 qase-report 命令，跳过 HTML 报告生成。")
        return None
    except subprocess.CalledProcessError as exc:
        error_message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        logger.exception("Qase HTML 报告生成失败: {}", error_message)
        return None
    return report_html_path


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
        retry_total = max(int(config.case_retry_times), 0)
        final_result: CaseExecutionResult | None = None
        last_error = ""
        for attempt in range(retry_total + 1):
            logger.info("开始执行 {} | {} | 第 {} 次尝试", case.case_id, case.scenario, attempt + 1)
            try:
                candidate_result = resolve_case_once(
                    session=session,
                    config=config,
                    doctor_rank=doctor_rank,
                    case=case,
                    rng=rng,
                    existing_results=results,
                    case_index=case_index,
                )
                logger.info("对话完成 {} | session_id={}", case.case_id, candidate_result.session_id)
                final_result = candidate_result
                if not is_retryable_result(candidate_result):
                    break
                last_error = candidate_result.failure_reason or candidate_result.error or "非成功状态"
                logger.warning("{} 第 {} 次尝试未成功: {}", case.case_id, attempt + 1, last_error)
            except Exception as exc:
                last_error = str(exc)
                logger.exception("{} 第 {} 次尝试失败: {}", case.case_id, attempt + 1, exc)
                final_result = build_execution_error_result(case, last_error)
            if attempt < retry_total and is_retryable_result(final_result):
                continue
            break
        if final_result is None:
            final_result = build_execution_error_result(case, last_error or f"{case.case_id} 执行失败")
        elif is_retryable_result(final_result):
            final_result = build_retryable_result(case, final_result, last_error or final_result.failure_reason or final_result.error or "执行失败")
        results.append(final_result)
        flush_outputs(results)
    drain_pending_results(session, config, results, case_index)
    flush_outputs(results)
    if config.llm_plan_review_enabled:
        try:
            review_file = run_local_plan_reviews(config, results, PLAN_REVIEW_FILE)
            logger.info("本地拜访计划审核结果已保存: {}", review_file)
        except Exception as exc:
            logger.exception("本地拜访计划审核失败，不影响接口测试结果: {}", exc)
    report_html_path = generate_qase_html_report(OUTPUT_DIR / "qase-report")
    if report_html_path is not None:
        logger.info("Qase HTML 报告已生成: {}", report_html_path)
    return results
