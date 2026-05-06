from pathlib import Path
import random
from typing import Any, Dict, List, Optional

from config.app_config import AppConfig
from config.constants import (
    DEFAULT_INVALID_FOCUS_INPUT,
    FOCUS_BRANCH_F1,
    FOCUS_BRANCH_F2_CUSTOM,
    FOCUS_BRANCH_F2_OPTION,
    FOCUS_BRANCH_F3,
)
from services.case_loader import CaseConfig, FocusStrategy
from services.case_loader import build_focus_strategy
from services.focus_service import choose_focus_answer, extract_focus_options
from services.validation_service import build_validation_checks
from utils.yaml_loader import load_yaml_file

DATA_FILE = Path(__file__).parent / "data" / "test_focus_strategy.yaml"


def build_test_config() -> AppConfig:
    """构建测试使用的运行配置。

    Args:
        None

    Returns:
        AppConfig: 测试配置对象。
    """
    return AppConfig(
        base_url="http://localhost",
        start_path="/start",
        message_path="/message",
        stop_path="/stop",
        detail_path="/detail",
        timeout_seconds=30,
        detail_poll_wait_seconds=0,
        detail_poll_interval_seconds=1,
        verify_ssl=False,
        default_focus_answer="A",
        log_level="INFO",
        accept="application/json, text/plain, */*",
        accept_language="zh-CN,zh;q=0.9",
        origin="http://localhost",
        referer="http://localhost/page",
        user_agent="pytest-agent",
        token="",
        cookie="",
        llm_enabled=False,
        llm_base_url="",
        llm_model="",
        llm_api_key="",
        llm_timeout_seconds=30,
    )


def build_test_case(
    branch: str,
    custom_focus_pool: Optional[List[str]] = None,
) -> CaseConfig:
    """构建测试使用的 case。

    Args:
        branch: 关注点分支。
        custom_focus_pool: 自定义关注点池。

    Returns:
        CaseConfig: 测试 case。
    """
    data = load_yaml_file(DATA_FILE)
    return CaseConfig(
        case_id="P999",
        scenario="测试关注点策略",
        answers=["既往拜访过"],
        expected={
            "doctor_type": data["doctor_info"]["type"],
            "doctor_grade": data["doctor_info"]["grade"],
            "trans_info": data["trans_info"],
            "support_info": data["support_info"],
            "focus_title": data["expected_focus_title"],
            "visit_plan_digest": data["doctor_info"],
        },
        focus_strategy=FocusStrategy(
            branch=branch,
            custom_focus_pool=custom_focus_pool or [],
            invalid_input=DEFAULT_INVALID_FOCUS_INPUT,
            fixed_option_label="",
        ),
    )


def test_extract_focus_options() -> None:
    data = load_yaml_file(DATA_FILE)

    options = extract_focus_options(data["question"])

    assert [option["label"] for option in options] == ["A", "B", "C", "D"]
    assert options[1]["text"] == data["expected_focus_title"]


def test_extract_focus_options_inline_question() -> None:
    question = (
        "[QUESTION]此次拜访，您预计医生可能的关注点是什么？"
        "[OPTIONS]A. 人血白蛋白作为血液制品，安全性是否可靠？ "
        "B. 白蛋白的多重生理功能有哪些临床意义？ "
        "C. 低白蛋白血症对ICU患者预后的影响究竟有多严重？ "
        "D. 纠正低白蛋白血症是否能切实改善患者死亡率？[/OPTIONS][/QUESTION]"
    )

    options = extract_focus_options(question)

    assert [option["label"] for option in options] == ["A", "B", "C", "D"]
    assert options[0]["text"] == "人血白蛋白作为血液制品，安全性是否可靠？"


def test_choose_focus_answer_by_branch() -> None:
    data = load_yaml_file(DATA_FILE)
    config = build_test_config()

    f1_answer, f1_decision = choose_focus_answer(
        data["question"],
        build_test_case(FOCUS_BRANCH_F1),
        config,
        random.Random(7),
    )
    f2_option_answer, f2_option_decision = choose_focus_answer(
        data["question"],
        build_test_case(FOCUS_BRANCH_F2_OPTION),
        config,
        random.Random(7),
    )
    f2_custom_answer, f2_custom_decision = choose_focus_answer(
        data["question"],
        build_test_case(FOCUS_BRANCH_F2_CUSTOM, data["custom_focus_pool"]),
        config,
        random.Random(7),
    )
    f3_answer, f3_decision = choose_focus_answer(
        data["question"],
        build_test_case(FOCUS_BRANCH_F3),
        config,
        random.Random(7),
    )

    assert f1_answer == "B"
    assert f1_decision is not None and f1_decision.actual_branch == FOCUS_BRANCH_F1
    assert f2_option_answer in {"A", "C", "D"}
    assert f2_option_decision is not None and f2_option_decision.actual_branch == FOCUS_BRANCH_F2_OPTION
    assert f2_custom_answer in data["custom_focus_pool"]
    assert f2_custom_decision is not None and f2_custom_decision.actual_branch == FOCUS_BRANCH_F2_CUSTOM
    assert f3_answer == DEFAULT_INVALID_FOCUS_INPUT
    assert f3_decision is not None and f3_decision.actual_branch == FOCUS_BRANCH_F3


def test_build_validation_checks_for_f2_custom() -> None:
    data = load_yaml_file(DATA_FILE)
    case = build_test_case(FOCUS_BRANCH_F2_CUSTOM, data["custom_focus_pool"])
    final_data: Dict[str, Any] = {}
    visit_plan: Dict[str, Any] = {
        "visit_plan_digest": {"doctorInfo": data["doctor_info"]},
        "comm_suggest": {
            "transitional_info": [data["trans_info"]],
            "support_info": data["support_info"],
        },
        "focus_point": {
            "items": [
                {
                    "title": data["dynamic_focus_title"],
                    "content": data["dynamic_focus_content"],
                }
            ]
        },
    }
    focus_decisions: List[Dict[str, str]] = [
        {
            "planned_branch": FOCUS_BRANCH_F2_CUSTOM,
            "actual_branch": FOCUS_BRANCH_F2_CUSTOM,
            "custom_input": "医保政策",
        }
    ]

    checks = build_validation_checks(case, final_data, visit_plan, focus_decisions)
    check_map = {check.field_name: check for check in checks}

    assert "focus_title" not in check_map
    assert check_map["focus_title.non_empty"].passed is True
    assert check_map["focus_content.non_empty"].passed is True
    assert "focus_title.not_fixed" not in check_map
    assert "focus_custom_input" not in check_map


def test_choose_focus_answer_for_non_focus_question_with_options() -> None:
    """验证非关注点选项题也可以走通用兜底。"""
    config = build_test_config()
    case = CaseConfig(
        case_id="P998",
        scenario="原始 AI 问询路径",
        answers=["首次拜访"],
        expected={},
        focus_strategy=None,
    )
    question = (
        "[QUESTION]针对医生可能认为“治疗目标不适用”的情况，你计划如何回应或调整沟通策略？"
        "[OPTIONS]A. 准备其他适应症证据 B. 准备具体患者案例 C. 询问医生具体原因[/OPTIONS][/QUESTION]"
    )

    answer, decision = choose_focus_answer(question, case, config, random.Random(7))

    assert answer in {"A", "B", "C"}
    assert decision is None


def test_build_focus_strategy_skip_when_no_fixed_focus() -> None:
    """验证无固定关注点预期时不默认生成 F1 策略。"""
    strategy = build_focus_strategy(
        {
            "case_id": "P014",
            "expected": {
                "focus_title": None,
                "focus_content": None,
            },
        }
    )

    assert strategy is None


def test_choose_focus_answer_prefer_fixed_option_label() -> None:
    """验证 F1 分支可优先使用显式固定选项标签。"""
    data = load_yaml_file(DATA_FILE)
    config = build_test_config()
    case = CaseConfig(
        case_id="P997",
        scenario="显式固定关注点选项",
        answers=["既往拜访过"],
        expected={"focus_title": "一个不会命中选项A的标题"},
        focus_strategy=FocusStrategy(
            branch=FOCUS_BRANCH_F1,
            custom_focus_pool=[],
            invalid_input=DEFAULT_INVALID_FOCUS_INPUT,
            fixed_option_label="A",
        ),
    )

    answer, decision = choose_focus_answer(data["question"], case, config, random.Random(7))

    assert answer == "A"
    assert decision is not None
    assert decision.fixed_option_label == "A"
    assert decision.actual_branch == FOCUS_BRANCH_F1


def test_choose_focus_answer_prefer_llm_match(monkeypatch) -> None:
    """验证开启 LLM 匹配时优先使用模型给出的选项。"""
    data = load_yaml_file(DATA_FILE)
    config = build_test_config()
    config.llm_enabled = True
    config.llm_base_url = "https://mock-llm.test"
    config.llm_model = "mock-model"
    config.llm_api_key = "mock-key"
    case = CaseConfig(
        case_id="P996",
        scenario="LLM 固定关注点匹配",
        answers=["既往拜访过"],
        expected={"focus_title": "主要还是价格太贵，现在DRG医保控费用是主要指标"},
        focus_strategy=FocusStrategy(
            branch=FOCUS_BRANCH_F1,
            custom_focus_pool=[],
            invalid_input=DEFAULT_INVALID_FOCUS_INPUT,
            fixed_option_label="",
        ),
    )

    monkeypatch.setattr(
        "services.focus_service.match_focus_option_by_llm",
        lambda config, question, focus_point: {
            "option_letter": "A",
            "focus_text": "白蛋白价格较高，是否具有成本效益？",
            "is_match_focus_point": True,
        },
    )

    answer, decision = choose_focus_answer(data["question"], case, config, random.Random(7))

    assert answer == "A"
    assert decision is not None
    assert decision.actual_branch == FOCUS_BRANCH_F1
