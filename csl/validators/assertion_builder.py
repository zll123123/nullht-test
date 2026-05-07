"""断言构建器。"""

from __future__ import annotations

from typing import Any, Optional

from config.constants import MATCH_CONTAINS, MATCH_EXACT, MATCH_LIST_EXACT, MATCH_NOT_CONTAINS, MATCH_NOT_EMPTY
from validators.assertion_models import ValidationCheck
from validators.assertions import CommonAssertion


def collapse_text(value: Any) -> str:
    """规整文本。"""
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
