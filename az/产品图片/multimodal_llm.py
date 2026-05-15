#!/usr/bin/env python3
"""用于产品图片核验的多模态 LLM 客户端。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from env_utils import load_local_env


CURRENT_DIR = Path(__file__).resolve().parent
load_local_env(CURRENT_DIR / ".env")

DEFAULT_LLM_MODEL_NAME = "qwen2.5-vl-72b-instruct"
DEFAULT_LLM_MODEL_VERSION = "latest"
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:25222"
DEFAULT_LLM_SERVICE_NAME = "nhtai_service_azure_gpt"
DEFAULT_LLM_HOST_HEADER = "prod.nhtai-service.internal.nullht.com"
DEFAULT_TIMEOUT_SECONDS = 120
MULTIMODAL_SYSTEM_PROMPT = """
你是一个专业的品牌图片比对助手。第一张图片是YOLO检测框的精确裁剪区域，第二张图片是该区域扩展后的上下文区域，后续图片是该品牌下的官方参考素材（logo、产品包装、品牌吉祥物、卡通形象等）。

                    请严格对比裁剪区域与每张参考素材，从以下维度判断是否为同一品牌内容：
                    1. 品牌名称文字是否一致（如中文品牌名、英文/拼音标识）
                    2. Logo图形、图标形状是否一致
                    3. 产品包装的形状、颜色搭配是否一致
                    4. 品牌吉祥物、卡通IP形象是否一致（包括造型、配色、服饰细节等）
                    5. 是否存在明确的、可辨识的品牌特征对应

                    分析建议：
                    - 优先参考第一张图片（精确裁剪）进行品牌特征的精确比对
                    - 第二张图片（扩展上下文）提供更多周边信息，有助于确认场景完整性和品牌关联性
                    - 当第一张图片区域过小或模糊时，结合第二张图片的上下文信息综合判断

                    重要：品牌吉祥物和卡通形象是品牌的核心资产之一，如果裁剪区域中的卡通形象与参考素材中的卡通形象在造型、配色、细节上高度一致，应判定为匹配。

                    以下情况不算匹配（即使视觉上有一定相似性）：
                    - 仅颜色相近但无品牌文字、logo或吉祥物对应
                    - 仅形状类似但品牌标识完全不同
                    - 纹理、背景等局部相似但核心品牌元素缺失
                    - 裁剪区域模糊不清、无法辨识具体内容

                    请给出匹配度评分(0-100)：
                    - 80-100：裁剪区域与参考素材高度一致，品牌标识清晰可辨
                    - 50-79：存在部分相似元素，但不足以确认为同一品牌
                    - 0-49：不匹配或无法判断

                    严格按照以下JSON格式输出，不要包含其他内容：
                    { "score": 匹配度评分(0-100的整数), "reason": "简要说明判断依据" }
""".strip()


def extract_score(response_text: str) -> int | None:
    """从模型返回文本中提取分数。

    参数:
        response_text: 模型原始返回文本。

    返回:
        解析后的分数；解析失败时返回 None。
    """
    try:
        payload = json.loads(response_text)
        score = payload.get("score")
        return int(score) if score is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        match = re.search(r"(\d{1,3})", response_text)
        return int(match.group(1)) if match else None


def build_multimodal_input(
    cropped_image_data_url: str,
    padded_image_data_url: str,
    reference_images: list[str],
) -> list[dict[str, Any]]:
    """构建 NHTAI 多模态请求中的用户消息内容。

    参数:
        cropped_image_data_url: 裁剪后检测区域图片的 data URL。
        padded_image_data_url: 扩展 padding 后区域图片的 data URL。
        reference_images: 参考图片的 data URL 列表。

    返回:
        请求内容列表。
    """
    input_content: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": cropped_image_data_url,
        }
    ]
    input_content.append(
        {
            "type": "image_url",
            "image_url": padded_image_data_url,
        }
    )
    for reference_image in reference_images:
        input_content.append(
            {
                "type": "image_url",
                "image_url": reference_image,
            }
        )
    return input_content


def build_nhtai_payload(
    cropped_image_data_url: str,
    padded_image_data_url: str,
    reference_images: list[str],
    llm_model: str,
) -> dict[str, Any]:
    """构建 NHTAI 请求体。

    参数:
        cropped_image_data_url: 裁剪后检测区域图片的 data URL。
        padded_image_data_url: 扩展 padding 后区域图片的 data URL。
        reference_images: 参考图片的 data URL 列表。
        llm_model: 模型名称。

    返回:
        请求 JSON 数据。
    """
    user_content = build_multimodal_input(
        cropped_image_data_url,
        padded_image_data_url,
        reference_images,
    )
    return {
        "service": DEFAULT_LLM_SERVICE_NAME,
        "payload": {
            "model_name": llm_model,
            "model_version": DEFAULT_LLM_MODEL_VERSION,
            "request_params": {
                "json": {
                    "messages": [
                        {
                            "role": "system",
                            "content": MULTIMODAL_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": user_content,
                        },
                    ],
                    "stream": False,
                    "response_format": {"type": "json_object"},
                },
                "timeout": DEFAULT_TIMEOUT_SECONDS,
            },
            "return_cost": True,
        },
    }


def extract_nhtai_content(response_json: dict[str, Any]) -> str:
    """从 NHTAI 响应 JSON 中提取模型文本内容。

    参数:
        response_json: 已解析的响应体。

    返回:
        模型回复文本。

    异常:
        ValueError: 当响应结构不符合预期时抛出。
    """
    choices = response_json.get("data", {}).get("choices", [])
    if not choices:
        raise ValueError(f"NHTAI 返回中缺少 choices: {response_json}")
    message = choices[0].get("message", {})
    content = message.get("content")
    if content is None:
        raise ValueError(f"NHTAI 返回中缺少 message.content: {response_json}")
    return str(content)


def call_multimodal_llm(
    cropped_image_data_url: str,
    padded_image_data_url: str,
    reference_images: list[str],
    llm_model: str,
) -> str:
    """调用 NHTAI 多模态接口并返回原始文本结果。

    参数:
        cropped_image_data_url: 裁剪后的检测区域图片 data URL。
        padded_image_data_url: 扩展 padding 后区域图片 data URL。
        reference_images: 参考图片 data URL 列表。
        llm_model: 模型名称。

    返回:
        模型原始输出文本。
    """
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/")
    host_header = os.getenv("OPENAI_HOST_HEADER", DEFAULT_LLM_HOST_HEADER).strip()
    payload = build_nhtai_payload(
        cropped_image_data_url,
        padded_image_data_url,
        reference_images,
        llm_model,
    )
    headers = {"Content-Type": "application/json"}
    if host_header:
        headers["Host"] = host_header
    response = requests.post(
        f"{base_url}/{DEFAULT_LLM_SERVICE_NAME}",
        json=payload,
        headers=headers,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_nhtai_content(response.json())


def multimodal_verify(
    cropped_image_data_url: str,
    padded_image_data_url: str,
    reference_images: list[str],
    llm_model: str,
    llm_score_threshold: int,
) -> bool:
    """使用 NHTAI 多模态模型校验单个检测结果。

    参数:
        cropped_image_data_url: 裁剪后的检测区域图片。
        padded_image_data_url: 扩展 padding 后区域图片。
        reference_images: 同一 cls 下的参考图片列表。
        llm_model: 多模态模型名称。
        llm_score_threshold: 允许通过的最低相似度分数。

    返回:
        分数大于等于阈值时返回 True，否则返回 False。
    """
    response_text = call_multimodal_llm(
        cropped_image_data_url=cropped_image_data_url,
        padded_image_data_url=padded_image_data_url,
        reference_images=reference_images,
        llm_model=llm_model,
    )
    score = extract_score(response_text)
    return score is not None and score >= llm_score_threshold
