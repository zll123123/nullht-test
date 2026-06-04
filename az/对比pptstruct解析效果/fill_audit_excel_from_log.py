#!/usr/bin/env python3
"""根据日志中的单页 `getPptStruct` 输出，回填 Excel 里的 pptStruct。

脚本作用：
1. 读取 `ppt原文抽取结果_获取pptstruct对比.xlsx`。
2. 从 Excel 中读取：
   - `taskid`
   - `页码`
3. 扫描日志，匹配这类单页日志：
   `[任务编号][getPptStruct] 第 N 页解析成功,解析结果为：{...}`
4. 按 `taskid + 页码` 找到对应页的 `pptStruct`。
5. 将结果写回 Excel 的 `日志中的pptstruct` 列。

默认输入：
1. Excel：脚本同目录下的 `ppt原文抽取结果_获取pptstruct对比.xlsx`
2. 日志：
   - 如果 `DEFAULT_LOG_SOURCE` 指向单个文件，则只读取该文件
   - 如果 `DEFAULT_LOG_SOURCE` 指向目录，则读取目录下所有 `app_*.out`

执行模式：
1. `error-page`
   - 默认模式
   - 只按当前行的 `页码` 提取对应页的 `pptStruct`
2. `full-file`
   - 提取该 `taskid` 下的整份文件所有页
   - 将整份页码到 `pptStruct` 的 JSON 写入当前行

可选参数：
1. `--sheet-name <sheet_name>`
   - 指定工作表，默认使用 active sheet
2. `--mode error-page`
   - 只提取当前页
3. `--mode full-file`
   - 提取整份文件全部页
4. `--skip-non-empty`
   - 如果 `日志中的pptstruct` 已有内容，则跳过不覆盖

调用示例：
1. 默认模式：
   `python fill_audit_excel_from_log.py`
2. 只提取错误页：
   `python fill_audit_excel_from_log.py --mode error-page`
3. 提取整份文件：
   `python fill_audit_excel_from_log.py --mode full-file`
4. 提取整份文件，但跳过已有内容：
   `python fill_audit_excel_from_log.py --mode full-file --skip-non-empty`
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Optional

from openpyxl import load_workbook

DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("ppt原文抽取结果_获取pptstruct对比.xlsx")
DEFAULT_LOG_SOURCE = Path(__file__).resolve().parent
TASK_ID_HEADER = "taskid"
PAGE_NUMBER_HEADER = "页码"
PPT_STRUCT_HEADER = "日志中的pptstruct"

TASK_ID_PATTERN = re.compile(r"TaskID:\s*([A-Za-z0-9]+)")
PAGE_PPT_STRUCT_PATTERN = re.compile(
    r"\[(?P<task_id>[A-Za-z0-9]+)\]\[getPptStruct\]\s*第\s*(?P<page_number>\d+)\s*页解析成功,解析结果为[:：]?\s*(?P<ppt_struct>\{.*\})"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 Excel 中的任务编号，从日志正文提取错误页或整份文件的 pptStruct 并回填。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
    parser.add_argument(
        "--mode",
        choices=("error-page", "full-file"),
        default="error-page",
        help="error-page 提取错误页码对应的 pptStruct；full-file 提取整份文件每一页的 pptStruct",
    )
    parser.add_argument(
        "--skip-non-empty",
        action="store_true",
        help="若 pptStruct 列已有内容则跳过，避免覆盖已写入内容",
    )
    return parser.parse_args()


def normalize_header(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def find_required_columns(sheet) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for column_index in range(1, sheet.max_column + 1):
        header_map[normalize_header(sheet.cell(1, column_index).value)] = column_index

    required = {
        "task_id": TASK_ID_HEADER,
        "page_number": PAGE_NUMBER_HEADER,
        "ppt_struct": PPT_STRUCT_HEADER,
    }
    result: Dict[str, int] = {}
    for key, header in required.items():
        column_index = header_map.get(normalize_header(header))
        if not column_index:
            raise AssertionError(f"Excel 缺少表头: {header}")
        result[key] = column_index
    return result


def list_log_files(log_source: Path):
    resolved = log_source.expanduser().resolve()
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        return sorted(path for path in resolved.iterdir() if path.is_file() and path.name.startswith("my-pod") and path.suffix == ".log")
    raise FileNotFoundError(f"日志路径不存在: {resolved}")


def build_ppt_struct_index(log_paths) -> Dict[str, Dict[str, object]]:
    index: Dict[str, Dict[str, object]] = {}
    for log_path in log_paths:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if "[getPptStruct]" not in line or "解析结果为" not in line:
                    continue
                match = PAGE_PPT_STRUCT_PATTERN.search(line)
                if not match:
                    continue
                try:
                    parsed = json.loads(match.group("ppt_struct"))
                except json.JSONDecodeError:
                    continue
                task_id = match.group("task_id")
                page_number = match.group("page_number")
                index.setdefault(task_id, {})[page_number] = parsed
    return index


def normalize_page_number(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def overwrite_cell(sheet, row_index: int, column_index: int, value: str) -> None:
    cell = sheet.cell(row_index, column_index)
    if cell.value not in (None, ""):
        cell.value = None
    cell.value = value


def build_full_file_ppt_struct(page_map: Dict[str, object]) -> str:
    ordered_pages = sorted(page_map.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0]))
    ordered_dict = {page_number: page_object for page_number, page_object in ordered_pages}
    return json.dumps(ordered_dict, ensure_ascii=False)


def main() -> int:
    args = parse_args()
    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    log_paths = list_log_files(DEFAULT_LOG_SOURCE)

    workbook = load_workbook(excel_path)
    sheet = workbook[args.sheet_name] if args.sheet_name else workbook.active
    column_map = find_required_columns(sheet)

    ppt_struct_index = build_ppt_struct_index(log_paths)
    updated_rows = 0

    for row_index in range(2, sheet.max_row + 1):
        task_id = sheet.cell(row_index, column_map["task_id"]).value
        page_number = sheet.cell(row_index, column_map["page_number"]).value
        existing_value = sheet.cell(row_index, column_map["ppt_struct"]).value

        if args.skip_non_empty and existing_value:
            continue
        if not task_id:
            continue

        normalized_task_id = str(task_id).strip()
        page_map = ppt_struct_index.get(normalized_task_id)
        if not isinstance(page_map, dict):
            overwrite_cell(sheet, row_index, column_map["ppt_struct"], "日志中未定位到该任务编号对应的pptStruct")
            updated_rows += 1
            continue

        if args.mode == "full-file":
            overwrite_cell(sheet, row_index, column_map["ppt_struct"], build_full_file_ppt_struct(page_map))
            updated_rows += 1
            continue

        normalized_page_number = normalize_page_number(page_number)
        if not normalized_page_number:
            continue

        page_object = page_map.get(normalized_page_number)
        if page_object is None:
            overwrite_cell(sheet, row_index, column_map["ppt_struct"], "日志中未定位到该任务编号对应错误页码的pptStruct")
            updated_rows += 1
            continue

        overwrite_cell(sheet, row_index, column_map["ppt_struct"], json.dumps(page_object, ensure_ascii=False))
        updated_rows += 1

    workbook.save(excel_path)
    print(f"Excel 已更新: {excel_path}")
    print(f"写入记录数: {updated_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
