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
<<<<<<< HEAD
DEFAULT_COOKIE = "acw_tc=65859a8117768449866044408ecdfc24e8492e4fba52def90885e51aef2080"
DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("新ppt解析-测试case-uat.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("fill_audit_excel_from_api.log")
DEFAULT_BEARER_TOKEN = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiIyZmY5ZjY0ZmYwYmZmY2I0MzhkNmQ0MWViZDA4ZTQ5MyIsImRldmljZVR5cGUiOiJERUYiLCJlZmYiOjE3NzY4NTMwNjY3OTksInJuU3RyIjoiUU5hdDl3OURmS3E1U3pXZkRFTFhjRUYwUzdPZTE3Sk0ifQ.SIvKIDSpWEYfn5goz_9q9tX4mY6Rp_v--Ir9NIU30Iw"
TIMEOUT_SECONDS = 60
TASK_ID_HEADER = "任务编号"
FILE_NAME_HEADER = "文件名称"
PAGE_NUMBER_HEADER = "报错页码"
POINT_NAME_HEADER = "报错审核点"
REASON_HEADER = "审核错误摘要"
=======
DEFAULT_COOKIE = "acw_tc=65859a8117767939047432241ece10cbbe6c8df7b6521d2132dd0aba97e07f"
DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("audit_result.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("fill_audit_excel_from_api.log")
DEFAULT_BEARER_TOKEN = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiIyZmY5ZjY0ZmYwYmZmY2I0MzhkNmQ0MWViZDA4ZTQ5MyIsImRldmljZVR5cGUiOiJERUYiLCJlZmYiOjE3NzY4NTMwNjY3OTksInJuU3RyIjoiUU5hdDl3OURmS3E1U3pXZkRFTFhjRUYwUzdPZTE3Sk0ifQ.SIvKIDSpWEYfn5goz_9q9tX4mY6Rp_v--Ir9NIU30Iw"
TIMEOUT_SECONDS = 60
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc

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

<<<<<<< HEAD
RUNTIME_CONFIG: Dict[str, Any] = {
    "bearer_token": DEFAULT_BEARER_TOKEN,
    "cookie": DEFAULT_COOKIE,
    "base_url": DEFAULT_BASE_URL,
    "sheet_name": None,
}
=======
RUNTIME_CONFIG: Dict[str, Any] = {}
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 Excel 中的任务编号调用审核管理接口，并将接口结果回填到 Excel。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
<<<<<<< HEAD
=======
    parser.add_argument(
        "--keep-existing-rows",
        action="store_true",
        help="默认会删除第 2 行之后的旧数据并重写；传入该参数后将只追加，不删除旧数据",
    )
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
    return parser.parse_args()


def configure_logger() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{message}")
    logger.add(DEFAULT_LOG_PATH, level="INFO", format="{message}", encoding="utf-8", mode="w")


def build_headers(token: str, cookie: str) -> Dict[str, str]:
<<<<<<< HEAD
    normalized_token = token.strip()
    if normalized_token.startswith("Bearer "):
        normalized_token = normalized_token[len("Bearer "):].strip()
    return {
        **COMMON_HEADERS,
        "Authorization": f"Bearer {normalized_token}",
=======
    return {
        **COMMON_HEADERS,
        "Authorization": f"Bearer {token}",
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
        "Content-Type": "application/json",
        "Cookie": cookie,
    }


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


<<<<<<< HEAD
def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def find_required_columns(sheet) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for column_index in range(1, sheet.max_column + 1):
        header_map[normalize_header(sheet.cell(1, column_index).value)] = column_index

    required = {
        "task_id": TASK_ID_HEADER,
        "file_name": FILE_NAME_HEADER,
        "page_number": PAGE_NUMBER_HEADER,
        "point_name": POINT_NAME_HEADER,
        "reason": REASON_HEADER,
    }
    columns: Dict[str, int] = {}
    for key, header in required.items():
        column_index = header_map.get(normalize_header(header))
        if not column_index:
            raise AssertionError(f"Excel 缺少表头: {header}")
        columns[key] = column_index
    return columns


def load_seed_rows(sheet, task_id_column: int, file_name_column: int) -> List[Tuple[int, str, str]]:
    rows: List[Tuple[int, str, str]] = []
    for row_index in range(2, sheet.max_row + 1):
        task_id = sheet.cell(row_index, task_id_column).value
        file_name = sheet.cell(row_index, file_name_column).value
        if not task_id:
            continue
        task_id = str(task_id).strip()
        rows.append((row_index, task_id, "" if file_name is None else str(file_name)))
    return rows


=======
def load_seed_rows(sheet) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for row_index in range(2, sheet.max_row + 1):
        task_id = sheet.cell(row_index, 1).value
        file_name = sheet.cell(row_index, 2).value
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


>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
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


<<<<<<< HEAD
def write_finding_to_row(sheet, row_index: int, column_map: Dict[str, int], finding: Dict[str, Any]) -> None:
    sheet.cell(row_index, column_map["task_id"]).value = finding["task_id"]
    sheet.cell(row_index, column_map["file_name"]).value = finding["file_name"]
    sheet.cell(row_index, column_map["page_number"]).value = finding["page_number"]
    sheet.cell(row_index, column_map["point_name"]).value = finding["point_name"]
    sheet.cell(row_index, column_map["reason"]).value = finding["reason"]


def write_findings_for_task(sheet, row_index: int, column_map: Dict[str, int], findings: List[Dict[str, Any]]) -> int:
    if not findings:
        findings = [
            {
                "page_number": "无",
                "point_name": "无",
                "reason": "未返回错误明细",
            }
        ]

    write_finding_to_row(sheet, row_index, column_map, findings[0])

    inserted_rows = 0
    for finding in findings[1:]:
        insert_at = row_index + inserted_rows + 1
        sheet.insert_rows(insert_at)
        write_finding_to_row(sheet, insert_at, column_map, finding)
        inserted_rows += 1
    return len(findings)


def test_fill_audit_excel_from_api() -> None:
=======
def write_rows(sheet, rows: List[Dict[str, Any]], keep_existing_rows: bool) -> None:
    start_row = sheet.max_row + 1 if keep_existing_rows and sheet.max_row >= 2 else 2
    for index, row in enumerate(rows, start=start_row):
        sheet.cell(index, 1).value = row["task_id"]
        sheet.cell(index, 2).value = row["file_name"]
        sheet.cell(index, 3).value = row["page_number"]
        sheet.cell(index, 4).value = row["point_name"]
        sheet.cell(index, 5).value = row["reason"]


def test_fill_audit_excel_from_api() -> None:
    assert RUNTIME_CONFIG, "未初始化运行参数，请使用 python 脚本方式启动。"
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
    assert DEFAULT_BEARER_TOKEN.strip(), "请先在代码常量 DEFAULT_BEARER_TOKEN 中配置 token。"

    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    workbook = load_workbook(excel_path)
    sheet = workbook[RUNTIME_CONFIG["sheet_name"]] if RUNTIME_CONFIG["sheet_name"] else workbook.active
<<<<<<< HEAD
    column_map = find_required_columns(sheet)
    seed_rows = load_seed_rows(sheet, column_map["task_id"], column_map["file_name"])
=======
    seed_rows = load_seed_rows(sheet)
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
    headers = build_headers(RUNTIME_CONFIG["bearer_token"], RUNTIME_CONFIG["cookie"])
    session = requests.Session()

    logger.info(f"Excel 路径: {excel_path}")
    logger.info(f"日志路径: {DEFAULT_LOG_PATH}")
    logger.info(f"待处理任务数: {len(seed_rows)}")

<<<<<<< HEAD
    updated_rows = 0
    row_results: List[Tuple[int, List[Dict[str, Any]]]] = []
    for row_index, task_id, file_name in seed_rows:
        try:
            list_row = fetch_list_row(session, RUNTIME_CONFIG["base_url"], task_id, headers)
            if not list_row:
                findings = [
=======
    if not RUNTIME_CONFIG["keep_existing_rows"]:
        clear_data_rows(sheet)

    output_rows: List[Dict[str, Any]] = []
    for task_id, file_name in seed_rows:
        try:
            list_row = fetch_list_row(session, RUNTIME_CONFIG["base_url"], task_id, headers)
            if not list_row:
                output_rows.append(
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
                    {
                        "task_id": task_id,
                        "file_name": file_name,
                        "page_number": "未查询到审核记录",
                        "point_name": "未查询到审核记录",
                        "reason": "未查询到审核记录",
                    }
<<<<<<< HEAD
                ]
            else:
                detail = fetch_detail(session, RUNTIME_CONFIG["base_url"], list_row["id"], headers)
                findings = expand_findings(task_id, file_name, detail)
        except Exception as exc:
            findings = [
=======
                )
                continue
            detail = fetch_detail(session, RUNTIME_CONFIG["base_url"], list_row["id"], headers)
            output_rows.extend(expand_findings(task_id, file_name, detail))
        except Exception as exc:
            output_rows.append(
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
                {
                    "task_id": task_id,
                    "file_name": file_name,
                    "page_number": f"处理失败: {exc}",
                    "point_name": f"处理失败: {exc}",
                    "reason": f"处理失败: {exc}",
                }
<<<<<<< HEAD
            ]
        row_results.append((row_index, findings))

    for row_index, findings in reversed(row_results):
        updated_rows += write_findings_for_task(sheet, row_index, column_map, findings)

    workbook.save(excel_path)

    logger.info(f"Excel 已更新: {excel_path}")
    logger.info(f"写入记录数: {updated_rows}")
=======
            )

    output_rows.sort(key=lambda item: (item["task_id"], str(item["page_number"]), item["point_name"]))
    write_rows(sheet, output_rows, RUNTIME_CONFIG["keep_existing_rows"])
    workbook.save(excel_path)

    logger.info(f"Excel 已更新: {excel_path}")
    logger.info(f"写入记录数: {len(output_rows)}")
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc


def main() -> int:
    args = parse_args()
    configure_logger()
<<<<<<< HEAD
    RUNTIME_CONFIG["sheet_name"] = args.sheet_name
=======
    RUNTIME_CONFIG.update(
        {
            "bearer_token": DEFAULT_BEARER_TOKEN,
            "cookie": DEFAULT_COOKIE,
            "base_url": DEFAULT_BASE_URL,
            "sheet_name": args.sheet_name,
            "keep_existing_rows": args.keep_existing_rows,
        }
    )
>>>>>>> 81cd2cebdc210178499d453638cca3cf255aaddc
    return pytest.main(["-s", __file__])


if __name__ == "__main__":
    sys.exit(main())
