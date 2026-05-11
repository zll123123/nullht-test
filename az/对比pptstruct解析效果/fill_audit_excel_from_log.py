#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Optional

from openpyxl import load_workbook


DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("ppt解析测试case.xlsx")
DEFAULT_LOG_SOURCE = Path(__file__).resolve().parent
TASK_ID_HEADER = "任务编号"
PAGE_NUMBER_HEADER = "报错页码"
PPT_STRUCT_HEADER = "日志中提取的pptstrut"

TASK_ID_PATTERN = re.compile(r"TaskID:\s*([A-Za-z0-9]+)")
FILE_ID_PATTERN = re.compile(r"getPptxFlow fileId\s*=\s*([^\s]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 Excel 中的任务编号和报错页码，从日志正文提取对应页的 pptStruct 并回填。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
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
        return sorted(path for path in resolved.iterdir() if path.is_file() and path.name.startswith("app_") and path.suffix == ".out")
    raise FileNotFoundError(f"日志路径不存在: {resolved}")


def build_task_to_file_id(log_paths) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for log_path in log_paths:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if "TaskID:" not in line or "getPptxFlow fileId" not in line:
                    continue
                task_match = TASK_ID_PATTERN.search(line)
                file_match = FILE_ID_PATTERN.search(line)
                if not task_match or not file_match:
                    continue
                mapping[task_match.group(1)] = file_match.group(1)
    return mapping


def build_ppt_struct_index(log_paths) -> Dict[str, Dict[str, object]]:
    index: Dict[str, Dict[str, object]] = {}
    for log_path in log_paths:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                stripped = line.lstrip()
                if not stripped.startswith('{"1":'):
                    continue
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                first_page = parsed.get("1")
                if not isinstance(first_page, dict):
                    continue
                first_id = first_page.get("_id")
                if not isinstance(first_id, str) or "_" not in first_id:
                    continue
                file_id = first_id.rpartition("_")[0]
                if file_id:
                    index[file_id] = parsed
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


def main() -> int:
    args = parse_args()
    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    log_paths = list_log_files(DEFAULT_LOG_SOURCE)

    workbook = load_workbook(excel_path)
    sheet = workbook[args.sheet_name] if args.sheet_name else workbook.active
    column_map = find_required_columns(sheet)

    task_to_file_id = build_task_to_file_id(log_paths)
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

        normalized_page_number = normalize_page_number(page_number)
        if not normalized_page_number:
            continue

        file_id = task_to_file_id.get(str(task_id).strip())
        if not file_id:
            overwrite_cell(sheet, row_index, column_map["ppt_struct"], "日志中未定位到该任务编号对应的file_id")
            updated_rows += 1
            continue

        page_map = ppt_struct_index.get(file_id)
        if not isinstance(page_map, dict):
            overwrite_cell(sheet, row_index, column_map["ppt_struct"], "日志中未定位到该任务编号对应的pptStruct")
            updated_rows += 1
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
