"""在执行产物完成后运行本地拜访计划审核。"""

from __future__ import annotations

from pathlib import Path
from typing import List

from config.app_config import AppConfig
from models.result_model import CaseExecutionResult, PlanReviewRecord
from reporters.plan_review_reporter import save_plan_review_results
from services.plan_review_service import review_visit_plan_by_llm


def run_local_plan_reviews(
    config: AppConfig,
    results: List[CaseExecutionResult],
    output_file: Path,
) -> List[PlanReviewRecord]:
    """在所有对话和拜访计划产物完成后执行审核。

    Args:
        config: 运行配置。
        results: 已完成执行结果。
        output_file: 本地审核结果文件路径。

    Returns:
        List[PlanReviewRecord]: 本地审核记录。
    """
    records: List[PlanReviewRecord] = []
    for case_result in results:
        review = review_visit_plan_by_llm(
            config=config,
            case_id=case_result.case_id,
            scenario=case_result.scenario,
            expected=case_result.expected,
            focus_strategy=case_result.focus_strategy,
            session_id=case_result.session_id,
            steps=case_result.steps,
            visit_plan=case_result.visit_plan,
        )
        records.append(
            PlanReviewRecord(
                case_id=case_result.case_id,
                scenario=case_result.scenario,
                session_id=case_result.session_id,
                review=review,
            )
        )
    save_plan_review_results(output_file, records)
    return records
