"""本地拜访计划审核结果输出，不参与测试报告。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from models.result_model import PlanReviewRecord


def save_plan_review_results(output_file: Path, records: List[PlanReviewRecord]) -> Path:
    """保存本地拜访计划审核结果。

    Args:
        output_file: 审核结果文件路径。
        records: 审核记录列表。

    Returns:
        Path: 实际写入的文件路径。
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"results": [record.to_dict() for record in records]}
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file
