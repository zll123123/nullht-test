"""Case 数据加载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.constants import DEFAULT_INVALID_FOCUS_INPUT, FOCUS_BRANCHES, FOCUS_BRANCH_F1, FOCUS_BRANCH_F2_CUSTOM
from models.case_model import CaseCollection, CaseConfig, FocusDecision, FocusStrategy
from utils.yaml_loader import load_yaml_file


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


def build_cases(data_file: Path) -> CaseCollection:
    """加载并构建 case 列表。

    Args:
        data_file: case YAML 路径。

    Returns:
        CaseCollection: 医生职称、冒烟用例和 case 列表。
    """
    data = load_yaml_file(data_file)
    doctor_rank = str(data["doctor_rank"])
    smoke_case_ids = [str(case_id) for case_id in data.get("smoke_case_ids") or []]
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
    return CaseCollection(
        doctor_rank=doctor_rank,
        smoke_case_ids=smoke_case_ids,
        cases=cases,
    )


__all__ = [
    "FocusStrategy",
    "FocusDecision",
    "CaseConfig",
    "CaseCollection",
    "build_focus_strategy",
    "build_cases",
]
