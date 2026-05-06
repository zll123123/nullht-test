"""拜访计划断言服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config.constants import MATCH_CONTAINS, MATCH_EXACT, MATCH_LIST_EXACT, MATCH_NOT_CONTAINS, MATCH_NOT_EMPTY, FOCUS_BRANCH_F1, FOCUS_BRANCH_F3
from services.case_loader import CaseConfig
from utils.common_assertions import CommonAssertion


@dataclass
class ValidationCheck:
    """单个断言结果。"""

    field_name: str
    expected: str
    actual: str
    passed: bool
    match_mode: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。

        Args:
            self: 当前实例。

        Returns:
            Dict[str, Any]: 字典结果。
        """
        return {
            "field_name": self.field_name,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "match_mode": self.match_mode,
        }


def collapse_text(value: Any) -> str:
    """规整文本。

    Args:
        value: 原始值。

    Returns:
        str: 归一化结果。
    """
    return CommonAssertion.normalize_text(value)


def build_non_empty_check(field_name: str, actual: Any) -> ValidationCheck:
    """构建非空断言。"""
    return ValidationCheck(
        field_name=field_name,
        expected="非空",
        actual=str(actual or ""),
        passed=bool(collapse_text(actual)),
        match_mode=MATCH_NOT_EMPTY,
    )


def build_not_contains_check(field_name: str, unexpected: Any, actual: Any) -> Optional[ValidationCheck]:
    """构建不包含断言。"""
    if not collapse_text(unexpected):
        return None
    return ValidationCheck(
        field_name=field_name,
        expected=f"不包含:{unexpected}",
        actual=str(actual or ""),
        passed=collapse_text(unexpected) not in collapse_text(actual),
        match_mode=MATCH_NOT_CONTAINS,
    )


def build_check(field_name: str, expected: Any, actual: Any, match_mode: str = MATCH_EXACT) -> Optional[ValidationCheck]:
    """构建单字段断言。"""
    if not collapse_text(expected):
        return None
    if match_mode == MATCH_CONTAINS:
        passed = CommonAssertion.assert_text_contains(expected, actual).passed
    elif match_mode == MATCH_LIST_EXACT:
        passed = CommonAssertion.assert_text_list_exact(expected, actual).passed
    else:
        passed = CommonAssertion.assert_text_equal(expected, actual).passed
    return ValidationCheck(field_name, str(expected), str(actual or ""), passed, match_mode)


def extract_visit_plan(final_data: Dict[str, Any], detail_data: Dict[str, Any]) -> Dict[str, Any]:
    """提取拜访计划。"""
    if isinstance(detail_data.get("visit_plan"), dict):
        return detail_data["visit_plan"]
    if isinstance(final_data.get("visit_plan"), dict):
        return final_data["visit_plan"]
    return {}


def join_literature_field(literatures: List[Dict[str, Any]], field_name: str) -> str:
    """拼接文献字段。"""
    return "\n".join(str(item.get(field_name) or "").strip() for item in literatures if item.get(field_name))


def get_transitional_info(visit_plan: Dict[str, Any]) -> str:
    """提取第一条传递信息。"""
    transitional_info = ((visit_plan.get("comm_suggest") or {}).get("transitional_info") or [])
    return str(transitional_info[0]) if transitional_info else ""


def get_focus_titles(final_data: Dict[str, Any], visit_plan: Dict[str, Any]) -> str:
    """提取关注点标题。"""
    items = ((visit_plan.get("focus_point") or {}).get("items") or [])
    titles = [str(item.get("title") or "").strip() for item in items if item.get("title")]
    if titles:
        return "\n".join(titles)
    phase3_focus_point = ((final_data.get("phase3_data") or {}).get("focus_point") or {})
    return str(phase3_focus_point.get("title") or "")


def get_focus_contents(final_data: Dict[str, Any], visit_plan: Dict[str, Any]) -> str:
    """提取关注点内容。"""
    items = ((visit_plan.get("focus_point") or {}).get("items") or [])
    contents = [str(item.get("content") or "").strip() for item in items if item.get("content")]
    if contents:
        return "\n".join(contents)
    phase3_focus_point = ((final_data.get("phase3_data") or {}).get("focus_point") or {})
    return str(phase3_focus_point.get("content") or "")


def get_focus_literature_titles(visit_plan: Dict[str, Any]) -> str:
    """提取关注点文献标题。"""
    return join_literature_field(((visit_plan.get("focus_point") or {}).get("literatures") or []), "title")


def get_focus_literature_summaries(visit_plan: Dict[str, Any]) -> str:
    """提取关注点文献摘要。"""
    return join_literature_field(((visit_plan.get("focus_point") or {}).get("literatures") or []), "research_summary")


def get_comm_literature_titles(visit_plan: Dict[str, Any]) -> str:
    """提取沟通文献标题。"""
    return join_literature_field(((visit_plan.get("comm_suggest") or {}).get("literatures") or []), "title")


def get_comm_literature_summaries(visit_plan: Dict[str, Any]) -> str:
    """提取沟通文献摘要。"""
    return join_literature_field(((visit_plan.get("comm_suggest") or {}).get("literatures") or []), "research_summary")


def get_recommended_materials(visit_plan: Dict[str, Any]) -> str:
    """提取推荐材料。"""
    return join_literature_field(visit_plan.get("literatures") or [], "title")


def get_effective_focus_branch(case: CaseConfig, focus_decisions: List[Dict[str, Any]]) -> str:
    """获取本轮实际命中的关注点分支。"""
    if focus_decisions:
        return str(focus_decisions[-1].get("actual_branch") or "")
    if case.focus_strategy is None:
        return ""
    return case.focus_strategy.branch


def build_focus_validation_checks(
    case: CaseConfig,
    focus_branch: str,
    focus_decisions: List[Dict[str, Any]],
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
) -> List[Optional[ValidationCheck]]:
    """构建关注点相关断言。"""
    expected = case.expected
    actual_title = get_focus_titles(final_data, visit_plan)
    actual_content = get_focus_contents(final_data, visit_plan)
    if focus_branch in {FOCUS_BRANCH_F1, FOCUS_BRANCH_F3, ""}:
        return [
            build_check("focus_title", expected.get("focus_title"), actual_title, MATCH_CONTAINS),
            build_check("focus_content", expected.get("focus_content"), actual_content, MATCH_CONTAINS),
            build_check("focus_literature_titles", expected.get("focus_literature_titles"), get_focus_literature_titles(visit_plan), MATCH_LIST_EXACT),
            build_check("focus_literature_summaries", expected.get("focus_literature_summaries"), get_focus_literature_summaries(visit_plan), MATCH_CONTAINS),
        ]
    checks: List[Optional[ValidationCheck]] = [
        build_non_empty_check("focus_title.non_empty", actual_title),
        build_non_empty_check("focus_content.non_empty", actual_content),
    ]
    return checks


def build_validation_checks(
    case: CaseConfig,
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
    focus_decisions: List[Dict[str, Any]],
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
        build_check("digest.type", (expected.get("visit_plan_digest") or {}).get("type"), digest.get("type")),
        build_check("digest.grade", (expected.get("visit_plan_digest") or {}).get("grade"), digest.get("grade")),
    ]
    if case.focus_strategy is not None:
        candidates.append(build_check("focus_branch", case.focus_strategy.branch, focus_branch))
    candidates.extend(build_focus_validation_checks(case, focus_branch, focus_decisions, final_data, visit_plan))
    return [check for check in candidates if check is not None]


def build_validation_result(
    case: CaseConfig,
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
    focus_decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """构建断言结果。"""
    checks = build_validation_checks(case, final_data, visit_plan, focus_decisions)
    passed_checks = sum(1 for check in checks if check.passed)
    return {
        "passed": passed_checks == len(checks),
        "total_checks": len(checks),
        "passed_checks": passed_checks,
        "failed_fields": [check.field_name for check in checks if not check.passed],
        "checks": [check.to_dict() for check in checks],
    }
