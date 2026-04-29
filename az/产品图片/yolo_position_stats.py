#!/usr/bin/env python3
"""
扫描 PPT 预览图目录，调用 YOLO 接口，并将每个文件每一页的 position 个数写入 Excel。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl import load_workbook


DEFAULT_API_URL = (
    "https://operate-img-product-service-slorbyhwzl.cn-shanghai.fcapp.run/predict/base64"
)
DEFAULT_INPUT_DIR = Path("/Users/layla.zhang/测试用例/测试材料/az/产品图片预览图")
DEFAULT_OUTPUT_FILE = Path(
    "/Users/layla.zhang/workspace/nullht-test/az/产品图片/yolo_position_stats.xlsx"
)
CONFIDENCE_THRESHOLD = 0.7
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统计测试材料目录下每个文件夹、每一页图片返回的 position 个数，并写入 Excel"
    )
    parser.add_argument(
        "--mode",
        default="generate",
        choices=["generate", "audit"],
        help="generate: 调接口生成统计表；audit: 比对已完善 Excel 中 position_count 和 expect_number",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help=f"测试材料根目录，默认：{DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--input-excel",
        default=str(Path("/Users/layla.zhang/workspace/nullht-test/az/产品图片/test_one_folder.xlsx")),
        help="audit 模式下输入的已完善 Excel 路径",
    )
    parser.add_argument(
        "--output",
        help="输出路径。generate 和 audit 模式默认值不同",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"接口地址，默认：{DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--model-type",
        default="logo",
        choices=["logo", "company"],
        help="接口 model_type 参数",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="接口请求超时时间（秒）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并发请求数，默认：8，建议不要超过 16",
    )
    return parser.parse_args()


def get_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).expanduser()
    if args.mode == "audit":
        return Path(args.input_excel).expanduser()
    return DEFAULT_OUTPUT_FILE


def extract_page_no(image_path: Path) -> int:
    match = re.search(r"(\d+)", image_path.stem)
    return int(match.group(1)) if match else 0


def split_folder_name(folder_name: str) -> tuple[str, str]:
    if "-" not in folder_name:
        return folder_name, ""
    detailed_id, task_id = folder_name.rsplit("-", 1)
    return detailed_id, task_id


def iter_task_folders(root_dir: Path) -> list[Path]:
    if not root_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在：{root_dir}")

    root_images = [
        path
        for path in root_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if root_images:
        return [root_dir]

    folders = [path for path in root_dir.iterdir() if path.is_dir() and not path.name.startswith(".")]
    return sorted(folders, key=lambda item: item.name)


def iter_images(folder_path: Path) -> list[Path]:
    images = [
        path
        for path in folder_path.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(images, key=lambda item: (extract_page_no(item), item.name))


def image_to_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def call_api(image_path: Path, api_url: str, model_type: str, timeout: int) -> dict:
    payload = {
        "base64_image": image_to_base64(image_path),
        "model_type": model_type,
    }
    response = requests.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def build_detail_row(folder_path: Path, image_path: Path, api_result: dict) -> dict:
    folder_name = folder_path.name
    detailed_id, task_id = split_folder_name(folder_name)
    detections = api_result.get("detections", [])
    confident_detections = [
        item for item in detections if float(item.get("may", 0)) >= CONFIDENCE_THRESHOLD
    ]
    position_count = len(confident_detections)
    return {
        "folder_name": folder_name,
        "detailed_id": detailed_id,
        "task_id": task_id,
        "page_no": extract_page_no(image_path),
        "position_count": position_count,
        "detection_count": len(confident_detections),
        "status": "success",
        "error_message": "",
        "raw_result": json.dumps(api_result, ensure_ascii=False),
    }


def build_error_row(folder_path: Path, image_path: Path, error_message: str) -> dict:
    folder_name = folder_path.name
    detailed_id, task_id = split_folder_name(folder_name)
    return {
        "folder_name": folder_name,
        "detailed_id": detailed_id,
        "task_id": task_id,
        "page_no": extract_page_no(image_path),
        "position_count": 0,
        "detection_count": 0,
        "status": "failed",
        "error_message": error_message,
        "raw_result": "",
    }


def process_image(
    folder_path: Path,
    image_path: Path,
    api_url: str,
    model_type: str,
    timeout: int,
) -> dict:
    try:
        api_result = call_api(
            image_path=image_path,
            api_url=api_url,
            model_type=model_type,
            timeout=timeout,
        )
        return build_detail_row(folder_path, image_path, api_result)
    except Exception as exc:  # noqa: BLE001
        return build_error_row(folder_path, image_path, str(exc))


def autosize_worksheet(worksheet) -> None:
    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_length = max(max_length, len(value))
        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 80)


def write_excel(detail_rows: list[dict], summary_rows: list[dict], output_path: Path) -> None:
    workbook = Workbook()

    detail_sheet = workbook.active
    detail_sheet.title = "明细"
    detail_headers = [
        "folder_name",
        "detailed_id",
        "task_id",
        "page_no",
        "position_count",
        "status",
        "error_message",
        "raw_result",
    ]
    detail_sheet.append(detail_headers)
    for cell in detail_sheet[1]:
        cell.font = Font(bold=True)
    for row in detail_rows:
        detail_sheet.append([row[header] for header in detail_headers])
    autosize_worksheet(detail_sheet)

    summary_sheet = workbook.create_sheet("汇总")
    summary_headers = [
        "folder_name",
        "detailed_id",
        "task_id",
        "page_count",
        "success_page_count",
        "failed_page_count",
        "total_position_count",
        "total_detection_count",
    ]
    summary_sheet.append(summary_headers)
    for cell in summary_sheet[1]:
        cell.font = Font(bold=True)
    for row in summary_rows:
        summary_sheet.append([row[header] for header in summary_headers])
    autosize_worksheet(summary_sheet)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)


def normalize_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def calculate_page_metrics(expect_number: int, position_count: int) -> tuple[int, int, int]:
    """Calculate TP, FP, and FN for one page.

    Args:
        expect_number: Expected detection count.
        position_count: Actual detection count.

    Returns:
        A tuple of (tp, fp, fn).
    """
    true_positive = min(expect_number, position_count)
    false_positive = max(position_count - expect_number, 0)
    false_negative = max(expect_number - position_count, 0)
    return true_positive, false_positive, false_negative


def audit_position_counts(input_excel: Path, output_path: Path) -> tuple[int, int, int]:
    workbook = load_workbook(input_excel)
    if "明细" not in workbook.sheetnames:
        raise ValueError("输入 Excel 缺少 '明细' sheet")

    detail_sheet = workbook["明细"]
    rows = detail_sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        raise ValueError("明细 sheet 为空")

    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "detailed_id", "task_id", "page_no", "position_count", "expect_number"]
    missing_headers = [header for header in required_headers if header not in header_map]
    if missing_headers:
        raise ValueError(f"明细 sheet 缺少列: {', '.join(missing_headers)}")

    mismatch_rows: list[dict[str, Any]] = []
    summary_map: dict[str, dict[str, Any]] = {}
    total_true_positive = 0
    total_false_positive = 0
    total_false_negative = 0

    for row in rows:
        folder_name = row[header_map["folder_name"]]
        if folder_name in (None, ""):
            continue
        detailed_id = row[header_map["detailed_id"]]
        task_id = row[header_map["task_id"]]
        page_no = row[header_map["page_no"]]
        position_count = normalize_count(row[header_map["position_count"]])
        expect_number = normalize_count(row[header_map["expect_number"]])

        if position_count is None and expect_number is None:
            continue

        normalized_position_count = position_count or 0
        normalized_expect_number = expect_number or 0
        true_positive, false_positive, false_negative = calculate_page_metrics(
            expect_number=normalized_expect_number,
            position_count=normalized_position_count,
        )
        total_true_positive += true_positive
        total_false_positive += false_positive
        total_false_negative += false_negative

        if position_count != expect_number:
            if normalized_position_count > normalized_expect_number:
                failure_type = "误报"
            else:
                failure_type = "漏报"
            mismatch_row = {
                "folder_name": folder_name,
                "detailed_id": detailed_id,
                "task_id": task_id,
                "page_no": page_no,
                "expect_number": expect_number,
                "position_count": position_count,
                "difference": (position_count or 0) - (expect_number or 0),
                "failure_type": failure_type,
            }
            mismatch_rows.append(mismatch_row)

            if folder_name not in summary_map:
                summary_map[folder_name] = {
                    "folder_name": folder_name,
                    "detailed_id": detailed_id,
                    "task_id": task_id,
                    "failed_page_count": 0,
                    "failed_page_nos": [],
                    "expected_error_count": 0,
                    "actual_error_count": 0,
                }
            summary_map[folder_name]["failed_page_count"] += 1
            summary_map[folder_name]["failed_page_nos"].append(page_no)
            summary_map[folder_name]["expected_error_count"] += normalized_expect_number
            summary_map[folder_name]["actual_error_count"] += normalized_position_count

    summary_rows = sorted(summary_map.values(), key=lambda item: item["folder_name"])
    mismatch_rows.sort(key=lambda item: (item["folder_name"], int(item["page_no"])))

    for sheet_name in ("汇总", "不一致明细", "审计汇总", "审计结果"):
        if sheet_name in workbook.sheetnames:
            del workbook[sheet_name]

    total_page_count = 0
    total_file_names: set[str] = set()
    for row in detail_sheet.iter_rows(min_row=2, values_only=True):
        folder_name = row[header_map["folder_name"]]
        if folder_name in (None, ""):
            continue
        total_page_count += 1
        total_file_names.add(str(folder_name))

    failed_page_count = len(mismatch_rows)
    mismatch_file_count = len(summary_rows)
    total_file_count = len(total_file_names)
    pass_rate = 1 - (failed_page_count / total_page_count) if total_page_count else 0
    audit_pass_ratio = 1 - (mismatch_file_count / total_file_count) if total_file_count else 0
    recall = (
        total_true_positive / (total_true_positive + total_false_negative)
        if (total_true_positive + total_false_negative)
        else 0
    )
    precision = (
        total_true_positive / (total_true_positive + total_false_positive)
        if (total_true_positive + total_false_positive)
        else 0
    )
    f1_score = (recall + precision) / 2 if (recall or precision) else 0

    result_sheet = workbook.create_sheet("审计结果")
    metric_headers = ["metric", "value"]
    result_sheet.append(metric_headers)
    for cell in result_sheet[1]:
        cell.font = Font(bold=True)
    metric_rows = [
        ("总文件数", total_file_count),
        ("总文件页数", total_page_count),
        ("不一致文件数", mismatch_file_count),
        ("失败页数", failed_page_count),
        ("TP", total_true_positive),
        ("FP", total_false_positive),
        ("FN", total_false_negative),
        ("召回率", recall),
        ("精确率", precision),
        ("F1score", f1_score),
        ("通过率", pass_rate),
        ("审核通过比例", audit_pass_ratio),
    ]
    for metric_row in metric_rows:
        result_sheet.append(metric_row)

    result_sheet.append(())
    summary_headers = [
        "folder_name",
        "detailed_id",
        "task_id",
        "failed_page_count",
        "failed_page_nos",
        "expected_error_count",
        "actual_error_count",
    ]
    result_sheet.append(summary_headers)
    summary_header_row_index = result_sheet.max_row
    for cell in result_sheet[summary_header_row_index]:
        cell.font = Font(bold=True)
    for item in summary_rows:
        item["failed_page_nos"] = ", ".join(str(page_no) for page_no in sorted(item["failed_page_nos"]))
        result_sheet.append([item[header] for header in summary_headers])

    result_sheet.append(())
    mismatch_headers = [
        "folder_name",
        "detailed_id",
        "task_id",
        "page_no",
        "failure_type",
        "expect_number",
        "position_count",
        "difference",
    ]
    result_sheet.append(mismatch_headers)
    mismatch_header_row_index = result_sheet.max_row
    for cell in result_sheet[mismatch_header_row_index]:
        cell.font = Font(bold=True)
    for item in mismatch_rows:
        result_sheet.append([item[header] for header in mismatch_headers])
    autosize_worksheet(result_sheet)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    return mismatch_file_count, failed_page_count, len(mismatch_rows)


def main() -> int:
    args = parse_args()
    output_path = get_output_path(args)

    if args.mode == "audit":
        input_excel = Path(args.input_excel).expanduser()
        try:
            file_count, failed_page_count, mismatch_count = audit_position_counts(
                input_excel=input_excel,
                output_path=output_path,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"audit 失败：{exc}", file=sys.stderr)
            return 1

        print(f"审计结果已写入：{output_path.resolve()}")
        print(
            f"完成：不一致文件数={file_count}，失败页数={failed_page_count}，"
            f"不一致记录数={mismatch_count}"
        )
        return 0

    input_dir = Path(args.input_dir).expanduser()

    try:
        task_folders = iter_task_folders(input_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not task_folders:
        print("未找到任何任务文件夹。", file=sys.stderr)
        return 1

    if args.workers < 1:
        print("并发数必须大于等于 1。", file=sys.stderr)
        return 1

    detail_rows: list[dict] = []
    tasks: list[tuple[Path, Path]] = []
    folder_image_counts: dict[str, int] = {}

    for folder_path in task_folders:
        images = iter_images(folder_path)
        if not images:
            continue
        folder_image_counts[folder_path.name] = len(images)
        for image_path in images:
            tasks.append((folder_path, image_path))

    if not tasks:
        print("没有生成任何结果，请检查目录中的图片文件。", file=sys.stderr)
        return 1

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(
                process_image,
                folder_path,
                image_path,
                args.api_url,
                args.model_type,
                args.timeout,
            ): (folder_path, image_path)
            for folder_path, image_path in tasks
        }
        for future in as_completed(future_map):
            row = future.result()
            detail_rows.append(row)
            if row["status"] == "success":
                print(
                    f"{row['folder_name']} | page {row['page_no']} | "
                    f"position_count={row['position_count']} | "
                    f"detection_count={row['detection_count']}"
                )
            else:
                print(
                    f"{row['folder_name']} | page {row['page_no']} | "
                    f"failed={row['error_message']}",
                    file=sys.stderr,
                )

    detail_rows.sort(key=lambda row: (row["folder_name"], row["page_no"]))

    summary_rows: list[dict] = []
    for folder_path in task_folders:
        folder_rows = [row for row in detail_rows if row["folder_name"] == folder_path.name]
        if not folder_rows:
            continue
        detailed_id, task_id = split_folder_name(folder_path.name)
        summary_rows.append(
            {
                "folder_name": folder_path.name,
                "detailed_id": detailed_id,
                "task_id": task_id,
                "page_count": folder_image_counts[folder_path.name],
                "success_page_count": sum(1 for row in folder_rows if row["status"] == "success"),
                "failed_page_count": sum(1 for row in folder_rows if row["status"] == "failed"),
                "total_position_count": sum(row["position_count"] for row in folder_rows),
                "total_detection_count": sum(row["detection_count"] for row in folder_rows),
            }
        )

    summary_rows.sort(key=lambda row: row["folder_name"])

    write_excel(detail_rows, summary_rows, output_path)
    print(f"\nExcel 已写入：{output_path.resolve()}")
    print(
        f"完成：任务文件夹={len(summary_rows)}，总页数={len(detail_rows)}，"
        f"成功页数={sum(row['success_page_count'] for row in summary_rows)}，"
        f"失败页数={sum(row['failed_page_count'] for row in summary_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
