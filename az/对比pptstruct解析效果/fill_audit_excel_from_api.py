#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest
import requests
from loguru import logger
from openpyxl import load_workbook


DEFAULT_BASE_URL = "https://dev-api-v3-az-mlr.nullht.com"
DEFAULT_LIST_PATH = "/api/audit/management/list"
DEFAULT_DETAIL_PATH = "/api/audit/management/detail"
DEFAULT_COOKIE = "acw_tc=65859a8117782338948823001ecdd84a9033d1b3213a43dd5480b194094817"
DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("ppt解析测试case.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("fill_audit_excel_from_api.log")
DEFAULT_BEARER_TOKEN = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiIyZmY5ZjY0ZmYwYmZmY2I0MzhkNmQ0MWViZDA4ZTQ5MyIsImRldmljZVR5cGUiOiJERUYiLCJlZmYiOjE3NzgzODQyMDc2NDcsInJuU3RyIjoiR09qeVNUc3F3aENrV2thZlUzaEdZUUZTY3A3cDZOeVoifQ.jCqonRBvyIlUmaVIbSv8cShPpHONmL8mfJm6iMWBlCg"
TIMEOUT_SECONDS = 60
TASK_ID_HEADER = "任务编号"
FILE_NAME_HEADER = "文件名称"
PAGE_NUMBER_HEADER = "报错页码"
POINT_NAME_HEADER = "报错审核点"
REASON_HEADER = "错误原因摘要"

COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://dev-v3-az-mlr.nullht.com",
    "Referer": "https://dev-v3-az-mlr.nullht.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

RUNTIME_CONFIG: Dict[str, Any] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 Excel 中的任务编号调用审核管理接口，并将接口结果回填到 Excel。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
    parser.add_argument(
        "--keep-existing-rows",
        action="store_true",
        help="默认会删除第 2 行之后的旧数据并重写；传入该参数后将只追加，不删除旧数据",
    )
    return parser.parse_args()


def configure_logger() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{message}")
    logger.add(DEFAULT_LOG_PATH, level="INFO", format="{message}", encoding="utf-8", mode="w")


def build_headers(token: str, cookie: str) -> Dict[str, str]:
    authorization = token.strip()
    if not authorization.lower().startswith("bearer "):
        authorization = f"Bearer {authorization}"
    return {
        **COMMON_HEADERS,
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Cookie": cookie,
    }


def init_runtime_config(sheet_name: Optional[str] = None, keep_existing_rows: bool = False) -> None:
    RUNTIME_CONFIG.update(
        {
            "bearer_token": DEFAULT_BEARER_TOKEN,
            "cookie": DEFAULT_COOKIE,
            "base_url": DEFAULT_BASE_URL,
            "sheet_name": sheet_name,
            "keep_existing_rows": keep_existing_rows,
        }
    )


def mask_token(token: str) -> str:
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


def log_request(name: str, url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> None:
    safe_headers = dict(headers)
    safe_headers["Authorization"] = f"Bearer {mask_token(headers['Authorization'].replace('Bearer ', '', 1))}"
    logger.info(f"===== {name} 请求开始 =====")
    logger.info(f"{name} URL: {url}")
    logger.info(f"{name} Headers: {json.dumps(safe_headers, ensure_ascii=False)}")
    logger.info(f"{name} Payload: {json.dumps(payload, ensure_ascii=False)}")


def post_json(session: requests.Session, url: str, payload: Dict[str, Any], headers: Dict[str, str], name: str) -> Dict[str, Any]:
    log_request(name, url, payload, headers)
    response = session.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    logger.info(f"{name} 响应状态码: {response.status_code}")
    logger.info(f"{name} 响应内容: {response.text}")
    logger.info(f"===== {name} 请求结束 =====")
    response.raise_for_status()
    return response.json()


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def find_required_columns(sheet) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for column_index in range(1, sheet.max_column + 1):
        header_map[normalize_header(sheet.cell(1, column_index).value)] = column_index

    required_headers = {
        "task_id": TASK_ID_HEADER,
        "file_name": FILE_NAME_HEADER,
        "page_number": PAGE_NUMBER_HEADER,
        "point_name": POINT_NAME_HEADER,
        "reason": REASON_HEADER,
    }
    columns: Dict[str, int] = {}
    for key, header in required_headers.items():
        column_index = header_map.get(header)
        if not column_index:
            raise AssertionError(f"Excel 缺少表头: {header}")
        columns[key] = column_index
    return columns


def load_seed_rows(sheet, column_map: Dict[str, int]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for row_index in range(2, sheet.max_row + 1):
        task_id = sheet.cell(row_index, column_map["task_id"]).value
        file_name = sheet.cell(row_index, column_map["file_name"]).value
        if not task_id:
            continue
        task_id = str(task_id).strip()
        if task_id in seen:
            continue
        rows.append((task_id, "" if file_name is None else str(file_name)))
        seen.add(task_id)
    return rows


def clear_data_rows(sheet) -> None:
    if sheet.max_row > 1:
        sheet.delete_rows(2, sheet.max_row - 1)


def fetch_list_row(session: requests.Session, base_url: str, task_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    response = post_json(
        session,
        f"{base_url}{DEFAULT_LIST_PATH}",
        {
            "page_num": 1,
            "page_size": 10,
            "status": [],
            "task_id": task_id,
            "sorts": ["CREATED_TIME_DESC"],
        },
        headers,
        "LIST",
    )
    if response.get("code") != "00000":
        raise RuntimeError(f"LIST 返回异常: {response.get('code')} {response.get('msg')}")
    return ((response.get("data") or {}).get("rows") or [None])[0]


def fetch_detail(session: requests.Session, base_url: str, row_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    response = post_json(
        session,
        f"{base_url}{DEFAULT_DETAIL_PATH}",
        {"id": row_id},
        headers,
        "DETAIL",
    )
    if response.get("code") != "00000":
        raise RuntimeError(f"DETAIL 返回异常: {response.get('code')} {response.get('msg')}")
    return response.get("data") or {}


def expand_findings(task_id: str, file_name: str, detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    page_details = detail.get("page_details") or []
    if not page_details:
        return [
            {
                "task_id": task_id,
                "file_name": file_name,
                "page_number": "无",
                "point_name": "无",
                "reason": "detail.page_details 为空",
            }
        ]

    rows: List[Dict[str, Any]] = []
    for page_detail in page_details:
        default_page_number = page_detail.get("page_number")
        for finding in page_detail.get("findings") or []:
            positions = finding.get("position") or []
            page_number = default_page_number
            if positions and positions[0].get("page_number") is not None:
                page_number = positions[0]["page_number"]
            rows.append(
                {
                    "task_id": task_id,
                    "file_name": file_name,
                    "page_number": page_number,
                    "point_name": finding.get("point_name") or "",
                    "reason": finding.get("reason")
                    or ((finding.get("extension") or {}).get("llm_reason"))
                    or "",
                }
            )
    return rows


def write_rows(sheet, rows: List[Dict[str, Any]], column_map: Dict[str, int], keep_existing_rows: bool) -> None:
    start_row = sheet.max_row + 1 if keep_existing_rows and sheet.max_row >= 2 else 2
    for index, row in enumerate(rows, start=start_row):
        sheet.cell(index, column_map["task_id"]).value = row["task_id"]
        sheet.cell(index, column_map["file_name"]).value = row["file_name"]
        sheet.cell(index, column_map["page_number"]).value = row["page_number"]
        sheet.cell(index, column_map["point_name"]).value = row["point_name"]
        sheet.cell(index, column_map["reason"]).value = row["reason"]


def test_fill_audit_excel_from_api() -> None:
    if not RUNTIME_CONFIG:
        configure_logger()
        init_runtime_config()
    assert DEFAULT_BEARER_TOKEN.strip(), "请先在代码常量 DEFAULT_BEARER_TOKEN 中配置 token。"

    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    workbook = load_workbook(excel_path)
    sheet = workbook[RUNTIME_CONFIG["sheet_name"]] if RUNTIME_CONFIG["sheet_name"] else workbook.active
    column_map = find_required_columns(sheet)
    seed_rows = load_seed_rows(sheet, column_map)
    headers = build_headers(RUNTIME_CONFIG["bearer_token"], RUNTIME_CONFIG["cookie"])
    session = requests.Session()

    logger.info(f"Excel 路径: {excel_path}")
    logger.info(f"日志路径: {DEFAULT_LOG_PATH}")
    logger.info(f"待处理任务数: {len(seed_rows)}")

    if not RUNTIME_CONFIG["keep_existing_rows"]:
        clear_data_rows(sheet)

    output_rows: List[Dict[str, Any]] = []
    for task_id, file_name in seed_rows:
        try:
            list_row = fetch_list_row(session, RUNTIME_CONFIG["base_url"], task_id, headers)
            if not list_row:
                output_rows.append(
                    {
                        "task_id": task_id,
                        "file_name": file_name,
                        "page_number": "未查询到审核记录",
                        "point_name": "未查询到审核记录",
                        "reason": "未查询到审核记录",
                    }
                )
                continue
            detail = fetch_detail(session, RUNTIME_CONFIG["base_url"], list_row["id"], headers)
            output_rows.extend(expand_findings(task_id, file_name, detail))
        except Exception as exc:
            output_rows.append(
                {
                    "task_id": task_id,
                    "file_name": file_name,
                    "page_number": f"处理失败: {exc}",
                    "point_name": f"处理失败: {exc}",
                    "reason": f"处理失败: {exc}",
                }
            )

    output_rows.sort(key=lambda item: (item["task_id"], str(item["page_number"]), item["point_name"]))
    write_rows(sheet, output_rows, column_map, RUNTIME_CONFIG["keep_existing_rows"])
    workbook.save(excel_path)

    logger.info(f"Excel 已更新: {excel_path}")
    logger.info(f"写入记录数: {len(output_rows)}")


def main() -> int:
    args = parse_args()
    configure_logger()
    init_runtime_config(args.sheet_name, args.keep_existing_rows)
    return pytest.main(["-s", __file__])


if __name__ == "__main__":
    sys.exit(main())
