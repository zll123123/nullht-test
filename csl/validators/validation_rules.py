"""拜访计划断言规则。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config.constants import FOCUS_BRANCH_F1, FOCUS_BRANCH_F3, MATCH_CONTAINS, MATCH_LIST_EXACT
from models.case_model import CaseConfig, FocusDecision
from validators.assertion_builder import build_check, build_non_empty_check
from validators.assertion_models import ValidationCheck
from validators.field_extractors import (
    get_comm_literature_summaries,
    get_comm_literature_titles,
    get_focus_contents,
    get_focus_literature_summaries,
    get_focus_literature_titles,
    get_focus_titles,
    get_recommended_materials,
    get_transitional_info,
)


def has_expected_focus_content(case: CaseConfig) -> bool:
    """判断是否存在可校验的原始关注点信息。"""
    expected = case.expected
    return bool(str(expected.get("focus_title") or "").strip() or str(expected.get("focus_content") or "").strip())


def get_effective_focus_branch(case: CaseConfig, focus_decisions: List[FocusDecision]) -> str:
    """获取本轮实际命中的关注点分支。"""
    if not has_expected_focus_content(case):
        return ""
    if focus_decisions:
        return focus_decisions[-1].actual_branch
    if case.focus_strategy is None:
        return ""
    return case.focus_strategy.branch


def build_focus_validation_checks(
    case: CaseConfig,
    focus_branch: str,
    focus_decisions: List[FocusDecision],
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
) -> List[Optional[ValidationCheck]]:
    """构建关注点相关断言。"""
    del focus_decisions
    expected = case.expected
    actual_title = get_focus_titles(final_data, visit_plan)
    actual_content = get_focus_contents(final_data, visit_plan)
    if not has_expected_focus_content(case):
        return [
            build_non_empty_check("focus_title.non_empty", actual_title),
            build_non_empty_check("focus_content.non_empty", actual_content),
        ]
    if focus_branch in {FOCUS_BRANCH_F1, FOCUS_BRANCH_F3, ""}:
        return [
            build_check("focus_title", expected.get("focus_title"), actual_title, MATCH_CONTAINS),
            build_check("focus_content", expected.get("focus_content"), actual_content, MATCH_CONTAINS),
            build_check("focus_literature_titles", expected.get("focus_literature_titles"), get_focus_literature_titles(visit_plan), MATCH_LIST_EXACT),
            build_check("focus_literature_summaries", expected.get("focus_literature_summaries"), get_focus_literature_summaries(visit_plan), MATCH_CONTAINS),
        ]
    return [
        build_non_empty_check("focus_title.non_empty", actual_title),
        build_non_empty_check("focus_content.non_empty", actual_content),
    ]


def build_validation_checks(
    case: CaseConfig,
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
    focus_decisions: List[FocusDecision],
) -> List[ValidationCheck]:
    """构建完整断言列表。"""
    expected = case.expected
    digest = ((visit_plan.get("visit_plan_digest") or {}).get("doctorInfo") or {})
    focus_branch = get_effective_focus_branch(case, focus_decisions)
    candidates: List[Optional[ValidationCheck]] = [
        build_check("doctor_type", expected.get("doctor_type"), digest.get("type")),
        build_check("doctor_grade", expected.get("doctor_grade"), digest.get("grade")),
        build_check("trans_info", expected.get("trans_info"), get_transitional_info(visit_plan)),
        build_check("support_info", expected.get("support_info"), (visit_plan.get("comm_suggest") or {}).get("support_info"), MATCH_CONTAINS),
        build_check("comm_literature_titles", expected.get("comm_literature_titles"), get_comm_literature_titles(visit_plan), MATCH_LIST_EXACT),
        build_check("comm_literature_summaries", expected.get("comm_literature_summaries"), get_comm_literature_summaries(visit_plan), MATCH_CONTAINS),
        build_check("recommended_materials", expected.get("recommended_materials"), get_recommended_materials(visit_plan), MATCH_CONTAINS),
        build_check("digest.department", (expected.get("visit_plan_digest") or {}).get("department"), digest.get("department")),
        build_check("digest.rank", (expected.get("visit_plan_digest") or {}).get("rank"), digest.get("rank")),
        build_check("digest.level", (expected.get("visit_plan_digest") or {}).get("level"), digest.get("level")),
        build_check("digest.type", (expected.get("visit_plan_digest") or {}).get("type"), digest.get("type")),
        build_check("digest.grade", (expected.get("visit_plan_digest") or {}).get("grade"), digest.get("grade")),
    ]
    if case.focus_strategy is not None and has_expected_focus_content(case):
        candidates.append(build_check("focus_branch", case.focus_strategy.branch, focus_branch))
    candidates.extend(build_focus_validation_checks(case, focus_branch, focus_decisions, final_data, visit_plan))
    return [check for check in candidates if check is not None]
