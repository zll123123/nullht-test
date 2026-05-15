"""Case 相关模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FocusStrategy:
    """关注点问题作答策略。"""

    branch: str
    custom_focus_pool: List[str]
    invalid_input: str
    fixed_option_label: str


@dataclass
class FocusDecision:
    """关注点问题实际执行结果。"""

    planned_branch: str
    actual_branch: str
    answer: str
    fixed_option_label: str
    fixed_option_text: str
    selected_option_label: str
    selected_option_text: str
    custom_input: str
    question: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "planned_branch": self.planned_branch,
            "actual_branch": self.actual_branch,
            "answer": self.answer,
            "fixed_option_label": self.fixed_option_label,
            "fixed_option_text": self.fixed_option_text,
            "selected_option_label": self.selected_option_label,
            "selected_option_text": self.selected_option_text,
            "custom_input": self.custom_input,
            "question": self.question,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FocusDecision":
        """从字典构造模型。"""
        return cls(
            planned_branch=str(data.get("planned_branch") or ""),
            actual_branch=str(data.get("actual_branch") or ""),
            answer=str(data.get("answer") or ""),
            fixed_option_label=str(data.get("fixed_option_label") or ""),
            fixed_option_text=str(data.get("fixed_option_text") or ""),
            selected_option_label=str(data.get("selected_option_label") or ""),
            selected_option_text=str(data.get("selected_option_text") or ""),
            custom_input=str(data.get("custom_input") or ""),
            question=str(data.get("question") or ""),
        )


@dataclass
class CaseConfig:
    """对话用例配置。"""

    case_id: str
    department: str
    scenario: str
    answers: List[str]
    expected: Dict[str, Any]
    focus_strategy: Optional[FocusStrategy]


@dataclass
class CaseCollection:
    """Case 集合配置。"""

    doctor_rank: str
    smoke_case_ids: List[str]
    cases: List[CaseConfig]
