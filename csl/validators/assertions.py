"""通用断言工具。"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, List


@dataclass
class AssertionResult:
    """断言结果。"""

    passed: bool
    expected: str
    actual: str
    similarity: float = 0.0


class CommonAssertion:
    """文本断言公共方法。"""

    @staticmethod
    def normalize_text(value: Any) -> str:
        """归一化文本。

        Args:
            value: 原始值。

        Returns:
            str: 归一化结果。
        """
        text = str(value or "")
        text = text.replace("\r", "\n")
        text = text.replace("（", "(").replace("）", ")")
        text = re.sub(r"[ \t\u3000]+", "", text)
        text = re.sub(r"\n+", "\n", text)
        text = re.sub(r"^[●▶•·]+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\{[^{}]+\}", "", text)
        text = re.sub(r"(?<=[\u4e00-\u9fffA-Za-z0-9\)\]])\d+(?:,\d+)*$", "", text)
        text = re.sub(r"(?m)(?<=[\u4e00-\u9fffA-Za-z0-9\)\]])\d+(?:,\d+)*$", "", text)
        text = re.sub(r"(?m)^\d+\.\s*\.\s*", "", text)
        text = re.sub(r"(?m)^\d+\.\s*", "", text)
        text = re.sub(r"(?m)^\.\s*", "", text)
        return text.strip()

    @classmethod
    def calculate_similarity(cls, expected: Any, actual: Any) -> float:
        """计算文本相似度。

        Args:
            expected: 预期值。
            actual: 实际值。

        Returns:
            float: 相似度。
        """
        normalized_expected = cls.normalize_text(expected)
        normalized_actual = cls.normalize_text(actual)
        if not normalized_expected and not normalized_actual:
            return 1.0
        return SequenceMatcher(None, normalized_expected, normalized_actual).ratio()

    @classmethod
    def assert_text_equal(cls, expected: Any, actual: Any) -> AssertionResult:
        """断言文本相等。"""
        normalized_expected = cls.normalize_text(expected)
        normalized_actual = cls.normalize_text(actual)
        similarity = cls.calculate_similarity(expected, actual)
        return AssertionResult(
            passed=normalized_expected == normalized_actual,
            expected=str(expected or ""),
            actual=str(actual or ""),
            similarity=similarity,
        )

    @classmethod
    def assert_text_contains(cls, expected: Any, actual: Any) -> AssertionResult:
        """断言文本包含。"""
        normalized_expected = cls.normalize_text(expected)
        normalized_actual = cls.normalize_text(actual)
        passed = normalized_expected in normalized_actual if normalized_expected else False
        if not passed and normalized_expected and normalized_actual:
            expected_lines = [line for line in normalized_expected.split("\n") if line]
            actual_lines = [line for line in normalized_actual.split("\n") if line]
            if expected_lines and actual_lines:
                passed = all(
                    any(SequenceMatcher(None, expected_line, actual_line).ratio() >= 0.85 for actual_line in actual_lines)
                    for expected_line in expected_lines
                )
        return AssertionResult(
            passed=passed,
            expected=str(expected or ""),
            actual=str(actual or ""),
            similarity=cls.calculate_similarity(expected, actual),
        )

    @classmethod
    def assert_text_list_exact(cls, expected: Any, actual: Any) -> AssertionResult:
        """断言多行列表逐条相等。"""
        expected_lines = cls._normalize_list(expected)
        actual_lines = cls._normalize_list(actual)
        return AssertionResult(
            passed=expected_lines == actual_lines,
            expected=str(expected or ""),
            actual=str(actual or ""),
            similarity=cls.calculate_similarity("\n".join(expected_lines), "\n".join(actual_lines)),
        )

    @classmethod
    def assert_text_similarity(cls, expected: Any, actual: Any, threshold: float) -> AssertionResult:
        """断言文本相似度达标。

        Args:
            expected: 预期值。
            actual: 实际值。
            threshold: 相似度阈值。

        Returns:
            AssertionResult: 断言结果。
        """
        similarity = cls.calculate_similarity(expected, actual)
        return AssertionResult(
            passed=similarity >= float(threshold),
            expected=str(expected or ""),
            actual=str(actual or ""),
            similarity=similarity,
        )

    @classmethod
    def _normalize_list(cls, value: Any) -> List[str]:
        """归一化列表文本。

        Args:
            value: 原始值。

        Returns:
            List[str]: 归一化后的列表。
        """
        text = str(value or "")
        lines = [cls.normalize_text(line) for line in text.splitlines()]
        return [line for line in lines if line]
