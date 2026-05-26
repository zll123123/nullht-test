#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pptx import Presentation


DEFAULT_EXCEL_PATH = Path(__file__).resolve().with_name("ppt原文抽取结果_获取pptstruct对比.xlsx")
DEFAULT_LOG_PATH = Path(__file__).resolve().with_name("review_pptstruct_semantics_to_excel.log")
DEFAULT_PPT_DIR = Path("/Users/layla.zhang/测试用例/测试材料/az/验证case/")
DEFAULT_LLM_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_LLM_MODEL = "MiniMax-M2.7"
DEFAULT_LLM_API_KEY = "sk-cp-96ZlkfZNixQvYfwfs6Q1Po-4vFUuoFlJK497LBl2wCUwK5LIkB5aFNJ2REdK3htdvv90O4-TQM8VC04AK733IrqMRR25Wl98XFF6pE92kfzHjGCq2DsK9xk"
DEFAULT_LLM_TIMEOUT_SECONDS = 120
DEFAULT_LLM_MAX_RETRIES = 3

FILE_NAME_HEADER = "文件名称"
PAGE_NUMBER_HEADER = "页码"
PPT_STRUCT_HEADER = "日志中的pptstruct"
PPT_SOURCE_HEADER = "ppt原文"
DIFF_HEADER = "diff"
LLM_ERROR_TYPE_HEADER = "LLM错误类型"
LLM_SEVERITY_HEADER = "LLM严重程度"
LLM_BASIS_HEADER = "LLM判断依据"
LLM_RESULT_HEADER = "人工审核结果"

SENTENCE_SEPARATOR_PATTERN = re.compile(r"[。！？!?；;]+|\n+")
WHITESPACE_PATTERN = re.compile(r"\s+")
ALIGNMENT_THRESHOLD = 0.55
MAX_REPORT_ITEMS = 5
MAX_TEXT_SNIPPET_LENGTH = 80


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于 PPT 原文与 pptStruct 文本对齐结果审核语义完整性和文本差异。")
    parser.add_argument("--sheet-name", help="可选，指定工作表名称；默认使用 active sheet")
    return parser.parse_args()


def setup_logging() -> None:
    logger.remove()
    logger.add(str(DEFAULT_LOG_PATH), level="INFO", encoding="utf-8", mode="w")


def normalize_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = normalized.replace(".pptx.pptx", ".pptx")
    normalized = normalized.replace(".ppt.ppt", ".ppt")
    normalized = WHITESPACE_PATTERN.sub("", normalized)
    return normalized


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def compact_text(text: str) -> str:
    return re.sub(r"[\s，,。！？!?；;:：、“”\"'‘’（）()\[\]【】·\-_/]", "", text).lower()


def shorten_text(text: str, max_length: int = MAX_TEXT_SNIPPET_LENGTH) -> str:
    text = normalize_text(text).replace("\n", " ")
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def normalize_page_number(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def build_ppt_index(ppt_dir: Path) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for path in sorted(ppt_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ppt", ".pptx"}:
            continue
        index[normalize_name(path.name)] = path
    return index


def run_command(command: List[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_command_output(command: List[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout


def require_command(command_name: str) -> None:
    if shutil.which(command_name) is None:
        raise RuntimeError("缺少依赖命令: {}".format(command_name))


def convert_ppt_to_pptx(ppt_path: Path, work_dir: Path) -> Path:
    require_command("soffice")
    output_dir = work_dir / "pptx"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pptx",
            "--outdir",
            str(output_dir),
            str(ppt_path),
        ]
    )
    pptx_path = output_dir / "{}.pptx".format(ppt_path.stem)
    if not pptx_path.exists():
        raise RuntimeError("未生成 PPTX: {}".format(pptx_path))
    return pptx_path


def resolve_presentation_path(ppt_path: Path, work_dir: Path, converted_cache: Dict[Path, Path]) -> Path:
    if ppt_path.suffix.lower() == ".pptx":
        return ppt_path
    cached = converted_cache.get(ppt_path)
    if cached is not None:
        return cached
    converted = convert_ppt_to_pptx(ppt_path, work_dir)
    converted_cache[ppt_path] = converted
    return converted


def safe_path_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)


def render_presentation_to_pdf(presentation_path: Path, work_dir: Path, pdf_cache: Dict[Path, Path]) -> Path:
    cached = pdf_cache.get(presentation_path)
    if cached is not None:
        return cached

    require_command("soffice")
    output_dir = work_dir / "pdf" / safe_path_name(presentation_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(presentation_path),
        ]
    )
    pdf_path = output_dir / "{}.pdf".format(presentation_path.stem)
    if not pdf_path.exists():
        pdf_files = sorted(output_dir.glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("未生成 PDF: {}".format(pdf_path))
        pdf_path = pdf_files[0]
    pdf_cache[presentation_path] = pdf_path
    return pdf_path


def extract_pdf_page_text(pdf_path: Path, page_number: int) -> str:
    require_command("pdftotext")
    return run_command_output(
        [
            "pdftotext",
            "-layout",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            str(pdf_path),
            "-",
        ]
    )


def render_pdf_page_to_png(pdf_path: Path, page_number: int, work_dir: Path) -> Path:
    require_command("pdftoppm")
    output_dir = work_dir / "ocr" / "{}_{}".format(safe_path_name(pdf_path), page_number)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / "page"
    run_command(
        [
            "pdftoppm",
            "-r",
            "300",
            "-png",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            str(pdf_path),
            str(output_prefix),
        ]
    )
    png_path = output_dir / "page.png"
    if not png_path.exists():
        raise RuntimeError("未生成页面截图: {}".format(png_path))
    return png_path


def ocr_image_text(image_path: Path) -> str:
    require_command("tesseract")
    return run_command_output(["tesseract", str(image_path), "stdout", "-l", "chi_sim+eng", "--psm", "6"])


def extract_slide_text_by_ocr(
    presentation_path: Path,
    page_number: int,
    work_dir: Path,
    pdf_cache: Dict[Path, Path],
) -> str:
    pdf_path = render_presentation_to_pdf(presentation_path, work_dir, pdf_cache)
    texts = [extract_pdf_page_text(pdf_path, page_number)]
    image_path = render_pdf_page_to_png(pdf_path, page_number, work_dir)
    texts.append(ocr_image_text(image_path))
    return normalize_text("\n".join(text for text in texts if text.strip()))


def collect_shape_texts(shape) -> List[str]:
    texts: List[str] = []
    if hasattr(shape, "shapes"):
        for child in shape.shapes:
            texts.extend(collect_shape_texts(child))
    if getattr(shape, "has_text_frame", False):
        text = normalize_text(shape.text or "")
        if text:
            texts.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = normalize_text(cell.text or "")
                if cell_text:
                    row_texts.append(cell_text)
            if row_texts:
                texts.append(" | ".join(row_texts))
    return texts


def extract_slide_source_text(
    ppt_path: Path,
    page_number: int,
    work_dir: Path,
    converted_cache: Dict[Path, Path],
    pdf_cache: Dict[Path, Path],
    presentation_cache: Dict[Path, Presentation],
) -> str:
    # 优先直接读取 PPT 页面中的文本对象，避免 OCR 带来的识别噪声。
    presentation_path = resolve_presentation_path(ppt_path, work_dir, converted_cache)
    presentation = presentation_cache.get(presentation_path)
    if presentation is None:
        presentation = Presentation(str(presentation_path))
        presentation_cache[presentation_path] = presentation
    if page_number < 1 or page_number > len(presentation.slides):
        raise RuntimeError("页码超出范围: {} / {}".format(page_number, len(presentation.slides)))
    slide = presentation.slides[page_number - 1]
    texts: List[str] = []
    for shape in slide.shapes:
        texts.extend(collect_shape_texts(shape))
    source_text = normalize_text("\n".join(texts))
    if source_text:
        return source_text

    logger.info("page text is empty, fallback to OCR: file={} page={}", ppt_path.name, page_number)
    return extract_slide_text_by_ocr(presentation_path, page_number, work_dir, pdf_cache)


def collect_struct_texts(value) -> List[str]:
    texts: List[str] = []
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            normalized = normalize_text(text)
            if normalized:
                texts.append(normalized)
        summary = value.get("ppt_summary")
        if isinstance(summary, str):
            normalized = normalize_text(summary)
            if normalized:
                texts.append(normalized)
        for child_key, child_value in value.items():
            if child_key in {"text", "ppt_summary"}:
                continue
            texts.extend(collect_struct_texts(child_value))
    elif isinstance(value, list):
        for child in value:
            texts.extend(collect_struct_texts(child))
    return texts


def build_ppt_struct_text(ppt_struct_obj: Dict[str, object]) -> str:
    ordered_texts: List[str] = []
    seen = set()
    # 将 pptStruct 中分散的 text / ppt_summary 按遍历顺序拼成可比对文本。
    for text in collect_struct_texts(ppt_struct_obj):
        key = compact_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered_texts.append(text)
    return normalize_text("\n".join(ordered_texts))


def split_sentences(text: str) -> List[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    sentences: List[str] = []
    for chunk in SENTENCE_SEPARATOR_PATTERN.split(normalized):
        sentence = normalize_text(chunk)
        if not sentence:
            continue
        if len(compact_text(sentence)) <= 1:
            continue
        sentences.append(sentence)
    return sentences


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, compact_text(left), compact_text(right)).ratio()


def build_best_match_map(sentences: List[str], candidates: List[str]) -> Dict[int, Tuple[Optional[int], float]]:
    result: Dict[int, Tuple[Optional[int], float]] = {}
    # 为每个句子挑选最相近的候选句，后续再做双向一致性校验。
    for sentence_index, sentence in enumerate(sentences):
        best_index: Optional[int] = None
        best_score = 0.0
        for candidate_index, candidate in enumerate(candidates):
            score = similarity(sentence, candidate)
            if score > best_score:
                best_index = candidate_index
                best_score = score
        result[sentence_index] = (best_index, best_score)
    return result


def summarize_char_diff(source_text: str, target_text: str, max_items: int = 3) -> str:
    # 对已对齐的句子做字符级差异摘要，输出替换 / 缺失 / 新增片段。
    matcher = SequenceMatcher(None, source_text, target_text)
    parts: List[str] = []
    for tag, source_start, source_end, target_start, target_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        source_fragment = source_text[source_start:source_end]
        target_fragment = target_text[target_start:target_end]
        if tag == "replace":
            parts.append("替换[{} -> {}]".format(shorten_text(source_fragment, 20), shorten_text(target_fragment, 20)))
        elif tag == "delete":
            parts.append("缺失[{}]".format(shorten_text(source_fragment, 20)))
        elif tag == "insert":
            parts.append("新增[{}]".format(shorten_text(target_fragment, 20)))
        if len(parts) >= max_items:
            break
    return "；".join(parts) if parts else "存在字符级差异"


def short_join(items: List[str], empty_text: str) -> str:
    if not items:
        return empty_text
    return "；".join(items[:MAX_REPORT_ITEMS])


def find_header_columns(sheet) -> Dict[str, int]:
    header_map: Dict[str, int] = {}
    for cell in sheet[1]:
        if isinstance(cell.value, str):
            header = cell.value.strip()
            if header:
                header_map[header] = cell.column
    return header_map


def ensure_output_column(sheet, header_map: Dict[str, int], header_name: str, preferred_index: int) -> int:
    column_index = header_map.get(header_name)
    if column_index is None:
        column_index = preferred_index
        sheet.cell(1, column_index).value = header_name
        header_map[header_name] = column_index
    return column_index


def require_columns(header_map: Dict[str, int], headers: List[str]) -> Dict[str, int]:
    missing = [header for header in headers if header not in header_map]
    if missing:
        raise RuntimeError("Excel 缺少表头: {}".format(", ".join(missing)))
    return {header: header_map[header] for header in headers}


def review_semantics(source_text: str, ppt_struct_obj: Dict[str, object]) -> Dict[str, object]:
    # 对比链路：PPT 原文 -> 句子切分 -> 双向对齐 -> 字符级差异摘要。
    struct_text = build_ppt_struct_text(ppt_struct_obj)
    source_sentences = split_sentences(source_text)
    struct_sentences = split_sentences(struct_text)

    if not source_sentences:
        return {
            "struct_text": struct_text,
            "diff_text": "PPT 原文为空，无法比对",
        }
    if not struct_sentences:
        return {
            "struct_text": struct_text,
            "diff_text": "pptStruct 未提取到有效文本",
        }

    source_to_struct = build_best_match_map(source_sentences, struct_sentences)
    struct_to_source = build_best_match_map(struct_sentences, source_sentences)

    missing_items: List[str] = []
    extra_items: List[str] = []
    diff_items: List[str] = []

    for source_index, source_sentence in enumerate(source_sentences):
        struct_index, score = source_to_struct[source_index]
        if struct_index is None or score < ALIGNMENT_THRESHOLD:
            missing_items.append("原文未覆盖: {}".format(shorten_text(source_sentence)))
            continue
        reverse_index, reverse_score = struct_to_source[struct_index]
        if reverse_index is None or reverse_score < ALIGNMENT_THRESHOLD:
            missing_items.append("原文未覆盖: {}".format(shorten_text(source_sentence)))
            continue
        struct_sentence = struct_sentences[struct_index]
        if compact_text(source_sentence) != compact_text(struct_sentence):
            diff_items.append(
                "原文[{}] vs pptStruct[{}]，{}".format(
                    shorten_text(source_sentence),
                    shorten_text(struct_sentence),
                    summarize_char_diff(source_sentence, struct_sentence),
                )
            )

    for struct_index, struct_sentence in enumerate(struct_sentences):
        source_index, score = struct_to_source[struct_index]
        if source_index is None or score < ALIGNMENT_THRESHOLD:
            extra_items.append("pptStruct 额外内容: {}".format(shorten_text(struct_sentence)))

    incomplete_items = missing_items + extra_items
    diff_text_parts: List[str] = []
    if incomplete_items:
        diff_text_parts.append(short_join(incomplete_items, ""))
    if diff_items:
        diff_text_parts.append(short_join(diff_items, ""))
    diff_text = "\n".join(part for part in diff_text_parts if part)
    return {
        "struct_text": struct_text,
        "diff_text": diff_text,
    }


def build_llm_prompt(source_text: str, struct_text: str, compare_summary: str) -> str:
    return """你是一名严格的医学内容审核助手。
    请基于给定的PPT原文、pptStruct文本和差异摘要，判断问题类型、严重程度和依据。

输出要求：
1. 仅输出JSON，不要输出Markdown代码块。
2. JSON字段固定为：error_type, severity, basis, result。
3. error_type 从以下枚举中选一个或多个并用顿号连接：语义遗漏、语义冗余、事实错误、表述偏差、结构错位、无法判断。
4. severity 只能是：高、中、低。
5. 如果审核通过或未发现明显问题，basis 必须返回空字符串。
6. 只有判断存在不一致或风险时，basis 才填写中文简洁说明判断依据。
7. result 用中文总结审核意见。

PPT原文：
{source_text}

pptStruct文本：
{struct_text}

对比差异：
{compare_summary}
""".format(source_text=source_text, struct_text=struct_text, compare_summary=compare_summary)


def normalize_llm_json(content: str) -> Dict[str, str]:
    normalized = content.strip()
    normalized = re.sub(r"<think>.*?</think>", "", normalized, flags=re.DOTALL).strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.startswith("json"):
            normalized = normalized[4:].strip()
    parsed = json.loads(normalized)
    return {
        "error_type": str(parsed.get("error_type") or "无法判断"),
        "severity": str(parsed.get("severity") or "无法判断"),
        "basis": str(parsed.get("basis") or ""),
        "result": str(parsed.get("result") or ""),
    }


def call_llm_review(source_text: str, struct_text: str, compare_summary: str) -> Dict[str, str]:
    if not DEFAULT_LLM_API_KEY or "请在这里填写实际LLM_API_KEY" in DEFAULT_LLM_API_KEY:
        return {
            "error_type": "LLM未配置",
            "severity": "无法判断",
            "basis": "请先在代码中配置 DEFAULT_LLM_API_KEY",
            "result": "未执行LLM审核",
        }
    payload = {
        "model": DEFAULT_LLM_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": "你只返回JSON。"},
            {"role": "user", "content": build_llm_prompt(source_text, struct_text, compare_summary)},
        ],
    }
    last_error: Optional[Exception] = None
    for attempt in range(1, DEFAULT_LLM_MAX_RETRIES + 1):
        try:
            response = requests.post(
                DEFAULT_LLM_BASE_URL.rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": "Bearer {}".format(DEFAULT_LLM_API_KEY),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=DEFAULT_LLM_TIMEOUT_SECONDS,
            )
            if response.status_code in {429, 500, 502, 503, 504, 529}:
                raise RuntimeError(
                    "LLM 服务暂时不可用(status={}): {}".format(response.status_code, shorten_text(response.text, 300))
                )
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            return normalize_llm_json(content)
        except Exception as exc:
            last_error = exc
            if attempt >= DEFAULT_LLM_MAX_RETRIES:
                break
            logger.warning("LLM 调用第 {} 次失败，准备重试: {}", attempt, exc)
            time.sleep(attempt)
    raise RuntimeError(str(last_error))


def extract_source_text_for_row(
    ppt_path: Path,
    page_number: int,
    temp_root: Path,
    converted_cache: Dict[Path, Path],
    pdf_cache: Dict[Path, Path],
    presentation_cache: Dict[Path, Presentation],
    source_text_cache: Dict[Tuple[Path, int], str],
) -> str:
    cache_key = (ppt_path, page_number)
    source_text = source_text_cache.get(cache_key)
    if source_text is None:
        source_text = extract_slide_source_text(
            ppt_path=ppt_path,
            page_number=page_number,
            work_dir=temp_root,
            converted_cache=converted_cache,
            pdf_cache=pdf_cache,
            presentation_cache=presentation_cache,
        )
        source_text_cache[cache_key] = source_text
    return source_text


def run_deterministic_compare(source_text: str, ppt_struct_obj: Dict[str, object]) -> Dict[str, object]:
    return review_semantics(source_text, ppt_struct_obj)


def run_llm_compare(source_text: str, struct_text: str, diff_text: str) -> Dict[str, str]:
    if not diff_text:
        return {
            "error_type": "无",
            "severity": "低",
            "basis": "",
            "result": "未发现明显问题",
        }
    return call_llm_review(source_text, struct_text, diff_text)


def main() -> int:
    setup_logging()
    args = parse_args()
    excel_path = DEFAULT_EXCEL_PATH.expanduser().resolve()
    if "请在这里填写实际PPT目录" in str(DEFAULT_PPT_DIR):
        raise RuntimeError("请先在代码中配置 DEFAULT_PPT_DIR")
    ppt_dir = DEFAULT_PPT_DIR.expanduser().resolve()
    if not ppt_dir.exists():
        raise RuntimeError("PPT 目录不存在: {}".format(ppt_dir))
    workbook = load_workbook(excel_path)
    sheet = workbook[args.sheet_name] if args.sheet_name else workbook.active
    ppt_index = build_ppt_index(ppt_dir)
    header_map = find_header_columns(sheet)
    required_input_columns = require_columns(header_map, [FILE_NAME_HEADER, PAGE_NUMBER_HEADER, PPT_STRUCT_HEADER])
    source_text_column = ensure_output_column(sheet, header_map, PPT_SOURCE_HEADER, sheet.max_column + 1)
    diff_column = ensure_output_column(sheet, header_map, DIFF_HEADER, max(sheet.max_column + 1, source_text_column + 1))
    llm_error_type_column = ensure_output_column(sheet, header_map, LLM_ERROR_TYPE_HEADER, max(sheet.max_column + 1, diff_column + 1))
    llm_severity_column = ensure_output_column(sheet, header_map, LLM_SEVERITY_HEADER, max(sheet.max_column + 1, llm_error_type_column + 1))
    llm_basis_column = ensure_output_column(sheet, header_map, LLM_BASIS_HEADER, max(sheet.max_column + 1, llm_severity_column + 1))
    llm_result_column = ensure_output_column(sheet, header_map, LLM_RESULT_HEADER, max(sheet.max_column + 1, llm_basis_column + 1))
    sheet.column_dimensions[get_column_letter(diff_column)].width = 80
    sheet.column_dimensions[get_column_letter(llm_error_type_column)].width = 20
    sheet.column_dimensions[get_column_letter(llm_severity_column)].width = 12
    sheet.column_dimensions[get_column_letter(llm_basis_column)].width = 60
    sheet.column_dimensions[get_column_letter(llm_result_column)].width = 40

    with tempfile.TemporaryDirectory(prefix="ppt-semantic-review-") as temp_dir:
        temp_root = Path(temp_dir)
        converted_cache: Dict[Path, Path] = {}
        pdf_cache: Dict[Path, Path] = {}
        presentation_cache: Dict[Path, Presentation] = {}
        source_text_cache: Dict[Tuple[Path, int], str] = {}

        for row_index in range(2, sheet.max_row + 1):
            file_name = sheet.cell(row_index, required_input_columns[FILE_NAME_HEADER]).value
            page_number = normalize_page_number(sheet.cell(row_index, required_input_columns[PAGE_NUMBER_HEADER]).value)
            ppt_struct_raw = sheet.cell(row_index, required_input_columns[PPT_STRUCT_HEADER]).value
            if not file_name or page_number is None or not ppt_struct_raw:
                continue
            logger.info("processing row={} file={} page={}", row_index, file_name, page_number)

            ppt_path = ppt_index.get(normalize_name(str(file_name)))
            if not ppt_path:
                sheet.cell(row_index, diff_column).value = "未找到源PPT文件"
                sheet.cell(row_index, llm_error_type_column).value = "无法判断"
                sheet.cell(row_index, llm_severity_column).value = "无法判断"
                sheet.cell(row_index, llm_basis_column).value = "未找到源PPT文件"
                sheet.cell(row_index, llm_result_column).value = "未执行LLM审核"
                continue

            try:
                ppt_struct_obj = json.loads(str(ppt_struct_raw))
            except Exception as exc:
                sheet.cell(row_index, diff_column).value = "pptStruct 解析失败: {}".format(exc)
                sheet.cell(row_index, llm_error_type_column).value = "无法判断"
                sheet.cell(row_index, llm_severity_column).value = "无法判断"
                sheet.cell(row_index, llm_basis_column).value = "pptStruct 解析失败: {}".format(exc)
                sheet.cell(row_index, llm_result_column).value = "未执行LLM审核"
                continue

            try:
                # 第一步：提取 PPT 原文。这里失败，后面的确定性对比和 LLM 都不再执行。
                source_text = extract_source_text_for_row(
                    ppt_path=ppt_path,
                    page_number=page_number,
                    temp_root=temp_root,
                    converted_cache=converted_cache,
                    pdf_cache=pdf_cache,
                    presentation_cache=presentation_cache,
                    source_text_cache=source_text_cache,
                )
                sheet.cell(row_index, source_text_column).value = source_text
            except Exception as exc:
                sheet.cell(row_index, source_text_column).value = "PPT 原文提取失败: {}".format(exc)
                diff_text = "审核失败: {}".format(exc)
                llm_result = {
                    "error_type": "无法判断",
                    "severity": "无法判断",
                    "basis": "PPT 原文提取失败: {}".format(exc),
                    "result": "未执行LLM审核",
                }
                sheet.cell(row_index, diff_column).value = diff_text
                sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
                sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
                sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
                sheet.cell(row_index, llm_result_column).value = llm_result["result"]
                continue

            try:
                # 第二步：确定性对比。这里失败，则不再执行 LLM。
                compare_result = run_deterministic_compare(source_text, ppt_struct_obj)
                struct_text = compare_result["struct_text"]
                diff_text = compare_result["diff_text"]
            except Exception as exc:
                diff_text = "确定性对比失败: {}".format(exc)
                llm_result = {
                    "error_type": "无法判断",
                    "severity": "无法判断",
                    "basis": "确定性对比失败: {}".format(exc),
                    "result": "未执行LLM审核",
                }
                sheet.cell(row_index, diff_column).value = diff_text
                sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
                sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
                sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
                sheet.cell(row_index, llm_result_column).value = llm_result["result"]
                continue

            try:
                # 第三步：调用 LLM。只有前两步成功后才会进入这里。
                llm_result = run_llm_compare(source_text, struct_text, diff_text)
            except Exception as exc:
                llm_result = {
                    "error_type": "无法判断",
                    "severity": "无法判断",
                    "basis": "LLM 调用失败: {}".format(exc),
                    "result": "未执行LLM审核",
                }

            sheet.cell(row_index, diff_column).value = diff_text
            sheet.cell(row_index, llm_error_type_column).value = llm_result["error_type"]
            sheet.cell(row_index, llm_severity_column).value = llm_result["severity"]
            sheet.cell(row_index, llm_basis_column).value = llm_result["basis"]
            sheet.cell(row_index, llm_result_column).value = llm_result["result"]

    workbook.save(excel_path)
    logger.info("Excel 已更新: {}", excel_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
