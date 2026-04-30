from pathlib import Path
from utils.common_assertions import CommonAssertion
from utils.yaml_loader import load_yaml_file

DATA_FILE = Path(__file__).parent / "data" / "test_common_assertions.yaml"


def test_assert_text_equal() -> None:
    """验证文本相等断言。"""
    data = load_yaml_file(DATA_FILE)

    for case in data["cases"][:3]:
        result = CommonAssertion.assert_text_equal(case["expected"], case["actual"])

        assert result.passed is case["passed"]


def test_assert_text_similarity() -> None:
    """验证文本相似度断言。"""
    data = load_yaml_file(DATA_FILE)

    for case in data["cases"][3:]:
        result = CommonAssertion.assert_text_similarity(
            case["expected"],
            case["actual"],
            case["threshold"],
        )

        assert result.passed is case["passed"]


def test_assert_text_contains() -> None:
    result = CommonAssertion.assert_text_contains(
        "1. ALBIOS研究支持早期使用白蛋白\n2. 白蛋白可降低并发症风险",
        "ALBIOS研究支持早期使用白蛋白\n白蛋白可降低并发症风险",
    )

    assert result.passed is True
