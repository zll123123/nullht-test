"""对话执行服务。"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from clients.chat_client import (
    fetch_visit_plan_detail,
    normalize_message,
    send_message,
    start_conversation,
    stop_conversation,
)
from config.app_config import AppConfig
from services.case_loader import CaseConfig, FocusDecision
from services.focus_service import choose_fallback_answer, choose_focus_answer, is_focus_question
from services.validation_service import build_validation_result, extract_visit_plan


def run_conversation_steps(
    session: Any,
    config: AppConfig,
    doctor_rank: str,
    case: CaseConfig,
    rng: random.Random,
) -> Dict[str, Any]:
    """执行单个 case 的完整对话流程。

    Args:
        session: 请求会话。
        config: 运行配置。
        doctor_rank: 医生职称回答。
        case: 当前用例。
        rng: 随机数生成器。

    Returns:
        Dict[str, Any]: 原始执行结果。
    """
    start_data = start_conversation(session, config)
    session_id = str(start_data["session_id"])
    planned_answers = [doctor_rank, *case.answers]
    steps: List[Dict[str, Any]] = []
    focus_decisions: List[Dict[str, Any]] = []
    question = (start_data.get("message") or [""])[-1]
    final_data: Dict[str, Any] = start_data
    while True:
        focus_decision: Optional[FocusDecision] = None
        if planned_answers:
            answer = planned_answers.pop(0)
        elif is_focus_question(str(question)):
            answer, focus_decision = choose_focus_answer(str(question), case, config, rng)
        else:
            answer = choose_fallback_answer(str(question), config, rng)
        final_data = send_message(session, config, session_id, answer)
        steps.append({"question": question, "answer": answer, "response": final_data})
        if focus_decision is not None:
            focus_decisions.append(focus_decision.to_dict())
        if final_data.get("is_complete"):
            break
        question = normalize_message(final_data)
        if not question:
            raise RuntimeError(f"{case.case_id} 未完成，但没有后续问题。")
    return {
        "session_id": session_id,
        "steps": steps,
        "final_data": final_data,
        "stop_data": stop_conversation(session, config, session_id),
        "detail_data": fetch_visit_plan_detail(session, config, session_id),
        "focus_decisions": focus_decisions,
    }


def run_case(
    session: Any,
    config: AppConfig,
    doctor_rank: str,
    case: CaseConfig,
    rng: random.Random,
) -> Dict[str, Any]:
    """执行单个用例并返回断言结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        doctor_rank: 医生职称回答。
        case: 当前用例。
        rng: 随机数生成器。

    Returns:
        Dict[str, Any]: 执行结果。
    """
    conversation_result = run_conversation_steps(session, config, doctor_rank, case, rng)
    final_data = conversation_result["final_data"]
    visit_plan = extract_visit_plan(final_data, conversation_result["detail_data"])
    focus_decisions = conversation_result.get("focus_decisions") or []
    return {
        "case_id": case.case_id,
        "scenario": case.scenario,
        "expected": case.expected,
        "focus_strategy": case.focus_strategy.branch if case.focus_strategy else "",
        "focus_decisions": focus_decisions,
        "session_id": conversation_result["session_id"],
        "steps": conversation_result["steps"],
        "final_data": final_data,
        "visit_plan": visit_plan,
        "stop_data": conversation_result["stop_data"],
        "detail_data": conversation_result["detail_data"],
        "validation": build_validation_result(case, final_data, visit_plan, focus_decisions),
    }
