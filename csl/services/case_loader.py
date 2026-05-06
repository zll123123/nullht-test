"""Case 数据加载。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.constants import DEFAULT_INVALID_FOCUS_INPUT, FOCUS_BRANCHES, FOCUS_BRANCH_F1, FOCUS_BRANCH_F2_CUSTOM
from utils.yaml_loader import load_yaml_file


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
        """转换为字典。

        Args:
            self: 当前实例。

        Returns:
            Dict[str, Any]: 可序列化字典。
        """
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


@dataclass
class CaseConfig:
    """对话用例配置。"""

    case_id: str
    scenario: str
    answers: List[str]
    expected: Dict[str, Any]
    focus_strategy: Optional[FocusStrategy]


def normalize_focus_branch(branch: str) -> str:
    """标准化关注点分支名称。

    Args:
        branch: 原始分支名称。

    Returns:
        str: 标准化后的分支名称。
    """
    return branch.strip().upper().replace("-", "_")


def build_focus_strategy(item: Dict[str, Any]) -> Optional[FocusStrategy]:
    """根据 YAML 构建关注点策略。

    Args:
        item: 单条 case 原始数据。

    Returns:
        Optional[FocusStrategy]: 关注点策略；不需要时返回 None。
    """
    expected = item.get("expected") or {}
    raw_strategy = item.get("focus_strategy") or {}
    if not raw_strategy and not expected.get("focus_title") and not expected.get("focus_content"):
        return None
    if not raw_strategy and expected.get("route_type"):
        return None
    branch = normalize_focus_branch(str(raw_strategy.get("branch") or FOCUS_BRANCH_F1))
    if branch not in FOCUS_BRANCHES:
        raise ValueError(f"{item.get('case_id', '')} 的关注点分支非法: {branch}")
    custom_focus_pool = [str(value) for value in raw_strategy.get("custom_focus_pool") or []]
    invalid_input = str(raw_strategy.get("invalid_input") or DEFAULT_INVALID_FOCUS_INPUT)
    fixed_option_label = str(raw_strategy.get("fixed_option_label") or "").strip().upper()
    if branch == FOCUS_BRANCH_F2_CUSTOM and not custom_focus_pool:
        raise ValueError(f"{item.get('case_id', '')} 的 F2 自定义关注点池不能为空")
    return FocusStrategy(
        branch=branch,
        custom_focus_pool=custom_focus_pool,
        invalid_input=invalid_input,
        fixed_option_label=fixed_option_label,
    )


def build_cases(data_file: Path) -> Tuple[str, List[CaseConfig]]:
    """加载并构建 case 列表。

    Args:
        data_file: case YAML 路径。

    Returns:
        Tuple[str, List[CaseConfig]]: 医生职称和 case 列表。
    """
    data = load_yaml_file(data_file)
    doctor_rank = str(data["doctor_rank"])
    cases: List[CaseConfig] = []
    for item in data.get("cases") or []:
        case_id = str(item.get("case_id", ""))
        scenario = str(item.get("scenario", ""))
        answers = [str(answer) for answer in item.get("answers") or []]
        if not case_id or not scenario or not answers:
            raise ValueError(f"case 数据不完整: {item}")
        cases.append(
            CaseConfig(
                case_id=case_id,
                scenario=scenario,
                answers=answers,
                expected=item.get("expected") or {},
                focus_strategy=build_focus_strategy(item),
            )
        )
    return doctor_rank, cases
