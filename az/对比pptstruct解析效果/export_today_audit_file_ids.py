#!/usr/bin/env python3
"""导出审核任务中的 file_id 小工具。"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "audit_file_ids.json"
DEFAULT_LOG_PATH = SCRIPT_DIR / "export_today_audit_file_ids.log"
DEFAULT_BASE_URL = "https://dev-api-v3-az-mlr.nullht.com"
DEFAULT_LIST_PATH = "/api/audit/management/list"
DEFAULT_DETAIL_PATH = "/api/audit/management/detail"
DEFAULT_ORIGIN = "https://dev-v3-az-mlr.nullht.com"
DEFAULT_TIMEOUT_SECONDS = 30
SUCCESS_CODE = "00000"


@dataclass(frozen=True)
class AuditTask:
    """审核任务摘要。

    Attributes:
        row_id: 列表接口返回的记录主键。
        task_id: 任务编号。
        audit_id: 审核编号。
        file_name: 文件名。
        created_time: 创建时间戳，毫秒。
    """

    row_id: str
    task_id: str
    audit_id: str
    file_name: str
    created_time: int


@dataclass(frozen=True)
class AuditFileRecord:
    """审核文件结果。

    Attributes:
        task_id: 任务编号。
        audit_id: 审核编号。
        file_name: 文件名。
        file_id: 原始文件 ID。
        pdf_file_id: PDF 文件 ID。
        created_time: 创建时间，格式化字符串。
    """

    task_id: str
    audit_id: str
    file_name: str
    file_id: str
    pdf_file_id: str
    created_time: str


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 命令行参数对象。
    """

    parser = argparse.ArgumentParser(description="从审核管理接口导出指定日期的 file_id。")
    parser.add_argument("--token", required=True, help="Bearer Token，支持带或不带 Bearer 前缀")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="筛选日期，格式 YYYY-MM-DD")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="接口域名")
    parser.add_argument("--page-size", type=int, default=100, help="列表分页大小")
    parser.add_argument("--max-pages", type=int, default=20, help="最多拉取多少页列表")
    parser.add_argument("--creator", help="可选，按创建人筛选")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="输出 JSON 文件路径")
    return parser.parse_args()


def setup_logger() -> None:
    """初始化日志配置。"""

    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{message}")
    logger.add(DEFAULT_LOG_PATH, level="INFO", format="{message}", encoding="utf-8", mode="w")


def normalize_token(token: str) -> str:
    """标准化 Bearer Token。

    Args:
        token: 原始 token 文本。

    Returns:
        str: 不带 Bearer 前缀的 token。
    """

    normalized = token.strip()
    if normalized.lower().startswith("bearer "):
        return normalized[7:].strip()
    return normalized


def build_headers(token: str) -> Dict[str, str]:
    """构建请求头。

    Args:
        token: Bearer Token。

    Returns:
        Dict[str, str]: HTTP 请求头。
    """

    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {normalize_token(token)}",
        "Content-Type": "application/json",
        "Origin": DEFAULT_ORIGIN,
        "Referer": f"{DEFAULT_ORIGIN}/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
    }


def post_json(
    session: requests.Session,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """发送 POST JSON 请求。

    Args:
        session: 请求会话。
        url: 请求地址。
        headers: 请求头。
        payload: JSON 请求体。

    Returns:
        Dict[str, Any]: 响应 JSON。
    """

    logger.info(f"POST {url}")
    logger.info(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    response = session.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT_SECONDS)
    logger.info(f"Status: {response.status_code}")
    response.raise_for_status()
    return response.json()


def parse_task(row: Dict[str, Any]) -> Optional[AuditTask]:
    """将列表记录转换为任务对象。

    Args:
        row: 列表接口单条记录。

    Returns:
        Optional[AuditTask]: 解析成功返回任务，否则返回 None。
    """

    row_id = str(row.get("id") or "").strip()
    task_id = str(row.get("task_id") or "").strip()
    audit_id = str(row.get("audit_id") or "").strip()
    file_name = str(row.get("file_name") or "").strip()
    created_time = int(row.get("created_time") or 0)
    if not all([row_id, task_id, audit_id, file_name, created_time]):
        return None
    return AuditTask(row_id, task_id, audit_id, file_name, created_time)


def is_same_day(timestamp_ms: int, target_date: str) -> bool:
    """判断时间戳是否属于目标日期。

    Args:
        timestamp_ms: 毫秒时间戳。
        target_date: 日期字符串，格式 YYYY-MM-DD。

    Returns:
        bool: 是否属于该日期。
    """

    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d") == target_date


def fetch_tasks(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    target_date: str,
    page_size: int,
    max_pages: int,
    creator: Optional[str],
) -> List[AuditTask]:
    """拉取指定日期的审核任务。

    Args:
        session: 请求会话。
        base_url: 接口域名。
        headers: 请求头。
        target_date: 目标日期。
        page_size: 每页数量。
        max_pages: 最大页数。
        creator: 创建人筛选条件。

    Returns:
        List[AuditTask]: 命中的审核任务。
    """

    tasks: List[AuditTask] = []
    for page_num in range(1, max_pages + 1):
        payload = build_list_payload(page_num, page_size, creator)
        response = post_json(session, f"{base_url}{DEFAULT_LIST_PATH}", headers, payload)
        rows = unwrap_rows(response)
        if not rows:
            break
        page_tasks = filter_tasks_by_date(rows, target_date)
        tasks.extend(page_tasks)
        if should_stop_paging(rows, target_date):
            break
    return tasks


def build_list_payload(page_num: int, page_size: int, creator: Optional[str]) -> Dict[str, Any]:
    """构建列表查询参数。

    Args:
        page_num: 页码。
        page_size: 分页大小。
        creator: 创建人筛选条件。

    Returns:
        Dict[str, Any]: 列表接口参数。
    """

    payload: Dict[str, Any] = {
        "page_num": page_num,
        "page_size": page_size,
        "sorts": ["CREATED_TIME_DESC"],
        "status": [],
    }
    if creator:
        payload["creator"] = creator
    return payload


def unwrap_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析列表接口响应。

    Args:
        response: 接口响应。

    Returns:
        List[Dict[str, Any]]: 记录列表。
    """

    code = str(response.get("code") or "")
    if code != SUCCESS_CODE:
        raise RuntimeError(f"列表接口失败: {code} {response.get('msg')}")
    data = response.get("data") or {}
    return list(data.get("rows") or [])


def filter_tasks_by_date(rows: List[Dict[str, Any]], target_date: str) -> List[AuditTask]:
    """过滤目标日期内的任务。

    Args:
        rows: 原始列表记录。
        target_date: 目标日期。

    Returns:
        List[AuditTask]: 过滤后的任务。
    """

    tasks: List[AuditTask] = []
    for row in rows:
        task = parse_task(row)
        if task and is_same_day(task.created_time, target_date):
            tasks.append(task)
    return tasks


def should_stop_paging(rows: List[Dict[str, Any]], target_date: str) -> bool:
    """判断是否可以停止翻页。

    Args:
        rows: 当前页数据。
        target_date: 目标日期。

    Returns:
        bool: 若当前页已经出现更早日期，则停止。
    """

    timestamps = [int(row.get("created_time") or 0) for row in rows if row.get("created_time")]
    if not timestamps:
        return True
    oldest_date = datetime.fromtimestamp(min(timestamps) / 1000).strftime("%Y-%m-%d")
    return oldest_date < target_date


def fetch_detail(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    row_id: str,
) -> Dict[str, Any]:
    """查询单条任务详情。

    Args:
        session: 请求会话。
        base_url: 接口域名。
        headers: 请求头。
        row_id: 列表记录 ID。

    Returns:
        Dict[str, Any]: 详情数据。
    """

    response = post_json(
        session,
        f"{base_url}{DEFAULT_DETAIL_PATH}",
        headers,
        {"id": row_id},
    )
    code = str(response.get("code") or "")
    if code != SUCCESS_CODE:
        raise RuntimeError(f"详情接口失败: {code} {response.get('msg')}")
    return dict(response.get("data") or {})


def build_record(task: AuditTask, detail: Dict[str, Any]) -> AuditFileRecord:
    """将详情数据整理为输出记录。

    Args:
        task: 审核任务。
        detail: 详情接口数据。

    Returns:
        AuditFileRecord: 输出记录。
    """

    return AuditFileRecord(
        task_id=task.task_id,
        audit_id=task.audit_id,
        file_name=task.file_name,
        file_id=str(detail.get("file_id") or ""),
        pdf_file_id=str(detail.get("pdf_file_id") or ""),
        created_time=datetime.fromtimestamp(task.created_time / 1000).strftime("%Y-%m-%d %H:%M:%S"),
    )


def write_output(output_path: Path, records: List[AuditFileRecord]) -> None:
    """写出 JSON 结果。

    Args:
        output_path: 输出文件路径。
        records: 结果记录列表。
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.__dict__ for record in records]
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(records: List[AuditFileRecord]) -> None:
    """输出简要结果到控制台。

    Args:
        records: 结果记录列表。
    """

    for record in records:
        logger.info(f"{record.task_id}\t{record.file_id}\t{record.file_name}")


def main() -> int:
    """程序入口。

    Returns:
        int: 退出码。
    """

    args = parse_args()
    setup_logger()
    headers = build_headers(args.token)
    session = requests.Session()
    tasks = fetch_tasks(
        session=session,
        base_url=args.base_url,
        headers=headers,
        target_date=args.date,
        page_size=args.page_size,
        max_pages=args.max_pages,
        creator=args.creator,
    )
    records = [build_record(task, fetch_detail(session, args.base_url, headers, task.row_id)) for task in tasks]
    write_output(args.output.expanduser().resolve(), records)
    print_summary(records)
    logger.info(f"共导出 {len(records)} 条记录")
    logger.info(f"输出文件: {args.output.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
