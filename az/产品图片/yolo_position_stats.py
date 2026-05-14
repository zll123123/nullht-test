#!/usr/bin/env python3
"""
扫描 PPT 预览图目录，调用 YOLO 接口，并将每个文件每一页的 position 个数写入 Excel。
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.styles import Font
from PIL import Image

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from env_utils import load_local_env
from multimodal_llm import DEFAULT_LLM_MODEL_NAME, call_multimodal_llm, extract_score

load_local_env(CURRENT_DIR / ".env")

DEFAULT_API_URL = (
    "https://operate-img-product-service-slorbyhwzl.cn-shanghai.fcapp.run/predict/base64"
)
DEFAULT_INPUT_DIR = Path("/Users/layla.zhang/测试用例/测试材料/az/产品图片预览图")
DEFAULT_RESULT_EXCEL = Path(
    os.getenv(
        "PRODUCT_IMAGE_RESULT_EXCEL",
        "/Users/layla.zhang/workspace/nullht-test/az/产品图片/结果统计.xlsx",
    )
)
CONFIDENCE_THRESHOLD = 0.7
REFERENCE_IMAGE_DIR = Path("/Users/layla.zhang/workspace/nullht-test/az/产品图片/logo")
TMP_CROP_DIR = Path(
    os.getenv(
        "PRODUCT_IMAGE_TMP_DIR",
        "/Users/layla.zhang/workspace/nullht-test/az/产品图片/tmp",
    )
)
LLM_SCORE_THRESHOLD = 80
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}
_reference_image_cache: dict[str, list[str]] = {}
_reference_image_path_cache: dict[str, list[str]] = {}
LLM_SAVE_BATCH_SIZE = 50
LLM_MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_COMPRESS_QUALITY = 50
INITIAL_COMPRESS_QUALITY = 85
COMPRESS_ATTEMPTS = 6
INITIAL_RESIZE_SCALE = 0.95
COMPRESS_STEP = 0.08
MAX_IMAGE_EDGE = 2048


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统计测试材料目录下每个文件夹、每一页图片返回的 position 个数，并写入 Excel"
    )
    parser.add_argument(
        "--mode",
        default="generate",
        choices=[
            "generate",
            "audit",
            "rerun",
            "rerun-rate-limit",
            "rerun-large-image",
            "rerun-from-raw",
            "rerun-retryable",
        ],
        help="generate: 生成新统计表；audit: 重算审计；rerun: 重跑 YOLO+LLM 并覆盖现有 Excel 结果列；rerun-rate-limit: 串行重跑限流页；rerun-large-image: 串行重跑图片过大页；rerun-from-raw: 基于现有raw_result重跑裁剪和LLM；rerun-retryable: 串行重跑限流页和图片过大页",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help=f"测试材料根目录，默认：{DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--input-excel",
        default=str(DEFAULT_RESULT_EXCEL),
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
    parser.add_argument(
        "--reference-dir",
        default=str(REFERENCE_IMAGE_DIR),
        help=f"按 cls 存放参考图片的根目录，默认：{REFERENCE_IMAGE_DIR}",
    )
    parser.add_argument(
        "--llm-model",
        default=os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL_NAME),
        help="多模态模型名，默认优先取 OPENAI_MODEL，否则使用 qwen2.5-vl-72b-instruct",
    )
    parser.add_argument(
        "--llm-score-threshold",
        type=int,
        default=LLM_SCORE_THRESHOLD,
        help="多模态相似度阈值，默认：80",
    )
    return parser.parse_args()


def get_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).expanduser()
    if args.mode in {"audit", "rerun", "generate"}:
        return Path(args.input_excel).expanduser()
    return DEFAULT_RESULT_EXCEL


def extract_page_no(image_path: Path) -> int:
    match = re.search(r"(\d+)", image_path.stem)
    return int(match.group(1)) if match else 0


def split_folder_name(folder_name: str) -> tuple[str, str]:
    if "-" not in folder_name:
        return folder_name, ""
    detailed_id, task_id = folder_name.rsplit("-", 1)
    return detailed_id, task_id


def load_expect_number_map(input_excel: Path) -> dict[tuple[str, int], int | None]:
    """从现有 Excel 读取每页的 expect_number。"""
    if not input_excel.exists():
        return {}
    workbook = load_workbook(input_excel, read_only=True)
    if "明细" not in workbook.sheetnames:
        return {}
    detail_sheet = workbook["明细"]
    rows = detail_sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        return {}
    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "page_no", "expect_number"]
    if any(header not in header_map for header in required_headers):
        return {}
    expect_map: dict[tuple[str, int], int | None] = {}
    for row in rows:
        folder_name = row[header_map["folder_name"]]
        page_no = normalize_count(row[header_map["page_no"]])
        expect_number = normalize_count(row[header_map["expect_number"]])
        if folder_name in (None, "") or page_no is None:
            continue
        expect_map[(str(folder_name), page_no)] = expect_number
    return expect_map


def load_rate_limited_pages(input_excel: Path) -> list[tuple[str, int]]:
    """读取 Excel 中疑似限流的页。"""
    workbook = load_workbook(input_excel, read_only=True)
    if "明细" not in workbook.sheetnames:
        return []
    detail_sheet = workbook["明细"]
    rows = detail_sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        return []
    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "page_no"]
    if any(header not in header_map for header in required_headers):
        return []
    pages: list[tuple[str, int]] = []
    patterns = (
        "throttling_error",
        "ratelimiterror",
        "you exceeded your current quota",
        "LiteLLM Retried",
        "\"code\": \"429\"",
        "\"code\":\"429\"",
        "'code': '429'",
        "limit_requests",
    )
    for row in rows:
        folder_name = row[header_map["folder_name"]]
        page_no = normalize_count(row[header_map["page_no"]])
        error_message = ""
        raw_result = ""
        if "error_message" in header_map and row[header_map["error_message"]] not in (None, ""):
            error_message = str(row[header_map["error_message"]])
        if "raw_result" in header_map and row[header_map["raw_result"]] not in (None, ""):
            raw_result = str(row[header_map["raw_result"]])
        if folder_name in (None, "") or page_no is None:
            continue
        raw_text = "\n".join([error_message, raw_result])
        if any(pattern in raw_text for pattern in patterns):
            pages.append((str(folder_name), page_no))
    return pages


def load_retryable_pages(input_excel: Path) -> list[tuple[str, int]]:
    """读取 Excel 中可重跑的失败页。

    包含两类：
    1. 429 / 限流类错误
    2. 图片过大类错误
    """
    workbook = load_workbook(input_excel, read_only=True)
    if "明细" not in workbook.sheetnames:
        return []
    detail_sheet = workbook["明细"]
    rows = detail_sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        return []
    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "page_no"]
    if any(header not in header_map for header in required_headers):
        return []

    retryable_patterns = (
        "throttling_error",
        "ratelimiterror",
        "you exceeded your current quota",
        "litellm retried",
        "\"code\": \"429\"",
        "\"code\":\"429\"",
        "'code': '429'",
        "limit_requests",
        "multimodal file size is too large",
        "file size is too large",
        "image too large",
        "payload too large",
    )
    pages: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        folder_name = row[header_map["folder_name"]]
        page_no = normalize_count(row[header_map["page_no"]])
        if folder_name in (None, "") or page_no is None:
            continue

        error_message = ""
        raw_result = ""
        llm_result = ""
        status = ""
        if "error_message" in header_map and row[header_map["error_message"]] not in (None, ""):
            error_message = str(row[header_map["error_message"]])
        if "raw_result" in header_map and row[header_map["raw_result"]] not in (None, ""):
            raw_result = str(row[header_map["raw_result"]])
        if "llm_result" in header_map and row[header_map["llm_result"]] not in (None, ""):
            llm_result = str(row[header_map["llm_result"]])
        if "status" in header_map and row[header_map["status"]] not in (None, ""):
            status = str(row[header_map["status"]]).lower()

        raw_text = "\n".join([status, error_message, raw_result, llm_result]).lower()
        key = (str(folder_name), page_no)
        if any(pattern in raw_text for pattern in retryable_patterns) and key not in seen:
            seen.add(key)
            pages.append(key)
    return pages


def load_large_image_pages(input_excel: Path) -> list[tuple[str, int]]:
    """读取 Excel 中图片过大的失败页。"""
    workbook = load_workbook(input_excel, read_only=True)
    if "明细" not in workbook.sheetnames:
        return []
    detail_sheet = workbook["明细"]
    rows = detail_sheet.iter_rows(values_only=True)
    headers = next(rows, None)
    if not headers:
        return []
    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "page_no"]
    if any(header not in header_map for header in required_headers):
        return []

    large_image_patterns = (
        "multimodal file size is too large",
        "file size is too large",
        "image too large",
        "payload too large",
    )
    pages: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        folder_name = row[header_map["folder_name"]]
        page_no = normalize_count(row[header_map["page_no"]])
        if folder_name in (None, "") or page_no is None:
            continue

        error_message = ""
        raw_result = ""
        llm_result = ""
        status = ""
        if "error_message" in header_map and row[header_map["error_message"]] not in (None, ""):
            error_message = str(row[header_map["error_message"]])
        if "raw_result" in header_map and row[header_map["raw_result"]] not in (None, ""):
            raw_result = str(row[header_map["raw_result"]])
        if "llm_result" in header_map and row[header_map["llm_result"]] not in (None, ""):
            llm_result = str(row[header_map["llm_result"]])
        if "status" in header_map and row[header_map["status"]] not in (None, ""):
            status = str(row[header_map["status"]]).lower()

        raw_text = "\n".join([status, error_message, raw_result, llm_result]).lower()
        key = (str(folder_name), page_no)
        if any(pattern in raw_text for pattern in large_image_patterns) and key not in seen:
            seen.add(key)
            pages.append(key)
    return pages


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


def find_page_image(input_dir: Path, folder_name: str, page_no: int) -> Path | None:
    """按文件夹名和页码定位原始页图。

    Args:
        input_dir: 测试材料根目录。
        folder_name: 任务文件夹名。
        page_no: 页码。

    Returns:
        命中的图片路径，未找到则返回 None。
    """
    folder_path = input_dir / folder_name
    if not folder_path.is_dir():
        return None
    for image_path in iter_images(folder_path):
        if extract_page_no(image_path) == page_no:
            return image_path
    return None


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


def image_bytes_to_data_url(image_bytes: bytes, mime_type: str) -> str:
    """将图片字节转换为 data URL。

    参数:
        image_bytes: 原始图片字节。
        mime_type: 图片的 MIME 类型。

    返回:
        base64 格式的 data URL 字符串。
    """
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def is_image_file(file_path: Path) -> bool:
    """判断文件是否为支持的图片格式。

    参数:
        file_path: 待检查的文件路径。

    返回:
        后缀受支持时返回 True，否则返回 False。
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def guess_mime_type(file_path: Path) -> str:
    """根据文件后缀推断图片 MIME 类型。

    参数:
        file_path: 图片文件路径。

    返回:
        MIME 类型字符串。
    """
    suffix = file_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return f"image/{suffix.lstrip('.')}"


def load_reference_images(reference_dir: Path, cls: str) -> list[str]:
    """加载并缓存指定 YOLO 类别的参考图片。

    参数:
        reference_dir: 参考图片根目录。
        cls: YOLO 类别名。

    返回:
        参考图片 data URL 列表。
    """
    cache_key = f"{reference_dir.resolve()}::{cls}"
    if cache_key in _reference_image_cache:
        return _reference_image_cache[cache_key]
    cls_dir = reference_dir / cls
    images: list[str] = []
    if cls_dir.is_dir():
        for path in sorted(cls_dir.iterdir()):
            if not path.is_file() or not is_image_file(path):
                continue
            original_bytes = path.read_bytes()
            compressed_bytes, compressed_format = compress_image_bytes(original_bytes)
            compressed_mime_type = (
                "image/jpeg"
                if compressed_format == "jpeg"
                else f"image/{compressed_format}"
            )
            images.append(image_bytes_to_data_url(compressed_bytes, compressed_mime_type))
    _reference_image_cache[cache_key] = images
    return images


def load_reference_image_paths(reference_dir: Path, cls: str) -> list[str]:
    """加载某个 cls 对应的参考图片本地路径。"""
    cache_key = f"{reference_dir.resolve()}::{cls}"
    if cache_key in _reference_image_path_cache:
        return _reference_image_path_cache[cache_key]
    cls_dir = reference_dir / cls
    image_paths = [
        str(path)
        for path in sorted(cls_dir.iterdir())
        if cls_dir.is_dir() and path.is_file() and is_image_file(path)
    ]
    _reference_image_path_cache[cache_key] = image_paths
    return image_paths


def get_padded_box(
    image: Image.Image,
    pos: list[Any],
) -> tuple[int, int, int, int] | None:
    """按 Java 逻辑计算带 padding 的裁剪框。

    Args:
        image: 原图对象。
        pos: 检测框坐标 [x1, y1, x2, y2]。

    Returns:
        扩框后的坐标，非法时返回 None。
    """
    if len(pos) < 4:
        return None
    x1 = max(0, int(float(pos[0])))
    y1 = max(0, int(float(pos[1])))
    x2 = min(image.width, int(float(pos[2])))
    y2 = min(image.height, int(float(pos[3])))
    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        return None

    pad = max(width, height) // 2
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(image.width, x2 + pad)
    y2 = min(image.height, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def crop_region(image_path: Path, pos: list[Any]) -> str | None:
    """从原图中裁剪检测区域并返回 PNG data URL。

    参数:
        image_path: 原图路径。
        pos: 检测框坐标 `[x1, y1, x2, y2]`。

    返回:
        PNG data URL；裁剪失败时返回 None。
    """
    with Image.open(image_path) as image:
        padded_box = get_padded_box(image, pos)
        if padded_box is None:
            return None
        x1, y1, x2, y2 = padded_box
        cropped = image.crop((x1, y1, x2, y2))
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        return image_bytes_to_data_url(buffer.getvalue(), "image/png")


def detect_image_format(image_bytes: bytes) -> str:
    """识别图片格式。

    Args:
        image_bytes: 图片二进制内容。

    Returns:
        图片格式名。
    """
    if len(image_bytes) >= 12:
        if image_bytes[:6] in {b"GIF87a", b"GIF89a"}:
            return "gif"
        if image_bytes[:2] == b"BM":
            return "bmp"
        if image_bytes[:4] in {b"II*\x00", b"MM\x00*"}:
            return "tiff"
        if image_bytes[:2] == b"\xff\xd8":
            return "jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"
        if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            return "webp"
        if b"heic" in image_bytes[4:12] or b"mif1" in image_bytes[4:12]:
            return "heic"
    return "jpeg"


def normalize_image_mode_for_format(image: Image.Image, image_format: str) -> Image.Image:
    """按目标格式规范化图片模式。

    Args:
        image: Pillow 图片对象。
        image_format: 目标格式。

    Returns:
        可用于保存的图片对象。
    """
    if image_format.lower() == "jpeg" and image.mode not in {"RGB", "L"}:
        return image.convert("RGB")
    return image


def resize_image(image: Image.Image, scale: float) -> Image.Image:
    """按比例缩放图片，策略对齐 Java 实现。"""
    new_width = max(10, int(image.width * scale))
    new_height = max(10, int(image.height * scale))
    if new_width == image.width and new_height == image.height:
        return image.copy()
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def limit_image_edge(image: Image.Image, max_edge: int = MAX_IMAGE_EDGE) -> Image.Image:
    """限制图片最长边，避免超大参考图压缩耗时过高。"""
    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge <= max_edge:
        return image.copy()
    scale = max_edge / float(longest_edge)
    new_size = (
        max(10, int(width * scale)),
        max(10, int(height * scale)),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def save_image_bytes(image: Image.Image, image_format: str, quality: int) -> bytes:
    """将图片压缩为指定格式字节。

    Args:
        image: Pillow 图片对象。
        image_format: 输出格式。
        quality: 压缩质量，0-100。

    Returns:
        压缩后的二进制内容。
    """
    buffer = io.BytesIO()
    target = normalize_image_mode_for_format(image, image_format)
    lower_format = image_format.lower()
    if lower_format == "jpeg":
        target.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
        )
    elif lower_format == "png":
        target.save(
            buffer,
            format="PNG",
            optimize=True,
            compress_level=9,
        )
    else:
        target.save(buffer, format=image_format.upper())
    return buffer.getvalue()


def compress_image_bytes(image_bytes: bytes, max_base64_size: int = LLM_MAX_IMAGE_BYTES) -> tuple[bytes, str]:
    """压缩图片字节，尽量对齐 Java 的多轮压缩逻辑。

    Args:
        image_bytes: 原始图片二进制内容。
        max_base64_size: 压缩后允许的最大 base64 长度。

    Returns:
        压缩后的图片字节和格式。
    """
    encoded_length = len(base64.b64encode(image_bytes))
    image_format = detect_image_format(image_bytes)
    if encoded_length <= max_base64_size:
        return image_bytes, image_format

    with Image.open(io.BytesIO(image_bytes)) as source_image:
        working_image = limit_image_edge(source_image.copy())

    if image_format in {"png", "bmp", "tiff", "webp", "heic"}:
        image_format = "jpeg"

    best_bytes = image_bytes
    best_size = encoded_length
    quality = INITIAL_COMPRESS_QUALITY
    scale = INITIAL_RESIZE_SCALE

    for _ in range(COMPRESS_ATTEMPTS):
        resized_image = resize_image(working_image, scale)
        compressed_bytes = save_image_bytes(resized_image, image_format, quality)
        compressed_size = len(base64.b64encode(compressed_bytes))
        if compressed_size <= max_base64_size:
            return compressed_bytes, image_format
        if compressed_size < best_size:
            best_bytes = compressed_bytes
            best_size = compressed_size
        quality = max(MIN_COMPRESS_QUALITY, quality - int(COMPRESS_STEP * 100))
        scale = max(0.5, scale - COMPRESS_STEP)

    return best_bytes, image_format


def crop_region_bytes(image_path: Path, pos: list[Any]) -> tuple[bytes, str] | None:
    """裁剪检测区域并返回图片字节。

    Args:
        image_path: 原图路径。
        pos: 检测框坐标。

    Returns:
        图片字节和 mime type，失败时返回 None。
    """
    with Image.open(image_path) as image:
        padded_box = get_padded_box(image, pos)
        if padded_box is None:
            return None
        x1, y1, x2, y2 = padded_box
        cropped = image.crop((x1, y1, x2, y2))
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def save_cropped_region(
    image_path: Path,
    detection: dict[str, Any],
    detection_index: int,
    output_dir: Path,
) -> str | None:
    """保存裁剪后的检测区域图片。

    Args:
        image_path: 原始图片路径。
        detection: 单个检测结果。
        detection_index: 当前页内同次处理的检测序号，从 1 开始。
        output_dir: 裁剪图根目录。

    Returns:
        保存后的图片路径字符串，失败时返回 None。
    """
    pos = detection.get("pos", [])
    cls = str(detection.get("cls", "")).strip() or "unknown"
    with Image.open(image_path) as image:
        padded_box = get_padded_box(image, pos)
        if padded_box is None:
            return None
        x1, y1, x2, y2 = padded_box
        cropped = image.crop((x1, y1, x2, y2))
        cls_dir = output_dir / cls
        cls_dir.mkdir(parents=True, exist_ok=True)
        page_no = extract_page_no(image_path)
        crop_path = cls_dir / f"{page_no}.{detection_index}.tmp.png"
        cropped.save(crop_path, format="PNG")
        return str(crop_path)


def verify_detections_with_multimodal(
    detections: list[dict[str, Any]],
    image_path: Path,
    reference_dir: Path,
    llm_model: str,
    llm_score_threshold: int,
    crop_output_dir: Path,
) -> list[dict[str, Any]]:
    """用多模态模型二次过滤 YOLO 检测结果。

    参数:
        detections: 经过置信度过滤后的 YOLO 检测结果。
        image_path: 原图路径。
        reference_dir: 参考图片根目录。
        llm_model: 多模态模型名称。
        llm_score_threshold: 允许通过的最低相似度分数。
        crop_output_dir: 裁剪图输出目录。

    返回:
        通过多模态校验后的检测结果列表。
    """
    verified_detections: list[dict[str, Any]] = []
    for index, detection in enumerate(detections, start=1):
        crop_path = save_cropped_region(
            image_path=image_path,
            detection=detection,
            detection_index=index,
            output_dir=crop_output_dir,
        )
        if crop_path:
            detection["crop_path"] = crop_path
        crop_payload = crop_region_bytes(image_path, detection.get("pos", []))
        if not crop_payload:
            verified_detections.append(detection)
            continue
        crop_bytes, crop_mime_type = crop_payload
        compressed_bytes, compressed_format = compress_image_bytes(crop_bytes)
        compressed_mime_type = "image/jpeg" if compressed_format == "jpeg" else f"image/{compressed_format}"
        cropped_image = image_bytes_to_data_url(compressed_bytes, compressed_mime_type)
        cls = str(detection.get("cls", "")).strip()
        reference_images = load_reference_images(reference_dir, cls)
        reference_image_paths = load_reference_image_paths(reference_dir, cls)
        detection["llm_logo_compare_paths"] = reference_image_paths
        if not reference_images:
            verified_detections.append(detection)
            continue
        llm_result = call_multimodal_llm(cropped_image, reference_images, llm_model)
        detection["llm_result"] = llm_result
        detection["llm_score"] = extract_score(llm_result)
        if detection["llm_score"] is not None and detection["llm_score"] >= llm_score_threshold:
            verified_detections.append(detection)
    return verified_detections


def filter_confident_detections(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """筛选置信度达标的检测框。"""
    return [
        dict(item)
        for item in detections
        if str(item.get("cls", "")).strip() != "logo_az"
        and float(item.get("may", 0)) >= CONFIDENCE_THRESHOLD
    ]


def build_detail_row(
    folder_path: Path,
    image_path: Path,
    api_result: dict,
    reference_dir: Path,
    llm_model: str,
    llm_score_threshold: int,
    crop_output_dir: Path,
) -> dict:
    folder_name = folder_path.name
    detailed_id, task_id = split_folder_name(folder_name)
    detections = api_result.get("detections", [])
    confident_detections = filter_confident_detections(detections)
    verified_detections = verify_detections_with_multimodal(
        detections=confident_detections,
        image_path=image_path,
        reference_dir=reference_dir,
        llm_model=llm_model,
        llm_score_threshold=llm_score_threshold,
        crop_output_dir=crop_output_dir,
    )
    final_number = len(verified_detections)
    return {
        "folder_name": folder_name,
        "detailed_id": detailed_id,
        "task_id": task_id,
        "page_no": extract_page_no(image_path),
        "expect_number": None,
        "position_count": final_number,
        "final_number": final_number,
        "threshold_positions(may>=0.7)": json.dumps(
            confident_detections,
            ensure_ascii=False,
        ),
        "llm_result": json.dumps(
            [item.get("llm_result", "") for item in confident_detections],
            ensure_ascii=False,
        ),
        "llm_crop_image_path": json.dumps(
            [item.get("crop_path", "") for item in confident_detections],
            ensure_ascii=False,
        ),
        "llm_logo_compare_image_path": json.dumps(
            [item.get("llm_logo_compare_paths", []) for item in confident_detections],
            ensure_ascii=False,
        ),
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
        "expect_number": None,
        "position_count": 0,
        "final_number": 0,
        "threshold_positions(may>=0.7)": "",
        "llm_result": "",
        "llm_crop_image_path": "",
        "llm_logo_compare_image_path": "",
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
    reference_dir: Path,
    llm_model: str,
    llm_score_threshold: int,
    crop_output_dir: Path,
) -> dict:
    try:
        api_result = call_api(
            image_path=image_path,
            api_url=api_url,
            model_type=model_type,
            timeout=timeout,
        )
        return build_detail_row(
            folder_path=folder_path,
            image_path=image_path,
            api_result=api_result,
            reference_dir=reference_dir,
            llm_model=llm_model,
            llm_score_threshold=llm_score_threshold,
            crop_output_dir=crop_output_dir,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_row(folder_path, image_path, str(exc))


def process_image_from_raw_result(
    folder_path: Path,
    image_path: Path,
    raw_result: Any,
    reference_dir: Path,
    llm_model: str,
    llm_score_threshold: int,
    crop_output_dir: Path,
) -> dict[str, Any]:
    """基于已有 raw_result 重跑裁剪、LLM 和统计。

    Args:
        folder_path: 图片所在任务目录。
        image_path: 原始页图路径。
        raw_result: Excel 中保存的 raw_result 字段。
        reference_dir: 参考图根目录。
        llm_model: 多模态模型名。
        llm_score_threshold: LLM 判定阈值。
        crop_output_dir: 裁剪图输出目录。

    Returns:
        新生成的明细行。
    """
    try:
        api_result = parse_raw_result(raw_result)
        if "detections" not in api_result:
            api_result = {"detections": []}
        return build_detail_row(
            folder_path=folder_path,
            image_path=image_path,
            api_result=api_result,
            reference_dir=reference_dir,
            llm_model=llm_model,
            llm_score_threshold=llm_score_threshold,
            crop_output_dir=crop_output_dir,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_row(folder_path, image_path, str(exc))


def apply_expect_numbers(
    detail_rows: list[dict[str, Any]],
    expect_map: dict[tuple[str, int], int | None],
) -> None:
    """将旧表中的 expect_number 写回新结果。"""
    for row in detail_rows:
        key = (str(row["folder_name"]), int(row["page_no"]))
        row["expect_number"] = expect_map.get(key)


def update_excel_rows(input_excel: Path, detail_rows: list[dict[str, Any]]) -> int:
    """按 folder_name + page_no 覆盖更新 Excel 明细行。"""
    workbook = load_workbook(input_excel)
    if "明细" not in workbook.sheetnames:
        raise ValueError("输入 Excel 缺少 '明细' sheet")
    detail_sheet = workbook["明细"]
    header_map = ensure_header_map(
        detail_sheet,
        [
            "folder_name",
            "detailed_id",
            "task_id",
            "page_no",
            "expect_number",
            "position_count",
            "final_number",
            "threshold_positions(may>=0.7)",
            "llm_result",
            "llm_crop_image_path",
            "llm_logo_compare_image_path",
            "status",
            "error_message",
            "raw_result",
        ],
    )
    row_map: dict[tuple[str, int], int] = {}
    for row_index in range(2, detail_sheet.max_row + 1):
        folder_name = detail_sheet.cell(row=row_index, column=header_map["folder_name"]).value
        page_no = normalize_count(detail_sheet.cell(row=row_index, column=header_map["page_no"]).value)
        if folder_name in (None, "") or page_no is None:
            continue
        row_map[(str(folder_name), page_no)] = row_index

    updated = 0
    for row in detail_rows:
        key = (str(row["folder_name"]), int(row["page_no"]))
        row_index = row_map.get(key)
        if row_index is None:
            continue
        for header, column_index in header_map.items():
            if header in row:
                detail_sheet.cell(row=row_index, column=column_index, value=row[header])
        updated += 1

    autosize_worksheet(detail_sheet)
    workbook.save(input_excel)
    return updated


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
        "expect_number",
        "position_count",
        "final_number",
        "threshold_positions(may>=0.7)",
        "llm_result",
        "llm_crop_image_path",
        "llm_logo_compare_image_path",
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
        "total_final_number",
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
    """按单页维度计算 TP、FP、FN。

    参数:
        expect_number: 预期检出数量。
        position_count: 实际检出数量。

    返回:
        `(tp, fp, fn)` 元组。
    """
    true_positive = min(expect_number, position_count)
    false_positive = max(position_count - expect_number, 0)
    false_negative = max(expect_number - position_count, 0)
    return true_positive, false_positive, false_negative


def parse_json_list(value: Any) -> list[Any]:
    """将单元格中的 JSON 数组解析为列表。

    Args:
        value: Excel 单元格中的值。

    Returns:
        解析后的列表，失败时返回空列表。
    """
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def classify_missing_reason(
    raw_payload: dict[str, Any],
    threshold_positions: list[dict[str, Any]],
    final_number: int,
) -> str:
    """细分漏报来源。

    Args:
        raw_payload: raw_result 解析结果。
        threshold_positions: may>=0.7 筛选后的检测框。
        final_number: 最终计数。

    Returns:
        漏报原因分类。
    """
    raw_detections = raw_payload.get("detections", [])
    if not raw_detections:
        return "raw_result为空"
    if not threshold_positions:
        return "may<0.7被过滤"
    if final_number < len(threshold_positions):
        return "LLM二次处理后过滤"
    return "其他不一致"


def build_failure_breakdown_sheet(
    workbook,
    mismatch_rows: list[dict[str, Any]],
    detail_header_map: dict[str, int],
    detail_rows: list[tuple[Any, ...]],
) -> None:
    """生成失败原因细分 sheet。

    Args:
        workbook: Excel 工作簿。
        mismatch_rows: 审计不一致明细。
        detail_header_map: 明细 sheet 表头映射。
        detail_rows: 明细 sheet 全量行数据。
    """
    if "失败原因细分" in workbook.sheetnames:
        del workbook["失败原因细分"]

    detail_map: dict[tuple[str, int], tuple[Any, ...]] = {}
    for row in detail_rows:
        folder_name = row[detail_header_map["folder_name"]]
        page_no = normalize_count(row[detail_header_map["page_no"]])
        if folder_name in (None, "") or page_no is None:
            continue
        detail_map[(str(folder_name), page_no)] = row

    summary_map: dict[str, dict[str, int]] = {
        "raw_result为空": {"page_count": 0, "missing_count": 0},
        "may<0.7被过滤": {"page_count": 0, "missing_count": 0},
        "LLM二次处理后过滤": {"page_count": 0, "missing_count": 0},
        "其他不一致": {"page_count": 0, "missing_count": 0},
    }
    breakdown_rows: list[dict[str, Any]] = []

    for item in mismatch_rows:
        key = (str(item["folder_name"]), int(item["page_no"]))
        detail_row = detail_map.get(key)
        if detail_row is None:
            continue

        raw_payload = parse_raw_result(detail_row[detail_header_map["raw_result"]])
        threshold_positions = parse_json_list(
            detail_row[detail_header_map["threshold_positions(may>=0.7)"]]
        )
        llm_results = parse_json_list(detail_row[detail_header_map["llm_result"]])
        final_number = normalize_count(detail_row[detail_header_map["final_number"]]) or 0
        expect_number = normalize_count(detail_row[detail_header_map["expect_number"]]) or 0
        missing_count = max(expect_number - final_number, 0)
        reason_category = classify_missing_reason(
            raw_payload=raw_payload,
            threshold_positions=threshold_positions,
            final_number=final_number,
        )

        summary_map.setdefault(reason_category, {"page_count": 0, "missing_count": 0})
        summary_map[reason_category]["page_count"] += 1
        summary_map[reason_category]["missing_count"] += missing_count

        breakdown_rows.append(
            {
                "folder_name": item["folder_name"],
                "detailed_id": item["detailed_id"],
                "task_id": item["task_id"],
                "page_no": item["page_no"],
                "expect_number": expect_number,
                "final_number": final_number,
                "missing_count": missing_count,
                "reason_category": reason_category,
                "raw_detection_count": len(raw_payload.get("detections", [])),
                "threshold_detection_count": len(threshold_positions),
                "llm_pass_count": final_number,
                "llm_result": json.dumps(llm_results, ensure_ascii=False),
            }
        )

    breakdown_sheet = workbook.create_sheet("失败原因细分")
    breakdown_sheet.append(["reason_category", "page_count", "missing_count"])
    for cell in breakdown_sheet[1]:
        cell.font = Font(bold=True)
    for reason_category in ["raw_result为空", "may<0.7被过滤", "LLM二次处理后过滤", "其他不一致"]:
        data = summary_map.get(reason_category, {"page_count": 0, "missing_count": 0})
        breakdown_sheet.append(
            [reason_category, data["page_count"], data["missing_count"]]
        )

    breakdown_sheet.append(())
    detail_headers = [
        "folder_name",
        "detailed_id",
        "task_id",
        "page_no",
        "expect_number",
        "final_number",
        "missing_count",
        "reason_category",
        "raw_detection_count",
        "threshold_detection_count",
        "llm_pass_count",
        "llm_result",
    ]
    breakdown_sheet.append(detail_headers)
    header_row_index = breakdown_sheet.max_row
    for cell in breakdown_sheet[header_row_index]:
        cell.font = Font(bold=True)
    for row in breakdown_rows:
        breakdown_sheet.append([row[header] for header in detail_headers])
    autosize_worksheet(breakdown_sheet)


def audit_position_counts(input_excel: Path, output_path: Path) -> tuple[int, int, int]:
    workbook = load_workbook(input_excel)
    if "明细" not in workbook.sheetnames:
        raise ValueError("输入 Excel 缺少 '明细' sheet")

    detail_sheet = workbook["明细"]
    detail_rows = list(detail_sheet.iter_rows(values_only=True))
    rows = iter(detail_rows)
    headers = next(rows, None)
    if not headers:
        raise ValueError("明细 sheet 为空")

    header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
    required_headers = ["folder_name", "detailed_id", "task_id", "page_no", "expect_number", "final_number"]
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
        final_number = normalize_count(row[header_map["final_number"]])
        expect_number = normalize_count(row[header_map["expect_number"]])

        if final_number is None and expect_number is None:
            continue

        normalized_position_count = final_number or 0
        normalized_expect_number = expect_number or 0
        true_positive, false_positive, false_negative = calculate_page_metrics(
            expect_number=normalized_expect_number,
            position_count=normalized_position_count,
        )
        total_true_positive += true_positive
        total_false_positive += false_positive
        total_false_negative += false_negative

        if final_number != expect_number:
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
                "final_number": final_number,
                "difference": (final_number or 0) - (expect_number or 0),
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

    for sheet_name in ("汇总", "不一致明细", "审计汇总", "审计结果", "失败原因细分"):
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
        "final_number",
        "difference",
    ]
    result_sheet.append(mismatch_headers)
    mismatch_header_row_index = result_sheet.max_row
    for cell in result_sheet[mismatch_header_row_index]:
        cell.font = Font(bold=True)
    for item in mismatch_rows:
        result_sheet.append([item[header] for header in mismatch_headers])
    autosize_worksheet(result_sheet)
    build_failure_breakdown_sheet(
        workbook=workbook,
        mismatch_rows=mismatch_rows,
        detail_header_map=header_map,
        detail_rows=detail_rows[1:],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    return mismatch_file_count, failed_page_count, len(mismatch_rows)


def parse_raw_result(raw_result: Any) -> dict[str, Any]:
    """解析明细中的 raw_result 字段。"""
    if raw_result in (None, ""):
        return {}
    if isinstance(raw_result, dict):
        return raw_result
    try:
        return json.loads(str(raw_result))
    except json.JSONDecodeError:
        return {}


def count_verified_number(raw_payload: dict[str, Any], llm_score_threshold: int) -> int:
    """按最终规则统计一页的有效检出数。"""
    verified_detections = raw_payload.get("verified_detections", [])
    count = 0
    for detection in verified_detections:
        score = normalize_count(detection.get("llm_score"))
        if score is not None and score >= llm_score_threshold:
            count += 1
    return count


def ensure_header_map(detail_sheet, required_headers: list[str]) -> dict[str, int]:
    """确保 sheet 中存在指定表头，不存在则追加。"""
    headers = [cell.value for cell in detail_sheet[1]]
    header_map = {
        str(header): index + 1
        for index, header in enumerate(headers)
        if header not in (None, "")
    }
    for header in required_headers:
        if header not in header_map:
            column_index = detail_sheet.max_column + 1
            detail_sheet.cell(row=1, column=column_index, value=header).font = Font(bold=True)
            header_map[header] = column_index
    return header_map


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

    if args.mode == "rerun-from-raw":
        output_path = Path(args.input_excel).expanduser()
        expect_map = load_expect_number_map(output_path)
        workbook = load_workbook(output_path, read_only=True)
        if "明细" not in workbook.sheetnames:
            print("输入 Excel 缺少 '明细' sheet", file=sys.stderr)
            return 1
        detail_sheet = workbook["明细"]
        rows = detail_sheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            print("明细 sheet 为空", file=sys.stderr)
            return 1
        header_map = {str(header): index for index, header in enumerate(headers) if header is not None}
        required_headers = ["folder_name", "page_no", "raw_result"]
        missing_headers = [header for header in required_headers if header not in header_map]
        if missing_headers:
            print(f"明细 sheet 缺少列: {', '.join(missing_headers)}", file=sys.stderr)
            return 1

        input_dir = Path(args.input_dir).expanduser()
        reference_dir = Path(args.reference_dir).expanduser()
        detail_rows: list[dict[str, Any]] = []
        processed = 0
        skipped = 0
        for row in rows:
            folder_name = row[header_map["folder_name"]]
            page_no = normalize_count(row[header_map["page_no"]])
            raw_result = row[header_map["raw_result"]]
            status = ""
            if "status" in header_map and row[header_map["status"]] not in (None, ""):
                status = str(row[header_map["status"]]).lower()
            if folder_name in (None, "") or page_no is None:
                continue
            image_path = find_page_image(input_dir, str(folder_name), page_no)
            if image_path is None:
                skipped += 1
                continue
            if raw_result in (None, "") and status == "failed":
                skipped += 1
                continue
            rerun_row = process_image_from_raw_result(
                folder_path=image_path.parent,
                image_path=image_path,
                raw_result=raw_result,
                reference_dir=reference_dir,
                llm_model=args.llm_model,
                llm_score_threshold=args.llm_score_threshold,
                crop_output_dir=TMP_CROP_DIR,
            )
            detail_rows.append(rerun_row)
            processed += 1
            print(
                f"rerun-from-raw | {folder_name} | page {page_no} | "
                f"status={rerun_row['status']} | final_number={rerun_row['final_number']}"
            )

        apply_expect_numbers(detail_rows, expect_map)
        updated = update_excel_rows(output_path, detail_rows)
        file_count, failed_page_count, mismatch_count = audit_position_counts(
            input_excel=output_path,
            output_path=output_path,
        )
        print(
            f"raw_result重跑完成：处理页数={processed}，跳过页数={skipped}，更新页数={updated}，"
            f"不一致文件数={file_count}，失败页数={failed_page_count}，不一致记录数={mismatch_count}"
        )
        return 0

    if args.mode in {"rerun-rate-limit", "rerun-large-image", "rerun-retryable"}:
        output_path = Path(args.input_excel).expanduser()
        expect_map = load_expect_number_map(output_path)
        if args.mode == "rerun-rate-limit":
            pages = load_rate_limited_pages(output_path)
            mode_label = "限流页"
        elif args.mode == "rerun-large-image":
            pages = load_large_image_pages(output_path)
            mode_label = "图片过大页"
        else:
            pages = load_retryable_pages(output_path)
            mode_label = "限流页和图片过大页"
        if not pages:
            print(f"未发现需要重跑的{mode_label}。")
            return 0
        input_dir = Path(args.input_dir).expanduser()
        reference_dir = Path(args.reference_dir).expanduser()
        detail_rows: list[dict[str, Any]] = []
        for folder_name, page_no in pages:
            image_path = find_page_image(input_dir, folder_name, page_no)
            if image_path is None:
                continue
            row = process_image(
                folder_path=image_path.parent,
                image_path=image_path,
                api_url=args.api_url,
                model_type=args.model_type,
                timeout=args.timeout,
                reference_dir=reference_dir,
                llm_model=args.llm_model,
                llm_score_threshold=args.llm_score_threshold,
                crop_output_dir=TMP_CROP_DIR,
            )
            detail_rows.append(row)
            print(
                f"{args.mode} | {folder_name} | page {page_no} | "
                f"status={row['status']} | final_number={row['final_number']}"
            )
        apply_expect_numbers(detail_rows, expect_map)
        updated = update_excel_rows(output_path, detail_rows)
        file_count, failed_page_count, mismatch_count = audit_position_counts(
            input_excel=output_path,
            output_path=output_path,
        )
        print(
            f"{mode_label}重跑完成：更新页数={updated}，"
            f"不一致文件数={file_count}，失败页数={failed_page_count}，不一致记录数={mismatch_count}"
        )
        return 0

    if args.mode in {"rerun", "generate"}:
        output_path = Path(args.input_excel).expanduser()
        expect_map = load_expect_number_map(output_path)
    else:
        expect_map = {}

    input_dir = Path(args.input_dir).expanduser()
    reference_dir = Path(args.reference_dir).expanduser()

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
                reference_dir,
                args.llm_model,
                args.llm_score_threshold,
                TMP_CROP_DIR,
            ): (folder_path, image_path)
            for folder_path, image_path in tasks
        }
        for future in as_completed(future_map):
            row = future.result()
            detail_rows.append(row)
            if row["status"] == "success":
                print(
                    f"{row['folder_name']} | page {row['page_no']} | "
                    f"final_number={row['final_number']}"
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
                "total_final_number": sum(row["final_number"] for row in folder_rows),
            }
        )

    summary_rows.sort(key=lambda row: row["folder_name"])
    apply_expect_numbers(detail_rows, expect_map)

    write_excel(detail_rows, summary_rows, output_path)
    print(f"\nExcel 已写入：{output_path.resolve()}")
    print(
        f"完成：任务文件夹={len(summary_rows)}，总页数={len(detail_rows)}，"
        f"成功页数={sum(row['success_page_count'] for row in summary_rows)}，"
        f"失败页数={sum(row['failed_page_count'] for row in summary_rows)}"
    )
    if args.mode == "rerun":
        file_count, failed_page_count, mismatch_count = audit_position_counts(
            input_excel=output_path,
            output_path=output_path,
        )
        print(
            f"审计重算完成：不一致文件数={file_count}，"
            f"失败页数={failed_page_count}，不一致记录数={mismatch_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
