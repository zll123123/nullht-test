"""拜访计划字段提取器。"""

from __future__ import annotations

from typing import Any, Dict, List


def extract_visit_plan(final_data: Dict[str, Any], detail_data: Dict[str, Any]) -> Dict[str, Any]:
    """提取拜访计划。"""
    if isinstance(detail_data.get("visit_plan"), dict):
        return detail_data["visit_plan"]
    if isinstance(final_data.get("visit_plan"), dict):
        return final_data["visit_plan"]
    return {}


def join_literature_field(literatures: List[Dict[str, Any]], field_name: str) -> str:
    """拼接文献字段。"""
    return "\n".join(str(item.get(field_name) or "").strip() for item in literatures if item.get(field_name))


def get_transitional_info(visit_plan: Dict[str, Any]) -> str:
    """提取第一条传递信息。"""
    transitional_info = ((visit_plan.get("comm_suggest") or {}).get("transitional_info") or [])
    return str(transitional_info[0]) if transitional_info else ""


def get_focus_titles(final_data: Dict[str, Any], visit_plan: Dict[str, Any]) -> str:
    """提取关注点标题。"""
    items = ((visit_plan.get("focus_point") or {}).get("items") or [])
    titles = [str(item.get("title") or "").strip() for item in items if item.get("title")]
    if titles:
        return "\n".join(titles)
    phase3_focus_point = ((final_data.get("phase3_data") or {}).get("focus_point") or {})
    return str(phase3_focus_point.get("title") or "")


def get_focus_contents(final_data: Dict[str, Any], visit_plan: Dict[str, Any]) -> str:
    """提取关注点内容。"""
    items = ((visit_plan.get("focus_point") or {}).get("items") or [])
    contents = [str(item.get("content") or "").strip() for item in items if item.get("content")]
    if contents:
        return "\n".join(contents)
    phase3_focus_point = ((final_data.get("phase3_data") or {}).get("focus_point") or {})
    return str(phase3_focus_point.get("content") or "")


def get_focus_literature_titles(visit_plan: Dict[str, Any]) -> str:
    """提取关注点文献标题。"""
    return join_literature_field(((visit_plan.get("focus_point") or {}).get("literatures") or []), "title")


def get_focus_literature_summaries(visit_plan: Dict[str, Any]) -> str:
    """提取关注点文献摘要。"""
    return join_literature_field(((visit_plan.get("focus_point") or {}).get("literatures") or []), "research_summary")


def get_comm_literature_titles(visit_plan: Dict[str, Any]) -> str:
    """提取沟通文献标题。"""
    return join_literature_field(((visit_plan.get("comm_suggest") or {}).get("literatures") or []), "title")


def get_comm_literature_summaries(visit_plan: Dict[str, Any]) -> str:
    """提取沟通文献摘要。"""
    return join_literature_field(((visit_plan.get("comm_suggest") or {}).get("literatures") or []), "research_summary")


def get_recommended_materials(visit_plan: Dict[str, Any]) -> str:
    """提取推荐材料。"""
    return join_literature_field(visit_plan.get("literatures") or [], "title")
