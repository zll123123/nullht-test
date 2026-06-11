"""LLM 对话评估服务，负责渲染评估 prompt 并保存模型判断结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from clients.llm_client import call_llm_text, normalize_llm_json
from config.app_config import AppConfig
from config.settings import PROMPTS_DIR
from models.result_model import ConversationEvaluation, ConversationStep
from utils.api_timing import ApiCallCollector


def is_conversation_evaluation_enabled(config: AppConfig) -> bool:
    """判断是否启用对话评估。

    Args:
        config: 运行配置。

    Returns:
        bool: 是否启用。
    """
    return bool(
        config.llm_enabled
        and config.llm_conversation_eval_enabled
        and config.llm_base_url
        and config.llm_model
        and config.llm_api_key
        and config.llm_conversation_eval_prompt_file
    )


def is_first_visit_scenario(scenario: str) -> bool:
    """判断当前场景是否为首次拜访路径。

    Args:
        scenario: 用例场景描述。

    Returns:
        bool: 是否为首次拜访路径。
    """
    return "首次拜访" in scenario


def build_non_first_visit_evaluation() -> ConversationEvaluation:
    """构建非首次拜访路径的固定评估结果。

    Args:
        None

    Returns:
        ConversationEvaluation: 固定 false 结果。
    """
    return ConversationEvaluation(
        enabled=True,
        result={
            "has_first_visit_history_question": False,
            "skip_reason": "非首次拜访路径，跳过LLM评估",
        },
    )


def resolve_prompt_file(config: AppConfig) -> Path:
    """解析对话评估 prompt 文件路径。

    Args:
        config: 运行配置。

    Returns:
        Path: prompt 文件路径。
    """
    prompt_file = Path(config.llm_conversation_eval_prompt_file)
    if prompt_file.is_absolute():
        return prompt_file
    return PROMPTS_DIR / prompt_file


def format_conversation_steps(steps: List[ConversationStep]) -> str:
    """格式化完整对话记录。

    Args:
        steps: 对话步骤列表。

    Returns:
        str: 可注入 prompt 的对话文本。
    """
    lines: List[str] = []
    for index, step in enumerate(steps, start=1):
        response = step.response or {}
        lines.extend(
            [
                f"第{index}轮",
                f"系统提问：{step.question}",
                f"测试回答：{step.answer}",
                f"is_complete：{response.get('is_complete')}",
                f"can_stop：{response.get('can_stop')}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def render_prompt(template: str, values: Dict[str, str]) -> str:
    """渲染 prompt 模板。

    Args:
        template: prompt 模板。
        values: 模板变量。

    Returns:
        str: 渲染后的 prompt。
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def parse_evaluation_content(content: str) -> Dict[str, Any]:
    """解析评估结果。

    Args:
        content: LLM 返回内容。

    Returns:
        Dict[str, Any]: JSON 结果或原始文本包装。
    """
    try:
        return normalize_llm_json(content)
    except Exception:
        return {"raw_text": content}


def evaluate_conversation_by_llm(
    config: AppConfig,
    case_id: str,
    scenario: str,
    session_id: str,
    steps: List[ConversationStep],
    final_data: Dict[str, Any],
    api_collector: ApiCallCollector | None = None,
) -> ConversationEvaluation:
    """调用 LLM 评估完整对话。

    Args:
        config: 运行配置。
        case_id: 用例编号。
        scenario: 用例场景。
        session_id: 会话 ID。
        steps: 对话步骤。
        final_data: 最后一轮响应 data。
        api_collector: 接口结果收集器。

    Returns:
        ConversationEvaluation: 对话评估结果。
    """
    if not is_conversation_evaluation_enabled(config):
        return ConversationEvaluation(enabled=False)
    if not is_first_visit_scenario(scenario):
        return build_non_first_visit_evaluation()
    try:
        prompt_template = resolve_prompt_file(config).read_text(encoding="utf-8")
        prompt = render_prompt(
            prompt_template,
            {
                "case_id": case_id,
                "scenario": scenario,
                "session_id": session_id,
                "conversation": format_conversation_steps(steps),
                "final_data": json.dumps(final_data, ensure_ascii=False, indent=2),
            },
        )
        content = call_llm_text(
            config=config,
            prompt=prompt,
            api_name="evaluate_conversation_by_llm",
            api_collector=api_collector,
            session_id=session_id,
            case_id=case_id,
        )
        return ConversationEvaluation(enabled=True, result=parse_evaluation_content(content))
    except Exception as exc:
        return ConversationEvaluation(enabled=True, error=str(exc))
