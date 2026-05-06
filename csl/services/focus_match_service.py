"""关注点匹配服务。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from clients.focus_match_client import call_focus_match_llm
from config.app_config import AppConfig

FOCUS_MATCH_PROMPT_TEMPLATE = """# 角色定义
你是一位擅长医药代表拜访场景语义理解与结构化提取的助手。

你的任务是根据“上一轮生成的问题及选项文本”和“固定关注点内容”，完成两件事：

1. 从题目选项中找到一个与固定关注点最语义匹配的选项；
2. 判断该选项是否与固定关注点内容是同一个意思。

# 核心目标
请基于输入内容，输出以下 3 个字段：

1. `option_letter`：最匹配的选项字母（A/B/C/D）
2. `focus_text`：该选项的原文
3. `is_match_focus_point`：是否与固定关注点是同一个意思

# 输入信息
- 【上一轮问题及选项】：{next_question}
- 【固定关注点内容】：{focus_point}

# 提取逻辑
1. 从 `next_question` 中识别 A/B/C/D 四个选项文本。
2. 将每个选项与 `focus_point` 进行语义比对，找到最匹配的选项。
3. 输出结果字段：
   - `option_letter` = 该选项字母
   - `focus_text` = 该选项原文
   - `is_match_focus_point`：
       - 如果语义一致，输出 `true`
       - 如果语义相关但不一致，输出 `false`
4. 如果没有任何选项与 `focus_point` 有明确语义对应，则：
   - `option_letter` = `""`
   - `focus_text` = `""`
   - `is_match_focus_point` = `""`

# 输出要求
- 输出必须是严格合法的 JSON
- 不输出解释、分析、备注
- 不改写选项原文
"""


def build_focus_match_prompt(question: str, focus_point: str) -> str:
    """构建关注点匹配提示词。

    Args:
        question: 当前问题和选项。
        focus_point: 固定关注点。

    Returns:
        str: 完整提示词。
    """
    return FOCUS_MATCH_PROMPT_TEMPLATE.format(next_question=question, focus_point=focus_point)


def match_focus_option_by_llm(
    config: AppConfig,
    question: str,
    focus_point: str,
) -> Optional[Dict[str, Any]]:
    """通过大模型匹配固定关注点对应选项。

    Args:
        config: 运行配置。
        question: 当前问题。
        focus_point: 固定关注点。

    Returns:
        Optional[Dict[str, Any]]: 匹配结果；不可用时返回 None。
    """
    if not config.llm_enabled:
        return None
    if not config.llm_base_url or not config.llm_model or not config.llm_api_key:
        return None
    return call_focus_match_llm(config, build_focus_match_prompt(question, focus_point))
