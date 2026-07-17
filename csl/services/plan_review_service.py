"""LLM 拜访计划审核服务，负责渲染审核 prompt 并保存审核结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from clients.llm_client import call_llm_text, normalize_llm_json
from config.app_config import AppConfig
from config.settings import PROMPTS_DIR
from models.result_model import ConversationStep, PlanReview
from services.conversation_evaluation_service import format_conversation_steps, render_prompt
from utils.api_timing import ApiCallCollector


def is_plan_review_enabled(config: AppConfig) -> bool:
    """判断是否启用拜访计划审核。

    Args:
        config: 运行配置。

    Returns:
        bool: 是否启用。
    """
    return bool(
        config.llm_enabled
        and config.llm_plan_review_enabled
        and config.llm_base_url
        and config.llm_model
        and config.llm_api_key
        and config.llm_plan_review_prompt_file
    )


def resolve_plan_review_prompt_file(config: AppConfig) -> Path:
    """解析拜访计划审核 prompt 文件路径。

    Args:
        config: 运行配置。

    Returns:
        Path: prompt 文件路径。
    """
    prompt_file = Path(config.llm_plan_review_prompt_file)
    if prompt_file.is_absolute():
        return prompt_file
    return PROMPTS_DIR / prompt_file


def parse_plan_review_content(content: str) -> Dict[str, Any]:
    """解析拜访计划审核结果。

    Args:
        content: LLM 返回内容。

    Returns:
        Dict[str, Any]: JSON 结果或原始文本包装。
    """
    try:
        return normalize_llm_json(content)
    except Exception:
        return {"raw_text": content}


def build_doctor_profile(expected: Dict[str, Any], visit_plan: Dict[str, Any]) -> str:
    """构建医生画像输入。

    Args:
        expected: YAML 中配置的预期结果。
        visit_plan: 最终拜访计划。

    Returns:
        str: JSON 格式医生画像。
    """
    digest = visit_plan.get("visit_plan_digest") or {}
    doctor_info = digest.get("doctorInfo") or {}
    expected_digest = expected.get("visit_plan_digest") or {}
    profile = {
        "expected": expected_digest,
        "actual_doctor_info": doctor_info,
        "doctor_type": expected.get("doctor_type"),
        "doctor_grade": expected.get("doctor_grade"),
    }
    return json.dumps(profile, ensure_ascii=False, indent=2)


def build_path_info(case_id: str, scenario: str, expected: Dict[str, Any], focus_strategy: str) -> str:
    """构建执行路径输入。

    Args:
        case_id: 用例编号。
        scenario: 用例场景。
        expected: YAML 中配置的预期结果。
        focus_strategy: 关注点策略。

    Returns:
        str: JSON 格式执行路径。
    """
    path_info = {
        "case_id": case_id,
        "scenario": scenario,
        "source_excel_row": expected.get("source_excel_row"),
        "focus_strategy": focus_strategy,
    }
    return json.dumps(path_info, ensure_ascii=False, indent=2)


def review_visit_plan_by_llm(
    config: AppConfig,
    case_id: str,
    scenario: str,
    expected: Dict[str, Any],
    focus_strategy: str,
    session_id: str,
    steps: List[ConversationStep],
    visit_plan: Dict[str, Any],
    api_collector: ApiCallCollector | None = None,
) -> PlanReview:
    """调用 LLM 审核最终拜访计划。

    Args:
        config: 运行配置。
        case_id: 用例编号。
        scenario: 用例场景。
        expected: YAML 中配置的预期结果。
        focus_strategy: 关注点策略。
        session_id: 会话 ID。
        steps: 对话步骤。
        visit_plan: 最终拜访计划。
        api_collector: 接口结果收集器。

    Returns:
        PlanReview: 拜访计划审核结果。
    """
    if not is_plan_review_enabled(config):
        return PlanReview(enabled=False)
    if not visit_plan:
        return PlanReview(enabled=True, error="拜访计划为空，无法审核")
    try:
        prompt_template = resolve_plan_review_prompt_file(config).read_text(encoding="utf-8")
        prompt = render_prompt(
            prompt_template,
            {
                "conversation": format_conversation_steps(steps),
                "visit_plan": json.dumps(visit_plan, ensure_ascii=False, indent=2),
                "doctor_profile": build_doctor_profile(expected, visit_plan),
                "path_info": build_path_info(case_id, scenario, expected, focus_strategy),
            },
        )
        content = call_llm_text(
            config=config,
            prompt=prompt,
            api_name="review_visit_plan_by_llm",
            api_collector=api_collector,
            session_id=session_id,
            case_id=case_id,
        )
        return PlanReview(enabled=True, result=parse_plan_review_content(content))
    except Exception as exc:
        return PlanReview(enabled=True, error=str(exc))
