from pathlib import Path
from config.constants import MATCH_CONTAINS
from services.case_loader import build_cases
from services.validation_service import build_check, collapse_text
from utils.execution_record_writer import build_case_record_lines, build_summary
from utils.yaml_loader import load_yaml_file

CASE_DATA_FILE = Path(__file__).parent / "data" / "test_case_priority.yaml"


def test_collapse_text() -> None:
    assert collapse_text("● 杰特贝林\n") == "杰特贝林"


def test_build_check_normalized_match() -> None:
    check = build_check("trans_info", "介绍 白蛋白", "介绍白蛋白")
    assert check is not None
    assert check.passed is True


def test_build_check_contains_match() -> None:
    check = build_check("focus_title", "安全性可靠么", "人血白蛋白是血液制品，安全性可靠么？", MATCH_CONTAINS)
    assert check is not None
    assert check.passed is True


def test_build_check_contains_match_ignore_list_prefix() -> None:
    check = build_check(
        "comm_literature_summaries",
        "1. ALBIOS研究支持早期使用白蛋白\n2. 白蛋白可降低并发症风险",
        "ALBIOS研究支持早期使用白蛋白\n白蛋白可降低并发症风险",
        MATCH_CONTAINS,
    )
    assert check is not None
    assert check.passed is True


def test_build_cases_prefer_yaml_expected() -> None:
    _, cases = build_cases(CASE_DATA_FILE)
    assert cases[0].expected["doctor_type"] == "来自YAML"

def test_load_yaml_file() -> None:
    data = load_yaml_file(CASE_DATA_FILE)
    assert data["cases"][0]["case_id"] == "P900"


def test_build_case_record_lines() -> None:
    lines = build_case_record_lines(
        {
            "case_id": "P001",
            "scenario": "示例场景",
            "status": "DONE",
            "session_id": "session-1",
            "focus_strategy": "F1",
            "focus_decisions": [{"actual_branch": "F1"}],
            "steps": [{"question": "系统提问1", "answer": "测试回答1", "response": {"message": "收到"}}],
            "visit_plan": {"visit_plan_digest": {"goal": "推进使用"}},
            "detail_data": {"visit_plan": {"session_id": "session-1"}},
            "validation": {"passed": True, "passed_checks": 2, "total_checks": 2, "failed_fields": [], "checks": []},
        }
    )
    joined = "\n".join(lines)
    assert "系统提问：系统提问1" in joined
    assert "测试回答：测试回答1" in joined
    assert "最终拜访计划" in joined
    assert "断言结果" in joined
    assert "状态：DONE" in joined


def test_build_summary_with_pending() -> None:
    summary = build_summary(
        [
            {"status": "PENDING_PLAN", "validation": {}},
            {"status": "DONE", "validation": {"passed": True}},
            {"status": "DONE", "validation": {"passed": False}},
            {"error": "boom"},
        ]
    )

    assert summary["pending"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 1
