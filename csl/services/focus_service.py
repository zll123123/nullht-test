"""关注点问题处理。"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from config.app_config import AppConfig
from config.constants import (
    DEFAULT_INVALID_FOCUS_INPUT,
    FOCUS_BRANCH_F1,
    FOCUS_BRANCH_F2_CUSTOM,
    FOCUS_BRANCH_F2_OPTION,
    FOCUS_BRANCH_F3,
)
from models.case_model import CaseConfig, FocusDecision
from services.focus_match_service import match_focus_option_by_llm
from validators.assertions import CommonAssertion

OPTIONS_BLOCK_PATTERN = re.compile(r"\[OPTIONS\](.*?)\[/OPTIONS\]", re.IGNORECASE | re.DOTALL)
FOCUS_OPTION_PATTERN = re.compile(
    r"(?s)([A-D])(?:[\.．、:：]|\s)\s*(.+?)(?=(?:\s+[A-D](?:[\.．、:：]|\s))|$)"
)


class FocusService:
    """关注点处理服务。"""

    @staticmethod
    def normalize_text(value: Any) -> str:
        """归一化文本。

        Args:
            value: 原始值。

        Returns:
            str: 归一化结果。
        """
        return CommonAssertion.normalize_text(value)

    @staticmethod
    def is_focus_question(question: str) -> bool:
        """判断是否为关注点问题。

        Args:
            question: 系统问题。

        Returns:
            bool: 是否命中关注点问题。
        """
        return "关注点" in question or "最可能关心" in question

    @staticmethod
    def extract_focus_options(question: str) -> List[Dict[str, str]]:
        """提取关注点选项。

        Args:
            question: 问题文本。

        Returns:
            List[Dict[str, str]]: 选项列表。
        """
        block_match = OPTIONS_BLOCK_PATTERN.search(question)
        cleaned_question = block_match.group(1) if block_match else question.replace("[OPTIONS]", "")
        options: List[Dict[str, str]] = []
        for label, option_text in FOCUS_OPTION_PATTERN.findall(cleaned_question):
            merged_text = " ".join(line.strip() for line in option_text.splitlines() if line.strip())
            options.append({"label": label.strip().upper(), "text": merged_text})
        return options

    @staticmethod
    def find_option_by_label(options: List[Dict[str, str]], label: str) -> Optional[Dict[str, str]]:
        """按标签查找选项。

        Args:
            options: 选项列表。
            label: 选项标签。

        Returns:
            Optional[Dict[str, str]]: 命中的选项。
        """
        normalized_label = label.strip().upper()
        for option in options:
            if option["label"] == normalized_label:
                return option
        return None

    @classmethod
    def calculate_focus_option_score(cls, focus_title: str, option_text: str) -> float:
        """计算固定关注点与候选选项的匹配分值。

        Args:
            focus_title: 固定关注点标题。
            option_text: 候选选项文本。

        Returns:
            float: 匹配分值。
        """
        normalized_title = cls.normalize_text(focus_title)
        normalized_option = cls.normalize_text(option_text)
        if normalized_title and normalized_title in normalized_option:
            return 1.0
        if normalized_option and normalized_option in normalized_title:
            return 1.0
        return CommonAssertion.calculate_similarity(focus_title, option_text)

    @classmethod
    def choose_fallback_answer(cls, question: str, config: AppConfig, rng: random.Random) -> str:
        """为未预设问题选择兜底回答。

        Args:
            question: 当前问题文本。
            config: 运行配置。
            rng: 随机数生成器。

        Returns:
            str: 回答内容。
        """
        if "[OPTIONS]" in question:
            options = cls.extract_focus_options(question)
            if options:
                return rng.choice(options)["label"]
        return config.default_focus_answer

    @classmethod
    def match_fixed_option(
        cls,
        options: List[Dict[str, str]],
        case: CaseConfig,
        config: AppConfig,
        question: str,
    ) -> Optional[Dict[str, str]]:
        """匹配固定关注点对应选项。

        Args:
            options: 当前问题选项。
            case: 当前用例。
            config: 运行配置。
            question: 当前问题文本。

        Returns:
            Optional[Dict[str, str]]: 固定关注点命中的选项。
        """
        strategy = case.focus_strategy
        if strategy is None:
            return None
        if strategy.fixed_option_label:
            fixed_option = cls.find_option_by_label(options, strategy.fixed_option_label)
            if fixed_option is not None:
                return fixed_option
        llm_match_result = match_focus_option_by_llm(config, question, str(case.expected.get("focus_title") or ""))
        if llm_match_result and llm_match_result.get("is_match_focus_point") is True:
            fixed_option = cls.find_option_by_label(options, str(llm_match_result.get("option_letter") or ""))
            if fixed_option is not None:
                return fixed_option
        focus_title = str(case.expected.get("focus_title") or "")
        if not options or not cls.normalize_text(focus_title):
            return None
        return max(options, key=lambda option: cls.calculate_focus_option_score(focus_title, option["text"]))

    @classmethod
    def classify_focus_branch(
        cls,
        answer: str,
        fixed_option: Optional[Dict[str, str]],
        options: List[Dict[str, str]],
    ) -> str:
        """根据实际回答反推关注点分支。

        Args:
            answer: 实际回答。
            fixed_option: 固定关注点对应选项。
            options: 当前问题全部选项。

        Returns:
            str: 实际命中的关注点分支。
        """
        normalized_answer = answer.strip()
        if normalized_answer in {"", DEFAULT_INVALID_FOCUS_INPUT, "不清楚"}:
            return FOCUS_BRANCH_F3
        selected_option = cls.find_option_by_label(options, normalized_answer)
        if selected_option is None:
            return FOCUS_BRANCH_F2_CUSTOM
        if fixed_option and selected_option["label"] == fixed_option["label"]:
            return FOCUS_BRANCH_F1
        return FOCUS_BRANCH_F2_OPTION

    @classmethod
    def resolve_focus_strategy(
        cls,
        question: str,
        case: CaseConfig,
        config: AppConfig,
        rng: random.Random,
    ) -> Tuple[str, Optional[FocusDecision]]:
        """根据策略生成关注点问题回答。

        Args:
            question: 当前问题。
            case: 当前用例。
            config: 运行配置。
            rng: 随机数生成器。

        Returns:
            Tuple[str, Optional[FocusDecision]]: 回答和执行记录。
        """
        if case.focus_strategy is None:
            return cls.choose_fallback_answer(question, config, rng), None
        strategy = case.focus_strategy
        options = cls.extract_focus_options(question)
        fixed_option = cls.match_fixed_option(options, case, config, question)
        answer = config.default_focus_answer
        custom_input = ""
        if strategy.branch == FOCUS_BRANCH_F1 and fixed_option:
            answer = fixed_option["label"]
        elif strategy.branch == FOCUS_BRANCH_F2_OPTION and options:
            non_fixed_options = [item for item in options if fixed_option is None or item["label"] != fixed_option["label"]]
            answer = rng.choice(non_fixed_options or options)["label"]
        elif strategy.branch == FOCUS_BRANCH_F2_CUSTOM:
            custom_input = rng.choice(strategy.custom_focus_pool)
            answer = custom_input
        elif strategy.branch == FOCUS_BRANCH_F3:
            answer = strategy.invalid_input
        selected_option = cls.find_option_by_label(options, answer)
        return answer, FocusDecision(
            planned_branch=strategy.branch,
            actual_branch=cls.classify_focus_branch(answer, fixed_option, options),
            answer=answer,
            fixed_option_label=fixed_option["label"] if fixed_option else "",
            fixed_option_text=fixed_option["text"] if fixed_option else "",
            selected_option_label=selected_option["label"] if selected_option else "",
            selected_option_text=selected_option["text"] if selected_option else "",
            custom_input=custom_input,
            question=question,
        )


def is_focus_question(question: str) -> bool:
    """兼容旧调用的关注点判断函数。"""
    return FocusService.is_focus_question(question)


def choose_fallback_answer(question: str, config: AppConfig, rng: random.Random) -> str:
    """兼容旧调用的兜底回答函数。"""
    return FocusService.choose_fallback_answer(question, config, rng)


def extract_focus_options(question: str) -> List[Dict[str, str]]:
    """兼容旧调用的选项提取函数。"""
    return FocusService.extract_focus_options(question)


def choose_focus_answer(
    question: str,
    case: CaseConfig,
    config: AppConfig,
    rng: random.Random,
) -> Tuple[str, Optional[FocusDecision]]:
    """兼容旧调用的关注点回答函数。"""
    return FocusService.resolve_focus_strategy(question, case, config, rng)
