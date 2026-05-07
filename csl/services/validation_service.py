"""兼容层：转发到 validators.validation_service。"""

from validators.assertion_builder import build_check, build_non_empty_check, build_not_contains_check, collapse_text
from validators.assertion_models import ValidationCheck, ValidationResult
from validators.field_extractors import extract_visit_plan
from validators.validation_rules import build_validation_checks
from validators.validation_service import build_validation_result

__all__ = [
    "ValidationCheck",
    "ValidationResult",
    "build_check",
    "build_non_empty_check",
    "build_not_contains_check",
    "collapse_text",
    "extract_visit_plan",
    "build_validation_checks",
    "build_validation_result",
]
