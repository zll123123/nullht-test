"""执行结果相关模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.case_model import FocusDecision
from validators.assertion_models import ValidationResult


@dataclass
class ConversationStep:
    """单轮对话步骤。"""

    question: str
    answer: str
    response: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "question": self.question,
            "answer": self.answer,
            "response": self.response,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationStep":
        """从字典构造模型。"""
        return cls(
            question=str(data.get("question") or ""),
            answer=str(data.get("answer") or ""),
            response=dict(data.get("response") or {}),
        )


@dataclass
class ConversationExecutionResult:
    """单个对话用例的执行结果。"""

    session_id: str
    steps: List[ConversationStep]
    final_data: Dict[str, Any]
    stop_data: Dict[str, Any]
    focus_decisions: List[FocusDecision]


@dataclass
class CaseExecutionResult:
    """单条 case 的完整执行结果。"""

    case_id: str
    scenario: str
    expected: Dict[str, Any]
    focus_strategy: str
    focus_decisions: List[FocusDecision]
    session_id: str
    steps: List[ConversationStep]
    final_data: Dict[str, Any]
    visit_plan: Dict[str, Any]
    stop_data: Dict[str, Any]
    detail_data: Dict[str, Any]
    validation: Optional[ValidationResult]
    status: str
    result_type: str = ""
    failure_reason: str = ""
    error: str = ""
    poll_attempts: int = 0
    next_poll_at: float = 0.0
    poll_deadline_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "expected": self.expected,
            "focus_strategy": self.focus_strategy,
            "focus_decisions": [item.to_dict() for item in self.focus_decisions],
            "session_id": self.session_id,
            "steps": [step.to_dict() for step in self.steps],
            "final_data": self.final_data,
            "visit_plan": self.visit_plan,
            "stop_data": self.stop_data,
            "detail_data": self.detail_data,
            "validation": self.validation.to_dict() if self.validation is not None else {},
            "status": self.status,
            "result_type": self.result_type,
            "failure_reason": self.failure_reason,
            "error": self.error,
            "poll_attempts": self.poll_attempts,
            "next_poll_at": self.next_poll_at,
            "poll_deadline_at": self.poll_deadline_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseExecutionResult":
        """从字典构造模型。"""
        validation_data = data.get("validation") or {}
        return cls(
            case_id=str(data.get("case_id") or ""),
            scenario=str(data.get("scenario") or ""),
            expected=dict(data.get("expected") or {}),
            focus_strategy=str(data.get("focus_strategy") or ""),
            focus_decisions=[FocusDecision.from_dict(item) for item in data.get("focus_decisions") or []],
            session_id=str(data.get("session_id") or ""),
            steps=[ConversationStep.from_dict(item) for item in data.get("steps") or []],
            final_data=dict(data.get("final_data") or {}),
            visit_plan=dict(data.get("visit_plan") or {}),
            stop_data=dict(data.get("stop_data") or {}),
            detail_data=dict(data.get("detail_data") or {}),
            validation=ValidationResult.from_dict(validation_data) if validation_data else None,
            status=str(data.get("status") or ""),
            result_type=str(data.get("result_type") or ""),
            failure_reason=str(data.get("failure_reason") or ""),
            error=str(data.get("error") or ""),
            poll_attempts=int(data.get("poll_attempts") or 0),
            next_poll_at=float(data.get("next_poll_at") or 0.0),
            poll_deadline_at=float(data.get("poll_deadline_at") or 0.0),
        )


@dataclass
class ExecutionSummary:
    """执行汇总结果。"""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    pending: int = 0
    total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "pending": self.pending,
            "total": self.total,
        }
