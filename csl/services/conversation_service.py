"""对话执行服务，负责按 case 回答问题、停止会话并触发对话评估。"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from clients.chat_client import (
    normalize_message,
    send_message,
    start_conversation,
    stop_conversation,
)
from config.app_config import AppConfig
from models.case_model import CaseConfig, FocusDecision
from models.result_model import CaseExecutionResult, ConversationExecutionResult, ConversationStep
from services.conversation_evaluation_service import evaluate_conversation_by_llm
from services.focus_service import choose_fallback_answer, choose_focus_answer, is_focus_question
from utils.api_timing import ApiCallCollector


def can_stop_conversation(final_data: Dict[str, Any]) -> bool:
    """判断当前会话是否允许调用停止接口。

    Args:
        final_data: 最后一轮消息接口返回的 data。

    Returns:
        bool: 是否允许停止会话。
    """
    return bool(final_data.get("can_stop"))


def run_conversation_steps(
    session: Any,
    config: AppConfig,
    doctor_rank: str,
    case: CaseConfig,
    rng: random.Random,
) -> ConversationExecutionResult:
    """执行单个 case 的完整对话流程。

    Args:
        session: 请求会话。
        config: 运行配置。
        doctor_rank: 医生职称回答。
        case: 当前用例。
        rng: 随机数生成器。

    Returns:
        ConversationExecutionResult: 原始执行结果。
    """
    api_collector = ApiCallCollector(case_id=case.case_id)
    start_data = start_conversation(session, config, api_collector=api_collector, case_id=case.case_id)
    session_id = str(start_data["session_id"])
    api_collector.set_session_id(session_id)
    planned_answers = [doctor_rank, *case.answers]
    steps: List[ConversationStep] = []
    focus_decisions: List[FocusDecision] = []
    question = (start_data.get("message") or [""])[-1]
    final_data: Dict[str, Any] = start_data
    first_can_stop_step_index = 0
    while True:
        focus_decision: Optional[FocusDecision] = None
        if planned_answers:
            answer = planned_answers.pop(0)
        elif is_focus_question(str(question)):
            answer, focus_decision = choose_focus_answer(
                str(question),
                case,
                config,
                rng,
                api_collector=api_collector,
                session_id=session_id,
            )
        else:
            answer = choose_fallback_answer(str(question), config, rng)
        final_data = send_message(session, config, session_id, answer, api_collector=api_collector)
        steps.append(ConversationStep(question=question, answer=answer, response=final_data))
        if can_stop_conversation(final_data) and first_can_stop_step_index == 0:
            first_can_stop_step_index = len(steps)
        if focus_decision is not None:
            focus_decisions.append(focus_decision)
        if final_data.get("is_complete"):
            break
        question = normalize_message(final_data)
        if not question:
            raise RuntimeError(f"{case.case_id} 未完成，但没有后续问题。")
    stop_data: Dict[str, Any] = {}
    stop_error = ""
    stop_called_step_index = 0
    if can_stop_conversation(final_data):
        stop_called_step_index = len(steps)
        try:
            stop_data = stop_conversation(session, config, session_id, api_collector=api_collector)
        except Exception as exc:
            stop_error = str(exc)
    conversation_evaluation = evaluate_conversation_by_llm(
        config=config,
        case_id=case.case_id,
        scenario=case.scenario,
        session_id=session_id,
        steps=steps,
        final_data=final_data,
        api_collector=api_collector,
    )
    return ConversationExecutionResult(
        session_id=session_id,
        steps=steps,
        final_data=final_data,
        stop_data=stop_data,
        stop_error=stop_error,
        first_can_stop_step_index=first_can_stop_step_index,
        stop_called_step_index=stop_called_step_index,
        focus_decisions=focus_decisions,
        api_call_records=api_collector.records,
        conversation_evaluation=conversation_evaluation,
    )

def build_pending_case_result(
    session: Any,
    config: AppConfig,
    doctor_rank: str,
    case: CaseConfig,
    rng: random.Random,
) -> CaseExecutionResult:
    """执行单个用例并生成待补全结果。

    Args:
        session: 请求会话。
        config: 运行配置。
        doctor_rank: 医生职称回答。
        case: 当前用例。
        rng: 随机数生成器。

    Returns:
        CaseExecutionResult: 待补全结果。
    """
    conversation_result = run_conversation_steps(
        session=session,
        config=config,
        doctor_rank=doctor_rank,
        case=case,
        rng=rng,
    )
    return CaseExecutionResult(
        case_id=case.case_id,
        scenario=case.scenario,
        expected=case.expected,
        focus_strategy=case.focus_strategy.branch if case.focus_strategy else "",
        focus_decisions=conversation_result.focus_decisions,
        session_id=conversation_result.session_id,
        steps=conversation_result.steps,
        final_data=conversation_result.final_data,
        visit_plan={},
        stop_data=conversation_result.stop_data,
        stop_error=conversation_result.stop_error,
        first_can_stop_step_index=conversation_result.first_can_stop_step_index,
        stop_called_step_index=conversation_result.stop_called_step_index,
        detail_data={},
        validation=None,
        status="PENDING_PLAN",
        api_call_records=conversation_result.api_call_records,
        conversation_evaluation=conversation_result.conversation_evaluation,
    )
