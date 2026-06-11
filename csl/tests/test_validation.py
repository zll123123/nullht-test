"""断言、用例加载与报告摘要相关单元测试。"""

from pathlib import Path
from config.constants import MATCH_CONTAINS, MATCH_LIST_EXACT
from models.case_model import FocusDecision
from models.result_model import CaseExecutionResult, ConversationStep
from services.case_loader import build_cases
from reporters.json_reporter import filter_cases
from reporters.markdown_reporter import build_case_record_lines, build_failed_case_summary_lines, build_summary
from utils.yaml_loader import load_yaml_file
from validators.assertion_builder import build_check, collapse_text
from validators.assertion_models import ValidationResult

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


def test_build_check_list_exact_match() -> None:
    check = build_check(
        "comm_literature_titles",
        "1. . Caironi et al. N Engl J Med 2014; 370: 1412‒21\n2. Jean-Louis Vincent, et al. Crit Care Med. 2004 Oct;3 (10):2029-38.",
        "1. Caironi et al. N Engl J Med 2014; 370: 1412‒21\n2. Jean-Louis Vincent, et al. Crit Care Med. 2004 Oct;3 (10):2029-38.",
        MATCH_LIST_EXACT,
    )
    assert check is not None
    assert check.passed is True


def test_validation_result_to_dict() -> None:
    validation = ValidationResult(
        passed=False,
        total_checks=2,
        passed_checks=1,
        failed_fields=["focus_title"],
        checks=[],
    )

    data = validation.to_dict()

    assert data["passed"] is False
    assert data["total_checks"] == 2
    assert data["passed_checks"] == 1
    assert data["failed_fields"] == ["focus_title"]


def test_build_cases_prefer_yaml_expected() -> None:
    case_collection = build_cases(CASE_DATA_FILE)
    assert case_collection.cases[0].expected["doctor_type"] == "来自YAML"
    assert case_collection.cases[0].department == "ICU"


def test_build_cases_load_smoke_case_ids() -> None:
    case_collection = build_cases(Path("/Users/layla.zhang/workspace/nullht-test/csl/data/csl_full_paths.yaml"))
    assert case_collection.smoke_case_ids == ["P003", "P021", "P032", "P061", "P084", "P048", "P077", "P106", "P107"]


def test_filter_cases_with_smoke_case_ids() -> None:
    case_collection = build_cases(Path("/Users/layla.zhang/workspace/nullht-test/csl/data/csl_full_paths.yaml"))
    filtered_cases = filter_cases(case_collection.cases, case_id=None, smoke_case_ids=["P009", "P029"])
    assert [case.case_id for case in filtered_cases] == ["P009", "P029"]


def test_filter_cases_with_department() -> None:
    case_collection = build_cases(Path("/Users/layla.zhang/workspace/nullht-test/csl/data/csl_full_paths.yaml"))
    filtered_cases = filter_cases(case_collection.cases, case_id=None, department="药剂科")
    assert filtered_cases
    assert all(case.department == "医院管理层/药剂科" for case in filtered_cases)

def test_load_yaml_file() -> None:
    data = load_yaml_file(CASE_DATA_FILE)
    assert data["cases"][0]["case_id"] == "P900"


def test_build_case_record_lines() -> None:
    lines = build_case_record_lines(
        CaseExecutionResult(
            case_id="P001",
            scenario="示例场景",
            expected={},
            focus_strategy="F1",
            focus_decisions=[
                FocusDecision(
                    planned_branch="F1",
                    actual_branch="F1",
                    answer="A",
                    fixed_option_label="A",
                    fixed_option_text="",
                    selected_option_label="A",
                    selected_option_text="",
                    custom_input="",
                    question="",
                )
            ],
            session_id="session-1",
            steps=[ConversationStep(question="系统提问1", answer="测试回答1", response={"message": "收到"})],
            final_data={},
            visit_plan={"visit_plan_digest": {"goal": "推进使用"}},
            stop_data={},
            detail_data={"visit_plan": {"session_id": "session-1"}},
            validation=ValidationResult(passed=True, passed_checks=2, total_checks=2, failed_fields=[], checks=[]),
            status="DONE",
        )
    )
    joined = "\n".join(lines)
    assert "系统提问：系统提问1" in joined
    assert "测试回答：测试回答1" in joined
    assert "最终拜访计划" in joined
    assert "断言结果" in joined
    assert "状态：DONE" in joined
    assert "系统响应" not in joined
    assert "详情接口返回" not in joined


def test_build_summary_with_pending() -> None:
    summary = build_summary(
        [
            CaseExecutionResult("P001", "a", {}, "", [], "", [], {}, {}, {}, {}, None, "PENDING_PLAN"),
            CaseExecutionResult(
                "P002",
                "b",
                {},
                "",
                [],
                "",
                [],
                {},
                {},
                {},
                {},
                ValidationResult(True, 1, 1, [], []),
                "DONE",
            ),
            CaseExecutionResult(
                "P003",
                "c",
                {},
                "",
                [],
                "",
                [],
                {},
                {},
                {},
                {},
                ValidationResult(False, 1, 0, ["x"], []),
                "DONE",
            ),
            CaseExecutionResult("P004", "d", {}, "", [], "", [], {}, {}, {}, {}, None, "DONE", error="boom"),
        ]
    )

    assert summary.pending == 1
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1


def test_build_failed_case_summary_lines() -> None:
    lines = build_failed_case_summary_lines(
        [
            CaseExecutionResult(
                "P001",
                "a",
                {},
                "",
                [],
                "",
                [],
                {},
                {},
                {},
                {},
                ValidationResult(True, 1, 1, [], []),
                "DONE",
                result_type="通过",
            ),
            CaseExecutionResult(
                "P009",
                "b",
                {},
                "",
                [],
                "",
                [],
                {},
                {},
                {},
                {},
                ValidationResult(False, 2, 0, ["focus_title", "focus_content"], []),
                "DONE",
                result_type="断言失败",
                failure_reason="断言失败字段: focus_title, focus_content",
            ),
        ]
    )

    joined = "\n".join(lines)
    assert "未通过 case 数：1" in joined
    assert "P009 | 断言失败" in joined
    assert "focus_title, focus_content" in joined
