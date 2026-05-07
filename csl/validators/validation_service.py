"""拜访计划断言服务。"""

from __future__ import annotations

from typing import Any, Dict, List

from models.case_model import CaseConfig, FocusDecision
from validators.assertion_models import ValidationResult
from validators.validation_rules import build_validation_checks


def build_validation_result(
    case: CaseConfig,
    final_data: Dict[str, Any],
    visit_plan: Dict[str, Any],
    focus_decisions: List[FocusDecision],
) -> ValidationResult:
    """构建断言结果。"""
    checks = build_validation_checks(case, final_data, visit_plan, focus_decisions)
    passed_checks = sum(1 for check in checks if check.passed)
    return ValidationResult(
        passed=passed_checks == len(checks),
        total_checks=len(checks),
        passed_checks=passed_checks,
        failed_fields=[check.field_name for check in checks if not check.passed],
        checks=checks,
    )
