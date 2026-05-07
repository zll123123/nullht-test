"""断言相关模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ValidationCheck:
    """单个断言结果。"""

    field_name: str
    expected: str
    actual: str
    passed: bool
    match_mode: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "field_name": self.field_name,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "match_mode": self.match_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationCheck":
        """从字典构造模型。"""
        return cls(
            field_name=str(data.get("field_name") or ""),
            expected=str(data.get("expected") or ""),
            actual=str(data.get("actual") or ""),
            passed=bool(data.get("passed")),
            match_mode=str(data.get("match_mode") or ""),
        )


@dataclass
class ValidationResult:
    """断言汇总结果。"""

    passed: bool
    total_checks: int
    passed_checks: int
    failed_fields: List[str]
    checks: List[ValidationCheck]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_fields": self.failed_fields,
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationResult":
        """从字典构造模型。"""
        return cls(
            passed=bool(data.get("passed")),
            total_checks=int(data.get("total_checks") or 0),
            passed_checks=int(data.get("passed_checks") or 0),
            failed_fields=[str(item) for item in data.get("failed_fields") or []],
            checks=[ValidationCheck.from_dict(item) for item in data.get("checks") or []],
        )
