from pathlib import Path
from validators.assertions import CommonAssertion
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


def test_assert_text_contains_ignore_format_marks() -> None:
    """验证包含断言可忽略项目符号、引用标记和空白差异。"""
    expected = (
        "● 无论是否是重症患者，人工胶体的这些安全隐患都始终存在，长期使用更是不利于患者的综合获益。\n"
        "● 《2021 SSC脓毒症与脓毒症休克管理国际指南》1：对成人脓毒症或脓毒性休克患者，不推荐使用羟乙基淀粉进行复苏；"
        "对成人脓毒症或脓毒性休克患者，不推荐使用明胶进行复苏\n"
        "● 近年来国际上卫生组织的建议越来越倾向于限制人工胶体的使用，这也反映了他们对人工胶体安全性的担忧。"
    )
    actual = (
        "无论是否是重症患者，人工胶体的这些安全隐患都始终存在，长期使用更是不利于患者的综合获益。\n"
        "《2021 SSC脓毒症与脓毒症休克管理国际指南》{1} 对成人脓毒症或脓毒性休克患者，不推荐使用羟乙基淀粉进行复苏；"
        "对成人脓毒症或脓毒性休克患者，不推荐使用明胶进行复苏\n"
        "    近年来国际上卫生组织的建议越来越倾向于限制人工胶体的使用，这也反映了他们对人工胶体安全性的担忧。"
    )

    result = CommonAssertion.assert_text_contains(expected, actual)

    assert result.passed is True


def test_assert_text_list_exact_ignore_number_noise() -> None:
    """验证文献列表可忽略编号噪音后逐条匹配。"""
    expected = (
        "1. . Caironi et al. N Engl J Med 2014; 370: 1412‒21\n"
        "2. Jean-Louis Vincent, et al. Crit Care Med. 2004 Oct;3 (10):2029-38.\n"
        "3. Dubois et al. Crit Care Med 2006 34: 2536-40"
    )
    actual = (
        "1. Caironi et al. N Engl J Med 2014; 370: 1412‒21\n"
        "2. Jean-Louis Vincent, et al. Crit Care Med. 2004 Oct;3 (10):2029-38.\n"
        "3. Dubois et al. Crit Care Med 2006 34: 2536-40"
    )

    result = CommonAssertion.assert_text_list_exact(expected, actual)

    assert result.passed is True


def test_assert_text_contains_ignore_tail_references() -> None:
    """验证行尾引用编号不影响包含断言。"""
    expected = "未显著增加严重脓毒症患者肾功能障碍风险（p=0.9206）1,2"
    actual = "未显著增加严重脓毒症患者肾功能障碍风险（p=0.9206）{1}{2}"

    result = CommonAssertion.assert_text_contains(expected, actual)

    assert result.passed is True
