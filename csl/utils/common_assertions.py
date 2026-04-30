"""公共断言工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


TEXT_CLEAN_PATTERN = re.compile(r"[\s●▶•{}]")
FULL_WIDTH_SPACE = "　"
EQUAL_ASSERTION_TYPE = "text_equal"
SIMILARITY_ASSERTION_TYPE = "text_similarity"
CONTAINS_ASSERTION_TYPE = "text_contains"
DEFAULT_SIMILARITY_THRESHOLD = 0.8


@dataclass
class AssertionResult:
    """通用断言结果。"""

    assertion_type: str
    expected: str
    actual: str
    passed: bool
    similarity_score: float
    message: str


class CommonAssertion:
    """公共断言类。"""

    @classmethod
    def normalize_text(cls, value: Any) -> str:
        """对文本做归一化处理。

        Args:
            value: 原始文本值。

        Returns:
            str: 归一化后的文本。
        """
        if value is None:
            return ""
        text = str(value).strip()
        text = TEXT_CLEAN_PATTERN.sub("", text)
        return text.replace(FULL_WIDTH_SPACE, "")

    @classmethod
    def calculate_similarity(
        cls,
        expected: Any,
        actual: Any,
        normalize: bool = True,
    ) -> float:
        """计算两段文本的相似度。

        Args:
            expected: 期望文本。
            actual: 实际文本。
            normalize: 是否先做文本归一化。

        Returns:
            float: 0 到 1 之间的相似度分值。
        """
        left_text = cls.normalize_text(expected) if normalize else str(expected or "")
        right_text = cls.normalize_text(actual) if normalize else str(actual or "")
        if not left_text and not right_text:
            return 1.0
        if not left_text or not right_text:
            return 0.0
        return SequenceMatcher(None, left_text, right_text).ratio()

    @classmethod
    def assert_text_equal(
        cls,
        expected: Any,
        actual: Any,
        normalize: bool = True,
    ) -> AssertionResult:
        """执行文本相等断言。

        Args:
            expected: 期望文本。
            actual: 实际文本。
            normalize: 是否先做文本归一化。

        Returns:
            AssertionResult: 断言结果。
        """
        left_text = cls.normalize_text(expected) if normalize else str(expected or "")
        right_text = cls.normalize_text(actual) if normalize else str(actual or "")
        passed = left_text == right_text
        message = "文本完全一致" if passed else "文本不一致"
        return AssertionResult(
            assertion_type=EQUAL_ASSERTION_TYPE,
            expected=str(expected or ""),
            actual=str(actual or ""),
            passed=passed,
            similarity_score=1.0 if passed else 0.0,
            message=message,
        )

    @classmethod
    def assert_text_similarity(
        cls,
        expected: Any,
        actual: Any,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        normalize: bool = True,
    ) -> AssertionResult:
        """执行文本相似度断言。

        Args:
            expected: 期望文本。
            actual: 实际文本。
            threshold: 判定通过的相似度阈值。
            normalize: 是否先做文本归一化。

        Returns:
            AssertionResult: 断言结果。
        """
        similarity_score = cls.calculate_similarity(expected, actual, normalize)
        passed = similarity_score >= threshold
        message = (
            f"文本相似度达标，当前分值={similarity_score:.4f}"
            if passed
            else f"文本相似度不达标，当前分值={similarity_score:.4f}"
        )
        return AssertionResult(
            assertion_type=SIMILARITY_ASSERTION_TYPE,
            expected=str(expected or ""),
            actual=str(actual or ""),
            passed=passed,
            similarity_score=similarity_score,
            message=message,
        )

    @classmethod
    def normalize_list_item_text(cls, value: Any) -> str:
        """归一化列表条目文本，忽略编号前缀。

        Args:
            value: 原始文本。

        Returns:
            str: 归一化后的文本。
        """
        text = cls.normalize_text(value)
        return re.sub(r"^\d+\.+", "", text)

    @classmethod
    def assert_text_contains(
        cls,
        expected: Any,
        actual: Any,
    ) -> AssertionResult:
        """执行支持列表编号归一化的包含断言。

        Args:
            expected: 期望文本。
            actual: 实际文本。

        Returns:
            AssertionResult: 断言结果。
        """
        expected_text = cls.normalize_text(expected)
        actual_text = cls.normalize_text(actual)
        if not expected_text:
            return AssertionResult(CONTAINS_ASSERTION_TYPE, "", str(actual or ""), True, 1.0, "无期望值，跳过校验")
        if expected_text in actual_text:
            return AssertionResult(CONTAINS_ASSERTION_TYPE, str(expected or ""), str(actual or ""), True, 1.0, "文本包含匹配成功")
        expected_lines = [
            cls.normalize_list_item_text(line)
            for line in str(expected or "").splitlines()
            if cls.normalize_list_item_text(line)
        ]
        actual_lines = [
            cls.normalize_list_item_text(line)
            for line in str(actual or "").splitlines()
            if cls.normalize_list_item_text(line)
        ]
        passed = bool(expected_lines) and bool(actual_lines) and all(
            any(expected_line in actual_line for actual_line in actual_lines)
            for expected_line in expected_lines
        )
        message = "文本包含匹配成功" if passed else "文本包含匹配失败"
        return AssertionResult(
            assertion_type=CONTAINS_ASSERTION_TYPE,
            expected=str(expected or ""),
            actual=str(actual or ""),
            passed=passed,
            similarity_score=1.0 if passed else 0.0,
            message=message,
        )
